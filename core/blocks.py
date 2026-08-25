"""Block catalog -- the single source of truth for what a block is.

The UI builds its palette and its per-row fields from BLOCK_TYPES, and the
runner dispatches on the same `type` strings, so adding a block means
editing this one table plus one handler in runner.py.

Field kinds the UI understands -- FIELD_KINDS below is the authoritative
list; a kind not in it has no renderer and would leave a blank row.
"""
import copy
from collections import abc

from .i18n import tr

PHASES = ("setup", "loop", "watch")
# The phase that runs once, and the one that repeats. The runner reads these
# rather than hardcoding the strings, so the two cannot drift apart.
PHASE_ONCE = "setup"
PHASE_REPEAT = "loop"
# Checked between blocks for as long as the macro runs. It is not part of the
# sequence: it interrupts it, does its thing, and then hands control back
# according to WATCH_AFTER_OPTIONS.
PHASE_WATCH = "watch"


class _PhaseLabels(abc.Mapping):
    """The phase headings, translated on lookup rather than at import.

    The KEYS are identifiers -- every saved macro stores them, so they can
    never change. The values are read text: main.py builds the UI's phase
    headings from them and the runner puts them into four log lines, all of
    it long after this module is imported and after the language may have
    been switched, so a plain dict of English words froze both in whichever
    language the process happened to start in.
    """

    def __iter__(self):
        return iter(PHASES)

    def __len__(self):
        return len(PHASES)

    def __getitem__(self, key):
        # Literal arguments rather than tr() over a stored English value:
        # the table scan in tests/test_messages.py reads the syntax tree, and
        # a message it cannot see is one that never gets a Russian entry.
        if key == PHASE_ONCE:
            return tr("Setup")
        if key == PHASE_REPEAT:
            return tr("Loop")
        if key == PHASE_WATCH:
            return tr("Watch")
        raise KeyError(key)


# Mapping, not dict: get(), items() and values() are then derived from the
# lookup above, so there is no second copy of the English to go stale.
PHASE_LABELS = _PhaseLabels()

FIELD_KINDS = ("int", "float", "text", "key", "bool", "choice", "modifiers",
               "region", "color", "template", "recording", "blocks",
               "map_point", "condition", "conditions")

# What a Vision block does when it does not find what it was looking for.
ON_FAIL_OPTIONS = ["continue", "run blocks", "restart phase", "restart macro",
                   "skip rest", "stop"]
# What happens once a "run blocks" fallback has finished.
ON_FAIL_AFTER_OPTIONS = ["continue main", "restart phase", "restart macro", "stop"]

# Camera Setup: sweep to the camera's own limit, or move an exact amount.
LOOK_MODE_OPTIONS = ["to limit", "exact"]

# What happens once the Watch phase has fired and finished its blocks.
WATCH_AFTER_OPTIONS = ["continue", "restart loop", "restart macro"]

# Read Text can compare what it read against a value. The numeric ones
# parse a number out of the OCR string, so "Wave 12" > 9 works.
TEXT_COMPARE_OPTIONS = ["off", "equals", "not equals", "contains",
                        "not contains", "greater", "greater or equal",
                        "less", "less or equal"]

_ON_FAIL_TEMPLATE = [
    {"key": "on_fail", "kind": "choice", "default": "continue",
     "options": ON_FAIL_OPTIONS},
    # Both only meaningful for "run blocks"; the UI hides them otherwise.
    {"key": "on_fail_blocks", "kind": "blocks", "default": []},
    {"key": "on_fail_after", "kind": "choice", "default": "continue main",
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

# No `label` here, for blocks or for fields: block_help.apply_to() writes one
# in the chosen language, and a second copy in this table would be dead text
# that drifts away from the one people actually read.
BLOCK_TYPES = [
    # ------------------------------------------------------------ mouse
    {"type": "click", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
         {"key": "button", "kind": "choice", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "clicks", "kind": "int", "default": 1},
         {"key": "hold_ms", "kind": "int", "default": 40},
     ]},
    {"type": "move", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
         {"key": "duration_ms", "kind": "int", "default": 0},
     ]},
    {"type": "move_by", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "dx", "kind": "int", "default": 0},
         {"key": "dy", "kind": "int", "default": 0},
         {"key": "duration_ms", "kind": "int", "default": 0},
     ]},
    {"type": "drag", "group": "Mouse", "color": "rose",
     "fields": [
         # Both default to "point", which is exactly what every macro
         # saved before these two fields existed did.
         {"key": "from_mode", "kind": "choice", "default": "point",
          "options": ["point", "current"]},
         {"key": "to_mode", "kind": "choice", "default": "point",
          "options": ["point", "offset"]},
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
         {"key": "x2", "kind": "int", "default": 0},
         {"key": "y2", "kind": "int", "default": 0},
         {"key": "button", "kind": "choice", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "duration_ms", "kind": "int", "default": 250},
     ]},
    {"type": "scroll", "group": "Mouse", "color": "rose",
     "fields": [
         {"key": "amount", "kind": "int", "default": -120},
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
     ]},

    # ------------------------------------------------------------ roblox
    # Game-specific blocks. They send nothing a Mouse or Keyboard block
    # cannot, but the defaults, the units and the map picker only make
    # sense for a game, and mixing them into Mouse buried the plain
    # blocks under them.
    # Camera-look drag. Separate from "drag" because the whole point is
    # that it sends nothing but relative deltas -- see the handler.
    {"type": "mouse_look", "group": "Roblox", "color": "lime",
     "fields": [
         {"key": "button", "kind": "choice", "default": "right",
          "options": ["right", "left", "middle", "none"]},
         # "to limit" sweeps far past the camera's stop and ends pinned
         # against it, which is the same place on every sensitivity.
         # "exact" is the old aim-a-distance behaviour.
         {"key": "mode", "kind": "choice", "default": "to limit",
          "options": LOOK_MODE_OPTIONS},
         {"key": "dx", "kind": "int", "default": 0},
         {"key": "dy", "kind": "int", "default": 400},
         {"key": "sweep_px", "kind": "int", "default": 40000},
         {"key": "steps", "kind": "int", "default": 40},
         {"key": "step_delay_ms", "kind": "int", "default": 8},
         {"key": "centre_first", "kind": "bool", "default": True},
         {"key": "settle_ms", "kind": "int", "default": 80},
     ]},
    {"type": "place_unit", "group": "Roblox", "color": "lime",
     "fields": [
         {"key": "unit", "kind": "key", "default": ""},
         # [map name, x, y, image width, image height]. The image size
         # travels with the point so the runner can scale it onto a
         # window of a different size without reading the PNG.
         {"key": "location", "kind": "map_point", "default": None},
         # The game enters placement mode on the hotkey and needs time
         # to spawn the ghost; a click before that is swallowed.
         {"key": "key_delay_ms", "kind": "int", "default": 500},
         {"key": "clicks", "kind": "int", "default": 2},
         {"key": "after_ms", "kind": "int", "default": 250},
     ]},
    # Kills the client and joins again through the launcher's deep link.
    # on_fail rides along because "the game never came back" is the one
    # failure a long unattended run has to be able to react to.
    {"type": "roblox_rejoin", "group": "Roblox", "color": "lime",
     "fields": [
         # One pasted share link replaces the two fields below it.
         {"key": "share_link", "kind": "text", "default": ""},
         {"key": "place_id", "kind": "text", "default": ""},
         {"key": "link_code", "kind": "text", "default": ""},
         {"key": "close_first", "kind": "bool", "default": True},
         {"key": "close_wait_ms", "kind": "int", "default": 4000},
         {"key": "timeout_ms", "kind": "int", "default": 90000},
         {"key": "settle_ms", "kind": "int", "default": 12000},
         {"key": "retarget", "kind": "bool", "default": True},
     ] + _on_fail_fields()},

    # --------------------------------------------------------- keyboard
    {"type": "send_key", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "key", "kind": "key", "default": ""},
         {"key": "hold_ms", "kind": "int", "default": 30},
         {"key": "modifiers", "kind": "modifiers", "default": []},
     ]},
    {"type": "type_text", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "text", "kind": "text", "default": ""},
         {"key": "delay_ms", "kind": "int", "default": 20},
     ]},
    {"type": "hold_key", "group": "Keyboard", "color": "blue",
     "fields": [
         {"key": "key", "kind": "key", "default": ""},
         {"key": "hold_ms", "kind": "int", "default": 1000},
     ]},

    # ----------------------------------------------------------- timing
    {"type": "wait_ms", "group": "Timing", "color": "amber",
     "fields": [{"key": "ms", "kind": "int", "default": 500}]},
    {"type": "wait_random", "group": "Timing", "color": "amber",
     "fields": [
         {"key": "min_ms", "kind": "int", "default": 200},
         {"key": "max_ms", "kind": "int", "default": 800},
     ]},

    # ----------------------------------------------------------- vision
    {"type": "wait_image", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "default": ""},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "threshold", "kind": "float", "default": 0.88},
         {"key": "region", "kind": "region", "default": None},
     ] + _on_fail_fields()},
    {"type": "click_image", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "default": ""},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "threshold", "kind": "float", "default": 0.88},
         {"key": "region", "kind": "region", "default": None},
         {"key": "button", "kind": "choice", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "default": 0},
         {"key": "offset_y", "kind": "int", "default": 0},
     ] + _on_fail_fields()},
    {"type": "wait_image_gone", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "template", "kind": "template", "default": ""},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "threshold", "kind": "float", "default": 0.88},
         {"key": "region", "kind": "region", "default": None},
     ] + _on_fail_fields()},
    {"type": "wait_color", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
         {"key": "color", "kind": "color", "default": "#ffffff"},
         # Same 0-1 scale as the image and text blocks. The old 0-255
         # `tolerance` is still honoured when a saved macro carries it.
         {"key": "confidence", "kind": "float", "default": 0.92},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
     ] + _on_fail_fields()},
    {"type": "click_color", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "color", "kind": "color", "default": "#ffffff"},
         {"key": "confidence", "kind": "float", "default": 0.90},
         {"key": "min_pixels", "kind": "int", "default": 40},
         {"key": "region", "kind": "region", "default": None},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "button", "kind": "choice", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "default": 0},
         {"key": "offset_y", "kind": "int", "default": 0},
     ] + _on_fail_fields()},
    {"type": "wait_text", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "text", "kind": "text", "default": ""},
         {"key": "region", "kind": "region", "default": None},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "confidence", "kind": "float", "default": 0.75},
         {"key": "match", "kind": "choice", "default": "contains",
          "options": ["contains", "exact"]},
     ] + _on_fail_fields()},
    {"type": "click_text", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "text", "kind": "text", "default": ""},
         {"key": "region", "kind": "region", "default": None},
         {"key": "timeout_ms", "kind": "int", "default": 8000},
         {"key": "confidence", "kind": "float", "default": 0.75},
         {"key": "button", "kind": "choice", "default": "left",
          "options": ["left", "right", "middle"]},
         {"key": "offset_x", "kind": "int", "default": 0},
         {"key": "offset_y", "kind": "int", "default": 0},
     ] + _on_fail_fields()},
    {"type": "read_text", "group": "Vision", "color": "teal",
     "fields": [
         {"key": "region", "kind": "region", "default": None},
         {"key": "confidence", "kind": "float", "default": 0.75},
         # "off" keeps the block exactly as it was before comparing existed:
         # read, log, carry on. Anything else turns it into a check.
         {"key": "compare", "kind": "choice", "default": "off",
          "options": TEXT_COMPARE_OPTIONS},
         {"key": "expect", "kind": "text", "default": ""},
     ] + _on_fail_fields()},

    # ------------------------------------------------------------ flow
    {"type": "if_else", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "condition", "kind": "condition", "default": None},
         {"key": "then_blocks", "kind": "blocks", "default": []},
         {"key": "else_blocks", "kind": "blocks", "default": []},
     ]},
    {"type": "while_loop", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "condition", "kind": "condition", "default": None},
         {"key": "blocks", "kind": "blocks", "default": []},
         {"key": "max_iter", "kind": "int", "default": 100},
     ]},
    {"type": "repeat_until", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "condition", "kind": "condition", "default": None},
         {"key": "blocks", "kind": "blocks", "default": []},
         {"key": "max_iter", "kind": "int", "default": 100},
     ]},
    {"type": "loop_start", "group": "Flow", "color": "violet",
     "fields": [{"key": "count", "kind": "int", "default": 2}]},
    {"type": "loop_end", "group": "Flow", "color": "violet",
     "fields": []},
    # The two jumps a Vision block could already make through on_fail, as
    # plain blocks -- so they can also sit at the end of a fallback list or
    # behind a Watch check.
    {"type": "restart_loop", "group": "Flow", "color": "violet",
     "fields": []},
    {"type": "restart_macro", "group": "Flow", "color": "violet",
     "fields": []},
    {"type": "playback", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "recording", "kind": "recording", "default": ""},
         {"key": "speed", "kind": "float", "default": 1.0},
     ]},
    {"type": "focus_window", "group": "Flow", "color": "violet",
     "fields": [
         {"key": "resize", "kind": "bool", "default": False},
         {"key": "width", "kind": "int", "default": 1280},
         {"key": "height", "kind": "int", "default": 720},
         {"key": "move", "kind": "bool", "default": False},
         {"key": "x", "kind": "int", "default": 0},
         {"key": "y", "kind": "int", "default": 0},
     ]},
    {"type": "log", "group": "Flow", "color": "violet",
     "fields": [{"key": "text", "kind": "text", "default": ""}]},

    # ----------------------------------------------------------- system
    {"type": "open_app", "group": "System", "color": "indigo",
     "fields": [
         {"key": "path", "kind": "text", "default": ""},
         {"key": "args", "kind": "text", "default": ""},
         {"key": "wait_ms", "kind": "int", "default": 0},
     ]},
    {"type": "kill_process", "group": "System", "color": "indigo",
     "fields": [
         {"key": "name", "kind": "text", "default": ""},
         {"key": "force", "kind": "bool", "default": True},
     ]},

    # ------------------------------------------------------------- notify
    {"type": "send_webhook", "group": "Notify", "color": "blue",
     "fields": [
         {"key": "message", "kind": "text", "default": ""},
         {"key": "title", "kind": "text", "default": ""},
         {"key": "color", "kind": "color", "default": ""},
         {"key": "footer", "kind": "text", "default": ""},
         {"key": "timestamp", "kind": "bool", "default": True},
         {"key": "source", "kind": "choice", "default": "none",
          "options": ["none", "target window", "whole screen", "region", "saved image"]},
         {"key": "region", "kind": "region", "default": None},
         {"key": "template", "kind": "template", "default": ""},
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

    Translated through i18n rather than assembled out of the catalog's
    labels: this is the highest-volume line in the log, so it has to read as
    a sentence in the log's language, while the values inside it stay
    whatever the macro actually stored.
    """
    params = block.get("params") or {}
    btype = block.get("type")

    def g(key, default=""):
        value = params.get(key)
        return default if value in (None, "") else value

    if btype == "click":
        clicks = int(g("clicks", 1) or 1)
        return tr("Click %s,%s (%s%s)") % (
            g("x", 0), g("y", 0), g("button", "left"),
            "" if clicks == 1 else " x%d" % clicks)
    if btype == "move":
        return tr("Move to %s,%s") % (g("x", 0), g("y", 0))
    if btype == "move_by":
        return tr("Move by %s,%s") % (g("dx", 0), g("dy", 0))
    if btype == "drag":
        # The summary has to say WHICH numbers these are: "0,200" means
        # the top-left corner as a point and "200 pixels down" as an
        # offset, and the row is unreadable if it does not distinguish
        # the two.
        start = (tr("cursor") if str(g("from_mode", "point")) == "current"
                 else "%s,%s" % (g("x", 0), g("y", 0)))
        if str(g("to_mode", "point")) == "offset":
            return tr("Drag from %s by %s,%s (%s)") % (
                start, g("x2", 0), g("y2", 0), g("button", "left"))
        return tr("Drag from %s to %s,%s (%s)") % (
            start, g("x2", 0), g("y2", 0), g("button", "left"))
    if btype == "mouse_look":
        if str(g("mode", "to limit")) != "exact":
            return tr("Camera to the limit %s,%s (%s)") % (
                g("dx", 0), g("dy", 0), g("button", "right"))
        return tr("Look %s,%s x%s (%s)") % (
            g("dx", 0), g("dy", 0), g("steps", 1), g("button", "right"))
    if btype == "place_unit":
        location = g("location", None)
        unit = g("unit", "") or "?"
        if isinstance(location, (list, tuple)) and len(location) >= 3:
            return tr("Place %s on %s at %s,%s") % (
                unit, location[0], location[1], location[2])
        # No spot picked yet: say so rather than print "None at 0,0".
        return tr("Place %s (no location)") % unit
    if btype == "roblox_rejoin":
        if str(g("share_link", "")).strip():
            return tr("Rejoin Roblox (%s)") % tr("share link")
        place = str(g("place_id", "")).strip()
        return tr("Rejoin Roblox (%s)") % (place or tr("server from Settings"))
    if btype == "restart_loop":
        return tr("Restart this phase")
    if btype == "restart_macro":
        return tr("Restart the macro")
    if btype == "if_else":
        cond = bool(params.get("condition"))
        return tr("If / Else (%s)") % (tr("condition set") if cond else tr("condition not set"))
    if btype == "while_loop":
        return tr("While loop (max %d)") % int(g("max_iter", 100) or 100)
    if btype == "repeat_until":
        return tr("Repeat until (max %d)") % int(g("max_iter", 100) or 100)
    if btype == "open_app":
        return tr("Open app %r") % str(g("path", ""))
    if btype == "kill_process":
        return tr("Kill process %r") % str(g("name", ""))
    if btype == "scroll":
        amount = int(g("amount", 0) or 0)
        # Two whole templates rather than one with "up" or "down" dropped
        # into it: a bare direction has no gender or case to agree with on
        # its own, so no table can translate it in isolation.
        if amount > 0:
            return tr("Scroll up %d") % abs(amount)
        return tr("Scroll down %d") % abs(amount)
    if btype == "send_key":
        mods = params.get("modifiers") or []
        combo = "+".join(list(mods) + [str(g("key", "?"))])
        return tr("Key %s") % combo
    if btype == "hold_key":
        return tr("Hold %s for %sms") % (g("key", "?"), g("hold_ms", 0))
    if btype == "type_text":
        text = str(g("text", ""))
        shown = text if len(text) <= 40 else text[:37] + "..."
        return tr("Type %r") % shown
    if btype == "wait_ms":
        return tr("Wait %sms") % g("ms", 0)
    if btype == "wait_random":
        return tr("Wait %s-%sms") % (g("min_ms", 0), g("max_ms", 0))
    if btype == "wait_image":
        return tr("Wait for image '%s'") % g("template", "?")
    if btype == "click_image":
        return tr("Click image '%s'") % g("template", "?")
    if btype == "wait_image_gone":
        return tr("Wait until image '%s' is gone") % g("template", "?")
    if btype == "wait_color":
        return tr("Wait for colour %s at %s,%s") % (g("color", "?"), g("x", 0),
                                                    g("y", 0))
    if btype == "click_color":
        return tr("Click colour %s") % g("color", "?")
    if btype == "wait_text":
        return tr("Wait for text %r") % str(g("text", ""))
    if btype == "click_text":
        return tr("Click text %r") % str(g("text", ""))
    if btype == "read_text":
        op = str(g("compare", "off") or "off")
        if op in ("", "off"):
            return tr("Read text")
        return tr("Read text %s %r") % (op, str(g("expect", "")))
    if btype == "loop_start":
        return tr("Loop start x%s") % g("count", 1)
    if btype == "loop_end":
        return tr("Loop end")
    if btype == "playback":
        return tr("Play recording '%s'") % g("recording", "?")
    if btype == "focus_window":
        bits = []
        if params.get("resize"):
            bits.append("%sx%s" % (g("width", 0), g("height", 0)))
        if params.get("move"):
            bits.append(tr("at %s,%s") % (g("x", 0), g("y", 0)))
        return tr("Focus target") + (" (" + " ".join(bits) + ")" if bits else "")
    if btype == "log":
        return tr("Log %r") % str(g("text", ""))
    if btype == "send_webhook":
        source = str(g("source", "none"))
        text = str(g("message", ""))
        shown = text if len(text) <= 30 else text[:27] + "..."
        return tr("Webhook %r%s") % (
            shown, "" if source == "none" else " + " + source)
    # Only reachable for a type with no case above; the label it falls back
    # to is whatever language the catalog is decorated in.
    spec = BY_TYPE.get(btype)
    return (spec or {}).get("label") or str(btype)


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

# Labels and hover help live in their own module so the table above stays
# compact and translatable; they are merged in here so every consumer sees
# one complete catalog.
from . import block_help as _block_help  # noqa: E402

_language = _block_help.DEFAULT_LANGUAGE
_block_help.apply_to(BLOCK_TYPES, _language)


def set_language(language: str) -> str:
    """Re-decorate the catalog with labels and help in another language.

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
