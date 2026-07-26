"""Macro Studio -- block-based macro builder with action recording.

pywebview entry point plus the Api class every JS call goes through.

Heavy imports (cv2, numpy, mss, pynput) stay lazy inside methods so
`python main.py --test` runs the CLI diagnostics on a bare install.
"""
import base64
import json
import os
import sys
import threading
import time
import webbrowser

from core import constants
from core import settings as settingsmod
from core import window as wm

constants.ensure_dirs()
wm.set_dpi_aware()

GUI_TITLE = "Macro Studio"
GUI_WIDTH = 1500
GUI_HEIGHT = 900
LOG_HISTORY_LIMIT = 500

HOTKEY_ACTIONS = ("hotkey_start", "hotkey_stop", "hotkey_pause",
                  "hotkey_record", "hotkey_pick")


class Api:
    """Every public method here is callable from JS as pywebview.api.<name>()."""

    def __init__(self):
        from core.logger import Logger
        from core.recorder import Recorder
        from core.runner import MacroRunner

        self._window = None
        self._logger = Logger()
        self._log_history = []
        self._status = {"running": False, "paused": False, "recording": False,
                        "action": "Idle", "loop": 0, "target": ""}
        self._recorder = Recorder(log=self.push_log)
        self._pending_events = []
        self._pending_meta = {}
        self.runner = MacroRunner(log=self.push_log, set_status=self._set_status)
        self._on_hotkeys_changed = None
        self._picking = False
        self._pick_result = None
        self._capture_cache = None
        self._capture_cache_hwnd = None
        self._maximized = False
        # Serialises target changes against the status poll, which also
        # writes settings when it re-finds a relaunched window.
        self._target_lock = threading.Lock()

        cfg = settingsmod.load()
        from core import pacing
        pacing.set_action_delay_ms(cfg.get("action_delay_ms", 0))

    # ------------------------------------------------------------ internals

    def set_window(self, window) -> None:
        self._window = window

    def _set_status(self, **kw) -> None:
        self._status.update(kw)

    def push_log(self, message: str) -> None:
        message = str(message)
        self._logger.log(message)
        entry = {"t": time.strftime("%H:%M:%S"), "msg": message}
        self._log_history.append(entry)
        if len(self._log_history) > LOG_HISTORY_LIMIT:
            del self._log_history[:-LOG_HISTORY_LIMIT]
        self._js("window.addLog && window.addLog(%s)" % json.dumps(entry))

    def push_ui(self, fn_name: str) -> None:
        self._js("window.%s && window.%s()" % (fn_name, fn_name))

    def _js(self, code: str) -> None:
        try:
            if self._window is not None:
                self._window.evaluate_js(code)
        except Exception:
            pass

    # -------------------------------------------------------------- general

    def get_version(self) -> str:
        return constants.get_version()

    def get_bootstrap(self) -> dict:
        """One call the UI makes on startup instead of six round-trips.

        Nothing in here may raise: this is the first call the frontend makes,
        and an exception crossing the bridge leaves the whole UI blank with
        no error anywhere the user can see.
        """
        from core import blocks as blockmod
        from core import templates as tpl

        try:
            from core import ocr
            engine = ocr.engine_name()
        except Exception as exc:
            # core.ocr imports cv2/numpy at module level; a broken install
            # must degrade to "no OCR", not blank the app.
            engine = "unavailable"
            self.push_log("OCR unavailable: %s" % exc)

        def safe(fn, fallback):
            try:
                return fn()
            except Exception as exc:
                self.push_log("Startup: %s" % exc)
                return fallback

        return {
            "version": constants.get_version(),
            "catalog": blockmod.catalog(),
            "phases": [{"key": p, "label": blockmod.PHASE_LABELS[p]}
                       for p in blockmod.PHASES],
            "settings": safe(settingsmod.load, dict(settingsmod.DEFAULTS)),
            "macros": safe(tpl.list_macros, []),
            "recordings": safe(tpl.list_recordings, []),
            "logs": self._log_history[-120:],
            "ocr_engine": engine,
            "display_scale": safe(wm.get_display_scale_percent, 100),
        }

    def get_logs(self) -> list:
        return self._log_history[-200:]

    def clear_logs(self) -> None:
        self._log_history = []
        self._js("window.clearLogs && window.clearLogs()")

    def minimize_window(self) -> None:
        try:
            self._window.minimize()
        except Exception:
            pass

    def toggle_maximize(self) -> dict:
        """The window is frameless, so the OS provides no maximise button --
        the custom title bar calls this instead."""
        try:
            if getattr(self, "_maximized", False):
                self._window.restore()
                self._maximized = False
            else:
                self._window.maximize()
                self._maximized = True
            return {"ok": True, "maximized": self._maximized}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def close_window(self) -> None:
        try:
            self.runner.stop()
            if self._recorder.active:
                self._recorder.cancel()
        finally:
            from core import capture
            capture.close_all_mss()
            self._logger.close()
            try:
                self._window.destroy()
            except Exception:
                pass

    def open_data_folder(self) -> bool:
        try:
            os.startfile(constants.APP_DIR)
            return True
        except Exception:
            return False

    def open_url(self, url: str) -> bool:
        # Only ever called with app-internal help links from the UI.
        if not str(url).startswith(("http://", "https://")):
            return False
        webbrowser.open(url)
        return True

    # --------------------------------------------------------------- target

    def list_windows(self) -> list:
        return wm.list_windows()

    def set_target(self, hwnd, title: str = "") -> dict:
        hwnd = int(hwnd or 0)
        if hwnd and not wm.is_window(hwnd):
            return {"ok": False, "reason": "gone"}
        if hwnd and wm.is_minimized(hwnd):
            # A minimized window has no usable client area, so every capture
            # and every coordinate would be wrong. Restore it on attach.
            wm.activate_window(hwnd)
            time.sleep(0.4)
        title = title or (wm.get_window_title(hwnd) if hwnd else "")
        with self._target_lock:
            settingsmod.update({"target_hwnd": hwnd, "target_title": title,
                                "target_mode": "window" if hwnd else "screen"})
        # A cached preview belongs to the window it was taken from; keeping
        # it would let a crop be saved from a completely different app.
        self._capture_cache = None
        self._capture_cache_hwnd = None
        self._status["target"] = title
        self.push_log("Target set: %s" % (title or "whole screen"))
        return {"ok": True, "hwnd": hwnd, "title": title, **self.get_target_info()}

    def use_screen_target(self) -> dict:
        with self._target_lock:
            settingsmod.update({"target_hwnd": 0, "target_mode": "screen",
                                "target_title": ""})
        self._capture_cache = None
        self._capture_cache_hwnd = None
        self._status["target"] = "Screen"
        self.push_log("Target set: whole screen")
        return {"ok": True, **self.get_target_info()}

    def get_target_info(self) -> dict:
        cfg = settingsmod.load()
        hwnd = int(cfg.get("target_hwnd") or 0)
        mode = cfg.get("target_mode", "window")
        if mode == "screen" or not hwnd:
            sw, sh = wm.get_screen_size()
            return {"mode": "screen", "hwnd": 0, "title": "Whole screen",
                    "alive": True, "minimized": False, "width": sw, "height": sh}
        alive = wm.is_window(hwnd)
        if not alive:
            # Re-find a relaunched app: same window title, new hwnd. Matched
            # on the FULL title, not a substring -- a loose match happily
            # retargeted an unrelated window whose title merely contained the
            # old one, and the macro then clicked into it.
            wanted = str(cfg.get("target_title") or "")
            found = 0
            if wanted:
                for info in wm.list_windows():
                    if info["title"] == wanted:
                        found = info["hwnd"]
                        break
            if found:
                hwnd = found
                with self._target_lock:
                    # Locked read-modify-write: a status poll landing here
                    # used to clobber a target the user had just picked.
                    if int(settingsmod.load().get("target_hwnd") or 0) != hwnd:
                        settingsmod.update({"target_hwnd": hwnd})
                alive = True
                self._capture_cache = None
        minimized = bool(alive and wm.is_minimized(hwnd))
        w, h = wm.get_client_size(hwnd) if (alive and not minimized) else (0, 0)
        return {"mode": "window", "hwnd": hwnd,
                "title": wm.get_window_title(hwnd) if alive else cfg.get("target_title", ""),
                "alive": alive, "minimized": minimized, "width": w, "height": h}

    def focus_target(self) -> bool:
        info = self.get_target_info()
        if info["mode"] == "window" and info["alive"]:
            return wm.activate_window(info["hwnd"])
        return False

    def _target_hwnd(self) -> int:
        info = self.get_target_info()
        return info["hwnd"] if (info["mode"] == "window" and info["alive"]) else 0

    def _coord_space(self) -> str:
        return "window" if self.get_target_info()["mode"] == "window" else "screen"

    # ------------------------------------------------------------ recording

    def start_recording(self) -> dict:
        if self._recorder.active:
            return {"ok": False, "reason": "already_recording"}
        if self.runner.is_running():
            return {"ok": False, "reason": "macro_running"}
        cfg = settingsmod.load()
        hwnd = self._target_hwnd()
        # The stop/record hotkeys must never end up inside the recording.
        self._recorder.suppress([cfg.get(a) for a in HOTKEY_ACTIONS])
        ok = self._recorder.start(hwnd=hwnd,
                                  record_moves=bool(cfg.get("record_mouse_move", True)),
                                  move_interval_ms=int(cfg.get("record_move_interval_ms", 40)))
        if not ok:
            return {"ok": False, "reason": "listener_failed"}
        self._status["recording"] = True
        self.push_log("Recording started -- do the actions, then press stop.")
        self.push_ui("onRecordingStarted")
        return {"ok": True}

    def stop_recording(self) -> dict:
        """Stop and PARK the events. Saving is a separate call so typing a
        name can't be captured as part of the recording."""
        if not self._recorder.active:
            return {"ok": False, "reason": "not_recording"}
        events = self._recorder.stop()
        self._status["recording"] = False
        self._pending_events = events
        self._pending_meta = {"count": len(events)}
        self.push_log("Recording stopped: %d events." % len(events))
        self.push_ui("onRecordingStopped")
        return {"ok": True, "count": len(events),
                "preview": self.preview_pending_blocks()}

    def cancel_recording(self) -> dict:
        self._recorder.cancel()
        self._status["recording"] = False
        self._pending_events = []
        self.push_log("Recording discarded.")
        self.push_ui("onRecordingStopped")
        return {"ok": True}

    def is_recording(self) -> bool:
        return bool(self._recorder.active)

    def recording_event_count(self) -> int:
        return self._recorder.peek_count() if self._recorder.active else len(self._pending_events)

    def preview_pending_blocks(self, keep_moves: bool = False, min_gap_ms: int = 60) -> list:
        from core import blocks as blockmod
        from core import recorder as rec
        blocks = rec.events_to_blocks(self._pending_events, self._coord_space(),
                                      int(min_gap_ms), bool(keep_moves))
        # Normalised before it leaves: the UI and the runner both assume every
        # block carries `once`/`enabled`, and recorder output omits `once`.
        return blockmod.normalize_list(rec.compress_text_blocks(blocks))

    def save_pending_recording(self, name: str) -> dict:
        from core import templates as tpl
        if not self._pending_events:
            return {"ok": False, "reason": "empty"}
        try:
            saved = tpl.save_recording(name, self._pending_events)
        except OSError as exc:
            self.push_log("Could not save recording: %s" % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log("Recording saved as '%s'." % saved)
        return {"ok": True, "name": saved, "recordings": tpl.list_recordings()}

    def discard_pending_recording(self) -> dict:
        self._pending_events = []
        return {"ok": True}

    def list_recordings(self) -> list:
        from core import templates as tpl
        return tpl.list_recordings()

    def load_recording_blocks(self, name: str, keep_moves: bool = False,
                              min_gap_ms: int = 60) -> list:
        from core import blocks as blockmod
        from core import recorder as rec
        from core import templates as tpl
        events = (tpl.load_recording(name) or {}).get("events") or []
        blocks = rec.events_to_blocks(events, self._coord_space(),
                                      int(min_gap_ms), bool(keep_moves))
        return blockmod.normalize_list(rec.compress_text_blocks(blocks))

    def delete_recording(self, name: str) -> dict:
        from core import templates as tpl
        ok = tpl.delete_recording(name)
        return {"ok": ok, "recordings": tpl.list_recordings()}

    def get_recording_actions(self, name: str) -> dict:
        """The editable action list behind a Play Recording block.

        Returns the stored edited list if there is one, otherwise the raw
        events converted on the fly -- so opening the editor on a brand new
        recording shows something to edit rather than a blank list.
        """
        from core import blocks as blockmod
        from core import recorder as rec
        from core import templates as tpl

        data = tpl.load_recording(name) or {}
        if not data.get("exists"):
            # Deleted or renamed since the block was created. Saying so is
            # what stops the editor from writing the file back into existence.
            return {"ok": False, "reason": "missing", "name": name}

        stored = data.get("blocks")
        # `is not None`: an empty edited list is a real state ("all actions
        # deleted"), not the absence of one.
        if stored is not None:
            return {"ok": True, "name": name, "edited": True,
                    "blocks": blockmod.normalize_list(stored),
                    "event_count": len(data.get("events") or [])}

        events = data.get("events") or []
        derived = rec.compress_text_blocks(
            rec.events_to_blocks(events, self._coord_space(), 60, True))
        return {"ok": True, "name": name, "edited": False,
                "blocks": blockmod.normalize_list(derived),
                "event_count": len(events)}

    def save_recording_actions(self, name: str, blocks: list) -> dict:
        """Write an edited action list back into the recording.

        The raw events are kept untouched, so «Reset to original» can always
        re-derive the actions from what was actually recorded.
        """
        from core import blocks as blockmod
        from core import templates as tpl
        try:
            saved = tpl.update_recording_blocks(name, blockmod.normalize_list(blocks))
        except FileNotFoundError:
            self.push_log("Recording '%s' no longer exists -- nothing saved." % name)
            return {"ok": False, "reason": "missing"}
        except OSError as exc:
            self.push_log("Could not save recording actions: %s" % exc)
            return {"ok": False, "reason": str(exc)}
        count = len(blocks or [])
        if count:
            self.push_log("Recording '%s': %d action(s) saved." % (saved, count))
        else:
            self.push_log("Recording '%s': all actions removed -- it will now do nothing."
                          % saved)
        return {"ok": True, "name": saved}

    def reset_recording_actions(self, name: str) -> dict:
        """Drop the edited list so playback goes back to the raw events."""
        from core import templates as tpl
        data = tpl.load_recording(name) or {}
        if not data.get("exists"):
            return {"ok": False, "reason": "missing", "name": name}
        try:
            tpl.save_recording(name, data.get("events") or [], None)
        except OSError as exc:
            return {"ok": False, "reason": str(exc)}
        self.push_log("Recording '%s' reset to the original events." % name)
        return self.get_recording_actions(name)

    # --------------------------------------------------------------- macros

    def list_macros(self) -> list:
        from core import templates as tpl
        return tpl.list_macros()

    def save_macro(self, name: str, macro: dict) -> dict:
        from core import templates as tpl
        try:
            saved = tpl.save_macro(name, macro)
        except OSError as exc:
            # An escaping OSError reaches JS as a silent null, and the UI's
            # debounced autosave would then discard edits without a word.
            self.push_log("Could not save macro: %s" % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log("Macro '%s' saved." % saved)
        return {"ok": True, "name": saved, "macros": tpl.list_macros()}

    def load_macro(self, name: str) -> dict:
        from core import templates as tpl
        return tpl.load_macro(name)

    def delete_macro(self, name: str) -> dict:
        from core import templates as tpl
        ok = tpl.delete_macro(name)
        return {"ok": ok, "macros": tpl.list_macros()}

    def export_macro_file(self, macro: dict, filename: str = "macro") -> dict:
        try:
            import webview
            path = self._window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename="%s.json" % filename)
            if not path:
                return {"ok": False, "reason": "cancelled"}
            if isinstance(path, (list, tuple)):
                path = path[0]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(macro, fh, indent=2, ensure_ascii=False)
            self.push_log("Exported to %s" % path)
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def import_macro_file(self) -> dict:
        try:
            import webview
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=("JSON (*.json)",))
            if not paths:
                return {"ok": False, "reason": "cancelled"}
            with open(paths[0], "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return {"ok": True, "macro": data}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    # ------------------------------------------------------------ execution

    def start_macro(self, macro: dict) -> dict:
        if self._recorder.active:
            return {"ok": False, "reason": "recording"}
        info = self.get_target_info()
        if info["mode"] == "window" and not info["alive"]:
            self.push_log("Target window is not available.")
            return {"ok": False, "reason": "no_target"}
        cfg = settingsmod.load()
        self._status["target"] = info["title"]
        return self.runner.start(macro, hwnd=info["hwnd"],
                                 coord_space=self._coord_space(),
                                 loop_forever=bool(cfg.get("loop_forever", True)),
                                 loop_count=int(cfg.get("loop_count", 1)))

    def stop_macro(self) -> dict:
        return self.runner.stop()

    def pause_macro(self) -> dict:
        return self.runner.pause()

    def resume_macro(self) -> dict:
        return self.runner.resume()

    def toggle_pause(self) -> dict:
        return self.runner.toggle_pause()

    def get_status(self) -> dict:
        status = dict(self._status)
        status["running"] = self.runner.is_running()
        status["paused"] = self.runner.is_paused()
        status["recording"] = bool(self._recorder.active)
        status["rec_count"] = self.recording_event_count()
        info = self.get_target_info()
        status["target"] = info["title"]
        status["target_alive"] = info["alive"]
        return status

    def run_single_block(self, block: dict) -> dict:
        """Test one row in isolation -- the fastest way to check a coordinate
        or an image without running the whole macro."""
        if self.runner.is_running():
            return {"ok": False, "reason": "running"}
        from core import blocks as blockmod
        probe = blockmod.normalize(block)
        if probe is None:
            return {"ok": False, "reason": "bad_block"}
        # Forced on: the row's own ONCE / disabled state is about its place in
        # a macro, and honouring it here would make the test button a silent
        # no-op on exactly the row the user is trying to debug.
        probe["enabled"] = True
        probe["once"] = False
        macro = {"phases": {blockmod.PHASE_ONCE: [probe], blockmod.PHASE_REPEAT: []}}
        return self.start_macro(macro)

    # -------------------------------------------------------------- picking

    def pick_point(self) -> dict:
        """Blocking-ish coordinate picker: waits for the user's next left
        click anywhere, then returns it in the target's coordinate space."""
        if self._picking:
            return {"ok": False, "reason": "already_picking"}
        try:
            from pynput import mouse as pmouse
        except ImportError:
            return {"ok": False, "reason": "pynput_missing"}

        self._picking = True
        self._pick_result = None
        done = threading.Event()

        def on_click(x, y, button, pressed):
            if pressed and getattr(button, "name", "") == "left":
                self._pick_result = (int(x), int(y))
                done.set()
                return False

        listener = None
        try:
            listener = pmouse.Listener(on_click=on_click)
            listener.start()
            self.push_log("Click anywhere to capture a coordinate...")
            got = done.wait(timeout=30)
        except Exception as exc:
            # try/finally around the flag: a listener that fails to start
            # used to leave _picking stuck True, disabling the picker for the
            # rest of the session with no way back.
            self.push_log("Coordinate picker failed: %s" % exc)
            return {"ok": False, "reason": "listener_failed"}
        finally:
            try:
                if listener is not None:
                    listener.stop()
            except Exception:
                pass
            self._picking = False

        if not got or self._pick_result is None:
            return {"ok": False, "reason": "timeout"}

        sx, sy = self._pick_result
        hwnd = self._target_hwnd()
        if hwnd:
            cx, cy = wm.screen_to_client(hwnd, sx, sy)
        else:
            cx, cy = sx, sy
        self.push_log("Picked %d, %d" % (cx, cy))
        return {"ok": True, "x": int(cx), "y": int(cy), "screen_x": sx, "screen_y": sy}

    def pick_color(self) -> dict:
        point = self.pick_point()
        if not point.get("ok"):
            return point
        from core import capture
        frame = capture.grab_screen_bgr(point["screen_x"], point["screen_y"], 1, 1)
        if frame is None or frame.size == 0:
            return {"ok": False, "reason": "capture_failed"}
        b, g, r = [int(v) for v in frame[0, 0][:3]]
        point["color"] = "#%02x%02x%02x" % (r, g, b)
        point["rgb"] = [r, g, b]
        self.push_log("Picked colour %s" % point["color"])
        return point

    # ------------------------------------------------------- image manager

    def capture_target_preview(self) -> dict:
        """Freeze the target into a data URI the UI can crop on a canvas."""
        from core import capture
        hwnd = self._target_hwnd()
        frame = capture.capture_target_bgr(hwnd)
        if frame is None:
            return {"ok": False, "reason": "capture_failed"}
        self._capture_cache = frame
        self._capture_cache_hwnd = hwnd
        h, w = frame.shape[:2]
        return {"ok": True, "image": capture.png_data_uri(frame), "width": w, "height": h}

    @staticmethod
    def _safe_template_name(name: str) -> str:
        """Sanitise a template name (it becomes a folder under Assets/).

        Unicode is kept: core.vision reads and writes through
        imread_unicode / imwrite_unicode, which handle non-ASCII paths.
        """
        from core.naming import safe_name
        return safe_name(name, "")

    def save_template_crop(self, name: str, x: int, y: int, w: int, h: int,
                           as_variant: bool = False) -> dict:
        """Cut the cached preview into Assets/<name>/<name>.png (or _altN)."""
        import cv2
        from core import vision

        if self._capture_cache is None:
            return {"ok": False, "reason": "no_capture"}
        if self._capture_cache_hwnd != self._target_hwnd():
            # The target changed since the preview was taken; cropping it
            # would silently save a piece of the previous window.
            return {"ok": False, "reason": "stale_capture"}
        safe = self._safe_template_name(name)
        if not safe:
            return {"ok": False, "reason": "bad_name"}
        frame = self._capture_cache
        fh, fw = frame.shape[:2]
        try:
            x, y, w, h = int(x), int(y), int(w), int(h)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "bad_region"}
        # Validated, not clamped: clamping an out-of-frame rect produced an
        # empty slice, and cv2.imwrite then raised across the JS bridge.
        if not (0 <= x < fw and 0 <= y < fh):
            return {"ok": False, "reason": "bad_region"}
        w = min(w, fw - x)
        h = min(h, fh - y)
        if w < 1 or h < 1:
            return {"ok": False, "reason": "bad_region"}
        crop = frame[y:y + h, x:x + w]

        folder = os.path.join(constants.ASSETS_DIR, safe)
        os.makedirs(folder, exist_ok=True)
        primary = os.path.join(folder, safe + ".png")
        if os.path.exists(primary) and as_variant:
            index = 2
            while os.path.exists(os.path.join(folder, "%s_alt%d.png" % (safe, index))):
                index += 1
            path = os.path.join(folder, "%s_alt%d.png" % (safe, index))
        else:
            path = primary
        # imwrite_unicode, not cv2.imwrite: OpenCV hands the filename to the
        # C runtime as bytes, so a Cyrillic name silently wrote nothing while
        # the app reported success.
        if not vision.imwrite_unicode(path, crop):
            return {"ok": False, "reason": "write_failed"}
        vision.clear_cache()
        self.push_log("Saved image '%s' (%dx%d)." % (os.path.basename(path), w, h))
        return {"ok": True, "path": path, "templates": vision.list_templates()}

    def list_templates(self) -> list:
        from core import vision
        return vision.list_templates()

    def get_template_thumb(self, name: str, filename: str = "") -> str:
        import cv2
        from core import capture, vision
        safe = self._safe_template_name(name)
        if not safe:
            return ""
        paths = vision.template_variant_paths(safe)
        if filename:
            # Compared as a bare basename: an unsanitised filename here was a
            # path-traversal foothold out of Assets/.
            wanted = os.path.basename(str(filename))
            paths = [p for p in paths if os.path.basename(p) == wanted] or paths
        if not paths:
            return ""
        img = vision.imread_unicode(paths[0], cv2.IMREAD_COLOR)
        if img is None:
            return ""
        return capture.png_data_uri(img)

    def delete_template(self, name: str, filename: str = "") -> dict:
        from core import vision
        safe = self._safe_template_name(name)
        if not safe:
            return {"ok": False, "reason": "bad_name"}
        wanted = os.path.basename(str(filename)) if filename else ""
        assets_root = os.path.abspath(constants.ASSETS_DIR)
        removed = 0
        for path in vision.template_variant_paths(safe):
            if wanted and os.path.basename(path) != wanted:
                continue
            # Belt and braces: never delete anything outside Assets/, even if
            # the name filter above were ever loosened.
            if not os.path.abspath(path).startswith(assets_root + os.sep):
                continue
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        folder = os.path.join(constants.ASSETS_DIR, safe)
        try:
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass
        vision.clear_cache()
        return {"ok": removed > 0, "templates": vision.list_templates()}

    def test_template(self, name: str, threshold: float = None) -> dict:
        from core import vision
        safe = self._safe_template_name(name)
        if not safe:
            return {"ok": False, "reason": "bad_name"}
        try:
            match = vision.find_image(self._target_hwnd(), safe, None, threshold)
        except vision.TemplateNotFound:
            # Must not cross the bridge as an exception: pywebview turns that
            # into a silent null on the JS side.
            return {"ok": False, "reason": "no_such_image"}
        if not match:
            return {"ok": False, "reason": "not_found"}
        return {"ok": True, **match}

    def open_assets_folder(self) -> bool:
        try:
            os.makedirs(constants.ASSETS_DIR, exist_ok=True)
            os.startfile(constants.ASSETS_DIR)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ settings

    def get_settings(self) -> dict:
        return settingsmod.load()

    def set_setting(self, key: str, value) -> dict:
        merged = settingsmod.update({key: value})
        if key == "action_delay_ms":
            from core import pacing
            pacing.set_action_delay_ms(value)
        if key in HOTKEY_ACTIONS and self._on_hotkeys_changed:
            self._on_hotkeys_changed(merged)
        return merged

    def reset_settings(self) -> dict:
        settingsmod.save({})
        merged = settingsmod.load()
        if self._on_hotkeys_changed:
            self._on_hotkeys_changed(merged)
        return merged

    # ------------------------------------------------------------- webhook

    def get_webhook_settings(self) -> dict:
        """The URL is a secret: only a masked form crosses the bridge, so it
        cannot end up in a screenshot or a log."""
        from core import webhook as hook
        cfg = settingsmod.load()
        url = str(cfg.get("webhook_url") or "")
        return {
            "enabled": bool(cfg.get("webhook_enabled")),
            "configured": hook.validate(url)["valid"],
            "masked": hook.mask(url) if url else "",
            "username": cfg.get("webhook_username") or "Macro Studio",
        }

    def save_webhook_settings(self, url: str = None, enabled: bool = None,
                              username: str = None) -> dict:
        """Each argument is optional so the UI can toggle `enabled` without
        having to resend (and therefore hold) the URL."""
        from core import webhook as hook
        changes = {}
        if url is not None:
            text = str(url).strip()
            if text:
                check = hook.validate(text)
                if not check["valid"]:
                    return {"ok": False, "reason": check["reason"]}
            changes["webhook_url"] = text
        if enabled is not None:
            changes["webhook_enabled"] = bool(enabled)
        if username is not None:
            changes["webhook_username"] = str(username)[:80]
        if changes:
            settingsmod.update(changes)
            self.push_log("Webhook settings updated.")
        return {"ok": True, **self.get_webhook_settings()}

    def clear_webhook_url(self) -> dict:
        settingsmod.update({"webhook_url": "", "webhook_enabled": False})
        self.push_log("Webhook URL removed.")
        return {"ok": True, **self.get_webhook_settings()}

    def test_webhook(self) -> dict:
        """Send one message, right now, at the user's explicit request."""
        from core import webhook as hook
        cfg = settingsmod.load()
        url = str(cfg.get("webhook_url") or "")
        check = hook.validate(url)
        if not check["valid"]:
            return {"ok": False, "reason": check["reason"]}
        result = hook.send(url, "Macro Studio test message.",
                           username=cfg.get("webhook_username") or "Macro Studio")
        self.push_log("Webhook test: %s"
                      % ("delivered" if result.get("ok") else result.get("reason")))
        return result

    def preview_webhook_source(self, source: str, region=None, template: str = "") -> dict:
        """What a Send Webhook block would attach, without sending anything."""
        from core import capture, vision, webhook as hook
        source = str(source or "none").strip().lower()
        if source == "none":
            return {"ok": True, "image": "", "detail": "text only"}
        if source == "saved image":
            safe = self._safe_template_name(template)
            paths = vision.template_variant_paths(safe) if safe else []
            if not paths:
                return {"ok": False, "reason": "no_such_image"}
            img = vision.imread_unicode(paths[0])
            return {"ok": img is not None, "image": capture.png_data_uri(img),
                    "detail": "image '%s'" % safe}

        hwnd = self._target_hwnd() if source == "target window" else 0
        crop = None
        if source == "region" and region:
            try:
                crop = tuple(int(v) for v in region)
            except (TypeError, ValueError):
                crop = None
        frame = capture.capture_target_bgr(hwnd, crop)
        if frame is None:
            return {"ok": False, "reason": "capture_failed"}
        data = hook.shrink_to_limit(frame)
        return {"ok": True, "image": capture.png_data_uri(frame),
                "detail": "%dx%d, %.0f KB" % (frame.shape[1], frame.shape[0],
                                               (len(data) if data else 0) / 1024.0)}

    def run_health_check(self) -> list:
        from core import capture, ocr
        results = []

        info = self.get_target_info()
        results.append({"name": "Target window",
                        "ok": info["alive"],
                        "detail": info["title"] or "not selected"})

        frame = capture.capture_target_bgr(self._target_hwnd())
        results.append({"name": "Screen capture",
                        "ok": frame is not None and bool(frame.any()),
                        "detail": ("%dx%d" % (frame.shape[1], frame.shape[0]))
                                  if frame is not None else "no pixels"})

        try:
            from core.mouse import Mouse
            m = Mouse()
            before = m.position()
            m.nudge(3, 0)
            time.sleep(0.05)
            after = m.position()
            m.move_to(*before)
            results.append({"name": "Synthetic input",
                            "ok": after != before,
                            "detail": "cursor moved" if after != before else "cursor did not move"})
        except Exception as exc:
            results.append({"name": "Synthetic input", "ok": False, "detail": str(exc)})

        scale = wm.get_display_scale_percent()
        results.append({"name": "Display scale", "ok": scale == 100,
                        "detail": "%d%%%s" % (scale, "" if scale == 100
                                              else " -- coordinates may drift")})

        engine = ocr.engine_name()
        results.append({"name": "OCR engine", "ok": engine != "none", "detail": engine})

        try:
            import pynput  # noqa: F401
            results.append({"name": "Recorder hooks", "ok": True, "detail": "pynput ready"})
        except ImportError:
            results.append({"name": "Recorder hooks", "ok": False, "detail": "pynput missing"})

        for row in results:
            self.push_log("[Health] %s: %s (%s)"
                          % (row["name"], "OK" if row["ok"] else "FAIL", row["detail"]))
        return results


# --------------------------------------------------------------- CLI --test

def run_diagnostics() -> None:
    print("Macro Studio %s -- diagnostics" % constants.get_version())
    print("APP_DIR:    %s" % constants.APP_DIR)
    print("BUNDLE_DIR: %s" % constants.BUNDLE_DIR)
    print()
    print("1) List windows")
    print("2) Mouse test (moves in a square)")
    print("3) Keyboard test (types 'hello' after 3s)")
    print("4) Capture test")
    print("5) All")
    choice = input("> ").strip()

    def test_windows():
        for info in wm.list_windows()[:40]:
            print("  %-10s %-8s %s" % (info["hwnd"], info["process"][:8], info["title"][:60]))

    def test_mouse():
        from core.mouse import Mouse
        m = Mouse()
        start = m.position()
        print("  cursor at %s" % (start,))
        for dx, dy in ((100, 0), (0, 100), (-100, 0), (0, -100)):
            m.move_to(start[0] + dx, start[1] + dy)
            time.sleep(0.25)
        m.move_to(*start)
        print("  done")

    def test_keyboard():
        from core.keyboard import Keyboard
        print("  focus a text field, typing in 3s...")
        time.sleep(3)
        Keyboard().type_text("hello")
        print("  done")

    def test_capture():
        from core import capture
        frame = capture.capture_target_bgr(0)
        print("  screen frame: %s" % (None if frame is None else frame.shape,))

    actions = {"1": [test_windows], "2": [test_mouse], "3": [test_keyboard],
               "4": [test_capture],
               "5": [test_windows, test_mouse, test_keyboard, test_capture]}
    for fn in actions.get(choice, []):
        fn()


# ------------------------------------------------------------------ launch

def _launch_ui() -> None:
    import webview

    api = Api()
    api.push_log("Macro Studio %s starting..." % constants.get_version())

    scale = wm.get_display_scale_percent()
    if scale != 100:
        api.push_log("Display scale is %d%% -- coordinates can drift; 100%% recommended." % scale)

    index = os.path.join(constants.UI_DIR, "index.html")
    # frameless: the UI draws its own title bar with its own minimise /
    # maximise / close buttons. Without this the OS bar is drawn on top of it
    # and the window has two of everything.
    # easy_drag=False because the whole window would otherwise drag; only the
    # element marked .pywebview-drag-region should.
    webview.settings["ALLOW_DOWNLOADS"] = False
    window = webview.create_window(GUI_TITLE, url=index, js_api=api,
                                   width=GUI_WIDTH, height=GUI_HEIGHT,
                                   min_size=(900, 600), background_color="#0d0f18",
                                   frameless=True, easy_drag=False)
    api.set_window(window)

    def register_hotkeys(cfg=None):
        try:
            import keyboard as kb
        except ImportError:
            api.push_log("Global hotkeys unavailable (keyboard package missing).")
            return
        cfg = cfg or settingsmod.load()
        try:
            kb.unhook_all()
        except Exception:
            pass
        # Stop is bound straight to the Python call, never routed through JS:
        # it must win over any in-flight evaluate_js round-trip.
        bindings = [
            (cfg.get("hotkey_start"), lambda: api.push_ui("hotkeyStart")),
            (cfg.get("hotkey_stop"), api.stop_macro),
            (cfg.get("hotkey_pause"), api.toggle_pause),
            (cfg.get("hotkey_record"), lambda: api.push_ui("hotkeyRecord")),
            (cfg.get("hotkey_pick"), lambda: api.push_ui("hotkeyPick")),
        ]
        for key, fn in bindings:
            if not key:
                continue
            try:
                kb.add_hotkey(key, fn, suppress=False)
            except (ValueError, ImportError, OSError) as exc:
                api.push_log("Could not bind hotkey %r: %s" % (key, exc))

    api._on_hotkeys_changed = register_hotkeys

    def on_shown():
        register_hotkeys()
        api.push_log("Ready. Pick a target window to begin.")

    def on_closing():
        try:
            api.runner.stop()
            if api._recorder.active:
                api._recorder.cancel()
        except Exception:
            pass
        from core import capture
        capture.close_all_mss()
        api._logger.close()

    window.events.shown += on_shown
    window.events.closing += on_closing

    webview.start()

    try:
        import keyboard as kb
        kb.unhook_all()
    except Exception:
        pass


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_diagnostics()
    else:
        _launch_ui()
