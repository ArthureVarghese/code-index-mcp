from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest

from code_index_mcp.embeddings.cache import EmbeddingCache, embedding_cache_key
from code_index_mcp.embeddings.provider import EmbeddingProvider


class ConcreteEmbeddingProvider(EmbeddingProvider):
    provider_name = "test"
    model_name = "test-model"
    version = "1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]


class TestEmbeddingProvider:
    def test_embed_one(self):
        provider = ConcreteEmbeddingProvider()
        result = provider.embed_one("hello")
        assert result == [5.0]

    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()

    def test_default_class_attrs(self):
        assert EmbeddingProvider.provider_name == "unknown"
        assert EmbeddingProvider.model_name == "unknown"
        assert EmbeddingProvider.version == "1"


class TestEmbeddingCache:
    def test_cache_miss_calls_provider(self):
        repos = MagicMock()
        repos.get_embedding.return_value = None
        provider = ConcreteEmbeddingProvider()
        cache = EmbeddingCache(repos, provider)

        result = cache.get_or_create("hash1", "hello")
        assert result == [5.0]
        repos.store_embedding.assert_called_once()

    def test_cache_hit_returns_cached(self):
        repos = MagicMock()
        repos.get_embedding.return_value = [99.0]
        provider = ConcreteEmbeddingProvider()
        cache = EmbeddingCache(repos, provider)

        result = cache.get_or_create("hash1", "hello")
        assert result == [99.0]
        repos.store_embedding.assert_not_called()

    def test_prepare_many_batches_misses_and_reports_counts(self):
        key1 = embedding_cache_key("h1", "test", "test-model", "1")
        repos = MagicMock()
        repos.get_embeddings_by_cache_keys.return_value = {key1: [9.0]}
        provider = MagicMock(
            provider_name="test", model_name="test-model", version="1"
        )
        provider.embed.return_value = [[2.0], [3.0]]
        cache = EmbeddingCache(repos, provider)

        vectors, entries, reused, recomputed = cache.prepare_many(
            [("h1", "first", "e1"), ("h2", "second", "e2"), ("h3", "third", "e3")]
        )

        assert vectors == [[9.0], [2.0], [3.0]]
        assert len(entries) == 2
        assert (reused, recomputed) == (1, 2)
        provider.embed.assert_called_once_with(["second", "third"])
        repos.store_embeddings.assert_not_called()

    def test_cache_key_includes_version(self):
        assert embedding_cache_key("h", "p", "m", "1") != embedding_cache_key(
            "h", "p", "m", "2"
        )


class TestEmbeddingProviderAbstract:
    def test_embed_raises(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()
