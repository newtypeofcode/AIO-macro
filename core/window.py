"""Win32 window enumeration, geometry and coordinate conversion.

The macro's coordinates are stored relative to the TARGET WINDOW's client
area, not the screen, so a recording still lands correctly after the user
moves or resizes that window. This module owns that translation.
"""
import ctypes
from ctypes import wintypes
import os

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shcore = None
try:
    shcore = ctypes.WinDLL("shcore")
except OSError:
    pass

# Explicit prototypes: ctypes' default c_int return TRUNCATES 64-bit handles.
user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
SW_RESTORE = 9
SW_SHOW = 5
SW_MINIMIZE = 6
HWND_TOP = 0
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
PW_RENDERFULLCONTENT = 0x2
DWMWA_CLOAKED = 14


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def set_dpi_aware() -> None:
    """Call once at startup, before any geometry is read.

    Every coordinate in this app assumes screen pixels and "Windows pixels"
    are the same thing. If this process and the target disagree (non-100%
    display scaling), everything drifts: captures come back the wrong size
    and clicks land near but not on the right spot. Each call can fail
    silently, so each return value is checked rather than assumed.
    """
    try:
        # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2. Pointer-sized:
        # a bare Python -1/-4 marshals as 0x00000000FFFFFFFC and fails.
        fn = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if fn is not None:
            fn.argtypes = [ctypes.c_void_p]
            fn.restype = wintypes.BOOL
            if fn(ctypes.c_void_p(-4)):
                return
    except Exception:
        pass
    try:
        if shcore is not None and shcore.SetProcessDpiAwareness(2) == 0:
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def get_display_scale_percent() -> int:
    try:
        fn = getattr(user32, "GetDpiForSystem", None)
        if fn is not None:
            return int(round(fn() / 96.0 * 100))
    except Exception:
        pass
    return 100


def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def is_window(hwnd) -> bool:
    # Deliberately NOT IsWindowVisible: a window hidden on purpose must not
    # read as "closed".
    return bool(hwnd) and bool(user32.IsWindow(int(hwnd)))


def is_window_visible(hwnd) -> bool:
    return bool(user32.IsWindowVisible(int(hwnd)))


def _is_cloaked(hwnd) -> bool:
    """UWP windows sit in the list as invisible shells; DwmGetWindowAttribute
    is the only thing that reports them as cloaked."""
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        value = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(wintypes.HWND(int(hwnd)), DWMWA_CLOAKED,
                                     ctypes.byref(value), ctypes.sizeof(value))
        return value.value != 0
    except Exception:
        return False


def get_window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(int(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(int(hwnd), buf, length + 1)
    return buf.value


def get_process_name(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


def get_window_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    return int(pid.value)


def is_minimized(hwnd) -> bool:
    return bool(user32.IsIconic(int(hwnd)))


def list_windows(include_hidden: bool = False):
    """Every real top-level application window, for the target picker.

    Filters out zero-size windows, tool windows, cloaked UWP shells and
    untitled ones -- otherwise the picker is 300 rows of invisible junk.

    Minimized windows are KEPT, flagged with minimized=True: Windows parks an
    iconic window at (-32000, -32000) with a stub 160x28 rect, so a plain
    size filter silently drops exactly the case a user hits most (the game is
    minimized while they set the macro up). attach restores it instead.
    """
    results = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        try:
            if not include_hidden and not user32.IsWindowVisible(hwnd):
                return True
            title = get_window_title(hwnd)
            if not title.strip():
                return True
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            if _is_cloaked(hwnd):
                return True

            minimized = is_minimized(hwnd)
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if not minimized and (w < 40 or h < 40):
                return True

            client_w, client_h = get_client_size(hwnd)
            results.append({
                "hwnd": int(hwnd),
                "title": title,
                "process": get_process_name(hwnd),
                "pid": get_window_pid(hwnd),
                "width": 0 if minimized else client_w,
                "height": 0 if minimized else client_h,
                "minimized": minimized,
            })
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    # Minimized last: the picker should surface usable targets first.
    results.sort(key=lambda r: (r["minimized"], r["process"], r["title"].lower()))
    return results


def find_window_by_title(substring: str):
    """First visible window whose title contains substring (case-insensitive)."""
    if not substring:
        return 0
    needle = substring.lower()
    for info in list_windows():
        if needle in info["title"].lower():
            return info["hwnd"]
    return 0


def get_window_rect(hwnd):
    rect = RECT()
    user32.GetWindowRect(int(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def get_client_size(hwnd):
    rect = RECT()
    user32.GetClientRect(int(hwnd), ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def client_to_screen(hwnd, x: int, y: int):
    pt = wintypes.POINT(int(x), int(y))
    user32.ClientToScreen(int(hwnd), ctypes.byref(pt))
    return pt.x, pt.y


def screen_to_client(hwnd, x: int, y: int):
    pt = wintypes.POINT(int(x), int(y))
    user32.ScreenToClient(int(hwnd), ctypes.byref(pt))
    return pt.x, pt.y


def get_client_rect_screen(hwnd):
    """Client area as (left, top, width, height) in screen coordinates --
    the origin every window-relative coordinate is measured from."""
    w, h = get_client_size(hwnd)
    left, top = client_to_screen(hwnd, 0, 0)
    return left, top, w, h


def is_foreground(hwnd) -> bool:
    return user32.GetForegroundWindow() == int(hwnd)


def activate_window(hwnd) -> bool:
    """Focus the window, returning whether it actually worked.

    SetForegroundWindow is refused when the calling thread doesn't own the
    current foreground window, so the fallback attaches our input queue to
    both threads first -- the standard workaround.
    """
    hwnd = int(hwnd)
    user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.SetForegroundWindow(hwnd):
        return True
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    this_thread = kernel32.GetCurrentThreadId()
    attached_fg = user32.AttachThreadInput(this_thread, fg_thread, True)
    attached_target = user32.AttachThreadInput(this_thread, target_thread, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return is_foreground(hwnd)
    finally:
        if attached_fg:
            user32.AttachThreadInput(this_thread, fg_thread, False)
        if attached_target:
            user32.AttachThreadInput(this_thread, target_thread, False)


def bring_to_top(hwnd) -> None:
    user32.SetWindowPos(int(hwnd), HWND_TOP, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def move_window(hwnd, x, y, w, h) -> None:
    user32.MoveWindow(int(hwnd), int(x), int(y), int(w), int(h), True)


def client_size_to_window_size(hwnd, width, height):
    """Outer size needed for a given CLIENT area at hwnd's current style."""
    style = user32.GetWindowLongW(int(hwnd), GWL_STYLE)
    ex_style = user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
    rect = RECT(0, 0, int(width), int(height))
    user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, ex_style)
    return rect.right - rect.left, rect.bottom - rect.top


def resize_client_to(hwnd, width, height) -> None:
    outer_w, outer_h = client_size_to_window_size(hwnd, width, height)
    left, top, _, _ = get_window_rect(hwnd)
    user32.SetWindowPos(int(hwnd), 0, left, top, outer_w, outer_h,
                        0x0004 | SWP_NOACTIVATE)  # SWP_NOZORDER


# --------------------------------------------------------- frameless chrome
#
# A frameless window has no OS border, so Windows never starts its own drag
# or resize loop. Rather than reimplementing those loops in JavaScript (which
# cannot keep up with the pointer and ignores snap, aero-snap and multi-
# monitor edges), we hand the job back to Windows: release the mouse capture
# and post the non-client button-down message it would have received if the
# user had grabbed a real border.

WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

RESIZE_EDGES = {
    "left": HTLEFT, "right": HTRIGHT, "top": HTTOP, "bottom": HTBOTTOM,
    "topleft": HTTOPLEFT, "topright": HTTOPRIGHT,
    "bottomleft": HTBOTTOMLEFT, "bottomright": HTBOTTOMRIGHT,
}


def begin_native_drag(hwnd) -> bool:
    """Start Windows' own move loop, as if the title bar had been grabbed."""
    try:
        user32.ReleaseCapture()
        user32.PostMessageW(int(hwnd), WM_NCLBUTTONDOWN, HTCAPTION, 0)
        return True
    except Exception:
        return False


def begin_native_resize(hwnd, edge: str) -> bool:
    """Start Windows' own resize loop from the named edge or corner."""
    code = RESIZE_EDGES.get(str(edge).lower())
    if code is None:
        return False
    try:
        user32.ReleaseCapture()
        user32.PostMessageW(int(hwnd), WM_NCLBUTTONDOWN, code, 0)
        return True
    except Exception:
        return False


def find_own_window(title: str):
    """Our own top-level window by exact title."""
    for info in list_windows():
        if info["title"] == title:
            return info["hwnd"]
    return 0


def capture_window_rgb(hwnd):
    """PrintWindow capture of the window's own contents.

    Works while the window is covered by another one, which a plain screen
    grab cannot do. Returns (bgra_bytes, w, h) or None on an all-black frame
    (some hardware-accelerated renderers do not answer PrintWindow).
    """
    import numpy as np

    hwnd = int(hwnd)
    w, h = get_client_size(hwnd)
    if w <= 0 or h <= 0:
        return None

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    hdc = user32.GetDC(hwnd)
    if not hdc:
        return None
    mem_dc = bitmap = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old = gdi32.SelectObject(mem_dc, bitmap)
        # A fresh GDI bitmap is NOT zeroed; recycled framebuffer garbage
        # would sail past the all-black check below.
        gdi32.PatBlt(mem_dc, 0, 0, w, h, 0x00000042)  # BLACKNESS
        user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)

        header = _BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        header.biWidth = w
        header.biHeight = -h          # negative == top-down rows
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0      # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(header), 0)
        gdi32.SelectObject(mem_dc, old)

        arr = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4)
        if not arr[:, :, :3].any():
            return None
        return arr[:, :, :3].copy(), w, h
    except Exception:
        return None
    finally:
        try:
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hdc)
        except Exception:
            pass
