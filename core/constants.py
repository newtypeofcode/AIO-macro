"""Central path resolution.

Two roots, because they behave differently once frozen by PyInstaller:

BUNDLE_DIR -- read-only resources shipped inside the app (ui/, VERSION).
APP_DIR    -- writable user data (settings.json, Templates/, Recordings/,
              Assets/, debug.log) that must live beside the real exe, not
              inside a onefile build's temp extraction dir (that dir can
              differ or be wiped between runs -- losing settings.json every
              launch would make the Settings screen pointless).
"""
import os
import sys

IS_FROZEN = hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False)

if hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
elif getattr(sys, "frozen", False):
    BUNDLE_DIR = os.path.dirname(sys.executable)
    # sys.executable, NOT sys.argv[0]: argv[0] can be a bare name when the app
    # is launched by a shortcut or from a shell, in which case abspath()
    # resolves it against the CURRENT WORKING DIRECTORY and all user data
    # (settings, macros, Assets) lands wherever the app happened to start.
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    APP_DIR = BUNDLE_DIR

UI_DIR = os.path.join(BUNDLE_DIR, "ui")
VERSION_FILE = os.path.join(BUNDLE_DIR, "VERSION")

# User-owned, always beside the exe so it survives updates and onefile temp
# extraction. Assets holds the reference PNGs the image blocks search for --
# the whole point is that the user can open, replace and add to them.
TEMPLATES_DIR = os.path.join(APP_DIR, "Templates")
RECORDINGS_DIR = os.path.join(APP_DIR, "Recordings")
ASSETS_DIR = os.path.join(APP_DIR, "Assets")
DEBUG_DIR = os.path.join(APP_DIR, "debug")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
LOG_FILE = os.path.join(APP_DIR, "debug.log")


def ensure_dirs() -> None:
    """Create the writable tree. Safe to call repeatedly."""
    for path in (TEMPLATES_DIR, RECORDINGS_DIR, ASSETS_DIR, DEBUG_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass


def get_version() -> str:
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"
