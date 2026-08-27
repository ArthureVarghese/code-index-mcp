from __future__ import annotations

import asyncio

from code_index_mcp.config import IndexConfig
from code_index_mcp.server import run_server
from code_index_mcp.utils.logging import configure_logging


def main() -> None:
    """Run the MCP server over stdio."""
    config = IndexConfig.from_environment()
    configure_logging(dev_mode=config.dev_mode)
    asyncio.run(run_server(config=config))


if __name__ == "__main__":
    main()
