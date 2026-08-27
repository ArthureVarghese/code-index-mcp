from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RelationshipCandidate:
    source_entity_id: str
    target_name: str
    relationship_type: str
    confidence: str
    line: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
