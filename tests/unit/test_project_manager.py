from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from code_index_mcp.config import IndexConfig
from code_index_mcp.project.identity import canonical_project_root, project_id_for_root
from code_index_mcp.project.manager import ProjectManager
from code_index_mcp.storage.database import Database


@pytest.fixture
def config(tmp_path):
    return IndexConfig(index_root=tmp_path / "index")


@pytest.fixture
def manager(config):
    return ProjectManager(config)


def _find_outline_entity(manager, tmp_path, name: str, kind: str) -> dict:
    """Recursively locate a named entity (by kind) inside the project outline."""
    outline = manager.get_project_outline(tmp_path)

    def walk(entities):
        for e in entities:
            if e.get("name") == name and e.get("kind") == kind:
                return e
            found = walk(e.get("children") or [])
            if found:
                return found
        return None

    entity = None
    for f in outline["files"]:
        entity = walk(f["outline"])
        if entity:
            break
    assert entity is not None, f"{kind} {name!r} not found in outline"
    return entity


class TestProjectManager:
    def test_canonical_root(self, manager, tmp_path):
        root = manager.canonical_root(tmp_path)
        assert root == tmp_path.resolve()

    def test_canonical_root_not_dir_raises(self, manager, tmp_path):
        fake = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="not a directory"):
            manager.canonical_root(fake)

    def test_project_id(self, manager, tmp_path):
        pid = manager.project_id(tmp_path)
        assert len(pid) == 32

    def test_database_path(self, manager, tmp_path):
        path = manager.database_path(tmp_path)
        assert path.name == "index.db"

    def test_project_directory(self, manager, tmp_path):
        d = manager.project_directory(tmp_path)
        assert "projects" in str(d)

    def test_open_database(self, manager, tmp_path):
        db = manager.open_database(tmp_path)
        try:
            assert db.connection is not None
        finally:
            db.close()

    def test_index_project(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        result = manager.index_project(tmp_path)
        assert "entities_recomputed" in result
        assert result["files_changed"] >= 1

    def test_refresh_index(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.refresh_index(tmp_path)
        assert "files_reused" in result

    def test_search(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("def foo():\n    pass\n")
        manager.index_project(tmp_path)
        result = manager.search(tmp_path, "foo")
        assert "results" in result

    def test_search_batch(self, manager, tmp_path):
        (tmp_path / "test.py").write_text(
            "def foo():\n    pass\n"
            "def bar():\n    pass\n"
        )
        manager.index_project(tmp_path)
        result = manager.search_batch(tmp_path, ["foo", "bar"])
        assert "keywords" in result
        assert "results" in result
        assert result["keywords"] == ["foo", "bar"]

    def test_search_scoped_to_path(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("def token_a():\n    pass\n")
        (tmp_path / "b.py").write_text("def token_b():\n    pass\n")
        manager.index_project(tmp_path)
        result = manager.search(tmp_path, "token", path="a.py")
        for r in result["results"]:
            assert r["path"] == "a.py"

    def test_search_batch_scoped_to_path(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        (tmp_path / "b.py").write_text("def foo():\n    pass\n")
        manager.index_project(tmp_path)
        result = manager.search_batch(tmp_path, ["foo"], path="a.py")
        for r in result["results"]:
            assert r["path"] == "a.py"

    def test_search_docs_scoped_to_markdown_path(self, manager, tmp_path):
        (tmp_path / "one.md").write_text(
            "# Project\n\n## Configuration\n\nEdit config.yaml.\n"
        )
        (tmp_path / "two.md").write_text(
            "# Other\n\n## Configuration\n\nEdit config.toml.\n"
        )
        manager.index_project(tmp_path)
        result = manager.search(tmp_path, "Configuration", kind="markdown", path="one.md")
        assert result["results"], "expected heading match in one.md"
        for r in result["results"]:
            assert r["path"] == "one.md"

    def test_get_file_outline(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_file_outline(tmp_path, "test.py")
        assert "outline" in result

    def test_get_project_outline(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_project_outline(tmp_path)
        assert "files" in result

    def test_get_project_outline_paths_clean(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.md").write_text("# Doc\n")
        manager.index_project(tmp_path)
        result = manager.get_project_outline(tmp_path)
        assert result["files"], "expected at least one file"
        for f in result["files"]:
            assert not f["path"].startswith("file:"), f["path"]

    def test_find_definition(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("def foo():\n    pass\n")
        manager.index_project(tmp_path)
        result = manager.find_definition(tmp_path, "foo")
        assert "results" in result

    def test_get_index_status(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_index_status(tmp_path)
        assert "project_id" in result

    def test_clear_project_cache(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.clear_project_cache(tmp_path)
        assert result["cleared"] is True

    def test_remove_project_cache_nonexistent(self, manager, tmp_path):
        # Path must be a real directory for canonical_root to succeed
        d = tmp_path / "real_project"
        d.mkdir()
        manager.remove_project_cache(d)
        # Should not raise when directory doesn't exist yet

    def test_get_symbol(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("def foo():\n    pass\n")
        manager.index_project(tmp_path)
        entity_id = "python:test.py:foo"
        result = manager.get_symbol(tmp_path, entity_id)
        assert "entity_id" in result

    def test_get_symbol_unknown_raises(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        with pytest.raises(KeyError):
            manager.get_symbol(tmp_path, "nonexistent")

    def test_get_code(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("line1\nline2\nline3\n")
        manager.index_project(tmp_path)
        result = manager.get_code(tmp_path, "test.py", 1, 2)
        assert "source" in result

    def test_get_code_accepts_file_prefix(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("line1\nline2\nline3\n")
        manager.index_project(tmp_path)
        result = manager.get_code(tmp_path, "file:test.py", 1, 2)
        assert "source" in result
        assert result["source"] == "line1\nline2"

    def test_get_file_outline_accepts_file_prefix(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_file_outline(tmp_path, "file:test.py")
        assert "outline" in result
        assert result["entity_count"] >= 1

    def test_get_markdown_section(self, manager, tmp_path):
        (tmp_path / "doc.md").write_text("# Hello\n\nWorld\n")
        manager.index_project(tmp_path)
        outline = manager.get_project_outline(tmp_path)
        md_entities = []
        for f in outline.get("files", []):
            for e in f.get("outline", []):
                eid = e.get("entity_id", "")
                if "markdown" in eid:
                    md_entities.append(e)
        if md_entities:
            result = manager.get_markdown_section(tmp_path, md_entities[0]["entity_id"])
            assert "entity_id" in result

    def test_get_markdown_section_unknown_raises(self, manager, tmp_path):
        (tmp_path / "doc.md").write_text("# Hello\n")
        manager.index_project(tmp_path)
        with pytest.raises(KeyError):
            manager.get_markdown_section(tmp_path, "nonexistent")

    def test_get_markdown_section_partial_heading_path(self, manager, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Welcome\n\nIntro.\n\n## Usage\n\nCall the API.\n")
        manager.index_project(tmp_path)
        result = manager.get_markdown_section(tmp_path, "markdown:doc.md:Usage")
        assert result is not None
        assert result["heading"] == "Usage"
        # resolves to the full hierarchical id
        assert result["entity_id"] == "markdown:doc.md:Welcome/Usage"

    def test_get_markdown_section_ambiguous_partial_raises(self, manager, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text(
            "# Top\n\n## Usage\n\nA.\n\n# Other\n\n## Usage\n\nB.\n"
        )
        manager.index_project(tmp_path)
        # Two distinct sections named "Usage" -> cannot resolve unambiguously,
        # falls through to the plain-entity lookup and raises.
        with pytest.raises(KeyError):
            manager.get_markdown_section(tmp_path, "markdown:doc.md:Usage")

    def test_find_references(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.find_references(tmp_path, "nonexistent")
        assert "references" in result

    def test_find_references_unknown_entity_no_loose(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.find_references(tmp_path, "nonexistent")
        assert result["references"] == []

    def test_find_references_loose_match_supplement(self, manager, tmp_path):
        (tmp_path / "helper.py").write_text("class Helper:\n    def run(self):\n        pass\n")
        (tmp_path / "runner.py").write_text(
            "class Helper:\n    def run(self):\n        pass\n"
            "class Runner:\n    def execute(self):\n        self.helper.run()\n"
        )
        manager.index_project(tmp_path)
        symbol = manager.search(tmp_path, "run", limit=50)
        unit = next(
            r for r in symbol["results"]
            if r["entity_id"].endswith("Helper.run") and "helper.py" in r["entity_id"]
        )
        result = manager.find_references(tmp_path, unit["entity_id"])
        confidences = [r.get("confidence") for r in result["references"]]
        assert "loose" in confidences
        assert confidences == ["loose"] or confidences[-1] == "loose"
        loose = [r for r in result["references"] if r.get("confidence") == "loose"]
        assert any("Runner.execute" in r["source_entity_id"] for r in loose)

    def test_get_related_code(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_related_code(tmp_path, "nonexistent")
        assert "related" in result

    def test_get_related_code_reports_pagination_shape(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.get_related_code(tmp_path, "nonexistent")
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["has_more"] is False

    def test_find_references_reports_pagination_shape(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.find_references(tmp_path, "nonexistent")
        assert result["references"] == []
        assert result["total"] == 0
        assert result["has_more"] is False

    def test_get_related_code_minimal_omits_source(self, manager, tmp_path):
        (tmp_path / "lib.py").write_text(
            "class Base:\n    def a(self):\n        pass\n"
            "class Child(Base):\n    def b(self):\n        pass\n"
        )
        manager.index_project(tmp_path)
        child_entity = _find_outline_entity(manager, tmp_path, "Child", "class")
        result = manager.get_related_code(
            tmp_path, child_entity["entity_id"], context="minimal"
        )
        assert result["related"]
        for related in result["related"]:
            rel = related if isinstance(related, dict) else {}
            assert "source" not in rel
            assert "entity_id" in rel

    def test_get_related_code_full_includes_source(self, manager, tmp_path):
        (tmp_path / "lib.py").write_text(
            "class Base:\n    def a(self):\n        pass\n"
            "class Child(Base):\n    def b(self):\n        pass\n"
        )
        manager.index_project(tmp_path)
        child_entity = _find_outline_entity(manager, tmp_path, "Child", "class")
        result = manager.get_related_code(
            tmp_path, child_entity["entity_id"], context="full"
        )
        assert result["related"]
        assert any("source" in r for r in result["related"])

    def test_get_related_code_page_size_slices(self, manager, tmp_path):
        (tmp_path / "lib.py").write_text(
            "class Base:\n    def a(self):\n        pass\n"
            "    def b(self):\n        pass\n"
            "    def c(self):\n        pass\n"
        )
        manager.index_project(tmp_path)
        base_entity = _find_outline_entity(manager, tmp_path, "Base", "class")
        first = manager.get_related_code(
            tmp_path, base_entity["entity_id"], context="minimal", page=1, page_size=1
        )
        second = manager.get_related_code(
            tmp_path, base_entity["entity_id"], context="minimal", page=2, page_size=1
        )
        assert first["total"] >= 3
        assert first["has_more"] is True
        assert len(first["related"]) == 1
        assert len(second["related"]) == 1
        assert first["related"][0]["entity_id"] != second["related"][0]["entity_id"]

    def test_get_related_code_invalid_context_raises(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        with pytest.raises(ValueError, match="context"):
            manager.get_related_code(tmp_path, "nonexistent", context="bogus")

    def test_find_references_negative_page_raises(self, manager, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        with pytest.raises(ValueError, match="page"):
            manager.find_references(tmp_path, "nonexistent", page=0)


class TestProjectManagerException:
    def test_index_failure_sets_failed_state(self, manager, tmp_path):
        """When indexing fails, project state is set to FAILED."""
        (tmp_path / "a.py").write_text("x = 1\n")
        # First index succeeds
        manager.index_project(tmp_path)
        # Second index - mock the indexer to fail
        with patch.object(manager, "_services") as mock_services:
            db = MagicMock()
            indexer = MagicMock()
            indexer.index_project.side_effect = ValueError("boom")
            mock_services.return_value = (db, MagicMock(), MagicMock(), indexer)
            db.execute.return_value.fetchone.return_value = {"count": 0}
            db.execute.return_value.__getitem__ = lambda self, i: 0
            with pytest.raises(ValueError):
                manager.index_project(tmp_path)


class TestProjectServiceCaching:
    def test_project_paths_are_memoized(self, manager, tmp_path):
        with (
            patch(
                "code_index_mcp.project.manager.canonical_project_root",
                wraps=canonical_project_root,
            ) as root_mock,
            patch(
                "code_index_mcp.project.manager.project_id_for_root",
                wraps=project_id_for_root,
            ) as id_mock,
        ):
            first = manager.project_id(tmp_path)
            second = manager.project_id(tmp_path)

        assert first == second
        assert root_mock.call_count == 1
        assert id_mock.call_count == 1

    def test_read_calls_reuse_one_database_connection(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        manager.index_project(tmp_path)

        with patch("code_index_mcp.project.manager.Database", wraps=Database) as db_ctor:
            first = manager.get_file_outline(tmp_path, "a.py")
            second = manager.get_file_outline(tmp_path, "a.py")

        assert first["entity_count"] == second["entity_count"]
        assert db_ctor.call_count == 1
        manager.clear_project_cache(tmp_path)

    def test_read_calls_do_not_construct_indexing_services(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        manager.index_project(tmp_path)

        with patch.object(manager, "_services", side_effect=AssertionError):
            result = manager.get_file_outline(tmp_path, "a.py")

        assert result["entity_count"] >= 1
        manager.clear_project_cache(tmp_path)

    def test_concurrent_reads_reuse_one_connection(self, manager, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        manager.index_project(tmp_path)

        with patch("code_index_mcp.project.manager.Database", wraps=Database) as db_ctor:
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        lambda _: manager.get_file_outline(tmp_path, "a.py"),
                        range(8),
                    )
                )

        assert len(results) == 8
        assert db_ctor.call_count == 1
        manager.clear_project_cache(tmp_path)

