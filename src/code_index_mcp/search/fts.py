from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


def tokenize(text: str) -> list[str]:
    """Split a query string into keyword tokens (identifiers/dotted names)."""
    return _TOKEN_RE.findall(text)


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
        path: str | None = None,
        tokens: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        explicit = tokens is not None
        if tokens is None:
            tokens = tokenize(query)
            query = " ".join(tokens)

        if not tokens:
            return []

        kwargs: dict[str, Any] = {"kind": kind, "limit": limit, "path": path}
        if explicit:
            kwargs["tokens"] = tokens
        return self.repositories.search_text(query, **kwargs)
