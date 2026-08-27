from __future__ import annotations

from unittest.mock import MagicMock, patch

from code_index_mcp.config import IndexConfig
from code_index_mcp.server import create_server


class TestCreateServer:
    def test_creates_server(self):
        server = create_server()
        assert server is not None

    def test_server_with_config(self):
        config = IndexConfig()
        server = create_server(config)
        assert server is not None


class TestToolFunctions:
    def _make_manager_mock(self):
        mock = MagicMock()
        mock.index_project.return_value = {"files_changed": 1}
        mock.refresh_index.return_value = {"files_reused": 1}
        mock.search.return_value = {"results": []}
        mock.get_symbol.return_value = {"entity_id": "e1"}
        mock.get_code.return_value = {"source": "x = 1"}
        mock.get_markdown_section.return_value = {"section_id": "s1"}
        mock.get_file_outline.return_value = {"entities": []}
        mock.get_project_outline.return_value = {"entities": []}
        mock.find_definition.return_value = {"definitions": []}
        mock.find_references.return_value = {"references": []}
        mock.get_related_code.return_value = {"parent": None, "children": []}
        mock.get_index_status.return_value = {"total_files": 0}
        mock.clear_project_cache.return_value = {"deleted": True}
        return mock

    @patch("code_index_mcp.server.ProjectManager")
    def test_index_project_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        # Call via the server's internal tool map
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["index_project"].fn("/tmp/proj", force=False)
        pm.index_project.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_refresh_index_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["refresh_index"].fn("/tmp/proj")
        pm.refresh_index.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_search_project_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["search_project"].fn("/tmp/proj", "query")
        pm.search.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_search_code_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["search_code"].fn("/tmp/proj", "query")
        pm.search.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_search_docs_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["search_docs"].fn("/tmp/proj", "query")
        pm.search.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_symbol_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_symbol"].fn("/tmp/proj", "entity:1")
        pm.get_symbol.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_code_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_code"].fn("/tmp/proj", "code.py", 1, 10)
        pm.get_code.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_markdown_section_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_markdown_section"].fn("/tmp/proj", "section:1")
        pm.get_markdown_section.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_file_outline_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_file_outline"].fn("/tmp/proj", "code.py")
        pm.get_file_outline.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_project_outline_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_project_outline"].fn("/tmp/proj")
        pm.get_project_outline.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_find_definition_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["find_definition"].fn("/tmp/proj", "foo")
        pm.find_definition.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_find_references_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["find_references"].fn("/tmp/proj", "entity:1")
        pm.find_references.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_related_code_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_related_code"].fn("/tmp/proj", "entity:1")
        pm.get_related_code.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_get_index_status_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["get_index_status"].fn("/tmp/proj")
        pm.get_index_status.assert_called_once()

    @patch("code_index_mcp.server.ProjectManager")
    def test_clear_project_cache_tool(self, MockPM):
        pm = self._make_manager_mock()
        MockPM.return_value = pm
        server = create_server()
        tools = {t.name: t for t in server._tool_manager._tools.values()}
        tools["clear_project_cache"].fn("/tmp/proj")
        pm.clear_project_cache.assert_called_once()


class TestCodebaseWorkflowPrompt:
    def test_prompt_registered(self):
        server = create_server()
        prompt = server._prompt_manager.get_prompt("codebase_workflow")
        assert prompt is not None
        assert prompt.name == "codebase_workflow"
        assert "index" in prompt.title.lower() or "workflow" in prompt.title.lower()
        assert prompt.description

    def test_prompt_renders_workflow(self):
        server = create_server()
        prompt = server._prompt_manager.get_prompt("codebase_workflow")
        messages = prompt.fn()
        assert messages, "prompt should return at least one message"
        text = "".join(
            m.content.text for m in messages if getattr(m, "content", None) is not None
        )
        # Core workflow steps are present and actionable.
        assert "index_project" in text
        assert "start_watching" in text
        assert "query" in text.lower()
        assert "find_definition" in text
        assert "find_references" in text
        assert "get_symbol" in text


class TestRunServer:
    def test_run_server_calls_create_and_run(self):
        import asyncio
        from unittest.mock import AsyncMock

        from code_index_mcp.server import run_server

        with patch("code_index_mcp.server.create_server") as mock_create:
            mock_server = MagicMock()
            mock_server.run_stdio_async = AsyncMock()
            mock_create.return_value = mock_server

            coro = run_server()
            asyncio.run(coro)
            coro.close()
            mock_create.assert_called_once()
            mock_server.run_stdio_async.assert_called_once()
