from __future__ import annotations

import ast
from unittest.mock import patch

from code_index_mcp.indexing.python.analyzer import (
    PythonAnalyzer,
    PythonParseResult,
    _expression_source,
    _signature,
)


class TestPythonAnalyzer:
    def setup_method(self):
        self.analyzer = PythonAnalyzer()

    def test_module_entity(self):
        result = self.analyzer.analyze("x = 1\n", "test.py")
        assert len(result.entities) >= 1
        module = result.entities[0]
        assert module.entity_type.value == "module"
        assert module.name == "test"

    def test_function_entity(self):
        source = "def foo():\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        funcs = [e for e in result.entities if e.name == "foo"]
        assert len(funcs) == 1
        assert funcs[0].entity_type.value == "function"

    def test_class_entity(self):
        source = "class MyClass:\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        classes = [e for e in result.entities if e.name == "MyClass"]
        assert len(classes) == 1
        assert classes[0].entity_type.value == "class"

    def test_method_entity(self):
        source = "class MyClass:\n    def method(self):\n        pass\n"
        result = self.analyzer.analyze(source, "test.py")
        methods = [e for e in result.entities if e.name == "method"]
        assert len(methods) == 1
        assert methods[0].entity_type.value == "method"

    def test_constructor(self):
        source = "class MyClass:\n    def __init__(self):\n        pass\n"
        result = self.analyzer.analyze(source, "test.py")
        inits = [e for e in result.entities if e.name == "__init__"]
        assert len(inits) == 1
        assert inits[0].entity_type.value == "constructor"

    def test_async_function(self):
        source = "async def af():\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        async_funcs = [e for e in result.entities if e.name == "af"]
        assert len(async_funcs) == 1
        assert async_funcs[0].entity_type.value == "async_function"

    def test_async_method(self):
        source = "class C:\n    async def am(self):\n        pass\n"
        result = self.analyzer.analyze(source, "test.py")
        methods = [e for e in result.entities if e.name == "am"]
        assert len(methods) == 1
        assert methods[0].entity_type.value == "method"

    def test_syntax_error_returns_error(self):
        result = self.analyzer.analyze("def\n", "test.py")
        assert result.syntax_error is not None
        assert len(result.entities) == 0

    def test_syntax_error_in_errors_property(self):
        result = PythonParseResult(entities=[], syntax_error="err")
        assert len(result.errors) == 1

    def test_no_syntax_error_errors_empty(self):
        result = PythonParseResult(entities=[], syntax_error=None)
        assert result.errors == []

    def test_nested_class(self):
        source = "def outer():\n    class Inner:\n        pass\n"
        result = self.analyzer.analyze(source, "test.py")
        nested = [e for e in result.entities if e.name == "Inner"]
        assert len(nested) == 1
        assert nested[0].entity_type.value == "nested_class"

    def test_decorators(self):
        source = "@staticmethod\ndef foo():\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        funcs = [e for e in result.entities if e.name == "foo"]
        assert len(funcs) == 1
        assert len(funcs[0].decorators) >= 1

    def test_docstring(self):
        source = 'def foo():\n    """My docstring."""\n    pass\n'
        result = self.analyzer.analyze(source, "test.py")
        funcs = [e for e in result.entities if e.name == "foo"]
        assert funcs[0].docstring == "My docstring."

    def test_module_docstring(self):
        source = '"""Module docstring."""\nx = 1\n'
        result = self.analyzer.analyze(source, "test.py")
        module = result.entities[0]
        assert module.docstring == "Module docstring."

    def test_custom_file_id(self):
        result = self.analyzer.analyze("x = 1\n", "test.py", file_id="custom")
        assert result.entities[0].file_id == "custom"

    def test_default_file_id(self):
        result = self.analyzer.analyze("x = 1\n", "test.py")
        assert result.entities[0].file_id == "test.py"

    def test_test_function_metadata(self):
        source = "def test_something():\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        test_funcs = [e for e in result.entities if e.name == "test_something"]
        assert test_funcs[0].metadata.get("is_test") is True

    def test_signature(self):
        source = "def foo(a, b):\n    pass\n"
        result = self.analyzer.analyze(source, "test.py")
        funcs = [e for e in result.entities if e.name == "foo"]
        assert funcs[0].signature is not None
        assert "foo" in funcs[0].signature

    def test_empty_source(self):
        result = self.analyzer.analyze("", "test.py")
        assert len(result.entities) == 1  # Just the module


class TestMakeEntityNone:
    def test_non_entity_node_returns_none(self):
        analyzer = PythonAnalyzer()
        source = "x = 1\n"
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr):
                result = analyzer._make_entity(
                    node, "file:test.py", "mod", source,
                    source.splitlines(keepends=True), None,
                )
                assert result is None
                break


class TestExpressionSource:
    def test_ast_get_source_segment_fails(self):
        node = ast.Constant(value=42)
        result = _expression_source("x = 1\n", node)
        assert isinstance(result, str)

    def test_both_fail(self):
        node = ast.Constant(value=42)
        seg = "code_index_mcp.indexing.python.analyzer.ast.get_source_segment"
        unp = "code_index_mcp.indexing.python.analyzer.ast.unparse"
        with patch(seg, side_effect=Exception), \
             patch(unp, side_effect=Exception):
            result = _expression_source("x = 1\n", node)
        assert result == "Constant"


class TestSignature:
    def test_unparse_fails_returns_name(self):
        node = ast.parse("def foo(): pass\n").body[0]
        with patch("code_index_mcp.indexing.python.analyzer.ast.unparse", side_effect=Exception):
            result = _signature(node)
        assert result == "foo"

    def test_non_function_returns_none(self):
        node = ast.parse("x = 1\n").body[0]
        result = _signature(node)
        assert result is None
