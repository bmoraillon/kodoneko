"""Modèles de données du moteur temporel kodoneko_temporal.

Purement factuels (extraits de git), sans notion d'effort ni de coût :
CommitInfo, FileChange, TemporalWindow, MonthlySegment.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CommitInfo:
    """Un commit individuel extrait de git.

    Tous les champs viennent de ``git log`` ou ``git show`` ; aucun jugement
    sémantique à ce niveau. C'est la matière première brute.
    """
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    author_date: datetime
    committer_date: datetime
    subject: str               # 1re ligne du message
    body: str                  # reste du message (peut être vide)
    files_added: tuple = ()    # fichiers nouveaux
    files_modified: tuple = ()  # fichiers modifiés
    files_deleted: tuple = ()  # fichiers supprimés
    files_renamed: tuple = ()  # tuples (old_path, new_path)
    insertions: int = 0
    deletions: int = 0
    is_merge: bool = False

    @property
    def total_files_touched(self) -> int:
        return (len(self.files_added) + len(self.files_modified)
                + len(self.files_deleted) + len(self.files_renamed))

    @property
    def churn(self) -> int:
        """Volume total de changement (insertions + suppressions)."""
        return self.insertions + self.deletions

    def to_dict(self) -> dict:
        d = asdict(self)
        d["author_date"] = self.author_date.isoformat()
        d["committer_date"] = self.committer_date.isoformat()
        return d


# ---------------------------------------------------------------------------
# Représentation d'un changement appliqué à un fichier
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileChange:
    """Synthèse d'un changement de fichier sur une période.

    Agrège tous les commits qui ont touché ce fichier dans la fenêtre.
    Utile pour fournir au LLM un résumé compact par fichier plutôt
    qu'un diff brut massif.
    """
    path: str
    change_type: str   # "added" | "modified" | "deleted" | "renamed"
    old_path: Optional[str] = None   # si renamed
    insertions: int = 0
    deletions: int = 0
    commits_count: int = 0   # nb de commits touchant ce fichier dans la fenêtre

    # Métriques delta (calculées par static_analysis)
    ncloc_before: Optional[int] = None
    ncloc_after: Optional[int] = None
    understandability_risk_before: Optional[float] = None
    understandability_risk_after: Optional[float] = None

    @property
    def ncloc_delta(self) -> Optional[int]:
        if self.ncloc_before is None or self.ncloc_after is None:
            return None
        return self.ncloc_after - self.ncloc_before

    @property
    def is_substantial(self) -> bool:
        """Heuristique : le changement est-il substantiel ou cosmétique ?

        Substantiel si :
        - fichier ajouté ou supprimé, OU
        - delta NCLOC > 5 lignes, OU
        - changement de risk d'understandability > 5 points
        """
        if self.change_type in ("added", "deleted"):
            return True
        if self.ncloc_delta is not None and abs(self.ncloc_delta) > 5:
            return True
        if (self.understandability_risk_before is not None
                and self.understandability_risk_after is not None):
            if abs(self.understandability_risk_after
                   - self.understandability_risk_before) > 5:
                return True
        return False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Fenêtre temporelle d'analyse
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemporalWindow:
    """Une fenêtre temporelle d'analyse (typiquement un mois calendaire).

    Bornes inclusives sur les dates (UTC).
    """
    start: date
    end: date
    label: str    # ex: "2025-11" pour novembre 2025, ou "2025-W47" pour semaine

    def contains(self, when: datetime) -> bool:
        """Indique si une date tombe dans la fenêtre."""
        d = when.date() if isinstance(when, datetime) else when
        return self.start <= d <= self.end

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
        }


# ---------------------------------------------------------------------------
# Segment mensuel d'un item (un morceau d'item dans une fenêtre)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonthlySegment:
    """L'activité d'UN item de changement pendant UNE fenêtre temporelle.

    Un item étalé sur 3 mois aura 3 MonthlySegments. Permet à un humain
    de relire l'évolution mois par mois sans perdre la vue d'ensemble.
    """
    window_label: str         # ex: "2025-11"
    commits_count: int
    insertions: int
    deletions: int
    files_touched_count: int
    summary: str = ""          # résumé court optionnel

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Item de changement narrativement cohérent
# ---------------------------------------------------------------------------

