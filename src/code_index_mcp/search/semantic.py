from __future__ import annotations

from typing import Any


class SemanticSearch:
    """Optional semantic search adapter.

    No embedding provider is required. When no provider is configured,
    search simply returns an empty result set.
    """

    def __init__(self, provider: Any = None):
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not self.provider:
            return []

        return self.provider.search(query, limit=limit)
