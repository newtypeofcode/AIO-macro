"""Win32 virtual-key codes plus name<->VK mapping.

The UI captures hotkeys through JS KeyboardEvent.key, and recordings store
key names, so both directions have to round-trip. Letters and digits map to
their ASCII code (VK_A == ord('A')), so only specials, F-keys and OEM
punctuation need a table.
"""

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12          # Alt
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21         # Page Up
VK_NEXT = 0x22          # Page Down
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_NUMPAD0 = 0x60
VK_MULTIPLY = 0x6A
VK_ADD = 0x6B
VK_SUBTRACT = 0x6D
VK_DECIMAL = 0x6E
VK_DIVIDE = 0x6F
VK_NUMLOCK = 0x90
VK_SCROLL = 0x91
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_OEM_1 = 0xBA         # ;:
VK_OEM_PLUS = 0xBB      # =+
VK_OEM_COMMA = 0xBC     # ,<
VK_OEM_MINUS = 0xBD     # -_
VK_OEM_PERIOD = 0xBE    # .>
VK_OEM_2 = 0xBF         # /?
VK_OEM_3 = 0xC0         # `~
VK_OEM_4 = 0xDB         # [{
VK_OEM_5 = 0xDC         # \|
VK_OEM_6 = 0xDD         # ]}
VK_OEM_7 = 0xDE         # '"

for _i in range(12):
    globals()["VK_F%d" % (_i + 1)] = 0x70 + _i

_SPECIAL_KEY_NAMES = {
    "backspace": VK_BACK, "tab": VK_TAB, "enter": VK_RETURN, "return": VK_RETURN,
    "shift": VK_SHIFT, "ctrl": VK_CONTROL, "control": VK_CONTROL,
    "alt": VK_MENU, "capslock": VK_CAPITAL, "esc": VK_ESCAPE, "escape": VK_ESCAPE,
    "space": VK_SPACE, " ": VK_SPACE,
    "pageup": VK_PRIOR, "pagedown": VK_NEXT, "end": VK_END, "home": VK_HOME,
    "left": VK_LEFT, "arrowleft": VK_LEFT, "up": VK_UP, "arrowup": VK_UP,
    "right": VK_RIGHT, "arrowright": VK_RIGHT, "down": VK_DOWN, "arrowdown": VK_DOWN,
    "insert": VK_INSERT, "delete": VK_DELETE, "del": VK_DELETE,
    "win": VK_LWIN, "meta": VK_LWIN, "numlock": VK_NUMLOCK,
}

_F_KEY_NAMES = {"f%d" % (i + 1): 0x70 + i for i in range(12)}

# Keyed by the literal character KeyboardEvent.key reports -- letters and
# digits have the ord() shortcut, OEM punctuation does not.
_OEM_KEY_NAMES = {
    ";": VK_OEM_1, ":": VK_OEM_1, "=": VK_OEM_PLUS, "+": VK_OEM_PLUS,
    ",": VK_OEM_COMMA, "<": VK_OEM_COMMA, "-": VK_OEM_MINUS, "_": VK_OEM_MINUS,
    ".": VK_OEM_PERIOD, ">": VK_OEM_PERIOD, "/": VK_OEM_2, "?": VK_OEM_2,
    "`": VK_OEM_3, "~": VK_OEM_3, "[": VK_OEM_4, "{": VK_OEM_4,
    "\\": VK_OEM_5, "|": VK_OEM_5, "]": VK_OEM_6, "}": VK_OEM_6,
    "'": VK_OEM_7, '"': VK_OEM_7,
}

# Canonical spelling per VK, declared explicitly rather than derived from
# _SPECIAL_KEY_NAMES' iteration order: these names are written into saved
# recordings, so which alias wins must not change if the alias table is
# ever reordered ("esc" vs "escape" silently swapping would invalidate
# every recording on disk).
_VK_TO_NAME = {
    VK_BACK: "backspace", VK_TAB: "tab", VK_RETURN: "enter",
    VK_SHIFT: "shift", VK_CONTROL: "ctrl", VK_MENU: "alt",
    VK_CAPITAL: "capslock", VK_ESCAPE: "escape", VK_SPACE: "space",
    VK_PRIOR: "pageup", VK_NEXT: "pagedown", VK_END: "end", VK_HOME: "home",
    VK_LEFT: "left", VK_UP: "up", VK_RIGHT: "right", VK_DOWN: "down",
    VK_INSERT: "insert", VK_DELETE: "delete",
    VK_LWIN: "win", VK_NUMLOCK: "numlock",
    # Left/right variants collapse to the plain name: a recording that says
    # "shift" must replay on either physical Shift.
    VK_LSHIFT: "shift", VK_RSHIFT: "shift",
    VK_LCONTROL: "ctrl", VK_RCONTROL: "ctrl",
    VK_LMENU: "alt", VK_RMENU: "alt",
}
_VK_TO_NAME.update({0x70 + _i: "f%d" % (_i + 1) for _i in range(12)})

MODIFIER_NAMES = {"shift": VK_SHIFT, "ctrl": VK_CONTROL, "alt": VK_MENU, "win": VK_LWIN}


def _vk_from_layout(ch: str):
    """Ask Windows which key produces this character on the ACTIVE layout.

    VkKeyScanW returns -1 when the character is unreachable; the low byte is
    the VK and the high byte the required modifiers (which callers handle
    separately, so only the VK is taken here).
    """
    try:
        import ctypes
        result = ctypes.WinDLL("user32", use_last_error=True).VkKeyScanW(ch)
    except Exception:
        return None
    if result == -1:
        return None
    return result & 0xFF


def key_name_to_vk(name):
    """Name -> VK code, or None (never raises) so an unbound hotkey is a
    silent no-op rather than a crash mid-run."""
    if not name:
        return None
    raw = str(name)
    low = raw.strip().lower()
    if low in _SPECIAL_KEY_NAMES:
        return _SPECIAL_KEY_NAMES[low]
    if low in _F_KEY_NAMES:
        return _F_KEY_NAMES[low]
    if raw in _OEM_KEY_NAMES:
        return _OEM_KEY_NAMES[raw]
    if low in _OEM_KEY_NAMES:
        return _OEM_KEY_NAMES[low]
    if len(low) == 1:
        # ord() is only valid for A-Z and 0-9, where VK codes coincide with
        # ASCII. Using it as a blanket fallback silently mapped punctuation
        # to unrelated keys: '!' -> 0x21 is VK_PRIOR (Page Up), '%' -> 0x25
        # is VK_LEFT, '(' -> 0x28 is VK_DOWN. Anything else goes through the
        # layout, which is what actually knows where the character lives.
        if low.isascii() and low.isalnum():
            return ord(low.upper())
        return _vk_from_layout(raw if len(raw) == 1 else low)
    return None


def vk_to_key_name(vk):
    """VK code -> the name the UI and recordings use."""
    try:
        vk = int(vk)
    except (TypeError, ValueError):
        return ""
    if vk in _VK_TO_NAME:
        return _VK_TO_NAME[vk]
    for char, code in _OEM_KEY_NAMES.items():
        if code == vk:
            return char
    if 0x30 <= vk <= 0x5A:
        return chr(vk).lower()
    return "vk%d" % vk
