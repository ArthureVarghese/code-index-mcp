from __future__ import annotations

import json

import pytest

from code_index_mcp.indexing.manager import IndexManager
from code_index_mcp.indexing.markdown.analyzer import MarkdownAnalyzer
from code_index_mcp.indexing.python.analyzer import PythonAnalyzer
from code_index_mcp.storage.database import Database
from code_index_mcp.storage.repositories import (
    EntityRepository,
    MarkdownSectionRepository,
    RelationshipRepository,
)


class RepositoryAdapter:
    def __init__(self, database: Database, project_root):
        self.database = database
        self.project_root = project_root
        self.entities = EntityRepository(database.connection)
        self.relationships = RelationshipRepository(database.connection)
        self.markdown_sections = MarkdownSectionRepository(database.connection)

    def get_file(self, relative_path: str):
        row = self.database.connection.execute(
            """
            SELECT *
            FROM files
            WHERE relative_path = ?
            LIMIT 1
            """,
            (relative_path,),
        ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result.setdefault("content_hash", result.get("exact_hash"))
        return result

    def get_entities_for_file(self, relative_path: str):
        return self.entities.list_for_file(f"file:{relative_path}")

    def upsert_entity(self, entity):
        # The analyzers currently default project_id to "".
        # Keep the DB project/file rows consistent with that.
        self.entities.upsert(entity)

    def upsert_entities(self, entities):
        self.entities.upsert_many(entities)

    def update_structural_hash(self, entity_id: str, structural_hash: str):
        self.entities.update_structural_hash(entity_id, structural_hash)

    def delete_entity(self, entity_id: str):
        self.entities.delete(entity_id)

    def list_entities(self):
        return [
            {
                "entity_id": e.entity_id,
                "qualified_name": e.qualified_name,
                "name": e.name,
            }
            for e in self.entities.list_all()
        ]

    def upsert_file(
        self,
        relative_path: str,
        content_hash: str,
        entity_count: int,
    ):
        from code_index_mcp.indexing.hashing import (
            exact_source_hash,
            semantic_hash_python,
        )

        path = self.project_root / relative_path
        stat = path.stat()

        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if path.suffix.lower() in {".py", ".pyi"}:
            source_kind = "python"
            semantic = semantic_hash_python(source)
        else:
            source_kind = "markdown"
            semantic = exact_source_hash(source)

        # The current IndexManager/analyzers use the default project_id="".
        project_id = ""

        self.database.connection.execute(
            """
            INSERT INTO projects (
                project_id,
                canonical_root,
                schema_version,
                indexer_version,
                indexing_state,
                configuration_fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                canonical_root = excluded.canonical_root
            """,
            (
                project_id,
                str(self.project_root.resolve()),
                1,
                "test",
                "ready",
                "",
            ),
        )

        file_id = f"file:{relative_path}"

        self.database.connection.execute(
            """
            INSERT INTO files (
                file_id,
                project_id,
                relative_path,
                canonical_path,
                source_kind,
                exact_hash,
                semantic_hash,
                size_bytes,
                mtime_ns,
                encoding,
                parser_version,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                project_id = excluded.project_id,
                canonical_path = excluded.canonical_path,
                source_kind = excluded.source_kind,
                exact_hash = excluded.exact_hash,
                semantic_hash = excluded.semantic_hash,
                size_bytes = excluded.size_bytes,
                mtime_ns = excluded.mtime_ns,
                parser_version = excluded.parser_version,
                metadata_json = excluded.metadata_json
            """,
            (
                file_id,
                project_id,
                relative_path,
                str(path.resolve()),
                source_kind,
                content_hash,
                semantic,
                stat.st_size,
                stat.st_mtime_ns,
                "utf-8",
                "test",
                json.dumps({"entity_count": entity_count}),
            ),
        )

    def delete_file(self, relative_path: str):
        self.database.connection.execute(
            """
            DELETE FROM files
            WHERE relative_path = ?
            """,
            (relative_path,),
        )


@pytest.fixture
def index_manager(tmp_path):
    database = Database(tmp_path / "index.db")

    repositories = RepositoryAdapter(
        database,
        tmp_path,
    )

    manager = IndexManager(
        database=database,
        python_analyzer=PythonAnalyzer(),
        markdown_analyzer=MarkdownAnalyzer(),
        repositories=repositories,
    )

    try:
        yield manager
    finally:
        database.close()
