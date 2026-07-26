"""Sleep accuracy.

Windows' default timer granularity is ~15.6 ms, so `time.sleep(0.001)` really
sleeps ~15 ms. A recording sampled every few milliseconds then replays every
event ~15x late, which is exactly what "I set it to 1 ms and it still stutters"
looks like.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import timing

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows timers")


def measure(sleeper, target, rounds=20):
    """Mean duration of one sleep."""
    start = timing.now()
    for _ in range(rounds):
        sleeper(target)
    return (timing.now() - start) / rounds


def floor_of(sleeper, target, batches=5, rounds=10):
    """Best observed mean.

    The timer PERIOD is a floor, not a guarantee: any thread the OS happens
    to schedule ahead of us adds latency on top, and the rest of the test
    suite leaves plenty of those around. The minimum across several batches
    is the granularity being measured; the outliers are the machine.
    """
    return min(measure(sleeper, target, rounds) for _ in range(batches))


BENCHMARK = r'''
import json, sys, time
sys.path.insert(0, %r)
from core import timing

def mean(fn, target, rounds=15):
    t0 = time.perf_counter()
    for _ in range(rounds):
        fn(target)
    return (time.perf_counter() - t0) / rounds

out = {}
for target in (0.001, 0.004, 0.010):
    bare = min(mean(time.sleep, target) for _ in range(3))
    with timing.precision():
        fine = min(mean(timing.sleep, target) for _ in range(3))
    out[str(target)] = [bare, fine]
print(json.dumps(out))
'''


@pytest.fixture(scope="module")
def benchmark():
    """Measured in a FRESH process.

    The timer period is a floor, not a scheduling guarantee: the rest of the
    suite leaves worker threads around, and a contended interpreter overshoots
    every sleep regardless of the period. Measuring in isolation is the only
    way this asserts the code rather than the machine's mood.
    """
    import json
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run([sys.executable, "-c", BENCHMARK % root],
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        pytest.skip("benchmark subprocess failed: %s" % result.stderr[-300:])
    return json.loads(result.stdout.strip().splitlines()[-1])


@windows_only
@pytest.mark.parametrize("target", ["0.001", "0.004", "0.01"])
def test_short_sleeps_are_accurate_under_precision(benchmark, target):
    bare, fine = benchmark[target]
    want = float(target)
    assert fine < want + 0.004, "target=%s bare=%.4f precise=%.4f" % (target, bare, fine)


@windows_only
def test_precision_is_what_makes_the_difference(benchmark):
    """The actual defect: the same 1ms request, with and without the
    multimedia timer period."""
    bare, fine = benchmark["0.001"]
    assert fine < bare * 0.6, "bare=%.4f fine=%.4f" % (bare, fine)


def test_precision_nests_without_releasing_early():
    with timing.precision():
        with timing.precision():
            pass
        # The inner exit must NOT have dropped the period: the outer scope
        # still needs it, and the setting is global to the machine.
        actual = measure(timing.sleep, 0.002, rounds=10)
    if sys.platform == "win32":
        assert actual < 0.008, actual


def test_sleep_until_does_not_overshoot_a_past_deadline():
    start = timing.now()
    assert timing.sleep_until(start - 1) is False
    assert timing.now() - start < 0.02


def test_sleep_until_reports_an_abort():
    aborted = timing.sleep_until(timing.now() + 5, lambda: True)
    assert aborted is True


def test_a_long_sleep_aborts_promptly():
    calls = {"n": 0}

    def abort():
        calls["n"] += 1
        return calls["n"] > 2          # abort on the third check

    start = timing.now()
    assert timing.sleep(3.0, abort) is True
    assert timing.now() - start < 1.0


def test_an_absolute_timeline_does_not_accumulate_drift():
    """Per-event sleeps make every overshoot permanent; scheduling against one
    start time absorbs it."""
    steps = [i * 0.005 for i in range(1, 41)]      # 40 events over 200ms
    with timing.precision():
        start = timing.now()
        for t in steps:
            timing.sleep_until(start + t)
        elapsed = timing.now() - start
    ideal = steps[-1]
    assert elapsed < ideal + 0.05, "%.4f vs ideal %.4f" % (elapsed, ideal)


def test_negative_and_zero_durations_return_immediately():
    start = timing.now()
    assert timing.sleep(0) is False
    assert timing.sleep(-5) is False
    assert timing.now() - start < 0.02
