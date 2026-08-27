from __future__ import annotations

from unittest.mock import AsyncMock, patch

from code_index_mcp.__main__ import main


class TestMain:
    def test_main_calls_asyncio_run(self):
        with patch("code_index_mcp.__main__.run_server", new_callable=AsyncMock) as mock_run:
            main()
            mock_run.assert_called_once()


class TestMainModule:
    def test_if_name_main(self):
        import code_index_mcp.__main__ as mod
        # The module should be importable without side effects
        assert hasattr(mod, "main")
