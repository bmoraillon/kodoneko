"""
Mock minimal de l'API tree-sitter pour permettre les tests sans tree-sitter
installé. Construit manuellement les nœuds qu'on souhaite tester.

NE PAS UTILISER EN PRODUCTION. Sert uniquement aux tests unitaires.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MockNode:
    """Mime un nœud tree-sitter avec les attributs essentiels."""
    type: str
    children: list = field(default_factory=list)
    start_point: tuple = (0, 0)
    end_point: tuple = (0, 0)
    text: bytes = b""
    fields: dict = field(default_factory=dict)

    @property
    def named_children(self):
        """Enfants nommés (par convention : pas de ponctuation pure)."""
        return [
            c for c in self.children
            if c.type not in {
                ",", ";", "(", ")", "{", "}", "[", "]", ":",
                "=>", "->", "?", "..."
            }
        ]

    def child_by_field_name(self, name: str):
        return self.fields.get(name)


@dataclass
class MockTree:
    root_node: MockNode


# Helpers pour construire des arbres facilement

def node(type_, *children, line=0, col=0, end_line=None, end_col=None,
         text=b"", **fields):
    """Crée un nœud rapidement."""
    if end_line is None:
        end_line = line
    if end_col is None:
        end_col = col + len(text) if text else col
    n = MockNode(
        type=type_,
        children=list(children),
        start_point=(line, col),
        end_point=(end_line, end_col),
        text=text,
    )
    if fields:
        n.fields = fields
    return n


def ident(name: str, line=0) -> MockNode:
    """Raccourci : crée un nœud `identifier`."""
    return node("identifier", line=line, text=name.encode("utf-8"))


def num(value, line=0) -> MockNode:
    """Raccourci : crée un nœud `integer`."""
    return node("integer", line=line, text=str(value).encode("utf-8"))


def string(value: str, line=0) -> MockNode:
    """Raccourci : crée un nœud `string`."""
    return node("string", line=line, text=value.encode("utf-8"))


def comment(value: str, line=0, end_line=None) -> MockNode:
    """Raccourci : crée un nœud `comment`."""
    if end_line is None:
        end_line = line
    return node("comment", line=line, end_line=end_line, text=value.encode("utf-8"))
