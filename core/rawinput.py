"""Raw mouse deltas via WM_INPUT.

pynput reports the cursor's absolute POSITION. That is useless for the case
that matters most in games: while the game holds the cursor captured (right
button held to turn the camera), the pointer does not move at all, so
position-based recording captures a drag as "nothing happened".

The hardware still reports movement, and WM_INPUT delivers it as relative
deltas regardless of what the cursor is doing. Recording those, and replaying
them with relative moves, is the only way a camera drag survives a round trip.

Windows-only. On anything else `Listener.start()` reports False and the caller
falls back to position-based recording.
"""
import ctypes
import sys
import threading
from ctypes import wintypes

_AVAILABLE = sys.platform == "win32"

if _AVAILABLE:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Explicit prototypes. Without them ctypes marshals LPARAM as a plain C
    # int and a real 64-bit message parameter raises
    # "OverflowError: int too long to convert" inside the window procedure --
    # where the exception is swallowed and only printed, so the pump appears
    # to work while every unhandled message is lost.
    user32.DefWindowProcW.restype = ctypes.c_long
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.GetRawInputData.restype = wintypes.UINT
    user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                       ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.UINT),
                                       wintypes.UINT]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.RegisterRawInputDevices.restype = wintypes.BOOL
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    # HMODULE is pointer-sized. Without this the handle is truncated to 32
    # bits and RegisterClassW dereferences garbage -- an access violation
    # that only shows up once the module happens to load above 4 GB.
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
else:                                    # pragma: no cover - non-Windows
    user32 = kernel32 = None

# ------------------------------------------------------------------ constants
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02
RIDEV_INPUTSINK = 0x00000100        # deliver even when we are not focused
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
MOUSE_MOVE_RELATIVE = 0x00
WM_INPUT = 0x00FF
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
HWND_MESSAGE = -3
CW_USEDEFAULT = 0x80000000


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT),
                ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD),
                ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD),
                ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE),
                ("wParam", wintypes.WPARAM)]


# Declared at module level, not nested: a class body cannot refer to a
# sibling defined in the same body.
class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT),
                ("usButtonData", wintypes.USHORT)]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [("ulButtons", wintypes.ULONG),
                ("buttons", _RAWMOUSE_BUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", wintypes.USHORT),
                ("u", _RAWMOUSE_UNION),
                ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG),
                ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.WINFUNCTYPE(
                    ctypes.c_long, wintypes.HWND, wintypes.UINT,
                    wintypes.WPARAM, wintypes.LPARAM)),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

# ------------------------------------------------------- shared window class
#
# A window class can only be registered once per process, and it keeps a
# pointer to the window procedure FOREVER. Giving each listener its own
# closure meant the class outlived the callback that backed it: the second
# listener created a window whose procedure had already been freed, so its
# messages went nowhere and it silently received no deltas.
#
# One module-level procedure, kept alive for the process lifetime, dispatches
# to whichever listener owns the window.
_CLASS_NAME = "MacroStudioRawInput"
_listeners_by_hwnd = {}
_class_registered = False
_class_lock = threading.Lock()
_shared_wndproc = None


def _dispatch(hwnd, msg, wparam, lparam):
    if msg == WM_INPUT:
        listener = _listeners_by_hwnd.get(int(hwnd))
        if listener is not None:
            listener._handle(lparam)
        return 0
    if msg == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if msg == WM_DESTROY:
        _listeners_by_hwnd.pop(int(hwnd), None)
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _ensure_class() -> bool:
    global _class_registered, _shared_wndproc
    with _class_lock:
        if _class_registered:
            return True
        _shared_wndproc = WNDPROC(_dispatch)      # module-level: never freed
        wc = WNDCLASS()
        wc.lpfnWndProc = _shared_wndproc
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = _CLASS_NAME
        if not user32.RegisterClassW(ctypes.byref(wc)):
            # 1410 == ERROR_CLASS_ALREADY_EXISTS: fine, ours from earlier.
            if ctypes.get_last_error() != 1410:
                return False
        _class_registered = True
        return True


def available() -> bool:
    return _AVAILABLE


class Listener:
    """Calls `on_delta(dx, dy)` for every raw mouse movement.

    Runs its own thread with its own message-only window, because raw input
    is delivered as a window message and needs a pump. The callback fires on
    that thread and must be cheap.
    """

    def __init__(self, on_delta):
        self._on_delta = on_delta
        self._thread = None
        self._hwnd = None
        self._ready = threading.Event()
        self._ok = False

    def start(self) -> bool:
        if not _AVAILABLE:
            return False
        if self._thread is not None:
            return self._ok
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="rawinput")
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self._ok

    def stop(self) -> None:
        hwnd = self._hwnd
        if hwnd:
            try:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self._hwnd = None
        self._ok = False

    # ------------------------------------------------------------- internals

    def _handle(self, lparam) -> None:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, None,
                               ctypes.byref(size), header_size)
        if size.value == 0:
            return
        buf = ctypes.create_string_buffer(size.value)
        got = user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, buf,
                                     ctypes.byref(size), header_size)
        if got != size.value:
            return
        raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
        if raw.header.dwType != RIM_TYPEMOUSE:
            return
        # Absolute-mode devices (tablets, some VMs and RDP) report a position
        # in a virtual desktop range, not a delta. Passing that through as a
        # delta would fling the cursor across the screen.
        if raw.mouse.usFlags & ~MOUSE_MOVE_RELATIVE:
            return
        dx, dy = raw.mouse.lLastX, raw.mouse.lLastY
        if dx or dy:
            try:
                self._on_delta(int(dx), int(dy))
            except Exception:
                pass

    def _run(self) -> None:
        try:
            if not _ensure_class():
                self._ready.set()
                return
            hinst = kernel32.GetModuleHandleW(None)
            hwnd = user32.CreateWindowExW(
                0, _CLASS_NAME, _CLASS_NAME, 0,
                0, 0, 0, 0, wintypes.HWND(HWND_MESSAGE), None, hinst, None)
            if not hwnd:
                self._ready.set()
                return
            self._hwnd = hwnd
            _listeners_by_hwnd[int(hwnd)] = self

            device = RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC,
                                    HID_USAGE_GENERIC_MOUSE,
                                    RIDEV_INPUTSINK, hwnd)
            if not user32.RegisterRawInputDevices(
                    ctypes.byref(device), 1, ctypes.sizeof(RAWINPUTDEVICE)):
                _listeners_by_hwnd.pop(int(hwnd), None)
                user32.DestroyWindow(hwnd)
                self._hwnd = None
                self._ready.set()
                return

            self._ok = True
            self._ready.set()

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            self._ok = False
            self._ready.set()
