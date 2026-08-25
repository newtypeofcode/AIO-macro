"""Restarting Roblox and rejoining a server.

Roblox has no "reconnect" of its own. What does work -- and what every
hand-rolled rejoin script ends up doing -- is the launcher's deep link:
hand the client a place id (plus the private server's linkCode when there is
one) and it drops you straight into that server.

Two details make or break it:

* The running client has to be gone first. A live RobloxPlayerBeta swallows
  the deep link and stays exactly where it is, so the macro would sit there
  waiting for a join that never happens.
* The client's own exe path is the most reliable thing to launch. Its folder
  changes with every Roblox update, so it is read from the running process
  while it is still alive, and only guessed from the Versions folder when
  nothing is running.

Everything Windows-only is bound lazily, so importing this module on another
platform (tests) is harmless.
"""
import ctypes
import os
import subprocess
import sys
import time

PLAYER_EXE = "robloxplayerbeta.exe"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000

_bound = None


def available() -> bool:
    return sys.platform == "win32"


def _bind():
    """ctypes handles for Psapi/kernel32, bound once. None off Windows."""
    global _bound
    if _bound is not None:
        return _bound or None
    if not available():
        _bound = False
        return None
    try:
        from ctypes import wintypes
        psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

        psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD),
                                       wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD)]
        psapi.EnumProcesses.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        _bound = {"psapi": psapi, "kernel32": kernel32, "wintypes": wintypes}
    except Exception:
        _bound = False
        return None
    return _bound


def process_path(pid: int) -> str:
    """Full exe path of a pid, or "" when it cannot be read.

    QUERY_LIMITED_INFORMATION rather than QUERY_INFORMATION: the limited
    right is enough for the image name and is granted for processes this one
    could not otherwise open.
    """
    api = _bind()
    if not api or not pid:
        return ""
    kernel32 = api["kernel32"]
    wintypes = api["wintypes"]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                  int(pid))
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                               ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_player_pids() -> list:
    """Every running RobloxPlayerBeta pid."""
    api = _bind()
    if not api:
        return []
    psapi = api["psapi"]
    wintypes = api["wintypes"]
    # Grown until it fits: a fixed 4096 silently truncates the list on a busy
    # box, and the one process that got cut is the one being looked for.
    capacity = 4096
    for _ in range(4):
        arr = (wintypes.DWORD * capacity)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(arr, ctypes.sizeof(arr),
                                   ctypes.byref(needed)):
            return []
        if needed.value < ctypes.sizeof(arr):
            count = needed.value // ctypes.sizeof(wintypes.DWORD)
            break
        capacity *= 2
    else:
        return []

    found = []
    for pid in arr[:count]:
        path = process_path(pid)
        if path and os.path.basename(path).lower() == PLAYER_EXE:
            found.append(int(pid))
    return found


def _versions_dirs() -> list:
    roots = []
    for var in ("LOCALAPPDATA", "PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(var, "").strip()
        if base:
            roots.append(os.path.join(base, "Roblox", "Versions"))
    return roots


def player_exe(hint: str = "") -> str:
    """Where RobloxPlayerBeta.exe lives.

    A running client is asked first -- that is the exact build the user is on.
    Failing that the newest folder under Roblox\\Versions wins, because an
    update leaves the old versions behind and launching one of those either
    fails or triggers a full re-download.
    """
    hint = str(hint or "").strip().strip('"')
    if hint and os.path.isfile(hint):
        return hint
    for pid in list_player_pids():
        path = process_path(pid)
        if path and os.path.isfile(path):
            return path
    best, best_time = "", -1.0
    for root in _versions_dirs():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            candidate = os.path.join(root, name, "RobloxPlayerBeta.exe")
            if not os.path.isfile(candidate):
                continue
            try:
                stamp = os.path.getmtime(candidate)
            except OSError:
                stamp = 0.0
            if stamp > best_time:
                best, best_time = candidate, stamp
    return best


def close_players(timeout: float = 6.0) -> int:
    """Kill every running client, and wait until they are actually gone.

    Terminated rather than asked politely: a client showing a modal ("you
    have been kicked", a purchase prompt) ignores WM_CLOSE, and the deep link
    that follows would be swallowed by the process still holding the
    protocol.
    """
    api = _bind()
    if not api:
        return 0
    kernel32 = api["kernel32"]
    pids = list_player_pids()
    for pid in pids:
        handle = kernel32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False,
                                     int(pid))
        if not handle:
            continue
        try:
            kernel32.TerminateProcess(handle, 0)
        finally:
            kernel32.CloseHandle(handle)

    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if not list_player_pids():
            break
        time.sleep(0.2)
    return len(pids)


def _digits(text: str) -> str:
    return "".join(c for c in str(text or "") if c.isdigit())


def parse_place_id(value: str) -> str:
    """Place id out of whatever the user pasted.

    A share link, a deep link or the bare number all end up here, because
    "copy the link" is what people actually do.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    low = text.lower()
    for marker in ("placeid=", "/games/", "placeid%3d"):
        at = low.find(marker)
        if at >= 0:
            tail = text[at + len(marker):]
            got = ""
            for ch in tail:
                if ch.isdigit():
                    got += ch
                elif got:
                    break
            if got:
                return got
    return _digits(text)


def parse_link_code(value: str) -> str:
    """linkCode out of a private-server link, or the code itself.

    The code is not numeric and can hold - and _, so it is taken verbatim
    once found; only surrounding URL punctuation is trimmed.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    low = text.lower()
    for marker in ("linkcode=", "privateserverlinkcode=", "linkcode%3d"):
        at = low.find(marker)
        if at >= 0:
            tail = text[at + len(marker):]
            got = ""
            for ch in tail:
                if ch in "&/? \t\"'":
                    break
                got += ch
            if got:
                return got
    if "://" in low or "/" in text:
        # A link with no linkCode at all is a public game, not a code.
        return ""
    return text


def parse_share_code(value: str) -> str:
    """The code out of a roblox.com/share link, or the bare code itself.

    A share link carries no place id and no linkCode -- the code stands for
    the whole invite, and only Roblox can turn it back into a server. So the
    code is passed straight to the client instead of being resolved here:
    that needs no API call, no logged-in cookie, and nothing that breaks when
    Roblox moves the endpoint.

    Game links and private-server links are deliberately refused: those two
    already have a place id and a linkCode, and reading them as share codes
    would send the client somewhere it cannot go.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    low = text.lower()
    looks_like_link = ("://" in low or "/" in text or "?" in text)
    if looks_like_link and "share" not in low:
        return ""

    for marker in ("code=", "code%3d"):
        at = low.find(marker)
        if at >= 0:
            tail = text[at + len(marker):]
            got = ""
            for ch in tail:
                if ch in "&/? \t\"'":
                    break
                got += ch
            return got
    if looks_like_link:
        return ""

    # A bare code pasted on its own. Share codes are long hex strings, so the
    # length floor is what keeps a place id from being read as one.
    if len(text) >= 16 and all(ch.isalnum() or ch in "-_" for ch in text):
        return text
    return ""


def share_uri(code: str, kind: str = "Server") -> str:
    """The deep link that opens a share code in the client, or "".

    Exactly the link the Roblox website hands to the protocol handler when you
    click a share link in a browser, so the client resolves the invite itself.
    """
    got = parse_share_code(code)
    if not got:
        return ""
    return "roblox://navigation/share_links?code=%s&type=%s" % (got, kind or "Server")


def join_uri(place_id: str, link_code: str = "") -> str:
    """The roblox:// deep link that joins the server, or "" without a place."""
    place = parse_place_id(place_id)
    if not place:
        return ""
    code = parse_link_code(link_code)
    uri = "roblox://placeId=%s" % place
    if code:
        uri += "&linkCode=%s" % code
    return uri


def launch(uri: str, exe: str = "") -> bool:
    """Hand the deep link to the client.

    The exe is preferred over the shell: os.startfile goes through the
    protocol handler, which on a machine with a broken registration (very
    common after moving Roblox between accounts) opens a browser page instead
    of the game.
    """
    if not uri:
        return False
    if exe and os.path.isfile(exe):
        try:
            subprocess.Popen([exe, uri], close_fds=True)
            return True
        except Exception:
            pass
    try:
        os.startfile(uri)  # noqa: E1101 -- Windows only, guarded by caller
        return True
    except Exception:
        return False


def find_player_window(min_client: int = 200):
    """hwnd of a usable Roblox client window, or 0.

    "Usable" matters: the launcher's splash and the tiny bootstrap window
    both carry Roblox in the title and appear seconds before the game does,
    so a size floor keeps the macro from targeting the splash and then
    clicking into nothing.
    """
    from . import window as wm

    best, best_area = 0, -1
    for info in wm.list_windows():
        hwnd = int(info.get("hwnd") or 0)
        if not hwnd:
            continue
        process = str(info.get("process") or "").lower()
        title = str(info.get("title") or "")
        if process != PLAYER_EXE and "roblox" not in title.lower():
            continue
        try:
            width, height = wm.get_client_size(hwnd)
        except Exception:
            continue
        if width < min_client or height < min_client:
            continue
        area = width * height
        if area > best_area:
            best, best_area = hwnd, area
    return best


def wait_for_window(timeout: float = 60.0, poll: float = 1.0,
                    should_stop=None, min_client: int = 200):
    """Poll until the game window is up. Returns the hwnd, or 0 on timeout.

    `should_stop` is called between polls so Stop lands during the minute
    this can take, instead of only after it.
    """
    deadline = time.time() + max(0.0, timeout)
    while True:
        hwnd = find_player_window(min_client)
        if hwnd:
            return hwnd
        if time.time() >= deadline:
            return 0
        if should_stop is not None and should_stop():
            return 0
        time.sleep(max(0.05, poll))
