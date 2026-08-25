"""Condition catalog and evaluator.

Conditions are used by if_else, while_loop and repeat_until blocks.
Each condition type has a COND_TYPES entry (for the UI palette) and an
_evaluate_* function (for the runner).

Condition dict shape:
    {"type": "text_contains", "params": {"text": "ok", "region": None, ...}}

The runner calls evaluate(cond, ctx) where ctx is a _ConditionContext.
"""
from __future__ import annotations
import copy
import math
import re
import time

# ------------------------------------------------------------------ context

class _ConditionContext:
    """Everything a condition evaluator may need from the runner."""
    def __init__(self, runner):
        self._r = runner
        # Per-runner state storage for stateful conditions (changed, stable…)
        if not hasattr(runner, '_cond_state'):
            runner._cond_state = {}

    def target(self):
        return self._r._target()

    def region(self, params):
        return self._r._region(params)

    def num(self, params, key, default):
        return self._r._num(params, key, default)

    def loop_index(self):
        return getattr(self._r, '_loop_index', 0)

    def log(self, msg):
        self._r._log(msg)

    def state(self, key):
        return self._r._cond_state.get(key)

    def set_state(self, key, val):
        self._r._cond_state[key] = val


# ------------------------------------------------------------------ helpers

def _as_number(text: str):
    """Extract first number from text. Returns float or None."""
    if not text:
        return None
    m = re.search(r'[-+]?\d+\.?\d*', text.replace(',', '.'))
    return float(m.group()) if m else None


def _dist(ax, ay, bx, by) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _hex_to_rgb(hex_str):
    h = (hex_str or '#ffffff').lstrip('#')
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 255, 255, 255


def _ocr_region(ctx, params):
    from . import capture, ocr
    region = ctx.region(params)
    frame = capture.capture_target_bgr(ctx.target(), region)
    if frame is None:
        return ''
    return ocr.read_text(frame).strip()


# ============================================================ TEXT conditions

def _eval_text_contains(params, ctx):
    needle = str(params.get('text') or '')
    text = _ocr_region(ctx, params)
    case = bool(params.get('case_sensitive'))
    if not case:
        return needle.lower() in text.lower()
    return needle in text


def _eval_text_not_contains(params, ctx):
    return not _eval_text_contains(params, ctx)


def _eval_text_equals(params, ctx):
    needle = str(params.get('text') or '')
    text = _ocr_region(ctx, params)
    case = bool(params.get('case_sensitive'))
    if not case:
        return text.lower() == needle.lower()
    return text == needle


def _eval_text_starts_with(params, ctx):
    needle = str(params.get('text') or '')
    text = _ocr_region(ctx, params)
    return text.lower().startswith(needle.lower())


def _eval_text_ends_with(params, ctx):
    needle = str(params.get('text') or '')
    text = _ocr_region(ctx, params)
    return text.lower().endswith(needle.lower())


def _eval_text_is_empty(params, ctx):
    return _ocr_region(ctx, params) == ''


def _eval_text_is_not_empty(params, ctx):
    return _ocr_region(ctx, params) != ''


def _eval_text_length(params, ctx):
    text = _ocr_region(ctx, params)
    op = str(params.get('operator') or 'equals')
    n = int(ctx.num(params, 'value', 0))
    length = len(text)
    if op == 'equals': return length == n
    if op == 'not equals': return length != n
    if op == 'greater': return length > n
    if op == 'greater or equal': return length >= n
    if op == 'less': return length < n
    if op == 'less or equal': return length <= n
    return False


def _eval_text_word_count(params, ctx):
    text = _ocr_region(ctx, params)
    op = str(params.get('operator') or 'equals')
    n = int(ctx.num(params, 'value', 0))
    count = len(text.split()) if text else 0
    if op == 'equals': return count == n
    if op == 'not equals': return count != n
    if op == 'greater': return count > n
    if op == 'greater or equal': return count >= n
    if op == 'less': return count < n
    if op == 'less or equal': return count <= n
    return False


def _eval_text_is_number(params, ctx):
    text = _ocr_region(ctx, params)
    return _as_number(text) is not None


def _eval_text_matches_regex(params, ctx):
    pattern = str(params.get('pattern') or '')
    text = _ocr_region(ctx, params)
    if not pattern:
        return False
    try:
        return bool(re.search(pattern, text))
    except re.error:
        return False


def _eval_text_is_date(params, ctx):
    text = _ocr_region(ctx, params)
    return bool(re.search(r'\d{1,4}[./-]\d{1,2}[./-]\d{1,4}', text))


def _eval_text_is_time(params, ctx):
    text = _ocr_region(ctx, params)
    return bool(re.search(r'\d{1,2}:\d{2}', text))


def _eval_text_all_caps(params, ctx):
    text = _ocr_region(ctx, params)
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _eval_text_contains_any_of(params, ctx):
    words_str = str(params.get('words') or '')
    words = [w.strip() for w in words_str.split(',') if w.strip()]
    text = _ocr_region(ctx, params).lower()
    return any(w.lower() in text for w in words)


def _eval_text_contains_all_of(params, ctx):
    words_str = str(params.get('words') or '')
    words = [w.strip() for w in words_str.split(',') if w.strip()]
    text = _ocr_region(ctx, params).lower()
    return all(w.lower() in text for w in words)


def _eval_text_changed(params, ctx):
    """True once when text in region differs from last check."""
    key = 'text_changed_%s' % str(params.get('region'))
    text = _ocr_region(ctx, params)
    prev = ctx.state(key)
    ctx.set_state(key, text)
    return prev is not None and text != prev


def _eval_text_stable_for(params, ctx):
    """True when the text has not changed for N ms."""
    key_text = 'stable_text_%s' % str(params.get('region'))
    key_since = 'stable_since_%s' % str(params.get('region'))
    ms = int(ctx.num(params, 'ms', 1000))
    text = _ocr_region(ctx, params)
    prev = ctx.state(key_text)
    if prev != text:
        ctx.set_state(key_text, text)
        ctx.set_state(key_since, time.time())
        return False
    since = ctx.state(key_since) or time.time()
    return (time.time() - since) * 1000 >= ms


# ====================================================== NUMBER conditions

def _eval_number_compare(params, ctx):
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    if n is None:
        return False
    op = str(params.get('operator') or 'equals')
    val = float(ctx.num(params, 'value', 0))
    if op == 'equals': return n == val
    if op == 'not equals': return n != val
    if op == 'greater': return n > val
    if op == 'greater or equal': return n >= val
    if op == 'less': return n < val
    if op == 'less or equal': return n <= val
    return False


def _eval_number_in_range(params, ctx):
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    if n is None:
        return False
    lo = float(ctx.num(params, 'min', 0))
    hi = float(ctx.num(params, 'max', 100))
    return lo <= n <= hi


def _eval_number_changed(params, ctx):
    key = 'num_changed_%s' % str(params.get('region'))
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    prev = ctx.state(key)
    ctx.set_state(key, n)
    return prev is not None and n is not None and n != prev


def _eval_number_increased(params, ctx):
    key = 'num_val_%s' % str(params.get('region'))
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    prev = ctx.state(key)
    ctx.set_state(key, n)
    return prev is not None and n is not None and n > prev


def _eval_number_decreased(params, ctx):
    key = 'num_val_%s' % str(params.get('region'))
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    prev = ctx.state(key)
    ctx.set_state(key, n)
    return prev is not None and n is not None and n < prev


def _eval_number_delta(params, ctx):
    """True when number changed by at least `delta` in either direction."""
    key = 'num_delta_%s' % str(params.get('region'))
    text = _ocr_region(ctx, params)
    n = _as_number(text)
    prev = ctx.state(key)
    ctx.set_state(key, n)
    if prev is None or n is None:
        return False
    delta = float(ctx.num(params, 'delta', 1))
    return abs(n - prev) >= delta


def _eval_ratio_compare(params, ctx):
    """Compare number from region1 vs region2."""
    from . import capture, ocr
    def read(region_key):
        region = params.get(region_key)
        r = None
        if region:
            try:
                x, y, w, h = [int(v) for v in region]
                r = (x, y, w, h) if w > 0 and h > 0 else None
            except Exception:
                pass
        frame = capture.capture_target_bgr(ctx.target(), r)
        return _as_number(ocr.read_text(frame).strip() if frame is not None else '')
    a = read('region')
    b = read('region2')
    if a is None or b is None or b == 0:
        return False
    op = str(params.get('operator') or 'greater')
    if op == 'equals': return a == b
    if op == 'not equals': return a != b
    if op == 'greater': return a > b
    if op == 'greater or equal': return a >= b
    if op == 'less': return a < b
    if op == 'less or equal': return a <= b
    return False


def _eval_text_same_in_regions(params, ctx):
    from . import capture, ocr
    def read(region_key):
        region = params.get(region_key)
        r = None
        if region:
            try:
                x, y, w, h = [int(v) for v in region]
                r = (x, y, w, h) if w > 0 and h > 0 else None
            except Exception:
                pass
        frame = capture.capture_target_bgr(ctx.target(), r)
        return ocr.read_text(frame).strip() if frame is not None else ''
    return read('region') == read('region2')


def _eval_text_different_in_regions(params, ctx):
    return not _eval_text_same_in_regions(params, ctx)


def _eval_text_count(params, ctx):
    """Count how many times needle appears anywhere on screen."""
    from . import capture, ocr
    needle = str(params.get('text') or '')
    frame = capture.capture_target_bgr(ctx.target(), None)
    if frame is None or not needle:
        return False
    text = ocr.read_text(frame).lower()
    count = text.lower().count(needle.lower())
    op = str(params.get('operator') or 'greater')
    val = int(ctx.num(params, 'value', 1))
    if op == 'equals': return count == val
    if op == 'not equals': return count != val
    if op == 'greater': return count > val
    if op == 'greater or equal': return count >= val
    if op == 'less': return count < val
    if op == 'less or equal': return count <= val
    return False


def _eval_text_present_anywhere(params, ctx):
    from . import capture, ocr
    needle = str(params.get('text') or '')
    frame = capture.capture_target_bgr(ctx.target(), None)
    if frame is None or not needle:
        return False
    text = ocr.read_text(frame)
    return needle.lower() in text.lower()


def _eval_text_near_image(params, ctx):
    """True if text is found within `max_dist` px of a template match."""
    from . import capture, ocr, vision
    template = str(params.get('template') or '')
    needle = str(params.get('text') or '')
    max_dist = float(ctx.num(params, 'max_dist', 150))
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    img_match = vision.find_image(ctx.target(), template, threshold=threshold)
    if not img_match:
        return False
    frame = capture.capture_target_bgr(ctx.target(), None)
    if frame is None:
        return False
    txt_hit = ocr.find_text(frame, needle, 0.7)
    if not txt_hit:
        return False
    return _dist(img_match['cx'], img_match['cy'],
                 txt_hit['cx'], txt_hit['cy']) <= max_dist


# ====================================================== VISION conditions

def _eval_image_present(params, ctx):
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    region = ctx.region(params)
    return vision.find_image(ctx.target(), template, region, threshold) is not None


def _eval_image_absent(params, ctx):
    return not _eval_image_present(params, ctx)


def _eval_image_count(params, ctx):
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    region = ctx.region(params)
    matches = vision.find_all_images(ctx.target(), template, region, threshold)
    count = len(matches)
    op = str(params.get('operator') or 'greater')
    val = int(ctx.num(params, 'value', 1))
    if op == 'equals': return count == val
    if op == 'not equals': return count != val
    if op == 'greater': return count > val
    if op == 'greater or equal': return count >= val
    if op == 'less': return count < val
    if op == 'less or equal': return count <= val
    return False


def _eval_pixel_brightness(params, ctx):
    import numpy as np
    from . import capture
    x = int(ctx.num(params, 'x', 0))
    y = int(ctx.num(params, 'y', 0))
    frame = capture.capture_target_bgr(ctx.target(), (x, y, 1, 1))
    if frame is None or frame.size == 0:
        return False
    b, g, r = int(frame[0, 0, 0]), int(frame[0, 0, 1]), int(frame[0, 0, 2])
    brightness = (r * 299 + g * 587 + b * 114) // 1000
    op = str(params.get('operator') or 'greater')
    val = int(ctx.num(params, 'value', 128))
    if op == 'greater': return brightness > val
    if op == 'greater or equal': return brightness >= val
    if op == 'less': return brightness < val
    if op == 'less or equal': return brightness <= val
    if op == 'equals': return brightness == val
    return False


def _eval_images_same(params, ctx):
    """Compare two screen regions for similarity."""
    import cv2
    import numpy as np
    from . import capture
    def grab(key):
        region = params.get(key)
        if not region:
            return None
        try:
            x, y, w, h = [int(v) for v in region]
        except Exception:
            return None
        return capture.capture_target_bgr(ctx.target(), (x, y, w, h))
    a = grab('region')
    b = grab('region2')
    if a is None or b is None:
        return False
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    diff = cv2.absdiff(a, b)
    similarity = 1.0 - float(np.mean(diff)) / 255.0
    threshold = float(ctx.num(params, 'threshold', 0.92))
    return similarity >= threshold


def _eval_color_changed(params, ctx):
    """True when color at (x,y) changed since last check."""
    x = int(ctx.num(params, 'x', 0))
    y = int(ctx.num(params, 'y', 0))
    key = 'color_at_%d_%d' % (x, y)
    from . import vision
    rgb = vision.sample_color(ctx.target(), x, y)
    prev = ctx.state(key)
    ctx.set_state(key, rgb)
    if prev is None or rgb is None:
        return False
    return rgb != prev


def _eval_screen_frozen(params, ctx):
    """True when screen has not changed for `ms` milliseconds."""
    import cv2
    import numpy as np
    from . import capture
    ms = int(ctx.num(params, 'ms', 2000))
    key_frame = 'frozen_frame'
    key_since = 'frozen_since'
    region = ctx.region(params)
    frame = capture.capture_target_bgr(ctx.target(), region)
    if frame is None:
        return False
    small = cv2.resize(frame, (64, 36))
    prev = ctx.state(key_frame)
    if prev is None:
        ctx.set_state(key_frame, small)
        ctx.set_state(key_since, time.time())
        return False
    diff = float(np.mean(cv2.absdiff(small, prev)))
    if diff > 2.0:
        ctx.set_state(key_frame, small)
        ctx.set_state(key_since, time.time())
        return False
    since = ctx.state(key_since) or time.time()
    return (time.time() - since) * 1000 >= ms


# ====================================================== DISTANCE conditions

def _eval_distance_from_point(params, ctx):
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    region = ctx.region(params)
    px = float(ctx.num(params, 'px', 0))
    py = float(ctx.num(params, 'py', 0))
    op = str(params.get('operator') or 'less')
    val = float(ctx.num(params, 'value', 200))
    match = vision.find_image(ctx.target(), template, region, threshold)
    if not match:
        return False
    d = _dist(match['cx'], match['cy'], px, py)
    if op == 'less': return d < val
    if op == 'less or equal': return d <= val
    if op == 'greater': return d > val
    if op == 'greater or equal': return d >= val
    return False


def _eval_distance_between_images(params, ctx):
    from . import vision
    t1 = str(params.get('template') or '')
    t2 = str(params.get('template2') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    op = str(params.get('operator') or 'less')
    val = float(ctx.num(params, 'value', 200))
    m1 = vision.find_image(ctx.target(), t1, threshold=threshold)
    m2 = vision.find_image(ctx.target(), t2, threshold=threshold)
    if not m1 or not m2:
        return False
    d = _dist(m1['cx'], m1['cy'], m2['cx'], m2['cy'])
    if op == 'less': return d < val
    if op == 'less or equal': return d <= val
    if op == 'greater': return d > val
    if op == 'greater or equal': return d >= val
    return False


def _eval_image_in_ring(params, ctx):
    """True if image is between min_dist and max_dist from a point."""
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    px = float(ctx.num(params, 'px', 0))
    py = float(ctx.num(params, 'py', 0))
    min_d = float(ctx.num(params, 'min_dist', 0))
    max_d = float(ctx.num(params, 'max_dist', 300))
    match = vision.find_image(ctx.target(), template, threshold=threshold)
    if not match:
        return False
    d = _dist(match['cx'], match['cy'], px, py)
    return min_d <= d <= max_d


def _eval_images_clustered(params, ctx):
    """True when all matches are within `max_dist` of each other's centroid."""
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    max_d = float(ctx.num(params, 'max_dist', 100))
    matches = vision.find_all_images(ctx.target(), template, threshold=threshold)
    if len(matches) < 2:
        return False
    cx = sum(m['cx'] for m in matches) / len(matches)
    cy = sum(m['cy'] for m in matches) / len(matches)
    return all(_dist(m['cx'], m['cy'], cx, cy) <= max_d for m in matches)


def _eval_image_moving_toward(params, ctx):
    """True when an image is getting closer to a point between frames."""
    from . import vision
    template = str(params.get('template') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    px = float(ctx.num(params, 'px', 0))
    py = float(ctx.num(params, 'py', 0))
    key = 'move_toward_%s' % template
    match = vision.find_image(ctx.target(), template, threshold=threshold)
    prev_d = ctx.state(key)
    if not match:
        return False
    d = _dist(match['cx'], match['cy'], px, py)
    ctx.set_state(key, d)
    return prev_d is not None and d < prev_d


def _eval_images_overlap(params, ctx):
    from . import vision
    t1 = str(params.get('template') or '')
    t2 = str(params.get('template2') or '')
    threshold = float(ctx.num(params, 'threshold', vision.DEFAULT_THRESHOLD))
    m1 = vision.find_image(ctx.target(), t1, threshold=threshold)
    m2 = vision.find_image(ctx.target(), t2, threshold=threshold)
    if not m1 or not m2:
        return False
    # bounding box overlap
    l1, r1 = m1['x'], m1['x'] + m1['w']
    t1b, b1 = m1['y'], m1['y'] + m1['h']
    l2, r2 = m2['x'], m2['x'] + m2['w']
    t2b, b2 = m2['y'], m2['y'] + m2['h']
    return l1 < r2 and r1 > l2 and t1b < b2 and b1 > t2b


# ====================================================== SYSTEM conditions

def _eval_process_running(params, ctx):
    name_pat = str(params.get('name') or '').lower()
    if not name_pat:
        return False
    try:
        import psutil
        return any(name_pat in (p.info.get('name') or '').lower()
                   for p in psutil.process_iter(['name']))
    except ImportError:
        import subprocess
        result = subprocess.run(['tasklist'], capture_output=True, text=True,
                                creationflags=0x08000000)
        return name_pat in result.stdout.lower()


def _eval_window_exists(params, ctx):
    title = str(params.get('title') or '').lower()
    if not title:
        return False
    try:
        from . import window as wm
        windows = wm.list_windows() if hasattr(wm, 'list_windows') else []
        return any(title in str(w).lower() for w in windows)
    except Exception:
        return False


def _eval_file_exists(params, ctx):
    import os
    path = str(params.get('path') or '')
    return os.path.exists(path) if path else False


# ====================================================== MACRO STATE conditions

def _eval_loop_iteration(params, ctx):
    op = str(params.get('operator') or 'equals')
    val = int(ctx.num(params, 'value', 1))
    i = ctx.loop_index()
    if op == 'equals': return i == val
    if op == 'not equals': return i != val
    if op == 'greater': return i > val
    if op == 'greater or equal': return i >= val
    if op == 'less': return i < val
    if op == 'less or equal': return i <= val
    return False


def _eval_random_chance(params, ctx):
    import random
    pct = float(ctx.num(params, 'percent', 50))
    return random.random() * 100 < pct


# ====================================================== COMBINATORS

def _eval_not(params, ctx):
    inner = params.get('condition')
    if not inner:
        return True
    return not evaluate(inner, ctx)


def _eval_and(params, ctx):
    conditions = params.get('conditions') or []
    return all(evaluate(c, ctx) for c in conditions)


def _eval_or(params, ctx):
    conditions = params.get('conditions') or []
    return any(evaluate(c, ctx) for c in conditions)


def _eval_xor(params, ctx):
    conditions = params.get('conditions') or []
    return sum(1 for c in conditions if evaluate(c, ctx)) % 2 == 1


def _eval_n_of(params, ctx):
    conditions = params.get('conditions') or []
    n = int(params.get('n') or 1)
    return sum(1 for c in conditions if evaluate(c, ctx)) >= n


# ================================================================ dispatch

_EVALUATORS = {
    # text
    'text_contains':          _eval_text_contains,
    'text_not_contains':      _eval_text_not_contains,
    'text_equals':            _eval_text_equals,
    'text_starts_with':       _eval_text_starts_with,
    'text_ends_with':         _eval_text_ends_with,
    'text_is_empty':          _eval_text_is_empty,
    'text_is_not_empty':      _eval_text_is_not_empty,
    'text_length':            _eval_text_length,
    'text_word_count':        _eval_text_word_count,
    'text_is_number':         _eval_text_is_number,
    'text_matches_regex':     _eval_text_matches_regex,
    'text_is_date':           _eval_text_is_date,
    'text_is_time':           _eval_text_is_time,
    'text_all_caps':          _eval_text_all_caps,
    'text_contains_any_of':   _eval_text_contains_any_of,
    'text_contains_all_of':   _eval_text_contains_all_of,
    'text_changed':           _eval_text_changed,
    'text_stable_for':        _eval_text_stable_for,
    'text_same_in_regions':   _eval_text_same_in_regions,
    'text_different_in_regions': _eval_text_different_in_regions,
    'text_count':             _eval_text_count,
    'text_present_anywhere':  _eval_text_present_anywhere,
    'text_near_image':        _eval_text_near_image,
    # numbers
    'number_compare':         _eval_number_compare,
    'number_in_range':        _eval_number_in_range,
    'number_changed':         _eval_number_changed,
    'number_increased':       _eval_number_increased,
    'number_decreased':       _eval_number_decreased,
    'number_delta':           _eval_number_delta,
    'ratio_compare':          _eval_ratio_compare,
    # vision
    'image_present':          _eval_image_present,
    'image_absent':           _eval_image_absent,
    'image_count':            _eval_image_count,
    'pixel_brightness':       _eval_pixel_brightness,
    'images_same':            _eval_images_same,
    'color_changed':          _eval_color_changed,
    'screen_frozen':          _eval_screen_frozen,
    # distance
    'distance_from_point':    _eval_distance_from_point,
    'distance_between_images':_eval_distance_between_images,
    'image_in_ring':          _eval_image_in_ring,
    'images_clustered':       _eval_images_clustered,
    'image_moving_toward':    _eval_image_moving_toward,
    'images_overlap':         _eval_images_overlap,
    # system
    'process_running':        _eval_process_running,
    'window_exists':          _eval_window_exists,
    'file_exists':            _eval_file_exists,
    # macro state
    'loop_iteration':         _eval_loop_iteration,
    'random_chance':          _eval_random_chance,
    # combinators
    'not':                    _eval_not,
    'and':                    _eval_and,
    'or':                     _eval_or,
    'xor':                    _eval_xor,
    'n_of':                   _eval_n_of,
}


def evaluate(cond: dict, ctx) -> bool:
    """Evaluate a condition dict. Returns bool. Never raises."""
    if not cond or not isinstance(cond, dict):
        return False
    ctype = cond.get('type', '')
    invert = bool(cond.get('invert'))
    fn = _EVALUATORS.get(ctype)
    if fn is None:
        return False
    try:
        result = bool(fn(cond.get('params') or {}, ctx))
    except Exception as exc:
        return False
    return (not result) if invert else result


# ================================================================ COND_TYPES
# Each entry: {"type", "group", "label", "fields": [...]}
# Reuses same field kinds as blocks.py.

_OP_COMPARE = ['equals', 'not equals', 'greater', 'greater or equal', 'less', 'less or equal']
_OP_DIST    = ['less', 'less or equal', 'greater', 'greater or equal']

COND_TYPES = [
    # ---- Text ----
    {'type': 'text_contains', 'group': 'Текст',
     'label': 'Текст содержит',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'case_sensitive', 'kind': 'bool', 'default': False}]},
    {'type': 'text_not_contains', 'group': 'Текст',
     'label': 'Текст не содержит',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_equals', 'group': 'Текст',
     'label': 'Текст равен',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'case_sensitive', 'kind': 'bool', 'default': False}]},
    {'type': 'text_starts_with', 'group': 'Текст',
     'label': 'Текст начинается с',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_ends_with', 'group': 'Текст',
     'label': 'Текст заканчивается на',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_is_empty', 'group': 'Текст',
     'label': 'Текст пустой',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_is_not_empty', 'group': 'Текст',
     'label': 'Текст не пустой',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_length', 'group': 'Текст',
     'label': 'Длина текста',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'operator', 'kind': 'choice', 'default': 'equals', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'int', 'default': 5}]},
    {'type': 'text_word_count', 'group': 'Текст',
     'label': 'Количество слов',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'int', 'default': 1}]},
    {'type': 'text_is_number', 'group': 'Текст',
     'label': 'Текст — число',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_matches_regex', 'group': 'Текст',
     'label': 'Текст по regex',
     'fields': [{'key': 'pattern', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_is_date', 'group': 'Текст',
     'label': 'Текст — дата',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_is_time', 'group': 'Текст',
     'label': 'Текст — время',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_all_caps', 'group': 'Текст',
     'label': 'Текст в верхнем регистре',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_contains_any_of', 'group': 'Текст',
     'label': 'Текст содержит хотя бы одно из',
     'fields': [{'key': 'words', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_contains_all_of', 'group': 'Текст',
     'label': 'Текст содержит всё из',
     'fields': [{'key': 'words', 'kind': 'text', 'default': ''},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_changed', 'group': 'Текст',
     'label': 'Текст изменился',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'text_stable_for', 'group': 'Текст',
     'label': 'Текст не меняется N мс',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'ms', 'kind': 'int', 'default': 1000}]},
    {'type': 'text_same_in_regions', 'group': 'Текст',
     'label': 'Одинаковый текст в 2 областях',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'region2', 'kind': 'region', 'default': None}]},
    {'type': 'text_different_in_regions', 'group': 'Текст',
     'label': 'Разный текст в 2 областях',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'region2', 'kind': 'region', 'default': None}]},
    {'type': 'text_count', 'group': 'Текст',
     'label': 'Текст встречается N раз',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater or equal', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'int', 'default': 1}]},
    {'type': 'text_present_anywhere', 'group': 'Текст',
     'label': 'Текст есть на экране',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''}]},
    {'type': 'text_near_image', 'group': 'Текст',
     'label': 'Текст рядом с картинкой',
     'fields': [{'key': 'text', 'kind': 'text', 'default': ''},
                {'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'max_dist', 'kind': 'int', 'default': 150},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88}]},
    # ---- Numbers ----
    {'type': 'number_compare', 'group': 'Числа',
     'label': 'Сравнить число',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'float', 'default': 0}]},
    {'type': 'number_in_range', 'group': 'Числа',
     'label': 'Число в диапазоне',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'min', 'kind': 'float', 'default': 0},
                {'key': 'max', 'kind': 'float', 'default': 100}]},
    {'type': 'number_changed', 'group': 'Числа',
     'label': 'Число изменилось',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'number_increased', 'group': 'Числа',
     'label': 'Число увеличилось',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'number_decreased', 'group': 'Числа',
     'label': 'Число уменьшилось',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'number_delta', 'group': 'Числа',
     'label': 'Изменение на дельту',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'delta', 'kind': 'float', 'default': 10}]},
    {'type': 'ratio_compare', 'group': 'Числа',
     'label': 'Сравнить числа из 2 областей',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'region2', 'kind': 'region', 'default': None},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater', 'options': _OP_COMPARE}]},
    # ---- Vision ----
    {'type': 'image_present', 'group': 'Изображение',
     'label': 'Картинка найдена',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'image_absent', 'group': 'Изображение',
     'label': 'Картинка не найдена',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    {'type': 'image_count', 'group': 'Изображение',
     'label': 'Кол-во картинок',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater or equal', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'int', 'default': 1}]},
    {'type': 'pixel_brightness', 'group': 'Изображение',
     'label': 'Яркость пикселя',
     'fields': [{'key': 'x', 'kind': 'int', 'default': 0},
                {'key': 'y', 'kind': 'int', 'default': 0},
                {'key': 'operator', 'kind': 'choice', 'default': 'greater', 'options': _OP_DIST},
                {'key': 'value', 'kind': 'int', 'default': 128}]},
    {'type': 'images_same', 'group': 'Изображение',
     'label': 'Области одинаковы',
     'fields': [{'key': 'region', 'kind': 'region', 'default': None},
                {'key': 'region2', 'kind': 'region', 'default': None},
                {'key': 'threshold', 'kind': 'float', 'default': 0.92}]},
    {'type': 'color_changed', 'group': 'Изображение',
     'label': 'Цвет изменился в точке',
     'fields': [{'key': 'x', 'kind': 'int', 'default': 0},
                {'key': 'y', 'kind': 'int', 'default': 0}]},
    {'type': 'screen_frozen', 'group': 'Изображение',
     'label': 'Экран завис',
     'fields': [{'key': 'ms', 'kind': 'int', 'default': 2000},
                {'key': 'region', 'kind': 'region', 'default': None}]},
    # ---- Distance ----
    {'type': 'distance_from_point', 'group': 'Расстояние',
     'label': 'Расстояние до точки',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'px', 'kind': 'int', 'default': 960},
                {'key': 'py', 'kind': 'int', 'default': 540},
                {'key': 'operator', 'kind': 'choice', 'default': 'less', 'options': _OP_DIST},
                {'key': 'value', 'kind': 'float', 'default': 200}]},
    {'type': 'distance_between_images', 'group': 'Расстояние',
     'label': 'Расстояние между картинками',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'template2', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'operator', 'kind': 'choice', 'default': 'less', 'options': _OP_DIST},
                {'key': 'value', 'kind': 'float', 'default': 200}]},
    {'type': 'image_in_ring', 'group': 'Расстояние',
     'label': 'Картинка в кольцевой зоне',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'px', 'kind': 'int', 'default': 960},
                {'key': 'py', 'kind': 'int', 'default': 540},
                {'key': 'min_dist', 'kind': 'float', 'default': 50},
                {'key': 'max_dist', 'kind': 'float', 'default': 300}]},
    {'type': 'images_clustered', 'group': 'Расстояние',
     'label': 'Картинки сгруппированы',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'max_dist', 'kind': 'float', 'default': 100}]},
    {'type': 'image_moving_toward', 'group': 'Расстояние',
     'label': 'Картинка движется к точке',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88},
                {'key': 'px', 'kind': 'int', 'default': 960},
                {'key': 'py', 'kind': 'int', 'default': 540}]},
    {'type': 'images_overlap', 'group': 'Расстояние',
     'label': 'Картинки перекрываются',
     'fields': [{'key': 'template', 'kind': 'template', 'default': ''},
                {'key': 'template2', 'kind': 'template', 'default': ''},
                {'key': 'threshold', 'kind': 'float', 'default': 0.88}]},
    # ---- System ----
    {'type': 'process_running', 'group': 'Система',
     'label': 'Процесс запущен',
     'fields': [{'key': 'name', 'kind': 'text', 'default': ''}]},
    {'type': 'window_exists', 'group': 'Система',
     'label': 'Окно открыто',
     'fields': [{'key': 'title', 'kind': 'text', 'default': ''}]},
    {'type': 'file_exists', 'group': 'Система',
     'label': 'Файл существует',
     'fields': [{'key': 'path', 'kind': 'text', 'default': ''}]},
    # ---- Macro state ----
    {'type': 'loop_iteration', 'group': 'Макрос',
     'label': 'Итерация цикла',
     'fields': [{'key': 'operator', 'kind': 'choice', 'default': 'equals', 'options': _OP_COMPARE},
                {'key': 'value', 'kind': 'int', 'default': 1}]},
    {'type': 'random_chance', 'group': 'Макрос',
     'label': 'Случайный шанс %',
     'fields': [{'key': 'percent', 'kind': 'float', 'default': 50}]},
    # ---- Combinators ----
    {'type': 'not', 'group': 'Логика',
     'label': 'НЕ (инверсия)',
     'fields': [{'key': 'condition', 'kind': 'condition', 'default': None}]},
    {'type': 'and', 'group': 'Логика',
     'label': 'И (все выполнены)',
     'fields': [{'key': 'conditions', 'kind': 'conditions', 'default': []}]},
    {'type': 'or', 'group': 'Логика',
     'label': 'ИЛИ (хотя бы одно)',
     'fields': [{'key': 'conditions', 'kind': 'conditions', 'default': []}]},
    {'type': 'xor', 'group': 'Логика',
     'label': 'XOR (ровно одно)',
     'fields': [{'key': 'conditions', 'kind': 'conditions', 'default': []}]},
    {'type': 'n_of', 'group': 'Логика',
     'label': 'N из (хотя бы N)',
     'fields': [{'key': 'n', 'kind': 'int', 'default': 2},
                {'key': 'conditions', 'kind': 'conditions', 'default': []}]},
]

BY_TYPE = {c['type']: c for c in COND_TYPES}


def default_params(cond_type: str) -> dict:
    import copy
    spec = BY_TYPE.get(cond_type)
    if not spec:
        return {}
    return {f['key']: copy.deepcopy(f.get('default')) for f in spec['fields']}


def catalog() -> list:
    return COND_TYPES
