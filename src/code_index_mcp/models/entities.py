from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EntityType(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    NESTED_FUNCTION = "nested_function"
    NESTED_CLASS = "nested_class"
    DECORATOR = "decorator"
    IMPORT = "import"
    FROM_IMPORT = "from_import"
    VARIABLE = "variable"
    CONSTANT = "constant"
    PROPERTY = "property"
    TEST = "test"
    MARKDOWN_DOCUMENT = "markdown_document"
    MARKDOWN_SECTION = "markdown_section"


class SourceKind(StrEnum):
    PYTHON = "python"
    MARKDOWN = "markdown"


class RelationshipKind(StrEnum):
    IMPORTS = "imports"
    DEFINES = "defines"
    CONTAINS = "contains"
    CALLS = "calls"
    REFERENCES = "references"
    INHERITS = "inherits"
    DECORATED_BY = "decorated_by"
    TESTS = "tests"
    DOCUMENTS = "documents"


class RelationshipConfidence(StrEnum):
    EXACT = "exact"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class SourceRange:
    start_line: int
    end_line: int
    start_column: int
    end_column: int

    def __post_init__(self) -> None:
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")

        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")

        if self.start_column < 0 or self.end_column < 0:
            raise ValueError("columns cannot be negative")

    def to_dict(self) -> dict[str, int]:
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_column": self.start_column,
            "end_column": self.end_column,
        }


@dataclass(frozen=True, slots=True)
class Entity:
    """A stable logical source entity.

    ``entity_id`` identifies the logical entity.
    ``content_hash`` identifies the current content/version.

    Convenience properties such as ``title`` and ``start_line`` preserve the
    API previously exposed by specialized entity models.
    """

    entity_id: str
    project_id: str
    file_id: str
    source_kind: SourceKind
    entity_type: EntityType
    name: str
    qualified_name: str
    parent_id: str | None
    source_range: SourceRange
    content_hash: str
    exact_source_hash: str
    semantic_hash: str
    structural_hash: str
    source: str
    docstring: str | None = None
    signature: str | None = None
    decorators: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def start_line(self) -> int:
        """Start line of the entity's source range."""
        return self.source_range.start_line

    @property
    def end_line(self) -> int:
        """End line of the entity's source range."""
        return self.source_range.end_line

    @property
    def start_column(self) -> int:
        """Start column of the entity's source range."""
        return self.source_range.start_column

    @property
    def end_column(self) -> int:
        """End column of the entity's source range."""
        return self.source_range.end_column

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "project_id": self.project_id,
            "file_id": self.file_id,
            "source_kind": self.source_kind.value,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "parent_id": self.parent_id,
            "source_range": self.source_range.to_dict(),
            "content_hash": self.content_hash,
            "exact_source_hash": self.exact_source_hash,
            "semantic_hash": self.semantic_hash,
            "structural_hash": self.structural_hash,
            "source": self.source,
            "docstring": self.docstring,
            "signature": self.signature,
            "decorators": list(self.decorators),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class Relationship:
    relationship_id: str
    project_id: str
    source_entity_id: str
    target_entity_id: str | None
    kind: RelationshipKind
    confidence: RelationshipConfidence
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "project_id": self.project_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "kind": self.kind.value,
            "confidence": self.confidence.value,
            "metadata": self.metadata,
        }
