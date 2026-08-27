from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PythonReference:
    source_name: str
    target_name: str
    kind: str
    confidence: str
    line: int


class PythonRelationshipAnalyzer(ast.NodeVisitor):
    """Conservative intra-file relationship extraction."""

    def __init__(self) -> None:
        self.current_scope: list[str] = []
        self.references: list[PythonReference] = []

    def analyze(self, tree: ast.AST) -> list[PythonReference]:
        self.current_scope.clear()
        self.references.clear()
        self.visit(tree)
        return list(self.references)

    @property
    def scope(self) -> str:
        return ".".join(self.current_scope)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            target = _name_of(base)
            if target:
                self.references.append(
                    PythonReference(
                        source_name=self.scope,
                        target_name=target,
                        kind="inherits",
                        confidence="exact",
                        line=node.lineno,
                    )
                )

        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        target = _name_of(node.func)

        if target:
            self.references.append(
                PythonReference(
                    source_name=self.scope,
                    target_name=target,
                    kind="calls",
                    confidence="exact",
                    line=node.lineno,
                )
            )

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.references.append(
                PythonReference(
                    source_name=self.scope,
                    target_name=node.id,
                    kind="references",
                    confidence="inferred",
                    line=node.lineno,
                )
            )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.references.append(
                PythonReference(
                    source_name=self.scope,
                    target_name=alias.name,
                    kind="imports",
                    confidence="exact",
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")

        for alias in node.names:
            target = f"{module}.{alias.name}".strip(".")

            self.references.append(
                PythonReference(
                    source_name=self.scope,
                    target_name=target,
                    kind="imports",
                    confidence="exact",
                    line=node.lineno,
                )
            )


def _name_of(node: ast.AST) -> str | None:
    try:
        return ast.unparse(node)
    except Exception:
        return None
