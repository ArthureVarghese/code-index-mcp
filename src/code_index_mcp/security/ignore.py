from __future__ import annotations

import logging
import os
import re
from fnmatch import translate
from pathlib import Path

from ..config import IndexConfig

logger = logging.getLogger(__name__)


class IgnoreMatcher:
    """Simple deterministic ignore matcher.

    Gitignore-style matching can be expanded later without changing callers.
    """

    def __init__(self, root: Path, config: IndexConfig) -> None:
        self.root = root.resolve()
        self.config = config
        self.patterns = self._load_patterns()
        self._compiled_patterns = [
            re.compile(translate(os.path.normcase(pattern))) for pattern in self.patterns
        ]

    def _relative(self, path: Path) -> Path:
        candidate = path.resolve() if path.is_symlink() else path
        return candidate.relative_to(self.root)

    def is_ignored_dir(self, path: Path) -> bool:
        try:
            relative = self._relative(path)
        except ValueError:
            return True

        if any(part in self.config.excluded_directories for part in relative.parts):
            logger.debug("IgnoreMatcher :: is_ignored_dir :: excluded directory: %s", path)
            return True

        normalized = os.path.normcase(relative.as_posix())
        name = os.path.normcase(relative.name)
        if any(
            pattern.match(normalized) or pattern.match(name)
            for pattern in self._compiled_patterns
        ):
            logger.debug("IgnoreMatcher :: is_ignored_dir :: matched pattern: %s", path)
            return True

        return False

    def _load_patterns(self) -> list[str]:
        patterns: list[str] = []

        for filename in (".gitignore", ".code-index-ignore"):
            path = self.root / filename

            if not path.is_file():
                continue

            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()

                    if line and not line.startswith("#"):
                        patterns.append(line)
            except UnicodeDecodeError:
                continue

        return patterns

    def is_ignored(self, path: Path) -> bool:
        try:
            relative = self._relative(path)
        except ValueError:
            return True

        if any(part in self.config.excluded_directories for part in relative.parts[:-1]):
            logger.debug("IgnoreMatcher :: is_ignored :: excluded directory: %s", path)
            return True

        if relative.name in self.config.excluded_files:
            logger.debug("IgnoreMatcher :: is_ignored :: excluded file: %s", path)
            return True

        if path.suffix.lower() not in self.config.extensions:
            logger.debug("IgnoreMatcher :: is_ignored :: excluded extension: %s", path)
            return True

        normalized = os.path.normcase(relative.as_posix())
        name = os.path.normcase(relative.name)

        if any(
            pattern.match(normalized) or pattern.match(name)
            for pattern in self._compiled_patterns
        ):
            logger.debug("IgnoreMatcher :: is_ignored :: matched pattern: %s", path)
            return True

        return False
