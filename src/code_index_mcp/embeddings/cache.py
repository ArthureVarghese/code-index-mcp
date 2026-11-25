from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from code_index_mcp.storage.repositories import utc_now

EmbeddingEntry = tuple[str, str, str, str, str, str, str, str, str]


def embedding_cache_key(content_hash: str, provider: str, model: str, version: str) -> str:
    return f"emb:{content_hash}:{provider}:{model}:{version}"


class EmbeddingCache:
    def __init__(
        self,
        repositories: Any,
        provider: Any,
    ):
        self.repositories = repositories
        self.provider = provider

    def get_or_create(
        self,
        content_hash: str,
        text: str,
        document_id: str = "",
    ) -> list[float]:
        cached = self.repositories.get_embedding(
            content_hash,
            self.provider.provider_name,
            self.provider.model_name,
            self.provider.version,
        )

        if cached is not None:
            return cached

        vector = self.provider.embed_one(text)

        self.repositories.store_embedding(
            content_hash,
            self.provider.provider_name,
            self.provider.model_name,
            self.provider.version,
            vector,
            document_id=document_id,
        )

        return vector

    def is_cached(self, content_hash: str) -> bool:
        return self.repositories.get_embedding(
            content_hash,
            self.provider.provider_name,
            self.provider.model_name,
            self.provider.version,
        ) is not None

    def prepare_many(
        self,
        items: Sequence[tuple[str, str, str]],
    ) -> tuple[list[list[float]], list[EmbeddingEntry], int, int]:
        """Resolve cache hits and provider misses without writing to storage."""
        provider = self.provider.provider_name
        model = self.provider.model_name
        version = self.provider.version
        keys = [
            embedding_cache_key(content_hash, provider, model, version)
            for content_hash, _, _ in items
        ]
        cached = self.repositories.get_embeddings_by_cache_keys(keys)

        missing = [index for index, key in enumerate(keys) if key not in cached]
        vectors = self.provider.embed([items[index][1] for index in missing]) if missing else []

        entries: list[EmbeddingEntry] = []
        results: list[list[float] | None] = [cached.get(key) for key in keys]
        for index, vector in zip(missing, vectors, strict=True):
            content_hash, _, document_id = items[index]
            results[index] = vector
            entries.append(
                (
                    keys[index],
                    self.repositories._current_project_id,
                    document_id,
                    content_hash,
                    provider,
                    model,
                    version,
                    json.dumps(vector),
                    utc_now(),
                )
            )

        return (
            [vector for vector in results if vector is not None],
            entries,
            len(items) - len(missing),
            len(missing),
        )

    def store_many(self, entries: list[EmbeddingEntry]) -> None:
        self.repositories.store_embeddings(entries)

    def get_or_create_many(
        self,
        items: Sequence[tuple[str, str, str]],
    ) -> tuple[list[list[float]], int, int]:
        vectors, entries, reused, recomputed = self.prepare_many(items)
        self.store_many(entries)
        return vectors, reused, recomputed
