"""Regressions.

One test per bug that was actually found and fixed, named after the symptom
so a failure here says what broke rather than just where.
"""
import os
import sys
import threading
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, capture, keys, recorder, vision
from core import settings as smod


def _ev(t, type_, **kw):
    return dict(t=t, type=type_, **kw)


# --------------------------------------------------------------- recorder

def test_wait_before_a_key_is_not_measured_from_a_stale_timestamp():
    """The key_up branch used to call push_wait with the DOWN timestamp,
    which was older than the clock once other events had been processed. The
    gap went negative, last_t rewound, and every later wait was inflated."""
    events = [
        _ev(0.0, "key_down", key="w", vk=0x57),
        _ev(5.0, "mouse_down", button="left", x=1, y=1, sx=1, sy=1),
        _ev(5.05, "mouse_up", button="left", x=1, y=1, sx=1, sy=1),
        _ev(6.0, "key_up", key="w", vk=0x57),
        _ev(6.5, "mouse_down", button="left", x=2, y=2, sx=2, sy=2),
        _ev(6.55, "mouse_up", button="left", x=2, y=2, sx=2, sy=2),
    ]
    out = recorder.events_to_blocks(events)
    waits = [b["params"]["ms"] for b in out if b["type"] == "wait_ms"]
    # Total inserted delay can never exceed the real span of the recording.
    assert sum(waits) <= 6600, waits
    assert all(ms >= 0 for ms in waits), waits


def test_timeline_never_goes_backwards_for_interleaved_keys_and_clicks():
    events = []
    for i in range(4):
        base = i * 1.0
        events += [
            _ev(base, "key_down", key="a", vk=0x41, char="a"),
            _ev(base + 0.7, "mouse_down", button="left", x=i, y=i, sx=i, sy=i),
            _ev(base + 0.75, "mouse_up", button="left", x=i, y=i, sx=i, sy=i),
            _ev(base + 0.8, "key_up", key="a", vk=0x41, char="a"),
        ]
    out = recorder.events_to_blocks(events)
    waits = [b["params"]["ms"] for b in out if b["type"] == "wait_ms"]
    assert all(ms >= 0 for ms in waits)
    assert sum(waits) <= 4000, waits


def test_a_long_press_becomes_hold_key_not_an_uninterruptible_send_key():
    """send_key's hold is a plain sleep, so a 30s recorded press would make
    Stop unresponsive for 30 seconds."""
    out = recorder.events_to_blocks([
        _ev(0.0, "key_down", key="w", vk=0x57),
        _ev(30.0, "key_up", key="w", vk=0x57),
    ])
    holds = [b for b in out if b["type"] == "hold_key"]
    assert len(holds) == 1
    assert holds[0]["params"]["hold_ms"] == 30000
    assert not [b for b in out if b["type"] == "send_key"]


def test_a_short_press_stays_a_send_key():
    out = recorder.events_to_blocks([
        _ev(0.0, "key_down", key="w", vk=0x57),
        _ev(0.2, "key_up", key="w", vk=0x57),
    ])
    assert [b["type"] for b in out] == ["send_key"]


def test_one_lost_key_up_does_not_disable_that_key_forever():
    """Auto-repeat suppression used to keep the key 'open' after a dropped
    release, so every later press of it was silently ignored."""
    events = [
        _ev(0.0, "key_down", key="a", vk=0x41, char="a"),   # release lost
        _ev(1.0, "key_down", key="a", vk=0x41, char="a"),
        _ev(1.1, "key_up", key="a", vk=0x41, char="a"),
        _ev(2.0, "key_down", key="a", vk=0x41, char="a"),
        _ev(2.1, "key_up", key="a", vk=0x41, char="a"),
    ]
    out = recorder.events_to_blocks(events)
    presses = [b for b in out if b["type"] in ("send_key", "hold_key")]
    assert len(presses) == 3, [b["type"] for b in out]


def test_an_unclosed_mouse_down_does_not_swallow_every_later_move():
    """A press whose release was lost used to swallow every subsequent move
    for the rest of the recording."""
    past_dangling = recorder.DANGLING_DOWN_S + 1
    events = [
        _ev(0.0, "mouse_down", button="left", x=1, y=1, sx=1, sy=1),   # no up
        _ev(past_dangling, "move", x=50, y=50, sx=50, sy=50),
        _ev(past_dangling + 1, "move", x=90, y=90, sx=90, sy=90),
    ]
    out = recorder.events_to_blocks(events, keep_moves=True)
    types = [b["type"] for b in out]
    assert "click" in types, types
    assert types.count("move") == 2, types


def test_moves_during_a_genuine_drag_are_still_absorbed():
    events = [
        _ev(0.0, "mouse_down", button="left", x=1, y=1, sx=1, sy=1),
        _ev(0.2, "move", x=40, y=40, sx=40, sy=40),
        _ev(0.4, "mouse_up", button="left", x=80, y=80, sx=80, sy=80),
    ]
    out = recorder.events_to_blocks(events, keep_moves=True)
    assert [b["type"] for b in out] == ["drag"]


def test_a_still_held_button_at_the_end_is_not_lost():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=7, y=8, sx=7, sy=8),
    ])
    assert [b["type"] for b in out] == ["click"]
    assert out[0]["params"]["x"] == 7


def test_absorbed_waits_survive_when_a_text_run_does_not_fold():
    """Two characters is below the fold threshold, so the wait between them
    must reappear -- dropping it silently destroyed the recording's timing."""
    events = []
    for i, ch in enumerate("ab"):
        events.append(_ev(i * 0.3, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(i * 0.3 + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    types = [b["type"] for b in out]
    assert types.count("send_key") == 2
    assert "wait_ms" in types, types


def test_the_wait_after_a_folded_text_run_survives():
    events = []
    for i, ch in enumerate("hello"):
        events.append(_ev(i * 0.2, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(i * 0.2 + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    # A click a moment later -- the pause before it must not vanish with the fold.
    events.append(_ev(1.5, "mouse_down", button="left", x=1, y=1, sx=1, sy=1))
    events.append(_ev(1.55, "mouse_up", button="left", x=1, y=1, sx=1, sy=1))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    types = [b["type"] for b in out]
    assert types.count("type_text") == 1
    assert "wait_ms" in types, types
    assert types.index("type_text") < types.index("wait_ms") < types.index("click")


def test_a_discarded_leading_move_does_not_create_a_phantom_first_wait():
    """The recorder's clock starts at the first event of any kind, so a
    stray mouse movement before the first real action showed up as a wait
    at the very start of the macro."""
    events = [
        _ev(0.0, "move", x=5, y=5, sx=5, sy=5),
        _ev(3.0, "mouse_down", button="left", x=9, y=9, sx=9, sy=9),
        _ev(3.05, "mouse_up", button="left", x=9, y=9, sx=9, sy=9),
    ]
    out = recorder.events_to_blocks(events, keep_moves=False)
    assert [b["type"] for b in out] == ["click"], [b["type"] for b in out]


def test_a_kept_leading_move_still_starts_immediately():
    events = [
        _ev(0.0, "move", x=5, y=5, sx=5, sy=5),
        _ev(3.0, "mouse_down", button="left", x=9, y=9, sx=9, sy=9),
        _ev(3.05, "mouse_up", button="left", x=9, y=9, sx=9, sy=9),
    ]
    out = recorder.events_to_blocks(events, keep_moves=True)
    assert out[0]["type"] == "move"
    assert [b["type"] for b in out] == ["move", "wait_ms", "click"]


def test_move_throttle_default_is_above_the_min_gap_default():
    """Throttling moves faster than the gap filter means no wait is ever
    inserted between them and the whole path replays instantly."""
    assert smod.DEFAULTS["record_move_interval_ms"] > 60


# ------------------------------------------------------------------- keys

@pytest.mark.parametrize("ch", ["!", "#", "$", "%", "&", "(", ")"])
def test_shifted_punctuation_is_not_mapped_to_a_navigation_key(ch):
    """ord() as a blanket fallback mapped '!' to 0x21 (Page Up), '%' to 0x25
    (Left arrow) and so on -- a completely different key."""
    vk = keys.key_name_to_vk(ch)
    navigation = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29}
    assert vk is None or vk not in navigation, (ch, vk)


def test_letters_and_digits_still_use_their_ascii_codes():
    assert keys.key_name_to_vk("a") == 0x41
    assert keys.key_name_to_vk("7") == 0x37


def test_canonical_key_names_are_stable():
    """These names are written into saved recordings, so which alias wins
    must not depend on dict ordering."""
    assert keys.vk_to_key_name(0x1B) == "escape"
    assert keys.vk_to_key_name(0x0D) == "enter"
    assert keys.vk_to_key_name(0x11) == "ctrl"
    # Left/right variants collapse so a recording replays on either.
    assert keys.vk_to_key_name(0xA0) == keys.vk_to_key_name(0xA1) == "shift"


# ----------------------------------------------------------------- blocks

def test_mutable_defaults_are_not_shared_between_blocks():
    """`modifiers` defaults to a literal [] in the catalog; handing it out by
    reference let one block's edit rewrite the catalog and every other block."""
    a = blocks.make_block("send_key", "a")
    b = blocks.make_block("send_key", "b")
    a["params"]["modifiers"].append("shift")
    assert b["params"]["modifiers"] == []
    assert blocks.BY_TYPE["send_key"]["fields"][2]["default"] == []


def test_every_field_kind_is_declared_renderable():
    for spec in blocks.catalog():
        for field in spec["fields"]:
            assert field["kind"] in blocks.FIELD_KINDS, (spec["type"], field)


def test_phase_constants_match_the_phase_tuple():
    assert blocks.PHASE_ONCE in blocks.PHASES
    assert blocks.PHASE_REPEAT in blocks.PHASES
    assert blocks.PHASE_ONCE != blocks.PHASE_REPEAT


def test_every_block_and_field_has_hover_help():
    """The UI renders these as tooltips; a missing one is an empty popup."""
    for spec in blocks.catalog():
        assert spec.get("desc"), "block %s has no description" % spec["type"]
        for field in spec["fields"]:
            assert field.get("help") is not None, (spec["type"], field["key"])
            if field["key"] not in ("region",):
                assert field["help"], "%s.%s has no help" % (spec["type"], field["key"])


def test_every_block_summarises_to_something_readable():
    """summarise() feeds the activity log, so it must never fall through to
    a raw dict or crash on an empty block."""
    for spec in blocks.catalog():
        block = blocks.make_block(spec["type"], "x")
        text = blocks.summarise(block)
        assert isinstance(text, str) and text.strip()
        assert "{" not in text and "params" not in text, (spec["type"], text)


def test_summaries_read_like_actions_not_key_value_dumps():
    assert blocks.summarise(blocks.make_block(
        "click", "a", {"x": 640, "y": 360, "clicks": 2})) == "Click 640,360 (left x2)"
    assert blocks.summarise(blocks.make_block(
        "send_key", "a", {"key": "c", "modifiers": ["ctrl"]})) == "Key ctrl+c"
    assert blocks.summarise(blocks.make_block("wait_ms", "a", {"ms": 250})) == "Wait 250ms"


def test_a_long_typed_string_is_truncated_in_the_log():
    text = "x" * 200
    summary = blocks.summarise(blocks.make_block("type_text", "a", {"text": text}))
    assert len(summary) < 60, summary
    assert summary.endswith("...'")


def test_every_vision_wait_block_can_fail_the_macro():
    for spec in blocks.catalog():
        if spec["type"].startswith("wait_") and spec["group"] == "Vision":
            keys_ = {f["key"] for f in spec["fields"]}
            assert "on_fail" in keys_, spec["type"]


# --------------------------------------------------------------- settings

def test_non_object_settings_file_does_not_crash_startup(tmp_path, monkeypatch):
    for content in ("null", '"just a string"', "[1,2,3]", "42"):
        path = tmp_path / "settings.json"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(smod, "SETTINGS_FILE", str(path))
        loaded = smod.load()
        assert isinstance(loaded, dict)
        assert loaded["action_delay_ms"] == smod.DEFAULTS["action_delay_ms"]


def test_failed_save_is_reported_not_swallowed(tmp_path, monkeypatch):
    # A directory where the settings file should be makes the write fail.
    target = tmp_path / "settings.json"
    target.mkdir()
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(target))
    assert smod.update({"x": 1}).get("_saved") is False


# ----------------------------------------------------------------- vision

def test_a_resaved_reference_image_is_picked_up_without_a_restart(tmp_path, monkeypatch):
    import cv2
    monkeypatch.setattr(vision, "ASSETS_DIR", str(tmp_path))
    vision.clear_cache()

    scene = np.full((200, 300, 3), 30, dtype=np.uint8)
    cv2.rectangle(scene, (120, 60), (170, 90), (200, 40, 40), -1)
    cv2.putText(scene, "OK", (128, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    folder = tmp_path / "btn"
    folder.mkdir()
    path = str(folder / "btn.png")
    # First save: textured noise, which cannot match anything in the scene.
    # (A FLAT patch would -- two uniform regions correlate perfectly.)
    rng = np.random.default_rng(1)
    cv2.imwrite(path, rng.integers(0, 255, (24, 40, 3), dtype=np.uint8))
    vision.clear_cache()
    assert vision.find_in_frame(scene, "btn") is None

    time.sleep(0.02)
    # Re-save the SAME path with the real crop, as the Image Manager does.
    cv2.imwrite(path, scene[60:90, 120:170].copy())
    assert vision.find_in_frame(scene, "btn") is not None, \
        "cache keyed on path alone ignored the new pixels"
    vision.clear_cache()


@pytest.mark.parametrize("name", ["иконка", "кнопка старт", "ボタン", "café"])
def test_a_non_ascii_template_name_actually_saves_and_matches(name, tmp_path, monkeypatch):
    """cv2.imwrite hands the filename to the C runtime as bytes, so a
    Cyrillic name wrote nothing at all while the app reported success --
    the user's first real action with the app hit exactly this."""
    import cv2
    monkeypatch.setattr(vision, "ASSETS_DIR", str(tmp_path))
    vision.clear_cache()

    scene = np.full((200, 300, 3), 30, dtype=np.uint8)
    cv2.rectangle(scene, (120, 60), (170, 90), (200, 40, 40), -1)
    cv2.putText(scene, "OK", (128, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    folder = tmp_path / name
    folder.mkdir()
    path = str(folder / (name + ".png"))
    assert vision.imwrite_unicode(path, scene[60:90, 120:170].copy())
    assert os.path.isfile(path)
    assert vision.imread_unicode(path) is not None

    vision.clear_cache()
    match = vision.find_in_frame(scene, name)
    assert match is not None and match["score"] > 0.95
    vision.clear_cache()


@pytest.mark.parametrize("name", ["моя запись", "запись 2", "テスト", "run (1)"])
def test_a_recording_keeps_its_name_in_any_language(name, tmp_path, monkeypatch):
    """The old ASCII-only filter collapsed every Cyrillic name to the same
    fallback, so two differently-named recordings silently overwrote each
    other."""
    from core import templates as tpl
    monkeypatch.setattr(tpl, "RECORDINGS_DIR", str(tmp_path))
    events = [{"t": 0.0, "type": "key_down", "key": "w", "vk": 0x57}]
    assert tpl.save_recording(name, events) == name
    assert name in tpl.list_recordings()
    assert tpl.load_recording(name)["events"] == events


def test_two_different_russian_names_do_not_collide(tmp_path, monkeypatch):
    from core import templates as tpl
    monkeypatch.setattr(tpl, "RECORDINGS_DIR", str(tmp_path))
    tpl.save_recording("первая", [{"t": 0.0, "type": "key_down", "key": "a"}])
    tpl.save_recording("вторая", [{"t": 0.0, "type": "key_down", "key": "b"}])
    assert sorted(tpl.list_recordings()) == ["вторая", "первая"]
    assert tpl.load_recording("первая")["events"][0]["key"] == "a"
    assert tpl.load_recording("вторая")["events"][0]["key"] == "b"


def test_macro_names_keep_unicode_too(tmp_path, monkeypatch):
    from core import templates as tpl
    monkeypatch.setattr(tpl, "TEMPLATES_DIR", str(tmp_path))
    assert tpl.save_macro("мой макрос", {"phases": {"setup": [], "loop": []}}) == "мой макрос"
    assert "мой макрос" in tpl.list_macros()


def test_name_sanitiser_still_blocks_traversal_and_devices():
    from core.naming import safe_name
    assert safe_name("../../evil") == "evil"
    assert "/" not in safe_name("a/b") and "\\" not in safe_name("a\\b")
    assert safe_name("", "fallback") == "fallback"
    assert safe_name("..", "fallback") == "fallback"
    assert safe_name("CON", "fallback") == "fallback"
    assert safe_name('bad<>:"|?*name') == "badname"
    assert len(safe_name("x" * 500)) <= 80


def test_template_name_sanitiser_keeps_unicode_but_blocks_traversal():
    import main
    safe = main.Api._safe_template_name
    assert safe("иконка") == "иконка"
    assert safe("кнопка старт") == "кнопка старт"
    # Separators removed, then the leading dots stripped: no way out of Assets/.
    assert safe("../../evil") == "evil"
    assert "/" not in safe("a/b") and "\\" not in safe("a\\b")
    assert safe("") == ""
    assert safe("..") == ""
    assert safe("CON") == ""                          # reserved device name
    assert safe('bad<>:"|?*name') == "badname"


def test_find_image_any_accepts_a_generator(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "ASSETS_DIR", str(tmp_path))
    vision.clear_cache()
    with pytest.raises(vision.TemplateNotFound):
        vision.find_image_any(0, (n for n in ("nope_a", "nope_b")))
    vision.clear_cache()


# ---------------------------------------------------------------- capture

def test_out_of_frame_region_returns_none_instead_of_wrong_pixels(monkeypatch):
    """Clamping an out-of-frame region returned pixels from a different place
    while the caller added back the UNCLAMPED origin, so every reported
    coordinate was wrong."""
    from core import window as wm

    class FakeShot:
        def __init__(self, w, h):
            self.width, self.height = w, h
            # Non-zero: an all-black frame is treated as a failed capture.
            self.raw = bytes([77]) * (w * h * 4)

    class FakeMSS:
        def grab(self, box):
            return FakeShot(box["width"], box["height"])

        def close(self):
            pass

    # Pretend hwnd 1234 is a live 200x150 window so the window-relative
    # region path (the one that used to clamp) is the one exercised.
    monkeypatch.setattr(wm, "is_window", lambda h: True)
    monkeypatch.setattr(wm, "capture_window_rgb", lambda h: None)
    monkeypatch.setattr(wm, "get_client_rect_screen", lambda h: (0, 0, 200, 150))
    capture.set_mss_factory(FakeMSS)
    capture.force_window_capture(False)
    try:
        capture.close_mss()
        assert capture.capture_target_bgr(1234, (10, 10, 20, 20)) is not None
        # Origin past the right/bottom edge: no honest pixels exist there.
        assert capture.capture_target_bgr(1234, (500, 500, 10, 10)) is None
        assert capture.capture_target_bgr(1234, (-5, 0, 10, 10)) is None
    finally:
        capture.set_mss_factory(None)
        capture.close_mss()
