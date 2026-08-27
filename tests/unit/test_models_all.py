from __future__ import annotations

from code_index_mcp.models.entities import Relationship, RelationshipConfidence


class TestModelsRelationships:
    def test_relationship_creation(self):
        r = Relationship(
            relationship_id="rel:1",
            project_id="proj:1",
            source_entity_id="src",
            target_entity_id="tgt",
            kind="calls",
            confidence=RelationshipConfidence.EXACT,
        )
        assert r.source_entity_id == "src"
        assert r.target_entity_id == "tgt"
        assert r.kind == "calls"

    def test_relationship_defaults(self):
        r = Relationship(
            relationship_id="rel:2",
            project_id="proj:1",
            source_entity_id="a",
            target_entity_id="b",
            kind="imports",
            confidence=RelationshipConfidence.EXACT,
        )
        assert r.confidence == RelationshipConfidence.EXACT
        assert r.metadata == {}

    def test_relationship_with_metadata(self):
        r = Relationship(
            relationship_id="rel:3",
            project_id="proj:1",
            source_entity_id="a",
            target_entity_id="b",
            kind="calls",
            confidence=RelationshipConfidence.EXACT,
            metadata={"key": "value"},
        )
        assert r.metadata == {"key": "value"}
