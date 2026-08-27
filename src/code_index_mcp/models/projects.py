from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IndexState(StrEnum):
    NEW = "new"
    INDEXING = "indexing"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    project_id: str
    canonical_root: str
    schema_version: int
    indexer_version: str
    indexing_state: IndexState
    configuration_fingerprint: str
    last_indexed_at: str | None
    indexed_files: int
    indexed_entities: int
    indexed_markdown_sections: int
    health: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "canonical_root": self.canonical_root,
            "schema_version": self.schema_version,
            "indexer_version": self.indexer_version,
            "indexing_state": self.indexing_state.value,
            "configuration_fingerprint": self.configuration_fingerprint,
            "last_indexed_at": self.last_indexed_at,
            "indexed_files": self.indexed_files,
            "indexed_entities": self.indexed_entities,
            "indexed_markdown_sections": self.indexed_markdown_sections,
            "health": self.health,
            "metadata": self.metadata,
        }
