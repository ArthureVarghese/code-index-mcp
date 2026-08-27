from __future__ import annotations

import logging
from typing import Any

from code_index_mcp.search.fts import FTSSearch
from code_index_mcp.search.ranking import SearchRanker
from code_index_mcp.search.semantic import SemanticSearch
from code_index_mcp.search.symbols import SymbolSearch

logger = logging.getLogger(__name__)


class SearchEngine:
    def __init__(
        self,
        repositories: Any,
        *,
        embedding_provider: Any = None,
    ):
        self.fts = FTSSearch(repositories)
        self.symbols = SymbolSearch(repositories)
        self.semantic = SemanticSearch(embedding_provider)
        self.ranker = SearchRanker()
        self._repos = repositories

    def search(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        logger.debug("SearchEngine :: search :: query=%s, kind=%s, limit=%s", query, kind, limit)
        symbol_results = self.symbols.search(
            query,
            kind=kind,
            limit=limit,
        )

        text_results = self.fts.search(
            query,
            kind=kind,
            limit=limit,
        )

        heading_results: list[dict[str, Any]] = []
        if kind in ("all", "markdown"):
            heading_results = self._repos.search_headings(query, limit=limit)

        semantic_results = self.semantic.search(query, limit=limit) if self.semantic.enabled else []

        merged = self._merge(
            symbol_results,
            text_results,
            heading_results,
            semantic_results,
        )

        ranked = self.ranker.rank(query, merged)[:limit]
        logger.info("SearchEngine :: search :: query=%s returned %d results", query, len(ranked))
        return ranked

    @staticmethod
    def _merge(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}

        for group in groups:
            for result in group:
                entity_id = result.get("entity_id")
                if not entity_id:
                    continue

                if entity_id not in merged:
                    merged[entity_id] = dict(result)
                else:
                    merged[entity_id]["score"] = float(merged[entity_id].get("score", 0)) + float(
                        result.get("score", 0)
                    )

        return list(merged.values())
