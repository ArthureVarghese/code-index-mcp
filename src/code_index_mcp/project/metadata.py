from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from code_index_mcp.config import IndexConfig
from code_index_mcp.indexing.versions import INDEXER_VERSION
from code_index_mcp.models.projects import IndexState, ProjectMetadata
from code_index_mcp.project.identity import project_id_for_root
from code_index_mcp.storage.database import Database
from code_index_mcp.storage.repositories import ProjectRepository, utc_now
from code_index_mcp.storage.schema import SCHEMA_VERSION

logger = logging.getLogger(__name__)


def new_project_metadata(
    project_root: str | Path,
    config: IndexConfig,
    *,
    state: IndexState = IndexState.NEW,
) -> ProjectMetadata:
    canonical_root = str(Path(project_root).resolve())
    project_id = project_id_for_root(canonical_root)

    return ProjectMetadata(
        project_id=project_id,
        canonical_root=canonical_root,
        schema_version=SCHEMA_VERSION,
        indexer_version=INDEXER_VERSION,
        indexing_state=state,
        configuration_fingerprint=config.fingerprint,
        last_indexed_at=None,
        indexed_files=0,
        indexed_entities=0,
        indexed_markdown_sections=0,
        health="new",
        metadata={},
    )


def ensure_project_metadata(
    database: Database,
    project_root: str | Path,
    config: IndexConfig,
) -> ProjectMetadata:
    """Create or load project metadata."""
    project_id = project_id_for_root(project_root)
    repository = ProjectRepository(database._connection)  # noqa: SLF001

    existing = repository.get(project_id)

    if existing is not None:
        logger.debug("ensure_project_metadata :: loaded existing for project_id=%s", project_id)
        return existing

    logger.debug("ensure_project_metadata :: creating new metadata for project_id=%s", project_id)
    metadata = new_project_metadata(project_root, config)

    with database.transaction():
        repository.upsert(metadata)

    return metadata


def set_project_state(
    database: Database,
    project_id: str,
    state: IndexState,
    *,
    health: str | None = None,
    last_indexed: bool = False,
) -> ProjectMetadata:
    repository = ProjectRepository(database._connection)  # noqa: SLF001
    current = repository.get(project_id)

    if current is None:
        raise ValueError(f"Unknown project: {project_id}")

    updated = replace(
        current,
        indexing_state=state,
        health=health if health is not None else current.health,
        last_indexed_at=utc_now() if last_indexed else current.last_indexed_at,
    )

    logger.debug("set_project_state :: project_id=%s, state=%s", project_id, state.value)

    with database.transaction():
        repository.upsert(updated)

    return updated
