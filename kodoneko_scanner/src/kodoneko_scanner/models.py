"""
Modèles de données pour le scanner.

Trois dataclasses :

- FileReport : résultat d'analyse d'un fichier (chemin + CombinedMetrics)
- Totals : valeurs agrégées sur un ensemble de fichiers
- RepoMetrics : rapport complet d'un dépôt (Totals + détail par fichier
  + détail par langage + erreurs)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from kodoneko_metrics import CombinedMetrics


@dataclass
class FileReport:
    """Résultat d'analyse d'un fichier.

    Attributs
    ---------
    path : str
        Chemin du fichier (absolu ou relatif à la racine du repo).
    relative_path : str
        Chemin relatif à la racine du repo (toujours posix-like, /).
    language : str
        Langage détecté.
    size_bytes : int
        Taille du fichier en octets (utile pour les filtres et la perf).
    metrics : CombinedMetrics | None
        Métriques calculées. None si l'analyse a échoué.
    error : str | None
        Message d'erreur si l'analyse a échoué (None sinon).
    """
    path: str
    relative_path: str
    language: str
    size_bytes: int
    metrics: Optional[CombinedMetrics] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "error": self.error,
        }


@dataclass
class Totals:
    """Valeurs agrégées sur un ensemble de fichiers.

    Pour les métriques additives (ncloc, sloc, volume...), on somme.
    Pour les métriques non-additives (CC, CCog, level...), on garde
    le maximum et la moyenne.
    """
    # Comptage de lignes (sommes)
    total: int = 0
    blank: int = 0
    comment: int = 0
    sloc: int = 0
    ncloc: int = 0
    # Halstead (sommes — N1, N2 sont additifs ; n1, n2 le sont moins mais
    # on les somme par convention pratique pour avoir un total)
    halstead_n1: int = 0
    halstead_n2: int = 0
    halstead_N1: int = 0
    halstead_N2: int = 0
    halstead_volume: float = 0.0
    halstead_effort: float = 0.0
    # McCabe (somme + max + moyenne)
    mccabe_sum: int = 0
    mccabe_max: int = 0
    mccabe_avg: float = 0.0
    # Cognitive (somme + max + moyenne) — depuis v0.4, alimenté par
    # m.understandability.cognitive (préservé pour comparabilité radon)
    cognitive_sum: int = 0
    cognitive_max: int = 0
    cognitive_avg: float = 0.0
    # Understandability (score composite 0-100) — nouveau v0.4
    understandability_max: float = 0.0
    understandability_avg: float = 0.0
    # Méta
    files_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepoMetrics:
    """Rapport complet de l'analyse d'un dépôt.

    Attributs
    ---------
    repo_path : str
        Chemin de la racine du dépôt scanné.
    files_scanned : int
        Nombre de fichiers analysés avec succès.
    files_skipped : int
        Nombre de fichiers sautés (langage non supporté, taille, erreur).
    totals : Totals
        Agrégations sur l'ensemble des fichiers.
    by_file : list[FileReport]
        Détail par fichier (un FileReport par fichier analysé).
    by_language : dict[str, Totals]
        Agrégations par langage.
    errors : list[dict]
        Liste des erreurs rencontrées : [{"path": str, "reason": str}].
    """
    repo_path: str
    files_scanned: int = 0
    files_skipped: int = 0
    totals: Totals = field(default_factory=Totals)
    by_file: list[FileReport] = field(default_factory=list)
    by_language: dict[str, Totals] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    def hotspots(self, top: int = 10, by: str = "understandability") -> list[FileReport]:
        """Retourne les `top` fichiers les plus complexes.

        Paramètres
        ----------
        top : int
            Nombre de fichiers à retourner.
        by : str
            Critère de tri : "understandability" (défaut depuis v0.4),
            "cognitive", "mccabe", "ncloc", "volume", "effort".
        """
        scored = [
            (f, _score_by(f, by))
            for f in self.by_file
            if f.metrics is not None
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [f for f, _ in scored[:top]]

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "files_skipped": self.files_skipped,
            "totals": self.totals.to_dict(),
            "by_file": [f.to_dict() for f in self.by_file],
            "by_language": {
                lang: t.to_dict() for lang, t in self.by_language.items()
            },
            "errors": self.errors,
        }


def _score_by(file_report: FileReport, criterion: str) -> float:
    """Helper interne : retourne la valeur scalaire d'un FileReport pour
    le critère donné."""
    if file_report.metrics is None:
        return 0
    m = file_report.metrics
    if criterion == "understandability":
        return m.understandability.risk
    if criterion == "cognitive":
        # Accède à la cognitive via understandability (préservé pour
        # comparabilité radon/SonarSource)
        return m.understandability.cognitive
    if criterion == "mccabe":
        return m.mccabe.value
    if criterion == "ncloc":
        return m.lines.ncloc
    if criterion == "volume":
        return m.halstead.volume
    if criterion == "effort":
        return m.halstead.effort
    raise ValueError(
        f"Critère inconnu : {criterion!r}. Valeurs : "
        "'understandability', 'cognitive', 'mccabe', 'ncloc', 'volume', 'effort'."
    )
