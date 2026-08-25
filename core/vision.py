"""Template matching and color detection over captured frames.

Coordinates returned are in CLIENT space of the target window (or screen
space in screen mode), matching how block coordinates are stored.
"""
import os
import time

import cv2
import numpy as np

from . import capture
from .constants import ASSETS_DIR

DEFAULT_THRESHOLD = 0.88
# 1.0 first so an exact-size hit costs nothing; the spread only runs on a
# miss, absorbing UI that renders slightly larger/smaller elsewhere.
SCALE_FACTORS = (1.0, 0.95, 1.05, 0.90, 1.10)

_template_cache = {}
_variant_cache = {}
_scaled_cache = {}


class TemplateNotFound(Exception):
    """No reference image on disk for this name -- a config problem, not a
    'not on screen right now' miss."""


def clear_cache() -> None:
    _template_cache.clear()
    _variant_cache.clear()
    _scaled_cache.clear()


def template_variant_paths(name: str):
    """Every reference PNG registered under one name.

    Resolution order: loose <name>.png, then every file inside <name>/ with
    the same-named one first. Multiple variants exist so a button that
    renders differently on another setup can be taught extra crops without
    touching code.
    """
    if not name:
        return []
    cached = _variant_cache.get(name)
    if cached is not None:
        return cached

    paths = []
    loose = os.path.join(ASSETS_DIR, name + ".png")
    if os.path.isfile(loose):
        paths.append(loose)

    folder = os.path.join(ASSETS_DIR, name)
    if os.path.isdir(folder):
        try:
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
        except OSError:
            files = []
        primary = name + ".png"
        if primary in files:
            files.remove(primary)
            files.insert(0, primary)
        paths.extend(os.path.join(folder, f) for f in files)

    _variant_cache[name] = paths
    return paths


def list_templates():
    """Catalog for the Image Manager: name -> list of variant files."""
    out = []
    try:
        entries = sorted(os.listdir(ASSETS_DIR))
    except OSError:
        return out
    seen = set()
    for entry in entries:
        full = os.path.join(ASSETS_DIR, entry)
        if os.path.isdir(full):
            name = entry
        elif entry.lower().endswith(".png"):
            name = entry[:-4]
        else:
            continue
        if name in seen:
            continue
        seen.add(name)
        variants = template_variant_paths(name)
        if variants:
            out.append({"name": name, "files": [os.path.basename(p) for p in variants],
                        "count": len(variants)})
    return out


def _stamp(path: str):
    """(mtime, size) -- the cache key component that notices an edited file.

    Keying on the path alone meant re-saving a reference PNG from the Image
    Manager had no effect until the app was restarted, which reads as "the
    new crop just doesn't work".
    """
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def imread_unicode(path: str, flags=cv2.IMREAD_UNCHANGED):
    """cv2.imread that works with non-ASCII paths.

    OpenCV passes the filename to the C runtime as bytes, so on Windows a
    path containing Cyrillic (or any non-ANSI character) simply fails and
    returns None. Reading the bytes in Python and decoding them in memory
    sidesteps the filename entirely.
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite_unicode(path: str, image) -> bool:
    """cv2.imwrite that works with non-ASCII paths. Returns success."""
    ext = os.path.splitext(path)[1] or ".png"
    try:
        ok, buf = cv2.imencode(ext, image)
        if not ok:
            return False
        with open(path, "wb") as fh:
            fh.write(buf.tobytes())
        return True
    except (OSError, cv2.error):
        return False


def _load_gray(path: str):
    stamp = _stamp(path)
    cached = _template_cache.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    img = imread_unicode(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    elif img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    _template_cache[path] = (stamp, gray)
    return gray


def load_template_grays(name: str):
    paths = template_variant_paths(name)
    if not paths:
        raise TemplateNotFound(name)
    grays = [g for g in (_load_gray(p) for p in paths) if g is not None]
    if not grays:
        raise TemplateNotFound(name)
    return grays


def _scaled_templates(name: str, scale: float):
    grays = load_template_grays(name)
    if scale == 1.0:
        # Already cached per-file with a freshness stamp; caching again here
        # would just be a second copy that can go stale independently.
        return grays
    # The stamps are part of the key, so a re-saved reference PNG produces a
    # different key and the resized copies of the OLD pixels are never
    # returned again.
    key = (name, scale, tuple(_stamp(p) for p in template_variant_paths(name)))
    cached = _scaled_cache.get(key)
    if cached is not None:
        return cached
    out = []
    for gray in grays:
        h, w = gray.shape[:2]
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        out.append(cv2.resize(gray, (nw, nh), interpolation=interp))
    _scaled_cache[key] = out
    return out


def _match_one(haystack_gray, template_gray, threshold: float):
    th, tw = template_gray.shape[:2]
    hh, hw = haystack_gray.shape[:2]
    if th > hh or tw > hw:
        return None
    result = cv2.matchTemplate(haystack_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    # TM_CCOEFF_NORMED divides by local window variance: a flat, solid patch
    # yields 0/0 -> inf, which sails past ANY threshold as a confident match.
    result[~np.isfinite(result)] = -1
    _minv, maxv, _minl, maxl = cv2.minMaxLoc(result)
    if maxv < threshold:
        return None
    x, y = maxl
    return {"x": int(x), "y": int(y), "w": int(tw), "h": int(th),
            "cx": int(x + tw / 2), "cy": int(y + th / 2), "score": float(maxv)}


def find_in_frame(frame_bgr, name: str, threshold: float = None):
    """Best match of `name` inside an already-captured frame."""
    if frame_bgr is None:
        return None
    threshold = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
    # Scale is the OUTER loop so the common 1.0 case never pays for the spread.
    for scale in SCALE_FACTORS:
        best = None
        for template in _scaled_templates(name, scale):
            match = _match_one(gray, template, threshold)
            if match and (best is None or match["score"] > best["score"]):
                best = match
        if best:
            best["scale"] = scale
            return best
    return None


def find_image(hwnd, name: str, region=None, threshold: float = None):
    """Capture and search. Returns a match dict in client coordinates."""
    frame = capture.capture_target_bgr(hwnd, region)
    if frame is None:
        return None
    match = find_in_frame(frame, name, threshold)
    if match and region:
        match["x"] += int(region[0])
        match["y"] += int(region[1])
        match["cx"] += int(region[0])
        match["cy"] += int(region[1])
    return match


def find_all_images(hwnd, name: str, region=None, threshold: float = None,
                   max_results: int = 50):
    """All non-overlapping matches of `name` in client coordinates.
    Returns list of match dicts sorted by score descending."""
    frame = capture.capture_target_bgr(hwnd, region)
    if frame is None:
        return []
    threshold = DEFAULT_THRESHOLD if threshold is None else float(threshold)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    results = []
    for scale in SCALE_FACTORS:
        for template in _scaled_templates(name, scale):
            th, tw = template.shape[:2]
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            locs = np.where(res >= threshold)
            for pt in zip(locs[1], locs[0]):
                cx, cy = pt[0] + tw // 2, pt[1] + th // 2
                # Suppress duplicates within half a template width
                too_close = any(
                    abs(m["cx"] - cx) < tw // 2 and abs(m["cy"] - cy) < th // 2
                    for m in results
                )
                if not too_close:
                    ox, oy = (int(region[0]), int(region[1])) if region else (0, 0)
                    results.append({
                        "x": pt[0] + ox, "y": pt[1] + oy,
                        "cx": cx + ox, "cy": cy + oy,
                        "w": tw, "h": th,
                        "score": float(res[pt[1], pt[0]]),
                    })
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
    results.sort(key=lambda m: m["score"], reverse=True)
    return results


def find_image_any(hwnd, names, region=None, threshold: float = None):
    """Several differently-named templates against ONE captured frame.

    Only raises TemplateNotFound when EVERY name is missing from disk --
    a single missing variant shouldn't kill a multi-candidate check.
    """
    # Materialised up front: a generator argument would be consumed by the
    # first pass and the missing-count comparison below would then always
    # think nothing was missing.
    names = list(names)
    frame = capture.capture_target_bgr(hwnd, region)
    if frame is None:
        return None, None
    missing = 0
    for name in names:
        try:
            match = find_in_frame(frame, name, threshold)
        except TemplateNotFound:
            missing += 1
            continue
        if match:
            if region:
                match["x"] += int(region[0])
                match["y"] += int(region[1])
                match["cx"] += int(region[0])
                match["cy"] += int(region[1])
            return match, name
    if missing and missing == len(names):
        raise TemplateNotFound(", ".join(names))
    return None, None


def wait_for_image(hwnd, name: str, region=None, threshold: float = None,
                   timeout: float = 8.0, interval: float = 0.25, stop_event=None):
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return None
        match = find_image(hwnd, name, region, threshold)
        if match:
            return match
        time.sleep(interval)
    return None


def wait_for_image_gone(hwnd, name: str, region=None, threshold: float = None,
                        timeout: float = 8.0, interval: float = 0.25, stop_event=None):
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return False
        frame = capture.capture_target_bgr(hwnd, region)
        # A failed capture is NOT proof the image left the screen. Treating
        # None as "gone" made this block succeed instantly whenever capture
        # was momentarily unavailable (window minimized, display switch).
        if frame is not None and find_in_frame(frame, name, threshold) is None:
            return True
        time.sleep(interval)
    return False


def sample_color(hwnd, x: int, y: int):
    """RGB tuple of one client-space pixel."""
    frame = capture.capture_target_bgr(hwnd, (int(x), int(y), 1, 1))
    if frame is None or frame.size == 0:
        return None
    b, g, r = frame[0, 0][:3]
    return int(r), int(g), int(b)


def color_matches(hwnd, x: int, y: int, rgb, tolerance: int = 20) -> bool:
    """Per-channel distance, not euclidean: a tolerance slider users can
    reason about ('within 20 of each channel')."""
    got = sample_color(hwnd, x, y)
    if got is None:
        return False
    return all(abs(int(got[i]) - int(rgb[i])) <= int(tolerance) for i in range(3))


def wait_for_color(hwnd, x: int, y: int, rgb, tolerance: int = 20,
                   timeout: float = 8.0, interval: float = 0.2, stop_event=None) -> bool:
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return False
        if color_matches(hwnd, x, y, rgb, tolerance):
            return True
        time.sleep(interval)
    return False


def find_color_region(hwnd, region, rgb, tolerance: int = 20, min_pixels: int = 30):
    """Centroid of the largest run of a colour inside a region -- template
    free detection for things that change shape but not hue (health bars,
    highlighted tiles)."""
    frame = capture.capture_target_bgr(hwnd, region)
    if frame is None:
        return None
    target = np.array([int(rgb[2]), int(rgb[1]), int(rgb[0])], dtype=np.int16)  # BGR
    diff = np.abs(frame.astype(np.int16) - target)
    mask = np.all(diff <= int(tolerance), axis=2).astype(np.uint8)
    if int(mask.sum()) < int(min_pixels):
        return None
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if num <= 1:
        return None
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[largest, cv2.CC_STAT_AREA] < int(min_pixels):
        return None
    cx, cy = centroids[largest]
    ox, oy = (int(region[0]), int(region[1])) if region else (0, 0)
    return {"cx": int(cx) + ox, "cy": int(cy) + oy,
            "area": int(stats[largest, cv2.CC_STAT_AREA])}


def save_debug(frame_bgr, name: str) -> str:
    from .constants import DEBUG_DIR
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, "%s.png" % name)
    return path if imwrite_unicode(path, frame_bgr) else ""
