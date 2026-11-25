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
        return self._search_once(query, kind=kind, limit=limit, path=path)

    def search_many(
        self,
        keywords: list[str],
        *,
        kind: str = "all",
        limit: int = 10,
        path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run one hybrid search with all keywords and tag each result."""
        logger.debug(
            "SearchEngine :: search_many :: keywords=%s, kind=%s, limit=%s, path=%s",
            keywords, kind, limit, path,
        )
        queries = [k.strip() for k in keywords if k and k.strip()]
        if not queries:
            return []

        combined = " ".join(queries)
        ranked = self._search_once(
            combined,
            kind=kind,
            limit=limit,
            path=path,
            tokens=queries,
        )

        results = []
        for result in ranked:
            entry = dict(result)
            matched = self._matching_keywords(entry, queries)
            entry["keywords"] = matched
            entry["score"] = float(entry.get("score", 0)) + 2.0 * len(matched)
            results.append(entry)

        results.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
        logger.info(
            "SearchEngine :: search_many :: keywords=%s returned %d results",
            keywords, len(results),
        )
        return results[:limit]

    def _search_once(
        self,
        query: str,
        *,
        kind: str,
        limit: int,
        path: str | None,
        tokens: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        logger.debug(
            "SearchEngine :: _search_once :: query=%s, kind=%s, limit=%s, path=%s",
            query, kind, limit, path,
        )
        extra: dict[str, Any] = {}
        if tokens is not None:
            extra["tokens"] = tokens

        symbol_results = self.symbols.search(
            query, kind=kind, limit=limit, path=path, **extra
        )
        text_results = self.fts.search(
            query, kind=kind, limit=limit, path=path, **extra
        )

        heading_results: list[dict[str, Any]] = []
        if kind in ("all", "markdown"):
            heading_extra = {"tokens": tokens} if tokens is not None else {}
            heading_results = self._repos.search_headings(
                query, limit=limit, path=path, **heading_extra
            )

        semantic_results = self.semantic.search(query, limit=limit) if self.semantic.enabled else []
        if path and self.semantic.enabled:
            semantic_results = [
                r for r in semantic_results
                if r.get("path", "").removeprefix("file:") == path
            ]

        merged = self._merge(
            symbol_results,
            text_results,
            heading_results,
            semantic_results,
        )

        ranked = self.ranker.rank(query, merged)[:limit]
        logger.info(
            "SearchEngine :: _search_once :: query=%s returned %d results",
            query,
            len(ranked),
        )
        return ranked

    @staticmethod
    def _matching_keywords(result: dict[str, Any], queries: list[str]) -> list[str]:
        haystack = " ".join(
            str(result.get(field, "")).lower()
            for field in ("name", "path", "qualified_name", "text", "heading_path")
        )
        matched = [query for query in queries if query.lower() in haystack]
        return list(dict.fromkeys(matched))

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
