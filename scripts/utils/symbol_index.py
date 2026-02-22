#!/usr/bin/env python3
from __future__ import annotations
import ast
from dataclasses import dataclass
from typing import List

@dataclass
class SymbolSpan:
    name: str
    kind: str
    start_line: int
    end_line: int

def index_python_symbols(source: str) -> List[SymbolSpan]:
    tree = ast.parse(source)
    spans: List[SymbolSpan] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if isinstance(getattr(node, "lineno", None), int) and isinstance(getattr(node, "end_lineno", None), int):
                spans.append(SymbolSpan(node.name, "function", node.lineno, node.end_lineno))
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if isinstance(getattr(node, "lineno", None), int) and isinstance(getattr(node, "end_lineno", None), int):
                spans.append(SymbolSpan(node.name, "function", node.lineno, node.end_lineno))
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if isinstance(getattr(node, "lineno", None), int) and isinstance(getattr(node, "end_lineno", None), int):
                spans.append(SymbolSpan(node.name, "class", node.lineno, node.end_lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return spans
