"""Thread-safe atomic settings.json access.

Every mutation goes through one module-level lock so a read-modify-write
from the UI thread can't lose a write from a background thread.
"""
import json
import os
import threading

from .constants import SETTINGS_FILE

_lock = threading.Lock()

DEFAULTS = {
    "target_mode": "window",        # "window" | "screen"
    "target_title": "",             # substring match for the chosen window
    "target_hwnd": 0,               # last attached hwnd, revalidated on use
    "action_delay_ms": 0,           # global pacing knob
    "default_threshold": 0.88,      # template matching
    "record_mouse_move": True,
    # How often the cursor position is sampled while recording. This is the
    # resolution of the recorded PATH, so it decides how smooth the replay
    # looks: at the old 80ms only ~12 positions a second were kept and the
    # cursor visibly hopped between them. 8ms is ~125Hz -- smooth, and still
    # far below the rate at which the raw hook fires.
    "record_move_interval_ms": 8,
    # The record screen's "Minimum gap" box, persisted so the preview shown
    # right after a take uses the same number the user last chose. 0 means
    # "insert no wait blocks at all".
    "record_min_gap_ms": 60,
    "theme_accent": "violet",
    "hotkey_start": "f1",
    "hotkey_stop": "f2",
    "hotkey_pause": "f3",
    "hotkey_record": "f4",
    "hotkey_pick": "f8",
    "loop_forever": True,
    "loop_count": 1,
    # The Watch phase. It is polled between blocks rather than on its own
    # thread: interrupting a block halfway would leave a mouse button held
    # or a key stuck down.
    "watch_enabled": True,
    "watch_interval_ms": 400,
    "watch_after": "continue",      # continue | restart loop | restart macro
    # Which server the Rejoin Server block goes back to when the block
    # itself is left blank -- the place id and the private server code.
    # Kept as settings so one edit fixes every rejoin block in every
    # macro when the private server link is regenerated.
    # A share link on its own is enough; the two fields under it are
    # only for the place id / linkCode form.
    "roblox_share_link": "",
    "roblox_place_id": "",
    "roblox_link_code": "",
    "theme": "midnight",
    "language": "en",
    # Discord webhook. Nothing is ever sent unless this is switched on AND a
    # Send Webhook block runs (or the user presses Test).
    "webhook_enabled": False,
    "webhook_url": "",
    "webhook_username": "Macro Studio",
    # Discord embed design defaults. The webhook URL remains the only secret.
    "webhook_title": "Macro report",
    "webhook_description": "",
    "webhook_color": "#8b5cf6",
    "webhook_footer": "Macro Studio",
    "webhook_timestamp": True,
}


def _load_unlocked() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    # A file holding valid JSON that is not an OBJECT (`null`, `"abc"`, `[]`)
    # parses fine and then explodes on .update() -- which would kill startup,
    # since load() runs before anything can report the problem.
    return data if isinstance(data, dict) else {}


def _save_unlocked(data: dict) -> bool:
    """Returns whether the write actually landed, so update() can tell the
    caller instead of silently reporting success on a read-only disk."""
    tmp = SETTINGS_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, SETTINGS_FILE)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def load() -> dict:
    """Stored values merged over DEFAULTS, so a new key added in a later
    version reads as its default instead of KeyError."""
    with _lock:
        merged = dict(DEFAULTS)
        merged.update(_load_unlocked())
        return merged


def save(data: dict) -> bool:
    with _lock:
        return _save_unlocked(data)


def update(changes: dict) -> dict:
    """Atomic multi-key merge under one lock. Preferred over
    load/mutate/save, which can drop a concurrent write.

    The returned dict carries `_saved: False` when the write failed, so a
    caller can surface "your setting did not persist" instead of showing a
    value that will be gone next launch.
    """
    with _lock:
        data = _load_unlocked()
        data.update(changes)
        saved = _save_unlocked(data)
        merged = dict(DEFAULTS)
        merged.update(data)
        if not saved:
            merged["_saved"] = False
        return merged


def get(key: str, fallback=None):
    return load().get(key, fallback)
