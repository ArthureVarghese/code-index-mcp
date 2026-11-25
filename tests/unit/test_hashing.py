import ast
from unittest.mock import patch

from code_index_mcp.indexing.hashing import (
    _normalize_fallback,
    normalize_python_source,
    semantic_hash,
    semantic_hash_ast,
    sha256_text,
)


def test_sha256_is_deterministic():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")


def test_semantic_hash_ignores_irrelevant_formatting():
    first = "def f():\n    return 1\n"
    second = "def f():\n\n    return 1\n"

    assert semantic_hash(first) == semantic_hash(second)


def test_semantic_hash_ast_ignores_formatting_and_nesting():
    first = ast.parse("class C:\n    def f(self):\n        return 1\n")
    second = ast.parse("class C:\n\n    def f(self):\n        return 1\n")

    first_node = first.body[0].body[0]
    second_node = second.body[0].body[0]

    assert semantic_hash_ast(first, "") == semantic_hash_ast(second, "")
    assert semantic_hash_ast(first_node, "") == semantic_hash_ast(second_node, "")


class TestNormalizePythonSource:
    def test_syntax_error_returns_fallback(self):
        result = normalize_python_source("def bad(:\n")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ast_dump_exception_returns_fallback(self):
        with patch("code_index_mcp.indexing.hashing.ast.dump", side_effect=Exception("boom")):
            result = normalize_python_source("x = 1\n")
        assert isinstance(result, str)
        assert "x = 1" in result

    def test_syntax_error_value_error_type_error(self):
        for src in ["", ">>>", "\x00\x01"]:
            result = normalize_python_source(src)
            assert isinstance(result, str)


class TestNormalizeFallback:
    def test_blank_lines_skipped(self):
        result = _normalize_fallback("a = 1\n\n\nb = 2\n")
        assert result == "a = 1\nb = 2"

    def test_comment_lines_skipped(self):
        result = _normalize_fallback("# comment\na = 1\n# another\n")
        assert result == "a = 1"

    def test_whitespace_collapsed(self):
        result = _normalize_fallback("x  =   1\n")
        assert result == "x = 1"
