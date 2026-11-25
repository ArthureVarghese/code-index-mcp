from __future__ import annotations

import logging

import pytest

from code_index_mcp.config import (
    IndexConfig,
    _env_bool,
)
from code_index_mcp.utils.logging import ColorFormatter


class TestIndexConfigDefaults:
    def test_default_values(self):
        cfg = IndexConfig()
        assert cfg.max_file_size_bytes == 10 * 1024 * 1024
        assert cfg.max_entity_source_bytes == 512 * 1024
        assert cfg.follow_symlinks is False
        assert cfg.enable_relationships is True
        assert cfg.enable_embeddings is False
        assert cfg.enable_summaries is False
        assert cfg.enable_watcher is False
        assert cfg.search_limit_default == 10
        assert cfg.search_limit_max == 100
        assert cfg.dev_mode is False

    def test_custom_values(self):
        cfg = IndexConfig(
            max_file_size_bytes=1024,
            max_entity_source_bytes=256,
            follow_symlinks=True,
            enable_embeddings=True,
            search_limit_default=5,
            search_limit_max=50,
        )
        assert cfg.max_file_size_bytes == 1024
        assert cfg.follow_symlinks is True
        assert cfg.enable_embeddings is True
        assert cfg.search_limit_default == 5
        assert cfg.search_limit_max == 50


class TestIndexConfigValidation:
    def test_max_file_size_zero_raises(self):
        with pytest.raises(ValueError, match="max_file_size_bytes must be positive"):
            IndexConfig(max_file_size_bytes=0)

    def test_max_file_size_negative_raises(self):
        with pytest.raises(ValueError, match="max_file_size_bytes must be positive"):
            IndexConfig(max_file_size_bytes=-1)

    def test_max_entity_source_bytes_zero_raises(self):
        with pytest.raises(ValueError, match="max_entity_source_bytes must be positive"):
            IndexConfig(max_entity_source_bytes=0)

    def test_watcher_debounce_negative_raises(self):
        with pytest.raises(ValueError, match="watcher_debounce_ms cannot be negative"):
            IndexConfig(watcher_debounce_ms=-1)

    def test_search_limit_default_zero_raises(self):
        msg = "search_limit_default must be between 1 and search_limit_max"
        with pytest.raises(ValueError, match=msg):
            IndexConfig(search_limit_default=0)

    def test_search_limit_default_exceeds_max_raises(self):
        msg = "search_limit_default must be between 1 and search_limit_max"
        with pytest.raises(ValueError, match=msg):
            IndexConfig(search_limit_default=200, search_limit_max=100)


class TestFingerprint:
    def test_fingerprint_is_deterministic(self):
        cfg = IndexConfig()
        assert cfg.fingerprint == cfg.fingerprint

    def test_different_configs_different_fingerprints(self):
        a = IndexConfig(max_file_size_bytes=100)
        b = IndexConfig(max_file_size_bytes=200)
        assert a.fingerprint != b.fingerprint

    def test_fingerprint_is_hex(self):
        import re
        fp = IndexConfig().fingerprint
        assert re.match(r"^[0-9a-f]{64}$", fp)


class TestProjectDirectory:
    def test_valid_project_id(self):
        cfg = IndexConfig()
        result = cfg.project_directory("myproject")
        assert result.name == "myproject"
        assert "projects" in str(result)

    def test_empty_project_id_raises(self):
        with pytest.raises(ValueError, match="Invalid project identifier"):
            IndexConfig().project_directory("")

    def test_slash_in_project_id_raises(self):
        with pytest.raises(ValueError, match="Invalid project identifier"):
            IndexConfig().project_directory("foo/bar")

    def test_backslash_in_project_id_raises(self):
        with pytest.raises(ValueError, match="Invalid project identifier"):
            IndexConfig().project_directory("foo\\bar")


class TestFromEnvironment:
    def test_default_from_env(self, monkeypatch):
        monkeypatch.delenv("CODE_INDEX_MCP_INDEX_ROOT", raising=False)
        monkeypatch.delenv("CODE_INDEX_MCP_MAX_FILE_SIZE", raising=False)
        monkeypatch.delenv("CODE_INDEX_MCP_RELATIONSHIPS", raising=False)
        monkeypatch.delenv("CODE_INDEX_MCP_EMBEDDINGS", raising=False)
        monkeypatch.delenv("CODE_INDEX_MCP_SUMMARIES", raising=False)
        monkeypatch.delenv("CODE_INDEX_MCP_WATCHER", raising=False)
        cfg = IndexConfig.from_environment()
        assert cfg.enable_relationships is True
        assert cfg.enable_embeddings is False

    def test_custom_index_root(self, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_MCP_INDEX_ROOT", "/tmp/test-index")
        cfg = IndexConfig.from_environment()
        assert "test-index" in str(cfg.index_root)

    def test_env_bool_true_values(self, monkeypatch):
        for val in ("1", "true", "yes", "on", "TRUE", "Yes"):
            monkeypatch.setenv("CODE_INDEX_MCP_EMBEDDINGS", val)
            cfg = IndexConfig.from_environment()
            assert cfg.enable_embeddings is True

    def test_env_bool_false_values(self, monkeypatch):
        for val in ("0", "false", "no", "off", "FALSE", "No"):
            monkeypatch.setenv("CODE_INDEX_MCP_EMBEDDINGS", val)
            cfg = IndexConfig.from_environment()
            assert cfg.enable_embeddings is False

    def test_env_bool_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_MCP_EMBEDDINGS", "maybe")
        with pytest.raises(ValueError, match="Invalid boolean"):
            IndexConfig.from_environment()

    def test_env_max_file_size(self, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_MCP_MAX_FILE_SIZE", "2048")
        cfg = IndexConfig.from_environment()
        assert cfg.max_file_size_bytes == 2048

    def test_env_watcher(self, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_MCP_WATCHER", "true")
        cfg = IndexConfig.from_environment()
        assert cfg.enable_watcher is True

    def test_env_summaries(self, monkeypatch):
        monkeypatch.setenv("CODE_INDEX_MCP_SUMMARIES", "1")
        cfg = IndexConfig.from_environment()
        assert cfg.enable_summaries is True


class TestEnvBool:
    def test_none_returns_default(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert _env_bool("TEST_BOOL", True) is True
        assert _env_bool("TEST_BOOL", False) is False

    def test_valid_true(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "true")
        assert _env_bool("TEST_BOOL", False) is True

    def test_valid_false(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "false")
        assert _env_bool("TEST_BOOL", True) is False

    def test_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "invalid")
        with pytest.raises(ValueError, match="Invalid boolean"):
            _env_bool("TEST_BOOL", False)


class TestLoggingDefaults:
    def test_environment_defaults_to_info(self, monkeypatch):
        monkeypatch.delenv("CODE_INDEX_MCP_DEV", raising=False)
        assert IndexConfig.from_environment().dev_mode is False

    def test_color_formatter_does_not_mutate_levelname(self):
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "message",
            (),
            None,
        )
        formatter = ColorFormatter("%(levelname)s %(message)s")

        formatted = formatter.format(record)

        assert "\033[" in formatted
        assert record.levelname == "INFO"
