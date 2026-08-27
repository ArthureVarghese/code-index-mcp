# Code Index MCP

Persistent, fine-grained Python and Markdown code intelligence for MCP-compatible coding agents.

## Goals

- Persistent per-project SQLite indexes.
- Python AST-based structural indexing.
- Section-level Markdown indexing.
- Stable entity IDs.
- Fine-grained SHA-256 content hashing.
- Incremental indexing and cache reuse.
- SQLite FTS-based search.
- Precise source retrieval.
- Static relationship analysis.
- Optional embeddings and summaries.
- Local stdio MCP transport.
- No Docker or external database server.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (for environment + dependency management)

## Installation

Create a virtual environment and install the package in editable mode:

```bash
uv venv
.\.venv\Scripts\activate   # Windows
source .venv/bin/activate   # Unix/macOS
uv pip install -e ".[dev]"
```

The `dev` extra installs everything needed to develop and test: pytest, mypy, and ruff.

### Optional filesystem watching

The `watch` extra adds the real-time file-watching dependency (`watchfiles`), enabling the `start_watching` / `stop_watching` tools:

```bash
uv pip install -e ".[watch]"
```

## Running

Launch the MCP server (communicates over MCP stdio):

```bash
code-index-mcp
```

Or directly with Python:

```bash
python -m code_index_mcp
```

### Index location

The persistent per-project index defaults to:

```
~/.code-index-mcp/
└── projects/
    └── <project-hash>/
        └── index.db
```

Set another location via the `CODE_INDEX_MCP_INDEX_ROOT` environment variable:

```bash
export CODE_INDEX_MCP_INDEX_ROOT=/path/to/index-cache   # Unix
$env:CODE_INDEX_MCP_INDEX_ROOT="C:\path\to\index-cache" # PowerShell
```

### Development mode

Run with `CODE_INDEX_MCP_DEV=true` to use a sandboxed index root under `~/.code-index-mcp/tests/` and enable `DEBUG` logging. This keeps dev/test runs isolated from your real index:

```bash
CODE_INDEX_MCP_DEV=true code-index-mcp   # or: CODE_INDEX_MCP_DEV=true uv run pytest
```

## Integrating with a client

The server speaks standard MCP over stdio. Register it in your MCP client's configuration, e.g. in `opencode.json` / `.mcp.json`:

```json
{
  "mcpServers": {
    "code-index": {
      "command": "code-index-mcp",
      "args": []
    }
  }
}
```

## Available tools

- `index_project` — build (or rebuild) the index for a project.
- `refresh_index` — incremental re-index of changed files.
- `search_project` / `search_code` / `search_docs` — hybrid search over the whole project, code only, or Markdown docs only.
- `get_symbol` — full metadata for an entity, with `minimal` / `normal` / `full` context verbosity.
- `get_code` — exact source slice for a file line range.
- `get_markdown_section` — a complete Markdown section, resolved by heading.
- `get_file_outline` / `get_project_outline` — hierarchical structure of a file or whole project.
- `find_definition` — locate where a symbol is defined.
- `find_references` — trace usages/call sites (exact + loose name matches), paginated.
- `get_related_code` — parent / siblings / children context, with verbosity and pagination.
- `get_index_status` — index health, file/entity counts, and cache statistics.
- `clear_project_cache` — wipe a project's cached index.
- `start_watching` / `stop_watching` / `list_watching` — real-time file watching lifecycle (requires the `watch` extra).

## Design

The index is organized around stable logical entities rather than files.

For example:

```
python:src/auth/service.py:AuthService.validate_token
```

is the identity of a method, while its SHA-256 content hash represents its current version.

Changing one method therefore does not require invalidating unrelated methods.

## Search workflow

The intended agent workflow is:

```
search_project
      |
      v
stable entity ID
      |
      v
get_symbol
      |
      v
find_references / get_related_code
```

Search returns compact entity-level results. Retrieval returns exact source and only the requested context.

## Development

Run the test suite (use dev mode to avoid touching your real index):

```bash
CODE_INDEX_MCP_DEV=true uv run pytest
```

Run a single test file:

```bash
CODE_INDEX_MCP_DEV=true uv run pytest tests/unit/test_python_analyzer.py
```

Lint with ruff:

```bash
uv run ruff check .
```

Type-check with mypy:

```bash
uv run mypy src/code_index_mcp
```

Test coverage:

```bash
CODE_INDEX_MCP_DEV=true uv run pytest --cov=code_index_mcp --cov-report=term-missing
```

## Security

The server performs static analysis only.

It does not:

- execute indexed Python;
- import project modules;
- allow arbitrary filesystem reads;
- follow paths outside configured project roots;
- require a remote database.

Project roots are canonicalized before indexing and project indexes are isolated by deterministic project identifiers.
