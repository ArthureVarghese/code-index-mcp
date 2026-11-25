from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from ..models.entities import (
    Entity,
    EntityType,
    Relationship,
    RelationshipConfidence,
    RelationshipKind,
    SourceKind,
    SourceRange,
)
from ..models.projects import IndexState, ProjectMetadata

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _file_id(relative_path: str) -> str:
    return f"file:{relative_path}"


def _row_to_entity(row: Any) -> Entity:
    return Entity(
        entity_id=row["entity_id"],
        project_id=row["project_id"],
        file_id=row["file_id"],
        source_kind=SourceKind(row["source_kind"]),
        entity_type=EntityType(row["entity_type"]),
        name=row["name"],
        qualified_name=row["qualified_name"],
        parent_id=row["parent_id"],
        source_range=SourceRange(
            start_line=row["start_line"],
            end_line=row["end_line"],
            start_column=row["start_column"],
            end_column=row["end_column"],
        ),
        content_hash=row["content_hash"],
        exact_source_hash=row["exact_source_hash"],
        semantic_hash=row["semantic_hash"],
        structural_hash=row["structural_hash"],
        source=row["source"],
        docstring=row["docstring"],
        signature=row["signature"],
        decorators=tuple(json.loads(row["decorators_json"])),
        metadata=json.loads(row["metadata_json"]),
    )


def _entity_result(entity: Entity) -> dict:
    return {
        **entity.to_dict(),
        "path": entity.file_id,
        "entity_type": entity.entity_type.value,
        "start_line": entity.source_range.start_line,
        "end_line": entity.source_range.end_line,
    }


class ProjectRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert(self, project: ProjectMetadata) -> None:
        logger.debug("ProjectRepository :: upsert :: project_id=%s", project.project_id)
        self.connection.execute(
            """
            INSERT INTO projects (
                project_id,
                canonical_root,
                schema_version,
                indexer_version,
                indexing_state,
                configuration_fingerprint,
                last_indexed_at,
                indexed_files,
                indexed_entities,
                indexed_markdown_sections,
                health,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                canonical_root = excluded.canonical_root,
                schema_version = excluded.schema_version,
                indexer_version = excluded.indexer_version,
                indexing_state = excluded.indexing_state,
                configuration_fingerprint = excluded.configuration_fingerprint,
                last_indexed_at = excluded.last_indexed_at,
                indexed_files = excluded.indexed_files,
                indexed_entities = excluded.indexed_entities,
                indexed_markdown_sections = excluded.indexed_markdown_sections,
                health = excluded.health,
                metadata_json = excluded.metadata_json
            """,
            (
                project.project_id,
                project.canonical_root,
                project.schema_version,
                project.indexer_version,
                project.indexing_state.value,
                project.configuration_fingerprint,
                project.last_indexed_at,
                project.indexed_files,
                project.indexed_entities,
                project.indexed_markdown_sections,
                project.health,
                json.dumps(project.metadata, sort_keys=True),
            ),
        )

    def get(self, project_id: str) -> ProjectMetadata | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

        if row is None:
            return None

        return ProjectMetadata(
            project_id=row["project_id"],
            canonical_root=row["canonical_root"],
            schema_version=row["schema_version"],
            indexer_version=row["indexer_version"],
            indexing_state=IndexState(row["indexing_state"]),
            configuration_fingerprint=row["configuration_fingerprint"],
            last_indexed_at=row["last_indexed_at"],
            indexed_files=row["indexed_files"],
            indexed_entities=row["indexed_entities"],
            indexed_markdown_sections=row["indexed_markdown_sections"],
            health=row["health"],
            metadata=json.loads(row["metadata_json"]),
        )

    def list_all(self) -> list[ProjectMetadata]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM projects
            """
        ).fetchall()

        result = []
        for row in rows:
            result.append(
                ProjectMetadata(
                    project_id=row["project_id"],
                    canonical_root=row["canonical_root"],
                    schema_version=row["schema_version"],
                    indexer_version=row["indexer_version"],
                    indexing_state=IndexState(row["indexing_state"]),
                    configuration_fingerprint=row["configuration_fingerprint"],
                    last_indexed_at=row["last_indexed_at"],
                    indexed_files=row["indexed_files"],
                    indexed_entities=row["indexed_entities"],
                    indexed_markdown_sections=row["indexed_markdown_sections"],
                    health=row["health"],
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return result

    def get_metadata_json(self, project_id: str) -> dict | None:
        """Get just the metadata_json for a project (lightweight)."""
        row = self.connection.execute(
            "SELECT metadata_json FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["metadata_json"])


class EntityRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert(self, entity: Entity) -> None:
        logger.debug("EntityRepository :: upsert :: entity_id=%s", entity.entity_id)
        self.connection.execute(
            """
            INSERT INTO entities (
                entity_id,
                project_id,
                file_id,
                source_kind,
                entity_type,
                name,
                qualified_name,
                parent_id,
                start_line,
                end_line,
                start_column,
                end_column,
                content_hash,
                exact_source_hash,
                semantic_hash,
                structural_hash,
                source,
                docstring,
                signature,
                decorators_json,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                file_id = excluded.file_id,
                source_kind = excluded.source_kind,
                entity_type = excluded.entity_type,
                name = excluded.name,
                qualified_name = excluded.qualified_name,
                parent_id = excluded.parent_id,
                start_line = excluded.start_line,
                end_line = excluded.end_line,
                start_column = excluded.start_column,
                end_column = excluded.end_column,
                content_hash = excluded.content_hash,
                exact_source_hash = excluded.exact_source_hash,
                semantic_hash = excluded.semantic_hash,
                structural_hash = excluded.structural_hash,
                source = excluded.source,
                docstring = excluded.docstring,
                signature = excluded.signature,
                decorators_json = excluded.decorators_json,
                metadata_json = excluded.metadata_json
            """,
            (
                entity.entity_id,
                entity.project_id,
                entity.file_id,
                entity.source_kind.value,
                entity.entity_type.value,
                entity.name,
                entity.qualified_name,
                entity.parent_id,
                entity.source_range.start_line,
                entity.source_range.end_line,
                entity.source_range.start_column,
                entity.source_range.end_column,
                entity.content_hash,
                entity.exact_source_hash,
                entity.semantic_hash,
                entity.structural_hash,
                entity.source,
                entity.docstring,
                entity.signature,
                json.dumps(entity.decorators),
                json.dumps(entity.metadata, sort_keys=True),
            ),
        )

    def upsert_many(self, entities: list[Entity]) -> None:
        if not entities:
            return

        self.connection.executemany(
            """
            INSERT INTO entities (
                entity_id,
                project_id,
                file_id,
                source_kind,
                entity_type,
                name,
                qualified_name,
                parent_id,
                start_line,
                end_line,
                start_column,
                end_column,
                content_hash,
                exact_source_hash,
                semantic_hash,
                structural_hash,
                source,
                docstring,
                signature,
                decorators_json,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                file_id = excluded.file_id,
                source_kind = excluded.source_kind,
                entity_type = excluded.entity_type,
                name = excluded.name,
                qualified_name = excluded.qualified_name,
                parent_id = excluded.parent_id,
                start_line = excluded.start_line,
                end_line = excluded.end_line,
                start_column = excluded.start_column,
                end_column = excluded.end_column,
                content_hash = excluded.content_hash,
                exact_source_hash = excluded.exact_source_hash,
                semantic_hash = excluded.semantic_hash,
                structural_hash = excluded.structural_hash,
                source = excluded.source,
                docstring = excluded.docstring,
                signature = excluded.signature,
                decorators_json = excluded.decorators_json,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    entity.entity_id,
                    entity.project_id,
                    entity.file_id,
                    entity.source_kind.value,
                    entity.entity_type.value,
                    entity.name,
                    entity.qualified_name,
                    entity.parent_id,
                    entity.source_range.start_line,
                    entity.source_range.end_line,
                    entity.source_range.start_column,
                    entity.source_range.end_column,
                    entity.content_hash,
                    entity.exact_source_hash,
                    entity.semantic_hash,
                    entity.structural_hash,
                    entity.source,
                    entity.docstring,
                    entity.signature,
                    json.dumps(entity.decorators),
                    json.dumps(entity.metadata, sort_keys=True),
                )
                for entity in entities
            ],
        )

    def update_structural_hash(self, entity_id: str, structural_hash: str) -> None:
        self.connection.execute(
            "UPDATE entities SET structural_hash = ? WHERE entity_id = ?",
            (structural_hash, entity_id),
        )

    def get(self, entity_id: str) -> Entity | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM entities
            WHERE entity_id = ?
            """,
            (entity_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_entity(row)

    def list_for_file(self, file_id: str) -> list[Entity]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM entities
            WHERE file_id = ?
            ORDER BY start_line, start_column, end_line
            """,
            (file_id,),
        ).fetchall()

        return [_row_to_entity(row) for row in rows]

    def list_all(self) -> list[Entity]:
        rows = self.connection.execute(
            "SELECT * FROM entities ORDER BY file_id, start_line"
        ).fetchall()
        return [_row_to_entity(row) for row in rows]

    def delete(self, entity_id: str) -> None:
        logger.debug("EntityRepository :: delete :: entity_id=%s", entity_id)
        self.connection.execute(
            "DELETE FROM entities WHERE entity_id = ?",
            (entity_id,),
        )


class RelationshipRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert(self, relationship: Relationship) -> None:
        logger.debug(
            "RelationshipRepository :: upsert :: relationship_id=%s",
            relationship.relationship_id,
        )
        self.connection.execute(
            """
            INSERT INTO relationships (
                relationship_id,
                project_id,
                source_entity_id,
                target_entity_id,
                relationship_kind,
                confidence,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relationship_id) DO UPDATE SET
                source_entity_id = excluded.source_entity_id,
                target_entity_id = excluded.target_entity_id,
                relationship_kind = excluded.relationship_kind,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json
            """,
            (
                relationship.relationship_id,
                relationship.project_id,
                relationship.source_entity_id,
                relationship.target_entity_id,
                relationship.kind.value,
                relationship.confidence.value,
                json.dumps(relationship.metadata, sort_keys=True),
            ),
        )

    def upsert_many(self, relationships: list[Relationship]) -> None:
        if not relationships:
            return

        self.connection.executemany(
            """
            INSERT INTO relationships (
                relationship_id,
                project_id,
                source_entity_id,
                target_entity_id,
                relationship_kind,
                confidence,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relationship_id) DO UPDATE SET
                source_entity_id = excluded.source_entity_id,
                target_entity_id = excluded.target_entity_id,
                relationship_kind = excluded.relationship_kind,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    relationship.relationship_id,
                    relationship.project_id,
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                    relationship.kind.value,
                    relationship.confidence.value,
                    json.dumps(relationship.metadata, sort_keys=True),
                )
                for relationship in relationships
            ],
        )

    def delete_for_entity(self, entity_id: str) -> None:
        logger.debug("RelationshipRepository :: delete_for_entity :: entity_id=%s", entity_id)
        self.connection.execute(
            """
            DELETE FROM relationships
            WHERE source_entity_id = ?
               OR target_entity_id = ?
            """,
            (entity_id, entity_id),
        )

    def find_for_entity(self, entity_id: str) -> list[Relationship]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM relationships
            WHERE source_entity_id = ?
               OR target_entity_id = ?
            ORDER BY relationship_kind
            """,
            (entity_id, entity_id),
        ).fetchall()

        return [
            Relationship(
                relationship_id=row["relationship_id"],
                project_id=row["project_id"],
                source_entity_id=row["source_entity_id"],
                target_entity_id=row["target_entity_id"],
                kind=RelationshipKind(row["relationship_kind"]),
                confidence=RelationshipConfidence(row["confidence"]),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]


class MarkdownSectionRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert(
        self,
        *,
        section_id: str,
        project_id: str,
        file_id: str,
        parent_section_id: str | None,
        heading: str,
        heading_level: int,
        heading_path: str,
        start_line: int,
        end_line: int,
        content_hash: str,
        exact_source_hash: str,
        semantic_hash: str,
        source: str,
    ) -> None:
        logger.debug("MarkdownSectionRepository :: upsert :: section_id=%s", section_id)
        self.connection.execute(
            """
            INSERT INTO markdown_sections (
                section_id, project_id, file_id, parent_section_id,
                heading, heading_level, heading_path,
                start_line, end_line,
                content_hash, exact_source_hash, semantic_hash,
                source, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            ON CONFLICT(section_id) DO UPDATE SET
                parent_section_id=excluded.parent_section_id,
                heading=excluded.heading,
                heading_level=excluded.heading_level,
                heading_path=excluded.heading_path,
                start_line=excluded.start_line,
                end_line=excluded.end_line,
                content_hash=excluded.content_hash,
                exact_source_hash=excluded.exact_source_hash,
                semantic_hash=excluded.semantic_hash,
                source=excluded.source
            """,
            (
                section_id, project_id, file_id, parent_section_id,
                heading, heading_level, heading_path,
                start_line, end_line,
                content_hash, exact_source_hash, semantic_hash, source,
            ),
        )

    def get(self, section_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM markdown_sections WHERE section_id = ?",
            (section_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_for_file(self, file_id: str) -> None:
        logger.debug("MarkdownSectionRepository :: delete_for_file :: file_id=%s", file_id)
        self.connection.execute(
            "DELETE FROM markdown_sections WHERE file_id = ?",
            (file_id,),
        )

    def find_by_heading_path(self, heading_path: str, project_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM markdown_sections WHERE heading_path = ? AND project_id = ?",
            (heading_path, project_id),
        ).fetchall()
        return [dict(r) for r in rows]


EmbeddingCacheEntry = tuple[str, str, str, str, str, str, str, str, str]
SummaryCacheEntry = tuple[str, str, str, str, str, str, str, str, str, str]


class RepositoryStore:
    """Small repository facade used by the indexing/search/retrieval layers."""

    def __init__(self, connection: Connection):
        self.connection = connection
        self.projects = ProjectRepository(connection)
        self.entities = EntityRepository(connection)
        self.relationships = RelationshipRepository(connection)
        self.markdown_sections = MarkdownSectionRepository(connection)
        self._current_project_id = ""
        self._project_id_cache: str | None = None

    def set_project_id(self, project_id: str) -> None:
        self._current_project_id = project_id
        self._project_id_cache = None

    # Compatibility helpers used by IndexManager.
    def get_file(self, relative_path: str) -> dict | None:
        where = "relative_path = ?"
        params: list[Any] = [relative_path]
        if self._current_project_id:
            where += " AND project_id = ?"
            params.append(self._current_project_id)

        row = self.connection.execute(
            f"SELECT * FROM files WHERE {where} LIMIT 1", params
        ).fetchone()
        if row is None:
            return None

        result = dict(row)
        result.setdefault("content_hash", result.get("exact_hash"))
        return result

    def upsert_file(self, relative_path: str, content_hash: str, entity_count: int) -> str:
        logger.debug("RepositoryStore :: upsert_file :: relative_path=%s", relative_path)
        row = self.connection.execute(
            "SELECT file_id, project_id FROM files WHERE relative_path = ? LIMIT 1",
            (relative_path,),
        ).fetchone()
        file_id = row["file_id"] if row else f"file:{relative_path}"
        project_id = row["project_id"] if row else self._current_project_id
        source_kind = "python" if relative_path.lower().endswith((".py", ".pyi")) else "markdown"
        self.connection.execute(
            """
            INSERT INTO files(
                file_id, project_id, relative_path, canonical_path, source_kind,
                exact_hash, semantic_hash, size_bytes, mtime_ns, encoding,
                parser_version, parse_status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?)
            ON CONFLICT(file_id) DO UPDATE SET
                project_id=excluded.project_id,
                canonical_path=excluded.canonical_path,
                source_kind=excluded.source_kind,
                exact_hash=excluded.exact_hash,
                semantic_hash=excluded.semantic_hash,
                size_bytes=excluded.size_bytes,
                mtime_ns=excluded.mtime_ns,
                parser_version=excluded.parser_version,
                parse_status='ok',
                metadata_json=excluded.metadata_json
            """,
            (file_id, project_id, relative_path, relative_path, source_kind,
             content_hash, content_hash, 0, 0, "utf-8", "0.1.0",
             json.dumps({"entity_count": entity_count})),
        )
        return file_id

    def get_entities_for_file(self, relative_path: str) -> list[Entity]:
        where = "f.relative_path = ?"
        params: list[Any] = [relative_path]
        if self._current_project_id:
            where += " AND f.project_id = ?"
            params.append(self._current_project_id)

        rows = self.connection.execute(
            f"""
            SELECT e.*
            FROM entities e
            JOIN files f ON f.file_id = e.file_id
            WHERE {where}
            ORDER BY e.start_line, e.start_column, e.end_line
            """,
            params,
        ).fetchall()
        return [_row_to_entity(row) for row in rows]

    def upsert_entity(self, entity: Entity) -> None:
        logger.debug("RepositoryStore :: upsert_entity :: entity_id=%s", entity.entity_id)
        # Ensure the FK parent file exists, including on a brand-new index.
        self.connection.execute(
            """
            INSERT OR IGNORE INTO files(
                file_id, project_id, relative_path, canonical_path, source_kind,
                exact_hash, semantic_hash, size_bytes, mtime_ns, encoding, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'utf-8', '0.1.0')
            """,
            (entity.file_id, entity.project_id,
             entity.file_id, entity.file_id, entity.source_kind.value,
             entity.exact_source_hash, entity.semantic_hash),
        )
        self.entities.upsert(entity)
        self._upsert_search_document(entity)

    def upsert_entities(self, entities: list[Entity]) -> None:
        if not entities:
            return

        self.connection.executemany(
            """
            INSERT OR IGNORE INTO files(
                file_id, project_id, relative_path, canonical_path, source_kind,
                exact_hash, semantic_hash, size_bytes, mtime_ns, encoding, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'utf-8', '0.1.0')
            """,
            [
                (entity.file_id, entity.project_id,
                 entity.file_id, entity.file_id, entity.source_kind.value,
                 entity.exact_source_hash, entity.semantic_hash)
                for entity in entities
            ],
        )
        self.entities.upsert_many(entities)

        for entity in entities:
            self._upsert_search_document(entity)

    def update_structural_hash(self, entity_id: str, structural_hash: str) -> None:
        self.entities.update_structural_hash(entity_id, structural_hash)

    def delete_entity(self, entity_id: str) -> None:
        logger.debug("RepositoryStore :: delete_entity :: entity_id=%s", entity_id)
        row = self.connection.execute(
            "SELECT document_id FROM search_documents WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        for r in row:
            self._delete_search_document(r["document_id"])
        self.entities.delete(entity_id)

    def _upsert_search_document(self, entity: Entity) -> None:
        document_id = f"entity:{entity.entity_id}"
        path = entity.file_id
        keywords = " ".join(entity.metadata.get("keywords", []))
        parts = [entity.name, entity.qualified_name, entity.docstring or "", entity.source]
        content = "\n".join(filter(None, parts))
        metadata_json = json.dumps(entity.metadata, sort_keys=True)

        existing = self.connection.execute(
            """
            SELECT title, path, content, keywords, metadata_json
            FROM search_documents
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()

        if existing is not None and (
            existing["title"],
            existing["path"],
            existing["content"],
            existing["keywords"],
            existing["metadata_json"],
        ) == (entity.name, path, content, keywords, metadata_json):
            return

        self.connection.execute(
            """
            INSERT INTO search_documents(
                document_id, project_id, entity_id, section_id, source_kind,
                title, path, content, keywords, metadata_json
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                project_id=excluded.project_id, entity_id=excluded.entity_id,
                source_kind=excluded.source_kind, title=excluded.title,
                path=excluded.path, content=excluded.content,
                keywords=excluded.keywords, metadata_json=excluded.metadata_json
            """,
            (document_id, entity.project_id, entity.entity_id, entity.source_kind.value,
             entity.name, path, content, keywords, metadata_json),
        )
        self.connection.execute("DELETE FROM search_fts WHERE document_id = ?", (document_id,))
        self.connection.execute(
            "INSERT INTO search_fts"
            "(document_id, project_id, title, path, content, keywords)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (document_id, entity.project_id, entity.name, path, content, keywords),
        )

    def _delete_search_document(self, document_id: str) -> None:
        self.connection.execute(
            "DELETE FROM search_fts WHERE document_id = ?", (document_id,)
        )
        self.connection.execute(
            "DELETE FROM search_documents WHERE document_id = ?",
            (document_id,),
        )

    def search_symbols(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
        path: str | None = None,
        tokens: list[str] | None = None,
    ) -> list[dict]:
        where = ""
        where_params: list = []
        if kind == "python":
            where = " AND f.source_kind = 'python'"
        elif kind == "markdown":
            where = " AND f.source_kind = 'markdown'"
        if path:
            where += " AND f.relative_path = ?"
            where_params.append(path)

        filters: list[str] = []
        filter_params: list = []
        q = query.strip().lower()
        if tokens:
            for token in tokens:
                filters.append("(lower(e.name) LIKE ? OR lower(e.qualified_name) LIKE ?)")
                filter_params.extend([f"%{token.lower()}%", f"%{token.lower()}%"])
        else:
            filters.append("(lower(e.name) LIKE ? OR lower(e.qualified_name) LIKE ?)")
            filter_params.extend([f"%{q}%", f"%{q}%"])

        exact = tokens or [q]
        exact_placeholders = ", ".join("?" for _ in exact)
        rows = self.connection.execute(
            f"""
            SELECT e.entity_id, f.relative_path AS path, e.entity_type AS kind,
                   e.name, e.qualified_name, e.start_line, e.end_line, e.source
            FROM entities e JOIN files f ON f.file_id=e.file_id
            WHERE ({' OR '.join(filters)}){where}
            ORDER BY CASE WHEN lower(e.name) IN ({exact_placeholders}) THEN 0 ELSE 1 END, e.name
            LIMIT ?
            """,
            (*filter_params, *where_params, *(token.lower() for token in exact), limit),
        ).fetchall()
        return [
            {"entity_id": r["entity_id"], "path": r["path"], "kind": r["kind"],
             "name": r["name"], "qualified_name": r["qualified_name"],
             "start_line": r["start_line"], "end_line": r["end_line"],
             "text": r["source"], "score": 10.0}
            for r in rows
        ]

    def search_text(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
        path: str | None = None,
        tokens: list[str] | None = None,
    ) -> list[dict]:
        where = "d.project_id = ?"
        params: list = [self._project_id()]
        if kind == "python":
            where += " AND d.source_kind = 'python'"
        elif kind == "markdown":
            where += " AND d.source_kind = 'markdown'"
        if path:
            where += " AND f.path = ?"
            params.append(f"file:{path}")

        def safe_token(value: str) -> str:
            return " ".join(re.sub(r"[^\w\s]", " ", value).split())

        if tokens:
            safe_tokens = [safe_token(token) for token in tokens]
            safe_tokens = [token for token in safe_tokens if token]
            if not safe_tokens:
                return []
            match = " OR ".join(safe_tokens)
        else:
            match = safe_token(query)
            if not match:
                return []

        rows = self.connection.execute(
            f"""
            SELECT d.entity_id, f.title, f.path, f.content, d.source_kind,
                   bm25(search_fts) AS score
            FROM search_fts f JOIN search_documents d ON d.document_id=f.document_id
            WHERE search_fts MATCH ? AND {where}
            ORDER BY bm25(search_fts)
            LIMIT ?
            """,
            (match, *params, limit),
        ).fetchall()
        return [
            {
                "entity_id": r["entity_id"],
                "path": r["path"].removeprefix("file:"),
                "kind": r["source_kind"],
                "name": r["title"],
                "text": r["content"],
                "score": float(-r["score"]),
            }
            for r in rows
            if r["entity_id"]
        ]

    def search_headings(
        self,
        query: str,
        *,
        limit: int = 20,
        path: str | None = None,
        tokens: list[str] | None = None,
    ) -> list[dict]:
        """Search markdown sections by heading with hierarchy awareness.

        Matches heading text using LIKE, ordered by heading_level ascending
        (more specific sections first).
        """
        search_tokens = tokens if tokens is not None else [t for t in query.split() if t]
        if not search_tokens:
            return []

        if tokens is None:
            conditions = " AND ".join(["m.heading LIKE ?"] * len(search_tokens))
            params: list[str] = [f"%{t}%" for t in search_tokens]
        else:
            conditions = " OR ".join(["m.heading LIKE ?"] * len(search_tokens))
            params = [f"%{t}%" for t in search_tokens]

        where = f"m.project_id = ? AND ({conditions})"
        full_params: list = [self._project_id(), *params]
        if path:
            where += " AND f.relative_path = ?"
            full_params.append(path)
        full_params.append(limit)

        rows = self.connection.execute(
            f"""
            SELECT m.section_id, m.heading, m.heading_level, m.heading_path,
                   f.relative_path AS relative_path, m.start_line, m.end_line
            FROM markdown_sections m LEFT JOIN files f ON f.file_id = m.file_id
            WHERE {where}
            ORDER BY m.heading_level ASC
            LIMIT ?
            """,
            full_params,
        ).fetchall()

        return [
            {
                "entity_id": r["section_id"],
                "path": r["relative_path"] or "",
                "kind": "markdown",
                "name": r["heading"],
                "heading_level": r["heading_level"],
                "heading_path": r["heading_path"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "score": 1.0 + (1.0 / max(r["heading_level"], 1)),
                "match_reason": "heading match",
            }
            for r in rows
        ]

    def _project_id(self) -> str:
        if self._project_id_cache is not None:
            return self._project_id_cache
        row = self.connection.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
        self._project_id_cache = row["project_id"] if row else ""
        return self._project_id_cache

    def get_entity(self, entity_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        return _entity_result(_row_to_entity(row)) if row else None

    def get_parent(self, entity_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT parent_id FROM entities WHERE entity_id=?", (entity_id,)
        ).fetchone()
        return self.get_entity(row["parent_id"]) if row and row["parent_id"] else None

    def get_children(self, entity_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM entities WHERE parent_id=? ORDER BY start_line",
            (entity_id,),
        ).fetchall()
        return [_entity_result(_row_to_entity(row)) for row in rows]

    def get_relationships(self, entity_id: str) -> list[dict]:
        return [r.to_dict() for r in self.relationships.find_for_entity(entity_id)]

    def get_file_region(self, path: str, start_line: int, end_line: int) -> dict:
        # First try reading from the indexed entity sources (cached in DB).
        file_where = "relative_path = ?"
        file_params: list[Any] = [path]
        if self._current_project_id:
            file_where += " AND project_id = ?"
            file_params.append(self._current_project_id)
        file_row = self.connection.execute(
            f"SELECT file_id FROM files WHERE {file_where} LIMIT 1", file_params
        ).fetchone()
        if file_row:
            entity_rows = self.connection.execute(
                """SELECT source, start_line, end_line
                   FROM entities WHERE file_id = ?
                   ORDER BY start_line""",
                (file_row["file_id"],),
            ).fetchall()
            if entity_rows:
                lines: list[str] = []
                seen_lines: set[int] = set()
                for er in entity_rows:
                    elines = er["source"].splitlines()
                    e_start = er["start_line"]
                    for i, line in enumerate(elines):
                        actual_line = e_start + i
                        if start_line <= actual_line <= end_line and actual_line not in seen_lines:
                            lines.append(line)
                            seen_lines.add(actual_line)
                if lines:
                    return {"path": path, "start_line": start_line,
                            "end_line": end_line, "source": "\n".join(lines),
                            "from_cache": True}

        # Fall back to reading from disk.
        row = self.connection.execute(
            "SELECT canonical_root FROM projects LIMIT 1"
        ).fetchone()
        if not row:
            raise KeyError("Project is not indexed")
        root = Path(row["canonical_root"]).resolve()
        target = (root / path).resolve()
        target.relative_to(root)
        disk_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, start_line)
        end = min(len(disk_lines), end_line)
        return {"path": path, "start_line": start, "end_line": end,
                "source": "\n".join(disk_lines[start-1:end]), "from_cache": False}

    def get_markdown_section(self, entity_id: str) -> dict | None:
        section = self.markdown_sections.get(entity_id)
        if section:
            section["entity_id"] = section["section_id"]
            section["entity_type"] = "markdown_section"
            return section
        # Tolerate a partial heading path: allow the caller to pass just the
        # section name (`markdown:docs/cache.md:Usage`) instead of the full
        # hierarchical path (`markdown:docs/cache.md:Welcome/Usage`).
        resolved = self._resolve_markdown_section_by_heading(entity_id)
        if resolved:
            return resolved
        return self.get_entity(entity_id)

    def _resolve_markdown_section_by_heading(self, entity_id: str) -> dict | None:
        prefix = "markdown:"
        if not entity_id.startswith(prefix):
            return None
        remainder = entity_id[len(prefix):]
        path, sep, heading = remainder.partition(":")
        if not sep or not heading:
            return None
        if "/" not in heading:
            file_id = _file_id(path)
            candidates = self.connection.execute(
                "SELECT * FROM markdown_sections"
                " WHERE file_id = ? AND (heading = ? OR heading_path = ?)",
                (file_id, heading, heading),
            ).fetchall()
            if len(candidates) == 1:
                row = dict(candidates[0])
                row["entity_id"] = row["section_id"]
                row["entity_type"] = "markdown_section"
                return row
        return None

    def list_entities(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM entities ORDER BY file_id,start_line"
        ).fetchall()
        return [_entity_result(_row_to_entity(row)) for row in rows]

    def clear(self) -> None:
        with self.connection:
            for table in ("search_fts", "search_documents", "relationships",
                          "entity_versions", "entities", "files"):
                self.connection.execute(f"DELETE FROM {table}")

    @staticmethod
    def _chunks(values: list[str], size: int = 500) -> Iterator[list[str]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

    def get_embeddings_by_cache_keys(self, cache_keys: list[str]) -> dict[str, list[float]]:
        result: dict[str, list[float]] = {}
        for chunk in self._chunks(cache_keys):
            if not chunk:
                continue
            placeholders = ", ".join("?" for _ in chunk)
            rows = self.connection.execute(
                "SELECT cache_key, vector_json FROM embeddings"
                f" WHERE cache_key IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                result[row["cache_key"]] = json.loads(row["vector_json"])
        return result

    def store_embeddings(self, entries: list[EmbeddingCacheEntry]) -> None:
        if not entries:
            return
        self.connection.executemany(
            """INSERT INTO embeddings
                (cache_key, project_id, document_id, semantic_hash,
                 provider, model, representation_version, vector_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                vector_json=excluded.vector_json, document_id=excluded.document_id""",
            entries,
        )

    def get_summaries_by_cache_keys(self, cache_keys: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for chunk in self._chunks(cache_keys):
            if not chunk:
                continue
            placeholders = ", ".join("?" for _ in chunk)
            rows = self.connection.execute(
                f"SELECT cache_key, summary FROM summaries WHERE cache_key IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                result[row["cache_key"]] = row["summary"]
        return result

    def store_summaries(self, entries: list[SummaryCacheEntry]) -> None:
        if not entries:
            return
        self.connection.executemany(
            """INSERT INTO summaries
                (cache_key, project_id, document_id, semantic_hash,
                 metadata_hash, provider, model, prompt_version, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                summary=excluded.summary, document_id=excluded.document_id""",
            entries,
        )

    def get_embedding(
        self, content_hash: str, provider: str, model: str, version: str
    ) -> list[float] | None:
        row = self.connection.execute(
            "SELECT vector_json FROM embeddings"
            " WHERE semantic_hash=? AND provider=?"
            " AND model=? AND representation_version=?",
            (content_hash, provider, model, version),
        ).fetchone()
        if row is None:
            return None
        import json as _json
        return _json.loads(row["vector_json"])

    def store_embedding(
        self, content_hash: str, provider: str, model: str, version: str,
        vector: list[float], *, document_id: str = "",
    ) -> None:
        import json as _json
        cache_key = f"emb:{content_hash}:{provider}:{model}:{version}"
        project_id = self._current_project_id
        if not document_id:
            document_id = f"entity:{content_hash}"
        self.connection.execute(
            """INSERT INTO embeddings
                (cache_key, project_id, document_id, semantic_hash,
                 provider, model, representation_version, vector_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                vector_json=excluded.vector_json""",
            (cache_key, project_id, document_id, content_hash,
             provider, model, version, _json.dumps(vector), utc_now()),
        )

    def get_summary(
        self,
        semantic_hash: str,
        metadata_hash: str,
        provider: str,
        model: str,
        version: str,
        prompt_version: str,
    ) -> str | None:
        cache_key = f"sum:{semantic_hash}:{provider}:{model}:{version}:{prompt_version}"
        row = self.connection.execute(
            "SELECT summary FROM summaries WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
        return row["summary"] if row else None


    def store_summary(
        self,
        semantic_hash: str,
        metadata_hash: str,
        provider: str,
        model: str,
        version: str,
        prompt_version: str,
        summary: str,
        *,
        document_id: str = "",
    ) -> None:
        cache_key = f"sum:{semantic_hash}:{provider}:{model}:{version}:{prompt_version}"
        project_id = self._current_project_id
        if not document_id:
            document_id = f"entity:{semantic_hash}"
        self.connection.execute(
            """INSERT INTO summaries
                (cache_key, project_id, document_id, semantic_hash,
                 metadata_hash, provider, model, prompt_version, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                summary=excluded.summary""",
            (cache_key, project_id, document_id, semantic_hash,
             metadata_hash, provider, model, prompt_version, summary, utc_now()),
        )
