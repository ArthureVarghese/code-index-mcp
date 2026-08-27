from __future__ import annotations

import re
from typing import Any


class SearchRanker:
    """Deterministic ranking for agent-oriented search."""

    def rank(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = query.strip().lower()
        terms = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", normalized))

        ranked = []

        for result in results:
            score = float(result.get("score", 0.0))
            name = str(result.get("name", "")).lower()
            path = str(result.get("path", "")).lower()
            text = str(result.get("text", "")).lower()
            reasons: list[str] = []

            if name == normalized:
                score += 100.0
                reasons.append("exact name match")
            elif normalized and normalized in name:
                score += 50.0
                reasons.append("name contains query")

            if normalized in path:
                score += 20.0
                reasons.append("path match")

            for term in terms:
                if term in name:
                    score += 10.0
                elif term in text:
                    score += 2.0

            if not reasons:
                reasons.append("content match")

            result = dict(result)
            result["score"] = round(score, 4)
            result["match_reason"] = "; ".join(reasons)
            ranked.append(result)

        return sorted(
            ranked,
            key=lambda item: (
                -float(item["score"]),
                str(item.get("path", "")),
                str(item.get("name", "")),
            ),
        )
