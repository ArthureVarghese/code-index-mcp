from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from code_index_mcp.retrieval.context import ContextBuilder

logger = logging.getLogger(__name__)


class RetrievalEngine:
    def __init__(self, repositories: Any):
        self.repositories = repositories
        self.context = ContextBuilder(repositories)

    def get_symbol(
        self,
        project: Path,
        entity_id: str,
        *,
        depth: str = "normal",
    ) -> dict[str, Any]:
        logger.debug("RetrievalEngine :: get_symbol :: entity_id=%s, depth=%s", entity_id, depth)
        entity = self.repositories.get_entity(entity_id)

        if not entity:
            raise KeyError(f"Unknown entity: {entity_id}")

        return self.context.build(entity, depth=depth)

    def get_code(
        self,
        project: Path,
        path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        logger.debug("RetrievalEngine :: get_code :: %s [%d:%d]", path, start_line, end_line)
        return self.repositories.get_file_region(
            path,
            start_line,
            end_line,
        )

    def get_markdown_section(
        self,
        entity_id: str,
        *,
        depth: str = "normal",
    ) -> dict[str, Any]:
        logger.debug("RetrievalEngine :: get_markdown_section :: %s depth=%s", entity_id, depth)
        section = self.repositories.get_markdown_section(entity_id)

        if not section:
            raise KeyError(f"Unknown Markdown section: {entity_id}")

        return self.context.build(section, depth=depth)
