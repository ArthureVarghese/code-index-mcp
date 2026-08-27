from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.indexing.manager import (
    IndexManager,
    _entity_hash,
    _entity_id,
    _entity_type,
)
from code_index_mcp.indexing.markdown.analyzer import MarkdownAnalyzer
from code_index_mcp.indexing.python.analyzer import PythonAnalyzer
from code_index_mcp.models.entities import Entity, EntityType, SourceKind


@pytest.fixture
def index_manager(tmp_path):
    db = MagicMock()
    repos = MagicMock()
    repos.get_file.return_value = None
    repos.get_entities_for_file.return_value = []
    python_analyzer = PythonAnalyzer()
    markdown_analyzer = MarkdownAnalyzer()
    return IndexManager(db, python_analyzer, markdown_analyzer, repos)


class TestIndexFileException:
    def test_exception_recorded_in_stats(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        # Make get_file raise to trigger exception path
        repos.get_file.side_effect = RuntimeError("db error")
        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("x = 1\n")
        result = pm.index_project(tmp_path)
        assert len(result["errors"]) >= 1
        assert "db error" in result["errors"][0]["error"]


class TestDiscoverFiles:
    def test_symlink_excluded(self, tmp_path):
        real = tmp_path / "real.py"
        real.write_text("x = 1\n")
        link = tmp_path / "link.py"
        link.symlink_to(real)
        db = MagicMock()
        repos = MagicMock()
        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        files = pm._discover_files(tmp_path)
        assert real in files
        assert link not in files

    def test_non_python_excluded(self, tmp_path):
        (tmp_path / "data.txt").write_text("hello\n")
        (tmp_path / "code.py").write_text("x = 1\n")
        db = MagicMock()
        repos = MagicMock()
        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        files = pm._discover_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "code.py"


class TestEntityReuse:
    def test_unchanged_hash_reuses_entity(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        from code_index_mcp.indexing.hashing import sha256_text

        content = "x = 1\n"
        file_hash = sha256_text(content)
        repos.get_file.return_value = {"content_hash": file_hash}
        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text(content)
        result = pm.index_project(tmp_path)
        assert result["files_reused"] >= 1


class TestDeleteOldEntities:
    def test_removed_entity_deleted(self, tmp_path):
        db = MagicMock()
        repos = MagicMock()
        repos.get_file.return_value = None
        from code_index_mcp.models.entities import SourceRange
        old_entity = Entity(
            entity_id="file:a.py::function:old_func",
            project_id="proj",
            file_id="file:a.py",
            source_kind=SourceKind.PYTHON,
            entity_type=EntityType.FUNCTION,
            name="old_func",
            qualified_name="old_func",
            parent_id=None,
            source_range=SourceRange(start_line=1, end_line=2, start_column=0, end_column=13),
            content_hash="old",
            exact_source_hash="old",
            semantic_hash="old",
            structural_hash="old",
            source="def old_func(): pass",
        )
        repos.get_entities_for_file.return_value = [old_entity]
        pm = IndexManager(db, PythonAnalyzer(), MarkdownAnalyzer(), repos)
        (tmp_path / "a.py").write_text("def new_func(): pass\n")
        pm.index_project(tmp_path)
        repos.delete_entity.assert_called()


class TestHelperFunctions:
    def test_entity_id_dict(self):
        assert _entity_id({"entity_id": "e1"}) == "e1"

    def test_entity_id_object(self):
        obj = MagicMock()
        obj.entity_id = "e2"
        assert _entity_id(obj) == "e2"

    def test_entity_hash_dict(self):
        assert _entity_hash({"content_hash": "h1"}) == "h1"

    def test_entity_hash_none(self):
        d = {}
        assert _entity_hash(d) is None

    def test_entity_hash_object(self):
        obj = MagicMock()
        obj.content_hash = "h2"
        assert _entity_hash(obj) == "h2"

    def test_entity_type_dict(self):
        assert _entity_type({"entity_type": "function"}) == "function"

    def test_entity_type_object_with_value(self):
        obj = MagicMock()
        obj.entity_type.value = "class"
        assert _entity_type(obj) == "class"

    def test_entity_type_none(self):
        assert _entity_type({}) == ""

    def test_entity_type_object_no_value(self):
        obj = MagicMock(spec=[])  # no entity_type attribute
        assert _entity_type(obj) == ""


class TestCanReuseEntity:
    def test_same_hash_reused(self):
        entity = MagicMock()
        entity.content_hash = "h1"
        assert IndexManager._can_reuse_entity(entity, entity) is True

    def test_module_always_reused(self):
        old = MagicMock()
        old.content_hash = "old"
        new = MagicMock()
        new.content_hash = "new"
        new.entity_type = "module"
        assert IndexManager._can_reuse_entity(old, new) is True

    def test_class_always_reused(self):
        old = MagicMock()
        old.content_hash = "old"
        new = MagicMock()
        new.content_hash = "new"
        new.entity_type = "class"
        assert IndexManager._can_reuse_entity(old, new) is True

    def test_function_not_reused(self):
        old = MagicMock()
        old.content_hash = "old"
        new = MagicMock()
        new.content_hash = "new"
        new.entity_type = "function"
        assert IndexManager._can_reuse_entity(old, new) is False
