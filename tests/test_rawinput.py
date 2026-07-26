"""Raw mouse deltas and self-echo suppression.

Both exist for cases position tracking cannot cover:
  * a game holding the cursor captured reports no cursor movement at all, so
    a camera drag recorded from positions looks like nothing happened;
  * everything this app injects arrives back through the same global hooks,
    so recording while a macro plays would capture the macro's own output.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import rawinput
from core import _input_win as backend

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows raw input")


# ------------------------------------------------------- echo suppression

def test_an_injected_key_is_recognised_as_ours():
    backend.clear_injected_marks()
    backend.key_down(0x5A)
    assert backend.was_injected("key_down", 0x5A) is True


def test_the_mark_is_consumed_so_a_real_repeat_still_records():
    backend.clear_injected_marks()
    backend.key_down(0x5A)
    assert backend.was_injected("key_down", 0x5A) is True
    # A genuine second press of the same key must NOT be swallowed.
    assert backend.was_injected("key_down", 0x5A) is False


def test_an_unrelated_event_is_never_ours():
    backend.clear_injected_marks()
    backend.key_down(0x5A)
    assert backend.was_injected("key_down", 0x41) is False
    assert backend.was_injected("key_up", 0x5A) is False


def test_press_and_release_are_tracked_separately():
    backend.clear_injected_marks()
    backend.key_down(0x5A)
    backend.key_up(0x5A)
    assert backend.was_injected("key_down", 0x5A) is True
    assert backend.was_injected("key_up", 0x5A) is True


def test_clicks_are_tracked_per_button():
    backend.clear_injected_marks()
    backend.button_down("left")
    backend.button_up("left")
    assert backend.was_injected("mouse_down", "left") is True
    assert backend.was_injected("mouse_up", "left") is True
    assert backend.was_injected("mouse_down", "right") is False


def test_a_stale_mark_is_not_treated_as_ours():
    """A user pressing the same key seconds later must be recorded."""
    backend.clear_injected_marks()
    backend.key_down(0x5A)
    time.sleep(0.01)
    assert backend.was_injected("key_down", 0x5A, window=0.001) is False


def test_clearing_marks_forgets_everything():
    backend.key_down(0x5A)
    backend.clear_injected_marks()
    assert backend.was_injected("key_down", 0x5A) is False


# ------------------------------------------------------------- raw deltas

@windows_only
def test_raw_input_is_available_on_windows():
    assert rawinput.available() is True


@windows_only
def test_the_listener_receives_the_deltas_we_generate():
    got = []
    listener = rawinput.Listener(lambda dx, dy: got.append((dx, dy)))
    assert listener.start() is True
    try:
        time.sleep(0.3)
        home = backend.cursor_pos()
        for _ in range(20):
            backend.move_rel(3, 2)
            time.sleep(0.008)
        time.sleep(0.4)
        backend.move_abs(*home)
    finally:
        listener.stop()

    assert len(got) >= 10, "only %d deltas arrived" % len(got)
    sx = sum(d[0] for d in got)
    sy = sum(d[1] for d in got)
    # 20 moves of (3, 2). Allowing slack for the physical mouse being nudged
    # mid-test, but the sign and rough magnitude must be right.
    assert sx > 0 and sy > 0, (sx, sy)
    assert 40 <= sx <= 90, sx


@windows_only
def test_starting_twice_is_harmless():
    listener = rawinput.Listener(lambda dx, dy: None)
    assert listener.start() is True
    try:
        assert listener.start() is True
    finally:
        listener.stop()


@windows_only
def test_stopping_a_listener_that_never_started_is_harmless():
    rawinput.Listener(lambda dx, dy: None).stop()


@windows_only
def test_a_raising_callback_does_not_kill_the_pump():
    seen = {"n": 0}

    def boom(dx, dy):
        seen["n"] += 1
        raise RuntimeError("callback exploded")

    listener = rawinput.Listener(boom)
    assert listener.start() is True
    try:
        time.sleep(0.2)
        home = backend.cursor_pos()
        for _ in range(6):
            backend.move_rel(2, 0)
            time.sleep(0.01)
        time.sleep(0.3)
        backend.move_abs(*home)
    finally:
        listener.stop()
    # Every delta still arrived: one bad callback must not stop the rest.
    assert seen["n"] >= 3, seen["n"]


# ------------------------------------------------------------- the event

def test_recorded_drag_deltas_replay_as_relative_moves():
    """The event carries [dx, dy, t] triples and the runner nudges by them."""
    from core import blocks
    from core.runner import MacroRunner

    moves = []

    class StubMouse:
        def nudge(self, dx=1, dy=0):
            moves.append((dx, dy))

        def move_to(self, x, y):
            moves.append(("abs", x, y))

        def click(self, *a, **k):
            pass

        def up(self, *a, **k):
            pass

        def down(self, *a, **k):
            pass

        def scroll(self, *a, **k):
            pass

        def position(self):
            return (0, 0)

    runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)
    runner.mouse = StubMouse()
    runner._replay_event({"t": 0.0, "type": "drag_deltas", "button": "right",
                          "deltas": [[5, -3, 0.0], [7, -2, 0.01], [1, 0, 0.02]]})
    assert moves == [(5, -3), (7, -2), (1, 0)], moves


def test_an_empty_delta_list_is_a_no_op():
    from core.runner import MacroRunner
    runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)

    class Boom:
        def nudge(self, *a, **k):
            raise AssertionError("should not move")

    runner.mouse = Boom()
    runner._replay_event({"t": 0, "type": "drag_deltas", "deltas": []})


def test_malformed_deltas_are_skipped_not_fatal():
    from core.runner import MacroRunner
    moves = []

    class StubMouse:
        def nudge(self, dx=1, dy=0):
            moves.append((dx, dy))

    runner = MacroRunner(log=lambda m: None, set_status=lambda **k: None)
    runner.mouse = StubMouse()
    runner._replay_event({"t": 0, "type": "drag_deltas",
                          "deltas": [[1, 2, 0.0], ["x", "y", "z"], None, [3, 4, 0.01]]})
    assert moves == [(1, 2), (3, 4)], moves
