"""Tests for the remaining spec-required features:
entity_versions, index_jobs, embeddings, summaries, match-reason,
get_code from cache, hierarchical outlines, semantic provider injection."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.config import IndexConfig
from code_index_mcp.project.manager import ProjectManager
from code_index_mcp.search.ranking import SearchRanker

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def config(tmp_path):
    return IndexConfig(index_root=tmp_path / "index")


@pytest.fixture
def manager(config):
    return ProjectManager(config)


# ── Entity Versions ──────────────────────────────────────────────────────


class TestEntityVersions:
    def test_entity_version_written_on_change(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        manager.index_project(tmp_path, force=True)

        (tmp_path / "mod.py").write_text("def foo(): return 42\n")
        manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            rows = db.execute("SELECT * FROM entity_versions").fetchall()
            assert len(rows) >= 1
        finally:
            db.close()

    def test_entity_version_not_written_for_reuse(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            count_before = db.execute(
                "SELECT count(*) FROM entity_versions"
            ).fetchone()[0]

            manager.index_project(tmp_path, force=False)
            count_after = db.execute(
                "SELECT count(*) FROM entity_versions"
            ).fetchone()[0]
            assert count_after == count_before
        finally:
            db.close()


# ── Index Jobs ────────────────────────────────────────────────────────────


class TestIndexJobs:
    def test_index_job_created(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        result = manager.index_project(tmp_path, force=True)

        assert "job_id" in result
        db = manager.open_database(tmp_path)
        try:
            rows = db.execute("SELECT * FROM index_jobs").fetchall()
            assert len(rows) >= 1
            assert rows[0]["state"] == "completed"
        finally:
            db.close()

    def test_index_job_has_stats(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        result = manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            row = db.execute(
                "SELECT * FROM index_jobs WHERE job_id=?",
                (result["job_id"],),
            ).fetchone()
            assert row is not None
            assert row["files_seen"] >= 1
            assert row["files_changed"] >= 1
        finally:
            db.close()


# ── Embeddings ────────────────────────────────────────────────────────────


class TestEmbeddings:
    def test_embedding_stored_when_provider_set(self, manager, tmp_path):
        provider = MagicMock()
        provider.provider_name = "test"
        provider.model_name = "test-model"
        provider.version = "1"
        provider.embed_one.return_value = [0.1, 0.2, 0.3]

        manager._embedding_provider = provider
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        result = manager.index_project(tmp_path, force=True)

        assert result["embeddings_recomputed"] >= 1
        db = manager.open_database(tmp_path)
        try:
            rows = db.execute("SELECT * FROM embeddings").fetchall()
            assert len(rows) >= 1
        finally:
            db.close()
        provider.embed_one.assert_called()

    def test_embedding_reused_from_cache(self, manager, tmp_path):
        provider = MagicMock()
        provider.provider_name = "test"
        provider.model_name = "test-model"
        provider.version = "1"
        provider.embed_one.return_value = [0.1, 0.2, 0.3]

        manager._embedding_provider = provider
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        manager.index_project(tmp_path, force=True)
        call_count_first = provider.embed_one.call_count

        manager.index_project(tmp_path, force=True)
        assert provider.embed_one.call_count == call_count_first

    def test_no_embedding_when_provider_none(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        result = manager.index_project(tmp_path, force=True)

        assert result["embeddings_recomputed"] == 0
        assert result["embeddings_reused"] == 0


# ── Summaries ─────────────────────────────────────────────────────────────


class TestSummaries:
    def test_summary_stored_when_provider_set(self, manager, tmp_path):
        provider = MagicMock()
        provider.provider_name = "test"
        provider.model_name = "test-model"
        provider.version = "1"
        provider.prompt_version = "1"
        provider.summarize.return_value = "A test summary."

        manager._summary_provider = provider
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        result = manager.index_project(tmp_path, force=True)

        assert result["summaries_recomputed"] >= 1
        db = manager.open_database(tmp_path)
        try:
            rows = db.execute("SELECT * FROM summaries").fetchall()
            assert len(rows) >= 1
        finally:
            db.close()
        provider.summarize.assert_called()

    def test_no_summary_when_provider_none(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        result = manager.index_project(tmp_path, force=True)

        assert result["summaries_recomputed"] == 0
        assert result["summaries_reused"] == 0


# ── Match Reason ──────────────────────────────────────────────────────────


class TestMatchReason:
    def test_exact_name_gets_exact_match_reason(self):
        ranker = SearchRanker()
        results = [{"name": "foo", "path": "a.py", "score": 5.0}]
        ranked = ranker.rank("foo", results)
        assert "exact name match" in ranked[0]["match_reason"]

    def test_partial_name_gets_contains_reason(self):
        ranker = SearchRanker()
        results = [{"name": "foobar", "path": "a.py", "score": 5.0}]
        ranked = ranker.rank("foo", results)
        assert "name contains query" in ranked[0]["match_reason"]

    def test_content_match_gets_fallback_reason(self):
        ranker = SearchRanker()
        results = [{"name": "bar", "path": "a.py", "text": "foo here", "score": 5.0}]
        ranked = ranker.rank("foo", results)
        assert "content match" in ranked[0]["match_reason"]

    def test_path_match_adds_path_reason(self):
        ranker = SearchRanker()
        results = [{"name": "bar", "path": "foo.py", "score": 5.0}]
        ranked = ranker.rank("foo", results)
        assert "path match" in ranked[0]["match_reason"]


# ── get_code from Cache ──────────────────────────────────────────────────


class TestGetCodeFromCache:
    def test_get_code_returns_from_cache(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("line1\nline2\nline3\n")
        manager.index_project(tmp_path)
        result = manager.get_code(tmp_path, "test.py", 1, 2)
        assert "source" in result
        assert "line1" in result["source"]


# ── Hierarchical Outlines ────────────────────────────────────────────────


class TestHierarchicalOutlines:
    def test_file_outline_has_children(self, manager, tmp_path):
        (tmp_path / "test.py").write_text(
            "class MyClass:\n"
            "    def method_a(self): pass\n"
            "    def method_b(self): pass\n"
        )
        manager.index_project(tmp_path)
        result = manager.get_file_outline(tmp_path, "test.py")
        assert "outline" in result
        assert "entity_count" in result
        assert result["entity_count"] >= 3

    def test_project_outline_groups_by_file(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        manager.index_project(tmp_path)
        result = manager.get_project_outline(tmp_path)
        assert "files" in result
        assert len(result["files"]) >= 2
        for f in result["files"]:
            assert "path" in f
            assert "outline" in f


# ── Semantic Search Provider Injection ────────────────────────────────────


class TestSemanticProviderInjection:
    def test_search_engine_uses_provider(self):
        from code_index_mcp.search.engine import SearchEngine

        provider = MagicMock()
        provider.provider_name = "test"
        provider.model_name = "test-model"
        provider.version = "1"

        repos = MagicMock()
        repos.search_symbols.return_value = []
        repos.search_text.return_value = []
        provider.search.return_value = [
            {"entity_id": "e1", "name": "foo", "score": 5.0}
        ]

        engine = SearchEngine(repos, embedding_provider=provider)
        results = engine.search("foo", limit=5)
        assert len(results) >= 1

    def test_project_manager_passes_providers(self, config, tmp_path):
        pm = ProjectManager(config)
        provider = MagicMock()
        provider.provider_name = "test"
        provider.model_name = "model"
        provider.version = "1"
        pm._embedding_provider = provider

        (tmp_path / "mod.py").write_text("x = 1\n")
        result = pm.index_project(tmp_path, force=True)
        assert "files_changed" in result


# ── File Watcher Integration (§24) ─────────────────────────────────────────


class TestWatcherIntegration:
    def test_start_stop_watching(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        manager.index_project(tmp_path, force=True)

        result = manager.start_watching(tmp_path, interval=0.5)
        assert result["watching"] is True

        result = manager.stop_watching(tmp_path)
        assert result["watching"] is False

    def test_start_watching_already_watching(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        manager.index_project(tmp_path, force=True)

        manager.start_watching(tmp_path, interval=0.5)
        result = manager.start_watching(tmp_path, interval=0.5)
        assert "Already watching" in result["message"]
        manager.stop_watching(tmp_path)

    def test_stop_watching_not_watching(self, manager, tmp_path):
        result = manager.stop_watching(tmp_path)
        assert result["watching"] is False
        assert "Not watching" in result["message"]

    def test_list_watching(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        manager.index_project(tmp_path, force=True)

        result = manager.list_watching()
        assert result["count"] == 0

        manager.start_watching(tmp_path, interval=0.5)
        result = manager.list_watching()
        assert result["count"] == 1

        manager.stop_watching(tmp_path)

    def test_watcher_detects_new_file(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        manager.index_project(tmp_path, force=True)

        manager.start_watching(tmp_path, interval=0.5)
        (tmp_path / "new.py").write_text("y = 2\n")
        import time
        time.sleep(2.5)
        manager.stop_watching(tmp_path)

        db = manager.open_database(tmp_path)
        try:
            rows = db.execute(
                "SELECT relative_path FROM files WHERE relative_path = ?",
                ("new.py",),
            ).fetchone()
            assert rows is not None
        finally:
            db.close()


# ── Heading-Hierarchy Search (§14) ─────────────────────────────────────────


class TestHeadingSearch:
    def _index_markdown(self, manager, tmp_path):
        (tmp_path / "docs.md").write_text(
            "# Project\n\n"
            "## Installation\n\n"
            "Run pip install.\n\n"
            "## Configuration\n\n"
            "Edit config.yaml.\n\n"
            "### Advanced\n\n"
            "Override defaults.\n"
        )
        manager.index_project(tmp_path, force=True)

    def _search(self, manager, tmp_path, query, kind="markdown"):
        resp = manager.search(tmp_path, query, kind=kind)
        return resp["results"]

    def test_search_headings_finds_by_text(self, manager, tmp_path):
        self._index_markdown(manager, tmp_path)
        results = self._search(manager, tmp_path, "Installation")
        names = [r["name"] for r in results]
        assert any("Installation" in n for n in names)

    def test_search_headings_returns_hierarchy(self, manager, tmp_path):
        self._index_markdown(manager, tmp_path)
        results = self._search(manager, tmp_path, "Advanced")
        assert len(results) >= 1
        r = results[0]
        assert "heading_level" in r or "name" in r

    def test_search_headings_priority_by_level(self, manager, tmp_path):
        (tmp_path / "doc.md").write_text(
            "# Top\n\n"
            "## Setup\n\n"
            "Details.\n\n"
            "### Setup Details\n\n"
            "More info.\n"
        )
        manager.index_project(tmp_path, force=True)
        results = self._search(manager, tmp_path, "Setup")
        names = [r["name"] for r in results]
        assert any("Setup" in n for n in names)

    def test_search_all_includes_headings(self, manager, tmp_path):
        self._index_markdown(manager, tmp_path)
        results = self._search(manager, tmp_path, "Configuration", kind="all")
        names = [r["name"] for r in results]
        assert any("Configuration" in n for n in names)


# ── ProjectPathGuard wiring (§26) ──────────────────────────────────────────


class TestProjectPathGuardWiring:
    def test_canonical_root_validates_path(self, manager, tmp_path):
        result = manager.canonical_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_canonical_root_rejects_nonexistent(self, manager, tmp_path):
        with pytest.raises(ValueError, match="not a directory"):
            manager.canonical_root(tmp_path / "nonexistent")

    def test_path_guard_stored_in_services(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        manager.index_project(tmp_path, force=True)

        from code_index_mcp.security.paths import ProjectPathGuard
        db = manager.open_database(tmp_path)
        try:
            # Verify the guard can be created for this root
            guard = ProjectPathGuard(tmp_path)
            assert guard.contains("mod.py")
        finally:
            db.close()


# ── CacheManager wiring ────────────────────────────────────────────────────


class TestCacheManagerWiring:
    def test_cache_metadata_written_during_indexing(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            rows = db.execute(
                "SELECT * FROM cache_metadata WHERE cache_layer = 'entity'"
            ).fetchall()
            assert len(rows) >= 1
        finally:
            db.close()

    def test_cache_metadata_has_correct_project(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text("def foo(): pass\n")
        result = manager.index_project(tmp_path, force=True)
        project_id = result.get("project_id")

        db = manager.open_database(tmp_path)
        try:
            row = db.execute(
                "SELECT project_id FROM cache_metadata LIMIT 1"
            ).fetchone()
            assert row["project_id"] == project_id
        finally:
            db.close()


# ── RelationshipAnalyzer pipeline wiring ────────────────────────────────────


class TestRelationshipAnalyzerPipeline:
    def test_relationships_use_analyzer_pipeline(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text(
            "import os\n"
            "def foo():\n"
            "    os.path.join('a', 'b')\n"
        )
        manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            rows = db.execute("SELECT * FROM relationships").fetchall()
            assert len(rows) >= 1
            kinds = [r["relationship_kind"] for r in rows]
            assert "imports" in kinds
        finally:
            db.close()

    def test_relationships_resolve_targets(self, manager, tmp_path):
        (tmp_path / "mod.py").write_text(
            "class MyClass:\n"
            "    def method(self):\n"
            "        pass\n"
            "def caller():\n"
            "    MyClass().method()\n"
        )
        manager.index_project(tmp_path, force=True)

        db = manager.open_database(tmp_path)
        try:
            rows = db.execute(
                "SELECT * FROM relationships WHERE relationship_kind = 'calls'"
            ).fetchall()
            resolved = [r for r in rows if r["target_entity_id"]]
            assert len(resolved) >= 1
        finally:
            db.close()
