from __future__ import annotations

from typing import Any


class SummaryCache:
    def __init__(
        self,
        repositories: Any,
        provider: Any,
    ):
        self.repositories = repositories
        self.provider = provider

    def get_or_create(
        self,
        semantic_hash: str,
        metadata_hash: str,
        text: str,
        metadata: dict,
        document_id: str = "",
    ) -> str:
        cached = self.repositories.get_summary(
            semantic_hash=semantic_hash,
            metadata_hash=metadata_hash,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            version=self.provider.version,
            prompt_version=self.provider.prompt_version,
        )

        if cached is not None:
            return cached

        summary = self.provider.summarize(text, metadata)

        self.repositories.store_summary(
            semantic_hash=semantic_hash,
            metadata_hash=metadata_hash,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            version=self.provider.version,
            prompt_version=self.provider.prompt_version,
            summary=summary,
            document_id=document_id,
        )

        return summary

    def is_cached(self, semantic_hash: str, metadata_hash: str) -> bool:
        return self.repositories.get_summary(
            semantic_hash=semantic_hash,
            metadata_hash=metadata_hash,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            version=self.provider.version,
            prompt_version=self.provider.prompt_version,
        ) is not None
