from __future__ import annotations

from typing import Any


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
