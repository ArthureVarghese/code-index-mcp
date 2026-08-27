from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CacheStats:
    files_seen: int = 0
    files_changed: int = 0
    files_reused: int = 0
    files_parsed: int = 0
    entities_reused: int = 0
    entities_recomputed: int = 0
    embeddings_reused: int = 0
    embeddings_recomputed: int = 0
    summaries_reused: int = 0
    summaries_recomputed: int = 0

    @property
    def entity_hit_ratio(self) -> float:
        total = self.entities_reused + self.entities_recomputed
        return self.entities_reused / total if total else 1.0

    @property
    def file_hit_ratio(self) -> float:
        total = self.files_reused + self.files_parsed
        return self.files_reused / total if total else 1.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "files_seen": self.files_seen,
            "files_changed": self.files_changed,
            "files_reused": self.files_reused,
            "files_parsed": self.files_parsed,
            "entities_reused": self.entities_reused,
            "entities_recomputed": self.entities_recomputed,
            "embeddings_reused": self.embeddings_reused,
            "embeddings_recomputed": self.embeddings_recomputed,
            "summaries_reused": self.summaries_reused,
            "summaries_recomputed": self.summaries_recomputed,
            "entity_hit_ratio": self.entity_hit_ratio,
            "file_hit_ratio": self.file_hit_ratio,
        }
