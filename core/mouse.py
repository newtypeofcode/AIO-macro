"""Screen-space mouse controller. All coordinates are absolute screen px."""
import time

from . import _input_win as backend
from . import pacing


class Mouse:
    def move_to(self, x: int, y: int) -> None:
        backend.move_abs(int(x), int(y))

    def nudge(self, dx: int = 1, dy: int = 0) -> None:
        """Tiny RELATIVE move. Some UI only registers hover from a genuine
        relative-move event, which an absolute jump never fires."""
        backend.move_rel(int(dx), int(dy))

    def down(self, button: str = "left") -> None:
        backend.button_down(button)

    def up(self, button: str = "left") -> None:
        backend.button_up(button)

    def click(self, x=None, y=None, button: str = "left", hold: float = 0.04,
              pace: bool = True) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
            time.sleep(0.012)
            self.nudge(1, 0)
            self.nudge(-1, 0)
        backend.button_down(button)
        try:
            time.sleep(max(0.0, hold))
        finally:
            # try/finally like drag(): SendInput raises when injection is
            # refused (an elevated window takes focus, the UAC secure desktop
            # appears), and a swallowed button_up leaves the button
            # physically held for the rest of the session.
            backend.button_up(button)
        if pace:
            pacing.action_pause()

    def double_click(self, x=None, y=None, button: str = "left", gap: float = 0.07) -> None:
        self.multi_click(x, y, button, count=2, gap=gap)

    def multi_click(self, x=None, y=None, button: str = "left", count: int = 1,
                    hold: float = 0.04, gap: float = 0.07) -> None:
        """N clicks at one spot.

        Pacing is applied ONCE at the end rather than per click: the global
        Macro Speed delay between the two clicks of a double-click pushes
        them past the system double-click time, and the target then sees two
        unrelated single clicks.
        """
        count = max(1, int(count))
        for i in range(count):
            self.click(x if i == 0 else None, y if i == 0 else None,
                       button, hold, pace=False)
            if i < count - 1:
                time.sleep(gap)
        pacing.action_pause()

    def drag(self, x1, y1, x2, y2, button: str = "left",
             steps: int = 24, duration: float = 0.25) -> None:
        """Linear interpolated move while the button is held. Interpolated
        rather than a single jump because a teleporting cursor reads as a
        click at the destination, not a drag."""
        self.move_to(x1, y1)
        time.sleep(0.03)
        backend.button_down(button)
        try:
            steps = max(1, int(steps))
            delay = max(0.0, duration) / steps
            for i in range(1, steps + 1):
                t = i / steps
                self.move_to(int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t))
                time.sleep(delay)
        finally:
            # Never leave the button physically held: every later move would
            # become a drag for the rest of the session.
            backend.button_up(button)
        pacing.action_pause()

    def move_path(self, points, duration: float = 0.3) -> None:
        """Replay a recorded cursor path through its own points."""
        if not points:
            return
        delay = max(0.0, duration) / max(1, len(points))
        for px, py in points:
            self.move_to(int(px), int(py))
            time.sleep(delay)

    def scroll(self, amount: int, horizontal: bool = False) -> None:
        # Windows wheel-delta units: +-120 per notch. No action_pause --
        # callers already pace tight scroll loops themselves.
        backend.scroll(int(amount), horizontal)

    def position(self):
        return backend.cursor_pos()
