from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest

from code_index_mcp.embeddings.cache import EmbeddingCache
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


class TestEmbeddingProviderAbstract:
    def test_embed_raises(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()
