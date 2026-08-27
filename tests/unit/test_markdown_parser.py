from __future__ import annotations

from code_index_mcp.indexing.markdown.parser import (
    MarkdownParser,
    extract_code_blocks,
    extract_keywords,
    extract_links,
    parse_sections,
)


class TestMarkdownParser:
    def test_parse_headings(self):
        parser = MarkdownParser()
        text = "# Title\n\n## Subtitle\n\n### Deep\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 3
        assert headings[0].level == 1
        assert headings[0].title == "Title"
        assert headings[1].level == 2
        assert headings[2].level == 3

    def test_headings_in_fenced_code_ignored(self):
        parser = MarkdownParser()
        text = "```\n# Not a heading\n```\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 0

    def test_headings_in_tilde_fence(self):
        parser = MarkdownParser()
        text = "~~~\n# Not a heading\n~~~\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 0

    def test_closing_fence_resets(self):
        parser = MarkdownParser()
        text = "```\n# Not heading\n```\n# Real heading\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 1
        assert headings[0].title == "Real heading"

    def test_stripped_closing_markers(self):
        parser = MarkdownParser()
        text = "## Title ##\n"
        headings = parser.parse_headings(text)
        assert headings[0].title == "Title"

    def test_heading_without_space_ignored(self):
        parser = MarkdownParser()
        text = "#NoSpace\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 0

    def test_empty_title_ignored(self):
        parser = MarkdownParser()
        text = "#\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 0

    def test_level_out_of_range(self):
        parser = MarkdownParser()
        text = "####### Too deep\n"
        headings = parser.parse_headings(text)
        assert len(headings) == 0


class TestParseSections:
    def test_single_section(self):
        text = "# Title\nContent here\n"
        sections = parse_sections(text)
        assert len(sections) == 1
        assert sections[0].heading.title == "Title"

    def test_multiple_sections(self):
        text = "# First\nContent 1\n\n## Second\nContent 2\n"
        sections = parse_sections(text)
        assert len(sections) == 2

    def test_parent_index(self):
        text = "# Parent\n\n## Child\nContent\n"
        sections = parse_sections(text)
        assert sections[1].parent_index == 0

    def test_no_headings(self):
        sections = parse_sections("Just text\n")
        assert len(sections) == 0

    def test_last_section_end_line(self):
        text = "# Title\nLine 1\nLine 2\n"
        sections = parse_sections(text)
        lines = text.splitlines(keepends=True)
        assert sections[0].end_line == len(lines)


class TestExtractLinks:
    def test_extract_links(self):
        text = "See [docs](https://example.com) for more"
        links = extract_links(text)
        assert "https://example.com" in links

    def test_no_links(self):
        links = extract_links("no links here")
        assert len(links) == 0


class TestExtractCodeBlocks:
    def test_extract_blocks(self):
        text = "```python\nx = 1\n```\n"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert "x = 1" in blocks[0]

    def test_no_blocks(self):
        blocks = extract_code_blocks("no code blocks")
        assert len(blocks) == 0


class TestExtractKeywords:
    def test_extracts_words(self):
        keywords = extract_keywords("Hello World Testing")
        assert "hello" in keywords
        assert "world" in keywords

    def test_filters_stop_words(self):
        keywords = extract_keywords("the and for with this")
        assert len(keywords) == 0

    def test_deduplicates(self):
        keywords = extract_keywords("foo bar foo baz")
        assert keywords.count("foo") == 1

    def test_filters_short_words(self):
        keywords = extract_keywords("a bb cccc")
        assert "a" not in keywords
        assert "bb" not in keywords
        assert "cccc" in keywords


class TestMarkdownProperties:
    def test_syntax_error_none_when_empty(self):
        from code_index_mcp.indexing.markdown.analyzer import MarkdownParseResult
        result = MarkdownParseResult(entities=())
        assert result.syntax_error is None

    def test_syntax_error_returns_first(self):
        from code_index_mcp.indexing.markdown.analyzer import MarkdownParseResult
        result = MarkdownParseResult(entities=(), errors=("err1", "err2"))
        assert result.syntax_error == "err1"
