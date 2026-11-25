from __future__ import annotations

import logging
from dataclasses import dataclass

from code_index_mcp.indexing.hashing import (
    entity_content_hash,
    exact_source_hash,
    sha256_text,
)
from code_index_mcp.indexing.markdown.parser import (
    extract_code_blocks,
    extract_keywords,
    extract_links,
    parse_sections,
)
from code_index_mcp.indexing.versions import MARKDOWN_ANALYZER_VERSION
from code_index_mcp.models.entities import (
    Entity,
    EntityType,
    SourceKind,
    SourceRange,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarkdownParseResult:
    entities: tuple[Entity, ...]
    errors: tuple[str, ...] = ()

    @property
    def syntax_error(self) -> str | None:
        return self.errors[0] if self.errors else None


class MarkdownAnalyzer:
    VERSION = MARKDOWN_ANALYZER_VERSION

    def analyze(
        self,
        source: str,
        relative_path: str,
        *,
        project_id: str = "",
        file_id: str | None = None,
    ) -> MarkdownParseResult:
        if file_id is None:
            file_id = relative_path

        logger.debug("MarkdownAnalyzer :: analyze :: analyzing %s", relative_path)
        sections = parse_sections(source)

        entities: list[Entity] = []
        section_ids: list[str] = []
        heading_paths = [self._heading_path(sections, index) for index in range(len(sections))]
        duplicate_counts: dict[tuple[str, str], int] = {}

        for index, section in enumerate(sections):
            title = section.heading.title
            heading_path = heading_paths[index]

            base_id = f"markdown:{relative_path}:{heading_path}"
            duplicate_key = (heading_path, title)
            duplicate_count = duplicate_counts.get(duplicate_key, 0)
            duplicate_counts[duplicate_key] = duplicate_count + 1

            section_id = f"{base_id}#{duplicate_count + 1}" if duplicate_count else base_id

            section_ids.append(section_id)

            parent_id = (
                section_ids[section.parent_index] if section.parent_index is not None else None
            )

            keywords = extract_keywords(section.source)
            links = extract_links(section.source)
            code_blocks = extract_code_blocks(section.source)

            semantic_hash = sha256_text(
                "\x1f".join(
                    (
                        title,
                        heading_path,
                        section.source.strip(),
                    )
                )
            )

            content_hash = entity_content_hash(
                normalized_source=section.source,
                structural_metadata={
                    "heading": title,
                    "level": section.heading.level,
                    "heading_path": heading_path,
                },
            )

            entities.append(
                Entity(
                    entity_id=section_id,
                    project_id=project_id,
                    file_id=file_id,
                    source_kind=SourceKind.MARKDOWN,
                    entity_type=EntityType.MARKDOWN_SECTION,
                    name=title,
                    qualified_name=heading_path,
                    parent_id=parent_id,
                    source_range=SourceRange(
                        start_line=section.start_line,
                        end_line=section.end_line,
                        start_column=0,
                        end_column=0,
                    ),
                    content_hash=content_hash,
                    exact_source_hash=exact_source_hash(section.source),
                    semantic_hash=semantic_hash,
                    structural_hash=sha256_text(
                        f"{title}\x1f{section.heading.level}\x1f{heading_path}"
                    ),
                    source=section.source,
                    metadata={
                        "analyzer_version": self.VERSION,
                        "heading_level": section.heading.level,
                        "heading_path": heading_path,
                        "keywords": list(keywords),
                        "links": list(links),
                        "code_blocks": list(code_blocks),
                    },
                )
            )

        return MarkdownParseResult(
            entities=tuple(entities),
        )

    def _heading_path(
        self,
        sections: list,
        index: int,
    ) -> str:
        current = sections[index]

        parts = [current.heading.title]
        parent = current.parent_index

        while parent is not None:
            parts.append(sections[parent].heading.title)
            parent = sections[parent].parent_index

        return "/".join(reversed(parts))
