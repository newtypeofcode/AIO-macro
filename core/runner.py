"""Block executor.

Runs the Setup phase once, then the Loop phase repeatedly until stopped.
Everything happens on one daemon thread; Pause/Stop are honoured at a single
choke point (`_checkpoint`) called before every block and inside every wait,
so Stop lands during a 30-second wait rather than only after it.
"""
import random
import re
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
from .i18n import tr
from .keyboard import Keyboard
from .mouse import Mouse


_NUMERIC_COMPARE = ("greater", "greater or equal", "less", "less or equal",
                    ">", ">=", "<", "<=")


def _as_number(text):
    """First number in an OCR string, or None.

    OCR hands back things like "Wave 12", "$1,250" or "1 250", so digits are
    picked out of the noise and space/apostrophe thousands separators are
    dropped. A comma is treated as a thousands separator only when exactly
    three digits follow it, otherwise as a decimal point ("1,5").
    """
    s = str(text or "").strip().lower()
    match = re.search(r"-?\d[\d\s.,']*", s)
    if not match:
        return None
    body = match.group(0).replace(" ", "").replace("'", "").rstrip(".,")
    if "," in body and "." in body:
        body = body.replace(",", "")
    elif "," in body:
        head, _, tail = body.rpartition(",")
        body = head + ("" if len(tail) == 3 else ".") + tail
    try:
        value = float(body)
    except ValueError:
        return None
    suffix = s[match.end():match.end() + 1]
    value *= {"k": 1e3, "m": 1e6, "b": 1e9}.get(suffix, 1.0)
    return value


def _compare_text(text, op, wanted) -> bool:
    """Read Text's comparison. Unknown operators pass, so a macro saved by a
    newer build cannot fail here for a reason nobody can see."""
    op = str(op or "").strip().lower().replace("_", " ")
    left = str(text or "").strip()
    right = str(wanted or "").strip()
    if op == "contains":
        return right.lower() in left.lower()
    if op == "not contains":
        return right.lower() not in left.lower()

    left_n, right_n = _as_number(left), _as_number(right)
    numeric = left_n is not None and right_n is not None
    if op in ("equals", "=", "=="):
        # Numbers when both sides are numbers -- "12" and "12.0" are equal --
        # otherwise a case-insensitive text match.
        return left_n == right_n if numeric else left.lower() == right.lower()
    if op in ("not equals", "!=", "<>"):
        return left_n != right_n if numeric else left.lower() != right.lower()
    if not numeric:
        return False
    if op in ("greater", ">"):
        return left_n > right_n
    if op in ("greater or equal", ">="):
        return left_n >= right_n
    if op in ("less", "<"):
        return left_n < right_n
    if op in ("less or equal", "<="):
        return left_n <= right_n
    return True


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
        # Run clock and counters, read by the status bar and by the webhook
        # report. _total_passes survives a "restart macro", which the per-run
        # pass counter deliberately does not.
        self._started_at = 0.0
        self._ended_at = 0.0
        self._total_passes = 0
        # Watch phase
        self._watch_blocks = []
        self._watch_interval = 0.4
        self._watch_after = "continue"
        self._watch_next = 0.0
        self._watch_fires = 0
        self._in_watch = False

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
        self._started_at = time.time()
        self._ended_at = 0.0
        self._total_passes = 0
        self._watch_blocks = []
        self._watch_next = 0.0
        self._watch_fires = 0
        self._in_watch = False
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

    def run_stats(self) -> dict:
        """How long the run has been going and how much it has done.

        Kept live while running and frozen afterwards, so the control bar can
        keep showing the last run's duration instead of snapping back to zero.
        """
        if not self._started_at:
            return {"elapsed_s": 0.0, "passes": 0, "watch_fires": 0}
        end = time.time() if self.is_running() else (self._ended_at or time.time())
        return {"elapsed_s": max(0.0, end - self._started_at),
                "passes": self._total_passes,
                "watch_fires": self._watch_fires}

    # ------------------------------------------------------------- plumbing

    def _checkpoint(self) -> bool:
        """The universal gate. Blocks while paused, returns True on stop."""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.08)
        if self._stop_event.is_set():
            if not self._stop_logged:
                self._stop_logged = True
                self._log(tr("Stopped."))
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
        self._log(tr("Target window disappeared -- stopping so clicks cannot "
                     "land on whatever is behind it."))
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
            self._log(tr("Runner error: %s") % exc)
        finally:
            self._ended_at = time.time()
            self._release_all()
            capture.close_mss()
            self._set_status(running=False, paused=False, action="Idle")
            self._log(tr("Run finished."))

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
                    self._log(tr("Restarted the macro %d times -- giving up.")
                              % _MAX_RUN_RESTARTS)
                    return
                self._log(tr("Restarting the whole macro (%d).") % restarts)
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
        watch_key = blockmod.PHASE_WATCH
        setup = blockmod.normalize_list(phases.get(once_key))
        loop = blockmod.normalize_list(phases.get(repeat_key))
        self._load_watch(blockmod.normalize_list(phases.get(watch_key)))

        if not setup and not loop and not self._watch_blocks:
            self._log(tr("Nothing to run -- every phase is empty."))
            return

        self._set_status(running=True, paused=False, action=tr("Starting"),
                         loop=0)
        # The phase LABELS, not the identifiers: the sentence around them is
        # translated, and "setup"/"loop" are storage keys that happen to be
        # English words -- the next two status lines already use the labels.
        self._log(tr("Run started (%d %s, %d %s blocks).")
                  % (len(setup), blockmod.PHASE_LABELS[once_key],
                     len(loop), blockmod.PHASE_LABELS[repeat_key]))
        if self._watch_blocks:
            self._log(tr("Watch: %d block(s), checked between steps every %d ms.")
                      % (len(self._watch_blocks), int(self._watch_interval * 1000)))

        if self._hwnd and wm.is_window(self._hwnd):
            title = wm.get_window_title(self._hwnd)
            self._log(tr("Target: %s") % (title or self._hwnd))
            # Deliberately NOT activating the target here. Stealing focus on
            # every run is the user's decision, not the runner's: put a Focus
            # Target block at the top of Setup when you want it. The implicit
            # activation also dragged a maximized window back to its restored
            # size and yanked the foreground away from whatever the user had
            # chosen -- including in whole-screen mode after an old target was
            # still remembered.
        elif self._coord_space == "window":
            self._log(tr("Target window is gone -- using screen coordinates."))

        if not setup and not loop:
            # The Watch phase on its own IS the macro: there is nothing to
            # interrupt, so it is polled directly until Stop.
            self._watch_idle_loop(watch_key)
            return

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
            self._total_passes += 1
            self._set_status(action=blockmod.PHASE_LABELS[repeat_key], loop=passes)
            if self._run_phase_once(loop, repeat_key) == "stop":
                return
            if not loop_forever and passes >= max(1, loop_count):
                self._log(tr("Reached %d loop pass(es).") % passes)
                return

    def _load_watch(self, blocks) -> None:
        """Read the Watch phase and its settings once, at the start of a run."""
        from . import settings as settingsmod

        try:
            cfg = settingsmod.load()
        except Exception:
            cfg = {}
        try:
            interval = float(cfg.get("watch_interval_ms", 400)) / 1000.0
        except (TypeError, ValueError):
            interval = 0.4
        # Floored: a 0 ms watch would run its check between every single block
        # with no pause at all and drown the run in polling.
        self._watch_interval = max(0.05, interval)
        self._watch_after = (str(cfg.get("watch_after") or "continue")
                             .strip().lower().replace(" ", "_"))
        enabled = bool(cfg.get("watch_enabled", True))
        self._watch_blocks = list(blocks) if (enabled and blocks) else []
        self._watch_next = 0.0
        self._in_watch = False

    def _run_watch_pass(self) -> bool:
        """One pass of the Watch phase. True when the event fired.

        "Fired" is defined by the machinery the Vision blocks already have:
        the block that CHECKS for the event carries On fail = "skip rest", so
        a pass where nothing was there abandons itself and counts as quiet.
        A pass that reaches its last block did something.
        """
        watch_key = blockmod.PHASE_WATCH
        try:
            self._run_blocks(self._watch_blocks, watch_key,
                             label=blockmod.PHASE_LABELS[watch_key])
            return True
        except _SkipRest:
            return False
        except _RestartPhase:
            # A block inside Watch asking for a restart IS the event.
            return True

    def _maybe_watch(self) -> None:
        """Run the Watch phase if it is due.

        Called between blocks and never inside one: interrupting a block
        halfway would leave a mouse button held or a key stuck down.

        A quiet pass leaves no trace at all -- log and status writes are
        collected and thrown away, because a check running every 400 ms would
        otherwise bury the run's own journal. They are replayed when the watch
        actually fires.
        """
        if self._in_watch or not self._watch_blocks:
            return
        if time.time() < self._watch_next:
            return

        outer_phase = self._phase_key
        real_log, real_status = self._log, self._set_status
        collected = []
        self._in_watch = True
        self._log = collected.append
        self._set_status = lambda **kw: None
        try:
            fired = self._run_watch_pass()
        finally:
            self._log, self._set_status = real_log, real_status
            self._in_watch = False
            self._phase_key = outer_phase
            # Measured from the END of the pass, so a slow check does not
            # immediately become due again.
            self._watch_next = time.time() + self._watch_interval

        if not fired:
            return
        self._watch_fires += 1
        self._log(tr("Watch fired (%d).") % self._watch_fires)
        for line in collected:
            self._log(line)

        mode = self._watch_after
        if mode == "restart_macro":
            self._log(tr("   watch done -- restarting the whole macro"))
            raise _RestartRun()
        if mode in ("restart_loop", "run_loop", "restart_phase"):
            if outer_phase == blockmod.PHASE_REPEAT:
                self._log(tr("   watch done -- restarting the Loop"))
                raise _RestartPhase()
            # Fired during Setup: "run the loop" means stop preparing.
            self._log(tr("   watch done -- moving on to the Loop"))
            raise _SkipRest()
        self._log(tr("   watch done -- carrying on"))

    def _watch_idle_loop(self, watch_key: str) -> None:
        """No Setup and no Loop: just watch until Stop."""
        self._log(tr("Only the Watch phase has blocks -- monitoring until Stop."))
        self._phase_key = blockmod.PHASE_REPEAT
        self._set_status(action=blockmod.PHASE_LABELS[watch_key])
        while not self._stop_event.is_set():
            if self._checkpoint():
                return
            try:
                self._maybe_watch()
            except (_RestartPhase, _SkipRest):
                # "restart loop" with no Loop to restart: keep watching.
                continue
            time.sleep(0.05)

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
                    self._log(tr("Restarted %s %d times without getting "
                                 "through -- giving up on this pass.")
                              % (blockmod.PHASE_LABELS.get(phase_key, phase_key),
                                 _MAX_PHASE_RESTARTS))
                    return "done"
                self._log(tr("   restarting %s from the top (%d)")
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
                self._log(tr("Loop guard tripped -- stopping the run."))
                self._stop_event.set()
                raise _StopRun()
            if self._checkpoint():
                return
            self._maybe_watch()

            block = block_list[index]
            btype = block["type"]

            # Flow-control markers are structural: honouring `enabled` or
            # `once` on them would desynchronise the stack and silently
            # change the body's repeat count instead of skipping a step.
            is_flow = btype in ("loop_start", "loop_end")
            if not is_flow:
                if not block.get("enabled", True):
                    self._log(tr("   - skipped (disabled): %s") % blockmod.summarise(block))
                    index += 1
                    continue
                if block.get("once") and is_repeating and self._loop_index > 1:
                    self._log(tr("   - skipped (ONCE, already ran): %s")
                              % blockmod.summarise(block))
                    index += 1
                    continue

            if btype == "loop_start":
                try:
                    count = max(1, int(block["params"].get("count", 1) or 1))
                except (TypeError, ValueError):
                    # One malformed count must cost one block, not the run.
                    self._log(tr("Loop Start has a bad count -- using 1."))
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
            # No tr() on the template -- it has no words. Both halves arrive
            # translated already: the phase label from PHASE_LABELS (or the
            # caller's, for a fallback) and the summary from summarise().
            self._log("%s #%d  %s" % (phase_label, step, summary))
            try:
                self._execute(block)
            except (_SkipRest, _StopRun, _RestartPhase, _RestartRun):
                raise
            except Exception as exc:
                self._log(tr("   ! %s failed: %s") % (btype, exc))
            else:
                elapsed = time.time() - started
                # Only worth reporting when the block actually took time --
                # a "took 0ms" line under every instant click is noise.
                if elapsed >= 0.4:
                    self._log(tr("   took %.1fs") % elapsed)
            index += 1

    # ------------------------------------------------------------ dispatch

    def _execute(self, block: dict) -> None:
        handler = getattr(self, "_do_" + block["type"], None)
        if handler is None:
            self._log(tr("No handler for block type %s") % block["type"])
            return
        handler(block["params"])

    def _fail(self, params: dict, message: str) -> None:
        """Apply the block's on_fail policy.

        The option strings are read loosely (spaces or underscores) so a macro
        saved before the wording changed keeps working.
        """
        mode = str(params.get("on_fail") or "continue").strip().lower().replace(" ", "_")
        # Logged as handed over: every caller has already run its own literal
        # through tr(). Translating here instead cannot work -- by this point
        # the image name is substituted and nothing would match a key.
        self._log(message)

        if mode == "run_blocks":
            fallback = blockmod.normalize_list(params.get("on_fail_blocks"))
            if not fallback:
                self._log(tr("   (no fallback blocks -- continuing)"))
                return
            self._log(tr("   running %d fallback block(s)") % len(fallback))
            # Nested one level only: a fallback that could itself restart the
            # phase from inside a fallback is a loop nobody can follow.
            depth = self._fallback_depth
            if depth >= _MAX_FALLBACK_DEPTH:
                self._log(tr("   fallback nested too deep -- skipping"))
                return
            self._fallback_depth = depth + 1
            try:
                self._run_blocks(fallback, self._phase_key or blockmod.PHASE_REPEAT,
                                 label=tr("Fallback"))
            finally:
                self._fallback_depth = depth

            # What to do now that the fallback is done. Default is to resume
            # the main sequence where it left off.
            after = str(params.get("on_fail_after")
                        or "continue main").strip().lower().replace(" ", "_")
            if after == "restart_phase":
                self._log(tr("   fallback done -- restarting the phase"))
                raise _RestartPhase()
            if after == "restart_macro":
                self._log(tr("   fallback done -- restarting the macro"))
                raise _RestartRun()
            if after == "stop":
                self._log(tr("   fallback done -- stopping"))
                self._stop_event.set()
                raise _StopRun()
            return

        if mode == "restart_phase":
            raise _RestartPhase()
        if mode == "restart_macro":
            raise _RestartRun()
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

    # A recorded path is a series of SAMPLES. Jumping straight to each one
    # reads as teleporting whenever two samples are far apart -- which is
    # what an old recording taken at the previous 80ms sample rate looks
    # like. Long hops are therefore split into short ones. Nothing is added
    # for a dense path: a sample within _SMOOTH_STEP_PX of the last position
    # is sent as-is, so a modern recording pays no cost and gains no delay.
    _SMOOTH_STEP_PX = 14
    _SMOOTH_MAX_STEPS = 8
    _SMOOTH_STEP_S = 0.002

    def _move_smooth(self, x: int, y: int) -> None:
        try:
            cx, cy = self.mouse.position()
        except Exception:
            self.mouse.move_to(x, y)
            return
        distance = max(abs(int(x) - int(cx)), abs(int(y) - int(cy)))
        if distance <= self._SMOOTH_STEP_PX:
            self.mouse.move_to(x, y)
            return
        steps = min(self._SMOOTH_MAX_STEPS, distance // self._SMOOTH_STEP_PX)
        for i in range(1, steps):
            fraction = i / steps
            self.mouse.move_to(int(cx + (x - cx) * fraction),
                               int(cy + (y - cy) * fraction))
            time.sleep(self._SMOOTH_STEP_S)
        self.mouse.move_to(x, y)

    def _do_move(self, params) -> None:
        x, y = self._to_screen(params.get("x", 0), params.get("y", 0))
        duration = max(0.0, self._num(params, "duration_ms", 0)) / 1000.0
        if duration <= 0:
            # No explicit duration: a straight jump for a short hop, a few
            # interpolated points for a long one. No pacing delay either way.
            self._move_smooth(x, y)
            return
        sx, sy = self.mouse.position()
        steps = max(2, int(duration * 60))
        for i in range(1, steps + 1):
            if self._checkpoint():
                return
            t = i / steps
            self.mouse.move_to(int(sx + (x - sx) * t), int(sy + (y - sy) * t))
            time.sleep(duration / steps)

    def _do_move_by(self, params) -> None:
        """Move the cursor BY an offset from wherever it is now.

        Sent as RELATIVE input, not as a jump to (position + offset). A game
        that locks and hides the pointer recenters it every frame and reads
        raw deltas, so an absolute jump moves nothing there; in an ordinary
        window the two look identical. See Mouse.move_by().

        Nothing here goes through _to_screen either: an offset is the same
        number of pixels in window space and in screen space, and converting
        it would add the window's origin on top.

        A zero on an axis means "leave that axis alone", which falls out of
        the arithmetic -- dx=0, dy=200 lands 200px lower at the same X.
        """
        dx = int(self._num(params, "dx", 0))
        dy = int(self._num(params, "dy", 0))
        if not dx and not dy:
            # Both zero is a no-op, not "move to 0,0".
            return
        duration = max(0.0, self._num(params, "duration_ms", 0)) / 1000.0
        if duration <= 0:
            # One relative event: the smallest thing a game can read as a
            # mouse delta, and instant in a normal window.
            self.mouse.move_by(dx, dy)
            return
        steps = max(2, int(duration * 60))
        delay = duration / steps
        for i in range(1, steps + 1):
            if self._checkpoint():
                return
            # Sliced by hand rather than handed to move_by(steps=...) so Stop
            # and Pause are honoured between steps of a long glide.
            self.mouse.move_by(int(round(dx * i / steps)) - int(round(dx * (i - 1) / steps)),
                               int(round(dy * i / steps)) - int(round(dy * (i - 1) / steps)))
            time.sleep(delay)

    def _do_drag(self, params) -> None:
        """Drag, with either end optionally free of fixed coordinates.

        From "current" starts wherever the cursor already is -- for dragging
        something the macro has just picked up or hovered, whose position is
        not known when the block is written. To "offset" reads x2/y2 as a
        delta instead of a destination, so "0, 200" drags 200 pixels straight
        down from the start regardless of where that start turned out to be.

        Missing or unknown values fall back to "point", so every macro saved
        before this existed behaves exactly as it did.
        """
        from_mode = str(params.get("from_mode") or "point").strip().lower()
        to_mode = str(params.get("to_mode") or "point").strip().lower()

        x1 = y1 = None
        if from_mode == "current":
            try:
                position = self.mouse.position()
                x1, y1 = int(position[0]), int(position[1])
            except Exception:
                # Cursor position unreadable: the written point is a better
                # answer than refusing to drag.
                x1 = y1 = None
        if x1 is None:
            x1, y1 = self._to_screen(params.get("x", 0), params.get("y", 0))

        button = str(params.get("button") or "left")
        duration = max(0.0, self._num(params, "duration_ms", 250) / 1000.0)

        if to_mode == "offset":
            # Relative input all the way, never "start + delta" as absolute
            # coordinates: this is the mode a locked-cursor game needs, where
            # the pointer is recentered every frame and only raw deltas are
            # read. An offset is also the same number of pixels in window and
            # screen space, so there is nothing to convert.
            dx = int(self._num(params, "x2", 0))
            dy = int(self._num(params, "y2", 0))
            self._held_buttons.add(button)
            try:
                if from_mode != "current":
                    # Park on the written start point first; from "current"
                    # the cursor is already where the drag should begin, and
                    # moving it would undo a deliberate hover.
                    self.mouse.move_to(x1, y1)
                    time.sleep(0.03)
                # A real relative event before the button lands: some targets
                # only register the hover from one, and never see the click.
                self.mouse.nudge(1, 0)
                self.mouse.nudge(-1, 0)
                self.mouse.drag_by(dx, dy, button,
                                   steps=max(1, int(duration * 60) or 1),
                                   duration=duration)
            finally:
                self._held_buttons.discard(button)
            return

        x2, y2 = self._to_screen(params.get("x2", 0), params.get("y2", 0))
        self._held_buttons.add(button)
        try:
            self.mouse.drag(x1, y1, x2, y2, button, duration=duration)
        finally:
            self._held_buttons.discard(button)

    def _target_centre(self):
        """Middle of the target window, or of the desktop in screen mode."""
        hwnd = self._target()
        if hwnd:
            try:
                left, top, width, height = wm.get_client_rect_screen(hwnd)
                if width > 0 and height > 0:
                    return left + width // 2, top + height // 2
            except Exception:
                pass
        from ._sendinput import virtual_screen_rect
        vx, vy, vw, vh = virtual_screen_rect()
        return vx + (vw or 1) // 2, vy + (vh or 1) // 2

    def _do_mouse_look(self, params) -> None:
        """Camera-look drag: a button held while raw deltas are streamed.

        This exists because Move and Drag cannot work in a game that locks
        and hides the pointer. Such a game recenters the cursor every frame
        and turns the camera from the RAW deltas, so an absolute reposition
        registers as no movement at all, and reading the cursor back gives
        the recentered point rather than where the macro thinks it is.

        Two modes, and the default one is the reason this block was
        rewritten. How far the camera turns per pixel of delta is the GAME's
        mouse sensitivity, which is not ours to read and differs from machine
        to machine (a PC and a VM will not agree, and a VM's own pointer
        scaling piles on top). So a fixed amount of travel cannot land the
        camera in a repeatable place -- it lands at a different pitch on every
        setup, which looks exactly like "the camera is offset".

        "to limit" therefore does not aim at all: it sends far more travel
        than any sensitivity needs (40000 px by default) so the camera runs
        into its own pitch stop and ends pinned against it. Past the stop the
        extra deltas do nothing, so overshooting is free -- and the stop is
        the one position that is identical everywhere. This is why the
        reference script's single mouse_event(MOVE, 0, 10000) works where a
        careful 3200 px did not.

        "exact" keeps the old behaviour for the rare case where a measured
        turn is what is wanted, and it is still spread over several deltas:
        a target reading one delta per frame clamps a single huge jump to a
        fraction of the turn, while a stream of moderate ones lands in full.
        """
        button = str(params.get("button") or "right").strip().lower()
        mode = str(params.get("mode") or "to limit").strip().lower()
        dx = int(self._num(params, "dx", 0))
        dy = int(self._num(params, "dy", 0))
        step_delay = max(0.0, self._num(params, "step_delay_ms", 8)) / 1000.0
        settle = max(0.0, self._num(params, "settle_ms", 80)) / 1000.0

        if mode == "exact":
            steps = max(1, int(self._num(params, "steps", 1)))
        else:
            # Repeat the delta until the sweep has been sent. Capped so a
            # silly sweep with a tiny delta cannot spin here for minutes.
            sweep = max(1, int(self._num(params, "sweep_px", 40000)))
            per = max(abs(dx), abs(dy)) or 1
            steps = min(2000, max(1, (sweep + per - 1) // per))
            self._log(tr("Camera: sweeping %d px past the limit (%d x %d,%d).")
                      % (steps * per, steps, dx, dy))

        if params.get("centre_first", True):
            # The button has to land inside the target, and the middle is the
            # one point that is always inside it.
            centre_x, centre_y = self._target_centre()
            self.mouse.move_to(centre_x, centre_y)
            time.sleep(0.15)
            # A genuine relative event, so the target sees a hover before the
            # press rather than a cursor that teleported in.
            self.mouse.nudge(1, 0)
            self.mouse.nudge(-1, 0)
            time.sleep(0.05)

        held = button in ("left", "right", "middle")
        if held:
            self._held_buttons.add(button)
            self.mouse.down(button)
        try:
            time.sleep(settle)
            for _ in range(steps):
                if self._checkpoint():
                    return
                self.mouse.move_by(dx, dy)
                time.sleep(step_delay)
            time.sleep(settle)
        finally:
            # In finally, and before anything else can raise: a right button
            # left physically down turns every later move in the run into a
            # camera drag.
            if held:
                self.mouse.up(button)
                self._held_buttons.discard(button)

    # ------------------------------------------------------------- roblox

    def _guess_map_reference(self, img_w, img_h):
        """What an undescribed map picture is most likely a picture of.

        Only pictures imported as files reach this -- anything shot inside the
        app records its own frame of reference next to the PNG. The shape is
        the one clue a bare image carries, and it is a decent one: a shot of
        the whole 1920x1080 screen and a 900x700 game window are not the same
        proportions.

        Ties go to the screen. Reading a full-screen picture as a window one
        is off by the window's entire offset on screen (the mistake that put
        units well above where they were picked), while the other way round
        is a scaling error inside the right area.
        """
        aspect = float(img_w) / float(img_h or 1)
        client = None
        hwnd = self._target()
        if hwnd:
            try:
                cw, ch = wm.get_client_size(hwnd)
            except Exception:
                cw = ch = 0
            if cw > 0 and ch > 0:
                client = (cw, ch)
        try:
            screen_w, screen_h = wm.get_screen_size()
        except Exception:
            screen_w = screen_h = 0

        if client and screen_w > 0 and screen_h > 0:
            window_err = abs(aspect - float(client[0]) / client[1])
            screen_err = abs(aspect - float(screen_w) / screen_h)
            if window_err < screen_err - 0.01:
                self._log(tr("This map picture has no saved geometry -- "
                             "read as a window shot."))
                return {"origin": "window", "left": 0, "top": 0,
                        "width": client[0], "height": client[1],
                        "ref_width": client[0], "ref_height": client[1]}
        if screen_w > 0 and screen_h > 0:
            self._log(tr("This map picture has no saved geometry -- "
                         "read as a whole-screen shot."))
            return {"origin": "screen", "left": 0, "top": 0,
                    "width": screen_w, "height": screen_h}
        # No screen metrics at all: the picture's own pixels are all there is.
        return {"origin": "window", "left": 0, "top": 0,
                "width": int(img_w), "height": int(img_h),
                "ref_width": int(img_w), "ref_height": int(img_h)}

    def _map_point_to_screen(self, location):
        """A spot picked on a map picture -> absolute screen point.

        The point is stored as a fraction of the picture it was picked on, and
        turned into a real point here using what that picture WAS:

        - a whole-screen shot means absolute screen pixels, and the target
          window must not enter into it at all -- scaling a screen picture
          into a window's client area is what placed units above the spot
          that was picked, by the window's own offset on screen;
        - a window shot means client pixels, rescaled to whatever size that
          client area is now, which is what lets one macro survive the game
          window being resized.
        """
        if not isinstance(location, (list, tuple)) or len(location) < 5:
            return None
        try:
            map_x, map_y = float(location[1]), float(location[2])
            img_w, img_h = float(location[3]), float(location[4])
        except (TypeError, ValueError):
            return None
        if img_w <= 0 or img_h <= 0:
            return None
        fx, fy = map_x / img_w, map_y / img_h

        from . import maps
        meta = maps.read_meta(location[0]) or self._guess_map_reference(img_w, img_h)

        if meta["origin"] == "screen":
            return (int(round(meta["left"] + fx * meta["width"])),
                    int(round(meta["top"] + fy * meta["height"])))

        client_x = meta["left"] + fx * meta["width"]
        client_y = meta["top"] + fy * meta["height"]
        ref_w = float(meta.get("ref_width") or meta["width"])
        ref_h = float(meta.get("ref_height") or meta["height"])

        hwnd = self._target()
        if hwnd:
            try:
                width, height = wm.get_client_size(hwnd)
            except Exception:
                width = height = 0
            if width > 0 and height > 0:
                return wm.client_to_screen(
                    hwnd,
                    int(round(client_x / ref_w * width)),
                    int(round(client_y / ref_h * height)))

        # The target is gone: nothing better than spreading the picture over
        # the desktop is available, and refusing outright would break macros
        # that run against whatever is in front.
        from ._sendinput import virtual_screen_rect
        vx, vy, vw, vh = virtual_screen_rect()
        return (vx + int(round(fx * (vw or 1))),
                vy + int(round(fy * (vh or 1))))

    def _do_place_unit(self, params) -> None:
        """Press the unit's hotkey, then click the spot picked on the map.

        Deliberately not a bare click: in a tower-defence style game the
        hotkey is what puts the game into placement mode, and a click without
        it lands on the world and does nothing at all.
        """
        point = self._map_point_to_screen(params.get("location"))
        if point is None:
            # Not a _fail: an unfinished block is a setup mistake, and
            # stopping the whole run for it hides which block it was.
            self._log(tr("No location picked for the unit."))
            return
        name = params.get("unit")
        vk = keymod.key_name_to_vk(name)
        if vk is None:
            self._log(tr("Unknown key: %r") % (name,))
            return

        self._held_keys.add(vk)
        try:
            self.keyboard.tap(vk, 0.03)
        finally:
            self._held_keys.discard(vk)
        # The game enters placement mode on the hotkey and needs time to
        # spawn the ghost; a click before that is swallowed, so the wait is
        # generous by default and adjustable per block.
        self._sleep(max(0.0, self._num(params, "key_delay_ms", 500)) / 1000.0)
        if self._checkpoint():
            return

        # Two clicks by default: the first one is eaten as "aim" by the
        # placement ghost often enough that a single click leaves the unit
        # unplaced with the hotkey still armed. multi_click keeps the pair
        # inside the double-click window -- looping click() here would put
        # the global Macro Speed delay between them and the game would see
        # two unrelated clicks.
        clicks = int(self._num(params, "clicks", 2) or 2)
        if clicks < 1:
            clicks = 1
        self._held_buttons.add("left")
        try:
            self.mouse.multi_click(point[0], point[1], "left", count=clicks)
        finally:
            self._held_buttons.discard("left")
        self._log(tr("Placed %s at %s,%s") % (name, point[0], point[1]))
        self._sleep(max(0.0, self._num(params, "after_ms", 250)) / 1000.0)

    def _do_roblox_rejoin(self, params) -> None:
        """Restart the Roblox client and rejoin the server.

        Roblox has no reconnect of its own, so this does what a hand-written
        rejoin script does: close the client, then hand the launcher a
        roblox:// deep link carrying the place id and the private server's
        linkCode.

        Order matters in two places.

        The exe path is read BEFORE the kill. It lives in a per-version
        folder that changes with every Roblox update, and the only reliable
        way to know the current one is to ask the running process -- after
        the kill there is nothing left to ask.

        The client must really be gone before the link is sent. A live client
        swallows the deep link and stays in the server it is already in, so
        the macro would wait out the whole timeout for a join that never
        started.

        Finally the new window becomes the target: the old hwnd died with the
        old process, and every window-relative coordinate in the macro would
        otherwise be measured against a window that no longer exists.
        """
        from . import roblox
        from . import settings as settingsmod

        if not roblox.available():
            self._fail(params, tr("Rejoin only works on Windows."))
            return

        cfg = settingsmod.load()
        # A share link is the whole invite in one string, so it wins over the
        # hand-typed pair: pasting one instead of picking the id and the code
        # apart by hand is the entire point of it.
        share = roblox.parse_share_code(params.get("share_link")
                                        or cfg.get("roblox_share_link") or "")
        place = roblox.parse_place_id(params.get("place_id")
                                     or cfg.get("roblox_place_id") or "")
        code = roblox.parse_link_code(params.get("link_code")
                                      or cfg.get("roblox_link_code") or "")
        if share:
            uri = roblox.share_uri(share)
            where = tr("share link")
        elif place:
            uri = roblox.join_uri(place, code)
            where = place + (tr(" (private server)") if code else "")
        else:
            self._fail(params, tr("Nothing to rejoin with -- paste a share "
                                  "link, or a place id, on the block or in "
                                  "Settings."))
            return
        exe = roblox.player_exe()

        if bool(params.get("close_first", True)):
            closed = roblox.close_players(
                max(1.0, self._num(params, "close_wait_ms", 4000) / 1000.0))
            self._log(tr("Closed %d Roblox client(s).") % closed)
            if self._sleep(max(0.0, self._num(params, "close_wait_ms", 4000))
                           / 1000.0):
                return

        self._log(tr("Rejoining %s...") % where)
        if not roblox.launch(uri, exe):
            self._fail(params, tr("Could not start the Roblox client."))
            return

        timeout = max(5.0, self._num(params, "timeout_ms", 90000) / 1000.0)
        hwnd = roblox.wait_for_window(
            timeout, 1.0, should_stop=lambda: self._stop_event.is_set())
        if self._checkpoint():
            return
        if not hwnd:
            self._fail(params, tr("Roblox did not come back within %ds.")
                       % int(timeout))
            return
        self._log(tr("Roblox is back: %s") % wm.get_window_title(hwnd))

        if bool(params.get("retarget", True)):
            self._hwnd = int(hwnd)
            self._target_was_alive = True
            try:
                settingsmod.update({"target_hwnd": int(hwnd),
                                    "target_title": wm.get_window_title(hwnd),
                                    "target_mode": "window"})
            except Exception:
                pass
            wm.activate_window(hwnd)
            self._log(tr("Target switched to the new Roblox window."))

        # The window exists long before the place is loaded and playable, so
        # the wait is generous by default: acting on a half-loaded game is
        # what makes a rejoin look like it worked and then do nothing.
        self._sleep(max(0.0, self._num(params, "settle_ms", 12000)) / 1000.0)

    def _do_restart_loop(self, params) -> None:
        """Start the phase this block sits in again, from its first block."""
        self._log(tr("Block asked to restart the phase."))
        raise _RestartPhase()

    def _do_restart_macro(self, params) -> None:
        """Start the whole macro again, Setup included."""
        self._log(tr("Block asked to restart the macro."))
        raise _RestartRun()

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
            self._log(tr("Unknown key: %r") % (name,))
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
            self._log(tr("Unknown key: %r") % (params.get("key"),))
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
            self._fail(params, tr("No image named '%s' in Assets -- capture "
                                  "it first.") % name)
        elif match is None:
            self._fail(params, tr("Image '%s' did not appear.") % name)
        else:
            self._log(tr("Found '%s' (%.2f).") % (name, match["score"]))

    def _do_click_image(self, params) -> None:
        name = str(params.get("template") or "")
        if not name:
            return
        match = self._wait_image(params, name)
        if match is _MISSING_TEMPLATE:
            self._fail(params, tr("No image named '%s' in Assets -- nothing "
                                  "clicked.") % name)
            return
        if match is None:
            self._fail(params, tr("Image '%s' not found -- nothing clicked.")
                       % name)
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
        self._log(tr("Clicked '%s' at %d,%d (%.2f).") % (name, cx, cy, match["score"]))

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
            self._log(tr("No image named '%s' in Assets -- treating as already gone.") % name)
            return
        if not gone:
            self._fail(params, tr("Image '%s' is still on screen.") % name)

    def _do_wait_color(self, params) -> None:
        rgb = _hex_to_rgb(params.get("color"))
        ok = vision.wait_for_color(
            self._target(), int(self._num(params, "x", 0)),
            int(self._num(params, "y", 0)), rgb,
            self._colour_tolerance(params, 0.92),
            max(0.0, self._num(params, "timeout_ms", 8000) / 1000.0),
            stop_event=self._gate)
        if not ok:
            self._fail(params, tr("Color %s never appeared at %s,%s.")
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
                        self._log(tr("Text matched exactly: %r") % text.strip())
                        return
                else:
                    hit = ocr.find_text(frame, needle, confidence)
                    if hit:
                        self._log(tr("Text matched: %r (%.2f)") % (hit["text"], hit["score"]))
                        return
            time.sleep(0.35)
        self._fail(params, tr("Text %r not found.") % needle)

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
            self._fail(params, tr("Text %r not found -- nothing clicked.")
                       % needle)
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
        self._log(tr("Clicked text %r at %d,%d (%.2f)") % (hit["text"], cx, cy, hit["score"]))

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
            self._fail(params, tr("Colour %s not found -- nothing clicked.")
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
        self._log(tr("Clicked colour %s at %d,%d (%d px)")
                  % (params.get("color"), cx, cy, found["area"]))

    def _do_read_text(self, params) -> None:
        region = self._region(params)
        frame = capture.capture_target_bgr(self._target(), region)
        confidence = max(0.0, min(1.0, self._num(params, "confidence", 0.75)))
        # Use find_text (same engine as click_text / wait_text): it applies
        # the confidence threshold and fuzzy matching so OCR misreads don't
        # silently swallow a match.  Empty needle -> first recognised line.
        hit = ocr.find_text(frame, "", confidence) if frame is not None else None
        # read_text still does the full-region sweep for the compare operators.
        text = ocr.read_text(frame).strip() if frame is not None else ""
        self._log(tr("Read: %r") % text)

        op = str(params.get("compare") or "off").strip().lower().replace("_", " ")
        if op in ("", "off", "none"):
            return
        wanted = str(params.get("expect") or "")

        # A missing number is its own failure: ">" against unreadable text is
        # not "false", it is "there was nothing to compare", and saying so in
        # the log is the difference between a five-second and an hour-long fix.
        if op in _NUMERIC_COMPARE and (_as_number(text) is None
                                       or _as_number(wanted) is None):
            self._fail(params, tr("Text check failed: no number in %r vs %r")
                       % (text, wanted))
            return

        if _compare_text(text, op, wanted):
            self._log(tr("   text check passed: %r %s %r") % (text, op, wanted))
            return
        self._fail(params, tr("Text check failed: %r %s %r") % (text, op, wanted))

    # ------------------------------------------------------------ system

    def _do_open_app(self, params) -> None:
        import subprocess
        path = str(params.get("path") or "").strip()
        if not path:
            self._log(tr("Open App: no path given."))
            return
        args_str = str(params.get("args") or "").strip()
        cmd = [path] + (args_str.split() if args_str else [])
        try:
            subprocess.Popen(cmd)
            self._log(tr("Opened: %s") % path)
        except Exception as exc:
            self._log(tr("Open App failed: %s") % exc)
        wait_ms = int(self._num(params, "wait_ms", 0))
        if wait_ms > 0:
            import time as _time
            _time.sleep(wait_ms / 1000.0)

    def _do_kill_process(self, params) -> None:
        name_pat = str(params.get("name") or "").strip().lower()
        if not name_pat:
            self._log(tr("Kill Process: no process name given."))
            return
        force = bool(params.get("force", True))
        killed = []
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pname = (proc.info["name"] or "").lower()
                    if name_pat in pname:
                        if force:
                            proc.kill()
                        else:
                            proc.terminate()
                        killed.append(pname)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            # psutil not installed: fall back to taskkill on Windows
            import subprocess
            try:
                flag = "/F" if force else ""
                cmd = ["taskkill", "/IM", "*%s*" % name_pat]
                if force:
                    cmd.insert(1, "/F")
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode == 0:
                    killed.append(name_pat)
            except Exception as exc:
                self._log(tr("Kill Process: %s") % exc)
        if killed:
            self._log(tr("Killed: %s") % ", ".join(killed))
        else:
            self._log(tr("Kill Process: no process matching %r found.") % name_pat)

        # ------------------------------------------------- conditions / control flow

    def _cond_ctx(self):
        from .conditions import _ConditionContext
        return _ConditionContext(self)

    def _eval_cond(self, cond) -> bool:
        from . import conditions as conds
        return conds.evaluate(cond, self._cond_ctx())

    def _do_if_else(self, params) -> None:
        from .blocks import normalize_list
        cond = params.get('condition')
        result = self._eval_cond(cond) if cond else False
        branch_key = 'then_blocks' if result else 'else_blocks'
        blocks = normalize_list(params.get(branch_key) or [])
        branch_name = 'Then' if result else 'Else'
        self._log(tr('If: condition %s -> %s') % ('true' if result else 'false', branch_name))
        if blocks:
            self._run_blocks(blocks, self._phase_key or 'loop', label=branch_name)

    def _do_while_loop(self, params) -> None:
        from .blocks import normalize_list
        cond = params.get('condition')
        blocks = normalize_list(params.get('blocks') or [])
        max_iter = int(self._num(params, 'max_iter', 100))
        iteration = 0
        while iteration < max_iter:
            if self._checkpoint():
                return
            if not self._eval_cond(cond):
                break
            self._log(tr('While: iteration %d') % (iteration + 1))
            self._run_blocks(blocks, self._phase_key or 'loop', label='While')
            iteration += 1
        if iteration >= max_iter:
            self._log(tr('While: reached max iterations (%d)') % max_iter)

    def _do_repeat_until(self, params) -> None:
        from .blocks import normalize_list
        cond = params.get('condition')
        blocks = normalize_list(params.get('blocks') or [])
        max_iter = int(self._num(params, 'max_iter', 100))
        iteration = 0
        while iteration < max_iter:
            if self._checkpoint():
                return
            self._log(tr('Repeat: iteration %d') % (iteration + 1))
            self._run_blocks(blocks, self._phase_key or 'loop', label='Repeat')
            iteration += 1
            if self._eval_cond(cond):
                break
        if iteration >= max_iter:
            self._log(tr('Repeat Until: reached max iterations (%d)') % max_iter)

        # ---------------------------------------------------------------- flow

    def _do_focus_window(self, params) -> None:
        if not (self._hwnd and wm.is_window(self._hwnd)):
            self._log(tr("No target window to focus."))
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
            self._log(tr("Target would not resize to %dx%d -- it is %dx%d.")
                      % (width, height, got_w, got_h))
        else:
            self._log(tr("Target now %dx%d at %d,%d.") % (got_w, got_h, x, y))

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
            self._log(tr("Webhook is switched off in Settings -- nothing sent."))
            return
        url = str(cfg.get("webhook_url") or "")
        check = hook.validate(url)
        if not check["valid"]:
            self._log(tr("Webhook URL is not usable (%s) -- nothing sent.") % check["reason"])
            return

        source = str(params.get("source") or "none").strip().lower()
        image = None
        label = tr("no attachment")
        if source in ("target window", "whole screen", "region"):
            hwnd = self._target() if source == "target window" else 0
            region = self._region(params) if source == "region" else None
            frame = capture.capture_target_bgr(hwnd, region)
            if frame is None:
                self._log(tr("Could not capture the %s -- sending text only.")
                          % _source_name(source))
            else:
                image = hook.shrink_to_limit(frame)
                label = "%s (%dx%d)" % (_source_name(source),
                                        frame.shape[1], frame.shape[0])
        elif source == "saved image":
            name = str(params.get("template") or "")
            paths = vision.template_variant_paths(name)
            if not paths:
                self._log(tr("No saved image named '%s' -- sending text only.") % name)
            else:
                img = vision.imread_unicode(paths[0])
                image = hook.encode_png(img)
                label = tr("image '%s'") % name

        stats = self.run_stats()
        fields = [
            {"name": tr("Runtime"),
             "value": hook.format_duration(stats["elapsed_s"])},
            {"name": tr("Loop passes"), "value": str(stats["passes"])},
        ]
        if stats["watch_fires"]:
            fields.append({"name": tr("Watch fired"),
                           "value": str(stats["watch_fires"])})
        target = ""
        if self._hwnd and wm.is_window(self._hwnd):
            target = wm.get_window_title(self._hwnd) or str(self._hwnd)
        fields.append({"name": tr("Target"), "value": target or tr("Whole screen")})
        if image is not None:
            fields.append({"name": tr("Attachment"), "value": label})

        embed = hook.build_embed(
            title=(str(params.get("title") or "") or
                   str(cfg.get("webhook_title") or tr("Macro report"))),
            description=(str(params.get("message") or "") or
                         str(cfg.get("webhook_description") or "")),
            fields=fields,
            image_filename="capture.png" if image is not None else "",
            footer=(str(params.get("footer") or "") or
                    str(cfg.get("webhook_footer") or "Macro Studio")),
            color=str(params.get("color") or cfg.get("webhook_color") or ""),
            timestamp=(bool(params["timestamp"]) if "timestamp" in params
                       else bool(cfg.get("webhook_timestamp", True))))
        # The text body stays empty on purpose: the same words inside the
        # embed AND above it reads like a stutter in the channel.
        result = hook.send(url, "", image, embed=embed,
                           username=str(cfg.get("webhook_username") or "") or "Macro Studio")
        if result.get("ok"):
            self._log(tr("Webhook sent (%s).") % label)
        else:
            self._log(tr("Webhook failed: %s") % result.get("reason"))

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
                self._log(tr("Playing '%s' (%d edited actions)") % (name, len(actions)))
                # Runs through the normal block machinery, so loops, on_fail
                # policies and per-block logging all work inside a recording.
                self._run_blocks(actions, self._phase_key or blockmod.PHASE_REPEAT)
                return
            self._log(tr("Recording '%s' has an empty action list -- nothing to do.") % name)
            return

        events = data.get("events") or []
        if not events:
            self._log(tr("Recording '%s' is empty.") % name)
            return
        self._log(tr("Playing '%s' (%d raw events)") % (name, len(events)))
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
                self._move_smooth(x, y)
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


def _source_name(source: str) -> str:
    """A webhook capture source in words.

    The option strings are stored inside saved macros, so they stay English
    identifiers; this is the one place they become something a translated
    log line can carry.
    """
    if source == "target window":
        return tr("target window")
    if source == "whole screen":
        return tr("whole screen")
    if source == "region":
        return tr("region")
    return source


def _hex_to_rgb(value):
    text = str(value or "#ffffff").lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255
