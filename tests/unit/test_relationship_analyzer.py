from __future__ import annotations

import ast

from code_index_mcp.indexing.relationships.analyzer import RelationshipAnalyzer
from code_index_mcp.indexing.relationships.models import RelationshipCandidate


class TestRelationshipCandidate:
    def test_creation(self):
        rc = RelationshipCandidate(
            source_entity_id="src",
            target_name="tgt",
            relationship_type="calls",
            confidence="exact",
            line=10,
            metadata={"key": "val"},
        )
        assert rc.source_entity_id == "src"
        assert rc.target_name == "tgt"
        assert rc.relationship_type == "calls"
        assert rc.confidence == "exact"
        assert rc.line == 10
        assert rc.metadata == {"key": "val"}

    def test_defaults(self):
        rc = RelationshipCandidate(
            source_entity_id="s",
            target_name="t",
            relationship_type="r",
            confidence="c",
        )
        assert rc.line is None
        assert rc.metadata == {}


class TestRelationshipAnalyzer:
    def test_analyze_python_resolves_targets(self):
        source = """
def foo():
    bar()
"""
        tree = ast.parse(source)
        entity_ids = {"foo": "entity:foo", "bar": "entity:bar"}
        analyzer = RelationshipAnalyzer()
        candidates = analyzer.analyze_python(
            module_entity_id="module:mod",
            tree=tree,
            entity_ids_by_qualified_name=entity_ids,
        )
        assert len(candidates) > 0
        call_candidates = [c for c in candidates if c.relationship_type == "calls"]
        assert len(call_candidates) == 1
        assert call_candidates[0].metadata.get("resolved_target") == "entity:bar"

    def test_analyze_python_unresolved_target(self):
        source = "foo()\n"
        tree = ast.parse(source)
        analyzer = RelationshipAnalyzer()
        candidates = analyzer.analyze_python(
            module_entity_id="module:mod",
            tree=tree,
            entity_ids_by_qualified_name={},
        )
        # foo() generates both a "calls" and a "references" candidate
        assert len(candidates) >= 1
        assert any(c.confidence == "inferred" for c in candidates)

    def test_analyze_python_import(self):
        source = "import os\n"
        tree = ast.parse(source)
        entity_ids = {"os": "entity:os"}
        analyzer = RelationshipAnalyzer()
        candidates = analyzer.analyze_python(
            module_entity_id="module:mod",
            tree=tree,
            entity_ids_by_qualified_name=entity_ids,
        )
        assert len(candidates) == 1
        assert candidates[0].relationship_type == "imports"

    def test_analyze_python_class_inheritance(self):
        source = "class Foo(Base):\n    pass\n"
        tree = ast.parse(source)
        entity_ids = {"Base": "entity:Base", "Foo": "entity:Foo"}
        analyzer = RelationshipAnalyzer()
        candidates = analyzer.analyze_python(
            module_entity_id="module:mod",
            tree=tree,
            entity_ids_by_qualified_name=entity_ids,
        )
        inherits = [c for c in candidates if c.relationship_type == "inherits"]
        assert len(inherits) == 1

    def test_analyze_python_source_fallback(self):
        # Use a source that produces references (Name in Load context)
        source = "print(x)\n"
        tree = ast.parse(source)
        analyzer = RelationshipAnalyzer()
        candidates = analyzer.analyze_python(
            module_entity_id="module:mod",
            tree=tree,
            entity_ids_by_qualified_name={},
        )
        assert len(candidates) > 0
        assert all(c.source_entity_id == "module:mod" for c in candidates)
