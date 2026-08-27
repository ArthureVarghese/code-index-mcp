from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = Path.home() / ".code-index-mcp"
DEV_INDEX_DIR = DEFAULT_INDEX_DIR / "tests"

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "node_modules",
        "dist",
        "build",
        ".code-index-mcp",
    }
)

DEFAULT_EXCLUDED_FILES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
    }
)

DEFAULT_EXTENSIONS = frozenset({".py", ".pyi", ".md", ".markdown"})


@dataclass(frozen=True, slots=True)
class IndexConfig:
    """Configuration controlling project indexing and cache behavior."""

    index_root: Path = DEFAULT_INDEX_DIR
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_entity_source_bytes: int = 512 * 1024
    excluded_directories: frozenset[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDED_DIRECTORIES
    )
    excluded_files: frozenset[str] = field(default_factory=lambda: DEFAULT_EXCLUDED_FILES)
    extensions: frozenset[str] = field(default_factory=lambda: DEFAULT_EXTENSIONS)
    follow_symlinks: bool = False
    enable_relationships: bool = True
    enable_embeddings: bool = False
    enable_summaries: bool = False
    enable_watcher: bool = False
    watcher_debounce_ms: int = 500
    search_limit_default: int = 10
    search_limit_max: int = 100
    dev_mode: bool = True

    def __post_init__(self) -> None:
        if self.max_file_size_bytes <= 0:
            logger.warning("IndexConfig :: __post_init__ :: max_file_size_bytes must be positive")
            raise ValueError("max_file_size_bytes must be positive")

        if self.max_entity_source_bytes <= 0:
            logger.warning(
                "IndexConfig :: __post_init__ :: max_entity_source_bytes must be positive"
            )
            raise ValueError("max_entity_source_bytes must be positive")

        if self.watcher_debounce_ms < 0:
            logger.warning("IndexConfig :: __post_init__ :: watcher_debounce_ms cannot be negative")
            raise ValueError("watcher_debounce_ms cannot be negative")

        if not 1 <= self.search_limit_default <= self.search_limit_max:
            logger.warning("IndexConfig :: __post_init__ :: search_limit_default out of range")
            raise ValueError("search_limit_default must be between 1 and search_limit_max")

    @property
    def fingerprint(self) -> str:
        """Return a deterministic hash of indexing-affecting configuration."""
        payload: dict[str, Any] = {
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_entity_source_bytes": self.max_entity_source_bytes,
            "excluded_directories": sorted(self.excluded_directories),
            "excluded_files": sorted(self.excluded_files),
            "extensions": sorted(self.extensions),
            "follow_symlinks": self.follow_symlinks,
            "enable_relationships": self.enable_relationships,
            "enable_embeddings": self.enable_embeddings,
            "enable_summaries": self.enable_summaries,
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    def project_directory(self, project_id: str) -> Path:
        """Return the persistent directory for one project."""
        if not project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project identifier")

        return self.index_root / "projects" / project_id

    @classmethod
    def from_environment(cls) -> IndexConfig:
        """Build configuration from environment variables."""
        logger.debug("from_environment :: loading config from environment variables")

        dev_mode = _env_bool("CODE_INDEX_MCP_DEV", True)

        # Explicit index root takes precedence over dev mode default
        index_root_env = os.environ.get("CODE_INDEX_MCP_INDEX_ROOT")
        if index_root_env is not None:
            index_root = Path(index_root_env).expanduser()
        elif dev_mode:
            index_root = DEV_INDEX_DIR
        else:
            index_root = DEFAULT_INDEX_DIR

        return cls(
            index_root=index_root,
            dev_mode=dev_mode,
            max_file_size_bytes=int(
                os.environ.get(
                    "CODE_INDEX_MCP_MAX_FILE_SIZE",
                    str(10 * 1024 * 1024),
                )
            ),
            enable_relationships=_env_bool(
                "CODE_INDEX_MCP_RELATIONSHIPS",
                True,
            ),
            enable_embeddings=_env_bool(
                "CODE_INDEX_MCP_EMBEDDINGS",
                False,
            ),
            enable_summaries=_env_bool(
                "CODE_INDEX_MCP_SUMMARIES",
                False,
            ),
            enable_watcher=_env_bool(
                "CODE_INDEX_MCP_WATCHER",
                False,
            ),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"Invalid boolean value for {name}: {value!r}")
