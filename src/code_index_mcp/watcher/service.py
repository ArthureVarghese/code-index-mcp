from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileWatcher:
    """Simple polling-based source file watcher."""

    def __init__(
        self,
        root: str | Path,
        callback: Callable[[Path], None],
        *,
        debounce_seconds: float = 0.25,
        interval_seconds: float = 0.1,
        ignore: Any | None = None,
        extensions: frozenset[str] | None = None,
        excluded_directories: frozenset[str] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.callback = callback
        self.debounce_seconds = max(0.0, debounce_seconds)
        self.interval_seconds = max(0.01, interval_seconds)
        self.ignore = ignore
        self.extensions = extensions or frozenset({".py", ".pyi", ".md", ".markdown"})
        self.excluded_directories = excluded_directories or frozenset()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot: dict[str, tuple[int, int]] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        logger.info("FileWatcher :: start :: watching %s", self.root)

        # Capture the baseline before starting the polling loop.
        self._snapshot = self._take_snapshot()

        self._thread = threading.Thread(
            target=self._run,
            name="code-index-file-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        logger.info("FileWatcher :: stop :: stopped watching %s", self.root)

        thread = self._thread

        if thread is not None and thread.is_alive():
            thread.join(timeout=max(1.0, self.interval_seconds * 10))

        self._thread = None

    def _run(self) -> None:
        pending = False
        last_change = 0.0

        while not self._stop_event.wait(self.interval_seconds):
            current = self._take_snapshot()

            if current != self._snapshot:
                self._snapshot = current
                pending = True
                last_change = time.monotonic()

            if pending:
                elapsed = time.monotonic() - last_change

                if elapsed >= self.debounce_seconds:
                    pending = False

                    try:
                        self.callback(self.root)
                    except Exception:
                        logger.exception(
                            "FileWatcher :: _run :: callback error for %s",
                            self.root,
                        )
                        continue

    def _take_snapshot(self) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}

        if not self.root.exists():
            return snapshot

        def walk(directory: Path) -> None:
            try:
                entries = list(os.scandir(directory))
            except OSError:
                return

            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue

                    path = Path(entry.path)

                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in self.excluded_directories:
                            continue
                        if self.ignore and self.ignore.is_ignored_dir(path):
                            continue
                        walk(path)
                        continue

                    if not entry.is_file(follow_symlinks=False):
                        continue

                    if path.suffix.lower() not in self.extensions:
                        continue

                    if self.ignore and self.ignore.is_ignored(path):
                        continue

                    stat = path.stat()
                    snapshot[path.relative_to(self.root).as_posix()] = (
                        stat.st_mtime_ns,
                        stat.st_size,
                    )
                except OSError:
                    continue

        walk(self.root)
        return snapshot

    def __enter__(self) -> FileWatcher:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()
