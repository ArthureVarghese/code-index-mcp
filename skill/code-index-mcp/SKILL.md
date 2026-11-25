---
name: code-index-mcp
description: Use code-index-mcp to index, search, and navigate Python and Markdown codebases. Load this skill before working in any Python/Markdown project. Tools query a persistent SQLite index instead of scanning files directly.
---

# Code-Index-MCP

## Purpose

code-index-mcp provides persistent, fine-grained code intelligence for Python and Markdown. It indexes every class, function, method, variable, and Markdown section into a SQLite database with stable entity IDs. All lookups go through the index — not file I/O.

## When to Use

- Every new project: run `index_project` once before any other tool
- After edits: use `refresh_index` (or rely on `start_watching` for auto-refresh)
- Any question about the codebase: search first, not grep or file reads
- Reading code: use line ranges from search hits, not whole files
- Tracing relationships: use entity IDs from search, pass to `find_references` / `get_symbol`

## Core Concepts

### Entity IDs
Stable across re-indexes. Format: `python:relative/path.py:QualifiedName` for Python, `markdown:relative/path.md:Heading` for Markdown. Pass entity IDs from search results directly to `get_symbol`, `find_references`, `get_related_code`.

### Project Root
Every tool takes `project_root` — the absolute path to the project root. This is the directory that was indexed. Use the same path every time.

### Incremental Indexing
`index_project` and `refresh_index` reuse cached entities for unchanged files. Only changed files are re-parsed. `refresh_index` calls `index_project` internally with `force=False`.

### Watcher Persistence
Watcher configs are stored in the central `projects.db` at `~/.code-index-mcp/projects.db` (or `CODE_INDEX_MCP_INDEX_ROOT`). After server restart, watchers are restored automatically on `ProjectManager` init by reading this central registry.

### Languages Supported
Python (AST-based), Markdown (section-level heading hierarchy).

---

## All 18 Tools

### Indexing (5 tools)

**index_project(project_root, force=False)**
- Builds the full searchable index: parses every Python file (AST) and Markdown file (section by section)
- `force=true` forces full re-index; `force=false` (default) is incremental
- Returns: `{files_seen, files_changed, files_reused, entities_recomputed, duration_seconds, ...}`
- Must be called before any search/retrieval tool has data

**refresh_index(project_root)**
- Incremental re-index: detects changed files, re-indexes only those
- Internally calls `index_project(project_root, force=False)`
- Returns: `{files_added, files_changed, files_removed, ...}`

**start_watching(project_root, interval=0.5)**
- Launches background file watcher; debounces changes (default 0.5s), triggers `refresh_index` on file changes
- Multiple projects can be watched simultaneously
- Config persisted to central `projects.db`; restored on restart
- Returns: `{"project": "...", "watching": true}`

**stop_watching(project_root)**
- Stops the background watcher for that project
- Removes config from central registry
- Returns: `{"project": "...", "watching": false}`

**list_watching()**
- No arguments
- Returns: `{"projects": ["path1", "path2", ...], "count": N}`
- Lists projects currently watched (includes restored on startup)

---

### Searching (3 tools)

All three return: `{query, path?, results: [...], total}` or `{keywords, path?, results: [...], total}`

**search_project(project_root, query, keywords?, path?, limit=20)**
- Hybrid search: symbol matching + FTS full-text + Markdown heading + optional semantic
- `keywords`: `true` → server splits `query` into tokens, runs each through the pipeline, merges results by `entity_id`, scores summed, each result tagged with matched keywords. `false`/`null`/omitted → single query search
- `path`: relative file path (e.g. `"src/app.py"`) to scope search to one file
- `limit`: max results (default 20)
- Hits include: `entity_id`, `path`, `start_line`, `end_line`, `score`, `name`, `kind`
- When `keywords=true`: each result also has `keywords: [matched_terms]`

**search_code(project_root, query, keywords?, path?, limit=20)**
- Same as `search_project` but `kind="python"` only — Python entities only, excludes Markdown
- `path` scoped to a Python file
- Returns Python entities with source snippets

**search_docs(project_root, query, keywords?, path?, limit=20)**
- Same as `search_project` but `kind="markdown"` only — Markdown sections only, excludes Python
- `path` scoped to a Markdown file
- Returns Markdown sections with heading hierarchy

---

### Retrieval (3 tools)

**get_symbol(project_root, entity_id, context="normal")**
- Get complete metadata for one entity
- `context`: `"minimal"` → name, kind, path, line range only; `"normal"` (default) → + signature, docstring, parent; `"full"` → + complete source text, callers/callees/imports/inheritance, children (with source)
- Returns: entity metadata with parent, children, callers, callees, imports, inheritance

**get_code(project_root, path, start_line, end_line)**
- Read exact source lines (inclusive, 1-indexed range)
- `path` accepted with or without `"file:"` prefix (prefix is stripped automatically)
- Returns: source text slice with file path and line boundaries

**get_markdown_section(project_root, entity_id, context="normal")**
- Read one complete Markdown section by heading
- `entity_id` format: `"markdown:path/to/file.md:ExactHeading"` or partial (unambiguous)
- `context`: `"normal"` (default) → heading + level + path + body (without raw text); `"full"` → + body text
- Returns: heading, level, full path in doc, body content, parent/child sections

---

### Structure (2 tools)

**get_file_outline(project_root, path)**
- Get structural outline of one file: all indexed entities (classes, functions, methods, variables)
- Returns: `{path, outline: [{entity_id, name, kind, start_line, end_line, children: [...]}, ...], entity_count}`
- Hierarchical: each node has `children` list (built from parent_id relationships)

**get_project_outline(project_root)**
- Entire project structure: groups every file's outline
- Returns: `{project, files: [{path, outline: [...]}, ...], entity_count}`

---

### Relationships (3 tools)

**find_definition(project_root, symbol)**
- Jump from symbol name to where it's defined
- `symbol`: bare name (`"User"`) or fully-qualified (`"app.auth.models.User"`)
- Resolution order: exact `qualified_name` match → exact `name` match → fallback search (Python only, exact name matches)
- Returns: `{symbol, results: [entity]}`

**find_references(project_root, entity_id, page=1, page_size=20)**
- Find every place an entity is referenced: imports, calls, inheritance, decorators
- Returns two kinds: `"confidence": "exact"` (statically resolved) and `"confidence": "loose"` (name-matched call sites)
- `page`: 1-based pagination; `page_size` capped at 100
- Returns: `{entity_id, references: [...], total, page, page_size, has_more}`

**get_related_code(project_root, entity_id, context="normal", page=1, page_size=20)**
- Get parent (class it belongs to), siblings (other members of same class/module), children (methods of a class)
- `context`: `"minimal"` → identity+location; `"normal"` (default) → + metadata; `"full"` → + source
- Returns: `{entity_id, context, related: [...], total, page, page_size, has_more}`

---

### Status (2 tools)

**get_index_status(project_root)**
- Check index health and freshness
- Returns: `{project_id, canonical_root, schema_version, indexing_state, indexed_files, indexed_entities, indexed_markdown_sections, health, last_indexed_at, cache_stats, ...}`

**clear_project_cache(project_root)**
- Wipe the SQLite index and all cached data for the project; next `index_project` does a full rebuild
- Returns: `{project, project_id, message}`

---

## Verified Workflows

### Workflow A: First-Time Setup
```
1. index_project(project_root, force=false)
2. start_watching(project_root)   # optional but recommended
3. get_index_status(project_root) # verify health="ready"
```

### Workflow B: Answer a Code Question
```
1. search_code(project_root, "symbol_name", keywords=true)   # locate
2. get_symbol(project_root, entity_id, context="full")       # understand fully
3. get_code(project_root, path, start_line, end_line)     # read relevant slice
4. find_references(project_root, entity_id)                 # impact analysis
```

### Workflow C: Answer a Docs Question
```
1. search_docs(project_root, "topic", keywords=true)
2. get_markdown_section(project_root, entity_id, context="full")
```

### Workflow D: Find Definition
```
1. find_definition(project_root, "SymbolName")
2. get_code / get_symbol on returned entity
```

### Workflow E: Explore File Structure
```
1. get_file_outline(project_root, "path/to/file.py")
2. get_code(project_root, "path/to/file.py", start, end)   # specific lines
```

### Workflow F: Explore Project Structure
```
1. get_project_outline(project_root)
```

### Workflow G: Keep Index Fresh After Edits
```
1. refresh_index(project_root)   # manual
   OR
1. start_watching(project_root) # automatic
```

### Workflow H: Stop Watching
```
1. stop_watching(project_root)
```

---

## Important Constraints

- Every tool requires `project_root` (absolute path, same path used to index)
- Entity IDs from search are stable — reuse them across tools
- `start_line`/`end_line` from search hits feed directly into `get_code`
- `path` parameter uses relative paths from project root (e.g. `"src/app.py"`)
- `keywords` is a boolean: `true` triggers batch multi-token search; omit/false for single query
- `refresh_index` is identical to `index_project` with `force=False`
- `page_size` capped at 100 on `find_references` and `get_related_code`
- `context` values: `"minimal"`, `"normal"` (default), `"full"`

---

## Common Mistakes

- **Forgetting `index_project`**: search/retrieval tools return empty until indexed
- **Using wrong `project_root`**: must be the same absolute path used for indexing
- **Reading whole files**: use `get_code` with line ranges from search hits instead
- **`keywords` as list**: `keywords` is a boolean (`true`/`false`/`null`), not a list of strings
- **`page_size` overflow**: capped at 100 — use pagination (`page`) for large result sets
- **`force=false` on stale index**: use `index_project(project_root, force=true)` for full rebuild
