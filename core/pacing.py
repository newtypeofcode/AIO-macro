"""Global 'macro speed' knob -- one extra delay applied at the input choke
points every action flows through, so a single setting slows everything.

Module-level rather than per-instance: Mouse/Keyboard objects get built in
several places, and a single float assignment is atomic under the GIL, so
no lock is needed.
"""
import time

_action_delay_s = 0.0


def set_action_delay_ms(ms) -> None:
    try:
        value = int(ms)
    except (TypeError, ValueError):
        value = 0
    value = max(0, min(2000, value))
    global _action_delay_s
    _action_delay_s = value / 1000.0


def get_action_delay_ms() -> int:
    return int(round(_action_delay_s * 1000))


def action_pause() -> None:
    # Fast path at the 0ms default: no sleep syscall at all.
    if _action_delay_s > 0:
        time.sleep(_action_delay_s)
