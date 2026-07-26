"""End-to-end recorder test: synthesize REAL input through SendInput, let the
pynput hooks capture it, convert to blocks, then replay those blocks into
Notepad and check the text that comes out.

This is the round trip the whole app exists for: record -> edit -> replay.
"""
import ctypes
import subprocess
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core import blocks, recorder, window as wm, keys as keymod
from core.keyboard import Keyboard
from core.mouse import Mouse
from core.runner import MacroRunner

wm.set_dpi_aware()
user32 = wm.user32
fails = []


def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + ((" -- " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def find_edit_child(hwnd):
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
    length = user32.SendMessageW(edit_hwnd, 0x000E, 0, 0)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(edit_hwnd, 0x000D, length + 1, buf)
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
check("notepad found", bool(notepad))
if not notepad:
    sys.exit(1)

wm.move_window(notepad, 150, 150, 900, 600)
time.sleep(0.4)
wm.activate_window(notepad)
time.sleep(0.6)
edit = find_edit_child(notepad)
cw, ch = wm.get_client_size(notepad)

print("== record real synthesized input ==")
rec = recorder.Recorder(log=print)
started = rec.start(hwnd=notepad, record_moves=True, move_interval_ms=40)
check("recorder started", started)
time.sleep(0.5)

mouse, kb = Mouse(), Keyboard()
# A click in the middle of the text area, then type "abc", then a pause,
# then a second click elsewhere. All through the real input stack.
mid = wm.client_to_screen(notepad, cw // 2, ch // 2)
mouse.click(mid[0], mid[1])
time.sleep(0.35)
for ch_name in "abc":
    kb.tap(keymod.key_name_to_vk(ch_name), hold=0.04)
    time.sleep(0.12)
time.sleep(0.7)
corner = wm.client_to_screen(notepad, 60, 40)
mouse.click(corner[0], corner[1])
time.sleep(0.4)

events = rec.stop()
# What the ORIGINAL typing produced, whatever the active layout turns the
# physical A/B/C keys into. Replay must reproduce exactly this.
typed_during_recording = read_edit_text(edit)
print("  original typing produced: %r" % typed_during_recording)
check("events captured", len(events) > 8, len(events))
check("recorder inactive after stop", not rec.active)
check("recording actually typed something", typed_during_recording.strip() != "")

kinds = {}
for ev in events:
    kinds[ev["type"]] = kinds.get(ev["type"], 0) + 1
print("  event kinds:", kinds)
check("mouse_down captured", kinds.get("mouse_down", 0) >= 2, kinds)
check("key_down captured", kinds.get("key_down", 0) >= 3, kinds)
check("timestamps start at 0", abs(events[0]["t"]) < 0.001, events[0]["t"])
check("timestamps ascend", all(events[i]["t"] <= events[i + 1]["t"]
                               for i in range(len(events) - 1)))

print("== convert to blocks ==")
converted = recorder.compress_text_blocks(
    recorder.events_to_blocks(events, "window", 60, False))
types = [b["type"] for b in converted]
print("  blocks:", types)
check("clicks converted", types.count("click") >= 2, types)
check("keys present (as send_key or type_text)",
      ("send_key" in types) or ("type_text" in types), types)
check("waits inserted for the real pauses", "wait_ms" in types, types)

click_blocks = [b for b in converted if b["type"] == "click"]
if click_blocks:
    first = click_blocks[0]["params"]
    check("first click coords ~ window centre",
          abs(first["x"] - cw // 2) <= 3 and abs(first["y"] - ch // 2) <= 3,
          (first["x"], first["y"], cw // 2, ch // 2))
if len(click_blocks) >= 2:
    second = click_blocks[-1]["params"]
    check("second click coords ~ (60,40)",
          abs(second["x"] - 60) <= 3 and abs(second["y"] - 40) <= 3,
          (second["x"], second["y"]))

total_wait = sum(b["params"]["ms"] for b in converted if b["type"] == "wait_ms")
check("total inserted wait is in a sane range (0.5s-4s)",
      500 <= total_wait <= 4000, "%dms" % total_wait)

print("== replay the converted blocks ==")
runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)
clear = {"phases": {"setup": [
    blocks.make_block("send_key", "a", {"key": "a", "modifiers": ["ctrl"]}),
    blocks.make_block("send_key", "d", {"key": "delete"}),
], "loop": []}}
runner.start(clear, hwnd=notepad, coord_space="window", loop_forever=False, loop_count=1)
while runner.is_running():
    time.sleep(0.1)
time.sleep(0.4)

replay = {"phases": {"setup": blocks.normalize_list(converted), "loop": []}}
runner.start(replay, hwnd=notepad, coord_space="window", loop_forever=False, loop_count=1)
deadline = time.time() + 30
while runner.is_running() and time.time() < deadline:
    time.sleep(0.1)
check("replay completed", not runner.is_running())
time.sleep(0.6)
got = read_edit_text(edit)
# Physical-key replay: the output must match what the ORIGINAL key presses
# produced under the active layout, not a hardcoded Latin string.
check("replay reproduced the original output",
      got.strip() == typed_during_recording.strip(),
      "replayed %r vs recorded %r" % (got, typed_during_recording))

print("== layout independence: physical keys, not layout characters ==")
key_events = [e for e in events if e["type"] == "key_down"]
names = [e["key"] for e in key_events]
vks = [e.get("vk") for e in key_events]
chars = [e.get("char") for e in key_events]
print("  names=%s vks=%s chars=%s" % (names, vks, chars))
check("recorded names are the physical keys (a,b,c)", names == ["a", "b", "c"], names)
check("vk codes captured", vks == [0x41, 0x42, 0x43], vks)
check("layout characters kept separately for text folding",
      all(c for c in chars), chars)
check("names differ from layout chars (non-Latin layout active)"
      if chars and chars[0] not in ("a", "b", "c") else
      "names match chars (Latin layout active)", True)

print("== save / load round trip ==")
from core import templates as tpl
tpl.save_recording("__rec_e2e", events)
loaded = tpl.load_recording("__rec_e2e")
check("recording round-trips", len(loaded["events"]) == len(events),
      (len(loaded["events"]), len(events)))
check("listed", "__rec_e2e" in tpl.list_recordings())
tpl.delete_recording("__rec_e2e")
check("deleted", "__rec_e2e" not in tpl.list_recordings())

print("== hotkey suppression ==")
rec2 = recorder.Recorder(log=lambda m: None)
rec2.suppress(["f2", "f4"])
rec2.start(hwnd=notepad, record_moves=False)
time.sleep(0.4)
kb.tap(keymod.key_name_to_vk("f2"), hold=0.04)
time.sleep(0.2)
kb.tap(keymod.key_name_to_vk("z"), hold=0.04)
time.sleep(0.3)
ev2 = rec2.stop()
recorded_keys = {e.get("key") for e in ev2 if e["type"] in ("key_down", "key_up")}
check("suppressed hotkey not recorded", "f2" not in recorded_keys, recorded_keys)
check("normal key still recorded", "z" in recorded_keys, recorded_keys)

print("== cleanup ==")
runner.start(clear, hwnd=notepad, coord_space="window", loop_forever=False, loop_count=1)
while runner.is_running():
    time.sleep(0.1)
time.sleep(0.3)
user32.PostMessageW(notepad, 0x0010, 0, 0)
time.sleep(0.8)
try:
    proc.terminate()
except Exception:
    pass

from core import capture
capture.close_all_mss()
print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
