"""
Couche d'interprétation : transforme les métriques chiffrées en
informations humainement lisibles.

Deux fonctionnalités principales :

1. **Commentaires de hotspots** : génère une phrase explicative par
   fichier à partir de ses niveaux de métriques (low/moderate/high/
   very_high).

2. **Indicateur de santé synthétique (PrimaryQualityScore)** : score 0-100 +
   grade A-E qui agrège l'état du dépôt en une seule valeur. Conçu pour
   être réutilisé en aval (UO, clustering, dashboards).

La séparation entre ce module (interprétation) et `models.py`/`scanner.py`
(calcul) est intentionnelle : les conventions d'interprétation peuvent
évoluer sans toucher au cœur du calcul.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .models import FileReport, RepoMetrics


# ===========================================================================
# Table de correspondance : niveau atteint → signification humaine
# ===========================================================================
#
# Pour chaque métrique et chaque niveau, deux informations :
#  - `verb`   : courte étiquette d'action (ex. "taille élevée")
#  - `meaning` : phrase d'interprétation plus complète
#
# Cette table est conçue pour être stable (réutilisable par d'autres
# briques du projet KodoNeko) mais reste accessible si on veut surcharger.

LEVEL_INTERPRETATIONS: dict[str, dict[str, dict[str, str]]] = {
    # ─────────────────────────────────────────────────────────────────
    # NCLOC : seuils en lignes
    # low=≤100, moderate=≤300, high=≤500, very_high=>500
    # ─────────────────────────────────────────────────────────────────
    "ncloc": {
        "low": {
            "verb": "fichier court",
            "meaning": "taille raisonnable",
        },
        "moderate": {
            "verb": "fichier moyen",
            "meaning": "taille notable, surveiller la cohésion",
        },
        "high": {
            "verb": "fichier long",
            "meaning": "candidat au découpage en sous-modules",
        },
        "very_high": {
            "verb": "fichier très long",
            "meaning": "découpage fortement conseillé",
        },
    },
    # ─────────────────────────────────────────────────────────────────
    # Halstead Volume : densité d'information
    # low=≤500, moderate=≤1500, high=≤3000, very_high=>3000
    # ─────────────────────────────────────────────────────────────────
    "halstead": {
        "low": {
            "verb": "code peu dense",
            "meaning": "volume d'information mesuré",
        },
        "moderate": {
            "verb": "densité modérée",
            "meaning": "code suffisamment riche en opérateurs/opérandes",
        },
        "high": {
            "verb": "code dense",
            "meaning": "beaucoup d'opérateurs ou de variables — vérifier "
                       "la cohérence du périmètre",
        },
        "very_high": {
            "verb": "code très dense",
            "meaning": "concentration anormale d'opérateurs/variables, "
                       "documenter ou simplifier",
        },
    },
    # ─────────────────────────────────────────────────────────────────
    # McCabe : 4 niveaux (low ≤10, moderate ≤20, high ≤50, very_high >50)
    # ─────────────────────────────────────────────────────────────────
    "mccabe": {
        "low": {
            "verb": "flux simple",
            "meaning": "peu de branchements, faible risque de bugs",
        },
        "moderate": {
            "verb": "complexité modérée",
            "meaning": "nombre de chemins notable, tests à soigner",
        },
        "high": {
            "verb": "complexité élevée",
            "meaning": "trop de chemins d'exécution, refactoring conseillé",
        },
        "very_high": {
            "verb": "complexité extrême",
            "meaning": "code très ramifié, refactoring fortement conseillé",
        },
    },
    # ─────────────────────────────────────────────────────────────────
    # Understandability (ISO/IEC 25010) : low ≤15, moderate ≤35, high ≤60
    # Fusion v2.0 de cognitive (Campbell) et readability (FRD).
    # ─────────────────────────────────────────────────────────────────
    "understandability": {
        "low": {
            "verb": "code clair",
            "meaning": "facile à comprendre : fonctions courtes, "
                       "peu d'imbrications, noms parlants",
        },
        "moderate": {
            "verb": "lecture attentive nécessaire",
            "meaning": "imbrications visibles ou fonctions un peu longues, "
                       "mais reste lisible",
        },
        "high": {
            "verb": "difficile à comprendre",
            "meaning": "fonctions longues, imbrications profondes "
                       "ou noms trop courts — refactoring conseillé",
        },
        "very_high": {
            "verb": "très difficile à comprendre",
            "meaning": "le code est dur à suivre, refactoring fortement conseillé",
        },
    },
}


# Seuils NCLOC (autres seuils déjà dans models.py)
_NCLOC_THRESHOLDS = [
    (100, "low"),
    (300, "moderate"),
    (500, "high"),
]


# Seuils Halstead Volume
_HALSTEAD_VOLUME_THRESHOLDS = [
    (500.0, "low"),
    (1500.0, "moderate"),
    (3000.0, "high"),
]


def _ncloc_level(value: int) -> str:
    """Classifie un NCLOC en niveau qualitatif."""
    for threshold, name in _NCLOC_THRESHOLDS:
        if value <= threshold:
            return name
    return "very_high"


def _halstead_level(volume: float) -> str:
    """Classifie un Halstead V en niveau qualitatif."""
    for threshold, name in _HALSTEAD_VOLUME_THRESHOLDS:
        if volume <= threshold:
            return name
    return "very_high"


# ===========================================================================
# Commentaires sur les hotspots (option C : verdict + chiffres + détail)
# ===========================================================================

# Niveaux ordonnés du moins au plus grave
_LEVEL_ORDER = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


# Verdict global pour un fichier : la pire métrique gagne
_HOTSPOT_VERDICTS = {
    "low": ("✅", "Code en bonne santé"),
    "moderate": ("ℹ️", "À surveiller"),
    "high": ("⚠️", "Refactoring conseillé"),
    "very_high": ("🔥", "Refactoring fortement conseillé"),
}


def _worst_level(levels: list[str]) -> str:
    """Retourne le niveau le plus grave parmi une liste de niveaux."""
    return max(levels, key=lambda l: _LEVEL_ORDER.get(l, 0))


def comment_file(file_report: FileReport) -> str:
    """Génère un commentaire humain pour un fichier (style hotspot).

    Format (option C) :

        <icône> <verdict global> (cognitive=18, mccabe=12, ncloc=50).
        <phrase d'explication détaillée>.

    Si le fichier n'a pas de métriques (erreur), retourne un message simple.
    """
    if file_report.metrics is None:
        reason = file_report.error or "métriques non disponibles"
        return f"⚪ Non analysé ({reason})"

    m = file_report.metrics

    # Niveaux de chaque métrique
    ncloc_level = _ncloc_level(m.lines.ncloc)
    hal_level = _halstead_level(m.halstead.volume)
    cc_level = m.mccabe.level
    u_level = m.understandability.level

    levels = [ncloc_level, hal_level, cc_level, u_level]
    worst = _worst_level(levels)
    icon, verdict = _HOTSPOT_VERDICTS[worst]

    # Première ligne : verdict + chiffres
    header = (
        f"{icon} {verdict} "
        f"(risk={m.understandability.risk:.0f}, "
        f"cognitive={m.understandability.cognitive}, "
        f"mccabe={m.mccabe.value}, "
        f"ncloc={m.lines.ncloc})"
    )

    # Deuxième ligne : explication des métriques qui dépassent
    # Ordre de priorité : understandability d'abord (vue globale),
    # puis mccabe, halstead, ncloc.
    issues = []
    if u_level in ("high", "very_high"):
        issues.append(LEVEL_INTERPRETATIONS["understandability"][u_level]["meaning"])
    if cc_level in ("high", "very_high"):
        issues.append(LEVEL_INTERPRETATIONS["mccabe"][cc_level]["meaning"])
    if hal_level in ("high", "very_high"):
        issues.append(LEVEL_INTERPRETATIONS["halstead"][hal_level]["meaning"])
    if ncloc_level in ("high", "very_high"):
        issues.append(LEVEL_INTERPRETATIONS["ncloc"][ncloc_level]["meaning"])

    if issues:
        return f"{header}. {issues[0].capitalize()}."
    elif worst == "moderate":
        # Identifier la métrique modérée principale
        for metric_name, level in [
            ("understandability", u_level), ("mccabe", cc_level),
            ("halstead", hal_level), ("ncloc", ncloc_level),
        ]:
            if level == "moderate":
                meaning = LEVEL_INTERPRETATIONS[metric_name][level]["meaning"]
                return f"{header}. {meaning.capitalize()}."
        return f"{header}."
    else:
        return f"{header}."


# ===========================================================================
# PrimaryQualityScore : indicateur synthétique 0-100 + grade A-E
# ===========================================================================

# Pondération des 4 métriques dans le score global.
# Depuis v0.4 (suite à la fusion cognitive+readability → understandability
# dans kodoneko_metrics v2.0), on a 4 métriques au lieu de 5.
# Plus de double comptage de la cognitive complexity (qui pesait à la fois
# en propre et comme composante du FRD).
#
# Pondération par défaut (overridable via fichier kodoneko.toml) :
#   - understandability (70 %) : métrique composite la plus riche, agrège
#     cognitive + 5 autres dimensions. Reflète directement la
#     maintenabilité ressentie. C'est l'indicateur principal.
#   - mccabe (15 %) : complexité cyclomatique, mesure les chemins
#     d'exécution. Indépendante et complémentaire.
#   - ncloc (10 %) : taille brute, indicateur rudimentaire mais utile
#     pour repérer les fichiers démesurés.
#   - halstead (5 %) : densité d'information, indicateur secondaire.
_METRIC_WEIGHTS = {
    "ncloc":             0.10,
    "halstead":          0.05,
    "mccabe":            0.15,
    "understandability": 0.70,
}


# Score de pénalité pour chaque niveau (sur 100).
# - low : 0 (pas de pénalité)
# - moderate : 25 (alerte)
# - high : 60 (problème)
# - very_high : 100 (critique)
_LEVEL_PENALTY = {
    "low": 0.0,
    "moderate": 25.0,
    "high": 60.0,
    "very_high": 100.0,
}


# Mapping score → grade lettre
_GRADE_THRESHOLDS = [
    (85, "A"),  # Excellent
    (70, "B"),  # Bon
    (55, "C"),  # Acceptable
    (40, "D"),  # Préoccupant
]
# Sinon : "E" (critique)


def _score_to_grade(score: float) -> str:
    """Convertit un score 0-100 en grade A-E."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


@dataclass(frozen=True)
class PrimaryQualityScore:
    """Indicateur synthétique de **qualité** d'un dépôt.

    Score 0-100 + grade A-E qui résume l'état de santé global d'un
    dépôt à partir des 4 familles de métriques produites par
    ``kodoneko_metrics``.

    **Sémantique du score** : *plus c'est haut, mieux c'est*. Un dépôt
    parfait (100 % low partout) score 100 (grade A). Un dépôt
    catastrophique (100 % very_high partout) score 0 (grade E).

    À distinguer absolument de ``UnderstandabilityMetrics.risk`` qui
    est un **score de risque** orienté à l'opposé (plus haut = pire).
    C'est pour préserver cette distinction sans ambiguïté que la
    classe a été renommée en v0.8 de ``PrimaryScore`` à
    ``PrimaryQualityScore``.

    Attributs
    ---------
    score : float
        **Quality score** 0-100 (plus c'est haut, mieux c'est).
    grade : str
        Grade lettre A-E (A=excellent, E=critique).
    breakdown : dict
        Détail par métrique : pour chaque métrique, le pourcentage de
        fichiers à chaque niveau (low/moderate/high/very_high) + la
        pénalité contribuée au score.
    files_critical : int
        Nombre de fichiers avec au moins une métrique en niveau very_high.
    files_warning : int
        Nombre de fichiers avec au moins une métrique en niveau high
        (sans atteindre very_high).
    files_total : int
        Nombre total de fichiers analysés.
    summary : str
        Phrase de synthèse (interprétation humaine du score).
    """
    score: float
    grade: str
    breakdown: dict
    files_critical: int
    files_warning: int
    files_total: int
    summary: str

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"PrimaryQualityScore(score={self.score:.1f}/100, grade={self.grade}, "
            f"critical={self.files_critical}, warning={self.files_warning}, "
            f"total={self.files_total})"
        )


# Phrases de résumé par grade
_GRADE_SUMMARIES = {
    "A": "Code en excellent état général. Pas d'intervention prioritaire.",
    "B": "Code globalement sain avec quelques zones à surveiller.",
    "C": "État acceptable mais plusieurs fichiers méritent attention.",
    "D": "État préoccupant. Un effort de refactoring est conseillé.",
    "E": "État critique. Refactoring nécessaire sur plusieurs fronts.",
}


def compute_primary_quality_score(
    report: RepoMetrics, config=None,
) -> PrimaryQualityScore:
    """Calcule l'indicateur de qualité globale d'un dépôt.

    Retourne un ``PrimaryQualityScore`` : score 0-100 + grade A-E,
    avec la sémantique *plus c'est haut, mieux c'est*. À l'opposé d'un
    score de risque.

    Méthode :

    1. Pour chaque métrique (ncloc, halstead, mccabe, understandability),
       calcule le pourcentage de fichiers à chaque niveau.
    2. Pour chaque métrique, calcule une pénalité moyenne pondérée par
       les pourcentages.
    3. Le **quality score** final est ``100 - somme_pondérée_des_pénalités``.
    4. Le grade est dérivé du score selon ``_GRADE_THRESHOLDS``.

    Paramètres
    ----------
    report : RepoMetrics
        Rapport de scan produit par `scan_repo`.
    config : KodoNekoConfig, optional
        Configuration personnalisée (poids, seuils). Si None, utilise
        les poids par défaut intégrés (`_METRIC_WEIGHTS`).

    Conception : un dépôt parfait (100 % low partout) score 100 (grade A).
    Un dépôt catastrophique (100 % very_high partout) score 0 (grade E).
    Entre les deux, score linéaire selon les pondérations.

    Retourne
    --------
    PrimaryQualityScore (immutable, sérialisable JSON via `.to_dict()`).
    """
    # Résolution des poids : config explicite > défauts intégrés
    if config is not None:
        weights = config.primary_weights
    else:
        weights = _METRIC_WEIGHTS

    valid_files = [f for f in report.by_file if f.metrics is not None]
    n = len(valid_files)
    if n == 0:
        return PrimaryQualityScore(
            score=0.0,
            grade="E",
            breakdown={},
            files_critical=0,
            files_warning=0,
            files_total=0,
            summary="Aucun fichier analysable.",
        )

    # 1) Classifier chaque fichier sur chaque métrique
    counts = {
        m: {"low": 0, "moderate": 0, "high": 0, "very_high": 0}
        for m in weights
    }
    files_critical = 0
    files_warning = 0
    for f in valid_files:
        m = f.metrics
        levels = {
            "ncloc": _ncloc_level(m.lines.ncloc),
            "halstead": _halstead_level(m.halstead.volume),
            "mccabe": m.mccabe.level,
            "understandability": m.understandability.level,
        }
        for metric, level in levels.items():
            counts[metric][level] += 1

        worst = _worst_level(list(levels.values()))
        if worst == "very_high":
            files_critical += 1
        elif worst == "high":
            files_warning += 1

    # 2) Calculer la pénalité moyenne par métrique
    breakdown = {}
    weighted_penalty_total = 0.0
    for metric, weight in weights.items():
        # Pénalité moyenne = somme(count[level] × penalty[level]) / n
        penalty = sum(
            counts[metric][level] * _LEVEL_PENALTY[level]
            for level in counts[metric]
        ) / n
        weighted_penalty_total += penalty * weight
        # Pourcentages pour le breakdown
        percentages = {
            level: round(100 * counts[metric][level] / n, 1)
            for level in counts[metric]
        }
        breakdown[metric] = {
            "weight": weight,
            "penalty_avg": round(penalty, 2),
            "percentages": percentages,
        }

    score = max(0.0, min(100.0, 100.0 - weighted_penalty_total))
    grade = _score_to_grade(score)

    # 3) Phrase de résumé
    base_summary = _GRADE_SUMMARIES[grade]
    if files_critical > 0:
        base_summary += f" ({files_critical} fichier(s) critique(s))"

    return PrimaryQualityScore(
        score=round(score, 1),
        grade=grade,
        breakdown=breakdown,
        files_critical=files_critical,
        files_warning=files_warning,
        files_total=n,
        summary=base_summary,
    )


# ===========================================================================
# Helper : afficher un rapport synthétique
# ===========================================================================

def format_primary_report(report: RepoMetrics, *, hotspot_count: int = 5) -> str:
    """Génère un rapport texte complet : PrimaryQualityScore + hotspots commentés.

    Cette fonction est un raccourci pour produire le rendu standard à
    afficher dans un notebook ou une CLI.
    """
    hi = compute_primary_quality_score(report)

    lines = []
    lines.append("=" * 60)
    lines.append(f"✨ Quality score : {hi.score:.1f}/100 (grade {hi.grade})")
    lines.append("=" * 60)
    lines.append(hi.summary)
    lines.append("")
    lines.append(f"Fichiers analysés : {hi.files_total}")
    lines.append(f"  ✅ Sains/modérés : "
                 f"{hi.files_total - hi.files_critical - hi.files_warning}")
    lines.append(f"  ⚠️  À surveiller  : {hi.files_warning}")
    lines.append(f"  🔥 Critiques     : {hi.files_critical}")

    if hotspot_count > 0:
        hotspots = report.hotspots(top=hotspot_count, by="understandability")
        if hotspots:
            lines.append("")
            lines.append(f"Top {len(hotspots)} hotspots (par understandability) :")
            for f in hotspots:
                lines.append(f"  • {f.relative_path}")
                lines.append(f"    {comment_file(f)}")

    return "\n".join(lines)
