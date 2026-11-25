from unittest.mock import patch

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
    assert "Configure Redis" in configuration.source
    assert "Install the project" not in configuration.source


def test_duplicate_headings_compute_paths_linearly():
    source = "".join(f"## Same\nbody {index}\n" for index in range(100))
    analyzer = MarkdownAnalyzer()

    with patch.object(analyzer, "_heading_path", wraps=analyzer._heading_path) as path_mock:
        result = analyzer.analyze(source, "duplicates.md")

    entity_ids = [entity.entity_id for entity in result.entities]
    assert path_mock.call_count == 100
    assert entity_ids[0].endswith(":Same")
    assert entity_ids[1].endswith(":Same#2")
    assert entity_ids[-1].endswith(":Same#100")
