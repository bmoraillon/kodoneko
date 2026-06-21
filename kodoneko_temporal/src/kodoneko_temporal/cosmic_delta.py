"""
Calcul du delta COSMIC entre deux états git.

Trois cas d'usage principaux :

1. Delta d'un commit spécifique : CFP_avant_commit vs CFP_après_commit
2. Delta entre deux refs (tags, branches, commits) : v1.0.0..v2.0.0
3. Delta entre deux dates : 2025-01-01..2025-06-30

Approche : checkout-and-scan via ``git worktree`` pour isoler les
analyses dans des dossiers temporaires sans affecter le working tree
de l'utilisateur.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from kodoneko_metrics.cosmic import CosmicDelta, CosmicMode, CosmicScanReport
from kodoneko_scanner import scan_repo_cosmic


# ===========================================================================
# Utilitaires git
# ===========================================================================

def _run_git(args: list[str], cwd: Path) -> str:
    """Exécute git et retourne stdout, lève RuntimeError si échec."""
    result = subprocess.run(
        ["git"] + args, cwd=str(cwd),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} a échoué (code {result.returncode}) : "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _resolve_ref(repo: Path, ref: str) -> str:
    """Résout une référence git (tag, branche, sha, HEAD~n) en SHA complet."""
    return _run_git(["rev-parse", ref], cwd=repo).strip()


def _commit_parent(repo: Path, commit_sha: str) -> Optional[str]:
    """Retourne le parent d'un commit, ou None si c'est le commit initial."""
    try:
        out = _run_git(["rev-parse", f"{commit_sha}^"], cwd=repo).strip()
        return out if out else None
    except RuntimeError:
        # Commit initial : pas de parent
        return None


def _commit_before_date(repo: Path, when: date | datetime,
                        branch: str = "HEAD") -> str:
    """Retourne le SHA du dernier commit sur ``branch`` avant ou égal à ``when``.

    Utilise ``git rev-list -1 --before=<date>``.
    """
    if isinstance(when, datetime):
        date_str = when.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_str = when.strftime("%Y-%m-%d 23:59:59")

    sha = _run_git(
        ["rev-list", "-1", f"--before={date_str}", branch],
        cwd=repo,
    ).strip()
    if not sha:
        raise RuntimeError(
            f"Aucun commit trouvé avant {date_str} sur {branch}"
        )
    return sha


# ===========================================================================
# Worktree management
# ===========================================================================

@contextmanager
def _git_worktree(repo: Path, sha: str):
    """Context manager qui crée un git worktree temporaire au commit donné.

    Yield le chemin du worktree, le détruit automatiquement en sortie.
    Robuste aux échecs de cleanup (ignore les erreurs).
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="kodoneko_cosmic_"))
    try:
        _run_git(["worktree", "add", "--detach", str(tmpdir), sha], cwd=repo)
        try:
            yield tmpdir
        finally:
            # Cleanup git worktree (best effort)
            try:
                _run_git(["worktree", "remove", "--force", str(tmpdir)], cwd=repo)
            except Exception:
                pass
    finally:
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)


# ===========================================================================
# API publique
# ===========================================================================

def compute_cosmic_at_ref(
    repo: str | Path,
    ref: str,
    *,
    mode: CosmicMode = "practical",
) -> CosmicScanReport:
    """Calcule l'état COSMIC complet du repo à une référence git donnée.

    Paramètres
    ----------
    repo : str | Path
        Chemin du repo git.
    ref : str
        Tag, branche, SHA, ou expression résolvable (HEAD~3, etc.)
    mode : "strict" | "practical"
        Mode COSMIC.

    Returns
    -------
    CosmicScanReport
    """
    repo = Path(repo).resolve()
    sha = _resolve_ref(repo, ref)
    with _git_worktree(repo, sha) as wt:
        report = scan_repo_cosmic(
            wt, mode=mode, use_git=True,
            scope_label=f"ref:{ref}@{sha[:8]}",
        )
    return report


def compute_cosmic_delta_for_commit(
    repo: str | Path,
    commit: str,
    *,
    mode: CosmicMode = "practical",
) -> CosmicDelta:
    """Calcule le delta CFP induit par un commit spécifique.

    Compare l'état du repo **avant** le commit (= état au parent) avec
    l'état **après** le commit (= état au commit lui-même). Le delta
    est la différence après − avant, par catégorie.

    Cas spécial : si ``commit`` est le commit initial du repo (sans
    parent), le ``before`` est un rapport vide (CFP = 0) et tout l'état
    du commit est compté comme ajouté.

    Paramètres
    ----------
    repo : str | Path
        Chemin du repo git.
    commit : str
        Référence du commit (SHA, tag, HEAD, etc.)
    mode : "strict" | "practical"
        Mode COSMIC.

    Returns
    -------
    CosmicDelta
        Contient les deux CosmicScanReport (avant/après) et leur diff.
    """
    repo = Path(repo).resolve()
    after_sha = _resolve_ref(repo, commit)
    before_sha = _commit_parent(repo, after_sha)

    # État avant
    if before_sha is None:
        before = CosmicScanReport(
            scope=f"before:initial-commit", mode=mode,
        )
    else:
        with _git_worktree(repo, before_sha) as wt:
            before = scan_repo_cosmic(
                wt, mode=mode, use_git=True,
                scope_label=f"before:{before_sha[:8]}",
            )

    # État après
    with _git_worktree(repo, after_sha) as wt:
        after = scan_repo_cosmic(
            wt, mode=mode, use_git=True,
            scope_label=f"after:{after_sha[:8]}",
        )

    return CosmicDelta(
        scope=f"commit:{after_sha[:8]}",
        mode=mode,
        before=before,
        after=after,
    )


def compute_cosmic_delta_for_range(
    repo: str | Path,
    *,
    since: str | date | datetime | None = None,
    until: str | date | datetime | None = None,
    mode: CosmicMode = "practical",
    branch: str = "HEAD",
) -> CosmicDelta:
    """Calcule le delta CFP entre deux refs ou deux dates.

    Au moins l'un de ``since`` ou ``until`` doit être renseigné.
    - ``since`` non renseigné → début du repo (= commit initial)
    - ``until`` non renseigné → HEAD

    Les refs (str) sont résolues directement par git.
    Les dates (date/datetime) sont converties vers le dernier commit
    avant ou égal à cette date sur ``branch``.

    Paramètres
    ----------
    repo : str | Path
    since : str | date | datetime | None
        Ref de départ ou date.
    until : str | date | datetime | None
        Ref d'arrivée ou date.
    mode : "strict" | "practical"
    branch : str
        Branche à considérer pour les conversions date → SHA.

    Returns
    -------
    CosmicDelta

    Examples
    --------
    >>> # Delta entre deux tags
    >>> delta = compute_cosmic_delta_for_range(
    ...     "/path/to/repo", since="v1.0.0", until="v1.1.0",
    ... )
    >>> print(delta.cfp_added)

    >>> # Delta d'une période
    >>> from datetime import date
    >>> delta = compute_cosmic_delta_for_range(
    ...     "/path/to/repo",
    ...     since=date(2025, 1, 1), until=date(2025, 6, 30),
    ... )
    """
    repo = Path(repo).resolve()

    # Résolution since
    if since is None:
        # Premier commit du repo
        first_sha = _run_git(
            ["rev-list", "--max-parents=0", branch],
            cwd=repo,
        ).strip().split("\n")[0]
        # On utilise un état vide comme "avant" car le 1er commit lui-même
        # contribue à l'inventaire.
        # Sémantique : delta entre rien et état actuel = total CFP actuel
        before = CosmicScanReport(scope="before:repo-start", mode=mode)
        since_label = "repo-start"
    elif isinstance(since, str):
        before_sha = _resolve_ref(repo, since)
        with _git_worktree(repo, before_sha) as wt:
            before = scan_repo_cosmic(
                wt, mode=mode, use_git=True,
                scope_label=f"since:{since}@{before_sha[:8]}",
            )
        since_label = since
    else:
        before_sha = _commit_before_date(repo, since, branch=branch)
        with _git_worktree(repo, before_sha) as wt:
            before = scan_repo_cosmic(
                wt, mode=mode, use_git=True,
                scope_label=f"since:{since}@{before_sha[:8]}",
            )
        since_label = str(since)

    # Résolution until
    if until is None:
        until_sha = _resolve_ref(repo, branch)
        until_label = branch
    elif isinstance(until, str):
        until_sha = _resolve_ref(repo, until)
        until_label = until
    else:
        until_sha = _commit_before_date(repo, until, branch=branch)
        until_label = str(until)

    with _git_worktree(repo, until_sha) as wt:
        after = scan_repo_cosmic(
            wt, mode=mode, use_git=True,
            scope_label=f"until:{until_label}@{until_sha[:8]}",
        )

    return CosmicDelta(
        scope=f"range:{since_label}..{until_label}",
        mode=mode,
        before=before,
        after=after,
    )
