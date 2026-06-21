"""Moteur temporel générique : applique un analyseur quelconque à l'historique.

Généralise le pattern « checkout un commit -> analyse l'arbre -> collecte le
résultat » à n'importe quelle fonction d'analyse. Un analyseur est une fonction
``(chemin_repo) -> résultat``. Permet d'observer l'évolution de TOUTE métrique
(COSMIC, lignes, Halstead, McCabe, compréhensibilité) dans le temps.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from .git_extract import is_git_repo, get_repo_date_range
from .windowing import iter_windows

Analyzer = Callable[[Path], Any]


class TemporalError(RuntimeError):
    """Erreur lors de l'analyse temporelle."""


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise TemporalError(f"git {' '.join(args)} a échoué : {result.stderr.strip()}")
    return result.stdout.strip()


def _resolve_ref(repo: Path, ref: str) -> str:
    return _run_git(["rev-parse", ref], cwd=repo)


def _commit_before_date(repo: Path, when, branch: str = "HEAD") -> Optional[str]:
    iso = when.date().isoformat() if isinstance(when, datetime) else when.isoformat()
    out = _run_git(["rev-list", "-1", f"--before={iso} 23:59:59", branch], cwd=repo)
    return out or None


@contextmanager
def _git_worktree(repo: Path, sha: str) -> Iterator[Path]:
    """Crée un git worktree temporaire au commit donné, le détruit en sortie."""
    tmpdir = Path(tempfile.mkdtemp(prefix="kodoneko_temporal_"))
    try:
        _run_git(["worktree", "add", "--detach", str(tmpdir), sha], cwd=repo)
        try:
            yield tmpdir
        finally:
            try:
                _run_git(["worktree", "remove", "--force", str(tmpdir)], cwd=repo)
            except Exception:
                pass
    finally:
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)


@dataclass
class TemporalPoint:
    """Résultat d'une analyse à un point temporel (un ref ou une fenêtre)."""
    label: str
    sha: str
    when: Optional[datetime] = None
    result: Any = None

    def to_dict(self) -> dict:
        res = self.result
        if hasattr(res, "to_dict"):
            res = res.to_dict()
        return {"label": self.label, "sha": self.sha,
                "when": self.when.isoformat() if self.when else None, "result": res}


@dataclass
class TemporalSeries:
    """Série de points temporels (analyse par fenêtres)."""
    points: list = field(default_factory=list)

    def __iter__(self):
        return iter(self.points)

    def __len__(self):
        return len(self.points)

    def labels(self) -> list:
        return [p.label for p in self.points]

    def results(self) -> list:
        return [p.result for p in self.points]

    def to_dict(self) -> dict:
        return {"points": [p.to_dict() for p in self.points]}


def analyze_at_ref(repo, ref: str, *, analyzer: Analyzer) -> TemporalPoint:
    """Applique un analyseur à l'état du repo à une référence git donnée.

    analyzer : fonction (Path) -> résultat, ex. scan_repo_cosmic ou scan_repo.
    """
    repo = Path(repo).resolve()
    if not is_git_repo(repo):
        raise TemporalError(f"{repo} n'est pas un dépôt git")
    sha = _resolve_ref(repo, ref)
    with _git_worktree(repo, sha) as wt:
        result = analyzer(wt)
    return TemporalPoint(label=ref, sha=sha, result=result)


def analyze_at_commit(repo, commit: str, *, analyzer: Analyzer) -> TemporalPoint:
    """Alias explicite de analyze_at_ref pour un SHA de commit."""
    return analyze_at_ref(repo, commit, analyzer=analyzer)


def analyze_over_windows(repo, *, analyzer: Analyzer, strategy: str = "monthly",
                         fixed_days: int = 30, start=None, end=None) -> TemporalSeries:
    """Applique un analyseur à l'état du repo à la fin de chaque fenêtre temporelle.

    strategy : "monthly" | "weekly" | "fixed". Retourne un TemporalPoint par
    fenêtre ayant au moins un commit.
    """
    repo = Path(repo).resolve()
    if not is_git_repo(repo):
        raise TemporalError(f"{repo} n'est pas un dépôt git")
    if start is None or end is None:
        d_start, d_end = get_repo_date_range(repo)
        start = start or d_start.date()
        end = end or d_end.date()
    points = []
    for window in iter_windows(start, end, strategy=strategy, fixed_days=fixed_days):
        sha = _commit_before_date(repo, window.end)
        if not sha:
            continue
        with _git_worktree(repo, sha) as wt:
            result = analyzer(wt)
        points.append(TemporalPoint(label=window.label, sha=sha, result=result))
    return TemporalSeries(points=points)
