"""Raw Win32 SendInput plumbing shared by the mouse and keyboard backends.

SendInput rather than SetCursorPos/mouse_event/pyautogui because it pushes
through the real input stack, which is what games actually listen to.
"""
import ctypes
from ctypes import wintypes
import sys

if sys.platform != "win32":
    raise RuntimeError("_sendinput is Windows-only")

user32 = ctypes.WinDLL("user32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MAPVK_VK_TO_VSC = 0


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyBdInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


def _dispatch(inp: Input) -> None:
    ctypes.set_last_error(0)
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(Input))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def send_mouse_input(mi: MouseInput) -> None:
    _dispatch(Input(type=INPUT_MOUSE, mi=mi))


def send_keyboard_input(ki: KeyBdInput) -> None:
    _dispatch(Input(type=INPUT_KEYBOARD, ki=ki))


def virtual_screen_rect():
    return (user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))


def screen_to_absolute(x: int, y: int):
    """Screen pixels -> SendInput's normalized 0..65535 range.

    Normalized against the FULL virtual desktop, which is why every absolute
    move must also carry MOUSEEVENTF_VIRTUALDESK -- without that flag Windows
    maps 0..65535 onto the primary monitor only, and every click silently
    lands on the wrong screen.

    Clamped because GetSystemMetrics reports a virtualized size to a
    DPI-unaware process; a wrong denominator degrades to "clicks the nearest
    screen edge" instead of an arbitrary coordinate.
    """
    vx, vy, vw, vh = virtual_screen_rect()
    vw = vw or 1
    vh = vh or 1
    # Divide by (span - 1), not span: the range 0..65535 maps onto the pixel
    # CENTRES of a vw-wide desktop, so using vw biases every coordinate
    # toward the origin and the rightmost/bottom pixel is unreachable.
    ax = int(round((x - vx) * 65535.0 / max(1, vw - 1)))
    ay = int(round((y - vy) * 65535.0 / max(1, vh - 1)))
    return max(0, min(65535, ax)), max(0, min(65535, ay))


def vk_to_scan(vk: int) -> int:
    return user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
