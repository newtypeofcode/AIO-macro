"""Shareable macro bundles.

A macro on its own is not portable: it names images and recordings that live
in the user's own Assets/ and Recordings/ folders, so a plain .json handed to
someone else fails on the first Click Image. A bundle is a zip carrying the
macro plus exactly the images and recordings it actually references.

Layout inside the zip:

    macro.json                  the macro itself
    manifest.json               what is inside and what produced it
    assets/<name>/<file>.png    every variant of each referenced image
    recordings/<name>.json      each referenced recording

Nothing else is collected. The user's other images, other recordings, their
settings and their webhook URL never go near the file.
"""
import json
import os
import zipfile

from . import blocks as blockmod
from . import naming
from . import templates as tpl
from . import vision
from .constants import ASSETS_DIR, RECORDINGS_DIR

BUNDLE_VERSION = 1
MANIFEST_NAME = "manifest.json"
MACRO_NAME = "macro.json"


# ------------------------------------------------------------- dependencies

def _walk_blocks(blocks):
    """Every block, including the ones nested in on_fail fallbacks."""
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        yield block
        params = block.get("params") or {}
        for value in params.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                for nested in _walk_blocks(value):
                    yield nested


def dependencies(macro: dict) -> dict:
    """{"images": [...], "recordings": [...]} referenced by a macro.

    Walks the fallback lists too -- a Click Image buried in an on-fail branch
    is just as much a dependency as one at the top level.
    """
    images, recordings = set(), set()
    phases = (macro or {}).get("phases") or {}
    for phase_blocks in phases.values():
        for block in _walk_blocks(phase_blocks):
            params = block.get("params") or {}
            name = str(params.get("template") or "").strip()
            if name:
                images.add(name)
            name = str(params.get("recording") or "").strip()
            if name:
                recordings.add(name)
    return {"images": sorted(images), "recordings": sorted(recordings)}


# ------------------------------------------------------------------ export

def export(macro: dict, path: str) -> dict:
    """Write a bundle. Returns a report of what went in and what was missing."""
    deps = dependencies(macro)
    report = {"images": [], "recordings": [], "missing_images": [],
              "missing_recordings": [], "path": path}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MACRO_NAME, json.dumps(macro, indent=2, ensure_ascii=False))

        for name in deps["images"]:
            paths = vision.template_variant_paths(name)
            if not paths:
                report["missing_images"].append(name)
                continue
            for src in paths:
                zf.write(src, "assets/%s/%s" % (name, os.path.basename(src)))
            report["images"].append(name)

        for name in deps["recordings"]:
            data = tpl.load_recording(name)
            if not data.get("exists"):
                report["missing_recordings"].append(name)
                continue
            payload = {k: v for k, v in data.items() if k != "exists"}
            zf.writestr("recordings/%s.json" % name,
                        json.dumps(payload, indent=2, ensure_ascii=False))
            report["recordings"].append(name)

        zf.writestr(MANIFEST_NAME, json.dumps({
            "bundle_version": BUNDLE_VERSION,
            "macro_name": (macro or {}).get("name", ""),
            "images": report["images"],
            "recordings": report["recordings"],
            "missing_images": report["missing_images"],
            "missing_recordings": report["missing_recordings"],
        }, indent=2, ensure_ascii=False))

    report["ok"] = True
    return report


# ------------------------------------------------------------------ import

def _safe_member(member: str):
    """Split a zip entry into (kind, name, filename), or None if it is not a
    member we are willing to write.

    A zip is untrusted input: an entry called `../../evil.png` or `C:\\x.png`
    would otherwise be written wherever it asked. Only the two shapes this
    format defines are accepted, and each part is re-sanitised.
    """
    normalised = member.replace("\\", "/")
    if normalised.startswith("/") or ".." in normalised.split("/"):
        return None
    parts = [p for p in normalised.split("/") if p]
    if len(parts) == 3 and parts[0] == "assets":
        name = naming.safe_name(parts[1], "")
        filename = os.path.basename(parts[2])
        if not name or not filename.lower().endswith(".png"):
            return None
        return ("image", name, filename)
    if len(parts) == 2 and parts[0] == "recordings":
        if not parts[1].lower().endswith(".json"):
            return None
        name = naming.safe_name(parts[1][:-5], "")
        return ("recording", name, None) if name else None
    return None


def inspect(path: str) -> dict:
    """What a bundle contains, without writing anything."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if MACRO_NAME not in names:
            raise ValueError("not a macro bundle (no %s)" % MACRO_NAME)
        macro = json.loads(zf.read(MACRO_NAME).decode("utf-8"))
        manifest = {}
        if MANIFEST_NAME in names:
            try:
                manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            except ValueError:
                manifest = {}

    images, recordings = set(), set()
    for member in names:
        parsed = _safe_member(member)
        if not parsed:
            continue
        kind, name, _ = parsed
        (images if kind == "image" else recordings).add(name)

    return {"macro": macro, "manifest": manifest,
            "images": sorted(images), "recordings": sorted(recordings)}


def _existing_conflicts(images, recordings):
    clashes = {"images": [], "recordings": []}
    for name in images:
        if vision.template_variant_paths(name):
            clashes["images"].append(name)
    for name in recordings:
        if tpl.recording_exists(name):
            clashes["recordings"].append(name)
    return clashes


def import_bundle(path: str, overwrite: bool = False) -> dict:
    """Unpack a bundle into the user's folders.

    With overwrite=False (the default) an image or recording whose name is
    already taken is SKIPPED rather than replaced -- importing someone else's
    macro must not quietly overwrite work of your own that happens to share a
    name. The report says exactly what was skipped.
    """
    info = inspect(path)
    conflicts = _existing_conflicts(info["images"], info["recordings"])
    report = {"ok": True, "macro": info["macro"], "manifest": info["manifest"],
              "images": [], "recordings": [],
              "skipped_images": [], "skipped_recordings": [], "rejected": []}

    skip_images = set() if overwrite else set(conflicts["images"])
    skip_recordings = set() if overwrite else set(conflicts["recordings"])

    assets_root = os.path.abspath(ASSETS_DIR)
    rec_root = os.path.abspath(RECORDINGS_DIR)

    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            parsed = _safe_member(member)
            if parsed is None:
                if member not in (MACRO_NAME, MANIFEST_NAME) and not member.endswith("/"):
                    report["rejected"].append(member)
                continue
            kind, name, filename = parsed

            if kind == "image":
                if name in skip_images:
                    if name not in report["skipped_images"]:
                        report["skipped_images"].append(name)
                    continue
                folder = os.path.join(ASSETS_DIR, name)
                target = os.path.join(folder, filename)
                # Belt and braces after the name sanitiser: never write
                # outside the folder this format is allowed to touch.
                if not naming.is_inside(target, assets_root):
                    report["rejected"].append(member)
                    continue
                os.makedirs(folder, exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(zf.read(member))
                if name not in report["images"]:
                    report["images"].append(name)

            else:
                if name in skip_recordings:
                    if name not in report["skipped_recordings"]:
                        report["skipped_recordings"].append(name)
                    continue
                target = os.path.join(RECORDINGS_DIR, name + ".json")
                if not naming.is_inside(target, rec_root):
                    report["rejected"].append(member)
                    continue
                try:
                    payload = json.loads(zf.read(member).decode("utf-8"))
                except ValueError:
                    report["rejected"].append(member)
                    continue
                os.makedirs(RECORDINGS_DIR, exist_ok=True)
                tpl.save_recording(name, payload.get("events") or [],
                                   payload.get("blocks"))
                report["recordings"].append(name)

    vision.clear_cache()
    return report
