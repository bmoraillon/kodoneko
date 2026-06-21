"""
setup_paths — Configuration des chemins d'import pour les notebooks.

Rend `kodoneko_metrics`, `kodoneko_scanner` et `kodoneko_temporal`
importables sans `pip install`.

Usage :
    import setup_paths; setup_paths.setup()
    from kodoneko_metrics import CodeAnalyzer, analyze
    from kodoneko_temporal import Classifier, load_changelog_config

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


_REQUIRED_SUBDIRS = ("kodoneko_metrics", "kodoneko_scanner", "kodoneko_temporal")


def find_project_root(start: Optional[Path] = None) -> Path:
    """Trouve la racine en remontant les parents jusqu'à voir les modules."""
    if start is None:
        start = Path(__file__).resolve().parent

    candidate = start
    for _ in range(6):
        if all((candidate / sub).is_dir() for sub in _REQUIRED_SUBDIRS):
            return candidate
        if candidate.parent == candidate:
            break
        candidate = candidate.parent

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents)[:5]:
        if all((parent / sub).is_dir() for sub in _REQUIRED_SUBDIRS):
            return parent

    raise RuntimeError(
        f"Impossible de trouver la racine contenant {_REQUIRED_SUBDIRS}. "
        "Lance setup(root=Path('...')) explicitement."
    )


def setup(root: Optional[Path] = None, verbose: bool = True) -> Path:
    """Configure sys.path pour rendre les modules importables."""
    if root is None:
        root = find_project_root()
    else:
        root = Path(root).resolve()

    added = []
    for sub in _REQUIRED_SUBDIRS:
        src_path = root / sub / "src"
        src_str = str(src_path)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)
            added.append(src_str)

    if verbose:
        print(f"📁 Racine du projet : {root}")
        if added:
            print(f"✓ {len(added)} chemin(s) ajouté(s) à sys.path")
            for p in added:
                rel = Path(p).relative_to(root)
                print(f"   • {rel}")
        else:
            print("✓ Chemins déjà configurés")
        _print_status()

    return root


def _print_status() -> None:
    print()
    print("📦 Modules :")
    for name in _REQUIRED_SUBDIRS:
        try:
            mod = __import__(name)
            version = getattr(mod, "__version__", "?")
            print(f"   ✓ {name} (v{version})")
        except ImportError as e:
            print(f"   ✗ {name} : {e}")

    print()
    print("🔧 Grammaires tree-sitter :")
    grammars = [
        ("tree_sitter", "tree-sitter (core)"),
        ("tree_sitter_python", "Python"),
        ("tree_sitter_typescript", "TypeScript/TSX"),
        ("tree_sitter_javascript", "JavaScript"),
    ]
    for module_name, label in grammars:
        try:
            __import__(module_name)
            print(f"   ✓ {label}")
        except ImportError:
            print(f"   ✗ {label} (non installé)")


if __name__ in ("__main__", "__builtin__"):
    setup()
