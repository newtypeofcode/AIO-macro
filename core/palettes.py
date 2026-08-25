"""CRUD and validation for shareable user block palettes."""
import json
import os

from .constants import PALETTES_DIR
from .jsonstore import read_json, write_json_atomic
from .naming import safe_name


def _path(name: str) -> str:
    return os.path.join(PALETTES_DIR, safe_name(name, "palette") + ".json")


def _clean(name: str, types) -> dict:
    seen = set()
    clean_types = []
    for value in types or []:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            clean_types.append(value)
    return {"name": safe_name(name, "palette"), "types": clean_types}


def list_palettes() -> list:
    try:
        names = sorted(f[:-5] for f in os.listdir(PALETTES_DIR)
                       if f.lower().endswith(".json"))
    except OSError:
        names = []
    result = []
    for name in names:
        data = load_palette(name)
        if data:
            result.append(data)
    return result


def load_palette(name: str):
    data = read_json(_path(name))
    if not isinstance(data, dict):
        return None
    return _clean(data.get("name") or name, data.get("types"))


def save_palette(name: str, types) -> dict:
    data = _clean(name, types)
    write_json_atomic(_path(data["name"]), data)
    return data


def delete_palette(name: str) -> bool:
    try:
        os.remove(_path(name))
        return True
    except OSError:
        return False


def export_palette(name: str, path: str) -> dict:
    data = load_palette(name)
    if not data:
        raise ValueError("palette_not_found")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return data


def import_palette(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError("bad_palette")
    return save_palette(data["name"], data.get("types"))
