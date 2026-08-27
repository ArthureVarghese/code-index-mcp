from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from code_index_mcp.storage.schema import SCHEMA_VERSION, schema_statements

logger = logging.getLogger(__name__)

_METADATA_TABLE = "code_index_schema_metadata"


class Database:
    """SQLite infrastructure layer."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )

        self._connection.row_factory = sqlite3.Row

        self._configure()
        self.initialize()
        logger.info("Database :: __init__ :: opened database at %s", self.path)

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the underlying connection for repository/test use."""
        return self._connection

    def _configure(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")

    def initialize(self) -> None:
        """Initialize or migrate the database schema."""
        self.initialize_schema()

    def initialize_schema(self) -> None:
        logger.debug("initialize_schema :: applying schema statements")
        with self.transaction():
            for statement in schema_statements():
                self._connection.execute(statement)

            self._ensure_schema_version()

    def _ensure_schema_version(self) -> None:
        if not self._table_exists(_METADATA_TABLE):
            self._connection.execute(
                f"""
                CREATE TABLE {_METADATA_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            self._connection.execute(
                f"""
                INSERT INTO {_METADATA_TABLE}(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(SCHEMA_VERSION),),
            )

            return

        row = self._connection.execute(
            f"""
            SELECT value
            FROM {_METADATA_TABLE}
            WHERE key = 'schema_version'
            """
        ).fetchone()

        if row is None:
            self._connection.execute(
                f"""
                INSERT INTO {_METADATA_TABLE}(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(SCHEMA_VERSION),),
            )
            return

        current_version = int(row["value"])

        if current_version > SCHEMA_VERSION:
            logger.warning(
                "_ensure_schema_version :: database schema %d is newer than supported %d",
                current_version,
                SCHEMA_VERSION,
            )
            raise RuntimeError(
                f"Database schema {current_version} is newer than supported schema {SCHEMA_VERSION}"
            )

        if current_version < SCHEMA_VERSION:
            logger.debug(
                "_ensure_schema_version :: migrating from v%d to v%d",
                current_version,
                SCHEMA_VERSION,
            )
            self._migrate(current_version, SCHEMA_VERSION)

    def _migrate(self, current: int, target: int) -> None:
        version = current

        while version < target:
            next_version = version + 1
            migration = MIGRATIONS.get(next_version)

            if migration is None:
                raise RuntimeError(
                    f"No migration available from schema {version} to {next_version}"
                )

            migration(self._connection)
            version = next_version

            self._connection.execute(
                f"""
                INSERT OR REPLACE INTO {_METADATA_TABLE}(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(version),),
            )

    def _table_exists(self, table_name: str) -> bool:
        row = self._connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()

        return row is not None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")

        try:
            yield self._connection
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def execute(
        self,
        sql: str,
        parameters: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        return self._connection.execute(sql, parameters)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


MIGRATIONS: dict[int, Any] = {}
