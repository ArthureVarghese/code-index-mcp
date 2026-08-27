from __future__ import annotations

import pytest

from code_index_mcp.cache.manager import CacheManager
from code_index_mcp.cache.stats import CacheStats
from code_index_mcp.storage.database import Database


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "test.db")
    # Insert a project row for FK constraints
    db.connection.execute(
        "INSERT INTO projects"
        " (project_id, canonical_root, schema_version,"
        " indexer_version, indexing_state,"
        " configuration_fingerprint)"
        " VALUES (?, ?, 1, 'test', 'ready', '')",
        ("proj1", str(tmp_path)),
    )
    yield db
    db.close()


@pytest.fixture
def cache_manager(database):
    return CacheManager(database.connection)


class TestCacheStats:
    def test_defaults(self):
        stats = CacheStats()
        assert stats.files_seen == 0
        assert stats.entity_hit_ratio == 1.0
        assert stats.file_hit_ratio == 1.0

    def test_entity_hit_ratio(self):
        stats = CacheStats(entities_reused=3, entities_recomputed=1)
        assert stats.entity_hit_ratio == pytest.approx(0.75)

    def test_file_hit_ratio(self):
        stats = CacheStats(files_reused=2, files_parsed=8)
        assert stats.file_hit_ratio == pytest.approx(0.2)

    def test_to_dict(self):
        stats = CacheStats(files_seen=5, entities_reused=3, entities_recomputed=2)
        d = stats.to_dict()
        assert d["files_seen"] == 5
        assert d["entities_reused"] == 3
        assert d["entity_hit_ratio"] == pytest.approx(0.6)


class TestCacheManager:
    def test_put_and_get(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="embeddings",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value={"vector": [1.0, 2.0]},
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
        )
        assert result == {"vector": [1.0, 2.0]}

    def test_get_missing_returns_none(self, cache_manager):
        result = cache_manager.get(
            project_id="proj1",
            cache_key="nonexistent",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
        )
        assert result is None

    def test_get_wrong_hash_returns_none(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value="data",
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="wrong_hash",
            dependency_hash=None,
            implementation_version="1.0",
        )
        assert result is None

    def test_invalidate(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value="data",
        )
        cache_manager.invalidate("key1")
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
        )
        assert result is None

    def test_put_overwrites(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value="old",
        )
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value="new",
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
        )
        assert result == "new"

    def test_get_with_dependency_hash(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash="dep1",
            implementation_version="1.0",
            value="data",
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash="dep1",
            implementation_version="1.0",
        )
        assert result == "data"

    def test_get_wrong_dependency_hash_returns_none(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash="dep1",
            implementation_version="1.0",
            value="data",
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash="dep2",
            implementation_version="1.0",
        )
        assert result is None

    def test_get_wrong_version_returns_none(self, cache_manager):
        cache_manager.put(
            project_id="proj1",
            cache_key="key1",
            layer="test",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="1.0",
            value="data",
        )
        result = cache_manager.get(
            project_id="proj1",
            cache_key="key1",
            source_hash="hash1",
            dependency_hash=None,
            implementation_version="2.0",
        )
        assert result is None
