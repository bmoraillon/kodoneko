"""Tests du moteur temporel kodoneko_temporal."""

import os
import subprocess
import tempfile
from pathlib import Path

from kodoneko_temporal import (
    is_git_repo, analyze_at_ref, analyze_over_windows,
    TemporalPoint, TemporalSeries, iter_windows,
)
from kodoneko_temporal.temporal_engine import TemporalError
from kodoneko_scanner import scan_repo_cosmic


def _make_repo() -> Path:
    d = Path(tempfile.mkdtemp(prefix="kdn_test_"))
    env = {**os.environ, "GIT_AUTHOR_DATE": "2025-01-15T12:00:00",
           "GIT_COMMITTER_DATE": "2025-01-15T12:00:00"}
    def git(*args, e=env):
        subprocess.run(["git", *args], cwd=str(d), env=e, capture_output=True, check=True)
    git("init"); git("config", "user.email", "t@t.com"); git("config", "user.name", "t")
    (d / "app").mkdir()
    (d / "app" / "a.py").write_text("def f():\n    pass\n")
    git("add", "-A"); git("commit", "-m", "init")
    (d / "app" / "a.py").write_text(
        '@app.get("/users")\ndef list_users(session=None):\n    return session.query(User).all()\n')
    env2 = {**os.environ, "GIT_AUTHOR_DATE": "2025-02-15T12:00:00",
            "GIT_COMMITTER_DATE": "2025-02-15T12:00:00"}
    git("add", "-A", e=env2); git("commit", "-m", "add endpoint", e=env2)
    return d


_COSMIC = lambda p: scan_repo_cosmic(p, use_git=False)


class TestGitDetection:
    def test_is_git_repo_true(self):
        assert is_git_repo(_make_repo())
    def test_is_git_repo_false(self):
        assert not is_git_repo(Path(tempfile.mkdtemp()))


class TestAnalyzeAtRef:
    def test_cosmic_at_head(self):
        pt = analyze_at_ref(_make_repo(), "HEAD", analyzer=_COSMIC)
        assert isinstance(pt, TemporalPoint)
        assert pt.result.total_cfp == 3
    def test_cosmic_at_initial_commit(self):
        pt = analyze_at_ref(_make_repo(), "HEAD~1", analyzer=_COSMIC)
        assert pt.result.total_cfp == 0
    def test_generic_analyzer(self):
        pt = analyze_at_ref(_make_repo(), "HEAD", analyzer=lambda p: 42)
        assert pt.result == 42
    def test_non_git_raises(self):
        try:
            analyze_at_ref(Path(tempfile.mkdtemp()), "HEAD", analyzer=_COSMIC)
            assert False
        except TemporalError:
            pass


class TestAnalyzeOverWindows:
    def test_monthly_series(self):
        series = analyze_over_windows(_make_repo(), analyzer=_COSMIC, strategy="monthly")
        assert isinstance(series, TemporalSeries)
        assert len(series) >= 1
        assert series.points[-1].result.total_cfp == 3
    def test_series_to_dict(self):
        series = analyze_over_windows(_make_repo(), analyzer=_COSMIC, strategy="monthly")
        assert "points" in series.to_dict()


class TestWindowing:
    def test_iter_windows_monthly(self):
        from datetime import date
        w = list(iter_windows(date(2025,1,1), date(2025,3,31), strategy="monthly"))
        assert len(w) == 3
        assert w[0].label == "2025-01"
