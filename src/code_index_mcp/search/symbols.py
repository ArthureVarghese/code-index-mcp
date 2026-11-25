from __future__ import annotations

from typing import Any


class SymbolSearch:
    def __init__(self, repositories: Any):
        self.repositories = repositories

    def search(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repositories.search_symbols(
            query, kind=kind, limit=limit, path=path
        )
