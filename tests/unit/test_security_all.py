from __future__ import annotations

import pytest

from code_index_mcp.config import IndexConfig
from code_index_mcp.security.ignore import IgnoreMatcher
from code_index_mcp.security.paths import (
    PathSecurityError,
    ProjectPathGuard,
)


class TestIgnoreMatcher:
    def test_ignores_excluded_directory(self, tmp_path):
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / ".git" / "config")

    def test_ignores_excluded_file(self, tmp_path):
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / ".env")

    def test_ignores_wrong_extension(self, tmp_path):
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / "image.png")

    def test_accepts_valid_file(self, tmp_path):
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert not matcher.is_ignored(tmp_path / "code.py")

    def test_ignores_outside_root(self, tmp_path):
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path.parent / "other.py")

    def test_gitignore_patterns(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / "debug.log")
        assert matcher.is_ignored(tmp_path / "code.py") is False

    def test_code_index_ignore(self, tmp_path):
        (tmp_path / ".code-index-ignore").write_text("secret.py\n")
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / "secret.py")

    def test_comment_lines_ignored(self, tmp_path):
        (tmp_path / ".gitignore").write_text("# this is a comment\n*.log\n")
        config = IndexConfig()
        matcher = IgnoreMatcher(tmp_path, config)
        assert matcher.is_ignored(tmp_path / "debug.log")

    def test_unicode_decode_error(self, tmp_path):
        (tmp_path / ".gitignore").write_bytes(b"\xff\xfe\n")
        config = IndexConfig()
        # Should not raise
        matcher = IgnoreMatcher(tmp_path, config)
        assert not matcher.is_ignored(tmp_path / "test.py")


class TestProjectPathGuard:
    def test_resolve_relative(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        result = guard.resolve("subdir/file.py")
        assert result == tmp_path / "subdir" / "file.py"

    def test_resolve_absolute_inside(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        target = tmp_path / "file.py"
        result = guard.resolve(str(target))
        assert result == target

    def test_resolve_escapes_raises(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        with pytest.raises(PathSecurityError, match="escapes"):
            guard.resolve("../outside.py")

    def test_relative(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        result = guard.relative(tmp_path / "subdir" / "file.py")
        assert result == "subdir/file.py"

    def test_contains_true(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        assert guard.contains("file.py") is True

    def test_contains_false(self, tmp_path):
        guard = ProjectPathGuard(tmp_path)
        assert guard.contains("../outside.py") is False

    def test_not_a_directory_raises(self, tmp_path):
        fake = tmp_path / "not_a_dir"
        fake.write_text("x")
        with pytest.raises(PathSecurityError):
            ProjectPathGuard(fake)
