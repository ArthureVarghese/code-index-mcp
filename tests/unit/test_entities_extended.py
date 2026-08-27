from __future__ import annotations

import pytest

from code_index_mcp.models.entities import (
    Entity,
    EntityType,
    Relationship,
    RelationshipConfidence,
    RelationshipKind,
    SourceKind,
    SourceRange,
)


def _make_entity(**overrides):
    defaults = dict(
        entity_id="e1",
        project_id="p1",
        file_id="f1",
        source_kind=SourceKind.PYTHON,
        entity_type=EntityType.FUNCTION,
        name="foo",
        qualified_name="foo",
        parent_id=None,
        source_range=SourceRange(start_line=1, end_line=1, start_column=0, end_column=6),
        content_hash="hash1",
        exact_source_hash="exact1",
        semantic_hash="sem1",
        structural_hash="struct1",
        source="def foo(): pass",
    )
    defaults.update(overrides)
    return Entity(**defaults)


class TestSourceRange:
    def test_valid(self):
        sr = SourceRange(1, 5, 0, 10)
        assert sr.start_line == 1

    def test_start_line_zero_raises(self):
        with pytest.raises(ValueError, match="start_line"):
            SourceRange(0, 5, 0, 10)

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="end_line"):
            SourceRange(5, 1, 0, 10)

    def test_negative_column_raises(self):
        with pytest.raises(ValueError, match="columns"):
            SourceRange(1, 5, -1, 10)

    def test_to_dict(self):
        sr = SourceRange(1, 5, 0, 10)
        d = sr.to_dict()
        assert d["start_line"] == 1
        assert d["end_column"] == 10


class TestEntity:
    def test_properties(self):
        e = _make_entity()
        assert e.name == "foo"
        assert e.start_line == 1
        assert e.end_line == 1
        assert e.start_column == 0
        assert e.end_column == 6

    def test_to_dict(self):
        e = _make_entity()
        d = e.to_dict()
        assert d["entity_id"] == "e1"
        assert d["entity_type"] == "function"
        assert d["source_kind"] == "python"

    def test_with_docstring(self):
        e = _make_entity(docstring="My docstring")
        assert e.docstring == "My docstring"

    def test_with_decorators(self):
        e = _make_entity(decorators=("@staticmethod",))
        assert e.decorators == ("@staticmethod",)


class TestRelationship:
    def test_to_dict(self):
        r = Relationship(
            relationship_id="r1",
            project_id="p1",
            source_entity_id="e1",
            target_entity_id="e2",
            kind=RelationshipKind.CALLS,
            confidence=RelationshipConfidence.EXACT,
        )
        d = r.to_dict()
        assert d["kind"] == "calls"
        assert d["confidence"] == "exact"

    def test_with_metadata(self):
        r = Relationship(
            relationship_id="r1",
            project_id="p1",
            source_entity_id="e1",
            target_entity_id=None,
            kind=RelationshipKind.IMPORTS,
            confidence=RelationshipConfidence.INFERRED,
            metadata={"key": "val"},
        )
        assert r.metadata == {"key": "val"}
