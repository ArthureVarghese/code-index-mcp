from __future__ import annotations

import hashlib
from pathlib import Path


def canonical_project_root(project_root: str | Path) -> Path:
    return Path(project_root).expanduser().resolve(strict=False)


def project_id_for_root(project_root: str | Path) -> str:
    """Return a stable project identifier derived from the canonical root."""
    canonical = canonical_project_root(project_root)

    return hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()[:32]
