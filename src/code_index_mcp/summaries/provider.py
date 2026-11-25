from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class SummaryProvider(ABC):
    provider_name = "unknown"
    model_name = "unknown"
    version = "1"
    prompt_version = "1"

    @abstractmethod
    def summarize(self, text: str, metadata: dict) -> str:
        raise NotImplementedError

    def summarize_many(
        self, texts: Sequence[str], metadata: Sequence[dict]
    ) -> list[str]:
        return [
            self.summarize(text, meta)
            for text, meta in zip(texts, metadata, strict=True)
        ]
