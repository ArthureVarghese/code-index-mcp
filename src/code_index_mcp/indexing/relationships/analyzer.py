from __future__ import annotations

import ast

from code_index_mcp.indexing.python.relationships import PythonRelationshipAnalyzer
from code_index_mcp.indexing.relationships.models import RelationshipCandidate


class RelationshipAnalyzer:
    """Resolve conservative relationships from indexed Python ASTs."""

    def analyze_python(
        self,
        *,
        module_entity_id: str,
        tree: ast.AST,
        entity_ids_by_qualified_name: dict[str, str],
    ) -> list[RelationshipCandidate]:
        candidates: list[RelationshipCandidate] = []
        seen: set[tuple[str, str, str, str]] = set()

        analyzer = PythonRelationshipAnalyzer()

        for reference in analyzer.analyze(tree):
            target_id = entity_ids_by_qualified_name.get(reference.target_name)

            source_id = entity_ids_by_qualified_name.get(reference.source_name) or module_entity_id

            confidence = "exact" if target_id is not None else reference.confidence

            metadata: dict[str, object] = {}

            if target_id is not None:
                metadata["resolved_target"] = target_id

            dedup_key = (source_id, reference.target_name, reference.kind, str(target_id or ""))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            candidates.append(
                RelationshipCandidate(
                    source_entity_id=source_id,
                    target_name=reference.target_name,
                    relationship_type=reference.kind,
                    confidence=confidence,
                    line=reference.line,
                    metadata=metadata,
                )
            )

        return candidates
