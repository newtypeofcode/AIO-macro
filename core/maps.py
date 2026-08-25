"""Map pictures for the Place Unit block.

A "map" here is the user's own screenshot of a game map, kept in
DATA_DIR/Maps. Nothing is captured automatically: a useful map picture is
framed by hand (the whole battlefield, no HUD in the way, taken once), and
re-taking it on every run would only give a worse one.

Everything is stored as PNG, including imported JPEGs -- the picker asks for
the picture by name and a single extension keeps that lookup from having to
guess, while re-encoding once at import beats decoding a JPEG on every open.
"""

import io
import json
import os
import re

from . import constants

# Letters (incl. Cyrillic), digits, space and a few separators. Anything else
# is dropped rather than escaped: these become file names, and a name the user
# typed must never be able to leave the Maps folder.
_UNSAFE = re.compile(r"[^0-9A-Za-z_\-. \u0400-\u04FF]+")

READ_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def safe_name(name: str) -> str:
    """File-system-safe map name, or "" when nothing usable is left."""
    cleaned = _UNSAFE.sub("", str(name or "")).strip().strip(".")
    return cleaned[:64]


def map_path(name: str) -> str:
    safe = safe_name(name)
    return os.path.join(constants.MAPS_DIR, safe + ".png") if safe else ""


def list_maps() -> list:
    """Names of the saved maps, sorted. Names only: the picker needs the list
    to open instantly, and decoding every picture just to fill a dropdown
    made that pause visible."""
    try:
        entries = sorted(os.listdir(constants.MAPS_DIR))
    except OSError:
        return []
    return [os.path.splitext(e)[0] for e in entries
            if e.lower().endswith(".png")]


def exists(name: str) -> bool:
    path = map_path(name)
    return bool(path) and os.path.isfile(path)


def meta_path(name: str) -> str:
    safe = safe_name(name)
    return os.path.join(constants.MAPS_DIR, safe + ".json") if safe else ""


def read_meta(name: str):
    """What the picture is a picture of, or None when nothing is recorded.

    {"origin": "window"|"screen", "left", "top", "width", "height",
     "ref_width", "ref_height"} -- see capture.frame_reference.

    A sidecar JSON rather than something inside the PNG: an imported picture
    genuinely has no such rectangle, and "no file" says that plainly instead
    of making every reader handle a half-filled header.
    """
    path = meta_path(name)
    if not path or not os.path.isfile(path):
        return None
    try:
        with io.open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("origin") not in ("window", "screen"):
        return None
    try:
        left, top = int(data["left"]), int(data["top"])
        width, height = int(data["width"]), int(data["height"])
        ref_w = int(data.get("ref_width") or width)
        ref_h = int(data.get("ref_height") or height)
    except (KeyError, TypeError, ValueError):
        return None
    # A zero size would divide by nothing downstream; a hand-edited or
    # truncated sidecar is treated as no sidecar at all.
    if width <= 0 or height <= 0 or ref_w <= 0 or ref_h <= 0:
        return None
    return {"origin": data["origin"], "left": left, "top": top,
            "width": width, "height": height,
            "ref_width": ref_w, "ref_height": ref_h}


def write_meta(name: str, meta) -> bool:
    """Record (or, with meta=None, forget) a map's frame of reference.

    Forgetting matters: re-saving a map from an imported file over one that
    was shot in-app would otherwise leave the old rectangle describing a
    picture it knows nothing about.
    """
    path = meta_path(name)
    if not path:
        return False
    if not meta:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            return False
        return True
    try:
        os.makedirs(constants.MAPS_DIR, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(meta, ensure_ascii=False, indent=1))
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_map(name: str, max_side: int = 0):
    """(data URI, width, height) for the picker, or None when unreadable.

    max_side shrinks the returned picture to that longest edge, for callers
    that only need a thumbnail. The width and height reported are always the
    real ones -- the picker maps clicks into stored pixels, so a scaled-down
    preview must never be allowed to change what a saved spot means.
    """
    from . import capture, vision
    import cv2

    path = map_path(name)
    if not path or not os.path.isfile(path):
        return None
    img = vision.imread_unicode(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    height, width = img.shape[:2]
    shown = img
    limit = int(max_side or 0)
    if limit > 0 and max(width, height) > limit:
        scale = float(limit) / float(max(width, height))
        shown = cv2.resize(img, (max(1, int(width * scale)),
                                 max(1, int(height * scale))),
                           interpolation=cv2.INTER_AREA)
    uri = capture.png_data_uri(shown)
    if not uri:
        return None
    return uri, int(width), int(height)


def save_map_frame(name: str, image, overwrite: bool = False, meta=None):
    """Write an in-memory BGR frame into Maps as PNG. Returns (name, w, h).

    Same collision rule as import_map -- a fresh shot lands beside the old
    map instead of over it, unless the caller is deliberately re-shooting a
    map that already exists (overwrite=True).
    """
    from . import vision

    if image is None:
        return None
    safe = safe_name(name)
    if not safe:
        return None
    os.makedirs(constants.MAPS_DIR, exist_ok=True)
    target = os.path.join(constants.MAPS_DIR, safe + ".png")
    if os.path.exists(target) and not overwrite:
        index = 2
        while os.path.exists(os.path.join(constants.MAPS_DIR,
                                          "%s %d.png" % (safe, index))):
            index += 1
        safe = "%s %d" % (safe, index)
        target = os.path.join(constants.MAPS_DIR, safe + ".png")
    if not vision.imwrite_unicode(target, image):
        return None
    height, width = image.shape[:2]
    # Written for the name actually used, which is not the one asked for when
    # a collision pushed the picture to "<name> 2".
    write_meta(safe, meta)
    return safe, int(width), int(height)


def import_map(src_path: str, name: str = ""):
    """Copy an image file into Maps as PNG. Returns (name, w, h) or None.

    Decoded and re-encoded rather than copied byte-for-byte so that a JPEG,
    a BMP or a screenshot with an alpha channel all end up as the same kind
    of file the picker and the runner expect.
    """
    from . import vision
    import cv2

    src = str(src_path or "")
    if not src or not os.path.isfile(src):
        return None
    safe = safe_name(name) or safe_name(os.path.splitext(os.path.basename(src))[0])
    if not safe:
        return None
    img = vision.imread_unicode(src, cv2.IMREAD_COLOR)
    if img is None:
        return None
    os.makedirs(constants.MAPS_DIR, exist_ok=True)

    # A second import of the same picture must not silently replace a map
    # that existing blocks already point at, so it lands beside it.
    target = os.path.join(constants.MAPS_DIR, safe + ".png")
    if os.path.exists(target):
        index = 2
        while os.path.exists(os.path.join(constants.MAPS_DIR,
                                          "%s %d.png" % (safe, index))):
            index += 1
        safe = "%s %d" % (safe, index)
        target = os.path.join(constants.MAPS_DIR, safe + ".png")

    if not vision.imwrite_unicode(target, img):
        return None
    height, width = img.shape[:2]
    # An imported file carries no geometry, and a stale sidecar from an
    # earlier map of the same name would describe the wrong picture.
    write_meta(safe, None)
    return safe, int(width), int(height)


def delete_map(name: str) -> bool:
    path = map_path(name)
    if not path:
        return False
    # Belt and braces: never unlink anything outside Maps/, even if safe_name
    # were ever loosened.
    root = os.path.abspath(constants.MAPS_DIR)
    if not os.path.abspath(path).startswith(root + os.sep):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    write_meta(name, None)          # the sidecar goes with the picture
    return True
