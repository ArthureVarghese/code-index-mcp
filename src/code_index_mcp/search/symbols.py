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
        tokens: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {"kind": kind, "limit": limit, "path": path}
        if tokens is not None:
            kwargs["tokens"] = tokens
        return self.repositories.search_symbols(query, **kwargs)
