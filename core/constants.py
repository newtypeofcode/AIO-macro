"""Central path resolution.

Three roots, because they behave differently:

BUNDLE_DIR -- read-only resources shipped inside the app (ui/, VERSION).
APP_DIR    -- where the app itself lives (the exe's folder). Read-only as far
              as user data is concerned; an installer or an update overwrites
              everything in it.
DATA_DIR   -- writable user data (settings.json, Templates/, Recordings/,
              Assets/, debug.log). On Windows this is
              the "Macro Studio" folder inside %APPDATA%.

User data deliberately does NOT live beside the exe any more. Anything in the
app folder is fair game for an update -- unpacking a new build over the old
one, or installing into a fresh folder, threw away every macro, template and
setting. %APPDATA% is per-user, writable without admin rights, and untouched
by updates. Set MACRO_STUDIO_HOME to put the data somewhere else (a portable
stick, a synced folder, a throwaway dir in tests).

Data saved by an older build is copied over on first launch -- see
migrate_legacy_data().
"""
import os
import shutil
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

APP_NAME = "Macro Studio"


def _resolve_data_dir() -> str:
    """Where the user's own files live.

    %APPDATA% first on Windows: it is per-user, needs no admin rights and no
    update ever touches it. The env override wins over everything so a
    portable copy -- or a test -- can keep its data to itself.
    """
    override = os.environ.get("MACRO_STUDIO_HOME", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return os.path.join(appdata, APP_NAME)
    if sys.platform == "darwin":
        return os.path.expanduser(os.path.join("~", "Library",
                                               "Application Support", APP_NAME))
    # Linux and a Windows box with no APPDATA (a stripped service account).
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return os.path.join(xdg or os.path.expanduser(os.path.join("~", ".config")),
                        APP_NAME)


DATA_DIR = _resolve_data_dir()
# Where the previous builds kept everything: beside the exe. Only read now,
# and only once, by migrate_legacy_data().
LEGACY_DATA_DIR = APP_DIR

UI_DIR = os.path.join(BUNDLE_DIR, "ui")
VERSION_FILE = os.path.join(BUNDLE_DIR, "VERSION")
ICON_FILE = os.path.join(UI_DIR, "img", "logo.ico")

# User-owned, in DATA_DIR so an update cannot reach them. Assets holds the
# reference PNGs the image blocks search for -- the whole point is that the
# user can open, replace and add to them.
TEMPLATES_DIR = os.path.join(DATA_DIR, "Templates")
RECORDINGS_DIR = os.path.join(DATA_DIR, "Recordings")
ASSETS_DIR = os.path.join(DATA_DIR, "Assets")
# Hand-made map screenshots the Place Unit block picks its spots on.
MAPS_DIR = os.path.join(DATA_DIR, "Maps")
# Reusable block groups: a named list of blocks the user can drop into
# any phase as many times as they like.
GROUPS_DIR = os.path.join(DATA_DIR, "Groups")
# Shareable user-defined palettes contain block type ids only, never macros or
# webhook secrets.
PALETTES_DIR = os.path.join(DATA_DIR, "Palettes")
DEBUG_DIR = os.path.join(DATA_DIR, "debug")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_FILE = os.path.join(DATA_DIR, "debug.log")

# What an older build kept beside the exe, and what to carry across.
_LEGACY_ITEMS = ("settings.json", "Templates", "Recordings", "Assets", "Maps",
                 "Groups")
# Written once the copy is done, so a user who deletes a migrated macro does
# not find it resurrected on the next launch.
_MIGRATION_MARKER = ".migrated-from"


def _copy_missing(src: str, dst: str) -> None:
    """Copy the tree, never overwriting anything already in the destination.

    The AppData copy is the live one from now on: if both sides have a file,
    the new location is the one the app has been writing to.
    """
    for folder, _dirs, files in os.walk(src):
        target = os.path.join(dst, os.path.relpath(folder, src))
        os.makedirs(target, exist_ok=True)
        for name in files:
            destination = os.path.join(target, name)
            if not os.path.exists(destination):
                shutil.copy2(os.path.join(folder, name), destination)


def migrate_legacy_data() -> list:
    """Carry data from an older build (kept beside the exe) into DATA_DIR.

    Copies rather than moves: if the user rolls back to the old build their
    macros are still where that build looks for them. Runs at most once --
    the marker file records that it happened.

    Returns the names it brought across, for the startup log.
    """
    if os.path.abspath(LEGACY_DATA_DIR) == os.path.abspath(DATA_DIR):
        return []
    marker = os.path.join(DATA_DIR, _MIGRATION_MARKER)
    if os.path.exists(marker):
        return []
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        return []

    brought = []
    for name in _LEGACY_ITEMS:
        source = os.path.join(LEGACY_DATA_DIR, name)
        destination = os.path.join(DATA_DIR, name)
        if not os.path.exists(source):
            continue
        try:
            if os.path.isdir(source):
                before = os.path.exists(destination)
                _copy_missing(source, destination)
                if not before:
                    brought.append(name)
            elif not os.path.exists(destination):
                shutil.copy2(source, destination)
                brought.append(name)
        except OSError:
            # A locked or unreadable leftover is not worth failing startup
            # over; the app simply starts with a clean copy of that item.
            continue
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(LEGACY_DATA_DIR)
    except OSError:
        pass
    return brought


def ensure_dirs() -> None:
    """Create the writable tree, migrating older data in. Safe to repeat."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        pass
    # Before the subfolders are created: an empty Recordings/ next to the exe
    # must not look like "the new location already has this".
    migrate_legacy_data()
    for path in (TEMPLATES_DIR, RECORDINGS_DIR, ASSETS_DIR, MAPS_DIR,
                 GROUPS_DIR, PALETTES_DIR, DEBUG_DIR):
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
