from __future__ import annotations

from abc import ABC, abstractmethod


class SummaryProvider(ABC):
    provider_name = "unknown"
    model_name = "unknown"
    version = "1"
    prompt_version = "1"

    @abstractmethod
    def summarize(self, text: str, metadata: dict) -> str:
        raise NotImplementedError
