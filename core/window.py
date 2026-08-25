"""Win32 window enumeration, geometry and coordinate conversion.

The macro's coordinates are stored relative to the TARGET WINDOW's client
area, not the screen, so a recording still lands correctly after the user
moves or resizes that window. This module owns that translation.
"""
import ctypes
from ctypes import wintypes
import os
import time

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


def restore_if_minimized(hwnd) -> bool:
    """Restore an iconic target before a capture, without changing its size.

    Capturing a minimized window produces an empty or stale frame on many
    renderers.  Do this centrally so blocks, conditions, image tools and
    webhook attachments all get the same behaviour.
    """
    hwnd = int(hwnd or 0)
    if not hwnd or not is_minimized(hwnd):
        return False
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        return True
    except Exception:
        return False


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

    SW_RESTORE is sent ONLY to a window that is actually minimized. Sending it
    unconditionally also UN-MAXIMIZES a maximized window, which is why simply
    focusing a maximized game snapped it back to its small restored size
    (e.g. 800x800). Nothing but the Focus Target block may resize a target.
    """
    hwnd = int(hwnd)
    if user32.IsIconic(hwnd):
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


# Why the first implementation did nothing.
#
# 1. lParam was 0. For WM_NCLBUTTONDOWN the OS move loop reads the grab
#    anchor out of lParam as screen coordinates, so 0 meant "grabbed at the
#    top-left corner of the desktop" -- the window either did not follow the
#    pointer at all or teleported on the first move.
# 2. ReleaseCapture() is per-THREAD. The mousedown happens inside the
#    WebView2 child window, which lives in a different process, so releasing
#    capture on the Python thread released nothing and the modal loop never
#    got a single WM_MOUSEMOVE.
#
# So: attach to the window's input thread before releasing capture, pass the
# real cursor position, and keep a watchdog that drags the window by hand if
# the OS loop still refuses to start.

WM_SYSCOMMAND = 0x0112
WM_CANCELMODE = 0x001F
SC_MOVE = 0xF010
SC_SIZE = 0xF000
GA_ROOT = 2
VK_LBUTTON = 0x01
SWP_NOZORDER = 0x0004

# WM_SYSCOMMAND's own edge numbering, which is NOT the HT* hit-test one.
WMSZ_EDGES = {
    "left": 1, "right": 2, "top": 3, "topleft": 4, "topright": 5,
    "bottom": 6, "bottomleft": 7, "bottomright": 8,
}

# How long to give the OS loop before taking over, and how often the manual
# fallback repositions the window (~125 fps: smooth without burning a core).
_NATIVE_LOOP_GRACE_S = 0.12
_MANUAL_STEP_S = 0.008
_MANUAL_TIMEOUT_S = 60.0


def _root_window(hwnd) -> int:
    """The top-level window: a click arriving from the WebView2 child must
    still move the frame, not the child."""
    try:
        root = user32.GetAncestor(int(hwnd), GA_ROOT)
        return int(root) if root else int(hwnd)
    except Exception:
        return int(hwnd)


def get_cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def _cursor_lparam() -> int:
    x, y = get_cursor_pos()
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def _release_capture_for(hwnd) -> None:
    """Release the mouse capture held by the window's OWN input thread.

    Capture is per-thread, and ours is not the thread holding it -- the
    WebView2 renderer is. AttachThreadInput briefly joins the two input
    queues so ReleaseCapture applies where it matters.
    """
    try:
        target_tid = user32.GetWindowThreadProcessId(int(hwnd), None)
        own_tid = kernel32.GetCurrentThreadId()
        attached = False
        if target_tid and target_tid != own_tid:
            attached = bool(user32.AttachThreadInput(own_tid, target_tid, True))
        try:
            user32.ReleaseCapture()
        finally:
            if attached:
                user32.AttachThreadInput(own_tid, target_tid, False)
    except Exception:
        pass


def _left_button_down() -> bool:
    try:
        return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False


def _watch_and_take_over(hwnd, kind: str, edge: str, min_size) -> None:
    """If the OS move/resize loop never started, do it by hand.

    Checked by geometry rather than by a return value: PostMessage succeeds
    whether or not DefWindowProc ends up running the loop.
    """
    import threading

    before = get_window_rect(hwnd)

    def worker() -> None:
        time.sleep(_NATIVE_LOOP_GRACE_S)
        if not is_window(hwnd) or not _left_button_down():
            return
        if get_window_rect(hwnd) != before:
            return                      # the OS loop is running -- leave it alone
        try:
            user32.PostMessageW(int(hwnd), WM_CANCELMODE, 0, 0)
        except Exception:
            pass
        if kind == "move":
            _manual_move(hwnd)
        else:
            _manual_resize(hwnd, edge, min_size)

    thread = threading.Thread(target=worker, name="frameless-chrome", daemon=True)
    thread.start()


def _manual_move(hwnd) -> None:
    left, top, right, bottom = get_window_rect(hwnd)
    w, h = right - left, bottom - top
    ox, oy = get_cursor_pos()
    deadline = time.perf_counter() + _MANUAL_TIMEOUT_S
    while _left_button_down() and time.perf_counter() < deadline:
        if not is_window(hwnd):
            return
        cx, cy = get_cursor_pos()
        user32.SetWindowPos(int(hwnd), 0, left + (cx - ox), top + (cy - oy), w, h,
                            SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(_MANUAL_STEP_S)


def _manual_resize(hwnd, edge: str, min_size) -> None:
    edge = str(edge).lower()
    min_w, min_h = (int(min_size[0]), int(min_size[1])) if min_size else (240, 160)
    left, top, right, bottom = get_window_rect(hwnd)
    ox, oy = get_cursor_pos()
    deadline = time.perf_counter() + _MANUAL_TIMEOUT_S
    while _left_button_down() and time.perf_counter() < deadline:
        if not is_window(hwnd):
            return
        cx, cy = get_cursor_pos()
        dx, dy = cx - ox, cy - oy
        new_left, new_top = left, top
        new_right, new_bottom = right, bottom
        if "left" in edge:
            new_left = min(left + dx, right - min_w)
        if "right" in edge:
            new_right = max(right + dx, left + min_w)
        if "top" in edge:
            new_top = min(top + dy, bottom - min_h)
        if "bottom" in edge:
            new_bottom = max(bottom + dy, top + min_h)
        user32.SetWindowPos(int(hwnd), 0, new_left, new_top,
                            new_right - new_left, new_bottom - new_top,
                            SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(_MANUAL_STEP_S)


def begin_native_drag(hwnd, min_size=None) -> bool:
    """Start Windows' own move loop, as if the title bar had been grabbed."""
    hwnd = _root_window(hwnd)
    if not hwnd or not is_window(hwnd):
        return False
    try:
        _release_capture_for(hwnd)
        lparam = _cursor_lparam()
        # SC_MOVE|HTCAPTION is the same loop a real title bar grab starts,
        # and unlike a bare WM_NCLBUTTONDOWN it also works when the click
        # was consumed by a child window of another process.
        user32.PostMessageW(int(hwnd), WM_SYSCOMMAND, SC_MOVE | HTCAPTION, lparam)
        user32.PostMessageW(int(hwnd), WM_NCLBUTTONDOWN, HTCAPTION, lparam)
        _watch_and_take_over(hwnd, "move", "", min_size)
        return True
    except Exception:
        return False


def begin_native_resize(hwnd, edge: str, min_size=None) -> bool:
    """Start Windows' own resize loop from the named edge or corner."""
    edge = str(edge).lower()
    code = RESIZE_EDGES.get(edge)
    wmsz = WMSZ_EDGES.get(edge)
    if code is None or wmsz is None:
        return False
    hwnd = _root_window(hwnd)
    if not hwnd or not is_window(hwnd):
        return False
    try:
        _release_capture_for(hwnd)
        lparam = _cursor_lparam()
        user32.PostMessageW(int(hwnd), WM_SYSCOMMAND, SC_SIZE + wmsz, lparam)
        user32.PostMessageW(int(hwnd), WM_NCLBUTTONDOWN, code, lparam)
        _watch_and_take_over(hwnd, "resize", edge, min_size)
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
    """PrintWindow capture of the window's CLIENT area.

    PrintWindow always paints the WHOLE window -- border and title bar
    included -- starting at the DC's origin, so a client-sized bitmap came
    back holding the top-left corner of the *outer* window: the picture was
    shifted down by the title bar height and cut off at the bottom. Every
    coordinate in a macro is measured against the client area, so a spot
    picked on such a picture was replayed exactly that many pixels too low.
    The bitmap is therefore window-sized and the client rectangle is cropped
    out of it afterwards.

    Works while the window is covered by another one, which a plain screen
    grab cannot do. Returns (bgr_bytes, client_w, client_h) or None on an
    all-black frame (some hardware-accelerated renderers do not answer
    PrintWindow).
    """
    import numpy as np

    hwnd = int(hwnd)
    client_w, client_h = get_client_size(hwnd)
    if client_w <= 0 or client_h <= 0:
        return None

    # Where the client area sits inside the window, in window pixels. If the
    # numbers do not add up (they can be odd for a maximized or DPI-scaled
    # window) fall back to the old client-sized bitmap rather than crop blind.
    w, h = client_w, client_h
    off_x = off_y = 0
    try:
        left, top, right, bottom = get_window_rect(hwnd)
        cs_x, cs_y = client_to_screen(hwnd, 0, 0)
        outer_w, outer_h = right - left, bottom - top
        dx, dy = cs_x - left, cs_y - top
        if (dx >= 0 and dy >= 0 and outer_w >= client_w + dx
                and outer_h >= client_h + dy):
            w, h, off_x, off_y = outer_w, outer_h, dx, dy
    except Exception:
        pass

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
        frame = arr[off_y:off_y + client_h, off_x:off_x + client_w, :3]
        if frame.shape[0] != client_h or frame.shape[1] != client_w:
            # Should not happen after the bounds check above; returning the
            # whole bitmap beats returning a silently mis-sized crop.
            frame = arr[:, :, :3]
            client_w, client_h = w, h
        if not frame.any():
            return None
        return frame.copy(), client_w, client_h
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
