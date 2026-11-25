from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from code_index_mcp.cache.stats import CacheStats
from code_index_mcp.config import IndexConfig
from code_index_mcp.indexing.manager import IndexManager
from code_index_mcp.indexing.markdown.analyzer import MarkdownAnalyzer
from code_index_mcp.indexing.python.analyzer import PythonAnalyzer
from code_index_mcp.models.projects import IndexState
from code_index_mcp.project.identity import canonical_project_root, project_id_for_root
from code_index_mcp.project.metadata import (
    ensure_central_db,
    ensure_project_metadata,
    set_project_state,
)
from code_index_mcp.retrieval.context import project_entity
from code_index_mcp.retrieval.engine import RetrievalEngine
from code_index_mcp.search.engine import SearchEngine
from code_index_mcp.security.ignore import IgnoreMatcher
from code_index_mcp.security.paths import PathSecurityError, ProjectPathGuard
from code_index_mcp.storage.database import Database
from code_index_mcp.storage.repositories import ProjectRepository, RepositoryStore

logger = logging.getLogger(__name__)

_FILE_ID_PREFIX = "file:"


def _normalize_path(path: str) -> str:
    """Strip a `file:`-prefix so paths returned by retrieval tools can round-trip
    back into path-based tools like `get_code` and `get_file_outline`."""
    if path.startswith(_FILE_ID_PREFIX):
        return path[len(_FILE_ID_PREFIX):]
    return path


def _validate_verbosity(context: str) -> str:
    """Normalize and validate a verbosity level for list/context tools."""
    if context not in ("minimal", "normal", "full"):
        raise ValueError(
            f"Invalid context value {context!r}; expected 'minimal', 'normal' or 'full'"
        )
    return context


def _paginate(
    items: list[Any],
    *,
    page: int,
    page_size: int,
    max_page_size: int = 100,
) -> tuple[list[Any], int, int]:
    """Slice ``items`` into one page, returning (page_items, total, has_more)."""
    if page < 1:
        raise ValueError("page must be >= 1")
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    page_size = min(page_size, max_page_size)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total, end < total


class ProjectManager:
    """High-level project lifecycle, indexing, search and retrieval API."""

    def __init__(self, config: IndexConfig | None = None) -> None:
        self.config = config or IndexConfig.from_environment()
        self.config.index_root.mkdir(parents=True, exist_ok=True)
        self._embedding_provider = None
        self._summary_provider = None
        self._watchers: dict[str, Any] = {}
        self._watchers_lock = threading.Lock()
        self._restore_watchers()

    def _restore_watchers(self) -> None:
        """Load watcher configs from central projects registry and start them."""
        try:
            central_db = ensure_central_db(self.config)
            repo = ProjectRepository(central_db._connection)
            projects = repo.list_all()
            for project in projects:
                watcher_config = project.metadata.get("watchers")
                if watcher_config and watcher_config.get("enabled"):
                    root = Path(watcher_config.get("canonical_root", project.canonical_root))
                    interval = watcher_config.get("interval", 0.5)
                    try:
                        self._start_watcher_internal(root, interval)
                        logger.info(
                            "Restored watcher for project: %s (interval=%.1f)",
                            root, interval
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to restore watcher for %s: %s", root, e
                        )
            central_db.close()
        except Exception as e:
            logger.warning("Failed to restore watchers from central registry: %s", e)

    def _start_watcher_internal(self, root: Path, interval: float) -> None:
        """Start a watcher without persisting config (for internal/restore use)."""
        from ..watcher.debounce import Debouncer
        from ..watcher.service import FileWatcher

        key = str(root)
        debouncer = Debouncer(
            delay=0.5,
            callback=lambda _path: self.refresh_index(root),
        )
        watcher = FileWatcher(
            root,
            callback=lambda p: debouncer.submit(str(p)),
            interval_seconds=interval,
        )
        watcher.start()

        with self._watchers_lock:
            self._watchers[key] = {"watcher": watcher, "debouncer": debouncer}

    def _save_watcher_config(self, project_root: Path, interval: float) -> None:
        """Persist watcher config to project metadata and central registry."""
        project_id = self.project_id(project_root)
        # Update project DB
        db = Database(self.database_path(project_root))
        repo = ProjectRepository(db._connection)
        project = repo.get(project_id)
        if project is None:
            db.close()
            return
        metadata = dict(project.metadata)
        metadata["watchers"] = {
            "enabled": True,
            "interval": interval,
            "canonical_root": str(project_root),
        }
        updated = project.__class__(
            project_id=project.project_id,
            canonical_root=project.canonical_root,
            schema_version=project.schema_version,
            indexer_version=project.indexer_version,
            indexing_state=project.indexing_state,
            configuration_fingerprint=project.configuration_fingerprint,
            last_indexed_at=project.last_indexed_at,
            indexed_files=project.indexed_files,
            indexed_entities=project.indexed_entities,
            indexed_markdown_sections=project.indexed_markdown_sections,
            health=project.health,
            metadata=metadata,
        )
        with db.transaction():
            repo.upsert(updated)
        db.close()
        # Also update central registry
        try:
            central_db = ensure_central_db(self.config)
            central_repo = ProjectRepository(central_db._connection)
            with central_db.transaction():
                central_repo.upsert(updated)
            central_db.close()
        except Exception as e:
            logger.warning("Failed to update watcher config in central registry: %s", e)

    def _remove_watcher_config(self, project_root: Path) -> None:
        """Remove watcher config from project metadata and central registry."""
        project_id = self.project_id(project_root)
        # Update project DB
        db = Database(self.database_path(project_root))
        repo = ProjectRepository(db._connection)
        project = repo.get(project_id)
        if project is None:
            db.close()
            return
        metadata = dict(project.metadata)
        metadata.pop("watchers", None)
        updated = project.__class__(
            project_id=project.project_id,
            canonical_root=project.canonical_root,
            schema_version=project.schema_version,
            indexer_version=project.indexer_version,
            indexing_state=project.indexing_state,
            configuration_fingerprint=project.configuration_fingerprint,
            last_indexed_at=project.last_indexed_at,
            indexed_files=project.indexed_files,
            indexed_entities=project.indexed_entities,
            indexed_markdown_sections=project.indexed_markdown_sections,
            health=project.health,
            metadata=metadata,
        )
        with db.transaction():
            repo.upsert(updated)
        db.close()
        # Also update central registry
        try:
            central_db = ensure_central_db(self.config)
            central_repo = ProjectRepository(central_db._connection)
            with central_db.transaction():
                central_repo.upsert(updated)
            central_db.close()
        except Exception as e:
            logger.warning("Failed to remove watcher config from central registry: %s", e)

    def canonical_root(self, project_root: str | Path) -> Path:
        root = canonical_project_root(project_root)
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")
        try:
            ProjectPathGuard(root)
        except PathSecurityError as exc:
            raise ValueError(f"Invalid project root: {exc}") from exc
        return root

    def project_id(self, project_root: str | Path) -> str:
        return project_id_for_root(self.canonical_root(project_root))

    def database_path(self, project_root: str | Path) -> Path:
        return self.config.project_directory(self.project_id(project_root)) / "index.db"

    def project_directory(self, project_root: str | Path) -> Path:
        return self.config.project_directory(self.project_id(project_root))

    def open_database(self, project_root: str | Path) -> Database:
        return Database(self.database_path(project_root))

    def _services(self, root: Path):
        db = self.open_database(root)
        metadata = ensure_project_metadata(db, root, self.config)
        repos = RepositoryStore(db.connection)
        repos.set_project_id(metadata.project_id)
        from ..cache.manager import CacheManager
        cache_mgr = CacheManager(db.connection)
        indexer = IndexManager(
            db, PythonAnalyzer(), MarkdownAnalyzer(), repos,
            ignore=IgnoreMatcher(root, self.config),
            embedding_provider=self._embedding_provider,
            summary_provider=self._summary_provider,
            cache_manager=cache_mgr,
        )
        return db, metadata, repos, indexer

    def index_project(self, project_root: Path, *, force: bool = False) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        logger.info("index_project :: starting indexing for %s (force=%s)", root, force)
        db, metadata, repos, indexer = self._services(root)
        try:
            set_project_state(db, metadata.project_id, IndexState.INDEXING, health="indexing")
            result = indexer.index_project(root, force=force)
            pid = metadata.project_id
            indexed_files = db.execute(
                "SELECT count(*) FROM files WHERE project_id=?", (pid,)
            ).fetchone()[0]
            indexed_entities = db.execute(
                "SELECT count(*) FROM entities WHERE project_id=?", (pid,)
            ).fetchone()[0]
            indexed_md = db.execute(
                "SELECT count(*) FROM entities "
                "WHERE project_id=? AND source_kind='markdown'", (pid,)
            ).fetchone()[0]
            # Update metadata directly to keep the operation atomic from the caller's perspective.
            from dataclasses import replace
            current = metadata
            health = "degraded" if result["errors"] else "healthy"
            state = IndexState.DEGRADED if result["errors"] else IndexState.READY
            now = __import__("datetime").datetime.now(
                __import__("datetime").UTC
            ).isoformat()

            cache_stats = CacheStats(
                files_seen=result.get("files_seen", 0),
                files_changed=result.get("files_changed", 0),
                files_reused=result.get("files_reused", 0),
                files_parsed=result.get("files_parsed", 0),
                entities_reused=result.get("entities_reused", 0),
                entities_recomputed=result.get("entities_recomputed", 0),
            )

            updated_metadata = dict(current.metadata)
            updated_metadata["last_indexing_stats"] = cache_stats.to_dict()
            updated_metadata["relationships_computed"] = result.get("relationships_computed", 0)

            updated = replace(
                current, indexing_state=state,
                health=health, last_indexed_at=now,
                indexed_files=indexed_files,
                indexed_entities=indexed_entities,
                indexed_markdown_sections=indexed_md,
                metadata=updated_metadata,
            )
            from ..storage.repositories import ProjectRepository
            with db.transaction():
                ProjectRepository(db.connection).upsert(updated)
            result["project_id"] = metadata.project_id
            logger.info("index_project :: completed indexing for %s", root)
            return result
        except Exception:
            logger.warning("index_project :: indexing failed for %s", root)
            set_project_state(db, metadata.project_id, IndexState.FAILED, health="failed")
            raise
        finally:
            db.close()

    def refresh_index(self, project_root: Path) -> dict[str, Any]:
        return self.index_project(project_root, force=False)

    def _open_retrieval(self, root: Path):
        db, metadata, repos, _ = self._services(root)
        return db, metadata, repos

    def search(
        self,
        project_root: Path,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
        path: str | None = None,
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        logger.debug(
            "search :: query=%s, kind=%s, limit=%s, path=%s", query, kind, limit, path
        )
        if path:
            path = _normalize_path(path)
        db, _, repos = self._open_retrieval(root)
        try:
            max_limit = self.config.search_limit_max
            results = SearchEngine(
                repos, embedding_provider=self._embedding_provider
            ).search(
                query, kind=kind, limit=min(limit, max_limit), path=path
            )
            return {"query": query, "path": path, "results": results, "total": len(results)}
        finally:
            db.close()

    def search_batch(
        self,
        project_root: Path,
        keywords: list[str],
        *,
        kind: str = "all",
        limit: int = 20,
        path: str | None = None,
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        logger.debug(
            "search_batch :: keywords=%s, kind=%s, limit=%s, path=%s",
            keywords, kind, limit, path,
        )
        if path:
            path = _normalize_path(path)
        db, _, repos = self._open_retrieval(root)
        try:
            max_limit = self.config.search_limit_max
            results = SearchEngine(
                repos, embedding_provider=self._embedding_provider
            ).search_many(
                keywords, kind=kind, limit=min(limit, max_limit), path=path
            )
            return {
                "keywords": list(keywords),
                "path": path,
                "results": results,
                "total": len(results),
            }
        finally:
            db.close()

    def get_symbol(
        self, project_root: Path, entity_id: str, *, context: str = "normal"
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        logger.debug("get_symbol :: entity_id=%s, context=%s", entity_id, context)
        db, _, repos = self._open_retrieval(root)
        try:
            return RetrievalEngine(repos).get_symbol(root, entity_id, depth=context)
        finally:
            db.close()

    def get_code(
        self, project_root: Path, path: str, start_line: int, end_line: int
    ) -> dict[str, Any]:
        path = _normalize_path(path)
        root = self.canonical_root(project_root)
        logger.debug("get_code :: path=%s, start_line=%s, end_line=%s", path, start_line, end_line)
        db, _, repos = self._open_retrieval(root)
        try:
            return RetrievalEngine(repos).get_code(root, path, start_line, end_line)
        finally:
            db.close()

    def get_markdown_section(
        self, project_root: Path, entity_id: str, *, context: str = "normal"
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        db, _, repos = self._open_retrieval(root)
        try:
            return RetrievalEngine(repos).get_markdown_section(entity_id, depth=context)
        finally:
            db.close()

    def get_file_outline(self, project_root: Path, path: str) -> dict[str, Any]:
        path = _normalize_path(path)
        root = self.canonical_root(project_root)
        db, _, repos = self._open_retrieval(root)
        try:
            entities = repos.get_entities_for_file(path)
            tree = _build_outline_tree(entities)
            return {"path": path, "outline": tree, "entity_count": len(entities)}
        finally:
            db.close()

    def get_project_outline(self, project_root: Path) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        db, _, repos = self._open_retrieval(root)
        try:
            all_entities = repos.list_entities()
            files_map: dict[str, list[dict]] = {}
            for e in all_entities:
                f = e.get("path", e.get("file_id", ""))
                files_map.setdefault(f, []).append(e)
            outline = []
            for fpath, ents in sorted(files_map.items()):
                tree = _build_outline_tree(ents)
                outline.append({"path": _normalize_path(fpath), "outline": tree})
            return {"project": str(root), "files": outline, "entity_count": len(all_entities)}
        finally:
            db.close()

    def find_definition(self, project_root: Path, symbol: str) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        db, _, repos = self._open_retrieval(root)
        try:
            # 1. Try exact qualified_name match first
            rows = db.execute(
                "SELECT entity_id FROM entities WHERE qualified_name = ? AND project_id = ?",
                (symbol, repos._current_project_id),
            ).fetchone()
            if rows:
                entity = repos.get_entity(rows["entity_id"])
                if entity:
                    return {"symbol": symbol, "results": [entity]}

            # 2. Try exact name match
            rows = db.execute(
                "SELECT entity_id FROM entities WHERE name = ? AND project_id = ?",
                (symbol, repos._current_project_id),
            ).fetchall()
            if rows:
                results = []
                for row in rows:
                    entity = repos.get_entity(row["entity_id"])
                    if entity:
                        results.append(entity)
                if results:
                    return {"symbol": symbol, "results": results}

            # 3. Fall back to search — return only exact name matches to avoid false positives
            results = self.search(project_root, symbol, kind="python", limit=20)["results"]
            exact = [
                r for r in results
                if r.get("name") == symbol or r.get("qualified_name") == symbol
            ]
            return {"symbol": symbol, "results": exact}
        finally:
            db.close()

    def find_references(
        self,
        project_root: Path,
        entity_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        db, _, repos = self._open_retrieval(root)
        try:
            exact = repos.get_relationships(entity_id)
            target = repos.get_entity(entity_id)
            loose = self._loose_references(repos, entity_id, target) if target else []
            references, total, has_more = _paginate(
                [*exact, *loose], page=page, page_size=page_size
            )
            return {
                "entity_id": entity_id,
                "references": references,
                "total": total,
                "page": page,
                "page_size": min(page_size, 100),
                "has_more": has_more,
            }
        finally:
            db.close()

    def _loose_references(
        self, repos: RepositoryStore, entity_id: str, target: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Supplement statically resolved references with loosely-fitted candidates.

        Attribute access (e.g. ``self.repositories.search_symbols(...)``) is not
        resolved to a target entity during indexing, so exact relationship analysis
        misses those call sites. Surface them by name matching instead.
        """
        name = target.get("name") or ""
        if not name:
            return []
        exact_ids = {entity_id}
        for rel in repos.get_relationships(entity_id):
            for side in (rel.get("source_entity_id"), rel.get("target_entity_id")):
                if side:
                    exact_ids.add(side)
        project_id = target.get("project_id")
        callable_types = {
            "function", "async_function", "method", "constructor",
            "nested_function", "test", "property",
        }
        loose: list[dict[str, Any]] = []
        for hit in repos.search_text(
            name, kind="python", limit=self.config.search_limit_max
        ):
            hit_id = hit.get("entity_id")
            if not hit_id or hit_id in exact_ids:
                continue
            # Surface only callable bodies that reference the target by name.
            candidate = repos.get_entity(hit_id)
            if not candidate or candidate.get("entity_type") not in callable_types:
                continue
            loose.append(
                {
                    "relationship_id": f"loose:{hit_id}",
                    "project_id": project_id,
                    "source_entity_id": hit_id,
                    "target_entity_id": entity_id,
                    "kind": "calls",
                    "confidence": "loose",
                    "metadata": {"match_reason": "name in source", "path": hit.get("path")},
                }
            )
        return loose

    def get_related_code(
        self,
        project_root: Path,
        entity_id: str,
        *,
        context: str = "normal",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        level = _validate_verbosity(context)
        db, _, repos = self._open_retrieval(root)
        try:
            children = repos.get_children(entity_id)
            parent = repos.get_parent(entity_id)
            related = [
                *((project_entity(c, level) for c in children) if children else []),
                *(([project_entity(parent, level)]) if parent else []),
            ]
            page_items, total, has_more = _paginate(
                related, page=page, page_size=page_size
            )
            return {
                "entity_id": entity_id,
                "context": level,
                "related": page_items,
                "total": total,
                "page": page,
                "page_size": min(page_size, 100),
                "has_more": has_more,
            }
        finally:
            db.close()

    def get_index_status(self, project_root: Path) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        db = self.open_database(root)
        try:
            metadata = ensure_project_metadata(db, root, self.config)
            status = metadata.to_dict()
            status["cache_stats"] = metadata.metadata.get("last_indexing_stats", {})
            status["relationships_computed"] = metadata.metadata.get("relationships_computed", 0)
            return status
        finally:
            db.close()

    def clear_project_cache(self, project_root: Path) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        directory = self.project_directory(root)
        self.remove_project_cache(root)
        return {
            "project": str(root),
            "project_id": project_id_for_root(root),
            "cleared": True,
            "directory": str(directory),
        }

    def remove_project_cache(self, project_root: str | Path) -> None:
        directory = self.project_directory(project_root)
        if not directory.exists():
            return
        directory.resolve().relative_to(self.config.index_root.resolve())
        import shutil
        shutil.rmtree(directory)

    def start_watching(self, project_root: Path, *, interval: float = 0.5) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        key = str(root)

        with self._watchers_lock:
            if key in self._watchers:
                return {
                    "project": str(root),
                    "watching": True,
                    "message": "Already watching",
                }

        self._start_watcher_internal(root, interval)
        self._save_watcher_config(root, interval)

        return {"project": str(root), "watching": True}

    def stop_watching(self, project_root: Path) -> dict[str, Any]:
        root = self.canonical_root(project_root)
        key = str(root)

        with self._watchers_lock:
            entry = self._watchers.pop(key, None)

        if entry is None:
            return {"project": str(root), "watching": False, "message": "Not watching"}

        entry["debouncer"].close()
        entry["watcher"].stop()
        self._remove_watcher_config(root)
        return {"project": str(root), "watching": False}

    def list_watching(self) -> dict[str, Any]:
        with self._watchers_lock:
            projects = [k for k in self._watchers]
        return {"projects": projects, "count": len(projects)}


def _build_outline_tree(entities: list) -> list[dict]:
    """Build a hierarchical outline from flat entity list, grouped by parent."""
    by_id: dict[str, dict] = {}
    for e in entities:
        is_dict = isinstance(e, dict)
        eid = getattr(e, "entity_id", None) or (e.get("entity_id", "") if is_dict else "")
        name = getattr(e, "name", None) or (e.get("name", "") if is_dict else "")
        etype = ""
        if is_dict:
            etype = e.get("entity_type", e.get("kind", ""))
        else:
            etype = getattr(e, "entity_type", None)
            if hasattr(etype, "value"):
                etype = etype.value
            else:
                etype = str(etype) if etype else ""
        sl = (
            getattr(e, "start_line", None)
            or (e.get("start_line", 0) if is_dict else 0)
        )
        el = (
            getattr(e, "end_line", None)
            or (e.get("end_line", 0) if is_dict else 0)
        )
        by_id[eid] = {
            "entity_id": eid,
            "name": name,
            "kind": etype,
            "start_line": sl,
            "end_line": el,
            "children": [],
        }

    roots: list[dict] = []
    for e in entities:
        is_dict = isinstance(e, dict)
        eid = getattr(e, "entity_id", None) or (e.get("entity_id", "") if is_dict else "")
        parent = (
            getattr(e, "parent_id", None)
            or (e.get("parent_id") if is_dict else None)
        )
        node = by_id.get(eid)
        if not node:
            continue
        if parent and parent in by_id:
            by_id[parent]["children"].append(node)
        else:
            roots.append(node)

    return roots
