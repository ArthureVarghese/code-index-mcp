from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable
from typing import Any

_WHITESPACE_RE = re.compile(r"[ \t]+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", errors="replace"))


def exact_source_hash(source: str) -> str:
    return sha256_text(source)


def normalize_python_source(source: str) -> str:
    """Normalize Python source for semantic comparison.

    AST-based normalization intentionally ignores comments and formatting while
    preserving meaningful syntax and values.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError):
        return _normalize_fallback(source)

    try:
        return ast.dump(
            tree,
            annotate_fields=True,
            include_attributes=False,
        )
    except Exception:
        return _normalize_fallback(source)


def _normalize_fallback(source: str) -> str:
    lines: list[str] = []

    for line in source.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        lines.append(_WHITESPACE_RE.sub(" ", stripped))

    return "\n".join(lines)


def semantic_hash_python(source: str) -> str:
    return sha256_text(normalize_python_source(source))


def semantic_hash(source: str) -> str:
    """Generic semantic hash.

    Python source is normalized through the AST when possible. Other text is
    normalized conservatively.
    """
    return semantic_hash_python(source)


def structural_hash(
    *,
    entity_type: str,
    name: str,
    qualified_name: str,
    signature: str | None,
    decorators: Iterable[str],
    child_ids: Iterable[str],
) -> str:
    payload = "\x1e".join(
        [
            entity_type,
            name,
            qualified_name,
            signature or "",
            *sorted(decorators),
            "--children--",
            *sorted(child_ids),
        ]
    )

    return sha256_text(payload)


def entity_content_hash(
    *,
    normalized_source: str,
    structural_metadata: dict[str, Any],
) -> str:
    import json

    metadata = json.dumps(
        structural_metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return sha256_text(f"{normalized_source}\x1e{metadata}")
