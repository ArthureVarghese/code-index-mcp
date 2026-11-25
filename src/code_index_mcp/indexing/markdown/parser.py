from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_CLOSE_RE = re.compile(r"\s+#+\s*$")
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", flags=re.DOTALL)
_KEYWORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b")

_STOP_WORDS = {
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


def _heading_from_line(line: str, line_number: int) -> MarkdownHeading | None:
    stripped = line.lstrip()

    if stripped.startswith("```") or stripped.startswith("~~~"):
        return None

    if not stripped.startswith("#"):
        return None

    level = len(stripped) - len(stripped.lstrip("#"))

    if not 1 <= level <= 6:
        return None

    if len(stripped) <= level or stripped[level] != " ":
        return None

    title = _HEADING_CLOSE_RE.sub("", stripped[level + 1 :].strip()).strip()
    return MarkdownHeading(level=level, title=title, line=line_number) if title else None


def _parse_structure(text: str) -> tuple[list[MarkdownHeading], list[ParsedMarkdownSection]]:
    lines = text.splitlines(keepends=True)
    headings: list[MarkdownHeading] = []
    sections: list[ParsedMarkdownSection] = []
    parent_stack: list[int] = []
    in_fenced_code = False
    fence_marker: str | None = None

    def close_section(index: int, end_line: int) -> None:
        section = sections[index]
        section.end_line = end_line
        section.source = "".join(lines[section.start_line - 1 : end_line])

    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()

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

        heading = _heading_from_line(line, line_number)
        if heading is None:
            continue

        if sections:
            close_section(len(sections) - 1, line_number - 1)

        while parent_stack and headings[parent_stack[-1]].level >= heading.level:
            parent_stack.pop()

        parent_index = parent_stack[-1] if parent_stack else None
        index = len(headings)
        headings.append(heading)
        sections.append(
            ParsedMarkdownSection(
                heading=heading,
                start_line=line_number,
                end_line=len(lines),
                source="",
                parent_index=parent_index,
            )
        )
        parent_stack.append(index)

    if sections:
        close_section(len(sections) - 1, len(lines))

    return headings, sections


class MarkdownParser:
    """Lightweight Markdown structural parser."""

    def parse_headings(self, text: str) -> list[MarkdownHeading]:
        headings, _ = _parse_structure(text)
        return headings


def parse_sections(text: str) -> list[ParsedMarkdownSection]:
    _, sections = _parse_structure(text)
    return sections


def extract_links(source: str) -> tuple[str, ...]:
    return tuple(_LINK_RE.findall(source))


def extract_code_blocks(source: str) -> tuple[str, ...]:
    return tuple(_CODE_BLOCK_RE.findall(source))


def extract_keywords(source: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for word in _KEYWORD_RE.findall(source):
        normalized = word.lower()
        if normalized in _STOP_WORDS or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return tuple(result)
