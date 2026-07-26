"""Block catalog -- the single source of truth for what a block is.

The UI builds its palette and its per-row fields from BLOCK_TYPES, and the
runner dispatches on the same `type` strings, so adding a block means
editing this one table plus one handler in runner.py.

Field kinds the UI understands -- FIELD_KINDS below is the authoritative
list; a kind not in it has no renderer and would leave a blank row.
"""
import copy

PHASES = ("setup", "loop")
PHASE_LABELS = {"setup": "Setup", "loop": "Loop"}
# The phase that runs once, and the one that repeats. The runner reads these
# rather than hardcoding the strings, so the two cannot drift apart.
PHASE_ONCE = "setup"
PHASE_REPEAT = "loop"

FIELD_KINDS = ("int", "float", "text", "key", "bool", "choice", "modifiers",
               "region", "color", "template", "recording", "blocks")

# What a Vision block does when it does not find what it was looking for.
ON_FAIL_OPTIONS = ["continue", "run blocks", "restart phase", "skip rest", "stop"]
# What happens once a "run blocks" fallback has finished.
ON_FAIL_AFTER_OPTIONS = ["continue main", "restart phase", "restart macro", "stop"]

_ON_FAIL_TEMPLATE = [
    {"key": "on_fail", "kind": "choice", "label": "On fail", "default": "continue",
     "options": ON_FAIL_OPTIONS},
    # Both only meaningful for "run blocks"; the UI hides them otherwise.
    {"key": "on_fail_blocks", "kind": "blocks", "label": "Fallback", "default": []},
    {"key": "on_fail_after", "kind": "choice", "label": "Then", "default": "continue main",
     "options": ON_FAIL_AFTER_OPTIONS},
]


def _on_fail_fields():
    """FRESH dicts for each block.

    Splicing one shared list into every Vision block (`] + ON_FAIL_FIELDS`)
    concatenates into a new list but reuses the same dict objects, so all
    seven blocks ended up sharing one `on_fail` field. Since the help text is
    written INTO that dict per block, the last one processed won -- every
    image and colour block was showing "if the text is not found".
    """
    return copy.deepcopy(_ON_FAIL_TEMPLATE)

BLOCK_TYPES = [
    # ------------------------------------------------------------ mouse
    {"type": "click", "label": "Click", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "x", "kind": "int", "label": "X", "default": 0},
         {"key": "y", "kind": "int", "label": "Y", "default": 0},
         {"key": "button", "kind": "choice", "label": "Button", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "clicks", "kind": "int", "label": "Clicks", "default": 1},
         {"key": "hold_ms", "kind": "int", "label": "Hold ms", "default": 40},
     ]},
    {"type": "move", "label": "Move Mouse", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "x", "kind": "int", "label": "X", "default": 0},
         {"key": "y", "kind": "int", "label": "Y", "default": 0},
         {"key": "duration_ms", "kind": "int", "label": "Duration ms", "default": 0},
     ]},
    {"type": "drag", "label": "Drag", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "x", "kind": "int", "label": "From X", "default": 0},
         {"key": "y", "kind": "int", "label": "From Y", "default": 0},
         {"key": "x2", "kind": "int", "label": "To X", "default": 0},
         {"key": "y2", "kind": "int", "label": "To Y", "default": 0},
         {"key": "button", "kind": "choice", "label": "Button", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "duration_ms", "kind": "int", "label": "Duration ms", "default": 250},
     ]},
    {"type": "scroll", "label": "Scroll", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "amount", "kind": "int", "label": "Amount", "default": -120},
         {"key": "x", "kind": "int", "label": "X", "default": 0},
         {"key": "y", "kind": "int", "label": "Y", "default": 0},
     ]},

    # --------------------------------------------------------- keyboard
    {"type": "send_key", "label": "Send Key", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "key", "kind": "key", "label": "Key", "default": ""},
         {"key": "hold_ms", "kind": "int", "label": "Hold ms", "default": 30},
         {"key": "modifiers", "kind": "modifiers", "label": "Modifiers", "default": []},
     ]},
    {"type": "type_text", "label": "Type Text", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "text", "kind": "text", "label": "Text", "default": ""},
         {"key": "delay_ms", "kind": "int", "label": "Per-char ms", "default": 20},
     ]},
    {"type": "hold_key", "label": "Hold Key", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "key", "kind": "key", "label": "Key", "default": ""},
         {"key": "hold_ms", "kind": "int", "label": "Hold ms", "default": 1000},
     ]},

    # ----------------------------------------------------------- timing
    {"type": "wait_ms", "label": "Wait (ms)", "group": "Timing", "color": "amber",
     "fields": [{"key": "ms", "kind": "int", "label": "Milliseconds", "default": 500}]},
    {"type": "wait_random", "label": "Wait Random", "group": "Timing", "color": "amber",
     "fields": [
         {"key": "min_ms", "kind": "int", "label": "Min ms", "default": 200},
         {"key": "max_ms", "kind": "int", "label": "Max ms", "default": 800},
     ]},

    # ----------------------------------------------------------- vision
    {"type": "wait_image", "label": "Wait for Image", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "label": "Image", "default": ""},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "threshold", "kind": "float", "label": "Confidence", "default": 0.88},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
     ] + _on_fail_fields()},
    {"type": "click_image", "label": "Click Image", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "label": "Image", "default": ""},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "threshold", "kind": "float", "label": "Confidence", "default": 0.88},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
         {"key": "button", "kind": "choice", "label": "Button", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "label": "Offset X", "default": 0},
         {"key": "offset_y", "kind": "int", "label": "Offset Y", "default": 0},
     ] + _on_fail_fields()},
    {"type": "wait_image_gone", "label": "Wait Image Gone", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "label": "Image", "default": ""},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "threshold", "kind": "float", "label": "Confidence", "default": 0.88},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
     ] + _on_fail_fields()},
    {"type": "wait_color", "label": "Wait for Color", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "x", "kind": "int", "label": "X", "default": 0},
         {"key": "y", "kind": "int", "label": "Y", "default": 0},
         {"key": "color", "kind": "color", "label": "Color", "default": "#ffffff"},
         # Same 0-1 scale as the image and text blocks. The old 0-255
         # `tolerance` is still honoured when a saved macro carries it.
         {"key": "confidence", "kind": "float", "label": "Confidence", "default": 0.92},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
     ] + _on_fail_fields()},
    {"type": "click_color", "label": "Click Color", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "color", "kind": "color", "label": "Color", "default": "#ffffff"},
         {"key": "confidence", "kind": "float", "label": "Confidence", "default": 0.90},
         {"key": "min_pixels", "kind": "int", "label": "Min pixels", "default": 40},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "button", "kind": "choice", "label": "Button", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "label": "Offset X", "default": 0},
         {"key": "offset_y", "kind": "int", "label": "Offset Y", "default": 0},
     ] + _on_fail_fields()},
    {"type": "wait_text", "label": "Wait for Text", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "text", "kind": "text", "label": "Text", "default": ""},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "confidence", "kind": "float", "label": "Confidence", "default": 0.75},
         {"key": "match", "kind": "choice", "label": "Match", "default": "contains",
          "options": ["contains", "exact"]},
     ] + _on_fail_fields()},
    {"type": "click_text", "label": "Click Text", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "text", "kind": "text", "label": "Text", "default": ""},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
         {"key": "timeout_ms", "kind": "int", "label": "Timeout ms", "default": 8000},
         {"key": "confidence", "kind": "float", "label": "Confidence", "default": 0.75},
         {"key": "button", "kind": "choice", "label": "Button", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "label": "Offset X", "default": 0},
         {"key": "offset_y", "kind": "int", "label": "Offset Y", "default": 0},
     ] + _on_fail_fields()},
    {"type": "read_text", "label": "Read Text", "group": "Vision", "color": "teal",
     "fields": [{"key": "region", "kind": "region", "label": "Region", "default": None}]},

    # ------------------------------------------------------------ flow
    {"type": "loop_start", "label": "Loop Start", "group": "Flow", "color": "violet",
     "fields": [{"key": "count", "kind": "int", "label": "Times", "default": 2}]},
    {"type": "loop_end", "label": "Loop End", "group": "Flow", "color": "violet",
     "fields": []},
    {"type": "playback", "label": "Play Recording", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "recording", "kind": "recording", "label": "Recording", "default": ""},
         {"key": "speed", "kind": "float", "label": "Speed", "default": 1.0},
     ]},
    {"type": "focus_window", "label": "Focus Target", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "resize", "kind": "bool", "label": "Resize", "default": False},
         {"key": "width", "kind": "int", "label": "Width", "default": 1280},
         {"key": "height", "kind": "int", "label": "Height", "default": 720},
         {"key": "move", "kind": "bool", "label": "Move", "default": False},
         {"key": "x", "kind": "int", "label": "X", "default": 0},
         {"key": "y", "kind": "int", "label": "Y", "default": 0},
     ]},
    {"type": "log", "label": "Log Message", "group": "Flow", "color": "violet",
     "fields": [{"key": "text", "kind": "text", "label": "Message", "default": ""}]},

    # ------------------------------------------------------------- notify
    {"type": "send_webhook", "label": "Send Webhook", "group": "Notify", "color": "blue",
     "fields": [
         {"key": "message", "kind": "text", "label": "Message", "default": ""},
         {"key": "source", "kind": "choice", "label": "Attach", "default": "none",
          "options": ["none", "target window", "whole screen", "region", "saved image"]},
         {"key": "region", "kind": "region", "label": "Region", "default": None},
         {"key": "template", "kind": "template", "label": "Image", "default": ""},
     ]},
]

BY_TYPE = {b["type"]: b for b in BLOCK_TYPES}


def default_params(block_type: str) -> dict:
    spec = BY_TYPE.get(block_type)
    if not spec:
        return {}
    # Deep-copied, NOT handed out by reference: send_key's `modifiers`
    # default is a literal [] in the table above, so appending to one
    # block's modifiers would rewrite the catalog itself and every other
    # block that had ever taken the default.
    return {f["key"]: copy.deepcopy(f.get("default")) for f in spec["fields"]}


def make_block(block_type: str, block_id: str, params: dict = None) -> dict:
    merged = default_params(block_type)
    if params:
        merged.update(params)
    return {"id": block_id, "type": block_type, "enabled": True,
            "once": False, "params": merged}


def normalize(block: dict) -> dict:
    """Fill in anything a hand-edited or older-version block is missing, so
    the runner never has to guard every single lookup."""
    if not isinstance(block, dict):
        return None
    block_type = block.get("type")
    if block_type not in BY_TYPE:
        return None
    params = default_params(block_type)
    params.update(block.get("params") or {})
    return {
        "id": block.get("id") or block_type,
        "type": block_type,
        "enabled": bool(block.get("enabled", True)),
        "once": bool(block.get("once", False)),
        "params": params,
    }


def normalize_list(blocks) -> list:
    out = []
    for block in (blocks or []):
        normalized = normalize(block)
        if normalized is not None:
            out.append(normalized)
    return out


def catalog() -> list:
    """What the UI renders its palette from."""
    return BLOCK_TYPES


def summarise(block: dict) -> str:
    """One-line human description of a block for the activity log.

    Deliberately per-type rather than a generic key=value dump: the log is
    read while watching the macro run, and "Click 640,360 (left)" is legible
    where "x=640 y=360 button=left clicks=1 hold_ms=40" is not.
    """
    params = block.get("params") or {}
    btype = block.get("type")

    def g(key, default=""):
        value = params.get(key)
        return default if value in (None, "") else value

    if btype == "click":
        clicks = int(g("clicks", 1) or 1)
        return "Click %s,%s (%s%s)" % (g("x", 0), g("y", 0), g("button", "left"),
                                        "" if clicks == 1 else " x%d" % clicks)
    if btype == "move":
        return "Move to %s,%s" % (g("x", 0), g("y", 0))
    if btype == "drag":
        return "Drag %s,%s -> %s,%s (%s)" % (g("x", 0), g("y", 0), g("x2", 0),
                                              g("y2", 0), g("button", "left"))
    if btype == "scroll":
        amount = int(g("amount", 0) or 0)
        return "Scroll %s %d" % ("up" if amount > 0 else "down", abs(amount))
    if btype == "send_key":
        mods = params.get("modifiers") or []
        combo = "+".join(list(mods) + [str(g("key", "?"))])
        return "Key %s" % combo
    if btype == "hold_key":
        return "Hold %s for %sms" % (g("key", "?"), g("hold_ms", 0))
    if btype == "type_text":
        text = str(g("text", ""))
        shown = text if len(text) <= 40 else text[:37] + "..."
        return "Type %r" % shown
    if btype == "wait_ms":
        return "Wait %sms" % g("ms", 0)
    if btype == "wait_random":
        return "Wait %s-%sms" % (g("min_ms", 0), g("max_ms", 0))
    if btype == "wait_image":
        return "Wait for image '%s'" % g("template", "?")
    if btype == "click_image":
        return "Click image '%s'" % g("template", "?")
    if btype == "wait_image_gone":
        return "Wait until image '%s' is gone" % g("template", "?")
    if btype == "wait_color":
        return "Wait for colour %s at %s,%s" % (g("color", "?"), g("x", 0), g("y", 0))
    if btype == "click_color":
        return "Click colour %s" % g("color", "?")
    if btype == "wait_text":
        return "Wait for text %r" % str(g("text", ""))
    if btype == "click_text":
        return "Click text %r" % str(g("text", ""))
    if btype == "read_text":
        return "Read text"
    if btype == "loop_start":
        return "Loop start x%s" % g("count", 1)
    if btype == "loop_end":
        return "Loop end"
    if btype == "playback":
        return "Play recording '%s'" % g("recording", "?")
    if btype == "focus_window":
        bits = []
        if params.get("resize"):
            bits.append("%sx%s" % (g("width", 0), g("height", 0)))
        if params.get("move"):
            bits.append("at %s,%s" % (g("x", 0), g("y", 0)))
        return "Focus target" + (" (" + " ".join(bits) + ")" if bits else "")
    if btype == "log":
        return "Log %r" % str(g("text", ""))
    if btype == "send_webhook":
        source = str(g("source", "none"))
        text = str(g("message", ""))
        shown = text if len(text) <= 30 else text[:27] + "..."
        return "Webhook %r%s" % (shown, "" if source == "none" else " + " + source)
    spec = BY_TYPE.get(btype)
    return spec["label"] if spec else str(btype)


def _self_check() -> None:
    """Fail loudly at import if the table and its contract drift apart --
    an unrenderable kind would otherwise show up as a silently blank row."""
    seen = set()
    for spec in BLOCK_TYPES:
        assert spec["type"] not in seen, "duplicate block type %r" % spec["type"]
        seen.add(spec["type"])
        for field in spec["fields"]:
            assert field["kind"] in FIELD_KINDS, \
                "%s.%s has unrenderable kind %r" % (spec["type"], field["key"], field["kind"])


_self_check()

# Hover help lives in its own module so the table above stays compact; it is
# merged in here so every consumer sees one complete catalog.
from . import block_help as _block_help  # noqa: E402

_language = _block_help.DEFAULT_LANGUAGE
_block_help.apply_to(BLOCK_TYPES, _language)


def set_language(language: str) -> str:
    """Re-decorate the catalog with help in another language.

    The catalog is a module-level singleton every consumer already holds a
    reference to, so this rewrites it in place rather than returning a copy.
    """
    global _language
    _language = language if language in _block_help.LANGUAGES \
        else _block_help.DEFAULT_LANGUAGE
    _block_help.apply_to(BLOCK_TYPES, _language)
    return _language


def get_language() -> str:
    return _language
