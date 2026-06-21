"""
Patterns COSMIC par langage.

Chaque sous-module expose une fonction ``detect_<lang>_movements(tree,
source_bytes, file_path, *, mode)`` qui parcourt l'AST tree-sitter et
retourne une liste de :class:`CosmicMovement`.
"""
