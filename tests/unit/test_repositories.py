from __future__ import annotations

from dataclasses import replace

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

    def _ensure_doc(self, db, document_id="doc1"):
        db.connection.execute(
            """INSERT INTO search_documents
                (document_id, project_id, entity_id, section_id, source_kind,
                 title, path, content, keywords, metadata_json)
               VALUES (?, 'proj1', NULL, NULL, 'python', 't', 'p', '', '', '{}')""",
            (document_id,),
        )

    def test_batch_embedding_lookup(self, database):
        self._ensure_doc(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.store_embedding("h1", "p", "m", "1", [1.0], document_id="doc1")

        key = "emb:h1:p:m:1"
        assert store.get_embeddings_by_cache_keys([key, "emb:missing:p:m:1"]) == {
            key: [1.0]
        }

    def test_batch_summary_lookup_and_version_scope(self, database):
        self._ensure_doc(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.store_summary(
            "sh", "mh", "p", "m", "1", "prompt", "summary", document_id="doc1"
        )

        key = "sum:sh:p:m:1:prompt"
        assert store.get_summaries_by_cache_keys([key]) == {key: "summary"}
        assert (
            store.get_summary("sh", "mh", "p", "m", "2", "prompt") is None
        )

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

    def test_search_text_uses_one_select_for_twenty_results(self, database):
        self._ensure_file(database)
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        for index in range(20):
            store.upsert_entity(_make_entity(f"e{index}"))
        store._project_id()

        traced: list[str] = []
        database.connection.set_trace_callback(traced.append)
        try:
            results = store.search_text("foo", limit=20)
        finally:
            database.connection.set_trace_callback(None)

        selects = [sql for sql in traced if sql.lstrip().upper().startswith("SELECT")]
        assert len(results) == 20
        assert len(selects) == 1

    def test_search_symbols_preserves_paths_starting_with_prefix_characters(self, database):
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:error.py", "proj1", "error.py", "error.py", "python", "h", "h"),
        )
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity("py:foo", file_id="file:error.py"))

        assert [r["path"] for r in store.search_symbols("foo")] == ["error.py"]

    def test_search_symbols_path_filter(self, database):
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:a.py", "proj1", "a.py", "a.py", "python", "h", "h"),
        )
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:b.py", "proj1", "b.py", "b.py", "python", "h", "h"),
        )
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity("py:foo", file_id="file:a.py"))
        store.upsert_entity(_make_entity("py:bar", file_id="file:b.py"))
        assert len(store.search_symbols("foo", path="b.py")) == 0
        assert len(store.search_symbols("foo", path="a.py")) == 1
        assert len(store.search_symbols("foo")) == 1

    def test_search_text_path_filter(self, database):
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:a.py", "proj1", "a.py", "a.py", "python", "h", "h"),
        )
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:b.py", "proj1", "b.py", "b.py", "python", "h", "h"),
        )
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store.upsert_entity(_make_entity("py:foo", file_id="file:a.py"))
        store.upsert_entity(_make_entity("py:bar", file_id="file:b.py"))
        only_a = store.search_text("foo", path="a.py")
        assert only_a, "expected at least one FTS hit inside a.py"
        for r in only_a:
            assert r["path"] == "a.py"

    def test_search_headings_path_filter(self, database):
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:doc.md", "proj1", "doc.md", "doc.md", "markdown", "h", "h"),
        )
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:other.md", "proj1", "other.md", "other.md", "markdown", "h", "h"),
        )
        for fpath in ("doc.md", "other.md"):
            database.connection.execute(
                "INSERT INTO markdown_sections"
                " (section_id, project_id, file_id, heading, heading_level,"
                " heading_path, start_line, end_line, content_hash,"
                " exact_source_hash, semantic_hash, source)"
                " VALUES (?, ?, ?, ?, 1, ?, 1, 3, 'ch', 'eh', 'sh', 'Install')",
                (f"md:sec:{fpath}", "proj1", f"file:{fpath}", "Install", "Install"),
            )
        database.connection.commit()
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        doc_only = store.search_headings("Install", path="doc.md")
        assert len(doc_only) == 1
        assert doc_only[0]["entity_id"] == "md:sec:doc.md"

    def test_search_headings_uses_one_select_for_twenty_results(self, database):
        database.connection.execute(
            _INSERT_FILES_SQL,
            ("file:doc.md", "proj1", "doc.md", "doc.md", "markdown", "h", "h"),
        )
        for index in range(20):
            database.connection.execute(
                "INSERT INTO markdown_sections"
                " (section_id, project_id, file_id, heading, heading_level,"
                " heading_path, start_line, end_line, content_hash,"
                " exact_source_hash, semantic_hash, source)"
                " VALUES (?, ?, ?, ?, 1, ?, 1, 3, 'ch', 'eh', 'sh', 'Install')",
                (f"md:sec:{index}", "proj1", "file:doc.md", "Install", "Install"),
            )
        store = RepositoryStore(database.connection)
        store.set_project_id("proj1")
        store._project_id()

        traced: list[str] = []
        database.connection.set_trace_callback(traced.append)
        try:
            results = store.search_headings("Install", limit=20)
        finally:
            database.connection.set_trace_callback(None)

        selects = [sql for sql in traced if sql.lstrip().upper().startswith("SELECT")]
        assert len(results) == 20
        assert len(selects) == 1

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


def _select_count(connection, operation):
    count = 0

    def trace(sql: str) -> None:
        nonlocal count
        if sql.strip().upper().startswith("SELECT"):
            count += 1

    connection.set_trace_callback(trace)
    try:
        result = operation()
    finally:
        connection.set_trace_callback(None)
    return result, count


def _seed_entities(database, count: int) -> None:
    database.connection.execute(
        _INSERT_FILES_SQL,
        ("file:f1.py", "proj1", "f1.py", "f1.py", "python", "h", "h"),
    )
    repo = EntityRepository(database.connection)
    for index in range(count):
        entity = _make_entity(f"e{index}")
        repo.upsert(
            replace(
                entity,
                source_range=replace(
                    entity.source_range,
                    start_line=index + 1,
                    end_line=index + 1,
                ),
            )
        )


def _query_plan(connection, sql: str, params=()) -> str:
    rows = connection.execute(
        f"EXPLAIN QUERY PLAN {sql}",
        params,
    ).fetchall()
    return " | ".join(row["detail"] for row in rows)


def test_list_all_uses_one_select(database):
    _seed_entities(database, 200)

    entities, selects = _select_count(database.connection, EntityRepository(
        database.connection
    ).list_all)

    assert len(entities) == 200
    assert selects == 1
    assert [e.name for e in entities[:3]] == ["e0", "e1", "e2"]


def test_repository_store_list_helpers_use_one_select(database):
    _seed_entities(database, 200)
    store = RepositoryStore(database.connection)
    store.set_project_id("proj1")
    parent = _make_entity("parent")
    store.entities.upsert(replace(parent, parent_id=None))
    store.entities.upsert(replace(_make_entity("child"), parent_id="parent"))

    entities, selects = _select_count(database.connection, store.list_entities)
    children, child_selects = _select_count(
        database.connection, lambda: store.get_children("parent")
    )
    file_entities, file_selects = _select_count(
        database.connection, lambda: store.get_entities_for_file("f1.py")
    )

    assert len(entities) >= 200
    assert selects == 1
    assert [c["entity_id"] for c in children] == ["child"]
    assert child_selects == 1
    assert len(file_entities) >= 200
    assert file_selects == 1


def test_hot_lookups_use_indexes(database):
    plans = {
        "files": _query_plan(
            database.connection,
            "SELECT file_id FROM files WHERE relative_path = ? AND project_id = ?",
            ("f1.py", "proj1"),
        ),
        "embeddings": _query_plan(
            database.connection,
            "SELECT vector_json FROM embeddings"
            " WHERE semantic_hash=? AND provider=?"
            " AND model=? AND representation_version=?",
            ("s", "p", "m", "v"),
        ),
        "summaries": _query_plan(
            database.connection,
            "SELECT summary FROM summaries"
            " WHERE semantic_hash=? AND metadata_hash=?"
            " AND provider=? AND model=? AND prompt_version=?",
            ("s", "m", "p", "model", "prompt"),
        ),
        "search_documents": _query_plan(
            database.connection,
            "SELECT entity_id FROM search_documents WHERE entity_id = ?",
            ("e1",),
        ),
        "markdown_sections": _query_plan(
            database.connection,
            "SELECT * FROM markdown_sections WHERE project_id = ? AND heading_path = ?",
            ("proj1", "Guide/Install"),
        ),
        "entities_for_file": _query_plan(
            database.connection,
            "SELECT * FROM entities WHERE file_id = ?"
            " ORDER BY start_line, start_column, end_line",
            ("file:f1.py",),
        ),
    }

    for name, plan in plans.items():
        assert "USING INDEX" in plan or "SEARCH" in plan, f"{name}: {plan}"
