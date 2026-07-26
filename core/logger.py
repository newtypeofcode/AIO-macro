"""Timestamped append-only log. The UI shows the bare message."""
import time

from .constants import LOG_FILE


class Logger:
    """Lazy, self-healing file logger: no handle is opened until the first
    write, and an OSError drops the handle so the next call reopens."""

    def __init__(self):
        self._file = None

    def _get_file(self):
        if self._file is None:
            try:
                self._file = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
            except OSError:
                return None
        return self._file

    def log(self, message: str) -> None:
        fh = self._get_file()
        if fh is None:
            return
        try:
            fh.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), message))
            fh.flush()
        except OSError:
            self._file = None

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
