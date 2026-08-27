from __future__ import annotations

import pytest

from code_index_mcp.config import IndexConfig
from code_index_mcp.models.projects import IndexState
from code_index_mcp.project.metadata import (
    ensure_project_metadata,
    new_project_metadata,
    set_project_state,
)
from code_index_mcp.storage.database import Database


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def config():
    return IndexConfig()


class TestNewProjectMetadata:
    def test_creates_metadata(self, tmp_path, config):
        meta = new_project_metadata(tmp_path, config)
        assert meta.project_id
        assert meta.canonical_root == str(tmp_path.resolve())
        assert meta.indexing_state == IndexState.NEW
        assert meta.health == "new"

    def test_custom_state(self, tmp_path, config):
        meta = new_project_metadata(tmp_path, config, state=IndexState.INDEXING)
        assert meta.indexing_state == IndexState.INDEXING


class TestEnsureProjectMetadata:
    def test_creates_new(self, database, tmp_path, config):
        meta = ensure_project_metadata(database, tmp_path, config)
        assert meta.project_id
        assert meta.indexing_state == IndexState.NEW

    def test_loads_existing(self, database, tmp_path, config):
        meta1 = ensure_project_metadata(database, tmp_path, config)
        meta2 = ensure_project_metadata(database, tmp_path, config)
        assert meta1.project_id == meta2.project_id


class TestSetProjectState:
    def test_set_state(self, database, tmp_path, config):
        meta = ensure_project_metadata(database, tmp_path, config)
        updated = set_project_state(
            database, meta.project_id, IndexState.INDEXING, health="indexing"
        )
        assert updated.indexing_state == IndexState.INDEXING

    def test_set_state_with_last_indexed(self, database, tmp_path, config):
        meta = ensure_project_metadata(database, tmp_path, config)
        updated = set_project_state(
            database, meta.project_id, IndexState.READY, last_indexed=True
        )
        assert updated.last_indexed_at is not None

    def test_set_state_unknown_raises(self, database, tmp_path, config):
        with pytest.raises(ValueError, match="Unknown project"):
            set_project_state(database, "nonexistent", IndexState.READY)
