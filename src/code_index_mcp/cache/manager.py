from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from sqlite3 import Connection
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """Persistence for independently invalidatable derived cache layers."""

    def __init__(self, connection: Connection, *, enabled: bool = True) -> None:
        self.connection = connection
        self.enabled = enabled

    def get(
        self,
        *,
        project_id: str,
        cache_key: str,
        source_hash: str,
        dependency_hash: str | None,
        implementation_version: str,
    ) -> Any | None:
        row = self.connection.execute(
            """
            SELECT metadata_json
            FROM cache_metadata
            WHERE project_id = ?
              AND cache_key = ?
              AND source_hash = ?
              AND (
                    dependency_hash = ?
                    OR (dependency_hash IS NULL AND ? IS NULL)
                  )
              AND implementation_version = ?
              AND status = 'valid'
            """,
            (
                project_id,
                cache_key,
                source_hash,
                dependency_hash,
                dependency_hash,
                implementation_version,
            ),
        ).fetchone()

        if row is None:
            logger.debug("CacheManager :: get :: cache miss for cache_key=%s", cache_key)
            return None

        logger.debug("CacheManager :: get :: cache hit for cache_key=%s", cache_key)
        return json.loads(row["metadata_json"])

    def put(
        self,
        *,
        project_id: str,
        cache_key: str,
        layer: str,
        source_hash: str,
        dependency_hash: str | None,
        implementation_version: str,
        value: Any,
    ) -> None:
        if not self.enabled:
            return

        self.connection.execute(
            """
            INSERT INTO cache_metadata (
                cache_key,
                project_id,
                cache_layer,
                source_hash,
                dependency_hash,
                implementation_version,
                status,
                created_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                project_id = excluded.project_id,
                cache_layer = excluded.cache_layer,
                source_hash = excluded.source_hash,
                dependency_hash = excluded.dependency_hash,
                implementation_version = excluded.implementation_version,
                status = 'valid',
                created_at = excluded.created_at,
                metadata_json = excluded.metadata_json
            """,
            (
                cache_key,
                project_id,
                layer,
                source_hash,
                dependency_hash,
                implementation_version,
                datetime.now(UTC).isoformat(),
                json.dumps(value, sort_keys=True),
            ),
        )

    def invalidate(self, cache_key: str) -> None:
        logger.debug("CacheManager :: invalidate :: cache_key=%s", cache_key)
        self.connection.execute(
            """
            UPDATE cache_metadata
            SET status = 'invalid'
            WHERE cache_key = ?
            """,
            (cache_key,),
        )
