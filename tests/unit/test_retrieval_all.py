from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.retrieval.context import ContextBuilder, project_entity
from code_index_mcp.retrieval.engine import RetrievalEngine


class TestProjectEntity:
    ENTITY = {
        "entity_id": "e1",
        "path": "a.py",
        "entity_type": "function",
        "name": "foo",
        "start_line": 1,
        "end_line": 5,
        "qualified_name": "mod.foo",
        "signature": "def foo(): ...",
        "docstring": "Does stuff",
        "source_kind": "python",
        "source": "def foo(): pass",
        "metadata": {"k": "v"},
    }

    def test_minimal(self):
        result = project_entity(self.ENTITY, "minimal")
        assert set(result.keys()) == {
            "entity_id", "path", "entity_type", "name",
            "start_line", "end_line",
        }
        assert result["entity_id"] == "e1"

    def test_normal_omits_source(self):
        result = project_entity(self.ENTITY, "normal")
        assert "source" not in result
        assert "metadata" not in result
        assert result["signature"] == "def foo(): ..."
        assert result["docstring"] == "Does stuff"

    def test_full_includes_source(self):
        result = project_entity(self.ENTITY, "full")
        assert result["source"] == "def foo(): pass"
        assert result["metadata"] == {"k": "v"}

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Invalid verbosity"):
            project_entity(self.ENTITY, "bogus")


class TestNestedVerbosityInContext:
    def test_normal_project_does_not_include_parent_source(self):
        repos = MagicMock()
        repos.get_parent.return_value = {
            "entity_id": "parent",
            "name": "Container",
            "entity_type": "class",
            "path": "a.py",
            "start_line": 1,
            "end_line": 9,
            "source": "class Container:\n    pass\n",
            "metadata": {"x": 1},
        }
        builder = ContextBuilder(repos)
        result = builder.build({"entity_id": "e1"}, depth="normal")
        assert result["parent"]["entity_id"] == "parent"
        assert "source" not in result["parent"]
        assert "metadata" not in result["parent"]

    def test_expanded_children_keep_source(self):
        repos = MagicMock()
        repos.get_parent.return_value = None
        repos.get_relationships.return_value = []
        repos.get_children.return_value = [
            {"entity_id": "c1", "name": "meth", "entity_type": "method",
             "path": "a.py", "start_line": 2, "end_line": 4,
             "source": "def meth(): pass", "metadata": {"y": 2}},
        ]
        builder = ContextBuilder(repos)
        result = builder.build({"entity_id": "e1"}, depth="expanded")
        assert result["children"][0]["entity_id"] == "c1"
        assert result["children"][0]["source"] == "def meth(): pass"


class TestContextBuilder:
    def test_minimal_depth(self):
        repos = MagicMock()
        builder = ContextBuilder(repos)
        entity = {
            "entity_id": "e1",
            "path": "a.py",
            "entity_type": "function",
            "name": "foo",
            "start_line": 1,
            "end_line": 5,
            "source": "def foo(): pass",
            "extra_field": "ignored",
        }
        result = builder.build(entity, depth="minimal")
        assert "entity_id" in result
        assert "source" not in result
        assert "extra_field" not in result

    def test_normal_depth(self):
        repos = MagicMock()
        repos.get_parent.return_value = None
        builder = ContextBuilder(repos)
        entity = {"entity_id": "e1", "name": "foo"}
        result = builder.build(entity, depth="normal")
        assert "parent" in result
        repos.get_parent.assert_called_once_with("e1")

    def test_expanded_depth(self):
        repos = MagicMock()
        repos.get_parent.return_value = {"entity_id": "parent"}
        repos.get_relationships.return_value = []
        repos.get_children.return_value = []
        builder = ContextBuilder(repos)
        entity = {"entity_id": "e1", "name": "foo"}
        result = builder.build(entity, depth="expanded")
        assert "callers" in result
        assert "callees" in result
        assert "imports" in result
        assert "inherits" in result
        assert "children" in result
        assert "parent" in result

    @pytest.mark.parametrize("depth", ["", "full ", "bogus", "expanded ", "normal-ish", 3])
    def test_invalid_depth_raises(self, depth):
        repos = MagicMock()
        builder = ContextBuilder(repos)
        entity = {"entity_id": "e1", "name": "foo"}
        with pytest.raises(ValueError, match="Invalid context/depth"):
            builder.build(entity, depth=depth)


class TestRetrievalEngine:
    def test_get_symbol(self):
        repos = MagicMock()
        repos.get_entity.return_value = {"entity_id": "e1", "name": "foo"}
        repos.get_parent.return_value = None
        engine = RetrievalEngine(repos)
        result = engine.get_symbol(
            __import__("pathlib").Path("/"), "e1"
        )
        assert result["entity_id"] == "e1"

    def test_get_symbol_not_found(self):
        repos = MagicMock()
        repos.get_entity.return_value = None
        engine = RetrievalEngine(repos)
        with pytest.raises(KeyError, match="Unknown entity"):
            engine.get_symbol(__import__("pathlib").Path("/"), "missing")

    def test_get_code(self):
        repos = MagicMock()
        repos.get_file_region.return_value = {"source": "code"}
        engine = RetrievalEngine(repos)
        result = engine.get_code(__import__("pathlib").Path("/"), "a.py", 1, 10)
        assert result["source"] == "code"

    def test_get_markdown_section(self):
        repos = MagicMock()
        repos.get_markdown_section.return_value = {"entity_id": "m1"}
        repos.get_parent.return_value = None
        engine = RetrievalEngine(repos)
        result = engine.get_markdown_section("m1")
        assert result["entity_id"] == "m1"

    def test_get_markdown_section_not_found(self):
        repos = MagicMock()
        repos.get_markdown_section.return_value = None
        engine = RetrievalEngine(repos)
        with pytest.raises(KeyError, match="Unknown Markdown section"):
            engine.get_markdown_section("missing")
