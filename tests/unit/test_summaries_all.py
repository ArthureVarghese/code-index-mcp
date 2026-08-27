from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.summaries.cache import SummaryCache
from code_index_mcp.summaries.provider import SummaryProvider


class ConcreteSummaryProvider(SummaryProvider):
    provider_name = "test"
    model_name = "test-model"
    version = "1"
    prompt_version = "1"

    def summarize(self, text: str, metadata: dict) -> str:
        return f"summary of {text[:10]}"


class TestSummaryProvider:
    def test_abstract(self):
        with pytest.raises(TypeError):
            SummaryProvider()

    def test_concrete(self):
        p = ConcreteSummaryProvider()
        assert p.summarize("hello world", {}) == "summary of hello worl"
        assert p.provider_name == "test"


class TestSummaryCache:
    def test_cache_miss(self):
        repos = MagicMock()
        repos.get_summary.return_value = None
        provider = ConcreteSummaryProvider()
        cache = SummaryCache(repos, provider)
        result = cache.get_or_create("sh", "mh", "text", {"k": "v"})
        assert result == "summary of text"
        repos.store_summary.assert_called_once()

    def test_cache_hit(self):
        repos = MagicMock()
        repos.get_summary.return_value = "cached summary"
        provider = ConcreteSummaryProvider()
        cache = SummaryCache(repos, provider)
        result = cache.get_or_create("sh", "mh", "text", {})
        assert result == "cached summary"
        repos.store_summary.assert_not_called()
