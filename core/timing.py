"""Accurate sleeping on Windows.

Windows' default timer granularity is ~15.6 ms. `time.sleep(0.001)` therefore
sleeps for up to 15 ms, and a replay that issues one sleep per recorded event
accumulates that error until the playback visibly stutters and drifts seconds
behind the original.

Two fixes, both needed:

* `precision()` asks the multimedia timer for 1 ms granularity for the
  duration of a run, so short sleeps are actually short;
* `sleep_until()` schedules against an ABSOLUTE deadline rather than sleeping
  a per-event duration, so an overshoot on one event is absorbed by the next
  instead of compounding.
"""
import ctypes
import sys
import time

_winmm = None
if sys.platform == "win32":
    try:
        _winmm = ctypes.WinDLL("winmm")
    except OSError:
        _winmm = None

# Granularity, in ms, requested from the OS timer.
_PERIOD_MS = 1
_depth = 0


class precision:
    """Context manager raising the OS timer resolution.

    Reference-counted: nesting is safe, and the period is only released once
    the outermost user is done. Every begin must be matched by an end -- the
    setting is global to the machine while it is held.
    """

    def __enter__(self):
        global _depth
        if _winmm is not None:
            if _depth == 0:
                try:
                    _winmm.timeBeginPeriod(_PERIOD_MS)
                except Exception:
                    pass
            _depth += 1
        return self

    def __exit__(self, *_exc):
        global _depth
        if _winmm is not None and _depth > 0:
            _depth -= 1
            if _depth == 0:
                try:
                    _winmm.timeEndPeriod(_PERIOD_MS)
                except Exception:
                    pass
        return False


def now() -> float:
    """Monotonic clock. perf_counter, not time.time: the latter can jump
    (NTP, DST) and is coarser on Windows."""
    return time.perf_counter()


def sleep_until(deadline: float, should_abort=None, slice_s: float = 0.05) -> bool:
    """Sleep until `deadline` (a perf_counter value). True if aborted.

    Long waits are sliced so Stop stays responsive; the last stretch is slept
    in one go so short delays are not chopped into rescheduling noise. The
    final sub-millisecond gap is spun, because no OS sleep is that precise.
    """
    while True:
        remaining = deadline - now()
        if remaining <= 0:
            return False
        if should_abort is not None and should_abort():
            return True
        if remaining > slice_s:
            time.sleep(slice_s)
            continue
        if remaining > 0.002:
            time.sleep(remaining - 0.001)
            continue
        # Sub-2ms: busy-wait. Any sleep here would overshoot by more than the
        # interval being waited for.
        while now() < deadline:
            pass
        return False


def sleep(seconds: float, should_abort=None) -> bool:
    """Duration form of sleep_until."""
    return sleep_until(now() + max(0.0, seconds), should_abort)
