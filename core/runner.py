"""Block executor.

Runs the Setup phase once, then the Loop phase repeatedly until stopped.
Everything happens on one daemon thread; Pause/Stop are honoured at a single
choke point (`_checkpoint`) called before every block and inside every wait,
so Stop lands during a 30-second wait rather than only after it.
"""
import random
import threading
import time

from . import blocks as blockmod
from . import capture
from . import keys as keymod
from . import ocr
from . import pacing
from . import templates as tpl
from . import timing
from . import vision
from . import window as wm
from .keyboard import Keyboard
from .mouse import Mouse


class _SkipRest(Exception):
    """A block asked to abandon the remaining blocks of this pass."""


class _StopRun(Exception):
    """A block asked to end the whole run."""


class _RestartPhase(Exception):
    """A block asked to start this phase again from the top."""


class _RestartRun(Exception):
    """A block asked to start the whole macro again, Setup included."""


class _MissingTemplate:
    """Sentinel: distinguishes 'no reference image on disk' from 'looked for
    it and it never showed up'. Both fail the block, but only one is a
    configuration mistake worth naming in the log."""

    def __repr__(self):
        return "<missing template>"


_MISSING_TEMPLATE = _MissingTemplate()

# A fallback sequence may itself contain vision blocks with fallbacks. One
# level of nesting is useful; unbounded nesting is a trace nobody can follow.
_MAX_FALLBACK_DEPTH = 3

# Guards "restart phase" against a condition that never clears.
_MAX_PHASE_RESTARTS = 50

# Same, for "restart macro" -- lower, because a whole-macro restart is a much
# heavier loop to be stuck in.
_MAX_RUN_RESTARTS = 20


class _PauseAwareGate:
    """Duck-types threading.Event for the vision helpers.

    Those helpers only ever ask `is_set()` to decide whether to abort, so
    they were blind to Pause: a paused run kept polling and, worse,
    click_image could fire a real click the moment its image appeared.
    Blocking here parks the poll loop for the whole pause and still reports
    Stop immediately.
    """

    def __init__(self, stop_event, pause_event):
        self._stop = stop_event
        self._pause = pause_event

    def is_set(self) -> bool:
        while self._pause.is_set() and not self._stop.is_set():
            time.sleep(0.08)
        return self._stop.is_set()


class MacroRunner:
    def __init__(self, log=None, set_status=None):
        self._log = log or (lambda msg: None)
        self._set_status = set_status or (lambda **kw: None)
        self._thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        # Handed to the vision helpers instead of the bare stop event so
        # their poll loops honour Pause as well as Stop.
        self._gate = _PauseAwareGate(self._stop_event, self._pause_event)
        self._stop_logged = False
        self._held_keys = set()
        self._held_buttons = set()
        self.mouse = Mouse()
        self.keyboard = Keyboard()
        self._hwnd = 0
        self._coord_space = "window"
        self._loop_index = 0
        self._phase_label = ""
        self._phase_key = ""
        self._fallback_depth = 0
        # Tracks whether the target was ever alive this run, so a target that
        # dies mid-run is distinguishable from one that was never there.
        self._target_was_alive = False

    # ------------------------------------------------------------ lifecycle

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def start(self, macro: dict, hwnd=0, coord_space: str = "window",
              loop_forever: bool = True, loop_count: int = 1) -> dict:
        if self.is_running():
            return {"ok": False, "reason": "already_running"}
        self._stop_event.clear()
        self._pause_event.clear()
        self._stop_logged = False
        self._hwnd = int(hwnd or 0)
        self._coord_space = coord_space
        self._loop_index = 0
        self._target_was_alive = bool(
            coord_space == "window" and self._hwnd and wm.is_window(self._hwnd))
        self._fallback_depth = 0
        self._thread = threading.Thread(
            target=self._run_session,
            args=(macro, bool(loop_forever), int(loop_count)),
            daemon=True)
        self._thread.start()
        return {"ok": True}

    def stop(self) -> dict:
        self._stop_event.set()
        # Clear pause too: a paused thread would otherwise park forever and
        # never reach the stop check.
        self._pause_event.clear()
        return {"ok": True}

    def pause(self) -> dict:
        self._pause_event.set()
        self._set_status(paused=True)
        return {"ok": True}

    def resume(self) -> dict:
        self._pause_event.clear()
        self._set_status(paused=False)
        return {"ok": True}

    def toggle_pause(self) -> dict:
        return self.resume() if self.is_paused() else self.pause()

    # ------------------------------------------------------------- plumbing

    def _checkpoint(self) -> bool:
        """The universal gate. Blocks while paused, returns True on stop."""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.08)
        if self._stop_event.is_set():
            if not self._stop_logged:
                self._stop_logged = True
                self._log("Stopped.")
            return True
        return False

    def _abort_now(self) -> bool:
        """Abort predicate for the timing helpers: honours Pause by blocking,
        and reports Stop."""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.05)
        return self._stop_event.is_set()

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep in slices, so Stop cuts into a long wait."""
        deadline = time.time() + max(0.0, seconds)
        while time.time() < deadline:
            if self._checkpoint():
                return True
            time.sleep(min(0.08, max(0.0, deadline - time.time())))
        return False

    def _release_all(self) -> None:
        """Nothing may stay physically held after a run ends -- a stuck W key
        would keep walking in the game long after Stop."""
        for vk in list(self._held_keys):
            try:
                self.keyboard.key_up(vk)
            except Exception:
                pass
        self._held_keys.clear()
        for button in list(self._held_buttons):
            try:
                self.mouse.up(button)
            except Exception:
                pass
        self._held_buttons.clear()

    def _window_alive(self) -> bool:
        """Whether the window-relative coordinate space is still usable.

        The FIRST time a live target disappears mid-run this stops the run:
        silently reinterpreting window-client coordinates as absolute screen
        coordinates would keep clicking, just in the wrong place on the
        desktop -- clicks landing on whatever happens to be there.
        """
        if self._coord_space != "window":
            return False
        if self._hwnd and wm.is_window(self._hwnd):
            return True
        if not self._target_was_alive:
            return False
        self._target_was_alive = False
        self._log("Target window disappeared -- stopping so clicks cannot "
                  "land on whatever is behind it.")
        self._stop_event.set()
        return False

    def _to_screen(self, x, y):
        """Block coordinates -> absolute screen pixels."""
        if self._window_alive():
            try:
                return wm.client_to_screen(self._hwnd, int(x), int(y))
            except Exception:
                pass
        return int(x), int(y)

    def _target(self):
        """hwnd to capture from, or 0 for full-screen mode."""
        return self._hwnd if self._window_alive() else 0

    # ------------------------------------------------------------- run loop

    def _run_session(self, macro: dict, loop_forever: bool, loop_count: int) -> None:
        try:
            self._run(macro, loop_forever, loop_count)
        except Exception as exc:
            self._log("Runner error: %s" % exc)
        finally:
            self._release_all()
            capture.close_mss()
            self._set_status(running=False, paused=False, action="Idle")
            self._log("Run finished.")

    def _run(self, macro: dict, loop_forever: bool, loop_count: int) -> None:
        """Outer shell: honours a "restart macro" fallback by starting the
        whole thing again, Setup included. Bounded for the same reason phase
        restarts are -- a condition that never clears must not spin silently.
        """
        restarts = 0
        while True:
            try:
                self._run_once(macro, loop_forever, loop_count)
                return
            except _RestartRun:
                restarts += 1
                if restarts > _MAX_RUN_RESTARTS:
                    self._log("Restarted the macro %d times -- giving up."
                              % _MAX_RUN_RESTARTS)
                    return
                self._log("Restarting the whole macro (%d)." % restarts)
                self._release_all()
                if self._checkpoint():
                    return

    def _run_once(self, macro: dict, loop_forever: bool, loop_count: int) -> None:
        phases = (macro or {}).get("phases") or {}
        # Phase identity comes from the catalog, not from string literals
        # repeated here: the UI builds its columns from the same constants,
        # so renaming a phase cannot leave one side executing nothing.
        once_key = blockmod.PHASE_ONCE
        repeat_key = blockmod.PHASE_REPEAT
        setup = blockmod.normalize_list(phases.get(once_key))
        loop = blockmod.normalize_list(phases.get(repeat_key))

        if not setup and not loop:
            self._log("Nothing to run -- both phases are empty.")
            return

        self._set_status(running=True, paused=False, action="Starting", loop=0)
        self._log("Run started (%d %s, %d %s blocks)."
                  % (len(setup), once_key, len(loop), repeat_key))

        if self._hwnd and wm.is_window(self._hwnd):
            title = wm.get_window_title(self._hwnd)
            self._log("Target: %s" % (title or self._hwnd))
            wm.activate_window(self._hwnd)
            time.sleep(0.25)
        elif self._coord_space == "window":
            self._log("Target window is gone -- using screen coordinates.")

        if setup:
            self._set_status(action=blockmod.PHASE_LABELS[once_key])
            if self._run_phase_once(setup, once_key) == "stop":
                return
            if self._stop_event.is_set():
                return

        if not loop:
            return

        passes = 0
        while not self._stop_event.is_set():
            passes += 1
            self._loop_index = passes
            self._set_status(action=blockmod.PHASE_LABELS[repeat_key], loop=passes)
            if self._run_phase_once(loop, repeat_key) == "stop":
                return
            if not loop_forever and passes >= max(1, loop_count):
                self._log("Reached %d loop pass(es)." % passes)
                return

    def _run_phase_once(self, block_list, phase_key: str) -> str:
        """Run one pass of a phase, honouring a "restart phase" fallback.

        Restarts are bounded: a condition that never clears would otherwise
        spin the same pass forever with no way to tell from the log.
        """
        restarts = 0
        while True:
            try:
                self._run_blocks(block_list, phase_key)
                return "done"
            except _SkipRest:
                return "done"
            except _StopRun:
                return "stop"
            except _RestartRun:
                raise                    # handled by _run, not here
            except _RestartPhase:
                restarts += 1
                if restarts > _MAX_PHASE_RESTARTS:
                    self._log("Restarted %s %d times without getting through -- "
                              "giving up on this pass."
                              % (blockmod.PHASE_LABELS.get(phase_key, phase_key),
                                 _MAX_PHASE_RESTARTS))
                    return "done"
                self._log("   restarting %s from the top (%d)"
                          % (blockmod.PHASE_LABELS.get(phase_key, phase_key), restarts))
                if self._checkpoint():
                    return "stop"

    def _run_blocks(self, phase_key_blocks, phase_key: str, label: str = None) -> None:
        """Sequential execution with a loop_start/loop_end stack.

        The stack holds [index_of_loop_start, remaining_iterations], so
        nesting works and a malformed list (loop_end without a start) is
        simply ignored rather than raising.
        """
        block_list = phase_key_blocks
        phase_label = label or blockmod.PHASE_LABELS.get(phase_key, phase_key)
        is_repeating = (phase_key == blockmod.PHASE_REPEAT)
        # Remembered so a nested run (a recording's edited actions) inherits
        # the phase it was invoked from rather than guessing.
        self._phase_key = phase_key
        stack = []
        index = 0
        step = 0
        guard = 0
        while index < len(block_list):
            guard += 1
            if guard > 100000:
                # Truncating the phase and continuing meant a runaway nested
                # loop simply restarted next pass, forever. Stop the run.
                self._log("Loop guard tripped -- stopping the run.")
                self._stop_event.set()
                raise _StopRun()
            if self._checkpoint():
                return

            block = block_list[index]
            btype = block["type"]

            # Flow-control markers are structural: honouring `enabled` or
            # `once` on them would desynchronise the stack and silently
            # change the body's repeat count instead of skipping a step.
            is_flow = btype in ("loop_start", "loop_end")
            if not is_flow:
                if not block.get("enabled", True):
                    self._log("   - skipped (disabled): %s" % blockmod.summarise(block))
                    index += 1
                    continue
                if block.get("once") and is_repeating and self._loop_index > 1:
                    self._log("   - skipped (ONCE, already ran): %s"
                              % blockmod.summarise(block))
                    index += 1
                    continue

            if btype == "loop_start":
                try:
                    count = max(1, int(block["params"].get("count", 1) or 1))
                except (TypeError, ValueError):
                    # One malformed count must cost one block, not the run.
                    self._log("Loop Start has a bad count -- using 1.")
                    count = 1
                stack.append([index, count - 1])
                index += 1
                continue

            if btype == "loop_end":
                if stack and stack[-1][1] > 0:
                    stack[-1][1] -= 1
                    index = stack[-1][0] + 1
                    continue
                if stack:
                    stack.pop()
                index += 1
                continue

            step += 1
            summary = blockmod.summarise(block)
            self._set_status(action="%s #%d %s" % (phase_label, step,
                                                   blockmod.BY_TYPE[btype]["label"]))
            # Every executed block is logged, with its real parameters, so the
            # journal is a readable trace of what the macro actually did
            # rather than only what went wrong.
            started = time.time()
            self._log("%s #%d  %s" % (phase_label, step, summary))
            try:
                self._execute(block)
            except (_SkipRest, _StopRun, _RestartPhase, _RestartRun):
                raise
            except Exception as exc:
                self._log("   ! %s failed: %s" % (btype, exc))
            else:
                elapsed = time.time() - started
                # Only worth reporting when the block actually took time --
                # a "took 0ms" line under every instant click is noise.
                if elapsed >= 0.4:
                    self._log("   took %.1fs" % elapsed)
            index += 1

    # ------------------------------------------------------------ dispatch

    def _execute(self, block: dict) -> None:
        handler = getattr(self, "_do_" + block["type"], None)
        if handler is None:
            self._log("No handler for block type %s" % block["type"])
            return
        handler(block["params"])

    def _fail(self, params: dict, message: str) -> None:
        """Apply the block's on_fail policy.

        The option strings are read loosely (spaces or underscores) so a macro
        saved before the wording changed keeps working.
        """
        mode = str(params.get("on_fail") or "continue").strip().lower().replace(" ", "_")
        self._log(message)

        if mode == "run_blocks":
            fallback = blockmod.normalize_list(params.get("on_fail_blocks"))
            if not fallback:
                self._log("   (no fallback blocks -- continuing)")
                return
            self._log("   running %d fallback block(s)" % len(fallback))
            # Nested one level only: a fallback that could itself restart the
            # phase from inside a fallback is a loop nobody can follow.
            depth = self._fallback_depth
            if depth >= _MAX_FALLBACK_DEPTH:
                self._log("   fallback nested too deep -- skipping")
                return
            self._fallback_depth = depth + 1
            try:
                self._run_blocks(fallback, self._phase_key or blockmod.PHASE_REPEAT,
                                 label="Fallback")
            finally:
                self._fallback_depth = depth

            # What to do now that the fallback is done. Default is to resume
            # the main sequence where it left off.
            after = str(params.get("on_fail_after")
                        or "continue main").strip().lower().replace(" ", "_")
            if after == "restart_phase":
                self._log("   fallback done -- restarting the phase")
                raise _RestartPhase()
            if after == "restart_macro":
                self._log("   fallback done -- restarting the macro")
                raise _RestartRun()
            if after == "stop":
                self._log("   fallback done -- stopping")
                self._stop_event.set()
                raise _StopRun()
            return

        if mode == "restart_phase":
            raise _RestartPhase()
        if mode == "skip_rest":
            raise _SkipRest()
        if mode == "stop":
            self._stop_event.set()
            raise _StopRun()

    def _colour_tolerance(self, params: dict, default_confidence: float) -> int:
        """Per-channel tolerance from the block's Confidence.

        Colour matching is expressed on the same 0-1 scale as image and text
        matching so every Vision block reads the same way: 1.0 is an exact
        colour, lower is more forgiving. A macro saved before this change
        carries a raw 0-255 `tolerance` instead, which still wins.
        """
        legacy = params.get("tolerance")
        if legacy is not None and legacy != "":
            try:
                return max(0, min(255, int(float(legacy))))
            except (TypeError, ValueError):
                pass
        confidence = self._num(params, "confidence", default_confidence)
        confidence = max(0.0, min(1.0, confidence))
        return int(round((1.0 - confidence) * 255))

    @staticmethod
    def _num(params: dict, key: str, default):
        """Numeric param with an explicit None check.

        `params.get(k) or default` turns a legitimate 0 into the default: a
        timeout of 0 means "check once, don't wait", and a hold of 0 means
        "tap instantly" -- both were silently replaced by 8000ms and 30ms.
        """
        value = params.get(key)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    # --------------------------------------------------------------- mouse

    def _do_click(self, params) -> None:
        x, y = self._to_screen(params.get("x", 0), params.get("y", 0))
        button = str(params.get("button") or "left")
        # Registered before the call so _release_all can recover the button
        # if SendInput refuses the button_up (elevated window, secure desktop).
        self._held_buttons.add(button)
        try:
            self.mouse.multi_click(x, y, button,
                                   int(self._num(params, "clicks", 1)),
                                   max(0.0, self._num(params, "hold_ms", 40) / 1000.0))
        finally:
            self._held_buttons.discard(button)

    def _do_move(self, params) -> None:
        x, y = self._to_screen(params.get("x", 0), params.get("y", 0))
        duration = max(0.0, self._num(params, "duration_ms", 0)) / 1000.0
        if duration <= 0:
            self.mouse.move_to(x, y)
            return
        sx, sy = self.mouse.position()
        steps = max(2, int(duration * 60))
        for i in range(1, steps + 1):
            if self._checkpoint():
                return
            t = i / steps
            self.mouse.move_to(int(sx + (x - sx) * t), int(sy + (y - sy) * t))
            time.sleep(duration / steps)

    def _do_drag(self, params) -> None:
        x1, y1 = self._to_screen(params.get("x", 0), params.get("y", 0))
        x2, y2 = self._to_screen(params.get("x2", 0), params.get("y2", 0))
        button = str(params.get("button") or "left")
        self._held_buttons.add(button)
        try:
            self.mouse.drag(x1, y1, x2, y2, button,
                            duration=max(0.0, self._num(params, "duration_ms", 250) / 1000.0))
        finally:
            self._held_buttons.discard(button)

    def _do_scroll(self, params) -> None:
        x = params.get("x")
        y = params.get("y")
        # `is not None`, not truthiness: (0, 0) is a legal coordinate (the
        # target's top-left corner), and treating it as "unset" made that one
        # spot unreachable while every other coordinate worked.
        if x is not None or y is not None:
            sx, sy = self._to_screen(x or 0, y or 0)
            self.mouse.move_to(sx, sy)
            time.sleep(0.03)
        self.mouse.scroll(int(self._num(params, "amount", 0)))
        pacing.action_pause()

    # ------------------------------------------------------------ keyboard

    def _do_send_key(self, params) -> None:
        name = params.get("key")
        vk = keymod.key_name_to_vk(name)
        if vk is None:
            self._log("Unknown key: %r" % (name,))
            return
        modifiers = [keymod.MODIFIER_NAMES[m] for m in (params.get("modifiers") or [])
                     if m in keymod.MODIFIER_NAMES]
        hold = max(0.0, self._num(params, "hold_ms", 30) / 1000.0)
        # Registered so _release_all can recover the key if the key_up is
        # refused mid-tap.
        self._held_keys.add(vk)
        try:
            if modifiers:
                self.keyboard.combo(*(modifiers + [vk]), hold=hold)
            else:
                self.keyboard.tap(vk, hold)
        finally:
            self._held_keys.discard(vk)

    def _do_hold_key(self, params) -> None:
        vk = keymod.key_name_to_vk(params.get("key"))
        if vk is None:
            self._log("Unknown key: %r" % (params.get("key"),))
            return
        self._held_keys.add(vk)
        try:
            self.keyboard.key_down(vk)
            # Default matches the catalog's 1000ms. It used to fall back to 0,
            # so a hold with a blank duration pressed and released instantly.
            self._sleep(max(0.0, self._num(params, "hold_ms", 1000) / 1000.0))
        finally:
            # finally, not after: a Stop mid-hold must still release the key.
            self.keyboard.key_up(vk)
            self._held_keys.discard(vk)
        pacing.action_pause()

    def _do_type_text(self, params) -> None:
        self.keyboard.type_text(str(params.get("text") or ""),
                                max(0.0, self._num(params, "delay_ms", 20) / 1000.0),
                                stop_event=self._stop_event)

    # -------------------------------------------------------------- timing

    def _do_wait_ms(self, params) -> None:
        self._sleep(max(0, int(params.get("ms") or 0)) / 1000.0)

    def _do_wait_random(self, params) -> None:
        low = max(0, int(params.get("min_ms") or 0))
        high = max(low, int(params.get("max_ms") or low))
        self._sleep(random.randint(low, high) / 1000.0)

    # -------------------------------------------------------------- vision

    @staticmethod
    def _region(params):
        region = params.get("region")
        if not region:
            return None
        try:
            x, y, w, h = [int(v) for v in region]
        except (TypeError, ValueError):
            return None
        return (x, y, w, h) if w > 0 and h > 0 else None

    def _wait_image(self, params, name: str):
        """Shared wait used by the image blocks.

        A missing reference PNG (typo'd name, deleted file) must go through
        the block's own on_fail policy, NOT escape as an exception -- letting
        TemplateNotFound propagate turned a configured `stop` into a silent
        `continue`, because _run_blocks catches every stray exception.

        Returns the match, or the sentinel MISSING when there is no template
        on disk at all, so the caller can word its message accordingly.
        """
        try:
            return vision.wait_for_image(
                self._target(), name, self._region(params),
                self._num(params, "threshold", vision.DEFAULT_THRESHOLD),
                max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0),
                stop_event=self._gate)
        except vision.TemplateNotFound:
            return _MISSING_TEMPLATE

    def _do_wait_image(self, params) -> None:
        name = str(params.get("template") or "")
        if not name:
            return
        match = self._wait_image(params, name)
        if match is _MISSING_TEMPLATE:
            self._fail(params, "No image named '%s' in Assets -- capture it first." % name)
        elif match is None:
            self._fail(params, "Image '%s' did not appear." % name)
        else:
            self._log("Found '%s' (%.2f)." % (name, match["score"]))

    def _do_click_image(self, params) -> None:
        name = str(params.get("template") or "")
        if not name:
            return
        match = self._wait_image(params, name)
        if match is _MISSING_TEMPLATE:
            self._fail(params, "No image named '%s' in Assets -- nothing clicked." % name)
            return
        if match is None:
            self._fail(params, "Image '%s' not found -- nothing clicked." % name)
            return
        # Re-gate before acting: the image may have appeared at the exact
        # moment the user hit Pause or Stop, and a click is not undoable.
        if self._checkpoint():
            return
        cx = match["cx"] + int(self._num(params, "offset_x", 0))
        cy = match["cy"] + int(self._num(params, "offset_y", 0))
        sx, sy = self._to_screen(cx, cy)
        button = str(params.get("button") or "left")
        self._held_buttons.add(button)
        try:
            self.mouse.click(sx, sy, button)
        finally:
            self._held_buttons.discard(button)
        self._log("Clicked '%s' at %d,%d (%.2f)." % (name, cx, cy, match["score"]))

    def _do_wait_image_gone(self, params) -> None:
        name = str(params.get("template") or "")
        if not name:
            return
        try:
            gone = vision.wait_for_image_gone(
                self._target(), name, self._region(params),
                self._num(params, "threshold", vision.DEFAULT_THRESHOLD),
                max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0),
                stop_event=self._gate)
        except vision.TemplateNotFound:
            # Nothing to look for means nothing can be on screen. Log it so a
            # typo is visible, but treat the condition as satisfied.
            self._log("No image named '%s' in Assets -- treating as already gone." % name)
            return
        if not gone:
            self._fail(params, "Image '%s' is still on screen." % name)

    def _do_wait_color(self, params) -> None:
        rgb = _hex_to_rgb(params.get("color"))
        ok = vision.wait_for_color(
            self._target(), int(self._num(params, "x", 0)),
            int(self._num(params, "y", 0)), rgb,
            self._colour_tolerance(params, 0.92),
            max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0),
            stop_event=self._gate)
        if not ok:
            self._fail(params, "Color %s never appeared at %s,%s."
                       % (params.get("color"), params.get("x"), params.get("y")))

    def _do_wait_text(self, params) -> None:
        needle = str(params.get("text") or "")
        if not needle:
            return
        exact = str(params.get("match") or "contains") == "exact"
        confidence = max(0.0, min(1.0, self._num(params, "confidence", 0.75)))
        deadline = time.time() + max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0)
        while time.time() < deadline:
            if self._checkpoint():
                return
            frame = capture.capture_target_bgr(self._target(), self._region(params))
            if frame is not None:
                if exact:
                    text = ocr.read_text(frame)
                    if text.strip().lower() == needle.lower():
                        self._log("Text matched exactly: %r" % text.strip())
                        return
                else:
                    hit = ocr.find_text(frame, needle, confidence)
                    if hit:
                        self._log("Text matched: %r (%.2f)" % (hit["text"], hit["score"]))
                        return
            time.sleep(0.35)
        self._fail(params, "Text %r not found." % needle)

    def _do_click_text(self, params) -> None:
        """OCR the region, locate the words, click them.

        Uses find_text rather than read_text because a click needs a
        POSITION, not just a yes/no -- and fuzzy matching matters here: OCR
        routinely returns a Cyrillic С in "Continue" or drops a letter, and
        an exact-only search would report visible text as absent.
        """
        needle = str(params.get("text") or "")
        if not needle:
            return
        confidence = max(0.0, min(1.0, self._num(params, "confidence", 0.75)))
        region = self._region(params)
        deadline = time.time() + max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0)
        hit = None
        while time.time() < deadline:
            if self._checkpoint():
                return
            frame = capture.capture_target_bgr(self._target(), region)
            if frame is not None:
                hit = ocr.find_text(frame, needle, confidence)
                if hit:
                    break
            time.sleep(0.35)

        if not hit:
            self._fail(params, "Text %r not found -- nothing clicked." % needle)
            return
        if self._checkpoint():
            return

        ox, oy = (int(region[0]), int(region[1])) if region else (0, 0)
        cx = hit["cx"] + ox + int(self._num(params, "offset_x", 0))
        cy = hit["cy"] + oy + int(self._num(params, "offset_y", 0))
        sx, sy = self._to_screen(cx, cy)
        button = str(params.get("button") or "left")
        self._held_buttons.add(button)
        try:
            self.mouse.click(sx, sy, button)
        finally:
            self._held_buttons.discard(button)
        self._log("Clicked text %r at %d,%d (%.2f)" % (hit["text"], cx, cy, hit["score"]))

    def _do_click_color(self, params) -> None:
        """Find the largest blob of a colour and click its centre.

        Cheaper than template matching and survives things that change shape
        but not hue -- a highlighted tile, a coloured button that resizes.
        """
        rgb = _hex_to_rgb(params.get("color"))
        region = self._region(params)
        tolerance = self._colour_tolerance(params, 0.90)
        min_pixels = int(self._num(params, "min_pixels", 40))
        deadline = time.time() + max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0)
        found = None
        while time.time() < deadline:
            if self._checkpoint():
                return
            found = vision.find_color_region(self._target(), region, rgb,
                                             tolerance, min_pixels)
            if found:
                break
            time.sleep(0.25)

        if not found:
            self._fail(params, "Colour %s not found -- nothing clicked."
                       % params.get("color"))
            return
        if self._checkpoint():
            return

        cx = found["cx"] + int(self._num(params, "offset_x", 0))
        cy = found["cy"] + int(self._num(params, "offset_y", 0))
        sx, sy = self._to_screen(cx, cy)
        button = str(params.get("button") or "left")
        self._held_buttons.add(button)
        try:
            self.mouse.click(sx, sy, button)
        finally:
            self._held_buttons.discard(button)
        self._log("Clicked colour %s at %d,%d (%d px)"
                  % (params.get("color"), cx, cy, found["area"]))

    def _do_read_text(self, params) -> None:
        frame = capture.capture_target_bgr(self._target(), self._region(params))
        self._log("Read: %r" % ocr.read_text(frame).strip())

    # ---------------------------------------------------------------- flow

    def _do_focus_window(self, params) -> None:
        if not (self._hwnd and wm.is_window(self._hwnd)):
            self._log("No target window to focus.")
            return
        wm.activate_window(self._hwnd)
        time.sleep(0.2)

        resize = bool(params.get("resize"))
        move = bool(params.get("move"))
        if not (resize or move):
            return

        try:
            left, top, right, bottom = wm.get_window_rect(self._hwnd)
        except Exception:
            left = top = 0
            right = bottom = 0

        if resize:
            # The width/height the user types is the CLIENT area -- that is
            # what every coordinate in the macro is measured against. Sizing
            # the outer frame instead would leave clicks off by the border.
            width = max(100, int(self._num(params, "width", 1280)))
            height = max(100, int(self._num(params, "height", 720)))
            outer_w, outer_h = wm.client_size_to_window_size(self._hwnd, width, height)
        else:
            outer_w, outer_h = right - left, bottom - top

        if move:
            x = int(self._num(params, "x", 0))
            y = int(self._num(params, "y", 0))
        else:
            x, y = left, top

        wm.move_window(self._hwnd, x, y, outer_w, outer_h)
        time.sleep(0.25)
        got_w, got_h = wm.get_client_size(self._hwnd)
        if resize and (abs(got_w - width) > 2 or abs(got_h - height) > 2):
            # Plenty of windows refuse a size (fixed dialogs, fullscreen
            # games). Saying so beats every later click silently missing.
            self._log("Target would not resize to %dx%d -- it is %dx%d."
                      % (width, height, got_w, got_h))
        else:
            self._log("Target now %dx%d at %d,%d." % (got_w, got_h, x, y))

    def _do_log(self, params) -> None:
        self._log(str(params.get("text") or ""))

    def _do_send_webhook(self, params) -> None:
        """Post a message to the configured Discord webhook.

        The URL lives in Settings, not in the block: a macro can then be
        exported and shared without leaking the secret.
        """
        from . import settings as settingsmod
        from . import webhook as hook

        cfg = settingsmod.load()
        if not cfg.get("webhook_enabled"):
            self._log("Webhook is switched off in Settings -- nothing sent.")
            return
        url = str(cfg.get("webhook_url") or "")
        check = hook.validate(url)
        if not check["valid"]:
            self._log("Webhook URL is not usable (%s) -- nothing sent." % check["reason"])
            return

        source = str(params.get("source") or "none").strip().lower()
        image = None
        label = "no attachment"
        if source in ("target window", "whole screen", "region"):
            hwnd = self._target() if source == "target window" else 0
            region = self._region(params) if source == "region" else None
            frame = capture.capture_target_bgr(hwnd, region)
            if frame is None:
                self._log("Could not capture the %s -- sending text only." % source)
            else:
                image = hook.shrink_to_limit(frame)
                label = "%s (%dx%d)" % (source, frame.shape[1], frame.shape[0])
        elif source == "saved image":
            name = str(params.get("template") or "")
            paths = vision.template_variant_paths(name)
            if not paths:
                self._log("No saved image named '%s' -- sending text only." % name)
            else:
                img = vision.imread_unicode(paths[0])
                image = hook.encode_png(img)
                label = "image '%s'" % name

        result = hook.send(url, str(params.get("message") or ""), image,
                           username=str(cfg.get("webhook_username") or "") or "Macro Studio")
        if result.get("ok"):
            self._log("Webhook sent (%s)." % label)
        else:
            self._log("Webhook failed: %s" % result.get("reason"))

    def _do_playback(self, params) -> None:
        """Play a saved recording.

        Two modes, decided by the recording itself:

        * if it carries an EDITED action list, those blocks are executed --
          this is what the block's "Edit actions" editor writes back;
        * otherwise the raw events are replayed verbatim at their original
          timing, which preserves camera drags and timing-sensitive
          sequences far better than tidied-up blocks.
        """
        name = str(params.get("recording") or "")
        if not name:
            return
        data = tpl.load_recording(name) or {}

        edited = data.get("blocks")
        # `is not None`, NOT truthiness: an EMPTY edited list means "the user
        # deleted every action", which must do nothing. Treating [] as "no
        # edits" silently replayed the whole original recording instead --
        # every click they had just deleted fired again.
        if edited is not None:
            actions = blockmod.normalize_list(edited)
            if actions:
                self._log("Playing '%s' (%d edited actions)" % (name, len(actions)))
                # Runs through the normal block machinery, so loops, on_fail
                # policies and per-block logging all work inside a recording.
                self._run_blocks(actions, self._phase_key or blockmod.PHASE_REPEAT)
                return
            self._log("Recording '%s' has an empty action list -- nothing to do." % name)
            return

        events = data.get("events") or []
        if not events:
            self._log("Recording '%s' is empty." % name)
            return
        self._log("Playing '%s' (%d raw events)" % (name, len(events)))
        speed = max(0.05, self._num(params, "speed", 1.0))
        ordered = sorted(events, key=lambda e: e.get("t", 0.0))
        try:
            # Scheduled against ONE absolute start time, not a chain of
            # per-event sleeps. Sleeping each gap separately makes every
            # overshoot permanent, and on Windows (15.6ms default timer
            # granularity) a recording sampled every few ms drifts seconds
            # behind and replays visibly jerkily. `precision` also asks the OS
            # for 1ms granularity so the short gaps are honoured at all.
            with timing.precision():
                start = timing.now()
                for ev in ordered:
                    if self._checkpoint():
                        break
                    deadline = start + float(ev.get("t", 0.0)) / speed
                    if timing.sleep_until(deadline, self._abort_now):
                        break
                    self._replay_event(ev)
        finally:
            # finally, not after the loop: an exception mid-replay would
            # otherwise leave every key and button the recording had pressed
            # physically held for the rest of the run.
            self._release_all()

    def _replay_event(self, ev: dict) -> None:
        etype = ev.get("type")
        if etype in ("move", "mouse_down", "mouse_up"):
            # Recordings carry BOTH spaces: client x/y and raw screen sx/sy.
            # In screen mode (or once the window is gone) the client values
            # are meaningless, so the screen pair is the one to use.
            if self._window_alive():
                x, y = self._to_screen(ev.get("x", 0), ev.get("y", 0))
            else:
                x = int(ev.get("sx", ev.get("x", 0)))
                y = int(ev.get("sy", ev.get("y", 0)))
            if etype == "move":
                self.mouse.move_to(x, y)
                return
            button = str(ev.get("button") or "left")
            self.mouse.move_to(x, y)
            if etype == "mouse_down":
                self.mouse.down(button)
                self._held_buttons.add(button)
            else:
                self.mouse.up(button)
                self._held_buttons.discard(button)
            return
        if etype == "drag_deltas":
            # Relative moves, replayed at their recorded pace. Absolute moves
            # would be wrong here: this event only exists because the cursor
            # was NOT moving -- the game had it captured and was reading raw
            # hardware deltas to turn the camera.
            deltas = ev.get("deltas") or []
            if not deltas:
                return
            start = timing.now()
            for item in deltas:
                if self._checkpoint():
                    return
                try:
                    dx, dy, at = int(item[0]), int(item[1]), float(item[2])
                except (TypeError, ValueError, IndexError):
                    continue
                if timing.sleep_until(start + at, self._abort_now):
                    return
                self.mouse.nudge(dx, dy)
            return

        if etype == "scroll":
            self.mouse.scroll(int(ev.get("dy", 0)) * 120)
            return
        if etype in ("key_down", "key_up"):
            # Prefer the VK the recorder captured: it is the physical key, so
            # it survives a layout change between recording and replay. The
            # name lookup is only the fallback for hand-written recordings.
            vk = ev.get("vk")
            try:
                vk = int(vk) if vk is not None else None
            except (TypeError, ValueError):
                vk = None
            if vk is None:
                vk = keymod.key_name_to_vk(ev.get("key"))
            if vk is None:
                return
            if etype == "key_down":
                self.keyboard.key_down(vk)
                self._held_keys.add(vk)
            else:
                self.keyboard.key_up(vk)
                self._held_keys.discard(vk)


def _hex_to_rgb(value):
    text = str(value or "#ffffff").lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255
