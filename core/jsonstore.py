"""Crash-safe atomic JSON writes for user-owned data."""
import json
import os


def write_json_atomic(path: str, data) -> None:
    """Write to <path>.tmp, fsync, then os.replace onto the target.

    Catches BaseException rather than Exception so a KeyboardInterrupt
    landing mid-dump still removes the scratch file instead of leaving a
    stray .tmp that looks like a real save.
    """
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default
