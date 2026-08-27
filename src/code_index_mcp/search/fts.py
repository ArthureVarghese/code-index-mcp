from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


class FTSSearch:
    """SQLite FTS-backed search with a safe fallback."""

    def __init__(self, repositories: Any):
        self.repositories = repositories

    def search(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        tokens = _TOKEN_RE.findall(query)

        if not tokens:
            return []

        return self.repositories.search_text(
            " ".join(tokens),
            kind=kind,
            limit=limit,
        )
