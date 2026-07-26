"""Windows implementation of the low-level input primitives."""
import ctypes
from ctypes import wintypes

from ._sendinput import (
    MouseInput, KeyBdInput, send_mouse_input, send_keyboard_input,
    screen_to_absolute, vk_to_scan, user32,
    MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK,
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL,
    KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_UNICODE,
)

import time

_BTN_DOWN = {"left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN,
             "middle": MOUSEEVENTF_MIDDLEDOWN}
_BTN_UP = {"left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP,
           "middle": MOUSEEVENTF_MIDDLEUP}

# ------------------------------------------------------- self-echo tracking
#
# Everything this module injects also arrives back through the global hooks
# the recorder listens on. Without a way to tell the two apart, recording
# while a macro plays captures the macro's own output and the recording grows
# a copy of itself every time it runs.
#
# A timestamp per (kind, identity) is enough: an injected event is observed
# within a millisecond or two, so anything matching inside the window is ours.
_ECHO_WINDOW_S = 0.12
_echoes = {}


def _mark(kind: str, identity) -> None:
    _echoes[(kind, identity)] = time.perf_counter()


def was_injected(kind: str, identity, window: float = _ECHO_WINDOW_S) -> bool:
    """Whether this app produced that event a moment ago.

    Consumes the mark, so a genuine second press of the same key right after
    a synthetic one is still recorded.
    """
    stamp = _echoes.pop((kind, identity), None)
    if stamp is None:
        return False
    return (time.perf_counter() - stamp) <= window


def clear_injected_marks() -> None:
    _echoes.clear()

# Without KEYEVENTF_EXTENDEDKEY these scancodes are ambiguous: VK_LEFT's
# scancode 0x4B IS numpad-4 to anything reading the raw scancode, so arrow
# keys and navigation silently do nothing in games.
_EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24,          # PageUp/Down, End, Home
    0x25, 0x26, 0x27, 0x28,          # arrows
    0x2D, 0x2E,                      # Insert, Delete
    0x6F,                            # numpad /
    0x90,                            # NumLock
    0xA3, 0xA5,                      # RControl, RAlt
    0x5B, 0x5C,                      # Win keys
}

# Set 1 physical positions. Sent by POSITION, not VK, so a recording made on
# QWERTY replays correctly on AZERTY -- VK_W is a different physical key
# there, but games bind movement to the physical WASD cluster.
_MOVE_SCANCODES = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20,
                   "q": 0x10, "e": 0x12, "r": 0x13, "f": 0x21,
                   "space": 0x39, "shift": 0x2A, "ctrl": 0x1D}


def move_abs(x: int, y: int) -> None:
    ax, ay = screen_to_absolute(x, y)
    send_mouse_input(MouseInput(
        dx=ax, dy=ay, mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        time=0, dwExtraInfo=0))


def move_rel(dx: int, dy: int) -> None:
    send_mouse_input(MouseInput(dx=int(dx), dy=int(dy), mouseData=0,
                                dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0))


def button_down(button: str = "left") -> None:
    flag = _BTN_DOWN.get(button)
    if flag:
        _mark("mouse_down", button)
        send_mouse_input(MouseInput(dx=0, dy=0, mouseData=0, dwFlags=flag,
                                    time=0, dwExtraInfo=0))


def button_up(button: str = "left") -> None:
    flag = _BTN_UP.get(button)
    if flag:
        _mark("mouse_up", button)
        send_mouse_input(MouseInput(dx=0, dy=0, mouseData=0, dwFlags=flag,
                                    time=0, dwExtraInfo=0))


def scroll(amount: int, horizontal: bool = False) -> None:
    flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    send_mouse_input(MouseInput(dx=0, dy=0, mouseData=int(amount),
                                dwFlags=flag, time=0, dwExtraInfo=0))


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _key_flags(vk: int) -> int:
    flags = KEYEVENTF_SCANCODE
    if vk in _EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    return flags


def key_down(vk: int) -> None:
    # Scan codes (wVk=0), not VK codes: that is what a real keyboard driver
    # reports, and games pick it up far more reliably.
    _mark("key_down", int(vk))
    send_keyboard_input(KeyBdInput(wVk=0, wScan=vk_to_scan(vk),
                                   dwFlags=_key_flags(vk), time=0, dwExtraInfo=0))


def key_up(vk: int) -> None:
    _mark("key_up", int(vk))
    send_keyboard_input(KeyBdInput(wVk=0, wScan=vk_to_scan(vk),
                                   dwFlags=_key_flags(vk) | KEYEVENTF_KEYUP,
                                   time=0, dwExtraInfo=0))


def unicode_char(ch: str, up: bool = False) -> None:
    """Type a literal character by its codepoint, bypassing the layout.
    Needed for text a scancode can't express (Cyrillic, accents, emoji).

    wScan is a WORD, so a codepoint above U+FFFF (emoji, rarer CJK) has to be
    sent as its UTF-16 surrogate PAIR. Passing the raw codepoint truncated it
    to 16 bits and typed an unrelated glyph.
    """
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    code = ord(ch)
    if code > 0xFFFF:
        code -= 0x10000
        units = (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
    else:
        units = (code,)
    for unit in units:
        send_keyboard_input(KeyBdInput(wVk=0, wScan=unit, dwFlags=flags,
                                       time=0, dwExtraInfo=0))


def is_key_down(vk: int) -> bool:
    # Real physical state regardless of which window has focus.
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def move_key_down(name: str) -> None:
    scan = _MOVE_SCANCODES.get(str(name).lower())
    if scan is None:
        return
    send_keyboard_input(KeyBdInput(wVk=0, wScan=scan, dwFlags=KEYEVENTF_SCANCODE,
                                   time=0, dwExtraInfo=0))


def move_key_up(name: str) -> None:
    scan = _MOVE_SCANCODES.get(str(name).lower())
    if scan is None:
        return
    send_keyboard_input(KeyBdInput(wVk=0, wScan=scan,
                                   dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP,
                                   time=0, dwExtraInfo=0))
