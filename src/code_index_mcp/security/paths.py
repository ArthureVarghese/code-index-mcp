from __future__ import annotations

from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a path escapes the configured project root."""


class ProjectPathGuard:
    """Restrict filesystem operations to one canonical project root."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve(strict=True)

        if not self.root.is_dir():
            raise PathSecurityError(f"Not a directory: {self.root}")

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)

        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        else:
            resolved = (self.root / candidate).resolve(strict=False)

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise PathSecurityError(f"Path escapes project root: {path}") from exc

        return resolved

    def relative(self, path: str | Path) -> str:
        resolved = self.resolve(path)
        return resolved.relative_to(self.root).as_posix()

    def contains(self, path: str | Path) -> bool:
        try:
            self.resolve(path)
            return True
        except PathSecurityError:
            return False
