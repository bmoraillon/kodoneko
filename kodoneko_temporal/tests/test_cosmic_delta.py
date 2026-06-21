"""Tests des helpers COSMIC temporels (compute_cosmic_at_ref / delta)."""

import os
import subprocess
import tempfile
from pathlib import Path

from kodoneko_temporal import (
    compute_cosmic_at_ref,
    compute_cosmic_delta_for_commit,
    compute_cosmic_delta_for_range,
)


def _make_repo() -> Path:
    """Repo à 2 commits : le 2e ajoute un endpoint (1 entry + 1 read + 1 exit)."""
    d = Path(tempfile.mkdtemp(prefix="kdn_cd_"))
    base_env = {**os.environ}

    def git(*args, date="2025-01-15T12:00:00"):
        e = {**base_env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run(["git", *args], cwd=str(d), env=e, capture_output=True, check=True)

    git("init")
    git("config", "user.email", "t@t.com")
    git("config", "user.name", "t")
    (d / "app").mkdir()
    (d / "app" / "a.py").write_text("def helper():\n    return 1\n")
    git("add", "-A")
    git("commit", "-m", "init")
    # Tag v0.1.0 sur l'état initial
    git("tag", "v0.1.0")
    # Commit 2 : ajoute un endpoint
    (d / "app" / "a.py").write_text(
        '@app.get("/users")\n'
        'def list_users(session=None):\n'
        '    return session.query(User).all()\n'
    )
    git("add", "-A", date="2025-02-15T12:00:00")
    git("commit", "-m", "add endpoint", date="2025-02-15T12:00:00")
    git("tag", "v0.2.0", date="2025-02-15T12:00:00")
    return d


class TestComputeCosmicAtRef:
    def test_at_head(self):
        d = _make_repo()
        report = compute_cosmic_at_ref(d, "HEAD")
        assert report.total_cfp == 3  # 1 endpoint

    def test_at_initial_tag(self):
        d = _make_repo()
        report = compute_cosmic_at_ref(d, "v0.1.0")
        assert report.total_cfp == 0  # pas encore d'endpoint


class TestDeltaForCommit:
    def test_delta_of_endpoint_commit(self):
        d = _make_repo()
        delta = compute_cosmic_delta_for_commit(d, "HEAD")
        # Le commit ajoute exactement 1 endpoint = +3 CFP
        assert delta.cfp_added == 3

    def test_delta_has_breakdown(self):
        d = _make_repo()
        delta = compute_cosmic_delta_for_commit(d, "HEAD")
        # Le delta porte une décomposition par type de mouvement
        assert delta.by_type_delta  # décomposition par type de mouvement


class TestDeltaForRange:
    def test_range_between_tags(self):
        d = _make_repo()
        delta = compute_cosmic_delta_for_range(d, since="v0.1.0", until="v0.2.0")
        assert delta.cfp_added == 3

    def test_range_full_history(self):
        d = _make_repo()
        delta = compute_cosmic_delta_for_range(d)
        # Du début à HEAD : +3 CFP
        assert delta.cfp_added == 3
