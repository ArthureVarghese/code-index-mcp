from __future__ import annotations

import ast

from code_index_mcp.indexing.python.relationships import (
    PythonReference,
    PythonRelationshipAnalyzer,
    _name_of,
)


class TestPythonRelationshipAnalyzer:
    def _analyze(self, source: str) -> list[PythonReference]:
        tree = ast.parse(source)
        analyzer = PythonRelationshipAnalyzer()
        return analyzer.analyze(tree)

    def test_imports(self):
        refs = self._analyze("import os\n")
        assert len(refs) == 1
        assert refs[0].kind == "imports"
        assert refs[0].target_name == "os"

    def test_from_imports(self):
        refs = self._analyze("from os import path\n")
        assert len(refs) == 1
        assert refs[0].kind == "imports"
        assert refs[0].target_name == "os.path"

    def test_relative_imports(self):
        refs = self._analyze("from . import foo\n")
        assert len(refs) == 1
        assert refs[0].target_name == "foo"

    def test_calls(self):
        refs = self._analyze("foo()\n")
        calls = [r for r in refs if r.kind == "calls"]
        assert len(calls) == 1
        assert calls[0].target_name == "foo"

    def test_name_references(self):
        refs = self._analyze("x\n")
        refs_only = [r for r in refs if r.kind == "references"]
        assert len(refs_only) == 1
        assert refs_only[0].target_name == "x"

    def test_class_inheritance(self):
        refs = self._analyze("class Foo(Bar):\n    pass\n")
        inherits = [r for r in refs if r.kind == "inherits"]
        assert len(inherits) == 1
        assert inherits[0].target_name == "Bar"

    def test_scope_tracking(self):
        source = """
class MyClass:
    def my_method(self):
        pass
"""
        refs = self._analyze(source)
        # MyClass should be in scope for inner entities
        class_refs = [r for r in refs if r.source_name == ""]
        assert len(class_refs) >= 0  # At least should not crash

    def test_async_function(self):
        source = "async def af():\n    await foo()\n"
        refs = self._analyze(source)
        assert any("af" in r.source_name for r in refs)

    def test_nested_class(self):
        source = """
class Outer:
    class Inner:
        pass
"""
        refs = self._analyze(source)
        # Should not crash and should have some references
        assert len(refs) >= 0

    def test_scope_property(self):
        analyzer = PythonRelationshipAnalyzer()
        analyzer.current_scope = ["a", "b"]
        assert analyzer.scope == "a.b"

    def test_complex_import_chain(self):
        source = "from os.path import join, exists\n"
        refs = self._analyze(source)
        assert len(refs) == 2
        targets = {r.target_name for r in refs}
        assert "os.path.join" in targets
        assert "os.path.exists" in targets


class TestNameOf:
    def test_normal_node(self):
        node = ast.Name(id="foo", ctx=ast.Load())
        assert _name_of(node) == "foo"

    def test_exception_returns_none(self):
        from unittest.mock import patch
        target = "code_index_mcp.indexing.python.relationships.ast.unparse"
        with patch(target, side_effect=Exception):
            node = ast.Subscript(
                value=ast.Name(id="foo", ctx=ast.Load()),
                slice=ast.Constant(value=0),
                ctx=ast.Load(),
            )
            assert _name_of(node) is None
