"""
CosmicAnalyzer — analyse COSMIC d'un fichier source.

Réutilise le parser tree-sitter de :class:`CodeAnalyzer` pour ne pas
dupliquer la logique de chargement des grammaires. Dispatche vers le
détecteur du bon langage selon le fichier analysé.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..analyzer import CodeAnalyzer
from ..detect import detect_language
from .models import CosmicFileReport, CosmicMode, CosmicMovement
from .patterns import java as patterns_java
from .patterns import javascript as patterns_javascript
from .patterns import python_ast as patterns_python_ast


def _detect_python_ast_wrapper(tree, source_bytes, file_path, *, mode):
    """Wrapper qui ignore le `tree` (calculé par tree-sitter) et utilise
    le détecteur ast stdlib à la place. Utilisé quand tree-sitter n'est
    pas installé ou pour Python où ast stdlib est suffisant."""
    return patterns_python_ast.detect_python_movements_ast(
        source_bytes, file_path, mode=mode,
    )


# Mapping langage → fonction de détection.
# Python : module ast stdlib (sans tree-sitter requis), via _DETECTORS_NATIVE.
# JavaScript / TypeScript / TSX / Java : tree-sitter.
# Le même détecteur sert pour JS et TS (TS = JS + annotations de types).
_DETECTORS_TS = {
    "javascript": patterns_javascript.detect_javascript_movements,
    "typescript": patterns_javascript.detect_javascript_movements,
    "tsx": patterns_javascript.detect_javascript_movements,
    "java": patterns_java.detect_java_movements,
    # "csharp": patterns_csharp.detect_csharp_movements,  # phase 2a
    # "go": patterns_go.detect_go_movements,  # phase 2b
}

# Détecteurs sans tree-sitter (fallback ou implémentation principale)
_DETECTORS_NATIVE = {
    "python": _detect_python_ast_wrapper,
}

_SUPPORTED = set(_DETECTORS_TS.keys()) | set(_DETECTORS_NATIVE.keys())


class CosmicAnalyzer:
    """Analyseur COSMIC réutilisant le parser de CodeAnalyzer.

    Paramètres
    ----------
    base : CodeAnalyzer, optionnel
        Instance de CodeAnalyzer à utiliser. Si ``None``, une nouvelle
        instance est créée. Recommandé : partager une instance entre
        plusieurs analyses pour bénéficier du cache de parsers.
    mode : "strict" | "practical", défaut "practical"
        - ``strict`` : aligné avec la spec COSMIC ISO/IEC 19761. Les
          calls HTTP sortants ne sont pas comptés.
        - ``practical`` : compte les calls HTTP sortants comme 1 Read
          (réponse) + 1 Write (requête), pour refléter l'effort
          technique réel d'intégration. Ce comportement diverge de
          la spec ISO et est documenté en tant que tel.

    Examples
    --------
    >>> from kodoneko_metrics.cosmic import CosmicAnalyzer
    >>> analyzer = CosmicAnalyzer(mode="practical")
    >>> report = analyzer.analyze_file("src/auth.py")
    >>> report.total_cfp
    7
    >>> report.by_type
    {'entry': 1, 'exit': 2, 'read': 3, 'write': 1}
    """

    SUPPORTED_LANGUAGES = tuple(sorted(_SUPPORTED))

    def __init__(
        self,
        base: Optional[CodeAnalyzer] = None,
        mode: CosmicMode = "practical",
    ):
        self.base = base if base is not None else CodeAnalyzer()
        self.mode = mode

    def supported_languages(self) -> list[str]:
        return sorted(_SUPPORTED)

    def analyze_file(
        self,
        path: str | Path,
        language: Optional[str] = None,
    ) -> CosmicFileReport:
        """Analyse un fichier source et retourne un :class:`CosmicFileReport`.

        Paramètres
        ----------
        path : str | Path
            Chemin du fichier à analyser.
        language : str, optionnel
            Forcer un langage spécifique. Si ``None``, détection automatique
            par extension et contenu.

        Returns
        -------
        CosmicFileReport
            Rapport contenant les mouvements détectés. Si le langage n'est
            pas supporté, retourne un rapport vide (pas d'erreur).
        """
        path = Path(path)
        src = path.read_bytes()

        # Détection langage
        if language is None:
            try:
                language = detect_language(src, hint_path=str(path))
            except Exception:
                return CosmicFileReport(path=str(path), language="unknown")

        if language is None or language not in _SUPPORTED:
            return CosmicFileReport(path=str(path), language=language or "unknown")

        movements = self._dispatch(language, src, str(path))
        return CosmicFileReport(
            path=str(path),
            language=language,
            movements=movements,
        )

    def analyze_source(
        self,
        source: str | bytes,
        language: str,
        file_path: str = "<inline>",
    ) -> CosmicFileReport:
        """Analyse un code source en mémoire (sans fichier sur disque).

        Utile pour les tests et pour analyser un diff.
        """
        if isinstance(source, str):
            source = source.encode("utf-8")

        if language not in _SUPPORTED:
            return CosmicFileReport(path=file_path, language=language)

        movements = self._dispatch(language, source, file_path)
        return CosmicFileReport(
            path=file_path,
            language=language,
            movements=movements,
        )

    def _dispatch(self, language: str, source_bytes: bytes, file_path: str) -> list:
        """Dispatche vers le détecteur disponible pour le langage.

        Stratégie :
        1. Tente le détecteur natif (sans tree-sitter) — utilisé pour Python.
        2. Sinon, tente tree-sitter via CodeAnalyzer.
        3. Si tree-sitter pas installé pour le langage, retourne liste vide
           et émet un warning unique (idempotent par langage).
        """
        # 1. Détecteur natif (pas de dépendance tree-sitter)
        native_fn = _DETECTORS_NATIVE.get(language)
        if native_fn is not None:
            return native_fn(None, source_bytes, file_path, mode=self.mode)

        # 2. Détecteur tree-sitter
        ts_fn = _DETECTORS_TS.get(language)
        if ts_fn is None:
            return []

        try:
            parser = self.base.get_parser(language)
        except Exception as e:
            # tree-sitter ou grammaire non installée. On signale (une seule fois
            # par langage) sur stderr et on retourne liste vide.
            if not hasattr(self, "_ts_warned"):
                self._ts_warned = set()
            if language not in self._ts_warned:
                import sys
                print(
                    f"[kodoneko_metrics.cosmic] tree-sitter indisponible pour "
                    f"{language!r} : {type(e).__name__}: {e}. "
                    f"Fichiers {language} ignorés. "
                    f"Installer : pip install tree-sitter tree-sitter-{language}",
                    file=sys.stderr,
                )
                self._ts_warned.add(language)
            return []

        try:
            tree = parser.parse(source_bytes)
        except Exception:
            return []

        return ts_fn(tree, source_bytes, file_path, mode=self.mode)
