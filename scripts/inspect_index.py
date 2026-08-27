from __future__ import annotations

import argparse
import json
from pathlib import Path

from code_index_mcp.project.manager import ProjectManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a Code Index MCP project index")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()

    manager = ProjectManager()

    status = manager.get_index_status(args.project.resolve())

    print(json.dumps(status, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
