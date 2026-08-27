import pytest

from code_index_mcp.security.paths import PathSecurityError, ProjectPathGuard


def test_rejects_parent_traversal(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    guard = ProjectPathGuard(root)
    with pytest.raises(PathSecurityError):
        guard.resolve("../secret.txt")


def test_accepts_file_inside_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    file = root / "src.py"
    file.write_text("x = 1")

    guard = ProjectPathGuard(root)
    assert guard.resolve("src.py") == file.resolve()
