"""
Modèles de données pour kodoneko_metrics.

Quatre familles de métriques :

- LineCounts : comptage de lignes (NCLOC, SLOC, blank, comment)
- HalsteadMetrics : métriques Halstead (n1, n2, N1, N2 + dérivées)
- McCabeMetrics : complexité cyclomatique
- UnderstandabilityMetrics : compréhensibilité du code (composite)
- CombinedMetrics : agrégation des quatre + métadonnées

La métrique **Understandability** fusionne ce qui était auparavant
`CognitiveMetrics` (Campbell 2017) et `ReadabilityMetrics` (FRD) en un
seul indicateur composite, aligné sur la sous-caractéristique
**Understandability** d'ISO/IEC 25010 (Usability).

La valeur cognitive brute (Campbell) est conservée en sous-attribut
(`understandability.cognitive`) pour préserver la comparabilité avec
les outils de l'écosystème (radon, SonarSource).

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Comptage de lignes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineCounts:
    """Résultat du comptage de lignes.

    Définitions (conformes à cloc / SonarQube) :

    - total   : lignes physiques totales (vides + commentaires + code)
    - blank   : lignes ne contenant que des espaces/tabulations
    - comment : lignes ne contenant qu'un commentaire (sans code mêlé)
    - sloc    : Source LOC = total - blank
    - ncloc   : Non-Comment LOC = total - blank - comment

    Une ligne `x = 1  # comment` compte comme NCLOC ET SLOC : elle porte
    du code, le commentaire est un bonus.

    Invariants :
    - sloc == total - blank
    - ncloc == sloc - comment
    - 0 <= ncloc <= sloc <= total
    """
    total: int
    blank: int
    comment: int
    sloc: int
    ncloc: int
    language: str
    backend: str

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"LineCounts({self.language}/{self.backend}: "
            f"total={self.total}, blank={self.blank}, "
            f"comment={self.comment}, sloc={self.sloc}, ncloc={self.ncloc})"
        )


# ---------------------------------------------------------------------------
# Halstead
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HalsteadMetrics:
    """Métriques Halstead d'un fragment de code.

    Définitions de base :

    - n1 : nombre d'opérateurs DISTINCTS
    - n2 : nombre d'opérandes DISTINCTS
    - N1 : nombre TOTAL d'occurrences d'opérateurs
    - N2 : nombre TOTAL d'occurrences d'opérandes

    Dérivées (propriétés calculées à la volée) :

    - vocabulary : n = n1 + n2
    - length     : N = N1 + N2
    - volume     : V = N · log2(n)
    - difficulty : D = (n1 / 2) · (N2 / n2)
    - effort     : E = D · V
    """
    n1: int = 0
    n2: int = 0
    N1: int = 0
    N2: int = 0
    language: str = ""
    backend: str = ""

    @property
    def vocabulary(self) -> int:
        return self.n1 + self.n2

    @property
    def length(self) -> int:
        return self.N1 + self.N2

    @property
    def volume(self) -> float:
        n = self.vocabulary
        if n <= 1:
            return 0.0
        return self.length * math.log2(n)

    @property
    def difficulty(self) -> float:
        if self.n2 == 0:
            return 0.0
        return (self.n1 / 2.0) * (self.N2 / self.n2)

    @property
    def effort(self) -> float:
        return self.difficulty * self.volume

    @property
    def estimated_bugs(self) -> float:
        """Estimation Halstead du nombre de bugs (V / 3000).

        Empirique et contestée — utile à titre indicatif seulement.
        """
        return self.volume / 3000.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["vocabulary"] = self.vocabulary
        d["length"] = self.length
        d["volume"] = round(self.volume, 4)
        d["difficulty"] = round(self.difficulty, 4)
        d["effort"] = round(self.effort, 4)
        d["estimated_bugs"] = round(self.estimated_bugs, 4)
        return d

    def __str__(self) -> str:
        return (
            f"HalsteadMetrics({self.language}/{self.backend}: "
            f"n1={self.n1}, n2={self.n2}, N1={self.N1}, N2={self.N2}, "
            f"V={self.volume:.2f}, D={self.difficulty:.2f})"
        )


# ---------------------------------------------------------------------------
# McCabe (complexité cyclomatique)
# ---------------------------------------------------------------------------

# Seuils standard issus de la littérature (NIST, Carnegie Mellon SEI) :
# - 1-10  : low      — code simple, faible risque
# - 11-20 : moderate — complexité modérée, surveillance recommandée
# - 21-50 : high     — complexité élevée, risque de bugs accru, refactoring conseillé
# - >50   : very_high — très complexe, refactoring fortement conseillé
_MCCABE_THRESHOLDS = [
    (10, "low"),
    (20, "moderate"),
    (50, "high"),
]


@dataclass(frozen=True)
class McCabeMetrics:
    """Métriques de complexité cyclomatique de McCabe.

    Définition standard :

        CC = 1 + (nombre de points de décision)

    Points de décision : `if`, `elif`, `for`, `while`, `case`, `except`,
    `&&`/`and`, `||`/`or`, ternaire `?:`, compréhensions, etc.

    Attributs
    ---------
    value : int
        Complexité cyclomatique totale (= 1 + decision_count).
    decision_count : int
        Nombre brut de points de décision détectés.
    level : str
        Qualification : "low" (≤10), "moderate" (≤20), "high" (≤50),
        "very_high" (>50). Selon les seuils NIST / Carnegie Mellon SEI.
    language : str
    backend : str
    """
    value: int = 1
    decision_count: int = 0
    level: str = "low"
    language: str = ""
    backend: str = ""

    @classmethod
    def from_decision_count(cls, decision_count: int, *,
                              language: str = "", backend: str = "") -> "McCabeMetrics":
        """Construit un McCabeMetrics à partir du nombre de décisions."""
        value = 1 + decision_count
        level = "very_high"
        for threshold, name in _MCCABE_THRESHOLDS:
            if value <= threshold:
                level = name
                break
        return cls(
            value=value,
            decision_count=decision_count,
            level=level,
            language=language,
            backend=backend,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"McCabeMetrics({self.language}/{self.backend}: "
            f"CC={self.value}, level={self.level})"
        )


# ===========================================================================
# Understandability (ISO/IEC 25010)
# ===========================================================================
#
# Fusion de ce qui était auparavant :
#   - CognitiveMetrics (Campbell, 2017)
#   - ReadabilityMetrics (FRD : First Read Difficulty)
#
# Référence normative : ISO/IEC 25010:2011, sous-caractéristique
# "Understandability" de Usability — "degree to which a product or
# system has attributes that enable users to easily understand
# whether it is appropriate".
#
# Implémentation : score composite 0-100 (plus haut = plus difficile)
# combinant 6 sous-métriques :
#
#   - cognitive (Campbell)   : complexité de contrôle, pénalise l'imbrication
#   - function_length        : longueur des fonctions
#   - nesting_depth          : profondeur maximale d'imbrication
#   - parameter_count        : nombre de paramètres
#   - line_density           : caractères/ligne non-vide (densité visuelle)
#   - identifier_length      : longueur des identifiants (inversée)
#
# La complexité cognitive de Campbell est conservée en sous-attribut
# (`UnderstandabilityMetrics.cognitive`) pour comparabilité avec radon,
# SonarSource et autres outils standards de l'écosystème.

# Seuils par sous-métrique (bornes low/high/very_high)
#
# Ces seuils ont été révisés en v2.2 suite à un run de calibration empirique
# sur un dataset pilote de 30 cas annotés (Python + TypeScript + Java, 10 par
# langage), équilibrés sur les 4 niveaux qualitatifs.
#
# Référence : `calibration/results/run_002_revised_defaults.md` dans le repo.
#
# Méthode résumée :
#   1. Constitution d'un dataset de 30 cas annotés par Claude Opus 4.7
#      (mélange de code généré et de code reproduit dans le style de
#      projets open source connus : CPython, requests, VSCode, Excalidraw,
#      Apache Commons, Spring).
#   2. Application des défauts d'origine (v2.0/v2.1) sur le dataset.
#      Résultat : excellent classement (Spearman 0.935) mais sous-estimation
#      systématique de 19 points en moyenne (accord catégoriel 33 %).
#   3. Test de propositions d'ajustements. La proposition retenue
#      ("Proposition B") resserre les seuils de 4 sous-métriques.
#      Résultat : accord catégoriel 80 %, RMSE 11.3, Spearman 0.977.
#   4. Pondérations laissées inchangées (changement minimal défendable).
#
# Limites assumées du pilote :
#   - n=30 cas, un seul annotateur (Claude) — risque de biais
#     systématique cohérent.
#   - Une calibration de production demande n≥150 et un panel
#     d'annotateurs (incl. humain).
#
# Toute proposition d'ajustement ultérieur doit passer par le harnais
# `calibration/evaluate.py` et démontrer une amélioration sur le dataset.
_UNDERSTANDABILITY_THRESHOLDS = {
    "cognitive":         {"low": 3,  "high": 10, "very_high": 20},
    "function_length":   {"low": 8,  "high": 25, "very_high": 50},
    "nesting_depth":     {"low": 1,  "high": 3,  "very_high": 5},
    "parameter_count":   {"low": 3,  "high": 5,  "very_high": 8},
    "line_density":      {"low": 25, "high": 50, "very_high": 80},
    # identifier_length est INVERSÉ : plus c'est court, pire c'est
    "identifier_length": {"low": 8,  "high": 5,  "very_high": 3},
}

# Pondérations dans le score composite (somme = 1.0)
_UNDERSTANDABILITY_WEIGHTS = {
    "cognitive":         0.30,
    "function_length":   0.20,
    "nesting_depth":     0.15,
    "parameter_count":   0.15,
    "line_density":      0.10,
    "identifier_length": 0.10,
}


def _normalize_component(
    value: float,
    metric: str,
    *,
    inverted: bool = False,
    thresholds: Optional[dict] = None,
) -> float:
    """Normalise une valeur en contribution 0-100 selon les seuils.

    - 0 si value ≤ low : pas de pénalité
    - 33 si value == high : pénalité modérée
    - 66 si value == very_high : pénalité forte
    - 100 si value largement au-delà : pénalité maximale

    Si inverted=True : plus la valeur est PETITE, plus la pénalité est grande.

    Paramètre `thresholds` : dict externe permettant d'injecter des seuils
    personnalisés (depuis un fichier de config). Si None, utilise les
    défauts intégrés dans `_UNDERSTANDABILITY_THRESHOLDS`.
    """
    t = (thresholds or _UNDERSTANDABILITY_THRESHOLDS)[metric]
    low, high, vhigh = t["low"], t["high"], t["very_high"]

    if inverted:
        # Inversion : on travaille avec "à quel point on est en dessous"
        if value >= low:
            return 0.0
        if value >= high:
            return 33.0 * (low - value) / (low - high)
        if value >= vhigh:
            return 33.0 + 33.0 * (high - value) / (high - vhigh)
        # Très court — saturation
        return min(100.0, 66.0 + 34.0 * (vhigh - value) / max(1, vhigh))

    # Cas standard
    if value <= low:
        return 0.0
    if value <= high:
        return 33.0 * (value - low) / (high - low)
    if value <= vhigh:
        return 33.0 + 33.0 * (value - high) / (vhigh - high)
    return min(100.0, 66.0 + 34.0 * (value - vhigh) / max(1, vhigh))


# Seuils de qualification du risque composite (0-100)
#
# Ces paliers ont été révisés en v2.3 suite à un second run de calibration
# sur le dataset enrichi n=45. Le run de validation a révélé un biais
# d'indulgence résiduel d'environ -11 points par rapport aux annotations
# humaines, particulièrement marqué sur les cas-frontières entre niveaux.
#
# Solution adoptée : absorber le biais en abaissant les paliers de level,
# sans toucher aux seuils des sous-métriques. Le risk numérique reste
# inchangé ; seule l'interprétation qualitative est plus stricte.
#
# Réf : `calibration/results/run_004_revised_levels.md`.
_UNDERSTANDABILITY_LEVELS = [
    (10, "low"),
    (27, "moderate"),
    (50, "high"),
]


def _risk_to_level(risk: float) -> str:
    """Classe un niveau de risque d'understandability en label qualitatif."""
    for threshold, name in _UNDERSTANDABILITY_LEVELS:
        if risk <= threshold:
            return name
    return "very_high"


@dataclass(frozen=True)
class FunctionUnderstandability:
    """Compréhensibilité d'UNE fonction.

    Permet de repérer une fonction problématique dans un fichier globalement
    bon (ex : une fonction de 200 lignes au milieu de 20 fonctions simples).

    Attributs
    ---------
    name : str
        Nom de la fonction (ou "<anonymous>" pour les lambdas).
    start_line, end_line : int
        Lignes 1-based dans le fichier source.
    length : int
        Nombre de lignes (end_line - start_line + 1).
    nesting_depth : int
        Profondeur maximale d'imbrication des structures de contrôle.
    parameter_count : int
        Nombre de paramètres formels.
    cognitive : int
        Complexité cognitive (Campbell) de la fonction. Conservée en
        sous-attribut pour comparabilité avec radon/SonarSource.
    risk : float
        **Niveau de risque** 0-100 propre à la fonction (plus c'est haut,
        plus la fonction est difficile à comprendre). À ne pas confondre
        avec ``PrimaryQualityScore.score`` qui est un score de QUALITÉ
        (plus c'est haut, mieux c'est) — d'où le choix du mot "risk" ici.
    level : str
        Niveau qualitatif : "low" / "moderate" / "high" / "very_high".
    """
    name: str
    start_line: int
    end_line: int
    length: int
    nesting_depth: int
    parameter_count: int
    cognitive: int
    risk: float
    level: str

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"FunctionUnderstandability({self.name}@{self.start_line}: "
            f"length={self.length}, depth={self.nesting_depth}, "
            f"params={self.parameter_count}, ccog={self.cognitive}, "
            f"risk={self.risk:.1f} ({self.level}))"
        )


@dataclass(frozen=True)
class UnderstandabilityMetrics:
    """Métriques de compréhensibilité au niveau FICHIER.

    Aligné sur la sous-caractéristique **Understandability** d'ISO/IEC 25010.

    Combine 6 sous-métriques en un **niveau de risque composite 0-100** :
    plus le risque est haut, plus le code est difficile à comprendre.

    Inclut aussi le détail par fonction (`functions`) pour repérer une
    fonction problématique noyée dans un fichier sain.

    Attributs
    ---------
    risk : float
        **Niveau de risque** composite 0-100 (plus c'est haut, plus c'est
        dur à lire). Ce n'est PAS un "score" au sens qualité — un risque
        élevé est mauvais. À ne pas confondre avec ``PrimaryQualityScore.score``
        (qui est inversement orienté).
    level : str
        Qualification : "low" / "moderate" / "high" / "very_high".
    cognitive : int
        Complexité cognitive globale du fichier (Campbell, 2017).
        Conservée en sous-attribut pour comparabilité avec radon
        et SonarSource.
    function_length_max, function_length_avg : int, float
        Longueur de la plus longue fonction (lignes) et longueur moyenne.
    nesting_depth_max : int
        Profondeur d'imbrication maximale dans tout le fichier.
    parameter_count_max : int
        Nombre maximum de paramètres trouvé sur une fonction.
    line_density_avg : float
        Nombre moyen de caractères non-blancs par ligne non-vide.
    identifier_length_avg : float
        Longueur moyenne des identifiants (variables, fonctions).
    functions : tuple[FunctionUnderstandability, ...]
        Détail par fonction (trié par risque décroissant).
    language : str
    backend : str
    """
    risk: float = 0.0
    level: str = "low"
    cognitive: int = 0
    function_length_max: int = 0
    function_length_avg: float = 0.0
    nesting_depth_max: int = 0
    parameter_count_max: int = 0
    line_density_avg: float = 0.0
    identifier_length_avg: float = 0.0
    functions: tuple = ()  # tuple de FunctionUnderstandability (immutable)
    language: str = ""
    backend: str = ""

    @classmethod
    def from_components(
        cls,
        *,
        cognitive: int,
        function_length_max: int,
        function_length_avg: float,
        nesting_depth_max: int,
        parameter_count_max: int,
        line_density_avg: float,
        identifier_length_avg: float,
        functions: list,
        language: str = "",
        backend: str = "",
        weights: Optional[dict] = None,
        thresholds: Optional[dict] = None,
    ) -> "UnderstandabilityMetrics":
        """Construit un UnderstandabilityMetrics à partir des sous-métriques.

        Calcule le niveau de risque composite en appliquant la formule
        pondérée sur les 6 sous-métriques.

        Paramètres optionnels :

        - ``weights`` : dict des 6 poids (cognitive, function_length, ...).
          Si None, utilise ``_UNDERSTANDABILITY_WEIGHTS`` (défauts intégrés).
        - ``thresholds`` : dict imbriqué metric → {low, high, very_high}.
          Si None, utilise ``_UNDERSTANDABILITY_THRESHOLDS``.

        Permet l'injection de pondérations et seuils depuis un fichier de
        configuration externe (cf. kodoneko_scanner.config).
        """
        w = weights or _UNDERSTANDABILITY_WEIGHTS

        c_cog = _normalize_component(cognitive, "cognitive", thresholds=thresholds)
        c_len = _normalize_component(function_length_max, "function_length", thresholds=thresholds)
        c_depth = _normalize_component(nesting_depth_max, "nesting_depth", thresholds=thresholds)
        c_params = _normalize_component(parameter_count_max, "parameter_count", thresholds=thresholds)
        c_density = _normalize_component(line_density_avg, "line_density", thresholds=thresholds)
        c_id = _normalize_component(
            identifier_length_avg, "identifier_length",
            inverted=True, thresholds=thresholds,
        )

        risk = (
            w["cognitive"]         * c_cog
            + w["function_length"]   * c_len
            + w["nesting_depth"]     * c_depth
            + w["parameter_count"]   * c_params
            + w["line_density"]      * c_density
            + w["identifier_length"] * c_id
        )
        # Borner [0, 100]
        risk = max(0.0, min(100.0, risk))

        return cls(
            risk=round(risk, 1),
            level=_risk_to_level(risk),
            cognitive=cognitive,
            function_length_max=function_length_max,
            function_length_avg=round(function_length_avg, 1),
            nesting_depth_max=nesting_depth_max,
            parameter_count_max=parameter_count_max,
            line_density_avg=round(line_density_avg, 1),
            identifier_length_avg=round(identifier_length_avg, 1),
            functions=tuple(functions),
            language=language,
            backend=backend,
        )

    def to_dict(self) -> dict:
        return {
            "risk": self.risk,
            "level": self.level,
            "cognitive": self.cognitive,
            "function_length_max": self.function_length_max,
            "function_length_avg": self.function_length_avg,
            "nesting_depth_max": self.nesting_depth_max,
            "parameter_count_max": self.parameter_count_max,
            "line_density_avg": self.line_density_avg,
            "identifier_length_avg": self.identifier_length_avg,
            "functions": [f.to_dict() for f in self.functions],
            "language": self.language,
            "backend": self.backend,
        }

    def __str__(self) -> str:
        return (
            f"UnderstandabilityMetrics({self.language}/{self.backend}: "
            f"risk={self.risk:.1f} ({self.level}), "
            f"cognitive={self.cognitive}, "
            f"fn_max_len={self.function_length_max}, "
            f"fn_max_depth={self.nesting_depth_max}, "
            f"functions={len(self.functions)})"
        )


# ---------------------------------------------------------------------------
# Combinaison NCLOC + Halstead + McCabe + Understandability
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CombinedMetrics:
    """Résultat agrégé : NCLOC + Halstead + McCabe + Understandability.

    Attributs
    ---------
    lines : LineCounts
    halstead : HalsteadMetrics
    mccabe : McCabeMetrics
    understandability : UnderstandabilityMetrics
    language : str
    """
    lines: LineCounts
    halstead: HalsteadMetrics
    mccabe: McCabeMetrics
    understandability: UnderstandabilityMetrics
    language: str

    def to_dict(self) -> dict:
        return {
            "lines": self.lines.to_dict(),
            "halstead": self.halstead.to_dict(),
            "mccabe": self.mccabe.to_dict(),
            "understandability": self.understandability.to_dict(),
            "language": self.language,
        }

    def __str__(self) -> str:
        return (
            f"CombinedMetrics({self.language}):\n"
            f"  lines:             ncloc={self.lines.ncloc}, sloc={self.lines.sloc}, "
            f"comment={self.lines.comment}\n"
            f"  halstead:          V={self.halstead.volume:.2f}, "
            f"D={self.halstead.difficulty:.2f}, "
            f"n1={self.halstead.n1}, n2={self.halstead.n2}\n"
            f"  mccabe:            CC={self.mccabe.value} ({self.mccabe.level})\n"
            f"  understandability: risk={self.understandability.risk:.1f} "
            f"({self.understandability.level}), "
            f"cognitive={self.understandability.cognitive}, "
            f"fn_max_len={self.understandability.function_length_max}, "
            f"fn_max_depth={self.understandability.nesting_depth_max}"
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LanguageNotSupported(ValueError):
    """Levée quand le langage demandé n'est pas supporté."""


class LanguageDetectionFailed(ValueError):
    """Levée quand la détection automatique de langage échoue."""
