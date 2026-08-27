from code_index_mcp.indexing.markdown.analyzer import MarkdownAnalyzer


def test_sections_are_independent_entities():
    source = """# Project

## Installation

Install the project.

## Configuration

Configure Redis.

## Development

Run tests.
"""

    result = MarkdownAnalyzer().analyze(
        source,
        "README.md",
    )

    titles = [entity.name for entity in result.entities]

    assert "Installation" in titles
    assert "Configuration" in titles
    assert "Development" in titles

    configuration = next(e for e in result.entities if e.name == "Configuration")

    assert configuration.source_range.start_line == 7
    assert configuration.source_range.end_line == 10
