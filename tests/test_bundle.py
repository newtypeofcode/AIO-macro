"""Shareable macro bundles: a macro plus exactly the images and recordings
it references.

Two things matter here. Completeness -- a bundle that is missing a
dependency fails on the recipient's first Click Image. And safety -- a bundle
is untrusted input, so it must not be able to write outside the two folders
this format owns, nor silently replace the recipient's own work.
"""
import json
import os
import sys
import zipfile

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, bundle, naming, vision
from core import templates as tpl


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolated Assets/ and Recordings/ for both the module under test and
    the modules it writes through."""
    assets = tmp_path / "Assets"
    recordings = tmp_path / "Recordings"
    assets.mkdir()
    recordings.mkdir()
    monkeypatch.setattr(bundle, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(bundle, "RECORDINGS_DIR", str(recordings))
    monkeypatch.setattr(vision, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(tpl, "RECORDINGS_DIR", str(recordings))
    vision.clear_cache()
    yield {"root": tmp_path, "assets": assets, "recordings": recordings}
    vision.clear_cache()


_image_seed = [0]


def make_image(workspace, name, variants=1):
    """Writes DIFFERENT bytes on every call, so "was it replaced?" is
    answerable. Uses imwrite_unicode: plain cv2.imwrite silently writes
    nothing at all when the path contains non-ASCII characters."""
    folder = workspace["assets"] / name
    folder.mkdir(parents=True, exist_ok=True)
    _image_seed[0] += 1
    rng = np.random.default_rng(_image_seed[0])
    for i in range(variants):
        patch = rng.integers(0, 255, (12, 16, 3), dtype=np.uint8)
        filename = "%s.png" % name if i == 0 else "%s_alt%d.png" % (name, i + 1)
        assert vision.imwrite_unicode(str(folder / filename), patch)
    vision.clear_cache()


def make_recording(name, events=None):
    return tpl.save_recording(name, events or [
        {"t": 0.0, "type": "key_down", "key": "w", "vk": 0x57}])


def macro_with(image=None, recording=None, nested_image=None, name="demo"):
    loop = []
    if image:
        loop.append(blocks.make_block("click_image", "a", {"template": image}))
    if recording:
        loop.append(blocks.make_block("playback", "b", {"recording": recording}))
    if nested_image:
        loop.append(blocks.make_block("wait_image", "c", {
            "template": "top_level_only" if not image else image,
            "on_fail": "run blocks",
            "on_fail_blocks": [
                blocks.make_block("click_image", "n", {"template": nested_image})],
        }))
    return {"name": name, "phases": {"setup": [], "loop": loop}}


# ------------------------------------------------------- dependency walking

def test_dependencies_finds_images_and_recordings():
    deps = bundle.dependencies(macro_with(image="btn", recording="run1"))
    assert deps["images"] == ["btn"]
    assert deps["recordings"] == ["run1"]


def test_dependencies_reaches_into_fallback_blocks():
    """A Click Image buried in an on-fail branch is just as much a dependency
    as one at the top level."""
    deps = bundle.dependencies(macro_with(image="btn", nested_image="deep"))
    assert "deep" in deps["images"], deps


def test_dependencies_ignores_empty_names():
    macro = {"phases": {"loop": [blocks.make_block("click_image", "a", {"template": ""})]}}
    assert bundle.dependencies(macro)["images"] == []


def test_dependencies_deduplicates():
    macro = {"phases": {"loop": [
        blocks.make_block("click_image", "a", {"template": "btn"}),
        blocks.make_block("wait_image", "b", {"template": "btn"})]}}
    assert bundle.dependencies(macro)["images"] == ["btn"]


def test_dependencies_of_an_empty_macro_are_empty():
    assert bundle.dependencies({}) == {"images": [], "recordings": []}
    assert bundle.dependencies(None) == {"images": [], "recordings": []}


# ------------------------------------------------------------------ export

def test_export_carries_every_variant_of_a_referenced_image(workspace):
    make_image(workspace, "btn", variants=3)
    path = str(workspace["root"] / "out.macrozip")
    report = bundle.export(macro_with(image="btn"), path)

    assert report["images"] == ["btn"]
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if m.startswith("assets/")]
    assert len(members) == 3, members


def test_export_carries_the_referenced_recording(workspace):
    make_recording("run1")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(recording="run1"), path)
    with zipfile.ZipFile(path) as zf:
        payload = json.loads(zf.read("recordings/run1.json").decode("utf-8"))
    assert payload["events"], payload


def test_export_includes_nothing_the_macro_does_not_use(workspace):
    """The user's other images must never ride along in a file they are about
    to hand to someone else."""
    make_image(workspace, "btn")
    make_image(workspace, "private_screenshot")
    make_recording("run1")
    make_recording("private_run")

    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="btn", recording="run1"), path)

    with zipfile.ZipFile(path) as zf:
        blob = "\n".join(zf.namelist())
    assert "private_screenshot" not in blob
    assert "private_run" not in blob


def test_export_reports_a_missing_dependency_rather_than_failing(workspace):
    path = str(workspace["root"] / "out.macrozip")
    report = bundle.export(macro_with(image="never_captured"), path)
    assert report["ok"] is True
    assert report["missing_images"] == ["never_captured"]
    assert os.path.isfile(path)


def test_the_manifest_records_what_went_in(workspace):
    make_image(workspace, "btn")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="btn", name="my macro"), path)
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["macro_name"] == "my macro"
    assert manifest["images"] == ["btn"]
    assert manifest["bundle_version"] == bundle.BUNDLE_VERSION


# ------------------------------------------------------------------ import

def test_a_bundle_round_trips(workspace):
    make_image(workspace, "btn", variants=2)
    make_recording("run1")
    macro = macro_with(image="btn", recording="run1")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro, path)

    # Wipe the workspace: this is the recipient's machine.
    import shutil
    shutil.rmtree(workspace["assets"])
    shutil.rmtree(workspace["recordings"])
    workspace["assets"].mkdir()
    workspace["recordings"].mkdir()
    vision.clear_cache()
    assert vision.template_variant_paths("btn") == []

    report = bundle.import_bundle(path)
    assert report["images"] == ["btn"]
    assert report["recordings"] == ["run1"]
    assert len(vision.template_variant_paths("btn")) == 2
    assert tpl.recording_exists("run1")
    assert report["macro"]["name"] == macro["name"]


def test_inspect_writes_nothing(workspace):
    make_image(workspace, "btn")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="btn"), path)

    import shutil
    shutil.rmtree(workspace["assets"])
    workspace["assets"].mkdir()
    vision.clear_cache()

    info = bundle.inspect(path)
    assert info["images"] == ["btn"]
    assert vision.template_variant_paths("btn") == [], "inspect must not write"


def test_an_existing_image_is_kept_not_overwritten(workspace):
    """Importing someone else's macro must not quietly replace work of your
    own that happens to share a name."""
    make_image(workspace, "btn")
    original = open(vision.template_variant_paths("btn")[0], "rb").read()

    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="btn"), path)

    # Replace ours with something different, then import.
    make_image(workspace, "btn")
    mine = open(vision.template_variant_paths("btn")[0], "rb").read()

    report = bundle.import_bundle(path, overwrite=False)
    assert report["skipped_images"] == ["btn"]
    assert open(vision.template_variant_paths("btn")[0], "rb").read() == mine
    assert original != mine, "fixture should have produced different bytes"


def test_overwrite_replaces_when_asked(workspace):
    make_image(workspace, "btn")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="btn"), path)
    exported = open(vision.template_variant_paths("btn")[0], "rb").read()

    make_image(workspace, "btn")          # different bytes now
    bundle.import_bundle(path, overwrite=True)
    assert open(vision.template_variant_paths("btn")[0], "rb").read() == exported


def test_an_existing_recording_is_kept_by_default(workspace):
    make_recording("run1", [{"t": 0.0, "type": "key_down", "key": "a", "vk": 0x41}])
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(recording="run1"), path)

    make_recording("run1", [{"t": 0.0, "type": "key_down", "key": "z", "vk": 0x5A}])
    report = bundle.import_bundle(path)
    assert report["skipped_recordings"] == ["run1"]
    assert tpl.load_recording("run1")["events"][0]["key"] == "z"


# ------------------------------------------------------------------ safety

def _forge(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("macro.json", json.dumps({"name": "x", "phases": {}}))
        for name, data in members:
            zf.writestr(name, data)


def test_a_traversal_path_is_refused(workspace):
    path = str(workspace["root"] / "evil.macrozip")
    _forge(path, [("assets/../../escaped/evil.png", b"\x89PNG"),
                  ("../outside.png", b"\x89PNG")])
    report = bundle.import_bundle(path)
    assert report["images"] == []
    assert len(report["rejected"]) == 2, report["rejected"]
    assert not (workspace["root"].parent / "outside.png").exists()
    assert not (workspace["root"] / "escaped").exists()


def test_an_absolute_path_is_refused(workspace):
    path = str(workspace["root"] / "evil.macrozip")
    _forge(path, [("/etc/passwd", b"x"), ("assets/a/b/c/deep.png", b"x")])
    report = bundle.import_bundle(path)
    assert report["images"] == []
    assert report["rejected"]


def test_a_non_png_asset_is_refused(workspace):
    """The format only ever writes images into Assets; anything else in that
    folder is somebody trying something."""
    path = str(workspace["root"] / "evil.macrozip")
    _forge(path, [("assets/x/payload.exe", b"MZ"),
                  ("assets/x/script.bat", b"@echo off")])
    report = bundle.import_bundle(path)
    assert report["images"] == []
    assert len(report["rejected"]) == 2


def test_a_dangerous_asset_name_is_refused(workspace):
    path = str(workspace["root"] / "evil.macrozip")
    _forge(path, [("assets/CON/x.png", b"\x89PNG"),
                  ("assets/../x.png", b"\x89PNG")])
    report = bundle.import_bundle(path)
    assert report["images"] == []


def test_a_corrupt_recording_is_refused_not_written(workspace):
    path = str(workspace["root"] / "evil.macrozip")
    _forge(path, [("recordings/broken.json", b"{ not json")])
    report = bundle.import_bundle(path)
    assert report["recordings"] == []
    assert "recordings/broken.json" in report["rejected"]
    assert not tpl.recording_exists("broken")


def test_a_zip_without_a_macro_is_rejected(workspace):
    path = str(workspace["root"] / "notabundle.zip")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(ValueError):
        bundle.inspect(path)


def test_safe_member_accepts_only_the_two_documented_shapes():
    assert bundle._safe_member("assets/btn/btn.png") == ("image", "btn", "btn.png")
    assert bundle._safe_member("recordings/run1.json") == ("recording", "run1", None)
    for bad in ("assets/btn.png", "assets/a/b/c.png", "recordings/a/b.json",
                "macro.json", "assets/x/y.txt", "/assets/x/y.png",
                "assets/../y/z.png", "recordings/x.txt"):
        assert bundle._safe_member(bad) is None, bad


def test_unicode_names_survive_a_round_trip(workspace):
    make_image(workspace, "кнопка старт")
    make_recording("моя запись")
    path = str(workspace["root"] / "out.macrozip")
    bundle.export(macro_with(image="кнопка старт", recording="моя запись"), path)

    import shutil
    shutil.rmtree(workspace["assets"])
    shutil.rmtree(workspace["recordings"])
    workspace["assets"].mkdir()
    workspace["recordings"].mkdir()
    vision.clear_cache()

    report = bundle.import_bundle(path)
    assert report["images"] == ["кнопка старт"]
    assert report["recordings"] == ["моя запись"]
    assert vision.template_variant_paths("кнопка старт")
