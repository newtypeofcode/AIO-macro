"""Unit tests -- no GUI, no synthetic input, safe to run anywhere on Windows.

Run with:  python -m pytest tests/ -v
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, constants, keys, recorder, templates, vision
from core import settings as smod


# ------------------------------------------------------------------- keys

@pytest.mark.parametrize("name,vk", [
    ("w", 0x57), ("a", 0x41), ("5", 0x35),
    ("f5", 0x74), ("f12", 0x7B),
    ("escape", 0x1B), ("esc", 0x1B), ("enter", 0x0D), ("space", 0x20),
    ("left", 0x25), ("arrowleft", 0x25), ("delete", 0x2E),
    (",", 0xBC), ("/", 0xBF), ("[", 0xDB),
])
def test_key_name_to_vk(name, vk):
    assert keys.key_name_to_vk(name) == vk


def test_key_name_to_vk_is_case_insensitive():
    assert keys.key_name_to_vk("F5") == keys.key_name_to_vk("f5")
    assert keys.key_name_to_vk("W") == keys.key_name_to_vk("w")


@pytest.mark.parametrize("junk", ["", None, "not-a-key", "  "])
def test_key_name_to_vk_returns_none_not_raises(junk):
    # An unbound hotkey must be a silent no-op, never a crash mid-run.
    assert keys.key_name_to_vk(junk) is None


@pytest.mark.parametrize("name", ["w", "a", "f5", "escape", "left", ","])
def test_vk_name_roundtrip(name):
    assert keys.vk_to_key_name(keys.key_name_to_vk(name)) == name


# ----------------------------------------------------------------- blocks

def test_every_catalog_type_has_a_runner_handler():
    from core.runner import MacroRunner
    handlers = {n[4:] for n in dir(MacroRunner) if n.startswith("_do_")}
    flow_only = {"loop_start", "loop_end"}  # handled inline by the loop stack
    for spec in blocks.catalog():
        assert spec["type"] in handlers or spec["type"] in flow_only, spec["type"]


def test_no_orphan_runner_handlers():
    from core.runner import MacroRunner
    handlers = {n[4:] for n in dir(MacroRunner) if n.startswith("_do_")}
    catalog_types = {b["type"] for b in blocks.catalog()}
    assert handlers <= catalog_types


def test_catalog_types_are_unique():
    types = [b["type"] for b in blocks.catalog()]
    assert len(types) == len(set(types))


def test_catalog_field_kinds_are_renderable():
    # FIELD_KINDS is the contract the frontend implements; comparing against a
    # second hand-written list here just meant maintaining it twice.
    for spec in blocks.catalog():
        for field in spec["fields"]:
            assert field["kind"] in blocks.FIELD_KINDS, (spec["type"], field)


def test_make_block_merges_over_defaults():
    block = blocks.make_block("click", "b1", {"x": 5})
    assert block["params"]["x"] == 5
    assert block["params"]["button"] == "left"   # untouched default
    assert block["params"]["clicks"] == 1


def test_normalize_rejects_unknown_type():
    assert blocks.normalize({"type": "definitely_not_a_block"}) is None
    assert blocks.normalize(None) is None
    assert blocks.normalize("nope") is None


def test_normalize_fills_missing_params():
    # A hand-edited or older-version block must not make the runner guard
    # every single lookup.
    out = blocks.normalize({"type": "wait_ms", "params": {}})
    assert out["params"]["ms"] == 500
    assert out["enabled"] is True
    assert out["once"] is False


def test_normalize_list_drops_bad_entries():
    out = blocks.normalize_list([{"type": "wait_ms"}, {"type": "zzz"}, None, 7])
    assert len(out) == 1


# --------------------------------------------------------------- settings

def test_settings_update_merges_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    smod.save({})
    smod.update({"alpha": 1})
    smod.update({"beta": 2})
    loaded = smod.load()
    assert loaded["alpha"] == 1 and loaded["beta"] == 2


def test_settings_defaults_merged_over_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    smod.save({"alpha": 1})
    # A key added in a later version must read as its default, not KeyError.
    assert smod.load()["action_delay_ms"] == smod.DEFAULTS["action_delay_ms"]


def test_settings_corrupt_file_reads_as_empty(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(path))
    assert smod.load()["action_delay_ms"] == smod.DEFAULTS["action_delay_ms"]


def test_settings_survives_concurrent_updates(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(smod, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    smod.save({})
    threads = [threading.Thread(target=smod.update, args=({"k%d" % i: i},))
               for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    loaded = smod.load()
    for i in range(10):
        assert loaded["k%d" % i] == i


# --------------------------------------------------------------- templates

def test_template_name_cannot_escape_its_folder():
    assert templates._safe_name("../../evil") == "evil"
    assert templates._safe_name("a/b\\c") == "abc"
    assert templates._safe_name("") == "macro"
    assert templates._safe_name(":*?") == "macro"


def test_macro_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(templates, "TEMPLATES_DIR", str(tmp_path))
    block = blocks.make_block("click", "b1", {"x": 7, "y": 9})
    templates.save_macro("demo", {"phases": {"setup": [block], "loop": []}})
    assert "demo" in templates.list_macros()
    loaded = templates.load_macro("demo")
    assert loaded["phases"]["setup"][0]["params"]["x"] == 7
    assert templates.delete_macro("demo")
    assert "demo" not in templates.list_macros()


def test_load_missing_macro_returns_empty_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(templates, "TEMPLATES_DIR", str(tmp_path))
    loaded = templates.load_macro("nope")
    assert loaded["phases"] == {"setup": [], "loop": []}


# --------------------------------------------------------------- recorder

def _ev(t, type_, **kw):
    return dict(t=t, type=type_, **kw)


def test_quick_press_becomes_a_click():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=10, y=20, sx=10, sy=20),
        _ev(0.05, "mouse_up", button="left", x=10, y=20, sx=10, sy=20),
    ])
    assert [b["type"] for b in out] == ["click"]
    assert out[0]["params"] == {"x": 10, "y": 20, "button": "left",
                                "clicks": 1, "hold_ms": 50}


def test_press_move_release_becomes_a_drag():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=10, y=10, sx=10, sy=10),
        _ev(0.1, "move", x=40, y=40, sx=40, sy=40),
        _ev(0.3, "mouse_up", button="left", x=80, y=90, sx=80, sy=90),
    ])
    assert [b["type"] for b in out] == ["drag"]
    assert out[0]["params"]["x2"] == 80 and out[0]["params"]["y2"] == 90


def test_tiny_movement_is_still_a_click_not_a_drag():
    # Hand jitter of a few pixels during a click must not become a drag.
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=10, y=10, sx=10, sy=10),
        _ev(0.05, "mouse_up", button="left", x=12, y=11, sx=12, sy=11),
    ])
    assert [b["type"] for b in out] == ["click"]


def test_key_hold_duration_is_preserved():
    out = recorder.events_to_blocks([
        _ev(0.0, "key_down", key="w", vk=0x57),
        _ev(0.6, "key_up", key="w", vk=0x57),
    ])
    assert out[0]["type"] == "send_key"
    assert 550 <= out[0]["params"]["hold_ms"] <= 650


def test_gaps_below_the_threshold_are_not_turned_into_waits():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=1, y=1, sx=1, sy=1),
        _ev(0.02, "mouse_up", button="left", x=1, y=1, sx=1, sy=1),
        _ev(0.05, "mouse_down", button="left", x=2, y=2, sx=2, sy=2),
        _ev(0.07, "mouse_up", button="left", x=2, y=2, sx=2, sy=2),
    ], min_gap_ms=60)
    assert "wait_ms" not in [b["type"] for b in out]


def test_real_gaps_become_waits():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_down", button="left", x=1, y=1, sx=1, sy=1),
        _ev(0.02, "mouse_up", button="left", x=1, y=1, sx=1, sy=1),
        _ev(1.5, "mouse_down", button="left", x=2, y=2, sx=2, sy=2),
        _ev(1.52, "mouse_up", button="left", x=2, y=2, sx=2, sy=2),
    ], min_gap_ms=60)
    waits = [b for b in out if b["type"] == "wait_ms"]
    assert len(waits) == 1
    assert 1400 <= waits[0]["params"]["ms"] <= 1550


def test_unpaired_events_do_not_crash():
    out = recorder.events_to_blocks([
        _ev(0.0, "mouse_up", button="left", x=1, y=1, sx=1, sy=1),
        _ev(0.1, "key_up", key="w"),
        _ev(0.2, "key_down", key="a"),   # never released
    ])
    assert isinstance(out, list)


def test_coord_space_selects_window_or_screen_coordinates():
    events = [_ev(0.0, "mouse_down", button="left", x=10, y=20, sx=500, sy=600),
              _ev(0.05, "mouse_up", button="left", x=10, y=20, sx=500, sy=600)]
    win = recorder.events_to_blocks(events, "window")[0]["params"]
    scr = recorder.events_to_blocks(events, "screen")[0]["params"]
    assert (win["x"], win["y"]) == (10, 20)
    assert (scr["x"], scr["y"]) == (500, 600)


def test_typing_folds_into_one_type_text_across_the_gaps():
    events = []
    for i, ch in enumerate("hello"):
        events.append(_ev(i * 0.2, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(i * 0.2 + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    assert [b["type"] for b in out] == ["type_text"]
    assert out[0]["params"]["text"] == "hello"


def test_type_text_uses_the_layout_character_not_the_physical_key():
    # Physical a/b/c/d on a Cyrillic layout produce ф/и/с/в. The block must
    # type what the user actually saw, while send_key keeps the physical key.
    pairs = [("a", "ф"), ("b", "и"), ("c", "с"), ("d", "в")]
    events = []
    for i, (physical, produced) in enumerate(pairs):
        vk = ord(physical.upper())
        events.append(_ev(i * 0.15, "key_down", key=physical, vk=vk, char=produced))
        events.append(_ev(i * 0.15 + 0.04, "key_up", key=physical, vk=vk, char=produced))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    assert [b["type"] for b in out] == ["type_text"]
    assert out[0]["params"]["text"] == "фисв"


def test_short_run_is_not_folded_and_keeps_order():
    events = []
    for i, ch in enumerate("ab"):
        events.append(_ev(i * 0.2, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(i * 0.2 + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    types = [b["type"] for b in out]
    assert "type_text" not in types
    assert types.count("send_key") == 2
    assert types.index("send_key") < types.index("wait_ms") < len(types)


def test_folding_is_broken_by_a_long_pause():
    events = []
    for i, ch in enumerate("hello"):
        events.append(_ev(i * 0.2, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(i * 0.2 + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    # 3 second pause, then more typing -- two separate text blocks, not one.
    for i, ch in enumerate("world"):
        t = 4.0 + i * 0.2
        events.append(_ev(t, "key_down", key=ch, vk=ord(ch.upper()), char=ch))
        events.append(_ev(t + 0.05, "key_up", key=ch, vk=ord(ch.upper()), char=ch))
    out = recorder.compress_text_blocks(recorder.events_to_blocks(events))
    texts = [b["params"]["text"] for b in out if b["type"] == "type_text"]
    assert texts == ["hello", "world"]


def test_modifier_combo_is_never_folded_into_text():
    events = [
        _ev(0.0, "key_down", key="a", vk=0x41, char="a"),
        _ev(0.05, "key_up", key="a", vk=0x41, char="a"),
    ]
    out = recorder.events_to_blocks(events)
    out[0]["params"]["modifiers"] = ["ctrl"]
    folded = recorder.compress_text_blocks(out * 5)
    assert all(b["type"] != "type_text" for b in folded)


# ----------------------------------------------------------------- vision

@pytest.fixture
def template_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(vision, "ASSETS_DIR", str(tmp_path))
    vision.clear_cache()
    yield tmp_path
    vision.clear_cache()


def _write_template(folder, name, patch):
    import cv2
    sub = folder / name
    sub.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(sub / (name + ".png")), patch)


def _scene():
    import cv2
    scene = np.full((200, 300, 3), 30, dtype=np.uint8)
    cv2.rectangle(scene, (120, 60), (170, 90), (200, 40, 40), -1)
    cv2.putText(scene, "OK", (128, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return scene


def test_template_is_found_at_the_right_place(template_dir):
    scene = _scene()
    _write_template(template_dir, "btn", scene[60:90, 120:170].copy())
    match = vision.find_in_frame(scene, "btn")
    assert match is not None
    assert match["score"] > 0.95
    assert abs(match["cx"] - 145) <= 2 and abs(match["cy"] - 75) <= 2


def test_no_false_positive_on_noise(template_dir):
    scene = _scene()
    _write_template(template_dir, "btn", scene[60:90, 120:170].copy())
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 60, (200, 300, 3), dtype=np.uint8)
    assert vision.find_in_frame(noise, "btn") is None


def test_flat_patch_does_not_match_infinity(template_dir):
    """TM_CCOEFF_NORMED divides by local variance: a solid patch yields 0/0
    -> inf, which sails past any threshold unless it is filtered out."""
    scene = _scene()
    _write_template(template_dir, "btn", scene[60:90, 120:170].copy())
    flat = np.full((120, 160, 3), 128, dtype=np.uint8)
    assert vision.find_in_frame(flat, "btn") is None


def test_template_larger_than_frame_is_a_miss_not_a_crash(template_dir):
    scene = _scene()
    _write_template(template_dir, "big", scene.copy())
    assert vision.find_in_frame(scene[0:20, 0:20], "big") is None


def test_missing_template_raises_template_not_found(template_dir):
    with pytest.raises(vision.TemplateNotFound):
        vision.load_template_grays("does_not_exist")


def test_multiscale_finds_a_resized_template(template_dir):
    import cv2
    scene = _scene()
    patch = scene[60:90, 120:170].copy()
    shrunk = cv2.resize(patch, None, fx=0.9, fy=0.9, interpolation=cv2.INTER_AREA)
    _write_template(template_dir, "btn", shrunk)
    assert vision.find_in_frame(scene, "btn") is not None


def test_all_variants_of_a_name_are_searched(template_dir):
    import cv2
    scene = _scene()
    sub = template_dir / "btn"
    sub.mkdir()
    # Primary is junk; the alt variant is the real crop. A hit requires that
    # every file under the name gets tried, not just the first.
    cv2.imwrite(str(sub / "btn.png"), np.full((10, 10, 3), 7, dtype=np.uint8))
    cv2.imwrite(str(sub / "btn_alt2.png"), scene[60:90, 120:170].copy())
    vision.clear_cache()
    assert len(vision.template_variant_paths("btn")) == 2
    assert vision.find_in_frame(scene, "btn") is not None


def test_none_frame_is_a_miss(template_dir):
    _write_template(template_dir, "btn", _scene()[60:90, 120:170].copy())
    assert vision.find_in_frame(None, "btn") is None
