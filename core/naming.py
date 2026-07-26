"""One filename sanitiser, shared by everything that turns a user-typed name
into a file or folder.

Unicode is deliberately KEPT: people name their macros, recordings and images
in their own language, and stripping non-ASCII silently turned "моя запись"
into "recording" -- two saves under different names quietly overwrote each
other. Only genuine filename hazards are removed.
"""
import os

# Characters Windows forbids in a filename, plus both path separators (this
# is the directory-escape guard) and control characters.
FORBIDDEN = set('<>:"/\\|?*') | {chr(c) for c in range(32)}

# Reserved DOS device names: a file or folder called CON or LPT1 cannot be
# created on Windows at all.
_RESERVED = {"CON", "PRN", "AUX", "NUL"}
_RESERVED |= {"COM%d" % i for i in range(1, 10)}
_RESERVED |= {"LPT%d" % i for i in range(1, 10)}

MAX_LENGTH = 80


def safe_name(name, fallback: str = "") -> str:
    """Sanitise a user-typed name for use as a file or folder name.

    Returns `fallback` (default "") when nothing usable is left, so callers
    can decide whether an unusable name is an error or gets a default.
    """
    cleaned = "".join(c for c in str(name or "") if c not in FORBIDDEN)
    # Trailing dots and spaces are silently dropped by Windows itself, which
    # would make "a." and "a" the same file.
    cleaned = cleaned.strip().strip(". ")
    if not cleaned or cleaned in (".", ".."):
        return fallback
    if cleaned.upper().split(".")[0] in _RESERVED:
        return fallback
    return cleaned[:MAX_LENGTH]


def is_inside(path: str, root: str) -> bool:
    """Whether `path` really resolves inside `root` -- the check that makes a
    sanitiser mistake non-fatal."""
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)
