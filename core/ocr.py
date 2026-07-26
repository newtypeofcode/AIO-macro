"""Text detection.

Two engines. Windows.Media.Ocr (via the winsdk WinRT projection) is
PREFERRED: it ships with Win10/11, needs no install and is roughly an order
of magnitude faster. Tesseract is the fallback for machines without it.
"""
import asyncio
import os
import re
import subprocess
import threading

import cv2
import numpy as np

_win_engine = None
_win_checked = False
_win_lock = threading.Lock()

_FALLBACK_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
# None = unchecked, "" = confirmed unavailable, else the resolved exe path.
_resolved_tesseract_cmd = None


# ---------------------------------------------------------------- Windows OCR

_win_failures = 0
# After this many consecutive failures the engine is written off and the
# Tesseract fallback becomes reachable. Without it, an engine that merely
# EXISTS but never returns anything usable permanently masked the fallback.
_WIN_FAILURE_LIMIT = 3


def windows_ocr_available() -> bool:
    global _win_engine, _win_checked
    # The whole probe runs under the lock: setting _win_checked before the
    # engine was populated let a concurrent caller see "unavailable" and
    # silently fall through to Tesseract.
    with _win_lock:
        if _win_checked:
            return _win_engine is not None
        try:
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.globalization import Language
            engine = None
            try:
                engine = OcrEngine.try_create_from_language(Language("en-US"))
            except Exception:
                engine = None
            if engine is None:
                engine = OcrEngine.try_create_from_user_profile_languages()
            _win_engine = engine
        except Exception:
            _win_engine = None
        _win_checked = True
        return _win_engine is not None


def _windows_ocr(img) -> str:
    if not windows_ocr_available():
        return ""
    try:
        from winsdk.windows.graphics.imaging import (
            SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode)
        from winsdk.windows.security.cryptography import CryptographicBuffer

        if img.ndim == 2:
            bgra = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        else:
            bgra = img
        h, w = bgra.shape[:2]
        buf = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)

        with _win_lock:
            # A fresh loop per call: asyncio loops are thread-bound, and this
            # gets called from whichever worker thread is running the macro.
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(_await_ocr(bitmap))
            finally:
                loop.close()
        global _win_failures
        _win_failures = 0
        return " ".join(line.text for line in result.lines) if result else ""
    except Exception:
        _note_windows_failure()
        return ""


def _note_windows_failure() -> None:
    """Write the engine off after repeated hard failures so the Tesseract
    fallback becomes reachable. Previously an engine that could be created
    but never actually worked masked the fallback forever."""
    global _win_failures, _win_engine
    with _win_lock:
        _win_failures += 1
        if _win_failures >= _WIN_FAILURE_LIMIT and _win_engine is not None:
            _win_engine = None


async def _await_ocr(bitmap):
    return await _win_engine.recognize_async(bitmap)


# ------------------------------------------------------------------ Tesseract

def _tesseract_runs(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=8,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
        return True
    except Exception:
        return False


def get_pytesseract():
    """Resolve the engine once and memoize. Raises RuntimeError when the
    package is present but the native binary isn't."""
    global _resolved_tesseract_cmd
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("pytesseract is not installed")

    if _resolved_tesseract_cmd is None:
        found = ""
        if _tesseract_runs("tesseract"):
            found = "tesseract"
        else:
            for path in _FALLBACK_TESSERACT_PATHS:
                if os.path.isfile(path) and _tesseract_runs(path):
                    found = path
                    break
        _resolved_tesseract_cmd = found
    if not _resolved_tesseract_cmd:
        raise RuntimeError("Tesseract engine not found")
    pytesseract.pytesseract.tesseract_cmd = _resolved_tesseract_cmd
    return pytesseract


def tesseract_available() -> bool:
    try:
        get_pytesseract()
        return True
    except Exception:
        return False


def reset_tesseract_cache() -> None:
    global _resolved_tesseract_cmd
    _resolved_tesseract_cmd = None


# ----------------------------------------------------------------- Preprocess

def candidate_masks(cell_bgr, upscale: int = 4, sharpen_amount: float = 1.4):
    """Several binarizations of the same crop.

    Game text is small, stylized and often gradient-filled, so no single
    threshold works everywhere. Cheaper to OCR three masks and keep the best
    result than to tune one mask per game.
    """
    if cell_bgr is None or cell_bgr.size == 0:
        return []
    img = cell_bgr
    if upscale and upscale > 1:
        img = cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    sharp = cv2.addWeighted(gray, 1 + sharpen_amount, blur, -sharpen_amount, 0)
    denoised = cv2.bilateralFilter(sharp, 5, 50, 50)

    masks = []
    _t, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Correct polarity: OCR wants dark text on light ground.
    if int(np.mean(otsu)) < 127:
        otsu = cv2.bitwise_not(otsu)
    masks.append(otsu)

    _t2, bright = cv2.threshold(denoised, 185, 255, cv2.THRESH_BINARY)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    masks.append(cv2.bitwise_not(bright))

    masks.append(cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 25, 10))
    return masks


def _score(text: str, pattern=None):
    """(regex matched, alphanumeric count) -- a full pattern match outranks
    any amount of raw characters."""
    clean = (text or "").strip()
    matched = 1 if (pattern and re.fullmatch(pattern, clean)) else 0
    return matched, sum(1 for c in clean if c.isalnum())


def read_text(frame_bgr, whitelist: str = "", psm_modes=(7, 6),
              pattern=None, upscale: int = 4) -> str:
    """Best-effort text from a crop, sweeping masks and page-seg modes."""
    if frame_bgr is None or frame_bgr.size == 0:
        return ""

    masks = candidate_masks(frame_bgr, upscale=upscale)
    if not masks:
        return ""

    if windows_ocr_available():
        best, best_score = "", (0, 0)
        for mask in masks:
            text = _windows_ocr(mask)
            if whitelist:
                text = "".join(c for c in text if c in whitelist)
            score = _score(text, pattern)
            if score > best_score:
                best, best_score = text.strip(), score
            if score[0]:
                return best
        return best

    try:
        pyt = get_pytesseract()
    except RuntimeError:
        return ""
    config = "--oem 3"
    if whitelist:
        config += ' -c tessedit_char_whitelist=%s' % whitelist
    best, best_score = "", (0, 0)
    for mask in masks:
        for psm in psm_modes:
            try:
                text = pyt.image_to_string(mask, config="%s --psm %d" % (config, psm))
            except Exception:
                continue
            score = _score(text, pattern)
            if score > best_score:
                best, best_score = text.strip(), score
            if score[0]:
                return best
    return best


def text_contains(frame_bgr, needle: str, case_sensitive: bool = False) -> bool:
    text = read_text(frame_bgr)
    if not case_sensitive:
        return needle.lower() in text.lower()
    return needle in text


# ------------------------------------------------------------ locating text

def _similarity(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def _windows_ocr_lines(img):
    """[(text, x, y, w, h)] per recognised line, in `img` pixel coordinates."""
    if not windows_ocr_available():
        return []
    try:
        from winsdk.windows.graphics.imaging import (
            SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode)
        from winsdk.windows.security.cryptography import CryptographicBuffer

        if img.ndim == 2:
            bgra = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        else:
            bgra = img
        h, w = bgra.shape[:2]
        buf = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
        with _win_lock:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(_await_ocr(bitmap))
            finally:
                loop.close()
        if not result:
            return []
        out = []
        for line in result.lines:
            rects = [word.bounding_rect for word in line.words]
            if not rects:
                continue
            left = min(r.x for r in rects)
            top = min(r.y for r in rects)
            right = max(r.x + r.width for r in rects)
            bottom = max(r.y + r.height for r in rects)
            out.append((line.text, int(left), int(top),
                        int(right - left), int(bottom - top)))
        return out
    except Exception:
        _note_windows_failure()
        return []


def _tesseract_lines(img):
    try:
        pyt = get_pytesseract()
    except RuntimeError:
        return []
    try:
        data = pyt.image_to_data(img, output_type=pyt.Output.DICT)
    except Exception:
        return []
    grouped = {}
    for i in range(len(data.get("text", []))):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        box = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
        entry = grouped.setdefault(key, {"words": [], "boxes": []})
        entry["words"].append(word)
        entry["boxes"].append(box)
    out = []
    for entry in grouped.values():
        boxes = entry["boxes"]
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[0] + b[2] for b in boxes)
        bottom = max(b[1] + b[3] for b in boxes)
        out.append((" ".join(entry["words"]), left, top, right - left, bottom - top))
    return out


def find_text(frame_bgr, needle: str, confidence: float = 0.7,
              case_sensitive: bool = False, upscale: int = 2):
    """Locate `needle` on screen and return where it is.

    Returns {"text", "x", "y", "w", "h", "cx", "cy", "score"} in `frame_bgr`
    pixel coordinates, or None.

    `confidence` governs the FUZZY path only. A literal substring hit is
    accepted regardless: if the recognised line really does contain the
    wanted text, no threshold should be able to argue with that. The fuzzy
    fallback exists because OCR routinely returns "Cоntinue" with a Cyrillic
    С or drops a letter, and an exact-only search would report text that is
    plainly on screen as absent.

    `case_sensitive` applies to the substring test. Fuzzy matching is
    inherently case-tolerant -- one differing capital barely moves the
    similarity ratio -- so it is not a strict filter.
    """
    if frame_bgr is None or frame_bgr.size == 0 or not needle:
        return None

    # Upscaled before recognition: small UI text is the case that fails, and
    # the boxes are scaled back down afterwards.
    img = frame_bgr
    scale = max(1, int(upscale))
    if scale > 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

    lines = _windows_ocr_lines(img) or _tesseract_lines(img)
    if not lines:
        return None

    wanted = needle if case_sensitive else needle.lower()
    best = None
    for text, x, y, w, h in lines:
        hay = text if case_sensitive else text.lower()
        if wanted in hay:
            score = 1.0
        else:
            score = _similarity(wanted, hay)
            if score < float(confidence):
                continue
        if best is None or score > best["score"]:
            best = {"text": text, "score": float(score),
                    "x": int(x / scale), "y": int(y / scale),
                    "w": max(1, int(w / scale)), "h": max(1, int(h / scale))}
        if score >= 1.0:
            break

    if best is None:
        return None
    best["cx"] = best["x"] + best["w"] // 2
    best["cy"] = best["y"] + best["h"] // 2
    return best


def engine_name() -> str:
    if windows_ocr_available():
        return "Windows OCR"
    if tesseract_available():
        return "Tesseract"
    return "none"
