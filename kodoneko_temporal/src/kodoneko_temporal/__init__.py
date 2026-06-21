"""kodoneko_temporal — analyse temporelle des métriques sur l'historique git.

Applique n'importe quel analyseur de métrique (COSMIC ou qualité) à l'état d'un
dépôt à un commit donné, ou à travers une suite de fenêtres temporelles.
Aucune notion d'effort ni de coût.

Auteur : Benoît Moraillon · Licence : AGPL-3.0
"""

from __future__ import annotations

from .models import CommitInfo, FileChange, TemporalWindow, MonthlySegment
from .git_extract import (
    GitExtractError, is_git_repo, get_repo_date_range,
    extract_commits, get_commit_diff, refine_file_status,
)
from .windowing import iter_windows
from .temporal_engine import (
    analyze_at_ref, analyze_at_commit, analyze_over_windows,
    TemporalPoint, TemporalSeries, TemporalError,
)
from .cosmic_delta import (
    compute_cosmic_at_ref, compute_cosmic_delta_for_commit,
    compute_cosmic_delta_for_range,
)

__version__ = "0.4.1"

__all__ = [
    "CommitInfo", "FileChange", "TemporalWindow", "MonthlySegment",
    "GitExtractError", "is_git_repo", "get_repo_date_range",
    "extract_commits", "get_commit_diff", "refine_file_status",
    "iter_windows",
    "analyze_at_ref", "analyze_at_commit", "analyze_over_windows",
    "TemporalPoint", "TemporalSeries", "TemporalError",
    "compute_cosmic_at_ref", "compute_cosmic_delta_for_commit",
    "compute_cosmic_delta_for_range",
]
