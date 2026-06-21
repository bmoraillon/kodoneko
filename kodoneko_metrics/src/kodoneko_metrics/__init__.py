"""
kodoneko-metrics — Métriques de qualité logicielle via tree-sitter.

API publique
============

**Classe principale** : `CodeAnalyzer`

    from kodoneko_metrics import CodeAnalyzer
    analyzer = CodeAnalyzer()
    r = analyzer.analyze("def f(): return 1", language="python")
    print(r.lines.ncloc, r.halstead.volume, r.mccabe.value)
    print(r.understandability.risk, r.understandability.cognitive)

L'instance garde un cache des grammaires tree-sitter chargées.

**Fonctions de convenance** (pour analyses ponctuelles) :

    from kodoneko_metrics import (
        analyze, count_lines, count_halstead, count_mccabe,
        count_understandability, count_understandability_by_function,
    )

**Modèles** :

    from kodoneko_metrics import (
        LineCounts, HalsteadMetrics, McCabeMetrics,
        UnderstandabilityMetrics, FunctionUnderstandability,
        CombinedMetrics,
    )

**Vocabulaire — score vs risk** :

Pour éviter toute confusion, KodoNeko distingue strictement deux notions :

- ``UnderstandabilityMetrics.risk`` (0-100) — **niveau de risque** au
  niveau d'un fichier. Plus c'est haut, plus le code est difficile à
  comprendre. *Pire si plus haut.*
- ``PrimaryQualityScore.score`` (0-100) — **indicateur de qualité globale**
  au niveau d'un dépôt (kodoneko_scanner). Plus c'est haut, mieux le
  dépôt se porte. *Mieux si plus haut.*

Cette asymétrie est volontaire : on garde le mot « score » pour ce qui
ressemble à une note (la qualité), et « risk » pour ce qui ressemble à
une alerte (la difficulté ressentie).

**Convention docstrings (v1.1+)** : les docstrings Python sont comptées
comme commentaires par défaut (cohérent spec UO KodoNeko). Pour le
comportement cloc-like, passer `exclude_docstrings=False`.

**Note v2.0** : `CognitiveMetrics` et `ReadabilityMetrics` ont été
fusionnées en `UnderstandabilityMetrics` (référence ISO/IEC 25010).
La valeur cognitive (Campbell) reste accessible via
`r.understandability.cognitive` pour comparabilité avec radon
et SonarSource.

**Note v2.1** : `UnderstandabilityMetrics.score` a été renommé en
`.risk` pour éviter la confusion avec `PrimaryQualityScore.score`. Idem
pour `FunctionUnderstandability.score`.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from typing import Optional

from ._input import SourceInput
from .analyzer import CodeAnalyzer
from .detect import detect_language, supported_languages
from .models import (
    CombinedMetrics,
    FunctionUnderstandability,
    HalsteadMetrics,
    LanguageDetectionFailed,
    LanguageNotSupported,
    LineCounts,
    McCabeMetrics,
    UnderstandabilityMetrics,
)

__version__ = "2.12.1"

__all__ = [
    # Classe principale
    "CodeAnalyzer",
    # Fonctions de convenance
    "analyze",
    "count_lines",
    "count_halstead",
    "count_mccabe",
    "count_understandability",
    "count_understandability_by_function",
    # Détection
    "detect_language",
    "supported_languages",
    # Modèles
    "LineCounts",
    "HalsteadMetrics",
    "McCabeMetrics",
    "UnderstandabilityMetrics",
    "FunctionUnderstandability",
    "CombinedMetrics",
    # Exceptions
    "LanguageNotSupported",
    "LanguageDetectionFailed",
    # Version
    "__version__",
]


# ---------------------------------------------------------------------------
# Fonctions de convenance
# ---------------------------------------------------------------------------

def analyze(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
    exclude_docstrings: bool = True,
) -> CombinedMetrics:
    """Calcule NCLOC + Halstead + McCabe + Understandability en une seule passe.

    Wrapper autour de `CodeAnalyzer().analyze()`.
    """
    return CodeAnalyzer().analyze(
        source, language=language, hint_path=hint_path,
        encoding=encoding, exclude_docstrings=exclude_docstrings,
    )


def count_lines(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
    exclude_docstrings: bool = True,
) -> LineCounts:
    """Compte les lignes (total, blank, comment, sloc, ncloc).

    Par défaut, les docstrings Python comptent comme commentaires.
    """
    return CodeAnalyzer().count_lines(
        source, language=language, hint_path=hint_path,
        encoding=encoding, exclude_docstrings=exclude_docstrings,
    )


def count_halstead(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> HalsteadMetrics:
    """Calcule les métriques Halstead."""
    return CodeAnalyzer().count_halstead(
        source, language=language, hint_path=hint_path, encoding=encoding,
    )


def count_mccabe(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> McCabeMetrics:
    """Calcule la complexité cyclomatique de McCabe."""
    return CodeAnalyzer().count_mccabe(
        source, language=language, hint_path=hint_path, encoding=encoding,
    )


def count_understandability(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> UnderstandabilityMetrics:
    """Calcule la compréhensibilité du code (ISO/IEC 25010).

    Retourne un ``UnderstandabilityMetrics`` dont l'attribut ``.risk``
    donne le niveau de risque composite 0-100 (plus haut = plus dur à
    comprendre). Combine 6 sous-métriques : cognitive (Campbell),
    longueur de fonction, profondeur d'imbrication, nombre de paramètres,
    densité visuelle, brièveté des identifiants.
    """
    return CodeAnalyzer().count_understandability(
        source, language=language, hint_path=hint_path, encoding=encoding,
    )


def count_understandability_by_function(
    source: SourceInput,
    *,
    language: Optional[str] = None,
    hint_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> list:
    """Retourne uniquement le détail par fonction, trié par risque décroissant."""
    return CodeAnalyzer().count_understandability_by_function(
        source, language=language, hint_path=hint_path, encoding=encoding,
    )
