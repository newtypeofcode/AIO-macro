"""Keyboard controller. Callers speak Win32 VK codes."""
import time

from . import _input_win as backend
from . import pacing
from . import keys as keymod


class Keyboard:
    def key_down(self, vk: int) -> None:
        # Raw and UNPACED: recordings time these from their own timestamps.
        backend.key_down(int(vk))

    def key_up(self, vk: int) -> None:
        backend.key_up(int(vk))

    def move_key_down(self, name: str) -> None:
        backend.move_key_down(name)

    def move_key_up(self, name: str) -> None:
        backend.move_key_up(name)

    def tap(self, vk: int, hold: float = 0.03, pace: bool = True) -> None:
        backend.key_down(int(vk))
        try:
            time.sleep(max(0.0, hold))
        finally:
            # try/finally like combo(): SendInput raises when injection is
            # refused mid-tap, and a skipped key_up leaves the key physically
            # held -- a stuck W walks the character until the app is closed.
            backend.key_up(int(vk))
        if pace:
            pacing.action_pause()

    def tap_name(self, name: str, hold: float = 0.03, pace: bool = True) -> bool:
        vk = keymod.key_name_to_vk(name)
        if vk is None:
            return False
        self.tap(vk, hold, pace)
        return True

    def combo(self, *vks, hold: float = 0.05) -> None:
        """All down in order, all up in REVERSE order -- releasing a modifier
        before the key it modifies is how Ctrl+C turns into a bare C."""
        pressed = []
        try:
            for vk in vks:
                backend.key_down(int(vk))
                pressed.append(int(vk))
            time.sleep(max(0.0, hold))
        finally:
            for vk in reversed(pressed):
                backend.key_up(vk)
        pacing.action_pause()

    def combo_names(self, names, hold: float = 0.05) -> bool:
        vks = []
        for name in names:
            vk = keymod.key_name_to_vk(name)
            if vk is None:
                return False
            vks.append(vk)
        if not vks:
            return False
        self.combo(*vks, hold=hold)
        return True

    def type_text(self, text: str, delay: float = 0.02, stop_event=None) -> None:
        """Unicode injection, so non-ASCII text types correctly regardless of
        the active keyboard layout.

        stop_event is checked per character: without it, Stop could not cut
        into a long Type Text block and had to wait out every keystroke.
        """
        for ch in str(text):
            if stop_event is not None and stop_event.is_set():
                return
            if ch == "\n":
                self.tap(keymod.VK_RETURN, pace=False)
            elif ch == "\t":
                self.tap(keymod.VK_TAB, pace=False)
            else:
                backend.unicode_char(ch, up=False)
                backend.unicode_char(ch, up=True)
            time.sleep(max(0.0, delay))
        pacing.action_pause()

    def is_down(self, vk: int) -> bool:
        return backend.is_key_down(int(vk))
