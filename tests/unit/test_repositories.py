from __future__ import annotations

import pytest

from code_index_mcp.models.entities import (
    Entity,
    EntityType,
    Relationship,
    RelationshipConfidence,
    RelationshipKind,
    SourceKind,
    SourceRange,
)
from code_index_mcp.storage.database import Database
from code_index_mcp.storage.repositories import (
    EntityRepository,
    ProjectRepository,
    RelationshipRepository,
    RepositoryStore,
    utc_now,
)

_INSERT_FILES_SQL = (
    "INSERT INTO files"
    " (file_id, project_id, relative_path, canonical_path,"
    " source_kind, exact_hash, semantic_hash,"
    " size_bytes, mtime_ns, encoding, parser_version)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'utf-8', 'test')"
)

_INSERT_PROJ_SQL = (
    "INSERT INTO projects"
    " (project_id, canonical_root, schema_version,"
    " indexer_version, indexing_state,"
    " configuration_fingerprint)"
    " VALUES (?, ?, 1, 'test', 'ready', '')"
)


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "test.db")
    db.connection.execute(
        _INSERT_PROJ_SQL,
        ("proj1", str(tmp_path)),
    )
    yield db
    db.close()


def _make_entity(entity_id="e1", project_id="proj1", file_id="file:f1.py"):
    return Entity(
        entity_id=entity_id,
        project_id=project_id,
        file_id=file_id,
        source_kind=SourceKind.PYTHON,
        entity_type=EntityType.FUNCTION,
        name=entity_id.split(":")[-1],
        qualified_name=entity_id.split(":")[-1],
        parent_id=None,
        source_range=SourceRange(1, 5, 0, 10),
        content_hash="hash1",
        exact_source_hash="exact1",
        semantic_hash="sem1",
        structural_hash="struct1",
        source="def foo(): pass",
    )


class TestUtcNow:
    def test_returns_iso_string(self):
        result = utc_now()
        assert "T" in result


class TestProjectRepository:
    def test_upsert_and_get(self, database):
        from code_index_mcp.models.projects import IndexState, ProjectMetadata

        repo = ProjectRepository(database.connection)
        meta = ProjectMetadata(
            project_id="test_proj",
            canonical_root="/tmp",
            schema_version=1,
            indexer_version="0.1.0",
            indexing_state=IndexState.NEW,
            configuration_fingerprint="fp",
            last_indexed_at=None,
            indexed_files=0,
            indexed_entities=0,
            indexed_markdown_sections=0,
            health="new",
            metadata={},
        )
        repo.upsert(meta)
        result = repo.get("test_proj")
        assert result is not None
        assert result.project_id == "test_proj"

    def test_get_nonexistent(self, database):
        repo = ProjectRepository(database.connection)
        assert repo.get("nonexistent") is None


class TestEntityRepository:
    def test_upsert_and_get(self, database):
        repo = EntityRepository(database.connection)
        # Need a file entry first
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )
        entity = _make_entity()
        repo.upsert(entity)
        result = repo.get("e1")
        assert result is not None
        assert result.entity_id == "e1"

    def test_list_for_file(self, database):
        repo = EntityRepository(database.connection)
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )
        repo.upsert(_make_entity("e1", file_id="file:f1.py"))
        repo.upsert(_make_entity("e2", file_id="file:f1.py"))
        entities = repo.list_for_file("file:f1.py")
        assert len(entities) == 2

    def test_delete(self, database):
        repo = EntityRepository(database.connection)
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )
        repo.upsert(_make_entity())
        repo.delete("e1")
        assert repo.get("e1") is None


class TestRelationshipRepository:
    def test_upsert_and_find(self, database):
        repo = RelationshipRepository(database.connection)
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )
        e_repo = EntityRepository(database.connection)
        e_repo.upsert(_make_entity("e1"))
        e_repo.upsert(_make_entity("e2"))

        rel = Relationship(
            relationship_id="r1",
            project_id="proj1",
            source_entity_id="e1",
            target_entity_id="e2",
            kind=RelationshipKind.CALLS,
            confidence=RelationshipConfidence.EXACT,
        )
        repo.upsert(rel)
        results = repo.find_for_entity("e1")
        assert len(results) == 1

    def test_delete_for_entity(self, database):
        repo = RelationshipRepository(database.connection)
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )
        e_repo = EntityRepository(database.connection)
        e_repo.upsert(_make_entity("e1"))
        e_repo.upsert(_make_entity("e2"))
        rel = Relationship(
            relationship_id="r1",
            project_id="proj1",
            source_entity_id="e1",
            target_entity_id="e2",
            kind=RelationshipKind.CALLS,
            confidence=RelationshipConfidence.EXACT,
        )
        repo.upsert(rel)
        repo.delete_for_entity("e1")
        assert len(repo.find_for_entity("e1")) == 0


class TestRepositoryStore:
    def _ensure_file(self, db, file_id="file:f1.py"):
        db.connection.execute(
            _INSERT_FILES_SQL,
            (file_id, "proj1", "f1.py", "f1.py", "python", "h", "h"),
        )

    def test_get_file(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        result = store.get_file("f1.py")
        assert result is not None

    def test_get_file_missing(self, database):
        store = RepositoryStore(database.connection)
        assert store.get_file("missing.py") is None

    def test_upsert_entity(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        entity = _make_entity()
        store.upsert_entity(entity)
        result = store.get_entity("e1")
        assert result is not None

    def test_get_entities_for_file(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity("e1", file_id="file:f1.py"))
        entities = store.get_entities_for_file("f1.py")
        assert len(entities) == 1

    def test_delete_entity(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity())
        store.delete_entity("e1")
        assert store.get_entity("e1") is None

    def test_search_symbols(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity())
        results = store.search_symbols("e1")
        assert len(results) == 1

    def test_search_symbols_kind_filters_source(self, database):
        self._ensure_file(database, file_id="file:f1.py")
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:d.md", "proj1", "docs/d.md", "docs/d.md", "markdown", "h", "h"),
        )
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        py_entity = _make_entity("py:foo")
        md_entity = _make_entity("md:bar", file_id="file:d.md")
        store.upsert_entity(py_entity)
        store.upsert_entity(md_entity)
        assert len(store.search_symbols("foo", kind="python")) == 1
        assert store.search_symbols("bar", kind="python") == []
        assert len(store.search_symbols("bar", kind="markdown")) == 1
        assert store.search_symbols("foo", kind="markdown") == []
        assert len(store.search_symbols("foo")) == 1

    def test_search_text(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity())
        results = store.search_text("foo")
        assert len(results) >= 1
        for r in results:
            assert not r["path"].startswith("file:")

    def test_search_text_path_consistent_with_symbols(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity())
        text = store.search_text("e1")
        symbols = store.search_symbols("e1")
        assert text, "expected FTS text result"
        assert symbols, "expected symbol result"
        for r in text + symbols:
            assert not r["path"].startswith("file:")

    def test_list_entities(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity("e1"))
        store.upsert_entity(_make_entity("e2"))
        entities = store.list_entities()
        assert len(entities) == 2

    def test_get_children(self, database):
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        children = store.get_children("nonexistent")
        assert children == []

    def test_get_parent(self, database):
        store = RepositoryStore(database.connection)
        result = store.get_parent("nonexistent")
        assert result is None

    def test_get_relationships(self, database):
        store = RepositoryStore(database.connection)
        result = store.get_relationships("nonexistent")
        assert result == []

    def test_get_markdown_section(self, database):
        store = RepositoryStore(database.connection)
        result = store.get_markdown_section("nonexistent")
        assert result is None

    def test_clear(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity())
        store.clear()
        assert store.list_entities() == []

    def test_upsert_file(self, database):
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        file_id = store.upsert_file("test.py", "hash1", 3)
        assert file_id

    def test_get_entities_for_file_missing(self, database):
        store = RepositoryStore(database.connection)
        assert store.get_entities_for_file("missing.py") == []

    def test_get_file_region(self, database, tmp_path):
        db = Database(tmp_path / "region.db")
        try:
            db.connection.execute(
                _INSERT_PROJ_SQL,
                ("proj1", str(tmp_path)),
            )
            (tmp_path / "code.py").write_text("line1\nline2\nline3\n")
            store = RepositoryStore(db.connection)
            result = store.get_file_region("code.py", 1, 2)
            assert "line1" in result["source"]
        finally:
            db.close()

    def test_get_file_region_no_project(self, database):
        # Use a fresh database with no projects table data
        store = RepositoryStore(database.connection)
        with pytest.raises((KeyError, FileNotFoundError)):
            store.get_file_region("code.py", 1, 5)
