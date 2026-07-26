"""What a Vision block does when it does not find what it was looking for.

Uses a template name that cannot exist, so every one of these blocks fails
immediately and deterministically without touching the screen.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import blocks
from core.runner import MacroRunner


class Probe:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(str(message))

    def count(self, text):
        return sum(1 for line in self.lines if line == text)

    def has(self, fragment):
        return any(fragment in line for line in self.lines)


def run(macro, loop_forever=False, loop_count=1, timeout=25.0):
    probe = Probe()
    runner = MacroRunner(log=probe.log, set_status=lambda **k: None)
    runner.start(macro, hwnd=0, coord_space="screen",
                 loop_forever=loop_forever, loop_count=loop_count)
    deadline = time.time() + timeout
    while runner.is_running() and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running(), "run did not finish"
    return probe


def failing(on_fail, fallback=None, bid="v"):
    params = {"template": "__no_such_image__", "timeout_ms": 60, "on_fail": on_fail}
    if fallback is not None:
        params["on_fail_blocks"] = fallback
    return blocks.make_block("wait_image", bid, params)


def log_block(bid, text):
    return blocks.make_block("log", bid, {"text": text})


def macro_of(setup=(), loop=()):
    return {"phases": {"setup": list(setup), "loop": list(loop)}}


# ------------------------------------------------------------- the options

def test_the_catalog_offers_every_on_fail_option():
    for spec in blocks.catalog():
        if spec["group"] != "Vision" or spec["type"] == "read_text":
            continue
        field = [f for f in spec["fields"] if f["key"] == "on_fail"][0]
        assert field["options"] == blocks.ON_FAIL_OPTIONS, spec["type"]
        keys = {f["key"] for f in spec["fields"]}
        assert "on_fail_blocks" in keys, spec["type"]


def test_continue_runs_the_rest():
    probe = run(macro_of(setup=[failing("continue"), log_block("t", "after")]))
    assert probe.count("after") == 1


def test_skip_rest_abandons_the_pass():
    probe = run(macro_of(setup=[failing("skip rest"), log_block("t", "after")]))
    assert probe.count("after") == 0


def test_stop_ends_the_run():
    probe = run(macro_of(loop=[failing("stop"), log_block("t", "after")]),
                loop_forever=True)
    assert probe.count("after") == 0


def test_the_old_underscore_spelling_still_works():
    """Macros saved before the wording changed carry skip_rest / run_blocks."""
    probe = run(macro_of(setup=[failing("skip_rest"), log_block("t", "after")]))
    assert probe.count("after") == 0


# ------------------------------------------------------------ run blocks

def test_run_blocks_executes_the_fallback_then_carries_on():
    probe = run(macro_of(setup=[
        failing("run blocks", [log_block("f", "fallback ran")]),
        log_block("t", "after"),
    ]))
    assert probe.count("fallback ran") == 1
    assert probe.count("after") == 1, "the main sequence must resume"


def test_the_fallback_runs_in_order():
    probe = run(macro_of(setup=[
        failing("run blocks", [log_block("a", "one"), log_block("b", "two")]),
    ]))
    assert probe.lines.index("one") < probe.lines.index("two")


def test_an_empty_fallback_is_reported_and_continues():
    probe = run(macro_of(setup=[
        failing("run blocks", []), log_block("t", "after")]))
    assert probe.has("no fallback blocks")
    assert probe.count("after") == 1


def test_a_fallback_only_runs_when_the_block_actually_fails():
    ok = blocks.make_block("log", "l", {"text": "main"})
    probe = run(macro_of(setup=[ok]))
    assert probe.count("main") == 1
    assert not probe.has("fallback")


def test_a_fallback_can_contain_a_loop():
    probe = run(macro_of(setup=[failing("run blocks", [
        blocks.make_block("loop_start", "s", {"count": 3}),
        log_block("t", "tick"),
        blocks.make_block("loop_end", "e", {}),
    ])]))
    assert probe.count("tick") == 3


def test_a_fallback_that_stops_ends_the_whole_run():
    probe = run(macro_of(loop=[
        failing("run blocks", [failing("stop", None, "inner")]),
        log_block("t", "after"),
    ]), loop_forever=True)
    assert probe.count("after") == 0


def test_nested_fallbacks_are_bounded():
    """A fallback whose own block fails into another fallback must not
    recurse without limit."""
    deep = failing("run blocks", [failing("run blocks", [
        failing("run blocks", [failing("run blocks", [log_block("x", "bottom")])])])])
    probe = run(macro_of(setup=[deep, log_block("t", "after")]))
    assert probe.has("nested too deep")
    assert probe.count("after") == 1, "the run must survive the guard"


# --------------------------------------------------------- restart phase

def test_restart_phase_starts_the_pass_again_from_the_top():
    """The first block logs, the second fails and restarts. A counter block
    would run once per attempt, so seeing it more than once proves the
    restart happened."""
    probe = run(macro_of(setup=[
        log_block("a", "top"),
        failing("restart phase"),
    ]))
    assert probe.count("top") > 1, probe.lines[:6]
    assert probe.has("restarting")


def test_restart_phase_is_bounded_so_it_cannot_spin_forever():
    probe = run(macro_of(setup=[log_block("a", "top"), failing("restart phase")]),
                timeout=60)
    assert probe.has("giving up on this pass")
    # Bounded by the guard, not by luck.
    assert probe.count("top") <= 60, probe.count("top")


def test_restart_phase_does_not_leak_into_the_next_phase():
    probe = run(macro_of(
        setup=[log_block("a", "setup"), failing("restart phase")],
        loop=[log_block("b", "loop")]), loop_count=1, timeout=60)
    assert probe.count("loop") == 1


def test_restart_inside_a_fallback_restarts_the_phase():
    probe = run(macro_of(setup=[
        log_block("a", "top"),
        failing("run blocks", [failing("restart phase", None, "inner")]),
    ]), timeout=60)
    assert probe.count("top") > 1
    assert probe.has("giving up on this pass")


# ------------------------------------------------------------- summaries

# --------------------------------------------------- what follows a fallback

def after(kind, inner_text="fallback ran", bid="v"):
    """A vision block that always fails, runs a one-line fallback, then does
    `kind`."""
    return blocks.make_block("wait_image", bid, {
        "template": "__no_such_image__", "timeout_ms": 60,
        "on_fail": "run blocks", "on_fail_after": kind,
        "on_fail_blocks": [log_block("f", inner_text)]})


def test_the_catalog_offers_every_after_option():
    for spec in blocks.catalog():
        if spec["group"] != "Vision" or spec["type"] == "read_text":
            continue
        field = [f for f in spec["fields"] if f["key"] == "on_fail_after"][0]
        assert field["options"] == blocks.ON_FAIL_AFTER_OPTIONS, spec["type"]


def test_continue_main_resumes_where_it_left_off():
    probe = run(macro_of(setup=[after("continue main"), log_block("t", "after")]))
    assert probe.count("fallback ran") == 1
    assert probe.count("after") == 1


def test_restart_phase_after_a_fallback_replays_the_phase():
    probe = run(macro_of(setup=[log_block("a", "top"), after("restart phase")]),
                timeout=60)
    assert probe.count("top") > 1
    assert probe.has("restarting the phase")


def test_restart_macro_replays_setup_as_well():
    """The whole point of "restart macro": Setup runs again, which a phase
    restart would never do."""
    probe = run(macro_of(
        setup=[log_block("s", "setup ran")],
        loop=[after("restart macro")]), loop_count=1, timeout=90)
    assert probe.count("setup ran") > 1, probe.count("setup ran")
    assert probe.has("Restarting the whole macro")


def test_restart_macro_is_bounded():
    probe = run(macro_of(loop=[after("restart macro")]), loop_count=1, timeout=120)
    assert probe.has("giving up")


def test_stop_after_a_fallback_ends_the_run():
    probe = run(macro_of(loop=[after("stop"), log_block("t", "after")]),
                loop_forever=True)
    assert probe.count("fallback ran") == 1
    assert probe.count("after") == 0


def test_the_after_option_is_ignored_unless_the_fallback_ran():
    """A block that succeeds must not restart anything."""
    probe = run(macro_of(setup=[
        blocks.make_block("log", "l", {"text": "main"}),
    ]))
    assert probe.count("main") == 1
    assert not probe.has("Restarting")


def test_a_block_with_a_fallback_still_summarises_readably():
    block = failing("run blocks", [log_block("f", "x")])
    text = blocks.summarise(block)
    assert "__no_such_image__" in text
    assert "{" not in text


def test_normalisation_keeps_the_fallback_list():
    block = failing("run blocks", [log_block("f", "x")])
    normalised = blocks.normalize(block)
    assert len(normalised["params"]["on_fail_blocks"]) == 1


def test_the_fallback_default_is_not_shared_between_blocks():
    a = blocks.make_block("wait_image", "a")
    b = blocks.make_block("wait_image", "b")
    a["params"]["on_fail_blocks"].append(log_block("x", "y"))
    assert b["params"]["on_fail_blocks"] == []
    spec_default = [f for f in blocks.BY_TYPE["wait_image"]["fields"]
                    if f["key"] == "on_fail_blocks"][0]["default"]
    assert spec_default == [], "the catalog's own default was mutated"
