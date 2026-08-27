from __future__ import annotations

from typing import Any

_MINIMAL_KEYS = (
    "entity_id",
    "path",
    "entity_type",
    "name",
    "start_line",
    "end_line",
)
_NORMAL_KEYS = (
    *_MINIMAL_KEYS,
    "qualified_name",
    "signature",
    "docstring",
    "source_kind",
)


def project_entity(entity: dict[str, Any], level: str) -> dict[str, Any]:
    """Project an entity down to a verbosity level.

    Used to bound how much of a *nested* entity (parent, children, siblings) is
    returned so list/context tools don't dump the full source of every related
    symbol:

      - "minimal": identity + location only (entity_id, name, kind, path, lines)
      - "normal":  adds qualified name, signature, docstring (no source text)
      - "full":    every field, including the raw ``source`` text
    """
    if level not in ("minimal", "normal", "full"):
        raise ValueError(
            f"Invalid verbosity level {level!r}; expected 'minimal', 'normal' or 'full'"
        )
    if level == "minimal":
        return {k: entity.get(k) for k in _MINIMAL_KEYS}
    if level == "normal":
        return {k: entity.get(k) for k in _NORMAL_KEYS}
    return dict(entity)


class ContextBuilder:
    """Building bounded retrieval context from indexed entities."""

    def __init__(self, repositories: Any):
        self.repositories = repositories

    def build(
        self,
        entity: dict[str, Any],
        *,
        depth: str = "normal",
    ) -> dict[str, Any]:
        result = dict(entity)

        # Map "full" to "expanded" for backward compatibility
        if depth == "full":
            depth = "expanded"

        if depth not in ("minimal", "normal", "expanded"):
            raise ValueError(
                f"Invalid context/depth value {depth!r}; expected one of "
                "'minimal', 'normal', 'expanded' (or 'full' alias)"
            )

        if depth == "minimal":
            return {
                key: result.get(key)
                for key in _MINIMAL_KEYS
            }

        parent = self.repositories.get_parent(entity["entity_id"])
        result["parent"] = (
            project_entity(parent, "full" if depth == "expanded" else "normal")
            if parent
            else None
        )

        if depth == "expanded":
            all_relationships = self.repositories.get_relationships(entity["entity_id"])

            callers = [
                r for r in all_relationships
                if r.get("target_entity_id") == entity["entity_id"]
                and r.get("relationship_kind") in ("calls", "references")
            ]
            callees = [
                r for r in all_relationships
                if r.get("source_entity_id") == entity["entity_id"]
                and r.get("relationship_kind") in ("calls", "references")
            ]
            imports = [
                r for r in all_relationships
                if r.get("source_entity_id") == entity["entity_id"]
                and r.get("relationship_kind") == "imports"
            ]
            inherits = [
                r for r in all_relationships
                if r.get("source_entity_id") == entity["entity_id"]
                and r.get("relationship_kind") == "inherits"
            ]

            result["callers"] = callers
            result["callees"] = callees
            result["imports"] = imports
            result["inherits"] = inherits
            result["children"] = [
                project_entity(c, "full")
                for c in self.repositories.get_children(entity["entity_id"])
            ]

        return result
