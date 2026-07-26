# Macro Studio

Block-based macro builder for Windows with action recording, computer vision and OCR.

Record your mouse and keyboard, get editable blocks, add waits for an image, a colour or a piece of text, and run it against any window.

No injection, no memory reading — synthetic input through `SendInput` plus screen analysis.

## Quick start

```bash
pip install -r requirements.txt
python main.py
```

Or double-click `run.bat`. Headless diagnostics: `python main.py --test`.

Needs **Windows 10/11**, **Python 3.10+** and the **WebView2 runtime** (already present on most systems). Tesseract is *not* required — Win10/11 use the built-in `Windows.Media.Ocr`, roughly ten times faster; Tesseract is only a fallback.

## How it works

```
Record      pynput hooks capture real input regardless of focus
   ↓
Events      [{t, type, key/button, x, y, vk, char}, ...]
   ↓
Convert     paired down/up → click; down-move-up → drag;
            gaps → wait; a run of characters → type text
   ↓
Blocks      edit them in the UI
   ↓
Run         SendInput scancodes + cv2.matchTemplate + OCR
```

Coordinates are stored **relative to the target window's client area**, so a macro survives the window being moved or resized. In whole-screen mode they are absolute.

**Layout independence.** The recorder stores the *physical key*, not the character. Pressing `A` on a Cyrillic layout gives `key="a"`, `vk=65`, `char="ф"` — the physical key is what replays; the character is only used to fold a run of keystrokes into one Type Text block. Type Text itself injects Unicode, so it types the same string under any layout.

## Blocks

| Group | Blocks |
|---|---|
| **Mouse** | Click · Move Mouse · Drag · Scroll |
| **Keyboard** | Send Key · Type Text · Hold Key |
| **Timing** | Wait (ms) · Wait Random |
| **Vision** | Wait for Image · Click Image · Wait Image Gone · Wait for Color · Click Color · Wait for Text · Click Text · Read Text |
| **Flow** | Loop Start / Loop End · Play Recording · Focus Target · Log Message |
| **Notify** | Send Webhook |

Every block has **ONCE** (skip on later loop passes), **▶** (run just this block) and an enable/disable toggle. Hover anything for an explanation.

**Confidence** on the image, text and colour blocks is one 0–1 scale. For text a literal substring always counts as found; the threshold only gates fuzzy matching, because OCR routinely confuses a Latin `C` with a Cyrillic `С`.

**On fail** decides what a Vision block does when it finds nothing: `continue`, `run blocks` (a nested fallback sequence with its own "then" — resume, restart the phase, restart the macro, or stop), `restart phase`, `skip rest` or `stop`.

## Two phases

**Setup** runs once. **Loop** repeats until you press Stop, or for a set number of passes.

## Screens

**Build** — palette on the left, the two phases on the right; drag to add and reorder.

**Record** — start/stop with a live event counter. Stopping shows the converted blocks; insert them into a phase as one `Play Recording` block (with an editor for the actions inside) or as separate rows. Saved recordings can be edited, inserted, played on the spot or deleted.

**Images** — capture the target, drag a rectangle, save it under a name. One name can hold several variants; all are tried when searching. Zoom 25–800 % with `−`/`+`/`Fit`; plain wheel scrolls, ctrl+wheel zooms, middle-drag pans. Crop coordinates always stay in source-image pixels.

**Setup** — target window, hotkeys, theme, language, action delay, Discord webhook, health check.

## Hotkeys

| Key | |
|---|---|
| F1 | Start |
| **F2** | **Stop** |
| F3 | Pause / resume |
| F4 | Toggle recording |
| F8 | Pick a coordinate by clicking |

F2 is bound straight to Python rather than routed through the UI, so Stop wins over anything in flight.

## Sharing

**Export with images and recordings** writes a `.macrozip` holding the macro plus exactly the images and recordings it references — nothing else of yours. Import unpacks it, refusing anything that tries to write outside the Assets and Recordings folders, and keeps your existing files unless you ask it to replace them.

## Data

Everything lives next to `main.py` (or the exe): `settings.json`, `debug.log`, `Templates/`, `Recordings/`, `Assets/`, `debug/`. None of it is tracked by git. `Assets/` is deliberately not bundled into the exe so the reference images stay editable.

## Tests

```bash
python -m pytest tests/ -q        # 301 tests, no GUI, no synthetic input
python tools/check_contract.py    # catalog ↔ runner ↔ API ↔ DOM
```

Integration scripts drive a real Notepad and read the text back through `WM_GETTEXT`. They take over the mouse and keyboard while running:

```bash
python tools/integration_notepad.py
python tools/integration_recorder.py
```

## Notable details

Each of these is a fix for a specific way things silently broke.

- **`SendInput`, not `SetCursorPos`/pyautogui** — it goes through the real input stack, which is what games listen to. Keys go as scancodes, like a real driver.
- **`MOUSEEVENTF_VIRTUALDESK` is mandatory** on absolute moves: without it Windows maps the 0–65535 range onto the primary monitor only, and multi-monitor clicks land silently in the wrong place.
- **`ord()` only for A–Z and 0–9.** As a general fallback it mapped punctuation onto navigation keys — `!` is `0x21`, which is Page Up. Everything else resolves through the active layout.
- **1 ms timer resolution.** Windows' default granularity is 15.6 ms, so `sleep(0.001)` really sleeps ~15 ms and a finely sampled recording replays visibly late. Playback also schedules against one absolute start time, so an overshoot never accumulates.
- **Raw mouse deltas via `WM_INPUT`.** When a game captures the cursor to turn the camera the pointer does not move, so position-based recording sees nothing happen. The hardware still reports deltas.
- **Self-echo suppression.** Everything the app injects comes back through the same hooks; without filtering, recording while a macro plays captures the macro's own output.
- **`result[~np.isfinite(result)] = -1`** after `matchTemplate`: the normalised method divides by local variance, so a flat patch yields `inf`, which passes any threshold as a confident match.
- **`PatBlt(BLACKNESS)` before `PrintWindow`** — a fresh GDI bitmap is not zeroed, and recycled framebuffer garbage would pass the "is the frame black?" check.
- **Window contents before screen grab.** A screen grab of an occluded window returns the *covering* window's pixels, which no black-frame check can detect.
- **`imread_unicode` / `imwrite_unicode`.** OpenCV passes filenames to the C runtime as bytes, so `cv2.imwrite` with a Cyrillic name writes nothing and reports success.
- **Frameless move and resize are handed to Windows** via `WM_NCLBUTTONDOWN`. Doing that loop in JavaScript chases the pointer a frame behind and loses snapping and multi-monitor edges.
- **Released in `finally`, everywhere.** `SendInput` raises when injection is refused (an elevated window takes focus, the secure desktop appears), and a skipped key-up leaves the key physically held.
- **Interruptible waits.** Sleeps are sliced and re-check the stop flag, so Stop lands *inside* a four-second wait rather than after it.
- **Atomic writes** (`tmp` + `fsync` + `os.replace`) for settings, macros and recordings.

## Limitations

Windows only. Display scaling must be **100 %** — the health check warns otherwise. Games whose anti-cheat blocks synthetic input will not work, and that is not something to work around. Some hardware-accelerated apps ignore `PrintWindow`; capture falls back to a screen grab, which needs the window visible.

## Building an exe

```bash
pip install pyinstaller
python build_exe.py
```

Output in `dist/`. User data is not bundled — the app creates the folders beside the exe on first run.
