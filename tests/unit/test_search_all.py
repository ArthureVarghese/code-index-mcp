from __future__ import annotations

from unittest.mock import MagicMock

from code_index_mcp.indexing.python.analyzer import PythonAnalyzer
from code_index_mcp.search.engine import SearchEngine
from code_index_mcp.search.fts import FTSSearch
from code_index_mcp.search.ranking import SearchRanker
from code_index_mcp.search.semantic import SemanticSearch
from code_index_mcp.search.symbols import SymbolSearch
from code_index_mcp.storage.database import Database
from code_index_mcp.storage.repositories import RepositoryStore


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
        repos.search_symbols.assert_called_once_with(
            "foo", kind="all", limit=20, path=None
        )

    def test_search_kind_passthrough(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        ss = SymbolSearch(repos)
        ss.search("incremental", kind="markdown")
        repos.search_symbols.assert_called_once_with(
            "incremental", kind="markdown", limit=20, path=None
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
            "incremental", kind="markdown", limit=10, path=None
        )

    def test_search_forwards_path_to_backends(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        repos.search_headings.return_value = []
        engine = SearchEngine(repos)
        engine.search("auth", kind="all", path="src/auth.py")
        repos.search_symbols.assert_called_once_with(
            "auth", kind="all", limit=10, path="src/auth.py"
        )
        repos.search_text.assert_called_once_with(
            "auth", kind="all", limit=10, path="src/auth.py"
        )
        repos.search_headings.assert_called_once_with(
            "auth", limit=10, path="src/auth.py"
        )


class TestSearchEngineBatch:
    def test_search_many_deduplicates_and_tags(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e1", "name": "foo", "score": 1.0}
        ]
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        results = engine.search_many(["foo", "bar"])
        entity_ids = [r["entity_id"] for r in results]
        assert entity_ids.count("e1") == 1
        assert "keywords" in results[0]

    def test_search_many_sums_scores_for_shared_entity(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e1", "name": "token", "score": 2.0}
        ]
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        results = engine.search_many(["token", "token"])
        assert len(results) == 1
        assert results[0]["keywords"] == ["token"]
        assert float(results[0]["score"]) > 2.0

    def test_search_many_merges_different_entities(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e:foo", "name": "foo", "score": 1.0},
            {"entity_id": "e:baz", "name": "baz", "score": 1.0},
        ]
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        results = engine.search_many(["foo", "baz"])
        ids = {r["entity_id"] for r in results}
        assert ids == {"e:foo", "e:baz"}

    def test_search_many_empty_and_blank_keywords(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        assert engine.search_many([]) == []
        assert engine.search_many(["", "   "]) == []

    def test_search_many_respects_limit(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e1", "name": "a", "score": 1.0},
            {"entity_id": "e2", "name": "b", "score": 2.0},
            {"entity_id": "e3", "name": "c", "score": 3.0},
        ]
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        results = engine.search_many(["a", "b"], limit=2)
        assert len(results) <= 2

    def test_search_many_runs_one_pipeline_pass(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        repos.search_headings.return_value = []
        engine = SearchEngine(repos)
        engine.search_many(["auth", "token", "scope", "user"], path="src/auth.py")
        repos.search_symbols.assert_called_once_with(
            "auth token scope user",
            kind="all",
            limit=10,
            path="src/auth.py",
            tokens=["auth", "token", "scope", "user"],
        )
        repos.search_text.assert_called_once()
        repos.search_headings.assert_called_once()

    def test_search_many_forwards_path(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        repos.search_headings.return_value = []
        engine = SearchEngine(repos)
        engine.search_many(["auth", "token"], path="src/auth.py")
        repos.search_symbols.assert_called_once_with(
            "auth token",
            kind="all",
            limit=10,
            path="src/auth.py",
            tokens=["auth", "token"],
        )

    def test_search_many_attributes_tokens_from_their_source(self):
        repos = MagicMock()
        repos.search_symbols.return_value = [
            {"entity_id": "e1", "name": "foo", "score": 1.0}
        ]
        repos.search_text.return_value = [
            {"entity_id": "e2", "name": "other", "text": "only bar here", "score": 1.0}
        ]
        engine = SearchEngine(repos)

        results = {r["entity_id"]: r for r in engine.search_many(["foo", "bar"])}

        assert results["e1"]["keywords"] == ["foo"]
        assert results["e2"]["keywords"] == ["bar"]

    def test_semantic_path_filter_removes_prefix_only(self):
        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        engine = SearchEngine(repos)
        engine.semantic = MagicMock()
        engine.semantic.enabled = True
        engine.semantic.search.return_value = [
            {"entity_id": "e1", "path": "file:error.py", "name": "x", "score": 1.0}
        ]

        results = engine.search("x", path="error.py")

        assert [r["entity_id"] for r in results] == ["e1"]


class TestSearchDocumentBatching:
    def test_unchanged_search_documents_skip_fts_rewrite(self, tmp_path):
        db = Database(tmp_path / "fts.db")
        try:
            db.execute(
                """
                INSERT INTO projects (
                    project_id, canonical_root, schema_version,
                    indexer_version, indexing_state, configuration_fingerprint
                ) VALUES ('p', ?, 1, 'test', 'ready', '')
                """,
                (str(tmp_path),),
            )
            repos = RepositoryStore(db.connection)
            repos.set_project_id("p")
            analyzed = PythonAnalyzer().analyze(
                "def foo():\n    return 1\n",
                "a.py",
                project_id="p",
                file_id="file:a.py",
            )

            repos.upsert_entities(analyzed.entities)

            statements: list[str] = []
            db.connection.set_trace_callback(statements.append)
            try:
                repos.upsert_entities(analyzed.entities)
            finally:
                db.connection.set_trace_callback(None)

            assert not any("search_fts" in statement for statement in statements)
            db.execute("INSERT INTO search_fts(search_fts) VALUES('integrity-check')")
        finally:
            db.close()
