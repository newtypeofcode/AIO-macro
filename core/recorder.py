"""Global input recorder.

Captures real mouse and keyboard activity into one timestamped event list,
then converts it into editable macro blocks -- record once, tweak the rows
afterwards instead of re-recording.

Listening uses pynput's low-level hooks (they see input regardless of which
window has focus). Playback deliberately does NOT go back through pynput --
it goes through our SendInput layer, which games accept far more reliably.
"""
import threading
import time

from . import window as wm
from . import keys as keymod
from .i18n import tr

# Self-echo suppression lives with the injection layer: everything this app
# sends through SendInput comes straight back through the same pynput hooks
# the recorder listens on. Without this import the hook callbacks raised
# NameError on the very first event, which surfaced as
# "start_recording: name '_input_backend' is not defined".
try:
    from . import _input_win as _input_backend
except Exception:                                   # pragma: no cover
    # Non-Windows (or a broken ctypes load): recording still works, it just
    # cannot tell our own injected events apart from real ones.
    class _NoEchoTracking:
        @staticmethod
        def was_injected(kind, identity, window=0.0) -> bool:
            return False

        @staticmethod
        def clear_injected_marks() -> None:
            return None

    _input_backend = _NoEchoTracking()

_BUTTON_NAMES = {"left": "left", "right": "right", "middle": "middle"}

# A recorded press longer than this becomes a Hold Key block instead of a
# send_key: send_key's hold is an uninterruptible sleep, so a long recorded
# hold would make Stop unresponsive for its whole duration.
LONG_HOLD_MS = 1500

# A mouse button still down after this long is treated as a lost release
# rather than an extremely slow drag, so the recording keeps working.
DANGLING_DOWN_S = 8.0


class Recorder:
    """One recording session.

    Timestamps start at the FIRST event, not at start(), so fumbling between
    clicking Record and actually doing something isn't replayed as dead time.
    """

    def __init__(self, log=None):
        self.active = False
        self._events = []
        self._start_time = None
        self._lock = threading.Lock()
        self._mouse_listener = None
        self._key_listener = None
        self._log = log or (lambda msg: None)
        self._record_moves = True
        self._move_interval = 0.04
        self._last_move_at = 0.0
        self._hwnd = 0
        self._client_origin = (0, 0)
        self._suppress_keys = set()
        self._raw = None
        self._held_buttons = set()
        self._raw_deltas = []
        self._raw_started_at = 0.0

    # ---------------------------------------------------------------- helpers

    def _now(self) -> float:
        # Locked: the mouse and keyboard listeners are separate threads, and
        # both racing to initialise the base could hand out a timestamp
        # measured against a base that was then overwritten -- producing
        # events that appear to travel backwards in time.
        with self._lock:
            if self._start_time is None:
                self._start_time = time.perf_counter()
                return 0.0
            return round(time.perf_counter() - self._start_time, 3)

    def _to_client(self, x, y):
        """Store BOTH screen and window-relative coordinates.

        Window-relative is what makes a recording survive the target being
        moved; screen coordinates are kept as the fallback for screen mode
        and for when the window is gone at replay time.
        """
        if self._hwnd and wm.is_window(self._hwnd):
            try:
                cx, cy = wm.screen_to_client(self._hwnd, x, y)
                return int(cx), int(cy)
            except Exception:
                pass
        return int(x), int(y)

    def _append(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    # ------------------------------------------------------- raw drag deltas

    def _raw_delta(self, dx: int, dy: int) -> None:
        """Hardware movement, from the raw-input thread.

        Only collected while a button is held. That is the case position
        tracking cannot cover: a game holding the cursor captured to turn the
        camera reports no cursor movement at all, so a drag recorded from
        positions is a drag that appears never to have happened.
        """
        with self._lock:
            if not self.active or not self._held_buttons:
                return
            self._raw_deltas.append([int(dx), int(dy),
                                     round(time.perf_counter() - self._raw_started_at, 4)])

    def _begin_drag(self, button: str) -> None:
        with self._lock:
            self._held_buttons.add(button)
            if len(self._held_buttons) == 1:
                self._raw_deltas = []
                self._raw_started_at = time.perf_counter()

    def _end_drag(self, button: str) -> None:
        with self._lock:
            self._held_buttons.discard(button)
            if self._held_buttons:
                return
            deltas = self._raw_deltas
            self._raw_deltas = []
        if len(deltas) >= 2:
            # Emitted as ONE event: a camera turn is thousands of tiny
            # deltas, and one row per delta would be unreadable and unusable.
            self._append({"t": self._now(), "type": "drag_deltas",
                          "button": button, "deltas": deltas})

    # ----------------------------------------------------------------- control

    def start(self, hwnd=0, record_moves: bool = True, move_interval_ms: int = 40) -> bool:
        if self.active:
            return False
        try:
            from pynput import mouse as pmouse, keyboard as pkeyboard
        except ImportError:
            self._log(tr("pynput is not installed -- recording unavailable."))
            return False

        self._events = []
        self._start_time = None
        self._last_move_at = 0.0
        self._record_moves = bool(record_moves)
        # Floor of 1ms, not 10ms: the setting is offered in milliseconds, and
        # silently multiplying a requested 1ms by ten made the recording far
        # coarser than asked for -- which is what a stuttery replay looks like.
        self._move_interval = max(0.001, float(move_interval_ms) / 1000.0)
        self._hwnd = int(hwnd or 0)

        # pynput >= 1.8 passes an extra `injected` flag to every hook. The
        # old two/four-argument signatures then raise TypeError on every
        # single event, so each callback accepts it explicitly -- and uses it
        # as one more self-echo signal.
        def on_click(x, y, button, pressed, injected=False, *_extra):
            name = _BUTTON_NAMES.get(getattr(button, "name", ""), "left")
            kind = "mouse_down" if pressed else "mouse_up"
            # Our own injected clicks come back through the same hook. Without
            # this, recording while a macro plays captures the macro's output
            # and the recording grows a copy of itself.
            if injected or _input_backend.was_injected(kind, name):
                return
            cx, cy = self._to_client(x, y)
            if pressed:
                self._begin_drag(name)
            else:
                self._end_drag(name)
            self._append({"t": self._now(), "type": kind,
                          "button": name, "x": cx, "y": cy,
                          "sx": int(x), "sy": int(y)})

        def on_move(x, y, injected=False, *_extra):
            if injected or not self._record_moves:
                return
            now = time.perf_counter()
            # Throttled: a raw hook fires hundreds of times a second and the
            # recording becomes unreadable (and huge) without this.
            if now - self._last_move_at < self._move_interval:
                return
            self._last_move_at = now
            cx, cy = self._to_client(x, y)
            self._append({"t": self._now(), "type": "move",
                          "x": cx, "y": cy, "sx": int(x), "sy": int(y)})

        def on_scroll(x, y, dx, dy, injected=False, *_extra):
            if injected:
                return
            cx, cy = self._to_client(x, y)
            self._append({"t": self._now(), "type": "scroll",
                          "dx": int(dx), "dy": int(dy), "x": cx, "y": cy})

        _ALIASES = {"cmd": "win", "cmd_r": "win", "alt_l": "alt", "alt_r": "alt",
                    "ctrl_l": "ctrl", "ctrl_r": "ctrl", "shift_l": "shift",
                    "shift_r": "shift", "alt_gr": "alt"}

        def key_identity(key):
            """(canonical name, produced character or None, vk or None).

            The VK code is the identity that gets REPLAYED, never the
            character: on a non-Latin layout pynput reports key.char as the
            layout's output ('я' for the physical Z key), and replaying that
            back types nothing at all. The character is kept separately, only
            so a run of typing can be folded into a literal type_text block.
            """
            vk = getattr(key, "vk", None)
            if vk is None:
                value = getattr(key, "value", None)
                vk = getattr(value, "vk", None)

            char = None
            try:
                if getattr(key, "char", None):
                    char = key.char
            except Exception:
                char = None

            name = None
            if vk is not None:
                try:
                    name = keymod.vk_to_key_name(int(vk))
                except Exception:
                    name = None
            # A name like "vk1234" means the VK table had nothing useful;
            # fall back to pynput's own spelling of the key.
            if not name or name.startswith("vk"):
                raw = str(key).replace("Key.", "").strip("'").lower()
                name = _ALIASES.get(raw, raw)
            else:
                name = _ALIASES.get(name, name)
            return name, char, (int(vk) if vk is not None else None)

        def on_press(key, injected=False, *_extra):
            if injected:
                return
            name, char, vk = key_identity(key)
            if name in self._suppress_keys or (char and char.lower() in self._suppress_keys):
                return
            if vk is not None and _input_backend.was_injected("key_down", int(vk)):
                return
            # Auto-repeat from a held key would otherwise flood the list with
            # duplicate downs that replay as machine-gun taps.
            with self._lock:
                for ev in reversed(self._events):
                    if ev.get("key") == name:
                        if ev["type"] == "key_down":
                            return
                        break
            self._append({"t": self._now(), "type": "key_down",
                          "key": name, "vk": vk, "char": char})

        def on_release(key, injected=False, *_extra):
            if injected:
                return
            name, char, vk = key_identity(key)
            if name in self._suppress_keys or (char and char.lower() in self._suppress_keys):
                return
            if vk is not None and _input_backend.was_injected("key_up", int(vk)):
                return
            self._append({"t": self._now(), "type": "key_up",
                          "key": name, "vk": vk, "char": char})

        def guard(fn):
            """A pynput callback that raises takes its listener thread down
            with it, and the recording then goes on "running" while capturing
            nothing. Log the fault and keep the hook alive instead.
            """
            def wrapped(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    self._log(tr("Recorder hook error: %s") % exc)
            return wrapped

        self._mouse_listener = pmouse.Listener(
            on_click=guard(on_click), on_move=guard(on_move),
            on_scroll=guard(on_scroll))
        self._key_listener = pkeyboard.Listener(
            on_press=guard(on_press), on_release=guard(on_release))
        self._mouse_listener.start()
        self._key_listener.start()

        # Optional: without it, drags are still recorded from positions, which
        # is correct everywhere except a game holding the cursor captured.
        self._held_buttons = set()
        self._raw_deltas = []
        try:
            from . import rawinput
            if rawinput.available():
                listener = rawinput.Listener(self._raw_delta)
                self._raw = listener if listener.start() else None
                if self._raw is None:
                    self._log(tr("Raw mouse input unavailable -- camera drags "
                                 "will be recorded from cursor positions only."))
        except Exception as exc:
            self._raw = None
            self._log(tr("Raw mouse input unavailable (%s).") % exc)

        _input_backend.clear_injected_marks()
        self.active = True
        return True

    def suppress(self, key_names) -> None:
        """Keys never written into a recording -- the hotkey that stops the
        recording must not become its own last event."""
        self._suppress_keys = {str(k).lower() for k in key_names if k}

    def stop(self):
        """Stop and return the raw events WITHOUT saving, so the caller can
        name them first (typing a name would otherwise be recorded)."""
        self.active = False
        for listener in (self._mouse_listener, self._key_listener):
            try:
                if listener is not None:
                    listener.stop()
            except Exception:
                pass
        self._mouse_listener = None
        self._key_listener = None
        if self._raw is not None:
            try:
                self._raw.stop()
            except Exception:
                pass
            self._raw = None
        self._held_buttons = set()
        self._raw_deltas = []
        with self._lock:
            events = list(self._events)
        return events

    def cancel(self) -> None:
        self.stop()
        with self._lock:
            self._events = []

    def peek_count(self) -> int:
        with self._lock:
            return len(self._events)


# ------------------------------------------------------- events -> blocks

def _new_id(prefix: str, index: int) -> str:
    return "%s%d" % (prefix, index)


def events_to_blocks(events, coord_space: str = "window",
                     min_gap_ms: int = 60, keep_moves: bool = False):
    """Turn a raw recording into editable blocks.

    Pairs each down with its matching up, collapses a quick down/up into one
    click block, turns a down-move-up into a drag, and inserts explicit wait
    blocks for the real pauses between actions. Gaps under min_gap_ms are
    dropped -- otherwise the list is 90% two-millisecond waits nobody wants
    to look at.

    min_gap_ms = 0 means NO waits at all. It used to mean "keep every gap",
    which put a wait before literally every action -- and since mouse moves
    are sampled at record_move_interval_ms, every one of those waits was that
    interval (80ms by default). Asking for a zero gap and getting an 80ms
    pause before each action is not what the number says, so zero now
    switches the wait blocks off entirely.
    """
    blocks = []
    if not events:
        return blocks

    events = sorted(events, key=lambda e: e.get("t", 0.0))
    key_x = "x" if coord_space == "window" else "sx"
    key_y = "y" if coord_space == "window" else "sy"

    def coord(ev, axis):
        return int(ev.get(key_x if axis == "x" else key_y,
                          ev.get("x" if axis == "x" else "y", 0)))

    index = 1
    # The clock starts at the first event that will actually produce a block.
    # The recorder's own base is the first event of ANY kind, so a leading
    # mouse movement that then gets discarded (keep_moves off) left a phantom
    # wait at the very start -- exactly what the recorder promises to avoid.
    last_t = 0.0
    for first in events:
        if keep_moves or first.get("type") != "move":
            last_t = float(first.get("t", 0.0))
            break

    pending_down = {}      # button -> down event, awaiting its up
    open_keys = {}         # key name -> (down event, index of its block)

    def next_id():
        nonlocal index
        block_id = _new_id("r", index)
        index += 1
        return block_id

    def push_wait(t):
        """Insert the real pause before an action that happens at time t.

        last_t only ever moves FORWARD. Feeding this a timestamp older than
        last_t (which the key_up branch used to do, passing the DOWN time
        after later events had already advanced the clock) produced a
        negative gap and then rewound last_t, inflating every later wait.
        """
        nonlocal last_t
        if t < last_t:
            return
        if min_gap_ms <= 0:
            # No pacing wanted at all -- the clock still advances so later
            # gaps stay honest if the setting is raised again.
            last_t = t
            return
        gap_ms = int(round((t - last_t) * 1000))
        if gap_ms >= min_gap_ms:
            blocks.append({"id": next_id(), "type": "wait_ms",
                           "enabled": True, "params": {"ms": gap_ms}})
        last_t = t

    def emit_mouse(down, up_ev, t):
        button = down.get("button", "left")
        x1, y1 = coord(down, "x"), coord(down, "y")
        x2, y2 = coord(up_ev, "x"), coord(up_ev, "y")
        hold_ms = int(round((t - float(down.get("t", t))) * 1000))
        if abs(x2 - x1) + abs(y2 - y1) > 6:
            # Drag blocks interpolate a straight line; the recorded
            # intermediate path is intentionally not kept, since the block
            # schema has no field for one.
            blocks.append({"id": next_id(), "type": "drag", "enabled": True,
                           "params": {"x": x1, "y": y1, "x2": x2, "y2": y2,
                                      "button": button,
                                      "duration_ms": max(60, hold_ms)}})
        else:
            blocks.append({"id": next_id(), "type": "click", "enabled": True,
                           "params": {"x": x1, "y": y1, "button": button,
                                      "clicks": 1,
                                      "hold_ms": max(20, min(hold_ms, 400))}})

    for ev in events:
        etype = ev.get("type")
        t = float(ev.get("t", 0.0))

        if etype == "move":
            # Moves during a held button belong to that drag. But a press
            # whose release was lost would otherwise swallow every move for
            # the REST of the recording, so a press left open longer than a
            # plausible drag is closed as a click and recording resumes.
            for button, down in list(pending_down.items()):
                if t - float(down.get("t", t)) > DANGLING_DOWN_S:
                    pending_down.pop(button, None)
                    emit_mouse(down, down, float(down.get("t", t)))
            if pending_down or not keep_moves:
                continue
            push_wait(t)
            blocks.append({"id": next_id(), "type": "move", "enabled": True,
                           "params": {"x": coord(ev, "x"), "y": coord(ev, "y"),
                                      "duration_ms": 0}})
            continue

        if etype == "mouse_down":
            button = ev.get("button", "left")
            stale = pending_down.pop(button, None)
            if stale is not None:
                # Its release was lost; emit it as a click rather than
                # dropping the action entirely.
                emit_mouse(stale, stale, float(stale.get("t", t)))
            push_wait(t)
            pending_down[button] = ev
            continue

        if etype == "mouse_up":
            button = ev.get("button", "left")
            down = pending_down.pop(button, None)
            if down is None:
                continue
            emit_mouse(down, ev, t)
            last_t = t
            continue

        if etype == "scroll":
            push_wait(t)
            blocks.append({"id": next_id(), "type": "scroll", "enabled": True,
                           "params": {"amount": int(ev.get("dy", 0)) * 120,
                                      "x": coord(ev, "x"), "y": coord(ev, "y")}})
            last_t = t
            continue

        if etype == "key_down":
            name = ev.get("key")
            if name in open_keys:
                # Its release was lost (focus change, dropped hook event).
                # Closing it here rather than ignoring the press means one
                # missing key_up costs one keystroke, not every future press
                # of that key for the rest of the recording.
                _stale_down, position = open_keys.pop(name)
                blocks[position]["params"]["hold_ms"] = 30
            # The block is emitted HERE, at the moment of the press, so the
            # wait before it is measured against the press. key_up only fills
            # in how long it was held.
            push_wait(t)
            char = ev.get("char")
            block = {"id": next_id(), "type": "send_key", "enabled": True,
                     "params": {"key": name, "hold_ms": 0, "modifiers": []}}
            # Carried OUTSIDE params (blocks.normalize drops unknown
            # top-level keys) purely so compress_text_blocks can rebuild
            # literal text: `key` stays the physical key so replay is
            # layout-independent, `_char` is what the layout produced.
            if char and len(str(char)) == 1:
                block["_char"] = str(char)
            blocks.append(block)
            open_keys[name] = (ev, len(blocks) - 1)
            last_t = t
            continue

        if etype == "key_up":
            name = ev.get("key")
            opened = open_keys.pop(name, None)
            if opened is None:
                continue
            down, position = opened
            hold_ms = max(0, int(round((t - float(down.get("t", t))) * 1000)))
            block = blocks[position]
            if hold_ms > LONG_HOLD_MS:
                # A multi-second press is a Hold Key, not a tap: send_key's
                # hold is an uninterruptible sleep, so a 30s recorded hold
                # would make Stop unresponsive for 30 seconds.
                char = block.pop("_char", None)
                block["type"] = "hold_key"
                block["params"] = {"key": name, "hold_ms": hold_ms}
            else:
                block["params"]["hold_ms"] = hold_ms
            if t > last_t:
                last_t = t

    # Anything still held when the recording stopped: emit it rather than
    # silently losing the action.
    for button, down in list(pending_down.items()):
        emit_mouse(down, down, float(down.get("t", last_t)))

    return blocks


def compress_text_blocks(blocks, min_run: int = 4, max_gap_ms: int = 400):
    """Fold a run of single-character send_key blocks into one type_text.

    Typing a sentence otherwise produces 40 unreadable rows; as one block it
    is also editable as text, which is the whole point.

    The short wait_ms blocks that events_to_blocks inserts BETWEEN keystrokes
    are absorbed rather than treated as run-breakers -- real typing always
    has 80-200ms gaps, so without this the run never survives long enough to
    fold. Their average becomes the resulting per-character delay.
    """
    out = []
    chars = []        # the send_key blocks collected so far
    absorbed = []     # wait blocks swallowed BETWEEN those keys
    pending = []      # waits held back until we know the run continues

    def flush():
        if len(chars) >= min_run:
            gaps = [int((w.get("params") or {}).get("ms", 0) or 0) for w in absorbed]
            delay = int(round(sum(gaps) / len(gaps))) if gaps else 20
            out.append({"id": chars[0]["id"], "type": "type_text", "enabled": True,
                        "once": chars[0].get("once", False),
                        "params": {"text": "".join(char_of(c) or "" for c in chars),
                                   "delay_ms": max(0, min(delay, 500))}})
            # `pending` are the waits AFTER the last character -- they belong
            # to whatever comes next, not to the typing, so they survive the
            # fold instead of being dropped with it.
            out.extend(pending)
        else:
            # Not long enough to fold -- emit exactly what came in, INCLUDING
            # the waits that were provisionally absorbed. Dropping them here
            # silently destroyed the recording's timing.
            merged = chars + absorbed + pending
            merged.sort(key=lambda b: _order.get(id(b), 0))
            out.extend(merged)
        chars.clear()
        absorbed.clear()
        pending.clear()

    _order = {}
    for position, block in enumerate(blocks):
        _order[id(block)] = position

    def char_of(block):
        """What this block would literally type, or None.

        Prefers the recorded _char (the layout's real output) over the
        physical key name, so text captured on a Cyrillic or AZERTY layout
        folds into the characters the user actually saw.
        """
        params = block.get("params") or {}
        if block.get("type") != "send_key" or params.get("modifiers"):
            return None
        recorded = block.get("_char")
        if recorded and len(str(recorded)) == 1 and str(recorded).isprintable():
            return str(recorded)
        name = str(params.get("key", ""))
        return name if len(name) == 1 else None

    for block in blocks:
        is_char = char_of(block) is not None
        if is_char:
            if pending:
                absorbed.extend(pending)
                pending.clear()
            chars.append(block)
            continue

        is_short_wait = (block.get("type") == "wait_ms"
                         and int((block.get("params") or {}).get("ms", 0) or 0) <= max_gap_ms)
        if is_short_wait and chars:
            pending.append(block)
            continue

        flush()
        out.append(block)
    flush()
    return out
