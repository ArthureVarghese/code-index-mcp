from __future__ import annotations

import pytest

from code_index_mcp.config import IndexConfig
from code_index_mcp.project.manager import ProjectManager


@pytest.fixture
def config(tmp_path):
    return IndexConfig(index_root=tmp_path / "index")


@pytest.fixture
def manager(config):
    return ProjectManager(config)


class TestEndToEndIndexSearchRetrieve:
    """End-to-end tests covering the full index -> search -> retrieve cycle."""

    def test_full_python_cycle(self, manager, tmp_path):
        source = '''"""Module docstring."""


class Service:
    """A service class."""

    def __init__(self, name):
        self.name = name

    def greet(self):
        """Return a greeting."""
        return f"Hello, {self.name}"

    async def fetch(self):
        """Async fetch."""
        return 42


def standalone():
    """A standalone function."""
    return "standalone"
'''
        (tmp_path / "service.py").write_text(source)
        (tmp_path / "utils.py").write_text("def helper():\n    return True\n")

        # Index
        result = manager.index_project(tmp_path)
        assert result["files_changed"] >= 2
        assert result["entities_recomputed"] >= 1

        # Search
        search_result = manager.search(tmp_path, "Service")
        assert search_result["total"] >= 1

        # Search for standalone
        search_result2 = manager.search(tmp_path, "standalone")
        assert search_result2["total"] >= 1

        # Project outline
        outline = manager.get_project_outline(tmp_path)

        def _count_nodes(nodes):
            return sum(1 + _count_nodes(n.get("children", [])) for n in nodes)

        total_entities = sum(
            _count_nodes(f.get("outline", []))
            for f in outline.get("files", [])
        )
        assert total_entities >= 3

        # File outline
        file_outline = manager.get_file_outline(tmp_path, "service.py")
        assert file_outline["entity_count"] >= 4  # module + class + methods

        # Get symbol
        symbol = manager.get_symbol(tmp_path, "python:service.py:Service.greet")
        assert "source" in symbol

        # Get code
        code = manager.get_code(tmp_path, "service.py", 1, 5)
        assert "source" in code

        # Get index status
        status = manager.get_index_status(tmp_path)
        assert status["indexed_files"] >= 2

    def test_incremental_reindex(self, manager, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        first = manager.index_project(tmp_path)
        assert first["files_changed"] >= 1

        # Change the file
        (tmp_path / "code.py").write_text("x = 2\n")
        second = manager.refresh_index(tmp_path)
        assert second["files_changed"] >= 1

    def test_full_markdown_cycle(self, manager, tmp_path):
        md = """# Getting Started

This is the introduction.

## Installation

Run pip install.

### From Source

Clone the repo.

## Usage

Just use it.
"""
        (tmp_path / "docs.md").write_text(md)
        result = manager.index_project(tmp_path)
        assert result["files_changed"] >= 1

        # Search for markdown content
        search = manager.search(tmp_path, "Installation", kind="markdown")
        assert search["total"] >= 1

        # Get outline should show sections
        outline = manager.get_file_outline(tmp_path, "docs.md")
        assert outline["entity_count"] >= 4  # 4 sections

    def test_mixed_project(self, manager, tmp_path):
        (tmp_path / "app.py").write_text("class App:\n    def run(self): pass\n")
        (tmp_path / "README.md").write_text("# App\n\nDocumentation.\n")
        result = manager.index_project(tmp_path)
        assert result["files_changed"] >= 2

        # Search all
        search = manager.search(tmp_path, "App")
        assert search["total"] >= 1

        # Clear cache
        cleared = manager.clear_project_cache(tmp_path)
        assert cleared["cleared"] is True

    def test_find_definition(self, manager, tmp_path):
        (tmp_path / "funcs.py").write_text("def my_function():\n    return 42\n")
        manager.index_project(tmp_path)
        result = manager.find_definition(tmp_path, "my_function")
        assert len(result["results"]) >= 1

    def test_find_references(self, manager, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        result = manager.find_references(tmp_path, "python:code.py:x")
        assert "references" in result

    def test_get_related_code(self, manager, tmp_path):
        (tmp_path / "code.py").write_text("class Foo:\n    def bar(self): pass\n")
        manager.index_project(tmp_path)
        result = manager.get_related_code(tmp_path, "python:code.py:Foo.bar")
        assert "related" in result

    def test_project_status(self, manager, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        manager.index_project(tmp_path)
        status = manager.get_index_status(tmp_path)
        assert status["project_id"]
        assert status["health"] in ("healthy", "new")

    def test_markdown_section_retrieval(self, manager, tmp_path):
        (tmp_path / "doc.md").write_text("# Title\n\nContent.\n")
        manager.index_project(tmp_path)
        outline = manager.get_project_outline(tmp_path)
        md_entities = []
        for f in outline.get("files", []):
            for e in f.get("outline", []):
                eid = e.get("entity_id", "")
                if "markdown" in eid:
                    md_entities.append(e)
        if md_entities:
            section = manager.get_markdown_section(tmp_path, md_entities[0]["entity_id"])
            assert "source" in section

    def test_syntax_error_handled(self, manager, tmp_path):
        (tmp_path / "bad.py").write_text("def\n")
        result = manager.index_project(tmp_path)
        # Should have errors but not crash
        assert "errors" in result
