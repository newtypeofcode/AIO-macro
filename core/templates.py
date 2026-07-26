"""CRUD for saved macros (Templates/) and recordings (Recordings/)."""
import json
import os

from .constants import TEMPLATES_DIR, RECORDINGS_DIR
from .jsonstore import write_json_atomic, read_json
from .naming import safe_name as _safe


def _safe_name(name: str, fallback: str = "macro") -> str:
    """Names come straight from the UI and become filenames.

    Unicode is preserved: the old ASCII-only filter turned every Cyrillic
    name into the fallback, so "моя запись" and "другая запись" both saved
    as "recording" and silently overwrote each other.
    """
    return _safe(name, fallback)


def _list_json(folder: str):
    try:
        return sorted(f[:-5] for f in os.listdir(folder) if f.lower().endswith(".json"))
    except OSError:
        return []


# ------------------------------------------------------------------ macros

def list_macros():
    return _list_json(TEMPLATES_DIR)


def save_macro(name: str, data: dict) -> str:
    safe = _safe_name(name)
    payload = dict(data or {})
    payload["name"] = safe
    write_json_atomic(os.path.join(TEMPLATES_DIR, safe + ".json"), payload)
    return safe


def load_macro(name: str) -> dict:
    safe = _safe_name(name)
    data = read_json(os.path.join(TEMPLATES_DIR, safe + ".json"))
    if not isinstance(data, dict):
        return {"name": safe, "phases": {"setup": [], "loop": []}}
    data.setdefault("name", safe)
    phases = data.setdefault("phases", {})
    phases.setdefault("setup", [])
    phases.setdefault("loop", [])
    return data


def delete_macro(name: str) -> bool:
    try:
        os.remove(os.path.join(TEMPLATES_DIR, _safe_name(name) + ".json"))
        return True
    except OSError:
        return False


def export_macro(name: str) -> dict:
    return load_macro(name)


def import_macro(payload: dict, name: str = "") -> str:
    if not isinstance(payload, dict):
        raise ValueError("not a macro file")
    target = name or payload.get("name") or "imported"
    return save_macro(target, payload)


# -------------------------------------------------------------- recordings

def list_recordings():
    return _list_json(RECORDINGS_DIR)


def save_recording(name: str, events: list, blocks=None) -> str:
    """Store a recording.

    `blocks` is the optional EDITED action list. The raw events are always
    kept: they are the lossless original, so editing the actions can be
    undone and re-derived, and a recording made before the editor existed
    still plays.
    """
    safe = _safe_name(name, "recording")
    payload = {"name": safe, "events": events or []}
    if blocks is not None:
        payload["blocks"] = blocks
    write_json_atomic(os.path.join(RECORDINGS_DIR, safe + ".json"), payload)
    return safe


def recording_exists(name: str) -> bool:
    safe = _safe_name(name, "recording")
    return os.path.isfile(os.path.join(RECORDINGS_DIR, safe + ".json"))


def load_recording(name: str) -> dict:
    """Load a recording.

    `exists` distinguishes a real empty recording from a missing file. Without
    it, callers happily "loaded" a deleted recording, wrote it back, and
    recreated it as a permanently empty zombie.
    """
    safe = _safe_name(name, "recording")
    data = read_json(os.path.join(RECORDINGS_DIR, safe + ".json"))
    if not isinstance(data, dict):
        return {"name": safe, "events": [], "blocks": None, "exists": False}
    data.setdefault("events", [])
    data.setdefault("blocks", None)
    data["exists"] = True
    return data


def update_recording_blocks(name: str, blocks) -> str:
    """Replace the edited action list, keeping the original events.

    Refuses to write when the recording is gone -- otherwise editing a
    recording that was deleted in another screen silently recreated it.
    """
    existing = load_recording(name)
    if not existing.get("exists"):
        raise FileNotFoundError(name)
    return save_recording(name, existing.get("events") or [], blocks)


def delete_recording(name: str) -> bool:
    try:
        os.remove(os.path.join(RECORDINGS_DIR, _safe_name(name, "recording") + ".json"))
        return True
    except OSError:
        return False
