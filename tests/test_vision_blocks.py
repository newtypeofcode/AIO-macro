"""Click Text and Click Color -- the coordinate-free vision blocks."""
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, capture, ocr, vision


@pytest.fixture
def button_scene():
    scene = np.full((300, 620, 3), 24, dtype=np.uint8)
    for label, x, y in (("Continue", 40, 40), ("Settings", 40, 130),
                        ("Exit Game", 40, 220)):
        cv2.rectangle(scene, (x, y), (x + 250, y + 56), (60, 60, 68), -1)
        cv2.putText(scene, label, (x + 18, y + 38), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (240, 240, 240), 2)
    return scene


ocr_needed = pytest.mark.skipif(ocr.engine_name() == "none",
                                reason="no OCR engine on this machine")


@pytest.fixture
def english_catalog():
    """Field labels are translated, so a test that reads one has to say
    which language it means -- the catalog carries whatever the last test
    to touch it left behind."""
    before = blocks.get_language()
    blocks.set_language("en")
    yield
    blocks.set_language(before)


# --------------------------------------------------------------- catalog

def test_the_new_blocks_are_in_the_catalog():
    types = {spec["type"] for spec in blocks.catalog()}
    assert "click_text" in types
    assert "click_color" in types


def test_the_new_blocks_have_handlers():
    from core.runner import MacroRunner
    assert hasattr(MacroRunner, "_do_click_text")
    assert hasattr(MacroRunner, "_do_click_color")


def test_every_matching_vision_block_offers_confidence(english_catalog):
    """Images, text and colour all match approximately, so they all expose the
    same 0-1 knob under the same name. Read Text is excluded: it reports what
    it sees rather than deciding whether something matched."""
    for spec in blocks.catalog():
        if spec["group"] != "Vision" or spec["type"] == "read_text":
            continue
        labels = {f["label"] for f in spec["fields"]}
        assert "Confidence" in labels, spec["type"]


def test_confidence_is_a_zero_to_one_float_everywhere(english_catalog):
    for spec in blocks.catalog():
        if spec["group"] != "Vision":
            continue
        for field in spec["fields"]:
            if field["label"] != "Confidence":
                continue
            assert field["kind"] == "float", spec["type"]
            assert 0.0 < field["default"] <= 1.0, (spec["type"], field["default"])


def test_image_confidence_keeps_its_old_param_name():
    # Renaming the label is cosmetic; renaming the key would break every
    # macro saved before the change.
    for name in ("wait_image", "click_image", "wait_image_gone"):
        keys = {f["key"] for f in blocks.BY_TYPE[name]["fields"]}
        assert "threshold" in keys, name


def test_every_block_owns_its_field_dicts():
    """Splicing one shared list of field dicts into several blocks reuses the
    SAME objects. The help text is written into those dicts per block, so the
    last block processed won and every image and colour block ended up
    showing "if the text is not found"."""
    seen = {}
    for spec in blocks.catalog():
        for field in spec["fields"]:
            owner = seen.get(id(field))
            assert owner is None, \
                "%s and %s share the same '%s' field object" \
                % (owner, spec["type"], field["key"])
            seen[id(field)] = spec["type"]


@pytest.mark.parametrize("block_type,expect", [
    ("wait_image", "image"), ("click_image", "image"),
    ("wait_image_gone", "image"),
    ("wait_color", "colour"), ("click_color", "colour"),
    ("wait_text", "text"), ("click_text", "text"),
])
def test_each_block_gets_its_own_on_fail_wording(english_catalog, block_type,
                                                 expect):
    from core import blocks as blockmod
    for language in ("en", "ru"):
        blockmod.set_language(language)
        field = [f for f in blockmod.BY_TYPE[block_type]["fields"]
                 if f["key"] == "on_fail"][0]
        assert field["help"], (block_type, language)
    blockmod.set_language("en")
    field = [f for f in blocks.BY_TYPE[block_type]["fields"]
             if f["key"] == "on_fail"][0]
    assert expect in field["help"].lower(), (block_type, field["help"][:70])


def test_colour_blocks_no_longer_expose_a_raw_tolerance():
    for name in ("wait_color", "click_color"):
        keys = {f["key"] for f in blocks.BY_TYPE[name]["fields"]}
        assert "tolerance" not in keys, name
        assert "confidence" in keys, name


def test_the_new_blocks_summarise_readably():
    assert blocks.summarise(blocks.make_block(
        "click_text", "a", {"text": "Continue"})) == "Click text 'Continue'"
    assert blocks.summarise(blocks.make_block(
        "click_color", "a", {"color": "#ff0000"})) == "Click colour #ff0000"


# ------------------------------------------------------------- find_text

@ocr_needed
def test_text_is_located_on_its_own_button(button_scene):
    for label, x, y in (("Continue", 40, 40), ("Settings", 40, 130),
                        ("Exit Game", 40, 220)):
        hit = ocr.find_text(button_scene, label)
        assert hit is not None, label
        assert x <= hit["cx"] <= x + 250, (label, hit)
        assert y <= hit["cy"] <= y + 56, (label, hit)


@ocr_needed
def test_a_literal_substring_is_accepted_at_any_confidence(button_scene):
    """If the recognised line really contains the text, no threshold should
    be able to argue with that."""
    assert ocr.find_text(button_scene, "Continu", confidence=0.99) is not None


@ocr_needed
def test_confidence_gates_the_fuzzy_path(button_scene):
    assert ocr.find_text(button_scene, "Xontinue", confidence=0.7) is not None
    assert ocr.find_text(button_scene, "Xontinue", confidence=0.99) is None


@ocr_needed
def test_unrelated_text_is_not_found(button_scene):
    assert ocr.find_text(button_scene, "Completely Different Words") is None


def test_find_text_on_an_empty_frame_is_a_miss():
    assert ocr.find_text(None, "x") is None
    assert ocr.find_text(np.zeros((0, 0, 3), dtype=np.uint8), "x") is None
    assert ocr.find_text(np.full((40, 40, 3), 10, dtype=np.uint8), "") is None


# ---------------------------------------------------------- find_colour

@pytest.fixture
def colour_scene(monkeypatch):
    scene = np.full((200, 300, 3), 20, dtype=np.uint8)
    cv2.circle(scene, (210, 70), 26, (40, 40, 220), -1)     # BGR: red
    monkeypatch.setattr(capture, "capture_target_bgr",
                        lambda hwnd=None, region=None: scene)
    return scene


def test_a_colour_blob_is_found_at_its_centre(colour_scene):
    found = vision.find_color_region(0, None, (220, 40, 40), 24, 40)
    assert found is not None
    assert abs(found["cx"] - 210) <= 4 and abs(found["cy"] - 70) <= 4
    assert found["area"] > 1500


def test_an_absent_colour_is_not_found(colour_scene):
    assert vision.find_color_region(0, None, (0, 255, 0), 10, 40) is None


def test_min_pixels_rejects_a_blob_that_is_too_small(colour_scene):
    assert vision.find_color_region(0, None, (220, 40, 40), 24, 99999) is None


def test_tolerance_widens_the_match(colour_scene):
    # A colour close to but not exactly the circle's.
    assert vision.find_color_region(0, None, (200, 60, 60), 2, 40) is None
    assert vision.find_color_region(0, None, (200, 60, 60), 40, 40) is not None
