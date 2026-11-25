from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from code_index_mcp.storage.repositories import utc_now

SummaryEntry = tuple[str, str, str, str, str, str, str, str, str, str]


def summary_cache_key(
    semantic_hash: str,
    provider: str,
    model: str,
    version: str,
    prompt_version: str,
) -> str:
    return f"sum:{semantic_hash}:{provider}:{model}:{version}:{prompt_version}"


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

    def prepare_many(
        self,
        items: Sequence[tuple[str, str, str, dict, str]],
    ) -> tuple[list[str], list[SummaryEntry], int, int]:
        """Resolve cache hits and provider misses without writing to storage."""
        provider = self.provider.provider_name
        model = self.provider.model_name
        version = self.provider.version
        prompt_version = self.provider.prompt_version
        keys = [
            summary_cache_key(semantic_hash, provider, model, version, prompt_version)
            for semantic_hash, _, _, _, _ in items
        ]
        cached = self.repositories.get_summaries_by_cache_keys(keys)

        missing = [index for index, key in enumerate(keys) if key not in cached]
        summaries = (
            self.provider.summarize_many(
                [items[index][2] for index in missing],
                [items[index][3] for index in missing],
            )
            if missing
            else []
        )

        entries: list[SummaryEntry] = []
        results: list[str | None] = [cached.get(key) for key in keys]
        for index, summary in zip(missing, summaries, strict=True):
            semantic_hash, metadata_hash, _, _, document_id = items[index]
            results[index] = summary
            entries.append(
                (
                    keys[index],
                    self.repositories._current_project_id,
                    document_id,
                    semantic_hash,
                    metadata_hash,
                    provider,
                    model,
                    prompt_version,
                    summary,
                    utc_now(),
                )
            )

        return (
            [summary for summary in results if summary is not None],
            entries,
            len(items) - len(missing),
            len(missing),
        )

    def store_many(self, entries: list[SummaryEntry]) -> None:
        self.repositories.store_summaries(entries)

    def get_or_create_many(
        self,
        items: Sequence[tuple[str, str, str, dict, str]],
    ) -> tuple[list[str], int, int]:
        summaries, entries, reused, recomputed = self.prepare_many(items)
        self.store_many(entries)
        return summaries, reused, recomputed
