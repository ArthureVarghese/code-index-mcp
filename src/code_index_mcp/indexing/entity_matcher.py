from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ..models.entities import Entity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EntityMatch:
    current: Entity
    previous: Entity | None
    status: str


def logical_entity_key(entity: Entity) -> str:
    """Return identity independent of source content."""
    return ":".join(
        (
            entity.source_kind.value,
            entity.file_id,
            entity.qualified_name,
            entity.entity_type.value,
        )
    )


def match_entities(
    current: list[Entity],
    previous: list[Entity],
) -> list[EntityMatch]:
    """Match current entities against previous entities by logical identity."""
    previous_by_key: dict[str, list[Entity]] = defaultdict(list)

    for entity in previous:
        previous_by_key[logical_entity_key(entity)].append(entity)

    matches: list[EntityMatch] = []

    for entity in current:
        candidates = previous_by_key.get(
            logical_entity_key(entity),
            [],
        )

        previous_entity = candidates.pop(0) if candidates else None

        if previous_entity is None:
            status = "new"
        elif previous_entity.content_hash == entity.content_hash:
            status = "unchanged"
        elif _is_container(entity):
            status = "unchanged"
        else:
            status = "changed"

        matches.append(
            EntityMatch(
                current=entity,
                previous=previous_entity,
                status=status,
            )
        )

    return matches


def _is_container(entity: Any) -> bool:
    value = (
        entity.get("entity_type")
        if isinstance(entity, dict)
        else getattr(entity, "entity_type", None)
    )

    if value is None:
        return False

    entity_type = getattr(value, "value", value)
    return str(entity_type).lower() in {
        "module",
        "class",
        "namespace",
    }


class EntityMatcher:
    """Match newly analyzed entities against previously indexed entities."""

    def match(
        self,
        previous: list[Entity],
        current: list[Entity],
    ) -> dict[str, Entity | None]:
        matches = match_entities(
            current=current,
            previous=previous,
        )
        logger.debug(
            "EntityMatcher :: match :: matched %d/%d entities",
            sum(1 for m in matches if m.previous is not None),
            len(current),
        )
        return {match.current.entity_id: match.previous for match in matches}
