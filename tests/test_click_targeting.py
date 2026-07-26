"""Where do the coordinate-free click blocks actually click?

The mouse is stubbed, so these run safely while you are using the machine.
What is verified is the arithmetic: region origin + match centre + offset,
translated into the target's coordinate space.
"""
import os
import sys
import time

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, capture, ocr, vision
from core.runner import MacroRunner

ocr_needed = pytest.mark.skipif(ocr.engine_name() == "none",
                                reason="no OCR engine on this machine")


class StubMouse:
    """Records clicks instead of performing them."""

    def __init__(self):
        self.clicks = []

    def click(self, x=None, y=None, button="left", hold=0.04, pace=True):
        self.clicks.append((x, y, button))

    def multi_click(self, x=None, y=None, button="left", count=1, hold=0.04, gap=0.07):
        self.clicks.append((x, y, button))

    def move_to(self, x, y):
        pass

    def up(self, button="left"):
        pass

    def down(self, button="left"):
        pass

    def scroll(self, amount, horizontal=False):
        pass

    def position(self):
        return (0, 0)


def run_block(block, frame, monkeypatch, region_aware=True):
    """Execute one block against a fixed frame with the mouse stubbed."""
    def fake_capture(hwnd=None, region=None):
        if region and region_aware:
            x, y, w, h = [int(v) for v in region]
            return frame[y:y + h, x:x + w].copy()
        return frame

    monkeypatch.setattr(capture, "capture_target_bgr", fake_capture)

    lines = []
    runner = MacroRunner(log=lines.append, set_status=lambda **k: None)
    stub = StubMouse()
    runner.mouse = stub
    runner.start({"phases": {"setup": [block], "loop": []}},
                 hwnd=0, coord_space="screen", loop_forever=False, loop_count=1)
    deadline = time.time() + 20
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running()
    return stub.clicks, lines


@pytest.fixture
def button_scene():
    scene = np.full((300, 620, 3), 24, dtype=np.uint8)
    for label, x, y in (("Continue", 40, 40), ("Settings", 40, 130)):
        cv2.rectangle(scene, (x, y), (x + 250, y + 56), (60, 60, 68), -1)
        cv2.putText(scene, label, (x + 18, y + 38), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (240, 240, 240), 2)
    return scene


# ---------------------------------------------------------------- text

@ocr_needed
def test_click_text_clicks_inside_the_right_button(button_scene, monkeypatch):
    block = blocks.make_block("click_text", "a", {"text": "Settings",
                                                   "timeout_ms": 3000})
    clicks, _ = run_block(block, button_scene, monkeypatch)
    assert len(clicks) == 1
    x, y, button = clicks[0]
    assert 40 <= x <= 290 and 130 <= y <= 186, clicks
    assert button == "left"


@ocr_needed
def test_click_text_picks_the_named_button_not_the_other_one(button_scene, monkeypatch):
    clicks, _ = run_block(blocks.make_block(
        "click_text", "a", {"text": "Continue", "timeout_ms": 3000}),
        button_scene, monkeypatch)
    assert 40 <= clicks[0][1] <= 96, clicks   # the top button's y range


@ocr_needed
def test_click_text_applies_the_offset(button_scene, monkeypatch):
    plain, _ = run_block(blocks.make_block(
        "click_text", "a", {"text": "Continue", "timeout_ms": 3000}),
        button_scene, monkeypatch)
    shifted, _ = run_block(blocks.make_block(
        "click_text", "a", {"text": "Continue", "timeout_ms": 3000,
                             "offset_x": 25, "offset_y": -10}),
        button_scene, monkeypatch)
    assert shifted[0][0] == plain[0][0] + 25
    assert shifted[0][1] == plain[0][1] - 10


@ocr_needed
def test_click_text_adds_back_the_region_origin(button_scene, monkeypatch):
    """The frame handed to OCR is a CROP, so its coordinates are relative to
    the region -- forgetting to add the origin back clicks the wrong place."""
    region = [30, 120, 300, 80]
    cropped, _ = run_block(blocks.make_block(
        "click_text", "a", {"text": "Settings", "timeout_ms": 3000,
                             "region": region}),
        button_scene, monkeypatch)
    assert cropped, "text not found inside the region"
    x, y, _button = cropped[0]
    # Lands on the Settings button. Compared against the button's real
    # bounds rather than the un-cropped run: OCR's line box shifts by a few
    # pixels when the input size changes, which is noise, whereas a missing
    # origin would be off by the region's 120px top edge.
    assert 40 <= x <= 290, cropped
    assert 130 <= y <= 186, cropped
    # And the origin really was added: without it the click would land at
    # y - 120, well above the button.
    assert y - region[1] < 130, "region origin was not added back"


@ocr_needed
def test_click_text_that_finds_nothing_clicks_nothing(button_scene, monkeypatch):
    clicks, lines = run_block(blocks.make_block(
        "click_text", "a", {"text": "No Such Label Here", "timeout_ms": 400}),
        button_scene, monkeypatch)
    assert clicks == []
    assert any("not found" in line for line in lines)


@ocr_needed
def test_click_text_on_fail_stop_ends_the_run(button_scene, monkeypatch):
    block = blocks.make_block("click_text", "a", {
        "text": "Nothing", "timeout_ms": 300, "on_fail": "stop"})
    clicks, lines = run_block(block, button_scene, monkeypatch)
    assert clicks == []


# --------------------------------------------------------------- colour

@pytest.fixture
def colour_scene():
    scene = np.full((200, 300, 3), 20, dtype=np.uint8)
    cv2.circle(scene, (210, 70), 26, (40, 40, 220), -1)     # BGR red
    return scene


def test_click_color_clicks_the_blob_centre(colour_scene, monkeypatch):
    clicks, _ = run_block(blocks.make_block("click_color", "a", {
        "color": "#dc2828", "confidence": 0.88, "timeout_ms": 2000}),
        colour_scene, monkeypatch)
    assert len(clicks) == 1
    x, y, _button = clicks[0]
    assert abs(x - 210) <= 5 and abs(y - 70) <= 5, clicks


def test_click_color_applies_the_offset(colour_scene, monkeypatch):
    clicks, _ = run_block(blocks.make_block("click_color", "a", {
        "color": "#dc2828", "confidence": 0.88, "timeout_ms": 2000,
        "offset_x": 12, "offset_y": 7}), colour_scene, monkeypatch)
    assert abs(clicks[0][0] - 222) <= 5 and abs(clicks[0][1] - 77) <= 5


def test_click_color_respects_the_button_choice(colour_scene, monkeypatch):
    clicks, _ = run_block(blocks.make_block("click_color", "a", {
        "color": "#dc2828", "confidence": 0.88, "timeout_ms": 2000,
        "button": "right"}), colour_scene, monkeypatch)
    assert clicks[0][2] == "right"


def test_click_color_that_finds_nothing_clicks_nothing(colour_scene, monkeypatch):
    clicks, lines = run_block(blocks.make_block("click_color", "a", {
        "color": "#00ff00", "confidence": 0.99, "timeout_ms": 400}),
        colour_scene, monkeypatch)
    assert clicks == []
    assert any("not found" in line for line in lines)


# ------------------------------------------------- confidence <-> tolerance

def test_higher_confidence_demands_a_closer_colour(colour_scene, monkeypatch):
    """A colour near but not equal to the circle's: loose confidence finds
    it, strict confidence does not."""
    near = {"color": "#c83c3c", "timeout_ms": 400}
    loose, _ = run_block(blocks.make_block(
        "click_color", "a", dict(near, confidence=0.80)), colour_scene, monkeypatch)
    strict, _ = run_block(blocks.make_block(
        "click_color", "a", dict(near, confidence=0.995)), colour_scene, monkeypatch)
    assert loose, "0.80 should have matched a near colour"
    assert strict == [], "0.995 should have rejected it"


def test_a_macro_saved_with_the_old_tolerance_still_works(colour_scene, monkeypatch):
    """Colour matching used to be a raw 0-255 `tolerance`. Macros saved then
    must keep behaving exactly as before."""
    legacy = blocks.make_block("click_color", "a", {
        "color": "#dc2828", "timeout_ms": 2000})
    legacy["params"]["tolerance"] = 30          # as an old file would carry it
    clicks, _ = run_block(legacy, colour_scene, monkeypatch)
    assert len(clicks) == 1
    assert abs(clicks[0][0] - 210) <= 5


def test_the_legacy_tolerance_wins_over_the_new_default(colour_scene, monkeypatch):
    legacy = blocks.make_block("click_color", "a", {
        "color": "#00ff00", "timeout_ms": 400})
    legacy["params"]["tolerance"] = 0           # exact green: not in the scene
    clicks, _ = run_block(legacy, colour_scene, monkeypatch)
    assert clicks == []


@pytest.mark.parametrize("confidence,expected", [
    (1.0, 0), (0.9, 26), (0.8, 51), (0.0, 255),
])
def test_confidence_maps_onto_the_per_channel_tolerance(confidence, expected):
    from core.runner import MacroRunner
    runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)
    got = runner._colour_tolerance({"confidence": confidence}, 0.9)
    assert abs(got - expected) <= 1, (confidence, got)


def test_a_junk_confidence_falls_back_to_the_default():
    from core.runner import MacroRunner
    runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)
    assert runner._colour_tolerance({"confidence": "nonsense"}, 0.9) == \
        runner._colour_tolerance({}, 0.9)
    # And a value outside 0-1 is clamped rather than producing a silly range.
    assert runner._colour_tolerance({"confidence": 5}, 0.9) == 0
    assert runner._colour_tolerance({"confidence": -2}, 0.9) == 255
