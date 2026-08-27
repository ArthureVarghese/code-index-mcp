from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class InvalidationPlan:
    changed_entities: set[str] = field(default_factory=set)
    removed_entities: set[str] = field(default_factory=set)
    reused_entities: set[str] = field(default_factory=set)

    changed_files: set[str] = field(default_factory=set)
    removed_files: set[str] = field(default_factory=set)

    invalidate_search: set[str] = field(default_factory=set)
    invalidate_embeddings: set[str] = field(default_factory=set)
    invalidate_summaries: set[str] = field(default_factory=set)
    invalidate_relationships: set[str] = field(default_factory=set)

    structural_changes: set[str] = field(default_factory=set)

    @property
    def changed(self) -> set[str]:
        """Compatibility alias used by the unit tests."""
        return self.changed_entities

    @property
    def unchanged(self) -> set[str]:
        """Entity IDs whose hashes did not change."""
        return self.reused_entities

    @property
    def removed(self) -> set[str]:
        return self.removed_entities

    @property
    def has_changes(self) -> bool:
        return bool(
            self.changed_entities
            or self.removed_entities
            or self.changed_files
            or self.removed_files
            or self.invalidate_search
            or self.invalidate_embeddings
            or self.invalidate_summaries
            or self.invalidate_relationships
            or self.structural_changes
        )


def calculate_invalidation(
    *,
    old_hashes: Mapping[str, str],
    new_hashes: Mapping[str, str],
) -> InvalidationPlan:
    """Compare two entity-hash mappings and produce an invalidation plan."""
    old_ids = set(old_hashes)
    new_ids = set(new_hashes)

    added = new_ids - old_ids
    removed = old_ids - new_ids
    common = old_ids & new_ids

    changed = {entity_id for entity_id in common if old_hashes[entity_id] != new_hashes[entity_id]}

    unchanged = common - changed

    return InvalidationPlan(
        changed_entities=changed | added,
        removed_entities=removed,
        reused_entities=unchanged,
        invalidate_search=changed | added | removed,
        invalidate_embeddings=changed | added | removed,
        invalidate_summaries=changed | added | removed,
        invalidate_relationships=changed | added | removed,
    )
