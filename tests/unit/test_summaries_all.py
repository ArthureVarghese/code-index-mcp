from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_index_mcp.summaries.cache import SummaryCache, summary_cache_key
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

    def test_summarize_many_defaults_to_loop(self):
        assert ConcreteSummaryProvider().summarize_many(
            ["hello", "world"], [{}, {}]
        ) == ["summary of hello", "summary of world"]


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

    def test_prepare_many_batches_misses_and_reports_counts(self):
        key1 = summary_cache_key("sh1", "test", "test-model", "1", "1")
        repos = MagicMock()
        repos.get_summaries_by_cache_keys.return_value = {key1: "cached"}
        provider = MagicMock(
            provider_name="test",
            model_name="test-model",
            version="1",
            prompt_version="1",
        )
        provider.summarize_many.return_value = ["s2", "s3"]
        cache = SummaryCache(repos, provider)

        summaries, entries, reused, recomputed = cache.prepare_many(
            [
                ("sh1", "mh1", "first", {}, "e1"),
                ("sh2", "mh2", "second", {}, "e2"),
                ("sh3", "mh3", "third", {}, "e3"),
            ]
        )

        assert summaries == ["cached", "s2", "s3"]
        assert len(entries) == 2
        assert (reused, recomputed) == (1, 2)
        provider.summarize_many.assert_called_once_with(
            ["second", "third"], [{}, {}]
        )
        repos.store_summaries.assert_not_called()

    def test_cache_key_includes_version(self):
        assert summary_cache_key("h", "p", "m", "1", "1") != summary_cache_key(
            "h", "p", "m", "2", "1"
        )
