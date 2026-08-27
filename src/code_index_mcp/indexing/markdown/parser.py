from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class MarkdownHeading:
    level: int
    title: str
    line: int


@dataclass(slots=True)
class ParsedMarkdownSection:
    heading: MarkdownHeading
    start_line: int
    end_line: int
    source: str
    parent_index: int | None = None


class MarkdownParser:
    """Lightweight Markdown structural parser."""

    def parse_headings(self, text: str) -> list[MarkdownHeading]:
        headings: list[MarkdownHeading] = []

        in_fenced_code = False
        fence_marker: str | None = None

        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            stripped = line.lstrip()

            # Ignore ATX-looking headings inside fenced code blocks.
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]

                if not in_fenced_code:
                    in_fenced_code = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fenced_code = False
                    fence_marker = None

                continue

            if in_fenced_code:
                continue

            if not stripped.startswith("#"):
                continue

            level = len(stripped) - len(stripped.lstrip("#"))

            if not 1 <= level <= 6:
                continue

            if len(stripped) <= level:
                continue

            if stripped[level] != " ":
                continue

            title = stripped[level + 1 :].strip()

            # Strip optional closing ATX sequence:
            # "## Title ##" -> "Title"
            title = re.sub(r"\s+#+\s*$", "", title).strip()

            if title:
                headings.append(
                    MarkdownHeading(
                        level=level,
                        title=title,
                        line=line_number,
                    )
                )

        return headings


def parse_sections(text: str) -> list[ParsedMarkdownSection]:
    lines = text.splitlines(keepends=True)
    headings = MarkdownParser().parse_headings(text)

    if not headings:
        return []

    sections: list[ParsedMarkdownSection] = []

    for index, heading in enumerate(headings):
        start_line = heading.line

        if index + 1 < len(headings):
            end_line = headings[index + 1].line - 1
        else:
            end_line = len(lines)

        source = "".join(lines[start_line - 1 : end_line])

        parent_index: int | None = None

        for previous_index in range(index - 1, -1, -1):
            previous = headings[previous_index]

            if previous.level < heading.level:
                parent_index = previous_index
                break

        sections.append(
            ParsedMarkdownSection(
                heading=heading,
                start_line=start_line,
                end_line=end_line,
                source=source,
                parent_index=parent_index,
            )
        )

    return sections


def extract_links(source: str) -> tuple[str, ...]:
    links = re.findall(
        r"\[[^\]]+\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)",
        source,
    )
    return tuple(links)


def extract_code_blocks(source: str) -> tuple[str, ...]:
    blocks = re.findall(
        r"```[^\n]*\n(.*?)```",
        source,
        flags=re.DOTALL,
    )

    return tuple(blocks)


def extract_keywords(source: str) -> tuple[str, ...]:
    words = re.findall(
        r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b",
        source,
    )

    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "into",
        "are",
        "was",
        "will",
        "your",
        "you",
    }

    result: list[str] = []

    for word in words:
        normalized = word.lower()

        if normalized in stop_words:
            continue

        if normalized not in result:
            result.append(normalized)

    return tuple(result)
