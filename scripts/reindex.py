from __future__ import annotations

import argparse
from pathlib import Path

from code_index_mcp.project.manager import ProjectManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex a Code Index MCP project")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()

    manager = ProjectManager()
    result = manager.index_project(
        args.project.resolve(),
        force=True,
    )

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
