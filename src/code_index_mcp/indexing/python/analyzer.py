from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

from ...indexing.hashing import (
    entity_content_hash,
    exact_source_hash,
    semantic_hash_ast,
    structural_hash,
)
from ...indexing.versions import PYTHON_ANALYZER_VERSION
from ...models.entities import Entity, EntityType, SourceKind, SourceRange

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PythonParseResult:
    entities: list[Entity]
    syntax_error: str | None
    tree: ast.AST | None = None

    @property
    def errors(self) -> list[str]:
        return [self.syntax_error] if self.syntax_error else []


class PythonAnalyzer:
    VERSION = PYTHON_ANALYZER_VERSION

    def analyze(
        self,
        source: str,
        relative_path: str,
        *,
        project_id: str = "",
        file_id: str | None = None,
    ) -> PythonParseResult:
        if file_id is None:
            file_id = relative_path

        logger.debug("PythonAnalyzer :: analyze :: analyzing %s", relative_path)

        try:
            tree = ast.parse(
                source,
                filename=relative_path,
                type_comments=True,
            )
        except (SyntaxError, ValueError, UnicodeError) as exc:
            logger.info("PythonAnalyzer :: analyze :: syntax error in %s: %s", relative_path, exc)
            return PythonParseResult(
                entities=[],
                syntax_error=f"{type(exc).__name__}: {exc}",
            )

        lines = source.splitlines(keepends=True)
        entities: list[Entity] = []

        module_name = Path(relative_path).stem

        module = Entity(
            entity_id=f"python:{relative_path}",
            project_id=project_id,
            file_id=file_id,
            source_kind=SourceKind.PYTHON,
            entity_type=EntityType.MODULE,
            name=module_name,
            qualified_name=module_name,
            parent_id=None,
            source_range=SourceRange(
                start_line=1,
                end_line=max(1, len(lines)),
                start_column=0,
                end_column=(len(lines[-1].rstrip("\r\n")) if lines else 0),
            ),
            content_hash=entity_content_hash(
                normalized_source=source,
                structural_metadata={
                    "kind": "module",
                    "path": relative_path,
                },
            ),
            exact_source_hash=exact_source_hash(source),
            semantic_hash=semantic_hash_ast(tree, source),
            structural_hash=structural_hash(
                entity_type="module",
                name=module_name,
                qualified_name=module_name,
                signature=None,
                decorators=(),
                child_ids=(),
            ),
            source=source,
            docstring=ast.get_docstring(tree),
            metadata={
                "analyzer_version": self.VERSION,
            },
        )

        entities.append(module)

        for node, parent, qualified_parent in self._walk_definitions(tree):
            entity = self._build_entity(
                node=node,
                parent=parent,
                qualified_parent=qualified_parent,
                project_id=project_id,
                file_id=file_id,
                relative_path=relative_path,
                source=source,
                lines=lines,
            )

            if entity is not None:
                entities.append(entity)

        return PythonParseResult(
            entities=entities,
            syntax_error=None,
            tree=tree,
        )

    def _walk_definitions(self, tree: ast.AST):
        stack: list[tuple[ast.AST, ast.AST | None, str]] = []

        for node in reversed(list(ast.iter_child_nodes(tree))):
            stack.append((node, tree, ""))

        while stack:
            node, parent, qualified_parent = stack.pop()

            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                yield node, parent, qualified_parent

                child_name = node.name
                child_qualified = (
                    f"{qualified_parent}.{child_name}" if qualified_parent else child_name
                )

                for child in reversed(list(ast.iter_child_nodes(node))):
                    stack.append((child, node, child_qualified))
            else:
                for child in reversed(list(ast.iter_child_nodes(node))):
                    stack.append((child, node, qualified_parent))

    def _build_entity(
        self,
        *,
        node: ast.AST,
        parent: ast.AST | None,
        qualified_parent: str,
        project_id: str,
        file_id: str,
        relative_path: str,
        source: str,
        lines: list[str],
    ) -> Entity | None:
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            return None

        name = node.name

        if isinstance(node, ast.AsyncFunctionDef):
            entity_type = (
                EntityType.METHOD if isinstance(parent, ast.ClassDef) else EntityType.ASYNC_FUNCTION
            )

        elif isinstance(node, ast.FunctionDef):
            if isinstance(parent, ast.ClassDef):
                entity_type = EntityType.CONSTRUCTOR if name == "__init__" else EntityType.METHOD
            else:
                entity_type = EntityType.FUNCTION

        else:
            entity_type = (
                EntityType.NESTED_CLASS
                if isinstance(
                    parent,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                else EntityType.CLASS
            )

        qualified_name = f"{qualified_parent}.{name}" if qualified_parent else name

        start_line = node.lineno
        end_line = getattr(node, "end_lineno", start_line)
        start_column = node.col_offset
        end_column = getattr(
            node,
            "end_col_offset",
            start_column,
        )

        source_text = _source_range(
            lines,
            start_line,
            end_line,
        )

        decorators = tuple(
            _expression_source(source, decorator)
            for decorator in getattr(
                node,
                "decorator_list",
                (),
            )
        )

        signature = _signature(node)
        semantic = semantic_hash_ast(node, source_text)

        structural = structural_hash(
            entity_type=entity_type.value,
            name=name,
            qualified_name=qualified_name,
            signature=signature,
            decorators=decorators,
            child_ids=(),
        )

        content = entity_content_hash(
            normalized_source=source_text,
            structural_metadata={
                "entity_type": entity_type.value,
                "name": name,
                "qualified_name": qualified_name,
                "signature": signature,
                "decorators": decorators,
            },
        )

        parent_id = (
            f"python:{relative_path}:{qualified_parent}"
            if qualified_parent
            else f"python:{relative_path}"
        )

        return Entity(
            entity_id=f"python:{relative_path}:{qualified_name}",
            project_id=project_id,
            file_id=file_id,
            source_kind=SourceKind.PYTHON,
            entity_type=entity_type,
            name=name,
            qualified_name=qualified_name,
            parent_id=parent_id,
            source_range=SourceRange(
                start_line=start_line,
                end_line=end_line,
                start_column=start_column,
                end_column=end_column,
            ),
            content_hash=content,
            exact_source_hash=exact_source_hash(source_text),
            semantic_hash=semantic,
            structural_hash=structural,
            source=source_text,
            docstring=ast.get_docstring(node),
            signature=signature,
            decorators=decorators,
            metadata={
                "analyzer_version": self.VERSION,
                "is_async": isinstance(
                    node,
                    ast.AsyncFunctionDef,
                ),
                "is_test": name.startswith("test_"),
            },
        )


def _source_range(
    lines: list[str],
    start_line: int,
    end_line: int,
) -> str:
    return "".join(lines[start_line - 1 : end_line])


def _expression_source(
    source: str,
    node: ast.AST,
) -> str:
    try:
        return ast.get_source_segment(source, node) or ast.unparse(node)
    except Exception:
        return type(node).__name__


def _signature(node: ast.AST) -> str | None:
    if not isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        ),
    ):
        return None

    try:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({ast.unparse(node.args)})"
    except Exception:
        return node.name
