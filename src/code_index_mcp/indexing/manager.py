from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_index_mcp.cache.invalidation import calculate_invalidation
from code_index_mcp.cache.manager import CacheManager
from code_index_mcp.config import IndexConfig
from code_index_mcp.indexing.entity_matcher import EntityMatcher, _is_container
from code_index_mcp.indexing.hashing import sha256_text
from code_index_mcp.indexing.relationships.analyzer import RelationshipAnalyzer
from code_index_mcp.indexing.versions import (
    INDEXER_VERSION,
    PYTHON_ANALYZER_VERSION,
)
from code_index_mcp.models.entities import (
    Relationship,
    RelationshipConfidence,
    RelationshipKind,
)

logger = logging.getLogger(__name__)

# Relationship kind mapping from PythonRelationshipAnalyzer to RelationshipKind
_RELATIONSHIP_KIND_MAP = {
    "imports": RelationshipKind.IMPORTS,
    "calls": RelationshipKind.CALLS,
    "inherits": RelationshipKind.INHERITS,
    "references": RelationshipKind.REFERENCES,
}

_CONFIDENCE_MAP = {
    "exact": RelationshipConfidence.EXACT,
    "inferred": RelationshipConfidence.INFERRED,
}


def _file_entity_count(file_row: dict | None) -> int:
    if not file_row:
        return 0

    metadata = file_row.get("metadata_json")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = {}

    if isinstance(metadata, dict):
        count = metadata.get("entity_count")
        if isinstance(count, int):
            return count

    return 0


class IndexManager:
    """Coordinates incremental project indexing."""

    def __init__(
        self,
        database: Any,
        python_analyzer: Any,
        markdown_analyzer: Any,
        repositories: Any,
        *,
        ignore: Any = None,
        embedding_provider: Any = None,
        summary_provider: Any = None,
        cache_manager: CacheManager | None = None,
        config: IndexConfig | None = None,
    ) -> None:
        self.config = config or IndexConfig()
        self.db = database
        self.python_analyzer = python_analyzer
        self.markdown_analyzer = markdown_analyzer
        self.repositories = repositories
        self.ignore = ignore

        self.matcher = EntityMatcher()
        self._relationship_pipeline = RelationshipAnalyzer()
        self._embedding_provider = embedding_provider
        self._summary_provider = summary_provider
        self._cache_manager = cache_manager

    def index_project(
        self,
        project_root: Path,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        import uuid

        started = time.monotonic()
        project_root = project_root.resolve()
        job_id = f"job:{uuid.uuid4().hex[:12]}"
        project_row = self.db.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
        project_id = project_row["project_id"] if project_row else ""

        files = self._discover_files(project_root)

        stats: dict[str, Any] = {
            "files_seen": len(files),
            "files_changed": 0,
            "files_reused": 0,
            "files_parsed": 0,
            "entities_reused": 0,
            "entities_recomputed": 0,
            "relationships_computed": 0,
            "embeddings_reused": 0,
            "embeddings_recomputed": 0,
            "summaries_reused": 0,
            "summaries_recomputed": 0,
            "errors": [],
        }

        resolver_map = (
            self._build_relationship_resolver_map()
            if self.config.enable_relationships
            else {}
        )
        pending_embeddings: list[Any] = []
        pending_summaries: list[Any] = []

        with self.db.transaction():
            try:
                self.db.execute(
                    "INSERT INTO index_jobs"
                    " (job_id, project_id, state, started_at)"
                    " VALUES (?, ?, 'running', ?)",
                    (job_id, project_id, datetime.now(UTC).isoformat()),
                )
            except Exception:
                logger.debug("Could not create index_job record (FK may not exist yet)")

            for path in files:
                try:
                    result = self._index_file(
                        project_root,
                        path,
                        force=force,
                        resolver_map=resolver_map,
                        pending_embeddings=pending_embeddings,
                        pending_summaries=pending_summaries,
                    )

                    for key, value in result.items():
                        if key in stats:
                            stats[key] += value

                except Exception as exc:
                    logger.exception("Failed to index %s", path)

                    stats["errors"].append(
                        {
                            "path": str(path),
                            "error": str(exc),
                        }
                    )

            stats["indexer_version"] = INDEXER_VERSION
            stats["job_id"] = job_id
            self._finalize_index_job(job_id, project_id, stats)

        self._enrich_entities(pending_embeddings, pending_summaries, stats)
        stats["duration_seconds"] = time.monotonic() - started
        self._finalize_index_job(job_id, project_id, stats)

        return stats

    def _finalize_index_job(
        self, job_id: str, project_id: str, stats: dict[str, Any]
    ) -> None:
        try:
            self.db.execute(
                """UPDATE index_jobs SET
                    state=?, completed_at=?, files_seen=?, files_changed=?,
                    files_reused=?, files_parsed=?, entities_reused=?,
                    entities_recomputed=?, embeddings_reused=?, embeddings_recomputed=?,
                    error=?
                WHERE job_id=?""",
                (
                    "completed" if not stats["errors"] else "failed",
                    datetime.now(UTC).isoformat(),
                    stats["files_seen"],
                    stats["files_changed"],
                    stats["files_reused"],
                    stats["files_parsed"],
                    stats["entities_reused"],
                    stats["entities_recomputed"],
                    stats["embeddings_reused"],
                    stats["embeddings_recomputed"],
                    json.dumps(stats["errors"]) if stats["errors"] else None,
                    job_id,
                ),
            )
        except Exception:
            logger.debug("Could not update index_job record")

    def _enrich_entities(
        self,
        pending_embeddings: list[Any],
        pending_summaries: list[Any],
        stats: dict[str, Any],
    ) -> None:
        if not pending_embeddings and not pending_summaries:
            return

        if pending_embeddings and self._embedding_provider:
            try:
                from code_index_mcp.embeddings.cache import EmbeddingCache

                cache = EmbeddingCache(self.repositories, self._embedding_provider)
                _, embedding_entries, reused, recomputed = cache.prepare_many(
                    [
                        (entity.semantic_hash, entity.source, f"entity:{entity.entity_id}")
                        for entity in pending_embeddings
                    ]
                )
                with self.db.transaction():
                    cache.store_many(embedding_entries)
                stats["embeddings_reused"] += reused
                stats["embeddings_recomputed"] += recomputed
            except Exception:
                logger.exception("Batch embedding enrichment failed")

        if pending_summaries and self._summary_provider:
            try:
                from code_index_mcp.summaries.cache import SummaryCache

                summary_cache = SummaryCache(self.repositories, self._summary_provider)
                _, summary_entries, reused, recomputed = summary_cache.prepare_many(
                    [
                        (
                            entity.semantic_hash,
                            entity.semantic_hash,
                            entity.source,
                            {
                                "name": entity.name,
                                "entity_type": entity.entity_type.value,
                            },
                            f"entity:{entity.entity_id}",
                        )
                        for entity in pending_summaries
                    ]
                )
                with self.db.transaction():
                    summary_cache.store_many(summary_entries)
                stats["summaries_reused"] += reused
                stats["summaries_recomputed"] += recomputed
            except Exception:
                logger.exception("Batch summary enrichment failed")

    def refresh_index(self, project_root: Path) -> dict[str, Any]:
        return self.index_project(project_root, force=False)

    def _discover_files(self, root: Path) -> list[Path]:
        result: list[Path] = []
        root = root.resolve()
        extensions = self.config.extensions
        excluded_directories = self.config.excluded_directories
        excluded_files = self.config.excluded_files
        max_size = self.config.max_file_size_bytes

        def walk(directory: Path) -> None:
            try:
                entries = list(os.scandir(directory))
            except OSError:
                return

            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue

                    path = Path(entry.path)

                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in excluded_directories:
                            continue
                        if self.ignore and self.ignore.is_ignored_dir(path):
                            continue
                        walk(path)
                        continue

                    if not entry.is_file(follow_symlinks=False):
                        continue

                    if entry.name in excluded_files:
                        continue

                    if path.suffix.lower() not in extensions:
                        continue

                    if entry.stat(follow_symlinks=False).st_size > max_size:
                        continue

                    if self.ignore and self.ignore.is_ignored(path):
                        continue

                    result.append(path)
                except OSError:
                    continue

        walk(root)
        return sorted(result)

    def _build_relationship_resolver_map(self) -> dict[str, str]:
        resolver: dict[str, str] = {}

        for entity in self.repositories.list_entities():
            entity_id = entity.get("entity_id", "")
            qualified_name = entity.get("qualified_name", "")
            name = entity.get("name", "")

            if qualified_name and entity_id:
                resolver[qualified_name] = entity_id
            if name and entity_id and name not in resolver:
                resolver[name] = entity_id

        return resolver

    def _index_file(
        self,
        root: Path,
        path: Path,
        *,
        force: bool,
        resolver_map: dict[str, str],
        pending_embeddings: list[Any],
        pending_summaries: list[Any],
    ) -> dict[str, int]:
        relative = path.relative_to(root).as_posix()

        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        file_hash = sha256_text(source)
        previous = self.repositories.get_file(relative)
        previous_hash = (
            (previous.get("exact_hash") or previous.get("content_hash"))
            if previous
            else None
        )

        if not force and previous and previous_hash == file_hash:
            return {
                "files_reused": 1,
                "files_changed": 0,
                "files_parsed": 0,
                "entities_reused": _file_entity_count(previous),
                "entities_recomputed": 0,
            }

        project_row = self.db.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
        project_id = project_row["project_id"] if project_row else ""

        if path.suffix.lower() in {".py", ".pyi"}:
            analyzed = self.python_analyzer.analyze(
                source,
                relative,
                project_id=project_id,
                file_id=f"file:{relative}",
            )
        else:
            analyzed = self.markdown_analyzer.analyze(
                source,
                relative,
                project_id=project_id,
                file_id=f"file:{relative}",
            )

        old_entities = self.repositories.get_entities_for_file(relative)

        old_hashes = {
            _entity_id(e): _entity_hash(e) or "" for e in old_entities
        }
        new_hashes = {
            e.entity_id: e.content_hash for e in analyzed.entities
        }

        plan = calculate_invalidation(old_hashes=old_hashes, new_hashes=new_hashes)

        if not force and not plan.has_changes and previous:
            return {
                "files_reused": 1,
                "files_changed": 0,
                "files_parsed": 1,
                "entities_reused": len(old_entities),
                "entities_recomputed": 0,
            }

        matched = self.matcher.match(
            old_entities,
            analyzed.entities,
        )

        result = {
            "files_changed": 1,
            "files_parsed": 1,
            "entities_reused": 0,
            "entities_recomputed": 0,
            "embeddings_reused": 0,
            "embeddings_recomputed": 0,
            "summaries_reused": 0,
            "summaries_recomputed": 0,
        }

        with self.db.savepoint():
            self.repositories.upsert_file(
                relative,
                file_hash,
                len(analyzed.entities),
            )

            changed_entities: list[Any] = []
            old_content_hashes: dict[str, str | None] = {}

            for entity in analyzed.entities:
                old = matched.get(entity.entity_id)

                if old and self._can_reuse_entity(old, entity):
                    result["entities_reused"] += 1
                    continue

                changed_entities.append(entity)
                old_content_hashes[entity.entity_id] = _entity_hash(old) if old else None

            if changed_entities:
                self.repositories.upsert_entities(changed_entities)

            for entity in changed_entities:
                result["entities_recomputed"] += 1
                old_content_hash = old_content_hashes.get(entity.entity_id)

                self._cache_entity(entity)

                if old_content_hash and old_content_hash != entity.content_hash:
                    self._write_entity_version(entity)

                if self._embedding_provider:
                    pending_embeddings.append(entity)

                if self._summary_provider:
                    pending_summaries.append(entity)

            for entity_id in plan.removed_entities:
                self.repositories.delete_entity(entity_id)

            relationships = self._compute_relationships(
                analyzed.entities,
                getattr(analyzed, "tree", None),
                relative,
                project_id,
                resolver_map,
            )
            if relationships:
                self.repositories.relationships.upsert_many(relationships)
            result["relationships_computed"] = len(relationships)

            self._populate_markdown_sections(
                analyzed.entities, project_id, file_id=f"file:{relative}"
            )

            self._recompute_container_hashes(analyzed.entities)

        return result

    def _compute_relationships(
        self,
        entities: list[Any],
        tree: Any,
        relative_path: str,
        project_id: str,
        resolver_map: dict[str, str],
    ) -> list[Relationship]:
        """Run RelationshipAnalyzer and convert RelationshipCandidates to Relationship objects."""
        if not self.config.enable_relationships or tree is None:
            return []

        entity_ids_by_qname = dict(resolver_map)
        for entity in entities:
            if entity.qualified_name:
                entity_ids_by_qname[entity.qualified_name] = entity.entity_id
            if entity.name and entity.name not in entity_ids_by_qname:
                entity_ids_by_qname[entity.name] = entity.entity_id

        module_entity_id = f"python:{relative_path}"
        candidates = self._relationship_pipeline.analyze_python(
            module_entity_id=module_entity_id,
            tree=tree,
            entity_ids_by_qualified_name=entity_ids_by_qname,
        )

        relationships: list[Relationship] = []
        seen: set[tuple[str, str, str]] = set()

        for candidate in candidates:
            kind = _RELATIONSHIP_KIND_MAP.get(candidate.relationship_type)
            if kind is None:
                continue

            source_id = candidate.source_entity_id
            target_id = candidate.metadata.get("resolved_target")

            dedup_key = (source_id, str(target_id or ""), kind.value)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            rel_id = _relationship_id(source_id, str(target_id or ""), kind.value)
            confidence = _CONFIDENCE_MAP.get(candidate.confidence, RelationshipConfidence.EXACT)

            relationships.append(
                Relationship(
                    relationship_id=rel_id,
                    project_id=project_id,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    kind=kind,
                    confidence=confidence,
                    metadata={"line": candidate.line, "analyzer": "python_ast"},
                )
            )

        return relationships

    def _cache_entity(self, entity: Any) -> None:
        """Record a cache-metadata entry for a newly computed entity."""
        if not self._cache_manager:
            return
        project_id = self.repositories._current_project_id
        if not project_id:
            return
        try:
            self._cache_manager.put(
                project_id=project_id,
                cache_key=f"entity:{entity.entity_id}",
                layer="entity",
                source_hash=entity.content_hash,
                dependency_hash=None,
                implementation_version=PYTHON_ANALYZER_VERSION,
                value={
                    "entity_id": entity.entity_id,
                    "name": entity.name,
                    "kind": entity.entity_type.value,
                },
            )
        except Exception:
            logger.debug("CacheManager :: failed to cache entity %s", entity.entity_id)

    def _write_entity_version(self, entity: Any) -> None:
        """Record a version snapshot when an entity's content hash changes."""
        from datetime import UTC, datetime

        self.db.execute(
            """INSERT OR IGNORE INTO entity_versions
                (entity_id, content_hash, exact_source_hash, semantic_hash,
                 structural_hash, indexer_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entity.entity_id,
                entity.content_hash,
                entity.exact_source_hash,
                entity.semantic_hash,
                entity.structural_hash,
                INDEXER_VERSION,
                datetime.now(UTC).isoformat(),
            ),
        )

    def _update_embedding(self, entity: Any) -> bool:
        """Update embedding for an entity. Returns True if reused from cache."""
        from code_index_mcp.embeddings.cache import EmbeddingCache

        cache = EmbeddingCache(self.repositories, self._embedding_provider)
        document_id = f"entity:{entity.entity_id}"

        existing = self.db.execute(
            "SELECT vector_json FROM embeddings WHERE document_id=?",
            (document_id,),
        ).fetchone()

        cache.get_or_create(
            content_hash=entity.semantic_hash,
            text=entity.source,
            document_id=document_id,
        )

        return existing is not None

    def _update_summary(self, entity: Any) -> bool:
        """Update summary for an entity. Returns True if reused from cache."""
        from code_index_mcp.summaries.cache import SummaryCache

        cache = SummaryCache(self.repositories, self._summary_provider)
        metadata_hash = entity.semantic_hash
        document_id = f"entity:{entity.entity_id}"

        existing = self.db.execute(
            "SELECT summary FROM summaries WHERE semantic_hash=? AND metadata_hash=?",
            (entity.semantic_hash, metadata_hash),
        ).fetchone()

        cache.get_or_create(
            semantic_hash=entity.semantic_hash,
            metadata_hash=metadata_hash,
            text=entity.source,
            metadata={"name": entity.name, "entity_type": entity.entity_type.value},
            document_id=document_id,
        )

        return existing is not None

    def _populate_markdown_sections(
        self, entities: list[Any], project_id: str, *, file_id: str
    ) -> None:
        """Populate the markdown_sections table for markdown entities."""
        for entity in entities:
            if entity.source_kind.value != "markdown":
                continue

            meta = entity.metadata
            self.repositories.markdown_sections.upsert(
                section_id=entity.entity_id,
                project_id=project_id,
                file_id=file_id,
                parent_section_id=entity.parent_id,
                heading=entity.name,
                heading_level=meta.get("heading_level", 1),
                heading_path=meta.get("heading_path", entity.name),
                start_line=entity.source_range.start_line,
                end_line=entity.source_range.end_line,
                content_hash=entity.content_hash,
                exact_source_hash=entity.exact_source_hash,
                semantic_hash=entity.semantic_hash,
                source=entity.source,
            )

    def _recompute_container_hashes(self, entities: list[Any]) -> None:
        """Recompute structural hashes for container entities using actual child IDs."""
        from code_index_mcp.indexing.hashing import structural_hash

        containers = [e for e in entities if e.entity_type.value in {"module", "class"}]
        children_by_parent: dict[str, list[str]] = {}

        for entity in entities:
            if entity.parent_id:
                children_by_parent.setdefault(entity.parent_id, []).append(entity.entity_id)

        for container in containers:
            child_ids = sorted(children_by_parent.get(container.entity_id, []))

            new_structural = structural_hash(
                entity_type=container.entity_type.value,
                name=container.name,
                qualified_name=container.qualified_name,
                signature=container.signature,
                decorators=container.decorators,
                child_ids=child_ids,
            )

            if new_structural != container.structural_hash:
                self.repositories.update_structural_hash(container.entity_id, new_structural)

    @staticmethod
    def _can_reuse_entity(old: Any, current: Any) -> bool:
        """
        Determine whether an existing entity can be retained.

        A class/module entity contains the source of its nested children, so
        its raw content hash changes whenever a method/function inside it
        changes. That does not make the class entity itself a changed entity.

        Child entities are matched by their logical entity ID and their own
        content hash, so only the actually modified child is recomputed.
        """
        if _entity_hash(old) == _entity_hash(current):
            return True

        # Container entities should not be invalidated merely because one of
        # their children changed or a child was added.
        return _is_container(current)


def _entity_id(entity: Any) -> str:
    if isinstance(entity, dict):
        return str(entity["entity_id"])

    return str(entity.entity_id)


def _entity_hash(entity: Any) -> str | None:
    if isinstance(entity, dict):
        return entity.get("content_hash")

    return entity.content_hash


def _entity_type(entity: Any) -> str:
    value = (
        entity.get("entity_type")
        if isinstance(entity, dict)
        else getattr(entity, "entity_type", None)
    )

    if value is None:
        return ""

    return getattr(value, "value", str(value)).lower()


def _relationship_id(source_id: str, target_id: str, kind: str) -> str:
    raw = f"{source_id}\x00{target_id}\x00{kind}"
    return "rel:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
