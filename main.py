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
from core.i18n import tr

constants.ensure_dirs()
wm.set_dpi_aware()

GUI_TITLE = "Macro Studio"
GUI_WIDTH = 1500
GUI_HEIGHT = 900
GUI_MIN_SIZE = (900, 600)
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
        # Run statistics (deep debug)
        self._run_stats = {"runs": 0, "errors": 0, "total_s": 0.0, "last_error": ""}
        self._run_start_time = None
        self._was_running = False
        self._capture_cache = None
        self._capture_cache_hwnd = None
        self._capture_ref = None
        self._maximized = False
        self._gui_hwnd = 0
        # Serialises target changes against the status poll, which also
        # writes settings when it re-finds a relaunched window.
        self._target_lock = threading.Lock()

        cfg = settingsmod.load()
        from core import pacing
        pacing.set_action_delay_ms(cfg.get("action_delay_ms", 0))
        # Before the first get_bootstrap, so the catalog the UI receives is
        # already in the saved language rather than the import-time default.
        self._apply_language(cfg.get("language"))

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
            engine = tr("unavailable")
            self.push_log(tr("OCR unavailable: %s") % exc)

        def safe(fn, fallback):
            try:
                return fn()
            except Exception as exc:
                self.push_log(tr("Startup: %s") % exc)
                return fallback

        return {
            "version": constants.get_version(),
            "catalog": blockmod.catalog(),
            "phases": [{"key": p, "label": blockmod.PHASE_LABELS[p]}
                       for p in blockmod.PHASES],
            "settings": safe(settingsmod.load, dict(settingsmod.DEFAULTS)),
            "macros": safe(tpl.list_macros, []),
            "recordings": safe(tpl.list_recordings, []),
            "groups": safe(self.list_block_groups, []),
            "palettes": safe(self.list_block_palettes, []),
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

    def _own_hwnd(self) -> int:
        """Our own window handle, cached.

        Asked of the native window object FIRST. Searching by title was the
        only route before, and it picks the wrong window whenever anything
        else on the desktop carries the same title -- including a second copy
        of this app, whose title bar then dragged the first one. The title
        search stays as the fallback for backends with no native handle.
        """
        if self._gui_hwnd and wm.is_window(self._gui_hwnd):
            return self._gui_hwnd

        native = getattr(self._window, "native", None) if self._window else None
        for attr in ("Handle", "handle", "winId", "hwnd"):
            value = getattr(native, attr, None)
            if value is None:
                continue
            try:
                if callable(value):
                    value = value()
                hwnd = int(value.ToInt64()) if hasattr(value, "ToInt64") else int(value)
            except Exception:
                continue
            if hwnd and wm.is_window(hwnd):
                self._gui_hwnd = hwnd
                return hwnd

        self._gui_hwnd = wm.find_own_window(GUI_TITLE)
        return self._gui_hwnd

    def begin_window_drag(self) -> bool:
        """Hand the move to Windows itself.

        The window is frameless, so there is no OS title bar to grab. Doing
        the move in JavaScript instead cannot keep up with the pointer and
        loses snapping and multi-monitor edges entirely.
        """
        hwnd = self._own_hwnd()
        if not hwnd:
            return False
        if self._maximized:
            # A maximised window cannot be moved: restore it first, exactly
            # like every native title bar does, or the drag does nothing.
            try:
                self._window.restore()
            except Exception:
                pass
        self._maximized = False
        return wm.begin_native_drag(hwnd, min_size=GUI_MIN_SIZE)

    def begin_window_resize(self, edge: str) -> bool:
        """Hand the resize to Windows itself, from the named edge/corner."""
        hwnd = self._own_hwnd()
        if not hwnd:
            return False
        self._maximized = False
        return wm.begin_native_resize(hwnd, edge, min_size=GUI_MIN_SIZE)

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
        # DATA_DIR, not the app folder: settings, macros, templates and
        # assets all live in %APPDATA% now.
        try:
            os.startfile(constants.DATA_DIR)
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
        self._capture_ref = None
        self._status["target"] = title
        # Not tr("Target set: %s") % "whole screen": a bare English noun
        # dropped into a translated sentence is exactly what the dedicated
        # message below exists to avoid.
        if title:
            self.push_log(tr("Target set: %s") % title)
        else:
            self.push_log(tr("Target set: whole screen"))
        return {"ok": True, "hwnd": hwnd, "title": title, **self.get_target_info()}

    def use_screen_target(self) -> dict:
        with self._target_lock:
            settingsmod.update({"target_hwnd": 0, "target_mode": "screen",
                                "target_title": ""})
        self._capture_cache = None
        self._capture_cache_hwnd = None
        self._capture_ref = None
        self._status["target"] = tr("Whole screen")
        self.push_log(tr("Target set: whole screen"))
        return {"ok": True, **self.get_target_info()}

    def get_target_info(self) -> dict:
        cfg = settingsmod.load()
        hwnd = int(cfg.get("target_hwnd") or 0)
        mode = cfg.get("target_mode", "window")
        if mode == "screen" or not hwnd:
            sw, sh = wm.get_screen_size()
            # The title is shown as-is in the header and the status bar; the
            # frontend only reaches for its own wording when this is empty,
            # and it never is.
            return {"mode": "screen", "hwnd": 0, "title": tr("Whole screen"),
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
                                  move_interval_ms=int(cfg.get("record_move_interval_ms", 8)))
        if not ok:
            return {"ok": False, "reason": "listener_failed"}
        self._status["recording"] = True
        self.push_log(tr("Recording started -- do the actions, then press stop."))
        self.push_ui("onRecordingStarted")
        return {"ok": True}

    def stop_recording(self) -> dict:
        """Stop and PARK the events. Saving is a separate call so typing a
        name can't be captured as part of the recording."""
        if not self._recorder.active:
            return {"ok": False, "reason": "not_recording"}
        events = self._recorder.stop()
        cfg = settingsmod.load()
        self._status["recording"] = False
        self._pending_events = events
        self._pending_meta = {"count": len(events)}
        self.push_log(tr("Recording stopped: %d events.") % len(events))
        self.push_ui("onRecordingStopped")
        # The saved recorder options, NOT the defaults: previewing a fresh
        # take with keep_moves off meant the mouse movement the user had just
        # recorded was missing from Converted blocks until something else
        # refreshed the list (saving did).
        return {"ok": True, "count": len(events),
                "preview": self.preview_pending_blocks(
                    keep_moves=bool(cfg.get("record_mouse_move", True)),
                    min_gap_ms=int(cfg.get("record_min_gap_ms", 60) or 0))}

    def cancel_recording(self) -> dict:
        self._recorder.cancel()
        self._status["recording"] = False
        self._pending_events = []
        self.push_log(tr("Recording discarded."))
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
            self.push_log(tr("Could not save recording: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log(tr("Recording saved as '%s'.") % saved)
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
            self.push_log(tr("Recording '%s' no longer exists -- nothing saved.") % name)
            return {"ok": False, "reason": "missing"}
        except OSError as exc:
            self.push_log(tr("Could not save recording actions: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        count = len(blocks or [])
        if count:
            self.push_log(tr("Recording '%s': %d action(s) saved.") % (saved, count))
        else:
            self.push_log(tr("Recording '%s': all actions removed -- it will now do nothing.")
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
        self.push_log(tr("Recording '%s' reset to the original events.") % name)
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
            self.push_log(tr("Could not save macro: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log(tr("Macro '%s' saved.") % saved)
        return {"ok": True, "name": saved, "macros": tpl.list_macros()}

    def load_macro(self, name: str) -> dict:
        from core import templates as tpl
        return tpl.load_macro(name)

    def delete_macro(self, name: str) -> dict:
        from core import templates as tpl
        ok = tpl.delete_macro(name)
        return {"ok": ok, "macros": tpl.list_macros()}

    def macro_dependencies(self, macro: dict) -> dict:
        """Which images and recordings a macro needs, and which are missing."""
        from core import bundle
        from core import templates as tpl
        from core import vision
        deps = bundle.dependencies(macro)
        return {
            "images": deps["images"],
            "recordings": deps["recordings"],
            "missing_images": [n for n in deps["images"]
                               if not vision.template_variant_paths(n)],
            "missing_recordings": [n for n in deps["recordings"]
                                   if not tpl.recording_exists(n)],
        }

    def export_macro_bundle(self, macro: dict, filename: str = "macro") -> dict:
        """Save a shareable .zip: the macro plus every image and recording it
        references. Nothing else of the user's is included."""
        from core import bundle
        try:
            import webview
            path = self._window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename="%s.macrozip" % filename,
                file_types=("Macro bundle (*.macrozip)", "All files (*.*)"))
            if not path:
                return {"ok": False, "reason": "cancelled"}
            if isinstance(path, (list, tuple)):
                path = path[0]
            report = bundle.export(macro, path)
        except Exception as exc:
            self.push_log(tr("Export failed: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log(tr("Exported '%s': %d image(s), %d recording(s).")
                      % (os.path.basename(path), len(report["images"]),
                         len(report["recordings"])))
        if report["missing_images"] or report["missing_recordings"]:
            self.push_log(tr("   missing and not included: %s")
                          % ", ".join(report["missing_images"]
                                      + report["missing_recordings"]))
        return report

    def inspect_macro_bundle(self) -> dict:
        """Open a bundle and report what it holds, WITHOUT writing anything --
        so the UI can show what is about to land and what would be replaced."""
        from core import bundle
        from core import templates as tpl
        from core import vision
        try:
            import webview
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Macro bundle (*.macrozip;*.zip)", "All files (*.*)"))
            if not paths:
                return {"ok": False, "reason": "cancelled"}
            info = bundle.inspect(paths[0])
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        return {
            "ok": True, "path": paths[0],
            "macro_name": (info["macro"] or {}).get("name", ""),
            "images": info["images"], "recordings": info["recordings"],
            "clash_images": [n for n in info["images"]
                             if vision.template_variant_paths(n)],
            "clash_recordings": [n for n in info["recordings"]
                                 if tpl.recording_exists(n)],
        }

    def import_macro_bundle(self, path: str, overwrite: bool = False) -> dict:
        """Unpack a bundle previously reported by inspect_macro_bundle."""
        from core import bundle
        try:
            report = bundle.import_bundle(path, bool(overwrite))
        except Exception as exc:
            self.push_log(tr("Import failed: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log(tr("Imported %d image(s), %d recording(s).")
                      % (len(report["images"]), len(report["recordings"])))
        for label, names in (("images", report["skipped_images"]),
                             ("recordings", report["skipped_recordings"])):
            if names:
                self.push_log(tr("   kept your existing %s: %s")
                              % (label, ", ".join(names)))
        if report["rejected"]:
            self.push_log(tr("   refused %d unexpected entr(y/ies) in the bundle")
                          % len(report["rejected"]))
        from core import templates as tpl
        report["recordings_list"] = tpl.list_recordings()
        return report

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
            self.push_log(tr("Exported to %s") % path)
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
            self.push_log(tr("Target window is not available."))
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
        stats = self.runner.run_stats()
        # Seconds, not a formatted string: the control bar counts on locally
        # between polls and formats it in the user's own layout.
        status["elapsed_s"] = round(float(stats.get("elapsed_s", 0.0)), 1)
        status["passes"] = int(stats.get("passes", 0))
        status["watch_fires"] = int(stats.get("watch_fires", 0))
        info = self.get_target_info()
        status["target"] = info["title"]
        status["target_alive"] = info["alive"]
        # Track run lifecycle for deep-debug statistics
        is_running = status["running"]
        if is_running and not self._was_running:
            self._run_start_time = time.time()
        elif not is_running and self._was_running:
            if self._run_start_time is not None:
                self._run_stats["runs"] += 1
                self._run_stats["total_s"] += time.time() - self._run_start_time
                self._run_start_time = None
        self._was_running = is_running
        # The runner parks this word back here when a run ends, so the bridge
        # is the one place both it and the startup value can be turned into
        # the user's language.
        if status["action"] == "Idle":
            status["action"] = tr("Idle")
        return status

    def get_run_stats(self) -> dict:
        """Return accumulated run statistics for the deep-debug panel."""
        runs = self._run_stats["runs"]
        total_s = self._run_stats["total_s"]
        avg_s = round(total_s / runs, 1) if runs > 0 else 0.0
        return {
            "runs": runs,
            "errors": self._run_stats["errors"],
            "avg_s": avg_s,
            "last_error": self._run_stats["last_error"]
        }

    def reset_run_stats(self) -> dict:
        """Reset accumulated run statistics."""
        self._run_stats = {"runs": 0, "errors": 0, "total_s": 0.0, "last_error": ""}
        self._run_start_time = None
        return {"ok": True}

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
            self.push_log(tr("Click anywhere to capture a coordinate..."))
            got = done.wait(timeout=30)
        except Exception as exc:
            # try/finally around the flag: a listener that fails to start
            # used to leave _picking stuck True, disabling the picker for the
            # rest of the session with no way back.
            self.push_log(tr("Coordinate picker failed: %s") % exc)
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
        self.push_log(tr("Picked %d, %d") % (cx, cy))
        return {"ok": True, "x": int(cx), "y": int(cy), "screen_x": sx, "screen_y": sy}

    def pick_exe_path(self) -> dict:
        """Open a file dialog so the user can browse for an executable."""
        try:
            import webview
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Executable (*.exe)", "All files (*.*)"))
            if not paths:
                return {"ok": False, "reason": "cancelled"}
            return {"ok": True, "path": paths[0]}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def get_condition_types(self) -> list:
        """Return condition type catalog for the UI condition builder."""
        try:
            from core.conditions import COND_TYPES
            return COND_TYPES
        except Exception:
            return []

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
        self.push_log(tr("Picked colour %s") % point["color"])
        return point

    # ------------------------------------------------------- image manager

    def _hide_self_for_capture(self) -> bool:
        """Get this window out of the shot.

        Only matters in whole-screen mode: the grab is of the desktop, and
        Macro Studio is sitting on top of it, so the crop the user wanted was
        half our own UI. In window mode the target is captured directly and
        hiding would only make the app flicker for nothing.
        """
        if self._window is None:
            return False
        try:
            self._window.hide()
        except Exception:
            return False
        # The compositor needs a moment to actually take the window off the
        # screen; grabbing immediately still catches it.
        time.sleep(0.35)
        return True

    def _show_self_after_capture(self, hidden: bool) -> None:
        if not hidden or self._window is None:
            return
        try:
            self._window.show()
        except Exception:
            pass

    def capture_target_preview(self, hwnd=None) -> dict:
        """Freeze a window into a data URI the UI can crop on a canvas.

        hwnd is what the Images screen asks the user for before every shot:
        None keeps the old behaviour (whatever the macro target is), 0 means
        the whole screen, and any other handle is a one-off shot that must
        NOT become the macro target -- picking a window to photograph is not
        the same decision as picking the window a macro drives.
        """
        from core import capture
        hwnd = self._target_hwnd() if hwnd is None else int(hwnd or 0)
        hidden = self._hide_self_for_capture() if not hwnd else False
        try:
            frame = capture.capture_target_bgr(hwnd)
        finally:
            self._show_self_after_capture(hidden)
        if frame is None:
            return {"ok": False, "reason": "capture_failed"}
        self._capture_cache = frame
        self._capture_cache_hwnd = hwnd
        # Remembered now, while the window it came from is still known: a
        # picture saved as a map has to say whether its pixels are screen
        # pixels or window pixels, and nothing can tell afterwards.
        self._capture_ref = capture.frame_reference(hwnd, frame)
        h, w = frame.shape[:2]
        return {"ok": True, "image": capture.png_data_uri(frame), "width": w, "height": h}

    def _capture_is_live(self) -> bool:
        """Is the cached shot still worth cropping?

        Only the shot window is checked -- the frame itself is cached, so its
        crop coordinates can never drift, and since the shot is now aimed by
        hand it is no longer wrong for it to differ from the macro target.
        A closed window is still refused: its handle is what "Re-capture"
        would shoot next, and the reason tells the UI to ask again.
        """
        if self._capture_cache is None:
            return False
        hwnd = self._capture_cache_hwnd or 0
        return not hwnd or wm.is_window(hwnd)

    def save_map_crop(self, name: str, x: int = 0, y: int = 0, w: int = 0,
                      h: int = 0, whole: bool = False) -> dict:
        """Save the cached shot (or a crop of it) into Maps as a map picture.

        The same capture the templates come from, written to the other folder:
        a map is normally the whole game window, so `whole` skips the crop
        rectangle instead of making the user drag one around the full frame.
        """
        from core import maps

        if self._capture_cache is None:
            return {"ok": False, "reason": "no_capture"}
        if not self._capture_is_live():
            return {"ok": False, "reason": "stale_capture"}
        safe = maps.safe_name(name)
        if not safe:
            return {"ok": False, "reason": "bad_name"}
        frame = self._capture_cache
        fh, fw = frame.shape[:2]
        if whole:
            crop = frame
        else:
            try:
                x, y, w, h = int(x), int(y), int(w), int(h)
            except (TypeError, ValueError):
                return {"ok": False, "reason": "bad_region"}
            if w < 2 or h < 2 or x < 0 or y < 0 or x + w > fw or y + h > fh:
                return {"ok": False, "reason": "bad_region"}
            crop = frame[y:y + h, x:x + w]
        # The crop's own offset inside the shot travels with it, so a map cut
        # out of one corner still knows where that corner is; without it every
        # cropped map would be read as if it started at the shot's origin.
        meta = None
        ref = getattr(self, "_capture_ref", None)
        if ref:
            ch, cw = crop.shape[:2]
            off_x, off_y = (0, 0) if whole else (x, y)
            meta = dict(ref)
            meta["left"] = int(ref.get("left", 0)) + int(off_x)
            meta["top"] = int(ref.get("top", 0)) + int(off_y)
            meta["width"], meta["height"] = int(cw), int(ch)

        # Overwriting is deliberate here: re-shooting a map by its own name is
        # the repair for "the map picture is out of date", and the blocks that
        # point at that name must follow the new picture.
        saved = maps.save_map_frame(safe, crop, overwrite=maps.exists(safe),
                                    meta=meta)
        if not saved:
            return {"ok": False, "reason": "write_failed"}
        safe, width, height = saved
        self.push_log(tr("Saved map '%s' (%dx%d).") % (safe, width, height))
        return {"ok": True, "name": safe, "width": width, "height": height,
                "maps": maps.list_maps()}

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
        if not self._capture_is_live():
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
        self.push_log(tr("Saved image '%s' (%dx%d).") % (os.path.basename(path), w, h))
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

    # -------------------------------------------------------- block groups

    def list_block_groups(self) -> list:
        from core import snippets
        return snippets.list_groups()

    def save_block_group(self, name: str, blocks: list) -> dict:
        """Store a reusable list of blocks under a name.

        Normalised on the way in, so a group saved by this build still opens
        after a field is added to one of its block types -- the same contract
        a saved macro gets.
        """
        from core import blocks as blockmod
        from core import snippets
        cleaned = blockmod.normalize_list(blocks)
        if not cleaned:
            return {"ok": False, "reason": "empty"}
        try:
            saved = snippets.save_group(name, cleaned)
        except (OSError, ValueError) as exc:
            self.push_log(tr("Could not save the block group: %s") % exc)
            return {"ok": False, "reason": str(exc)}
        self.push_log(tr("Block group '%s' saved (%d block(s)).")
                      % (saved, len(cleaned)))
        return {"ok": True, "name": saved, "count": len(cleaned),
                "groups": snippets.list_groups()}

    def load_block_group(self, name: str) -> dict:
        from core import blocks as blockmod
        from core import snippets
        found = snippets.load_group(name)
        if not found:
            return {"ok": False, "reason": "missing"}
        return {"ok": True, "name": snippets.safe_name(name),
                "blocks": blockmod.normalize_list(found)}

    def rename_block_group(self, name: str, new_name: str) -> dict:
        from core import snippets
        try:
            saved = snippets.rename_group(name, new_name)
        except (OSError, ValueError) as exc:
            return {"ok": False, "reason": str(exc)}
        if not saved:
            return {"ok": False, "reason": "missing"}
        return {"ok": True, "name": saved, "groups": snippets.list_groups()}

    def delete_block_group(self, name: str) -> dict:
        from core import snippets
        ok = snippets.delete_group(name)
        if ok:
            self.push_log(tr("Block group '%s' deleted.")
                          % snippets.safe_name(name))
        return {"ok": ok, "groups": snippets.list_groups()}

    def open_groups_folder(self) -> bool:
        try:
            os.makedirs(constants.GROUPS_DIR, exist_ok=True)
            os.startfile(constants.GROUPS_DIR)
            return True
        except Exception:
            return False

    # ------------------------------------------------------- block palettes

    def list_block_palettes(self) -> list:
        from core import palettes
        return palettes.list_palettes()

    def save_block_palette(self, name: str, types: list) -> dict:
        from core import blocks as blockmod
        from core import palettes
        allowed = {spec["type"] for spec in blockmod.catalog()}
        clean = [str(value) for value in (types or []) if str(value) in allowed]
        if not clean:
            return {"ok": False, "reason": "empty"}
        try:
            saved = palettes.save_palette(name, clean)
        except (OSError, ValueError) as exc:
            return {"ok": False, "reason": str(exc)}
        return {"ok": True, "palette": saved,
                "palettes": palettes.list_palettes()}

    def delete_block_palette(self, name: str) -> dict:
        from core import palettes
        ok = palettes.delete_palette(name)
        return {"ok": ok, "palettes": palettes.list_palettes()}

    def export_block_palette(self, name: str) -> dict:
        from core import palettes
        try:
            import webview
            path = self._window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename="%s.palette.json" % name,
                file_types=("Block palette (*.palette.json;*.json)", "All files (*.*)"))
            if not path:
                return {"ok": False, "reason": "cancelled"}
            if isinstance(path, (list, tuple)):
                path = path[0]
            saved = palettes.export_palette(name, path)
            return {"ok": True, "path": path, "palette": saved}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def import_block_palette(self) -> dict:
        from core import blocks as blockmod
        from core import palettes
        try:
            import webview
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Block palette (*.palette.json;*.json)", "All files (*.*)"))
            if not paths:
                return {"ok": False, "reason": "cancelled"}
            imported = palettes.import_palette(paths[0])
            allowed = {spec["type"] for spec in blockmod.catalog()}
            saved = palettes.save_palette(
                imported["name"],
                [value for value in imported.get("types", []) if value in allowed])
            if not saved["types"]:
                palettes.delete_palette(saved["name"])
                return {"ok": False, "reason": "empty"}
            return {"ok": True, "palette": saved,
                    "palettes": palettes.list_palettes()}
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def open_palettes_folder(self) -> bool:
        try:
            os.makedirs(constants.PALETTES_DIR, exist_ok=True)
            os.startfile(constants.PALETTES_DIR)
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- maps

    def list_maps(self) -> list:
        from core import maps
        return maps.list_maps()

    def get_map(self, name: str) -> dict:
        """The map picture plus its pixel size, for the location picker."""
        from core import maps
        data = maps.read_map(name)
        if not data:
            return {"ok": False, "reason": "unreadable"}
        uri, width, height = data
        return {"ok": True, "name": maps.safe_name(name), "image": uri,
                "width": width, "height": height}

    def get_map_thumb(self, name: str, max_side: int = 320) -> dict:
        """A small preview of a map, for the cards on the Images screen."""
        from core import maps
        data = maps.read_map(name, int(max_side or 0))
        if not data:
            return {"ok": False, "reason": "unreadable"}
        uri, width, height = data
        return {"ok": True, "name": maps.safe_name(name), "image": uri,
                "width": width, "height": height}

    def import_map(self, name: str = "") -> dict:
        """Pick an image file and keep it in Maps as the map to place on."""
        from core import maps
        try:
            import webview
            paths = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Images (*.png;*.jpg;*.jpeg;*.bmp;*.webp)",
                            "All files (*.*)"))
            if not paths:
                return {"ok": False, "reason": "cancelled"}
            added = maps.import_map(paths[0], name)
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        if not added:
            return {"ok": False, "reason": "unreadable"}
        safe, width, height = added
        self.push_log(tr("Saved map '%s' (%dx%d).") % (safe, width, height))
        return {"ok": True, "name": safe, "width": width, "height": height,
                "maps": maps.list_maps()}

    def delete_map(self, name: str) -> dict:
        from core import maps
        ok = maps.delete_map(name)
        return {"ok": ok, "maps": maps.list_maps()}

    def open_maps_folder(self) -> bool:
        try:
            os.makedirs(constants.MAPS_DIR, exist_ok=True)
            os.startfile(constants.MAPS_DIR)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ settings

    def get_settings(self) -> dict:
        return settingsmod.load()

    def _apply_language(self, value) -> str:
        """Point the block catalog at a language, and report which one stuck.

        The catalog is rewritten in place, so this has to happen on the
        Python side: the UI can translate its own chrome on its own, but
        block descriptions and field help come from `catalog()` and would
        stay in whichever language the module was imported with.
        """
        from core import blocks as blockmod
        from core import i18n
        try:
            language = blockmod.set_language(value)
        except Exception as exc:
            self.push_log(tr("Language: %s") % exc)
            language = blockmod.get_language()
        # Log lines are translated from a separate table, so pointing only
        # the catalog at the new language left the app talking in two at
        # once: Russian tooltips over an English run log.
        i18n.set_language(language)
        return language

    def set_setting(self, key: str, value) -> dict:
        if key == "language":
            # An unsupported code falls back rather than raising, and the
            # fallback is what gets saved -- otherwise settings.json keeps a
            # language nothing can render and the picker highlights nothing.
            value = self._apply_language(value)
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
        self._apply_language(merged.get("language"))
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
            "design": {
                "title": cfg.get("webhook_title") or "Macro report",
                "description": cfg.get("webhook_description") or "",
                "color": cfg.get("webhook_color") or "#8b5cf6",
                "footer": cfg.get("webhook_footer") or "Macro Studio",
                "timestamp": bool(cfg.get("webhook_timestamp", True)),
            },
        }

    def save_webhook_settings(self, url: str = None, enabled: bool = None,
                              username: str = None, design: dict = None) -> dict:
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
        if isinstance(design, dict):
            if "title" in design:
                changes["webhook_title"] = str(design["title"] or "")[:256]
            if "description" in design:
                changes["webhook_description"] = str(design["description"] or "")[:4096]
            if "color" in design:
                colour = str(design["color"] or "").strip()
                if not colour.startswith("#"):
                    colour = "#" + colour
                try:
                    int(colour[1:], 16)
                    valid_colour = len(colour) == 7
                except ValueError:
                    valid_colour = False
                changes["webhook_color"] = colour.lower() if valid_colour else "#8b5cf6"
            if "footer" in design:
                changes["webhook_footer"] = str(design["footer"] or "")[:2048]
            if "timestamp" in design:
                changes["webhook_timestamp"] = bool(design["timestamp"])
        if changes:
            settingsmod.update(changes)
            self.push_log(tr("Webhook settings updated."))
        return {"ok": True, **self.get_webhook_settings()}

    def clear_webhook_url(self) -> dict:
        settingsmod.update({"webhook_url": "", "webhook_enabled": False})
        self.push_log(tr("Webhook URL removed."))
        return {"ok": True, **self.get_webhook_settings()}

    def test_webhook(self) -> dict:
        """Send one message, right now, at the user's explicit request."""
        from core import webhook as hook
        cfg = settingsmod.load()
        url = str(cfg.get("webhook_url") or "")
        check = hook.validate(url)
        if not check["valid"]:
            return {"ok": False, "reason": check["reason"]}
        stats = self.runner.run_stats()
        embed = hook.build_embed(
            title=cfg.get("webhook_title") or tr("Macro report"),
            description=cfg.get("webhook_description") or "",
            fields=[{"name": tr("Runtime"),
                     "value": hook.format_duration(stats.get("elapsed_s", 0.0))},
                    {"name": tr("Loop passes"),
                     "value": str(stats.get("passes", 0))}],
            footer=cfg.get("webhook_footer") or "Macro Studio",
            color=cfg.get("webhook_color"),
            timestamp=bool(cfg.get("webhook_timestamp", True)))
        result = hook.send(url, tr("Macro Studio test message."), embed=embed,
                           username=cfg.get("webhook_username") or "Macro Studio")
        # Only the failure branch substitutes: what comes back there is a
        # machine code (not_https, http_404), and inventing Russian for it
        # would hide the string the user has to quote when asking for help.
        if result.get("ok"):
            self.push_log(tr("Webhook test: delivered."))
        else:
            self.push_log(tr("Webhook test: %s") % result.get("reason"))
        return result

    def preview_webhook_source(self, source: str, region=None, template: str = "") -> dict:
        """What a Send Webhook block would attach, without sending anything."""
        from core import capture, vision, webhook as hook
        source = str(source or "none").strip().lower()
        # `source` itself stays an English identifier -- it is stored inside
        # saved macros -- but `detail` is only ever shown, so it translates.
        if source == "none":
            return {"ok": True, "image": "", "detail": tr("text only")}
        if source == "saved image":
            safe = self._safe_template_name(template)
            paths = vision.template_variant_paths(safe) if safe else []
            if not paths:
                return {"ok": False, "reason": "no_such_image"}
            img = vision.imread_unicode(paths[0])
            return {"ok": img is not None, "image": capture.png_data_uri(img),
                    "detail": tr("image '%s'") % safe}

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
                "detail": tr("%dx%d, %.0f KB")
                          % (frame.shape[1], frame.shape[0],
                             (len(data) if data else 0) / 1024.0)}

    def run_health_check(self) -> list:
        """Six checks of the things a macro needs before it can work.

        Every row is translated here rather than in the frontend: the panel
        renders `name` and `detail` straight into the DOM as text, so there
        is nothing on the JS side to translate them with, and the same rows
        are what the log lines below are built from.
        """
        from core import capture, ocr
        results = []

        info = self.get_target_info()
        results.append({"name": tr("Target window"),
                        "ok": info["alive"],
                        "detail": info["title"] or tr("not selected")})

        frame = capture.capture_target_bgr(self._target_hwnd())
        results.append({"name": tr("Screen capture"),
                        "ok": frame is not None and bool(frame.any()),
                        "detail": ("%dx%d" % (frame.shape[1], frame.shape[0]))
                                  if frame is not None else tr("no pixels")})

        try:
            from core.mouse import Mouse
            m = Mouse()
            before = m.position()
            m.nudge(3, 0)
            time.sleep(0.05)
            after = m.position()
            m.move_to(*before)
            results.append({"name": tr("Synthetic input"),
                            "ok": after != before,
                            "detail": tr("cursor moved") if after != before
                                      else tr("cursor did not move")})
        except Exception as exc:
            # The only detail here that stays English: it is whatever the
            # mouse backend raised, and there is no message to look up.
            results.append({"name": tr("Synthetic input"), "ok": False,
                            "detail": str(exc)})

        scale = wm.get_display_scale_percent()
        drift = "" if scale == 100 else tr(" -- coordinates may drift")
        results.append({"name": tr("Display scale"), "ok": scale == 100,
                        "detail": "%d%%%s" % (scale, drift)})

        engine = ocr.engine_name()
        results.append({"name": tr("OCR engine"), "ok": engine != "none",
                        "detail": engine})

        try:
            import pynput  # noqa: F401
            results.append({"name": tr("Recorder hooks"), "ok": True,
                            "detail": tr("pynput ready")})
        except ImportError:
            results.append({"name": tr("Recorder hooks"), "ok": False,
                            "detail": tr("pynput missing")})

        for row in results:
            verdict = tr("OK") if row["ok"] else tr("FAIL")
            self.push_log(tr("[Health] %s: %s (%s)")
                          % (row["name"], verdict, row["detail"]))
        return results


# --------------------------------------------------------------- CLI --test

def run_diagnostics() -> None:
    print("Macro Studio %s -- diagnostics" % constants.get_version())
    print("APP_DIR:    %s" % constants.APP_DIR)
    print("DATA_DIR:   %s" % constants.DATA_DIR)
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
    api.push_log(tr("Macro Studio %s starting...") % constants.get_version())

    scale = wm.get_display_scale_percent()
    if scale != 100:
        api.push_log(tr("Display scale is %d%% -- coordinates can drift; "
                        "100%% recommended.") % scale)

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
                                   frameless=True, easy_drag=False, resizable=True)
    api.set_window(window)

    def register_hotkeys(cfg=None):
        try:
            import keyboard as kb
        except ImportError:
            api.push_log(tr("Global hotkeys unavailable (keyboard package missing)."))
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
                api.push_log(tr("Could not bind hotkey %r: %s") % (key, exc))

    api._on_hotkeys_changed = register_hotkeys

    def on_shown():
        register_hotkeys()
        api.push_log(tr("Ready. Pick a target window to begin."))

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
