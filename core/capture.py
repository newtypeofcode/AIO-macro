"""Screen and window capture with a thread-local mss pool.

Two paths, tried in order and remembered:
  1. window contents via PrintWindow -- works while the target is covered
  2. plain screen grab via mss BitBlt -- works when PrintWindow returns black

The switch is sticky but self-correcting in BOTH directions: whichever path
last produced real pixels wins, and a black frame flips it back.
"""
import threading
import time

import numpy as np

from . import window as wm

_local = threading.local()
# A plain set, not a WeakSet: mss.MSS defines __slots__ and cannot be weakly
# referenced. Membership is therefore released explicitly by close_mss(),
# which every capture path calls in its finally, so a thread that exits
# normally does not leak its instance.
_instances = set()
# ids of instances closed by close_all_mss, so another thread's thread-local
# slot can notice its handle is dead instead of using it after close.
_closed_instances = set()
_lock = threading.Lock()
_mss_factory = None

# None = undecided, True = window-content path, False = screen-grab path.
_use_window_capture = None


def set_mss_factory(factory) -> None:
    """Injection point for tests."""
    global _mss_factory
    _mss_factory = factory


def get_mss():
    """Thread-local mss instance. Reused rather than recreated per grab:
    a fresh MSS() per capture thrashes GDI handles at poll rates."""
    inst = getattr(_local, "mss", None)
    if inst is not None and id(inst) in _closed_instances:
        # close_all_mss cannot reach another thread's local slot, so a stale
        # handle is detected here instead of being reused after close.
        # Tracked by id() because mss.MSS has __slots__ and takes neither an
        # attribute nor a weak reference.
        _closed_instances.discard(id(inst))
        inst = None
        _local.mss = None
    if inst is None:
        if _mss_factory is not None:
            inst = _mss_factory()
        else:
            import mss as mss_mod
            inst = mss_mod.mss()
        _local.mss = inst
        with _lock:
            _instances.add(inst)
    return inst


def close_mss() -> None:
    inst = getattr(_local, "mss", None)
    if inst is not None:
        try:
            inst.close()
        except Exception:
            pass
        with _lock:
            _instances.discard(inst)
        _local.mss = None


def close_all_mss() -> None:
    """Shutdown-only: closes every thread's instance.

    Other threads keep a reference in their own thread-local slot, which this
    cannot reach, so `_closed` is stamped on each instance and get_mss()
    treats a closed one as absent and rebuilds it.
    """
    with _lock:
        items = list(_instances)
        _instances.clear()
    for inst in items:
        try:
            inst.close()
        except Exception:
            pass
        try:
            _closed_instances.add(id(inst))
        except Exception:
            pass


def grab_screen_bgr(left: int, top: int, width: int, height: int):
    """Raw screen-region grab as a BGR ndarray."""
    if width <= 0 or height <= 0:
        return None
    try:
        sct = get_mss()
        shot = sct.grab({"left": int(left), "top": int(top),
                          "width": int(width), "height": int(height)})
        arr = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return arr[:, :, :3].copy()
    except Exception:
        # A dead handle (display change, session switch) must not be reused.
        close_mss()
        return None


def capture_target_bgr(hwnd=None, region=None):
    """The main capture. Returns a BGR ndarray of the target's client area,
    or of `region` (x, y, w, h in client coordinates) within it.

    With hwnd=None it captures the screen instead, and `region` is read as
    absolute screen coordinates.
    """
    global _use_window_capture

    if not hwnd or not wm.is_window(hwnd):
        if region:
            return grab_screen_bgr(*region)
        sw, sh = wm.get_screen_size()
        return grab_screen_bgr(0, 0, sw, sh)

    # A minimized target has no meaningful client pixels. Restore it here,
    # at the single capture boundary, so every caller gets a real screenshot.
    if wm.restore_if_minimized(hwnd):
        # Give the compositor a moment to recreate the client surface before
        # PrintWindow/BitBlt reads it.
        time.sleep(0.25)

    def _window_path():
        result = wm.capture_window_rgb(hwnd)
        if result is None:
            return None
        frame, _w, _h = result
        return frame

    def _screen_path():
        left, top, w, h = wm.get_client_rect_screen(hwnd)
        if w <= 0 or h <= 0:
            return None
        return grab_screen_bgr(left, top, w, h)

    # Window contents first while undecided: a screen grab of an occluded
    # window silently returns the COVERING window's pixels, and since those
    # are not black the fallback logic can never detect the mistake. The
    # window path either works or comes back black, which is detectable.
    prefer_window = True if _use_window_capture is None else _use_window_capture
    order = (_window_path, _screen_path) if prefer_window else (_screen_path, _window_path)

    frame = None
    for fn in order:
        frame = fn()
        if frame is not None and frame.any():
            _use_window_capture = (fn is _window_path)
            break
        frame = None

    if frame is None:
        return None

    if region:
        x, y, w, h = [int(v) for v in region]
        fh, fw = frame.shape[:2]
        # A region outside the frame is a caller mistake, not something to
        # paper over: clamping it into an in-frame rect used to return
        # pixels from the wrong place while the caller added back the
        # UNCLAMPED origin, so every reported coordinate was wrong.
        if x < 0 or y < 0 or x >= fw or y >= fh:
            return None
        w = min(w, fw - x)
        h = min(h, fh - y)
        if w < 1 or h < 1:
            return None
        return frame[y:y + h, x:x + w].copy()
    return frame


def frame_reference(hwnd=None, frame=None):
    """What a captured frame is a picture OF, as a dict, or None.

    {"origin": "window"|"screen", "left", "top", "width", "height",
     "ref_width", "ref_height"}

    Both window paths in capture_target_bgr cover the CLIENT area (PrintWindow
    is handed the client DC at the client size), so a window frame is measured
    from the client origin and its rect is in client coordinates -- that is
    what lets a spot be rescaled when the window is a different size later.
    A screen frame's rect is absolute screen pixels instead.

    Recorded with saved map pictures because the two cannot be told apart
    afterwards: the same spot on a full-screen shot means a screen coordinate
    and on a window shot a window-relative one, and reading one as the other
    puts the click a window-offset away from where it was picked.
    """
    if frame is None:
        return None
    fh, fw = frame.shape[:2]
    if fw <= 0 or fh <= 0:
        return None
    if not hwnd or not wm.is_window(hwnd):
        return {"origin": "screen", "left": 0, "top": 0,
                "width": int(fw), "height": int(fh)}
    return {"origin": "window", "left": 0, "top": 0,
            "width": int(fw), "height": int(fh),
            "ref_width": int(fw), "ref_height": int(fh)}


def force_window_capture(on: bool = True) -> None:
    global _use_window_capture
    _use_window_capture = bool(on)


def png_data_uri(frame_bgr, scale: int = 1) -> str:
    """BGR ndarray -> base64 PNG data URI for the UI."""
    import base64
    import cv2

    if frame_bgr is None:
        return ""
    img = frame_bgr
    if scale and scale != 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
