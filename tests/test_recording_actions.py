"""A recording as a single reusable, editable unit.

Covers the path behind the "Play Recording" block: raw events are the
lossless original, an optional edited action list overrides playback, and
resetting drops back to the events.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks, recorder
from core import templates as tpl
from core.runner import MacroRunner


@pytest.fixture
def rec_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tpl, "RECORDINGS_DIR", str(tmp_path))
    return tmp_path


def _ev(t, type_, **kw):
    return dict(t=t, type=type_, **kw)


EVENTS = [
    _ev(0.0, "mouse_down", button="left", x=10, y=20, sx=110, sy=120),
    _ev(0.05, "mouse_up", button="left", x=10, y=20, sx=110, sy=120),
    _ev(0.6, "move", x=40, y=60, sx=140, sy=160),
    _ev(1.0, "key_down", key="w", vk=0x57, char="w"),
    _ev(1.4, "key_up", key="w", vk=0x57, char="w"),
]


# ------------------------------------------------------------- persistence

def test_a_recording_saves_events_and_no_actions_by_default(rec_dir):
    tpl.save_recording("run", EVENTS)
    data = tpl.load_recording("run")
    assert len(data["events"]) == len(EVENTS)
    assert data["blocks"] is None


def test_edited_actions_persist_without_losing_the_events(rec_dir):
    tpl.save_recording("run", EVENTS)
    edited = [blocks.make_block("wait_ms", "a", {"ms": 250})]
    tpl.update_recording_blocks("run", edited)

    data = tpl.load_recording("run")
    assert len(data["events"]) == len(EVENTS), "raw events must survive an edit"
    assert len(data["blocks"]) == 1
    assert data["blocks"][0]["params"]["ms"] == 250


def test_resetting_actions_restores_raw_playback(rec_dir):
    tpl.save_recording("run", EVENTS)
    tpl.update_recording_blocks("run", [blocks.make_block("wait_ms", "a", {"ms": 1})])
    assert tpl.load_recording("run")["blocks"]
    tpl.save_recording("run", tpl.load_recording("run")["events"], None)
    assert tpl.load_recording("run")["blocks"] is None


def test_a_recording_predating_the_editor_still_loads(rec_dir):
    # Written by an older version: no "blocks" key at all.
    from core.jsonstore import write_json_atomic
    write_json_atomic(str(rec_dir / "old.json"), {"name": "old", "events": EVENTS})
    data = tpl.load_recording("old")
    assert data["blocks"] is None
    assert len(data["events"]) == len(EVENTS)


# --------------------------------------------------------------- movements

def test_mouse_movement_is_kept_in_the_raw_events(rec_dir):
    """Playback replays events verbatim, so a recorded path is preserved
    even though the block conversion drops moves by default."""
    tpl.save_recording("run", EVENTS)
    kinds = [e["type"] for e in tpl.load_recording("run")["events"]]
    assert "move" in kinds


def test_block_conversion_can_keep_movements_on_request():
    without = [b["type"] for b in recorder.events_to_blocks(EVENTS, keep_moves=False)]
    with_moves = [b["type"] for b in recorder.events_to_blocks(EVENTS, keep_moves=True)]
    assert "move" not in without
    assert "move" in with_moves


def test_the_recorder_records_movement_by_default():
    from core import settings as smod
    assert smod.DEFAULTS["record_mouse_move"] is True


# ---------------------------------------------------------------- playback

class Probe:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(str(message))

    def has(self, fragment):
        return any(fragment in line for line in self.lines)


def _run(macro, timeout=15.0):
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=lambda **k: None)
    runner.start(macro, hwnd=0, coord_space="screen", loop_forever=False, loop_count=1)
    deadline = time.time() + timeout
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running()
    return probe


def test_playback_runs_the_edited_actions_when_there_are_any(rec_dir):
    tpl.save_recording("run", EVENTS)
    tpl.update_recording_blocks("run", [
        blocks.make_block("log", "a", {"text": "edited action ran"}),
        blocks.make_block("wait_ms", "b", {"ms": 20}),
    ])
    probe = _run({"phases": {"setup": [
        blocks.make_block("playback", "p", {"recording": "run"})], "loop": []}})
    assert probe.has("edited action ran")
    assert probe.has("2 edited actions")
    assert not probe.has("raw events")


def test_playback_falls_back_to_raw_events_without_an_edit(rec_dir):
    tpl.save_recording("run", EVENTS)
    probe = _run({"phases": {"setup": [
        blocks.make_block("playback", "p", {"recording": "run"})], "loop": []}})
    assert probe.has("raw events")


def test_deleting_every_action_makes_playback_do_nothing(rec_dir):
    """An empty edited list means "the user deleted every action".

    Treating [] as "no edits" made playback fall back to the raw events and
    replay the entire original recording -- every click they had just
    deleted fired again.
    """
    tpl.save_recording("run", EVENTS)
    tpl.update_recording_blocks("run", [])
    probe = _run({"phases": {"setup": [
        blocks.make_block("playback", "p", {"recording": "run"})], "loop": []}})
    assert probe.has("empty action list"), probe.lines
    assert not probe.has("raw events"), "an emptied recording replayed itself"


def test_an_empty_edit_is_stored_as_empty_not_as_absent(rec_dir):
    tpl.save_recording("run", EVENTS)
    tpl.update_recording_blocks("run", [])
    assert tpl.load_recording("run")["blocks"] == []
    assert tpl.load_recording("run")["blocks"] is not None


# ------------------------------------------------------------ missing file

def test_load_reports_whether_the_recording_exists(rec_dir):
    tpl.save_recording("here", EVENTS)
    assert tpl.load_recording("here")["exists"] is True
    assert tpl.load_recording("gone")["exists"] is False


def test_editing_a_deleted_recording_does_not_recreate_it(rec_dir):
    """Writing the edited list back used to resurrect a deleted recording as
    a permanently empty zombie file."""
    tpl.save_recording("run", EVENTS)
    tpl.delete_recording("run")
    assert "run" not in tpl.list_recordings()

    with pytest.raises(FileNotFoundError):
        tpl.update_recording_blocks("run", [blocks.make_block("wait_ms", "a", {"ms": 5})])
    assert "run" not in tpl.list_recordings(), "the deleted recording came back"


def test_the_api_refuses_to_edit_a_missing_recording(rec_dir, monkeypatch):
    import main
    monkeypatch.setattr(main.constants, "RECORDINGS_DIR", str(rec_dir), raising=False)
    api = main.Api()

    assert api.get_recording_actions("never_existed")["ok"] is False
    assert api.get_recording_actions("never_existed")["reason"] == "missing"
    assert api.save_recording_actions("never_existed", [])["ok"] is False
    assert api.reset_recording_actions("never_existed")["ok"] is False
    assert "never_existed" not in tpl.list_recordings()


def test_the_api_round_trips_an_existing_recording(rec_dir):
    import main
    api = main.Api()
    tpl.save_recording("real", EVENTS)

    got = api.get_recording_actions("real")
    assert got["ok"] is True and got["edited"] is False
    assert got["event_count"] == len(EVENTS)
    assert got["blocks"], "derived actions should not be empty"

    saved = api.save_recording_actions("real", [blocks.make_block("wait_ms", "a", {"ms": 42})])
    assert saved["ok"] is True

    again = api.get_recording_actions("real")
    assert again["edited"] is True
    assert again["blocks"][0]["params"]["ms"] == 42

    back = api.reset_recording_actions("real")
    assert back["ok"] is True and back["edited"] is False


def test_edited_actions_go_through_the_normal_block_machinery(rec_dir):
    """Loops inside a recording's action list must work, which is only true
    if playback runs them through _run_blocks rather than a private loop."""
    tpl.save_recording("run", EVENTS)
    tpl.update_recording_blocks("run", [
        blocks.make_block("loop_start", "s", {"count": 3}),
        blocks.make_block("log", "l", {"text": "tick"}),
        blocks.make_block("loop_end", "e", {}),
    ])
    probe = _run({"phases": {"setup": [
        blocks.make_block("playback", "p", {"recording": "run"})], "loop": []}})
    assert sum(1 for line in probe.lines if line == "tick") == 3


def test_playback_of_a_missing_recording_is_not_fatal(rec_dir):
    probe = _run({"phases": {"setup": [
        blocks.make_block("playback", "p", {"recording": "nope"}),
        blocks.make_block("log", "l", {"text": "after"})], "loop": []}})
    assert probe.has("after")
