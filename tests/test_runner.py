"""Runner semantics -- control flow, failure policies, cleanup.

Uses `log` blocks as probes so nothing is actually typed or clicked: these
tests are safe to run while you are using the machine.
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks
from core.runner import MacroRunner


class Probe:
    """Collects log lines and lets a test wait for the run to end."""

    def __init__(self):
        self.lines = []
        self.status = []

    def log(self, message):
        self.lines.append(str(message))

    def set_status(self, **kw):
        self.status.append(kw)

    def ticks(self, text):
        return sum(1 for line in self.lines if line == text)


def run(macro, loop_forever=False, loop_count=1, timeout=15.0):
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro, hwnd=0, coord_space="screen",
                 loop_forever=loop_forever, loop_count=loop_count)
    deadline = time.time() + timeout
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running(), "runner did not finish within %.0fs" % timeout
    return probe, runner


def macro_of(setup=(), loop=()):
    return {"phases": {"setup": list(setup), "loop": list(loop)}}


def log_block(bid, text):
    return blocks.make_block("log", bid, {"text": text})


def wait_block(bid, ms):
    return blocks.make_block("wait_ms", bid, {"ms": ms})


# ------------------------------------------------------------ basic flow

def test_setup_runs_once_then_loop_runs_n_times():
    probe, _ = run(macro_of(setup=[log_block("s", "setup")],
                            loop=[log_block("l", "loop")]),
                   loop_count=3)
    assert probe.ticks("setup") == 1
    assert probe.ticks("loop") == 3


def test_empty_macro_reports_and_exits():
    probe, _ = run(macro_of())
    assert any("Nothing to run" in line for line in probe.lines)


def test_setup_only_macro_does_not_hang():
    probe, _ = run(macro_of(setup=[log_block("s", "only")]), loop_forever=True)
    assert probe.ticks("only") == 1


def test_disabled_block_is_skipped():
    block = log_block("s", "should not run")
    block["enabled"] = False
    probe, _ = run(macro_of(setup=[block, log_block("t", "ran")]))
    assert probe.ticks("should not run") == 0
    assert probe.ticks("ran") == 1


def test_once_block_only_fires_on_the_first_loop_pass():
    once = log_block("o", "once")
    once["once"] = True
    probe, _ = run(macro_of(loop=[once, log_block("e", "every")]), loop_count=4)
    assert probe.ticks("once") == 1
    assert probe.ticks("every") == 4


def test_once_in_setup_still_runs():
    # Setup only ever runs one pass, so `once` there must not suppress it.
    once = log_block("o", "setup once")
    once["once"] = True
    probe, _ = run(macro_of(setup=[once]))
    assert probe.ticks("setup once") == 1


def test_unknown_block_type_is_dropped_by_normalisation():
    probe, _ = run({"phases": {"setup": [{"type": "not_a_block"},
                                         log_block("s", "ran")], "loop": []}})
    assert probe.ticks("ran") == 1


# ------------------------------------------------------------------ loops

def test_loop_start_end_repeats_the_enclosed_blocks():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 3}),
        log_block("t", "tick"),
        blocks.make_block("loop_end", "b", {}),
    ]))
    assert probe.ticks("tick") == 3


def test_nested_loops_multiply():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 3}),
        blocks.make_block("loop_start", "b", {"count": 2}),
        log_block("t", "x"),
        blocks.make_block("loop_end", "c", {}),
        blocks.make_block("loop_end", "d", {}),
    ]))
    assert probe.ticks("x") == 6


def test_loop_count_of_one_runs_body_once():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 1}),
        log_block("t", "x"),
        blocks.make_block("loop_end", "b", {}),
    ]))
    assert probe.ticks("x") == 1


def test_loop_count_of_zero_is_clamped_to_one_not_infinite():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 0}),
        log_block("t", "x"),
        blocks.make_block("loop_end", "b", {}),
    ]))
    assert probe.ticks("x") == 1


def test_loop_end_without_a_start_is_ignored():
    probe, _ = run(macro_of(setup=[
        log_block("t", "before"),
        blocks.make_block("loop_end", "b", {}),
        log_block("u", "after"),
    ]))
    assert probe.ticks("before") == 1 and probe.ticks("after") == 1


def test_loop_start_without_an_end_does_not_hang():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 5}),
        log_block("t", "x"),
    ]))
    assert probe.ticks("x") == 1


def test_blocks_after_a_loop_still_run():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 2}),
        log_block("t", "in"),
        blocks.make_block("loop_end", "b", {}),
        log_block("u", "out"),
    ]))
    assert probe.ticks("in") == 2 and probe.ticks("out") == 1


# ------------------------------------------------------- failure policies

def _missing_image(bid, on_fail):
    return blocks.make_block("wait_image", bid, {
        "template": "__definitely_missing__", "timeout_ms": 120,
        "on_fail": on_fail})


def test_on_fail_continue_runs_the_rest():
    probe, _ = run(macro_of(setup=[
        _missing_image("i", "continue"), log_block("t", "after")]))
    assert probe.ticks("after") == 1


def test_on_fail_skip_rest_abandons_the_pass_but_not_the_run():
    probe, _ = run(macro_of(loop=[
        _missing_image("i", "skip_rest"), log_block("t", "after")]),
        loop_count=3)
    assert probe.ticks("after") == 0
    # skip_rest ends the PASS; the loop must still make all three passes.
    assert sum(1 for s in probe.status if s.get("loop") == 3) >= 1


def test_on_fail_stop_ends_the_whole_run():
    probe, _ = run(macro_of(loop=[
        _missing_image("i", "stop"), log_block("t", "after")]),
        loop_forever=True, timeout=20)
    assert probe.ticks("after") == 0


def test_skip_rest_inside_a_loop_block_still_ends_the_pass():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("loop_start", "a", {"count": 3}),
        _missing_image("i", "skip_rest"),
        log_block("t", "in"),
        blocks.make_block("loop_end", "b", {}),
        log_block("u", "out"),
    ]))
    assert probe.ticks("in") == 0 and probe.ticks("out") == 0


def test_a_block_that_raises_does_not_kill_the_run():
    bad = blocks.make_block("click", "c", {})
    bad["params"]["x"] = "not-a-number"
    probe, _ = run(macro_of(setup=[bad, log_block("t", "after")]))
    assert probe.ticks("after") == 1
    assert any("failed" in line for line in probe.lines)


# -------------------------------------------------------- stop and pause

def test_stop_interrupts_a_long_wait_promptly():
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro_of(loop=[wait_block("w", 8000)]),
                 hwnd=0, coord_space="screen", loop_forever=True)
    time.sleep(0.4)
    started = time.time()
    runner.stop()
    while runner.is_running() and time.time() - started < 5:
        time.sleep(0.02)
    elapsed = time.time() - started
    assert not runner.is_running()
    # The wait sleeps in slices and re-checks, so Stop must land in well
    # under a second rather than after the full 8s.
    assert elapsed < 1.0, elapsed


def test_pause_halts_progress_and_resume_continues_it():
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro_of(loop=[log_block("t", "tick"), wait_block("w", 60)]),
                 hwnd=0, coord_space="screen", loop_forever=True)
    time.sleep(0.5)
    runner.pause()
    time.sleep(0.3)
    frozen = probe.ticks("tick")
    time.sleep(0.8)
    assert probe.ticks("tick") == frozen, "run advanced while paused"
    runner.resume()
    time.sleep(0.6)
    assert probe.ticks("tick") > frozen
    runner.stop()
    while runner.is_running():
        time.sleep(0.02)


def test_stop_while_paused_still_ends_the_run():
    # Stop must clear the pause too, or the thread parks forever.
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro_of(loop=[wait_block("w", 200)]),
                 hwnd=0, coord_space="screen", loop_forever=True)
    time.sleep(0.3)
    runner.pause()
    time.sleep(0.3)
    runner.stop()
    deadline = time.time() + 5
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running()


def test_second_start_while_running_is_refused():
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro_of(loop=[wait_block("w", 300)]),
                 hwnd=0, coord_space="screen", loop_forever=True)
    time.sleep(0.3)
    result = runner.start(macro_of(loop=[wait_block("w", 300)]), hwnd=0,
                          coord_space="screen")
    assert result["ok"] is False and result["reason"] == "already_running"
    runner.stop()
    while runner.is_running():
        time.sleep(0.02)


def test_status_returns_to_idle_after_the_run():
    probe, _ = run(macro_of(setup=[log_block("s", "x")]))
    last = [s for s in probe.status if "running" in s]
    assert last and last[-1]["running"] is False


# -------------------------------------------------------------- cleanup

def test_held_key_is_released_when_the_run_ends():
    from core import keys as keymod
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    runner.start(macro_of(loop=[blocks.make_block(
        "hold_key", "h", {"key": "shift", "hold_ms": 5000})]),
        hwnd=0, coord_space="screen", loop_forever=True)
    time.sleep(0.8)
    assert runner.keyboard.is_down(keymod.VK_SHIFT), "hold_key never pressed"
    runner.stop()
    deadline = time.time() + 5
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.3)
    assert not runner.keyboard.is_down(keymod.VK_SHIFT), "shift left held after Stop"


def test_wait_random_stays_within_its_bounds():
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=probe.set_status)
    started = time.time()
    runner.start(macro_of(setup=[blocks.make_block(
        "wait_random", "w", {"min_ms": 300, "max_ms": 500})]),
        hwnd=0, coord_space="screen")
    while runner.is_running():
        time.sleep(0.02)
    elapsed = time.time() - started
    assert 0.25 <= elapsed <= 1.2, elapsed


def test_inverted_random_bounds_do_not_hang():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("wait_random", "w", {"min_ms": 500, "max_ms": 100}),
        log_block("t", "after")]))
    assert probe.ticks("after") == 1


def test_playback_of_a_missing_recording_is_reported_not_fatal():
    probe, _ = run(macro_of(setup=[
        blocks.make_block("playback", "p", {"recording": "__no_such_recording__"}),
        log_block("t", "after")]))
    assert probe.ticks("after") == 1
