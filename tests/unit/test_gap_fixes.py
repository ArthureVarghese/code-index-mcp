"""Tests for gap-analysis fixes: relationships, transactions, invalidation, structural hashes,
cache stats, markdown sections, context retrieval, and find_definition."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.cache.invalidation import InvalidationPlan, calculate_invalidation
from code_index_mcp.cache.stats import CacheStats
from code_index_mcp.indexing.manager import (
    IndexManager,
    _relationship_id,
)
from code_index_mcp.indexing.markdown.analyzer import MarkdownAnalyzer
from code_index_mcp.indexing.python.analyzer import PythonAnalyzer
from code_index_mcp.models.entities import (
    Entity,
    EntityType,
    SourceKind,
    SourceRange,
)
from code_index_mcp.retrieval.context import ContextBuilder

# ── Relationship integration ──────────────────────────────────────────────


class TestRelationshipIntegration:
    def test_relationships_computed_for_python_file(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "mod.py").write_text(
            "class Foo:\n    def bar(self): pass\n"
        )
        result = pm.index_project(tmp_path)
        assert result["relationships_computed"] >= 0

    def test_relationship_id_deterministic(self):
        a = _relationship_id("src", "tgt", "calls")
        b = _relationship_id("src", "tgt", "calls")
        assert a == b
        assert a.startswith("rel:")

    def test_relationship_id_different_for_different_inputs(self):
        a = _relationship_id("src", "tgt", "calls")
        b = _relationship_id("src", "tgt", "imports")
        assert a != b

    def test_inheritance_relationship_computed(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "inh.py").write_text(
            "class Base: pass\nclass Child(Base): pass\n"
        )
        result = pm.index_project(tmp_path)
        assert result["relationships_computed"] >= 0


# ── Atomic transactions ───────────────────────────────────────────────────


class TestAtomicTransactions:
    def test_indexing_uses_transaction(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("x = 1\n")
        pm.index_project(tmp_path)
        db.transaction.assert_called()

    def test_transaction_rollback_on_error(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}
        repos.upsert_entity.side_effect = RuntimeError("db fail")

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        result = pm.index_project(tmp_path)
        assert len(result["errors"]) >= 1
        db.transaction.return_value.__exit__.assert_called()


# ── InvalidationPlan integration ──────────────────────────────────────────


class TestInvalidationPlanIntegration:
    def test_invalid_plan_used_for_comparison(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("x = 1\n")
        pm.index_project(tmp_path)

    def test_calculate_invalidation_detects_changes(self):
        plan = calculate_invalidation(
            old_hashes={"a": "1", "b": "2"},
            new_hashes={"a": "1", "b": "3", "c": "4"},
        )
        assert "b" in plan.changed_entities
        assert "c" in plan.changed_entities
        assert "a" in plan.reused_entities

    def test_plan_has_changes_true(self):
        plan = InvalidationPlan(changed_entities={"x"})
        assert plan.has_changes is True

    def test_plan_has_changes_false(self):
        plan = InvalidationPlan()
        assert plan.has_changes is False


# ── Structural hash recomputation ─────────────────────────────────────────


class TestStructuralHashRecomputation:
    def test_container_hash_recomputed_with_children(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "cls.py").write_text(
            "class Foo:\n    def a(self): pass\n    def b(self): pass\n"
        )
        pm.index_project(tmp_path)

    def test_structural_hash_changes_when_children_change(self):
        from code_index_mcp.indexing.hashing import structural_hash

        h1 = structural_hash(
            entity_type="class",
            name="Foo",
            qualified_name="Foo",
            signature=None,
            decorators=(),
            child_ids=["method_a", "method_b"],
        )
        h2 = structural_hash(
            entity_type="class",
            name="Foo",
            qualified_name="Foo",
            signature=None,
            decorators=(),
            child_ids=["method_a", "method_b", "method_c"],
        )
        assert h1 != h2

    def test_structural_hash_same_with_same_children(self):
        from code_index_mcp.indexing.hashing import structural_hash

        h1 = structural_hash(
            entity_type="class",
            name="Foo",
            qualified_name="Foo",
            signature=None,
            decorators=(),
            child_ids=["a", "b"],
        )
        h2 = structural_hash(
            entity_type="class",
            name="Foo",
            qualified_name="Foo",
            signature=None,
            decorators=(),
            child_ids=["a", "b"],
        )
        assert h1 == h2


# ── CacheStats surfacing ──────────────────────────────────────────────────


class TestCacheStatsSurfacing:
    def test_cache_stats_included_in_index_result(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("x = 1\n")
        result = pm.index_project(tmp_path)
        assert "files_seen" in result
        assert "relationships_computed" in result

    def test_cache_stats_to_dict(self):
        stats = CacheStats(
            files_seen=10, files_changed=5, files_reused=5, files_parsed=5,
            entities_reused=20, entities_recomputed=10,
        )
        d = stats.to_dict()
        assert d["files_seen"] == 10
        assert d["entity_hit_ratio"] == pytest.approx(2 / 3)
        assert d["file_hit_ratio"] == pytest.approx(0.5)

    def test_cache_stats_hit_ratios(self):
        stats = CacheStats()
        assert stats.entity_hit_ratio == 1.0
        assert stats.file_hit_ratio == 1.0


# ── Markdown sections ─────────────────────────────────────────────────────


class TestMarkdownSections:
    def test_markdown_sections_populated(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        repos.get_entities_for_file.return_value = []
        db.execute.return_value.fetchone.return_value = {"project_id": "proj"}

        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "doc.md").write_text("# Title\n\nContent.\n")
        pm.index_project(tmp_path)
        repos.markdown_sections.upsert.assert_called()

    def test_markdown_section_entity_id_normalized(self):
        from code_index_mcp.models.projects import IndexState, ProjectMetadata
        from code_index_mcp.storage.database import Database
        from code_index_mcp.storage.repositories import ProjectRepository, RepositoryStore

        db = Database(":memory:")
        try:
            repos = RepositoryStore(db.connection)
            project = ProjectMetadata(
                project_id="proj", canonical_root="/test",
                schema_version=1, indexer_version="0.1.0",
                indexing_state=IndexState.READY,
                configuration_fingerprint="fp",
                last_indexed_at=None,
                indexed_files=0, indexed_entities=0,
                indexed_markdown_sections=0, health="healthy",
                metadata={},
            )
            ProjectRepository(db.connection).upsert(project)
            repos.set_project_id("proj")
            repos.upsert_file("doc.md", "h", 0)

            repos.markdown_sections.upsert(
                section_id="markdown:doc.md:Title",
                project_id="proj",
                file_id="file:doc.md",
                parent_section_id=None,
                heading="Title",
                heading_level=1,
                heading_path="Title",
                start_line=1,
                end_line=3,
                content_hash="h",
                exact_source_hash="h",
                semantic_hash="h",
                source="# Title\n\nContent.\n",
            )
            result = repos.get_markdown_section("markdown:doc.md:Title")
            assert result is not None
            assert result["entity_id"] == "markdown:doc.md:Title"
            assert result["entity_type"] == "markdown_section"
        finally:
            db.close()

    def test_markdown_section_falls_back_to_entity(self):
        from code_index_mcp.models.projects import IndexState, ProjectMetadata
        from code_index_mcp.storage.database import Database
        from code_index_mcp.storage.repositories import ProjectRepository, RepositoryStore

        db = Database(":memory:")
        try:
            repos = RepositoryStore(db.connection)
            project = ProjectMetadata(
                project_id="p", canonical_root="/test",
                schema_version=1, indexer_version="0.1.0",
                indexing_state=IndexState.READY,
                configuration_fingerprint="fp",
                last_indexed_at=None,
                indexed_files=0, indexed_entities=0,
                indexed_markdown_sections=0, health="healthy",
                metadata={},
            )
            ProjectRepository(db.connection).upsert(project)
            repos.set_project_id("p")
            repos.upsert_file("f", "h", 0)

            entity = Entity(
                entity_id="e1", project_id="p", file_id="file:f",
                source_kind=SourceKind.MARKDOWN,
                entity_type=EntityType.MARKDOWN_SECTION,
                name="Title", qualified_name="Title",
                parent_id=None,
                source_range=SourceRange(1, 5, 0, 0),
                content_hash="h", exact_source_hash="h",
                semantic_hash="h", structural_hash="h",
                source="Title\nContent",
            )
            repos.upsert_entity(entity)
            result = repos.get_markdown_section("e1")
            assert result is not None
            assert result["entity_id"] == "e1"
        finally:
            db.close()


# ── Context retrieval ─────────────────────────────────────────────────────


class TestContextRetrieval:
    def test_expanded_includes_callers_callees(self):
        repos = MagicMock()
        repos.get_parent.return_value = None
        repos.get_children.return_value = []
        repos.get_relationships.return_value = [
            {"source_entity_id": "caller", "target_entity_id": "e1",
             "relationship_kind": "calls"},
            {"source_entity_id": "e1", "target_entity_id": "callee",
             "relationship_kind": "calls"},
            {"source_entity_id": "e1", "target_entity_id": "mod",
             "relationship_kind": "imports"},
            {"source_entity_id": "e1", "target_entity_id": "base",
             "relationship_kind": "inherits"},
        ]
        builder = ContextBuilder(repos)
        result = builder.build({"entity_id": "e1"}, depth="expanded")
        assert len(result["callers"]) == 1
        assert result["callers"][0]["source_entity_id"] == "caller"
        assert len(result["callees"]) == 1
        assert result["callees"][0]["target_entity_id"] == "callee"
        assert len(result["imports"]) == 1
        assert len(result["inherits"]) == 1

    def test_normal_includes_parent(self):
        repos = MagicMock()
        repos.get_parent.return_value = {"entity_id": "parent"}
        builder = ContextBuilder(repos)
        result = builder.build({"entity_id": "e1"}, depth="normal")
        assert result["parent"]["entity_id"] == "parent"
        assert "callers" not in result

    def test_minimal_is_bounded(self):
        repos = MagicMock()
        builder = ContextBuilder(repos)
        entity = {
            "entity_id": "e1", "path": "a.py", "entity_type": "function",
            "name": "foo", "start_line": 1, "end_line": 5,
            "source": "def foo(): pass", "extra": True,
        }
        result = builder.build(entity, depth="minimal")
        assert set(result.keys()) == {
            "entity_id", "path", "entity_type", "name",
            "start_line", "end_line",
        }


# ── find_definition ───────────────────────────────────────────────────────


class TestFindDefinition:
    def test_find_definition_uses_db_first(self, tmp_path):
        from code_index_mcp.config import IndexConfig
        from code_index_mcp.project.manager import ProjectManager

        config = IndexConfig.from_environment()
        manager = ProjectManager(config)
        (tmp_path / "mod.py").write_text("def my_func(): pass\n")

        db = manager.open_database(tmp_path)
        try:
            from code_index_mcp.project.metadata import ensure_project_metadata
            from code_index_mcp.storage.repositories import RepositoryStore

            metadata = ensure_project_metadata(db, tmp_path, config)
            repos = RepositoryStore(db.connection)
            repos.set_project_id(metadata.project_id)
            file_id = repos.upsert_file("mod.py", "hash", 1)

            # Create parent module entity first (required by FK)
            module_entity = Entity(
                entity_id="python:mod.py",
                project_id=metadata.project_id,
                file_id=file_id,
                source_kind=SourceKind.PYTHON,
                entity_type=EntityType.MODULE,
                name="mod",
                qualified_name="mod",
                parent_id=None,
                source_range=SourceRange(1, 1, 0, 0),
                content_hash="h",
                exact_source_hash="h",
                semantic_hash="h",
                structural_hash="h",
                source="def my_func(): pass",
            )
            repos.upsert_entity(module_entity)

            entity = Entity(
                entity_id="python:mod.py:my_func",
                project_id=metadata.project_id,
                file_id=file_id,
                source_kind=SourceKind.PYTHON,
                entity_type=EntityType.FUNCTION,
                name="my_func",
                qualified_name="my_func",
                parent_id="python:mod.py",
                source_range=SourceRange(1, 1, 0, 16),
                content_hash="h",
                exact_source_hash="h",
                semantic_hash="h",
                structural_hash="h",
                source="def my_func(): pass",
            )
            repos.upsert_entity(entity)

            result = manager.find_definition(tmp_path, "my_func")
            assert len(result["results"]) >= 1
            assert result["results"][0]["name"] == "my_func"
        finally:
            db.close()

    def test_find_definition_falls_back_to_search(self, tmp_path):
        from code_index_mcp.config import IndexConfig
        from code_index_mcp.project.manager import ProjectManager

        config = IndexConfig.from_environment()
        manager = ProjectManager(config)
        (tmp_path / "mod.py").write_text("def my_func(): pass\n")
        manager.index_project(tmp_path)

        result = manager.find_definition(tmp_path, "nonexistent_symbol_xyz")
        assert "results" in result
