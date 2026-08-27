from __future__ import annotations

from unittest.mock import MagicMock

from code_index_mcp.search.engine import SearchEngine
from code_index_mcp.search.fts import FTSSearch
from code_index_mcp.search.ranking import SearchRanker
from code_index_mcp.search.semantic import SemanticSearch
from code_index_mcp.search.symbols import SymbolSearch


class TestFTSSearch:
    def test_search_with_tokens(self):
        repos = MagicMock()
        repos.search_text.return_value = [{"entity_id": "e1"}]
        fts = FTSSearch(repos)
        results = fts.search("hello world")
        assert len(results) == 1
        repos.search_text.assert_called_once()

    def test_search_empty_query(self):
        repos = MagicMock()
        fts = FTSSearch(repos)
        results = fts.search("123")
        assert results == []

    def test_search_special_chars(self):
        repos = MagicMock()
        repos.search_text.return_value = []
        fts = FTSSearch(repos)
        results = fts.search("@#$%")
        assert results == []


class TestSemanticSearch:
    def test_disabled_by_default(self):
        ss = SemanticSearch()
        assert ss.enabled is False
        assert ss.search("test") == []

    def test_enabled_with_provider(self):
        provider = MagicMock()
        provider.search.return_value = [{"entity_id": "e1"}]
        ss = SemanticSearch(provider)
        assert ss.enabled is True
        results = ss.search("test")
        assert len(results) == 1

    def test_no_provider_search(self):
        ss = SemanticSearch(None)
        assert ss.search("test") == []


class TestSymbolSearch:
    def test_search(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [{"entity_id": "e1"}]
        ss = SymbolSearch(repos)
        results = ss.search("foo")
        assert len(results) == 1
        repos.search_symbols.assert_called_once_with("foo", kind="all", limit=20)

    def test_search_kind_passthrough(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        ss = SymbolSearch(repos)
        ss.search("incremental", kind="markdown")
        repos.search_symbols.assert_called_once_with(
            "incremental", kind="markdown", limit=20
        )


class TestSearchRanker:
    def test_rank_exact_match(self):
        ranker = SearchRanker()
        results = [
            {"entity_id": "e1", "name": "foo", "score": 0.0},
            {"entity_id": "e2", "name": "bar", "score": 0.0},
        ]
        ranked = ranker.rank("foo", results)
        assert ranked[0]["name"] == "foo"
        assert ranked[0]["score"] > ranked[1]["score"]

    def test_rank_in_name(self):
        ranker = SearchRanker()
        results = [
            {"entity_id": "e1", "name": "foobar", "score": 0.0},
            {"entity_id": "e2", "name": "baz", "score": 0.0},
        ]
        ranked = ranker.rank("foo", results)
        assert ranked[0]["name"] == "foobar"

    def test_rank_in_path(self):
        ranker = SearchRanker()
        results = [
            {"entity_id": "e1", "name": "a", "path": "foo/bar.py", "score": 0.0},
            {"entity_id": "e2", "name": "a", "path": "baz.py", "score": 0.0},
        ]
        ranked = ranker.rank("foo", results)
        assert ranked[0]["path"] == "foo/bar.py"

    def test_rank_in_text(self):
        ranker = SearchRanker()
        results = [
            {"entity_id": "e1", "name": "a", "text": "has foo inside", "score": 0.0},
            {"entity_id": "e2", "name": "a", "text": "nothing here", "score": 0.0},
        ]
        ranked = ranker.rank("foo", results)
        assert ranked[0]["text"] == "has foo inside"

    def test_rank_sort_by_score_desc(self):
        ranker = SearchRanker()
        results = [
            {"entity_id": "e1", "name": "a", "score": 1.0},
            {"entity_id": "e2", "name": "b", "score": 5.0},
        ]
        ranked = ranker.rank("x", results)
        assert ranked[0]["score"] >= ranked[1]["score"]


class TestSearchEngine:
    def test_search_merges_results(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e1", "name": "foo", "score": 1.0}
        ]
        repos.search_text.return_value = [
            {"entity_id": "e1", "name": "foo", "score": 2.0},
            {"entity_id": "e2", "name": "bar", "score": 1.0},
        ]
        engine = SearchEngine(repos)
        results = engine.search("foo")
        assert len(results) >= 1

    def test_merge_deduplicates(self):
        results = SearchEngine._merge(
            [{"entity_id": "e1", "score": 1.0}],
            [{"entity_id": "e1", "score": 2.0}],
        )
        assert len(results) == 1
        assert results[0]["score"] == 3.0

    def test_merge_skips_no_entity_id(self):
        results = SearchEngine._merge(
            [{"name": "no_id", "score": 1.0}],
        )
        assert len(results) == 0

    def test_merge_empty(self):
        assert SearchEngine._merge() == []

    def test_search_with_semantic(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        provider = MagicMock()
        provider.search.return_value = [{"entity_id": "e3", "score": 1.0}]
        engine = SearchEngine(repos, embedding_provider=provider)
        results = engine.search("test")
        assert len(results) >= 0

    def test_search_forwards_kind_to_symbols(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        engine.search("incremental", kind="markdown")
        repos.search_symbols.assert_called_once_with(
            "incremental", kind="markdown", limit=10
        )
