from __future__ import annotations

from code_index_mcp.project.identity import (
    canonical_project_root,
    project_id_for_root,
)


class TestIdentity:
    def test_canonical_project_root(self, tmp_path):
        result = canonical_project_root(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_project_id_for_root_deterministic(self, tmp_path):
        id1 = project_id_for_root(tmp_path)
        id2 = project_id_for_root(tmp_path)
        assert id1 == id2

    def test_project_id_is_32_hex(self, tmp_path):
        pid = project_id_for_root(tmp_path)
        assert len(pid) == 32
        int(pid, 16)  # Should not raise

    def test_different_roots_different_ids(self, tmp_path):
        a = project_id_for_root(tmp_path / "a")
        b = project_id_for_root(tmp_path / "b")
        assert a != b
