"""Saved block groups.

A group is a named, reusable list of blocks -- "the five blocks that rejoin
and re-centre the camera" -- that can be dropped into Setup, Loop or Watch as
many times as needed. It is not a macro: it has no phases, no target and no
loop settings, and inserting it copies the blocks in rather than linking to
them, so editing one copy never disturbs another.

Stored one JSON file per group in DATA_DIR/Groups, next to Templates and
Recordings, so an update cannot reach them.
"""
import os
import time

from .constants import GROUPS_DIR
from .jsonstore import read_json, write_json_atomic
from .naming import is_inside, safe_name as _clean


def safe_name(name: str, fallback: str = "group") -> str:
    return _clean(name, fallback)


def _path(name: str) -> str:
    path = os.path.join(GROUPS_DIR, safe_name(name) + ".json")
    # A sanitiser slip must not let a name like ..\..\settings write outside
    # the folder, so the resolved path is checked as well.
    if not is_inside(path, GROUPS_DIR):
        raise ValueError("bad group name")
    return path


def list_groups() -> list:
    """Every saved group as {name, count, saved}, newest first.

    The block count travels with the list because that is what the picker
    shows, and reading every file to render one grid would be silly.
    """
    try:
        names = os.listdir(GROUPS_DIR)
    except OSError:
        return []
    out = []
    for filename in names:
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(GROUPS_DIR, filename)
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        blocks = data.get("blocks")
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = 0.0
        out.append({
            "name": str(data.get("name") or filename[:-5]),
            "count": len(blocks) if isinstance(blocks, list) else 0,
            "saved": float(data.get("saved") or stamp),
        })
    out.sort(key=lambda item: item["saved"], reverse=True)
    return out


def exists(name: str) -> bool:
    try:
        return os.path.isfile(_path(name))
    except ValueError:
        return False


def save_group(name: str, blocks: list, overwrite: bool = True) -> str:
    """Store the blocks under a name. Returns the name actually used."""
    safe = safe_name(name)
    path = _path(safe)
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(safe)
    os.makedirs(GROUPS_DIR, exist_ok=True)
    write_json_atomic(path, {
        "name": safe,
        "blocks": list(blocks or []),
        "saved": time.time(),
    })
    return safe


def load_group(name: str) -> list:
    """The group's blocks, or [] when there is no such group.

    Deliberately not normalised here: the runner and the UI each have their
    own normaliser, and running a stale block through the wrong one is how a
    field silently loses its value.
    """
    try:
        data = read_json(_path(name))
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    blocks = data.get("blocks")
    return blocks if isinstance(blocks, list) else []


def rename_group(name: str, new_name: str) -> str:
    """Rename in place. Returns the new name, or "" if it did not happen."""
    blocks = load_group(name)
    if not blocks:
        return ""
    saved = save_group(new_name, blocks)
    if saved != safe_name(name):
        delete_group(name)
    return saved


def delete_group(name: str) -> bool:
    try:
        os.remove(_path(name))
        return True
    except (OSError, ValueError):
        return False
