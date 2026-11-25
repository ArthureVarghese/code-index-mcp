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
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        logger.debug(
            "SearchEngine :: search :: query=%s, kind=%s, limit=%s, path=%s",
            query, kind, limit, path,
        )
        symbol_results = self.symbols.search(
            query,
            kind=kind,
            limit=limit,
            path=path,
        )

        text_results = self.fts.search(
            query,
            kind=kind,
            limit=limit,
            path=path,
        )

        heading_results: list[dict[str, Any]] = []
        if kind in ("all", "markdown"):
            heading_results = self._repos.search_headings(
                query, limit=limit, path=path
            )

        semantic_results = self.semantic.search(query, limit=limit) if self.semantic.enabled else []
        if path and self.semantic.enabled:
            semantic_results = [
                r for r in semantic_results
                if r.get("path", "").lstrip("file:") == path
            ]

        merged = self._merge(
            symbol_results,
            text_results,
            heading_results,
            semantic_results,
        )

        ranked = self.ranker.rank(query, merged)[:limit]
        logger.info("SearchEngine :: search :: query=%s returned %d results", query, len(ranked))
        return ranked

    def search_many(
        self,
        keywords: list[str],
        *,
        kind: str = "all",
        limit: int = 10,
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run several keyword searches and merge them into one deduplicated list.

        Each keyword is searched independently using the full hybrid pipeline,
        then results are merged across keywords keyed by ``entity_id``: scores
        are summed (an entity matching multiple keywords ranks higher) and the
        matching keyword(s) are accumulated onto the result as ``keywords``.
        """
        logger.debug(
            "SearchEngine :: search_many :: keywords=%s, kind=%s, limit=%s, path=%s",
            keywords, kind, limit, path,
        )
        queries = [k.strip() for k in keywords if k and k.strip()]
        if not queries:
            return []

        merged: dict[str, dict[str, Any]] = {}
        for query in queries:
            for result in self.search(query, kind=kind, limit=limit, path=path):
                entity_id = result.get("entity_id")
                if not entity_id:
                    continue
                if entity_id not in merged:
                    entry = dict(result)
                    entry["keywords"] = []
                    merged[entity_id] = entry
                entry = merged[entity_id]
                entry["score"] = float(entry.get("score", 0)) + float(result.get("score", 0))
                if query not in entry["keywords"]:
                    entry["keywords"].append(query)

        results = sorted(
            merged.values(),
            key=lambda r: float(r.get("score", 0)),
            reverse=True,
        )[:limit]
        logger.info(
            "SearchEngine :: search_many :: keywords=%s returned %d results",
            keywords, len(results),
        )
        return results

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
