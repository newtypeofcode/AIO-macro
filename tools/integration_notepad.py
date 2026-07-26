"""End-to-end: drive a real app (Notepad) with the real input stack and read
the result back out of it. Verifies SendInput, window targeting, client->screen
coordinate conversion, the runner, and the recorder round-trip -- for real,
not with mocks."""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core import blocks, capture, recorder, window as wm
from core.runner import MacroRunner

wm.set_dpi_aware()
user32 = wm.user32
fails = []


def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + ((" -- " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def find_edit_child(hwnd):
    """Notepad's text area is a child control; classic Notepad uses Edit,
    Win11 Notepad uses RichEditD2DPT."""
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(child, _l):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(child, buf, 256)
        if buf.value in ("Edit", "RichEditD2DPT", "RICHEDIT50W"):
            found.append(child)
        return True

    user32.EnumChildWindows(hwnd, PROC(cb), 0)
    return found[0] if found else 0


def read_edit_text(edit_hwnd):
    WM_GETTEXTLENGTH, WM_GETTEXT = 0x000E, 0x000D
    length = user32.SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(edit_hwnd, WM_GETTEXT, length + 1, buf)
    return buf.value


print("== launch notepad ==")
proc = subprocess.Popen(["notepad.exe"])
notepad = 0
for _ in range(40):
    time.sleep(0.25)
    for info in wm.list_windows():
        if info["process"] == "notepad.exe" and info["pid"] == proc.pid:
            notepad = info["hwnd"]
            break
    if notepad:
        break
check("notepad window found", bool(notepad), notepad)
if not notepad:
    proc.terminate()
    sys.exit(1)

wm.move_window(notepad, 120, 120, 900, 620)
time.sleep(0.5)
wm.activate_window(notepad)
time.sleep(0.6)

edit = find_edit_child(notepad)
check("notepad edit control found", bool(edit), edit)

cw, ch = wm.get_client_size(notepad)
print("  notepad client area: %dx%d" % (cw, ch))

runner = MacroRunner(log=lambda m: print("    [run]", m), set_status=lambda **k: None)


def run(macro, timeout=25):
    runner.start(macro, hwnd=notepad, coord_space="window",
                 loop_forever=False, loop_count=1)
    deadline = time.time() + timeout
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.1)
    return not runner.is_running()


print("== test 1: click into the text area, then type ==")
macro1 = {"phases": {"setup": [
    blocks.make_block("focus_window", "f", {}),
    blocks.make_block("wait_ms", "w0", {"ms": 400}),
    blocks.make_block("click", "c1", {"x": cw // 2, "y": ch // 2}),
    blocks.make_block("wait_ms", "w1", {"ms": 250}),
    blocks.make_block("type_text", "t1", {"text": "hello macro", "delay_ms": 25}),
], "loop": []}}
check("macro 1 completed", run(macro1))
time.sleep(0.6)
text = read_edit_text(edit)
check("typed text landed in notepad", "hello macro" in text, repr(text))

print("== test 2: send_key with a modifier (ctrl+a) then Delete ==")
macro2 = {"phases": {"setup": [
    blocks.make_block("send_key", "k1", {"key": "a", "modifiers": ["ctrl"], "hold_ms": 60}),
    blocks.make_block("wait_ms", "w", {"ms": 250}),
    blocks.make_block("send_key", "k2", {"key": "delete", "hold_ms": 40}),
    blocks.make_block("wait_ms", "w2", {"ms": 250}),
], "loop": []}}
check("macro 2 completed", run(macro2))
time.sleep(0.5)
check("ctrl+a then delete cleared the text", read_edit_text(edit).strip() == "",
      repr(read_edit_text(edit)))

print("== test 3: loop block types repeatedly ==")
macro3 = {"phases": {"setup": [], "loop": [
    blocks.make_block("type_text", "t", {"text": "ab", "delay_ms": 15}),
    blocks.make_block("wait_ms", "w", {"ms": 120}),
]}}
runner.start(macro3, hwnd=notepad, coord_space="window", loop_forever=False, loop_count=4)
deadline = time.time() + 20
while runner.is_running() and time.time() < deadline:
    time.sleep(0.1)
check("macro 3 completed", not runner.is_running())
time.sleep(0.5)
got = read_edit_text(edit)
check("loop ran exactly 4 times", got.strip() == "abababab", repr(got))

print("== test 4: hold_key releases on Stop ==")
from core import keys as keymod
macro4 = {"phases": {"setup": [], "loop": [
    blocks.make_block("hold_key", "h", {"key": "shift", "hold_ms": 8000}),
]}}
runner.start(macro4, hwnd=notepad, coord_space="window", loop_forever=True)
time.sleep(1.2)
held_during = runner.keyboard.is_down(keymod.VK_SHIFT)
runner.stop()
for _ in range(40):
    if not runner.is_running():
        break
    time.sleep(0.1)
time.sleep(0.4)
held_after = runner.keyboard.is_down(keymod.VK_SHIFT)
check("shift was actually held during the block", held_during)
check("shift released after Stop", not held_after)

print("== test 5: vision -- capture notepad, crop a template, find it again ==")
import cv2
import os
from core import vision, constants
frame = capture.capture_target_bgr(notepad)
check("captured notepad", frame is not None and frame.any(),
      None if frame is None else frame.shape)
if frame is not None:
    fh, fw = frame.shape[:2]
    # A crop from the middle of the text area, where "abababab" was typed.
    cx0, cy0 = 20, 20
    crop = frame[cy0:cy0 + 40, cx0:cx0 + 120].copy()
    folder = os.path.join(constants.ASSETS_DIR, "__e2e")
    os.makedirs(folder, exist_ok=True)
    cv2.imwrite(os.path.join(folder, "__e2e.png"), crop)
    vision.clear_cache()
    match = vision.find_image(notepad, "__e2e")
    check("template found in the live window", match is not None,
          None if match is None else round(match["score"], 3))
    if match:
        check("template located at the right spot",
              abs(match["x"] - cx0) <= 3 and abs(match["y"] - cy0) <= 3,
              (match["x"], match["y"]))
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    vision.clear_cache()

print("== test 6: coordinate conversion is exact ==")
left, top, w, h = wm.get_client_rect_screen(notepad)
sx, sy = wm.client_to_screen(notepad, 100, 50)
check("client->screen matches client rect origin", (sx, sy) == (left + 100, top + 50),
      (sx, sy, left + 100, top + 50))
back = wm.screen_to_client(notepad, sx, sy)
check("screen->client round-trips", back == (100, 50), back)

print("== test 7: recorded events replay verbatim ==")
from core import templates as tpl
from core.keyboard import Keyboard as _KB

clear_macro = {"phases": {"setup": [
    blocks.make_block("send_key", "sa", {"key": "a", "modifiers": ["ctrl"]}),
    blocks.make_block("send_key", "sd", {"key": "delete"}),
    blocks.make_block("wait_ms", "w", {"ms": 200}),
], "loop": []}}

# Baseline: what the PHYSICAL H and I keys produce under whatever keyboard
# layout is currently active. Asserting a literal "hi" would make this test
# pass only on a Latin layout -- physical-key replay is layout-independent
# by design, so the expected output has to be measured, not assumed.
run(clear_macro)
time.sleep(0.3)
_kb = _KB()
for _name in ("h", "i"):
    _kb.tap(keymod.key_name_to_vk(_name), hold=0.04)
    time.sleep(0.15)
time.sleep(0.4)
expected = read_edit_text(edit).strip()
print("  physical H,I produce %r under the active layout" % expected)
check("baseline typed two characters", len(expected) == 2, repr(expected))

events = [
    {"t": 0.0, "type": "key_down", "key": "h", "vk": 0x48},
    {"t": 0.05, "type": "key_up", "key": "h", "vk": 0x48},
    {"t": 0.15, "type": "key_down", "key": "i", "vk": 0x49},
    {"t": 0.20, "type": "key_up", "key": "i", "vk": 0x49},
]
tpl.save_recording("__e2e_rec", events)
macro7 = {"phases": {"setup": [
    blocks.make_block("send_key", "sa", {"key": "a", "modifiers": ["ctrl"]}),
    blocks.make_block("send_key", "sd", {"key": "delete"}),
    blocks.make_block("wait_ms", "w", {"ms": 200}),
    blocks.make_block("playback", "p", {"recording": "__e2e_rec", "speed": 1.0}),
], "loop": []}}
check("macro 7 completed", run(macro7))
time.sleep(0.5)
check("playback reproduced the physical keys",
      read_edit_text(edit).strip() == expected,
      "%r vs %r" % (read_edit_text(edit).strip(), expected))

# A recording without vk codes must still work via the name fallback.
run(clear_macro)
time.sleep(0.3)
tpl.save_recording("__e2e_rec2", [
    {"t": 0.0, "type": "key_down", "key": "h"}, {"t": 0.05, "type": "key_up", "key": "h"},
    {"t": 0.15, "type": "key_down", "key": "i"}, {"t": 0.20, "type": "key_up", "key": "i"},
])
macro7b = {"phases": {"setup": [
    blocks.make_block("playback", "p", {"recording": "__e2e_rec2", "speed": 1.0}),
], "loop": []}}
check("macro 7b completed", run(macro7b))
time.sleep(0.5)
check("name-only recording falls back correctly",
      read_edit_text(edit).strip() == expected,
      "%r vs %r" % (read_edit_text(edit).strip(), expected))
tpl.delete_recording("__e2e_rec")
tpl.delete_recording("__e2e_rec2")

print("== test 8: type_text is layout-independent (unicode injection) ==")
run(clear_macro)
time.sleep(0.3)
macro8 = {"phases": {"setup": [
    blocks.make_block("type_text", "t", {"text": "Hi-42 Привет", "delay_ms": 15}),
], "loop": []}}
check("macro 8 completed", run(macro8))
time.sleep(0.6)
check("type_text produced the literal text regardless of layout",
      read_edit_text(edit).strip() == "Hi-42 Привет",
      repr(read_edit_text(edit)))

print("== cleanup ==")
macro_clear = {"phases": {"setup": [
    blocks.make_block("send_key", "sa", {"key": "a", "modifiers": ["ctrl"]}),
    blocks.make_block("send_key", "sd", {"key": "delete"}),
], "loop": []}}
run(macro_clear)
time.sleep(0.4)
try:
    user32.PostMessageW(notepad, 0x0010, 0, 0)  # WM_CLOSE
    time.sleep(0.8)
    proc.terminate()
except Exception:
    pass
capture.close_all_mss()

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
