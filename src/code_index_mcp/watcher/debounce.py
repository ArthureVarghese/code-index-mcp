from __future__ import annotations

import threading
from collections.abc import Callable


class Debouncer:
    def __init__(
        self,
        delay: float,
        callback: Callable[[str], None],
    ):
        self.delay = delay
        self.callback = callback
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def submit(self, path: str) -> None:
        with self._lock:
            timer = self._timers.pop(path, None)

            if timer:
                timer.cancel()

            timer = threading.Timer(
                self.delay,
                self._fire,
                args=(path,),
            )
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)

        self.callback(path)

    def close(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()

        for timer in timers:
            timer.cancel()
