"""
Extraction de commits depuis un dépôt git (version robuste).

Stratégie : on appelle git trois fois, chaque appel étant simple et
sans sentinelle binaire fragile.

1. ``git log --pretty=format:...`` pour récupérer les métadonnées
   commit par commit (sha, dates, auteur, subject, body, parents).
2. ``git log --name-status`` pour obtenir la classification exacte
   add/modify/delete/rename de chaque fichier.
3. ``git log --numstat`` pour obtenir les insertions/suppressions
   agrégées par commit.

Cette séparation est plus simple et plus robuste que de tout faire en
un seul appel avec des sentinelles binaires que git peut altérer.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .models import CommitInfo, TemporalWindow


# Séparateur inter-commits : un mot improbable encadré de @@@. Git ne
# l'altère pas car ce sont juste des caractères ASCII normaux.
_COMMIT_BREAK = "@@@KODONEKO_COMMIT@@@"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GitExtractError(RuntimeError):
    """Erreur d'extraction git."""


# ---------------------------------------------------------------------------
# Sanity / utilitaires
# ---------------------------------------------------------------------------

def is_git_repo(path: str | Path) -> bool:
    """Indique si le chemin est un repo git valide."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(p), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_repo_date_range(repo_path: str | Path) -> tuple[datetime, datetime]:
    """Retourne (date du 1er commit, date du dernier commit) en UTC."""
    p = Path(repo_path).expanduser().resolve()
    if not is_git_repo(p):
        raise GitExtractError(f"Pas un repo git : {p}")

    try:
        first = subprocess.run(
            ["git", "-C", str(p), "log", "--reverse", "--format=%aI", "-1"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        last = subprocess.run(
            ["git", "-C", str(p), "log", "--format=%aI", "-1"],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitExtractError(f"git log a échoué : {e.stderr}") from e

    first_str = first.stdout.strip()
    last_str = last.stdout.strip()
    if not first_str or not last_str:
        raise GitExtractError(f"Repo vide : {p}")

    return (_parse_iso(first_str), _parse_iso(last_str))


# ---------------------------------------------------------------------------
# Extraction principale
# ---------------------------------------------------------------------------

def extract_commits(
    repo_path: str | Path,
    *,
    window: Optional[TemporalWindow] = None,
    include_merges: bool = False,
    branch: Optional[str] = None,
) -> list[CommitInfo]:
    """Extrait les commits, optionnellement filtrés par fenêtre temporelle.

    Stratégie en 3 passes git pour robustesse.
    Retourne une liste triée chronologiquement (du plus ancien au plus récent).
    """
    p = Path(repo_path).expanduser().resolve()
    if not is_git_repo(p):
        raise GitExtractError(f"Pas un repo git : {p}")

    common_args = []
    if window is not None:
        common_args.append(f"--since={window.start.isoformat()}")
        until_exclusive = window.end + timedelta(days=1)
        common_args.append(f"--until={until_exclusive.isoformat()}")
    if not include_merges:
        common_args.append("--no-merges")
    if branch:
        common_args.append(branch)

    metadata_by_sha = _extract_metadata(p, common_args)
    status_by_sha = _extract_name_status(p, common_args)
    numstat_by_sha = _extract_numstat(p, common_args)

    commits = []
    for sha, meta in metadata_by_sha.items():
        status = status_by_sha.get(sha, ([], [], [], []))
        numstat = numstat_by_sha.get(sha, (0, 0))
        added, modified, deleted, renamed = status
        total_ins, total_del = numstat
        commits.append(CommitInfo(
            sha=sha,
            short_sha=sha[:7],
            author_name=meta["author_name"],
            author_email=meta["author_email"],
            author_date=meta["author_date"],
            committer_date=meta["committer_date"],
            subject=meta["subject"],
            body=meta["body"],
            files_added=tuple(added),
            files_modified=tuple(modified),
            files_deleted=tuple(deleted),
            files_renamed=tuple(renamed),
            insertions=total_ins,
            deletions=total_del,
            is_merge=meta["is_merge"],
        ))

    commits.sort(key=lambda c: c.author_date)
    return commits


# ---------------------------------------------------------------------------
# Passe 1 : métadonnées
# ---------------------------------------------------------------------------

def _extract_metadata(repo: Path, common_args: list[str]) -> dict:
    """Retourne {sha: dict_de_métadonnées}."""
    # Format : 8 lignes par commit (les 7 premières fixes, la 8e = body
    # qui peut être multiligne), puis _COMMIT_BREAK comme séparateur.
    fmt = "%H%n%an%n%ae%n%aI%n%cI%n%P%n%s%n%B" + _COMMIT_BREAK
    args = [
        "git", "-C", str(repo), "log",
        f"--pretty=format:{fmt}",
        "--no-patch",
    ] + common_args

    try:
        result = subprocess.run(args, capture_output=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        raise GitExtractError(
            f"git log (metadata) a échoué : "
            f"{e.stderr.decode('utf-8', errors='replace')}"
        ) from e

    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        text = result.stdout.decode("latin-1", errors="replace")

    out = {}
    for raw_block in text.split(_COMMIT_BREAK):
        block = raw_block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 7:
            continue
        sha = lines[0].strip()
        author_name = lines[1]
        author_email = lines[2]
        author_date_iso = lines[3].strip()
        committer_date_iso = lines[4].strip()
        parents = lines[5].strip().split()
        subject = lines[6]
        body_full = "\n".join(lines[7:]) if len(lines) > 7 else ""
        body = body_full
        if body.startswith(subject):
            body = body[len(subject):].lstrip("\n").strip()
        else:
            body = body.strip()

        try:
            author_date = _parse_iso(author_date_iso)
            committer_date = _parse_iso(committer_date_iso)
        except ValueError:
            continue

        out[sha] = {
            "author_name": author_name,
            "author_email": author_email,
            "author_date": author_date,
            "committer_date": committer_date,
            "subject": subject,
            "body": body,
            "is_merge": len(parents) > 1,
        }
    return out


# ---------------------------------------------------------------------------
# Passe 2 : name-status (A/M/D/R)
# ---------------------------------------------------------------------------

def _extract_name_status(repo: Path, common_args: list[str]) -> dict:
    """Retourne {sha: (added, modified, deleted, renamed)}."""
    fmt = "%H" + _COMMIT_BREAK
    args = [
        "git", "-C", str(repo), "log",
        f"--pretty=format:{fmt}",
        "--name-status",
        "--no-color",
        "--find-renames",
    ] + common_args

    try:
        result = subprocess.run(args, capture_output=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        raise GitExtractError(
            f"git log (name-status) a échoué : "
            f"{e.stderr.decode('utf-8', errors='replace')}"
        ) from e

    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        text = result.stdout.decode("latin-1", errors="replace")

    out = {}
    for raw_block in text.split(_COMMIT_BREAK):
        block = raw_block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        if not lines:
            continue
        sha = lines[0].strip()
        added, modified, deleted, renamed = [], [], [], []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if not parts:
                continue
            status = parts[0]
            if status.startswith("A") and len(parts) >= 2:
                added.append(parts[1])
            elif status.startswith("M") and len(parts) >= 2:
                modified.append(parts[1])
            elif status.startswith("D") and len(parts) >= 2:
                deleted.append(parts[1])
            elif (status.startswith("R") or status.startswith("C")) and len(parts) >= 3:
                renamed.append((parts[1], parts[2]))
        out[sha] = (added, modified, deleted, renamed)
    return out


# ---------------------------------------------------------------------------
# Passe 3 : numstat (insertions/suppressions agrégées)
# ---------------------------------------------------------------------------

def _extract_numstat(repo: Path, common_args: list[str]) -> dict:
    """Retourne {sha: (total_insertions, total_deletions)}."""
    fmt = "%H" + _COMMIT_BREAK
    args = [
        "git", "-C", str(repo), "log",
        f"--pretty=format:{fmt}",
        "--numstat",
        "--no-color",
    ] + common_args

    try:
        result = subprocess.run(args, capture_output=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        raise GitExtractError(
            f"git log (numstat) a échoué : "
            f"{e.stderr.decode('utf-8', errors='replace')}"
        ) from e

    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        text = result.stdout.decode("latin-1", errors="replace")

    out = {}
    for raw_block in text.split(_COMMIT_BREAK):
        block = raw_block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        if not lines:
            continue
        sha = lines[0].strip()
        total_ins, total_del = 0, 0
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                total_ins += _safe_int(parts[0])
                total_del += _safe_int(parts[1])
        out[sha] = (total_ins, total_del)
    return out


# ---------------------------------------------------------------------------
# Récupération de diffs (v0.3)
# ---------------------------------------------------------------------------

def get_commit_diff(
    repo_path: str | Path,
    sha: str,
    *,
    max_size_bytes: int = 1_000_000,
    timeout: float = 30.0,
) -> str:
    """Récupère le diff unifié d'un commit via ``git show``.

    Utilisé par l'extraction de signaux locaux (``code_signals``). Le
    diff retourné est le diff produit par ``git show --no-color -U3``
    qui inclut les en-têtes ``diff --git`` exploitables par
    ``parse_unified_diff``.

    Paramètres
    ----------
    repo_path : path-like
        Chemin du dépôt git.
    sha : str
        SHA du commit (court ou long, peu importe — git résout).
    max_size_bytes : int
        Taille max du diff à retourner (en octets de bytes brut). Si
        dépassée, le diff est tronqué et un commentaire de troncature
        est appliqué. Évite d'exploser la mémoire sur des commits
        géants (genoa-style refactors importés en bloc).
    timeout : float
        Timeout subprocess (secondes).

    Retourne
    --------
    str : diff unifié, ou chaîne vide si le commit n'existe pas ou
        si l'appel git échoue (on ne lève pas — un diff manquant ne
        doit pas casser le pipeline).
    """
    p = Path(repo_path).expanduser().resolve()
    if not is_git_repo(p):
        return ""
    if not sha:
        return ""

    args = [
        "git", "-C", str(p), "show",
        "--no-color", "--unified=3", "--format=", "--no-textconv",
        sha,
    ]
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout, check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""

    if result.returncode != 0:
        return ""

    raw = result.stdout
    if max_size_bytes > 0 and len(raw) > max_size_bytes:
        raw = raw[:max_size_bytes]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        text += "\n# [diff tronqué : taille originale > max_size_bytes]\n"
        return text

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def get_commits_diff_combined(
    repo_path: str | Path,
    shas: list,
    *,
    max_size_bytes_per_commit: int = 200_000,
    max_total_size_bytes: int = 2_000_000,
) -> str:
    """Récupère et concatène les diffs de plusieurs commits.

    Pratique pour un item de changement composé de plusieurs commits :
    le ``code_signals`` peut alors voir le tableau d'ensemble en une
    seule passe sans gérer la concaténation lui-même.

    Les diffs sont séparés par une ligne blanche, et chaque diff est
    capé à ``max_size_bytes_per_commit``. Si le total dépasse
    ``max_total_size_bytes``, les diffs restants sont omis (avec un
    commentaire de troncature).

    Paramètres
    ----------
    repo_path : path-like
    shas : list[str]
    max_size_bytes_per_commit : int
        Limite par commit. Compromis entre information et coût mémoire.
    max_total_size_bytes : int
        Limite globale pour l'ensemble des diffs.

    Retourne
    --------
    str : diff unifié concaténé. Chaîne vide si shas est vide.
    """
    if not shas:
        return ""

    pieces: list = []
    total = 0
    truncated_count = 0
    for sha in shas:
        diff = get_commit_diff(
            repo_path, sha, max_size_bytes=max_size_bytes_per_commit,
        )
        if not diff:
            continue
        if total + len(diff.encode("utf-8")) > max_total_size_bytes:
            truncated_count = len(shas) - len(pieces)
            break
        pieces.append(diff)
        total += len(diff.encode("utf-8"))

    out = "\n".join(pieces)
    if truncated_count > 0:
        out += (
            f"\n# [diff tronqué : {truncated_count} commit(s) restants "
            f"non inclus, taille max atteinte]\n"
        )
    return out


# ---------------------------------------------------------------------------
# Compat ancienne API
# ---------------------------------------------------------------------------

def refine_file_status(repo_path: str | Path, commits: list[CommitInfo]) -> list[CommitInfo]:
    """Compat : ne fait rien désormais (intégré à extract_commits)."""
    return commits


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _safe_int(s: str) -> int:
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 (formats %aI et %cI de git) en datetime aware UTC."""
    iso_str = iso_str.strip()
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
