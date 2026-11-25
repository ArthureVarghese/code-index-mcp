from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import UserMessage

from code_index_mcp.config import IndexConfig
from code_index_mcp.project.manager import ProjectManager
from code_index_mcp.search.fts import tokenize
from code_index_mcp.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def create_server(config: IndexConfig | None = None) -> FastMCP:
    config = config or IndexConfig.from_environment()
    configure_logging(dev_mode=config.dev_mode)
    manager = ProjectManager(config)
    server = FastMCP(
        name="code-index-mcp",
        instructions=(
            "This is your always-fresh, queryable map of the codebase — fine-grained, "
            "persistent intelligence over Python and Markdown. PREFER THIS over grep and over "
            "reading whole files: instead of grepping or opening a file to answer a fact about "
            "the code or docs (where a symbol is, what it does, who calls it, what a doc says), "
            "query this map first. Open each project with index_project (turns every Python "
            "class/function/variable and every Markdown section into searchable entities), then "
            "start_watching so the map stays in sync as files change. Then search instead of "
            "grep: search_project / search_code / search_docs to locate entities and docs, and "
            "read only the relevant slice instead of whole files via get_symbol / "
            "get_markdown_section / get_code (line range). Use find_definition / "
            "find_references to trace connections (no manual import-diving), and "
            "get_file_outline / get_project_outline for structure without full source. Entity "
            "IDs returned by search are stable across re-indexes, so pass them straight into "
            "get_symbol, get_related_code, and find_references. The index is incremental and "
            "cached, so targeted lookups are far faster and cheaper than grepping or reading "
            "whole files."
            "\n\nTools:\n"
            '{"index_project":{"project_root":"str","force":"bool=false"}},'
            '{"refresh_index":{"project_root":"str"}},'
            '{"search_project":{"project_root":"str","query":"str","keywords":"bool?","path":"str?","limit":"int=20"}},'
            '{"search_code":{"project_root":"str","query":"str","keywords":"bool?","path":"str?","limit":"int=20"}},'
            '{"search_docs":{"project_root":"str","query":"str","keywords":"bool?","path":"str?","limit":"int=20"}},'
            '{"get_symbol":{"project_root":"str","entity_id":"str","context":"str=normal"}},'
            '{"get_code":{"project_root":"str","path":"str","start_line":"int","end_line":"int"}},'
            '{"get_markdown_section":{"project_root":"str","entity_id":"str","context":"str=normal"}},'
            '{"get_file_outline":{"project_root":"str","path":"str"}},'
            '{"get_project_outline":{"project_root":"str"}},'
            '{"find_definition":{"project_root":"str","symbol":"str"}},'
            '{"find_references":{"project_root":"str","entity_id":"str","page":"int=1","page_size":"int=20"}},'
            '{"get_related_code":{"project_root":"str","entity_id":"str","context":"str=normal","page":"int=1","page_size":"int=20"}},'
            '{"get_index_status":{"project_root":"str"}},'
            '{"clear_project_cache":{"project_root":"str"}},'
            '{"start_watching":{"project_root":"str","interval":"float=0.5"}},'
            '{"stop_watching":{"project_root":"str"}},'
            '{"list_watching":{}}'
            "\ncontext: minimal|normal|full (get_symbol); expanded also on get_related_code."
        ),
    )

    @server.tool()
    def index_project(project_root: str, force: bool = False) -> dict:
        """Build the index that powers every other tool — your first move per project.

        Indexes every Python file (AST-parse to each class, method, function,
        variable) and Markdown file (section by section with heading hierarchy)
        into a fast persistent SQLite map with stable entity IDs. Do this once
        per project_root BEFORE relying on the search/retrieval tools — without
        it there's nothing to query. Later calls only re-index changed files,
        so it's cheap to re-run. Set up start_watching after this and you can
        keep querying the map instead of reading whole files.

        Returns file/entity counts and how much was reused from cache.
        """
        logger.debug("index_project :: project_root=%s, force=%s", project_root, force)
        return manager.index_project(Path(project_root), force=force)

    @server.tool()
    def refresh_index(project_root: str) -> dict:
        """Fast incremental re-index after you edit files.

        Detects exactly which Python/Markdown files changed since the last
        index and updates just those, reusing still-valid cached entities — so
        your searchable map stays current instead of going stale (a manual
        alternative to start_watching). Run after editing code/docs so you can
        keep querying the index instead of re-reading whole files.

        Returns counts of files added, changed, and removed.
        """
        logger.debug("refresh_index :: project_root=%s", project_root)
        return manager.refresh_index(Path(project_root))

    @server.tool()
    def search_project(
        project_root: str,
        query: str,
        keywords: bool | None = None,
        path: str | None = None,
        limit: int = 20,
    ) -> dict:
        """The one-stop search over the whole codebase — code AND docs together.

        PREFER this over grep: it answers "where is X / what references / what does it say"
        from the index instead of scanning raw text. Use it when a question might live in
        either Python or Markdown (or you're not sure which). It merges symbol matching,
        full-text search, Markdown heading matching, and optional semantic search into a
        single ranked list. Every hit returns a stable entity_id plus file path, line
        range, and a relevance score. Search hits include `start_line`/`end_line` — pass
        those straight into get_code to read only that slice instead of the whole file.

        Set `keywords` to true to search several terms at once: the server splits
        `query` into tokens, searches each one independently through the normal
        pipeline, then combines and deduplicates by entity_id — an entity matching
        multiple keywords ranks higher — and each result is tagged with the
        keyword(s) it matched.

        Pass `path` (a relative file path, e.g. "src/app/auth.py") to restrict
        the search to just that one file — useful for finding where a term
        appears inside a specific file.

        Start here; then drill into get_symbol / get_code /
        get_markdown_section with the entity_ids it returns.
        """
        logger.debug(
            "search_project :: project_root=%s, query=%s, keywords=%s, path=%s",
            project_root, query, keywords, path,
        )
        if keywords:
            return manager.search_batch(
                Path(project_root),
                tokenize(query),
                kind="all",
                limit=limit,
                path=path,
            )
        return manager.search(
            Path(project_root), query, kind="all", limit=limit, path=path
        )

    @server.tool()
    def search_code(
        project_root: str,
        query: str,
        keywords: bool | None = None,
        path: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search only Python code — classes, functions, methods, variables.

        PREFER this over grep for Python: it matches by name, fully-qualified name,
        docstring, and source text from the index, and excludes all Markdown noise. Perfect
        when you know the answer is in Python — e.g. "find every function that
        touches config" or "where is `validate_token` defined/used". Hits include
        `start_line`/`end_line` — pass them to get_code to read only that slice.

        Set `keywords` to true to search several terms at once: the server splits
        `query` into tokens, searches each independently, then combines and
        deduplicates by entity_id, tagged with the keyword(s) each matched.

        Pass `path` (a relative file path, e.g. "src/app/state.py") to restrict
        the search to just that one Python file.

        Returns matched Python entities with scores and source snippets.
        """
        logger.debug(
            "search_code :: project_root=%s, query=%s, keywords=%s, path=%s",
            project_root, query, keywords, path,
        )
        if keywords:
            return manager.search_batch(
                Path(project_root),
                tokenize(query),
                kind="python",
                limit=limit,
                path=path,
            )
        return manager.search(
            Path(project_root), query, kind="python", limit=limit, path=path
        )

    @server.tool()
    def search_docs(
        project_root: str,
        query: str,
        keywords: bool | None = None,
        path: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search only Markdown documentation sections — pure, clean docs.

        PREFER this over grep for docs: it matches heading text, section body, and
        extracted keywords from the index, returning each section with its full heading
        hierarchy so you can locate it in the document. Perfect for "what does
        the README say about caching?" or finding a doc page to cite or update.
        Excludes all Python code results. Hits include `start_line`/`end_line` — pass
        them to get_code or get_markdown_section to read only that part.

        Set `keywords` to true to search several terms at once: the server splits
        `query` into tokens, searches each independently, then combines and
        deduplicates by entity_id, tagged with the keyword(s) each matched.

        Pass `path` (a relative file path, e.g. "docs/cache.md") to restrict the
        search to just that one Markdown file.

        Returns matched Markdown sections with scores.
        """
        logger.debug(
            "search_docs :: project_root=%s, query=%s, keywords=%s, path=%s",
            project_root, query, keywords, path,
        )
        if keywords:
            return manager.search_batch(
                Path(project_root),
                tokenize(query),
                kind="markdown",
                limit=limit,
                path=path,
            )
        return manager.search(
            Path(project_root), query, kind="markdown", limit=limit, path=path
        )

    @server.tool()
    def get_symbol(project_root: str, entity_id: str, context: str = "normal") -> dict:
        """Get complete metadata for one entity (class, method, function, ...).

        PREFER this over opening the file to inspect a symbol: it reads the exact slice
        from the index. Pass the stable entity_id from any search (e.g.
        "python:src/app/auth.py:User.login") to learn everything about it:
        kind, signature, docstring, source range, file path, plus its parent
        (the class), children, callers, callees, imports, and inheritance.

        The context parameter controls how much surrounding code to include:
          - "minimal": identity + location only (name, kind, path, line range)
          - "normal":  adds signature, docstring and its parent (default; no raw
                       source for the nested parent)
          - "full":    adds the complete source text plus callers/callees/
                       imports/inheritance and children (with source)

        Your go-to when you've found an entity and want to understand it fully.
        """
        logger.debug("get_symbol :: project_root=%s, entity_id=%s", project_root, entity_id)
        return manager.get_symbol(Path(project_root), entity_id, context=context)

    @server.tool()
    def get_code(project_root: str, path: str, start_line: int, end_line: int) -> dict:
        """Read exact source lines from a file (inclusive, 1-indexed range).

        PREFER this over reading the whole file: it pulls just the relevant slice from the
        cache/index. The precise way to get the raw text of a function, class, or any
        line range once you know its location from search or an outline. Give
        it a path (with or without a "file:" prefix) plus start_line/end_line,
        and it returns that exact source slice — great for reading the real
        implementation before you modify or explain it.

        Returns the source text with file path and line boundaries.
        """
        logger.debug("get_code :: project_root=%s, path=%s", project_root, path)
        return manager.get_code(Path(project_root), path, start_line, end_line)

    @server.tool()
    def get_markdown_section(project_root: str, entity_id: str, context: str = "normal") -> dict:
        """Read one complete Markdown section, resolved by heading.

        PREFER this over reading/scraping the whole Markdown file: it returns the exact
        section from the index. Pass an entity ID such as
        "markdown:README.md:Installation" — or just "markdown:README.md:Install"
        (a partial heading name is resolved for you when unambiguous). You get
        the heading, its level and full path in the doc, the body content, and
        related parent/child sections. context="full" includes the body text.
        """
        logger.debug("get_markdown_section :: root=%s, id=%s", project_root, entity_id)
        return manager.get_markdown_section(Path(project_root), entity_id, context=context)

    @server.tool()
    def get_file_outline(project_root: str, path: str) -> dict:
        """Get the structural outline of one file (classes, functions, methods).

        PREFER this over reading the whole file to see what's in it: it lists every
        indexed entity with its kind, line range, and nesting from the index, so you can
        see at a glance what's defined where. Great for orienting yourself in a new
        file before diving into specific symbols.

        Returns the outline tree with entity name, kind, and line range.
        """
        logger.debug("get_file_outline :: project_root=%s, path=%s", project_root, path)
        return manager.get_file_outline(Path(project_root), path)

    @server.tool()
    def get_project_outline(project_root: str) -> dict:
        """See the entire project's structure at a glance.

        Groups every file's outline by path so you can quickly map out the whole
        Python + Markdown layout — which modules define what, and where the docs
        live — without reading any full source. Use this to build context about
        a codebase you're unfamiliar with before zeroing in on specific files.

        Returns a tree of files and their entity summaries.
        """
        logger.debug("get_project_outline :: project_root=%s", project_root)
        return manager.get_project_outline(Path(project_root))

    @server.tool()
    def find_definition(project_root: str, symbol: str) -> dict:
        """Jump from a symbol name straight to where it's defined.

        PREFER this over grepping for a definition: it resolves names via the index.
        Hand it a bare name ("User", "login") or a fully-qualified one
        ("app.auth.models.User") and it resolves to the defining entity with
        its file path and line range — no manual grepping through imports.
        Ideal answer to "where is this defined / what does it look like?"

        Returns the matching entity metadata, or an error if not found.
        """
        logger.debug("find_definition :: project_root=%s, symbol=%s", project_root, symbol)
        return manager.find_definition(Path(project_root), symbol)

    @server.tool()
    def find_references(
        project_root: str,
        entity_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Trace where an entity is used and called across the codebase.

        PREFER this over grepping for usages: it traces references via the index.
        Pass a stable entity_id to find every place it's referenced: imports,
        calls, inheritance, decorators — each with its relationship kind and
        source location. Beyond exact, statically-resolved references, it also
        surfaces "likely" matches (confidence:"loose") for call sites that
        resolve only by name, e.g. `self.service.method()`. Perfect for "who
        calls this?" / "what depends on this?" impact analysis.

        References are paginated: pass `page` (1-based) and `page_size` to page
        through them. The response includes `total`, `page`, `page_size` and
        `has_more` so you can keep fetching until `has_more` is false.

        Returns an ordered list of relationships (exact first, then loose).
        """
        logger.debug("find_references :: project_root=%s, entity_id=%s", project_root, entity_id)
        return manager.find_references(
            Path(project_root), entity_id, page=page, page_size=page_size
        )

    @server.tool()
    def get_related_code(
        project_root: str,
        entity_id: str,
        context: str = "normal",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Get an entity's surrounding code context — parent, siblings, children.

        Pass an entity_id and see where it sits in the hierarchy: the class it
        belongs to (parent), its peer methods (siblings), and its own methods
        (children). Use this to understand how a symbol fits into its container
        before editing, without navigating files manually.

        The `context` parameter controls how much of each related entity is
        returned:
          - "minimal": identity + location only (name, kind, path, lines)
          - "normal":  adds signature, docstring (default; no raw source)
          - "full":    includes the complete source text

        Results are paginated via `page` (1-based) and `page_size`; the response
        includes `total`, `has_more` and the pages you asked for.

        Returns the related parent and children with their metadata.
        """
        logger.debug("get_related_code :: project_root=%s, entity_id=%s", project_root, entity_id)
        return manager.get_related_code(
            Path(project_root), entity_id, context=context, page=page, page_size=page_size
        )

    @server.tool()
    def get_index_status(project_root: str) -> dict:
        """Check the health and freshness of the index.

        Shows indexed file/entity counts (Python + Markdown), last-index time,
        cache hit ratios, and storage info. Use it to confirm a project is
        indexed and current — e.g. before deciding whether to refresh_index —
        or to diagnose why a search returned nothing.

        Returns index metadata: file counts, entity counts, and timing.
        """
        logger.debug("get_index_status :: project_root=%s", project_root)
        return manager.get_index_status(Path(project_root))

    @server.tool()
    def clear_project_cache(project_root: str) -> dict:
        """Wipe the persistent index for a project so it rebuilds fresh.

        Removes the SQLite database and all cached data for that project; the
        next index_project does a full from-scratch rebuild. Use this when you
        suspect the index is stale or corrupted and want a clean slate.

        Returns confirmation with the path of the deleted index.
        """
        logger.debug("clear_project_cache :: project_root=%s", project_root)
        return manager.clear_project_cache(Path(project_root))

    @server.tool()
    def start_watching(project_root: str, interval: float = 0.5) -> dict:
        """Keep the index in sync so you can query instead of reading files.

        Launches a background watcher that re-indexes any changed
        Python/Markdown file after a short debounce (default 0.5s). Turn it on
        after index_project and the map always reflects the workspace — meaning
        you can keep using search/get_symbol/find_references against fresh data
        rather than re-reading source each time. Multiple projects can be
        watched at once.

        Returns confirmation with the watched path and polling interval.
        """
        logger.debug("start_watching :: project_root=%s, interval=%s", project_root, interval)
        return manager.start_watching(Path(project_root), interval=interval)

    @server.tool()
    def stop_watching(project_root: str) -> dict:
        """Stop the background auto-index watcher for a project.

        Stops watching so files stop triggering re-indexes. The existing index
        stays intact — only the live auto-rebuild is paused. Call
        start_watching to resume, or refresh_index/index_project to update
        manually.

        Returns confirmation that the path is no longer watched.
        """
        logger.debug("stop_watching :: project_root=%s", project_root)
        return manager.stop_watching(Path(project_root))

    @server.tool()
    def list_watching() -> dict:
        """See which projects currently have the live auto-index watcher on.

        Lists active watchers with their project root paths, polling intervals,
        and uptime — handy for verifying that a project will stay fresh
        automatically while you edit.

        Returns the list of watched paths and their configuration.
        """
        logger.debug("list_watching")
        return manager.list_watching()

    @server.prompt(
        name="codebase_workflow",
        title="Python & Markdown code intelligence workflow",
        description=(
            "How to use this server: index + watch a project, then query targeted "
            "slices instead of reading whole files. Load this before working on a "
            "Python/Markdown codebase."
        ),
    )
    def codebase_workflow():
        """Inject the recommended usage workflow for code-intelligence queries."""
        return [
            UserMessage(
                "Use the code-index-mcp tools to answer questions about Python and "
                "Markdown — query the index instead of grepping or reading whole files. "
                "Workflow:\n"
                "\n"
                "1. INDEX FIRST — call `index_project(root)` once per project so the "
                "code/docs are searchable. Re-run only when files change.\n"
                "2. STAY FRESH — call `start_watching(root)` to auto re-index on "
                "edit, or `refresh_index(root)` manually after changes.\n"
                "3. QUERY, DON'T READ — for a specific fact, use the targeted tool:\n"
                "   - `search_project` (code + docs) or `search_code` / `search_docs` "
                "to locate. Scope to one file with `path` (e.g. "
                "`path=\"src/app/auth.py\"`); match several terms at once by passing "
                "`keywords=true` (the server splits the query into terms).\n"
                "   - Search hits include `start_line`/`end_line` — pass them to "
                "`get_code(path, start, end)` to read only that exact line range.\n"
                "   - `find_definition(symbol)` → where something is defined.\n"
                "   - `find_references(entity_id)` → who calls / uses it.\n"
                "   - `get_symbol(entity_id)`, `get_markdown_section(entity_id)` → "
                "full details of one entity/section. `get_code` / `get_symbol` / "
                "`get_markdown_section` read just the relevant slice instead of the "
                "whole file.\n"
                "   - `get_file_outline(path)` / `get_project_outline(root)` → "
                "structure without full source.\n"
                "\n"
                "Entity IDs from any search are stable — pass them straight into "
                "get_symbol / get_related_code / find_references. The index is "
                "incremental and cached, so targeted lookups beat grepping or reading "
                "whole files."
            )
        ]

    return server


async def run_server(config: IndexConfig | None = None) -> None:
    srv = create_server(config)
    logger.info("run_server :: starting code-index-mcp server")
    await srv.run_stdio_async()


server = create_server()
