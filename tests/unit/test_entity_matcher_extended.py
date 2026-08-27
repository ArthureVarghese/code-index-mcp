from __future__ import annotations

from code_index_mcp.indexing.entity_matcher import (
    EntityMatcher,
    logical_entity_key,
    match_entities,
)
from code_index_mcp.models.entities import (
    Entity,
    EntityType,
    SourceKind,
    SourceRange,
)


def _make_entity(
    entity_id,
    qualified_name="foo",
    entity_type=EntityType.FUNCTION,
    content_hash="hash1",
    source_kind=SourceKind.PYTHON,
    file_id="f1",
):
    return Entity(
        entity_id=entity_id,
        project_id="p1",
        file_id=file_id,
        source_kind=source_kind,
        entity_type=entity_type,
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        parent_id=None,
        source_range=SourceRange(1, 1, 0, 6),
        content_hash=content_hash,
        exact_source_hash="e1",
        semantic_hash="s1",
        structural_hash="st1",
        source="code",
    )


class TestLogicalEntityKey:
    def test_key_generation(self):
        e = _make_entity("e1", qualified_name="mod.foo")
        key = logical_entity_key(e)
        assert "python" in key
        assert "f1" in key
        assert "mod.foo" in key
        assert "function" in key


class TestMatchEntities:
    def test_new_entity(self):
        current = [_make_entity("e1")]
        matches = match_entities(current, [])
        assert len(matches) == 1
        assert matches[0].status == "new"
        assert matches[0].previous is None

    def test_unchanged_entity(self):
        old = _make_entity("e1", content_hash="h1")
        current = [_make_entity("e1", content_hash="h1")]
        matches = match_entities(current, [old])
        assert matches[0].status == "unchanged"

    def test_changed_entity(self):
        old = _make_entity("e1", content_hash="h1")
        current = [_make_entity("e1", content_hash="h2")]
        matches = match_entities(current, [old])
        assert matches[0].status == "changed"

    def test_container_unchanged(self):
        old = _make_entity("e1", content_hash="h1", entity_type=EntityType.CLASS)
        current = [_make_entity("e1", content_hash="h2", entity_type=EntityType.CLASS)]
        matches = match_entities(current, [old])
        assert matches[0].status == "unchanged"


class TestEntityMatcher:
    def test_match(self):
        matcher = EntityMatcher()
        old = [_make_entity("e1", content_hash="h1")]
        current = [_make_entity("e1", content_hash="h1")]
        result = matcher.match(old, current)
        assert "e1" in result
        assert result["e1"] is not None

    def test_match_new(self):
        matcher = EntityMatcher()
        result = matcher.match([], [_make_entity("e1")])
        assert result["e1"] is None
