"""
Détection automatique du langage.

Stratégie en cascade :
1. Extension de fichier (si disponible)
2. Shebang (`#!/usr/bin/env python3`)
3. Heuristiques de contenu

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import os
import re
from typing import Optional

from ._input import SourceInput, normalize_input


# ---------------------------------------------------------------------------
# Mapping extension → langage canonique
# ---------------------------------------------------------------------------

# Le nom retourné correspond à un parser tree-sitter installable.
_EXTENSION_MAP: dict[str, str] = {
    # Python
    ".py": "python", ".pyi": "python", ".pyw": "python",
    # JavaScript / TypeScript
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    # Systèmes
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    # Scripting
    ".rb": "ruby",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
}


_SHEBANG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^#!.*\bpython[0-9.]*\b"), "python"),
    (re.compile(r"^#!.*\bnode\b"), "javascript"),
    (re.compile(r"^#!.*\b(bash|sh|zsh)\b"), "bash"),
    (re.compile(r"^#!.*\bruby\b"), "ruby"),
]


_CONTENT_HEURISTICS: list[tuple[str, re.Pattern, int]] = [
    # Python
    ("python", re.compile(r"^\s*def\s+\w+\s*\(", re.MULTILINE), 3),
    ("python", re.compile(r"^\s*class\s+\w+(\([^)]*\))?\s*:", re.MULTILINE), 3),
    ("python", re.compile(r"^\s*from\s+\S+\s+import\s+", re.MULTILINE), 3),
    ("python", re.compile(r"^\s*import\s+\w+\s*$", re.MULTILINE), 2),
    # TypeScript (annotations explicites)
    ("typescript", re.compile(r"^\s*interface\s+\w+\s*\{", re.MULTILINE), 4),
    ("typescript", re.compile(r"^\s*type\s+\w+\s*=", re.MULTILINE), 4),
    ("typescript", re.compile(r":\s*(string|number|boolean|void|any|unknown)\b"), 3),
    # JavaScript
    ("javascript", re.compile(r"^\s*function\s+\w+\s*\(", re.MULTILINE), 2),
    ("javascript", re.compile(r"^\s*const\s+\w+\s*=", re.MULTILINE), 2),
    ("javascript", re.compile(r"^\s*let\s+\w+\s*=", re.MULTILINE), 2),
    ("javascript", re.compile(r"=>\s*[\{(]"), 3),
    ("javascript", re.compile(r"^\s*export\s+(default\s+)?", re.MULTILINE), 2),
    ("javascript", re.compile(r"^\s*import\s+.+\s+from\s+['\"]", re.MULTILINE), 3),
    # Rust
    ("rust", re.compile(r"^\s*fn\s+\w+\s*\(", re.MULTILINE), 3),
    ("rust", re.compile(r"^\s*let\s+(mut\s+)?\w+\s*:", re.MULTILINE), 3),
    ("rust", re.compile(r"\bimpl\s+\w+\s+for\s+\w+"), 4),
    # Go
    ("go", re.compile(r"^\s*func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\s*\(", re.MULTILINE), 3),
    ("go", re.compile(r"^\s*package\s+\w+\s*$", re.MULTILINE), 4),
]


def detect_language(
    source: SourceInput,
    *,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> Optional[str]:
    """Détecte le langage d'un fragment de code ou d'un fichier.

    Retourne le nom canonique du langage ("python", "typescript", ...)
    ou None si la détection échoue.
    """
    # Cas spécial : chaîne courte sans \n qui ressemble à un chemin
    if isinstance(source, str) and "\n" not in source and len(source) < 4096:
        ext_lang = _detect_by_extension(source)
        if ext_lang is not None:
            return ext_lang

    text, detected_path = normalize_input(
        source, encoding=encoding, treat_str_as="auto",
    )
    path = hint_path or detected_path

    if path is not None:
        lang = _detect_by_extension(path)
        if lang is not None:
            return lang

    lang = _detect_by_shebang(text)
    if lang is not None:
        return lang

    return _detect_by_content(text)


def _detect_by_extension(path: str) -> Optional[str]:
    _, ext = os.path.splitext(path)
    return _EXTENSION_MAP.get(ext.lower())


def _detect_by_shebang(text: str) -> Optional[str]:
    if not text.startswith("#!"):
        return None
    first_line = text.split("\n", 1)[0]
    for pattern, lang in _SHEBANG_PATTERNS:
        if pattern.match(first_line):
            return lang
    return None


def _detect_by_content(text: str, *, min_score: int = 3) -> Optional[str]:
    scores: dict[str, int] = {}
    for lang, pattern, weight in _CONTENT_HEURISTICS:
        if pattern.search(text):
            scores[lang] = scores.get(lang, 0) + weight
    if not scores:
        return None
    best_lang, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score < min_score:
        return None
    return best_lang


def supported_languages() -> list[str]:
    """Liste des langages dont la détection est possible (via extension,
    shebang ou heuristiques). Inclut les langages que tree-sitter ne sait
    pas forcément analyser — vérifier avec `CodeAnalyzer.supported_languages()`.
    """
    langs = set(_EXTENSION_MAP.values())
    langs.update(lang for lang, _, _ in _CONTENT_HEURISTICS)
    langs.update(lang for _, lang in _SHEBANG_PATTERNS)
    return sorted(langs)
