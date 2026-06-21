"""
Tests pour kodoneko_scanner.

Tests organisés en familles :
- Tests des modèles (sans dépendance externe)
- Tests de l'énumération des fichiers (avec dossiers temporaires)
- Tests d'intégration scan_repo (skippés si tree-sitter pas installé)
- Tests de la CLI
"""
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "kodoneko_metrics" / "src"))

import pytest

from kodoneko_scanner import (
    DEFAULT_EXCLUDED_DIRS,
    FileReport,
    RepoMetrics,
    Totals,
    scan_repo,
)
from kodoneko_scanner.scanner import (
    _is_git_repo,
    _walk_dir,
)


def _try_import_tree_sitter() -> bool:
    try:
        import tree_sitter
        import tree_sitter_python
        return True
    except ImportError:
        return False


HAS_TREE_SITTER = _try_import_tree_sitter()
TS_SKIP = pytest.mark.skipif(
    not HAS_TREE_SITTER, reason="tree-sitter non installé"
)


# ===========================================================================
# Modèles
# ===========================================================================

class TestTotals:
    def test_default_values_are_zero(self):
        t = Totals()
        assert t.total == 0
        assert t.ncloc == 0
        assert t.halstead_volume == 0.0
        assert t.files_count == 0

    def test_to_dict(self):
        t = Totals(total=100, ncloc=80, mccabe_max=5)
        d = t.to_dict()
        assert d["total"] == 100
        assert d["ncloc"] == 80
        assert d["mccabe_max"] == 5


class TestFileReport:
    def test_basic(self):
        f = FileReport(
            path="/foo/bar.py",
            relative_path="bar.py",
            language="python",
            size_bytes=1024,
        )
        assert f.metrics is None
        assert f.error is None

    def test_to_dict_no_metrics(self):
        f = FileReport(
            path="/foo.py", relative_path="foo.py",
            language="python", size_bytes=42,
        )
        d = f.to_dict()
        assert d["language"] == "python"
        assert d["metrics"] is None


class TestRepoMetricsHotspots:
    """Test du tri des hotspots — sans tree-sitter (avec métriques mockées)."""

    def _make_file(self, name, cognitive_value, mccabe_value, ncloc):
        """Construit un FileReport avec des métriques minimalement valides."""
        from kodoneko_metrics import (
            CombinedMetrics, LineCounts, HalsteadMetrics,
            McCabeMetrics, UnderstandabilityMetrics,
        )
        m = CombinedMetrics(
            lines=LineCounts(
                total=ncloc, blank=0, comment=0,
                sloc=ncloc, ncloc=ncloc,
                language="python", backend="mock",
            ),
            halstead=HalsteadMetrics(
                n1=1, n2=1, N1=1, N2=1,
                language="python", backend="mock",
            ),
            mccabe=McCabeMetrics.from_decision_count(
                mccabe_value - 1, language="python", backend="mock",
            ),
            understandability=UnderstandabilityMetrics.from_components(
                cognitive=cognitive_value,
                function_length_max=10,
                function_length_avg=10.0,
                nesting_depth_max=1,
                parameter_count_max=2,
                line_density_avg=40.0,
                identifier_length_avg=8.0,
                functions=[],
                language="python", backend="mock",
            ),
            language="python",
        )
        return FileReport(
            path=name, relative_path=name,
            language="python", size_bytes=100, metrics=m,
        )

    def test_hotspots_by_cognitive(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file("a.py", cognitive_value=5, mccabe_value=3, ncloc=10),
            self._make_file("b.py", cognitive_value=20, mccabe_value=2, ncloc=30),
            self._make_file("c.py", cognitive_value=15, mccabe_value=8, ncloc=20),
        ]
        hotspots = report.hotspots(top=2, by="cognitive")
        assert len(hotspots) == 2
        assert hotspots[0].relative_path == "b.py"  # cognitive=20
        assert hotspots[1].relative_path == "c.py"  # cognitive=15

    def test_hotspots_by_mccabe(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file("a.py", cognitive_value=5, mccabe_value=3, ncloc=10),
            self._make_file("b.py", cognitive_value=20, mccabe_value=2, ncloc=30),
            self._make_file("c.py", cognitive_value=15, mccabe_value=8, ncloc=20),
        ]
        hotspots = report.hotspots(top=10, by="mccabe")
        assert hotspots[0].relative_path == "c.py"  # mccabe=8

    def test_hotspots_by_ncloc(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file("a.py", cognitive_value=5, mccabe_value=3, ncloc=10),
            self._make_file("b.py", cognitive_value=20, mccabe_value=2, ncloc=30),
        ]
        hotspots = report.hotspots(top=1, by="ncloc")
        assert hotspots[0].relative_path == "b.py"

    def test_invalid_criterion_raises(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [self._make_file("a.py", 1, 1, 1)]
        with pytest.raises(ValueError):
            report.hotspots(top=1, by="unknown")


# ===========================================================================
# Énumération des fichiers
# ===========================================================================

class TestWalkDir:
    """Test du parcours manuel de répertoire."""

    def test_simple_walk(self, tmp_path):
        # Créer une mini-arborescence
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "c.py").write_text("z = 3")
        files = list(_walk_dir(tmp_path, frozenset()))
        names = sorted(f.name for f in files)
        assert names == ["a.py", "b.py", "c.py"]

    def test_excluded_dir(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "ignored.py").write_text("nope")
        files = list(_walk_dir(tmp_path, frozenset({"node_modules"})))
        names = [f.name for f in files]
        assert "a.py" in names
        assert "ignored.py" not in names

    def test_nested_excluded_dir(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "__pycache__").mkdir()
        (tmp_path / "sub" / "__pycache__" / "ignored.pyc").write_text("x")
        files = list(_walk_dir(tmp_path, frozenset({"__pycache__"})))
        names = [f.name for f in files]
        assert "ignored.pyc" not in names


# ===========================================================================
# Validation des paramètres
# ===========================================================================

class TestScanRepoValidation:
    def test_path_must_exist(self):
        with pytest.raises(ValueError):
            scan_repo("/nonexistent/path/abc123")

    def test_path_must_be_dir(self, tmp_path):
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        with pytest.raises(ValueError):
            scan_repo(str(f))


# ===========================================================================
# Intégration scan_repo (tree-sitter requis)
# ===========================================================================

@TS_SKIP
class TestScanRepoIntegration:
    """Test du scan d'un mini-projet réel."""

    def _make_miniproject(self, tmp_path):
        """Crée un mini-projet Python avec 3 fichiers."""
        (tmp_path / "simple.py").write_text(
            'def f():\n    return 1\n'
        )
        (tmp_path / "complex.py").write_text(
            'def g(x):\n'
            '    if x > 0:\n'
            '        for i in range(x):\n'
            '            if i % 2:\n'
            '                print(i)\n'
            '    return x\n'
        )
        # Fichier ignoré (extension inconnue)
        (tmp_path / "readme.txt").write_text("hello")
        # Dossier ignoré
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "ignored.pyc").write_bytes(b"binary")

    def test_basic_scan(self, tmp_path):
        self._make_miniproject(tmp_path)
        r = scan_repo(str(tmp_path), use_git=False)
        # 2 fichiers Python analysés
        assert r.files_scanned == 2
        # readme.txt et le pyc sont sautés
        assert r.files_skipped >= 1
        # NCLOC > 0
        assert r.totals.ncloc > 0
        # Au moins une fonction avec McCabe > 1
        assert r.totals.mccabe_max >= 2

    def test_by_language(self, tmp_path):
        self._make_miniproject(tmp_path)
        r = scan_repo(str(tmp_path), use_git=False)
        assert "python" in r.by_language
        assert r.by_language["python"].files_count == 2

    def test_languages_filter(self, tmp_path):
        self._make_miniproject(tmp_path)
        # Ne demander que TypeScript : aucun fichier ne passe
        r = scan_repo(str(tmp_path), use_git=False, languages=["typescript"])
        assert r.files_scanned == 0

    def test_hotspots(self, tmp_path):
        self._make_miniproject(tmp_path)
        r = scan_repo(str(tmp_path), use_git=False)
        hotspots = r.hotspots(top=5, by="cognitive")
        # complex.py doit être plus haut que simple.py
        assert len(hotspots) == 2
        assert hotspots[0].relative_path == "complex.py"

    def test_to_dict_serializable(self, tmp_path):
        self._make_miniproject(tmp_path)
        r = scan_repo(str(tmp_path), use_git=False)
        d = r.to_dict()
        # Doit être JSON-sérialisable
        json_str = json.dumps(d)
        assert "files_scanned" in json_str
        assert "totals" in json_str

    def test_max_file_size(self, tmp_path):
        # Créer un fichier "gros" et un petit
        (tmp_path / "big.py").write_text("x = 1\n" * 1000)  # ~6KB
        (tmp_path / "small.py").write_text("y = 2\n")
        # Avec un max de 100 octets, big.py doit être sauté
        r = scan_repo(str(tmp_path), use_git=False, max_file_size=100)
        names = [f.relative_path for f in r.by_file]
        assert "small.py" in names
        assert "big.py" not in names

    def test_errors_logged_not_raised(self, tmp_path):
        # Un fichier avec syntaxe invalide ne doit pas faire planter le scan
        (tmp_path / "ok.py").write_text("x = 1\n")
        (tmp_path / "bad.py").write_text("def f(:\n    nope")
        r = scan_repo(str(tmp_path), use_git=False)
        # ok.py doit être analysé
        # bad.py peut soit être analysé (tree-sitter tolère le code invalide)
        # soit être en erreur (selon la grammaire)
        assert r.files_scanned >= 1


# ===========================================================================
# CLI
# ===========================================================================

@TS_SKIP
class TestCLI:
    """Test de la CLI."""

    def test_cli_text_output(self, tmp_path, capsys=None):
        from kodoneko_scanner.cli import main
        (tmp_path / "a.py").write_text("def f(): return 1\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main([str(tmp_path), "--no-git"])

        assert exit_code == 0
        output = buf.getvalue()
        assert "Totaux globaux" in output
        assert "NCLOC" in output

    def test_cli_json_output(self, tmp_path):
        from kodoneko_scanner.cli import main
        (tmp_path / "a.py").write_text("def f(): return 1\n")

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main([str(tmp_path), "--no-git", "--json"])

        assert exit_code == 0
        data = json.loads(buf.getvalue())
        assert "files_scanned" in data
        assert "totals" in data

    def test_cli_invalid_path(self):
        from kodoneko_scanner.cli import main
        exit_code = main(["/nonexistent/abc123"])
        assert exit_code == 1


# ===========================================================================
# Tests de l'interpréteur (table de correspondance + PrimaryQualityScore)
# ===========================================================================

from kodoneko_scanner import (
    PrimaryQualityScore,
    LEVEL_INTERPRETATIONS,
    comment_file,
    compute_primary_quality_score,
    format_primary_report,
)
from kodoneko_scanner.interpret import (
    _halstead_level, _ncloc_level, _score_to_grade,
)


class TestLevelInterpretations:
    """Tests de la table de correspondance."""

    def test_all_metrics_have_4_levels(self):
        """Chaque métrique doit avoir les 4 niveaux."""
        for metric in ("ncloc", "halstead", "mccabe", "understandability"):
            assert metric in LEVEL_INTERPRETATIONS
            for level in ("low", "moderate", "high", "very_high"):
                entry = LEVEL_INTERPRETATIONS[metric][level]
                assert "verb" in entry
                assert "meaning" in entry
                assert len(entry["verb"]) > 0
                assert len(entry["meaning"]) > 0


class TestThresholdHelpers:
    """Tests des helpers _ncloc_level et _halstead_level."""

    def test_ncloc_levels(self):
        assert _ncloc_level(50) == "low"
        assert _ncloc_level(100) == "low"
        assert _ncloc_level(150) == "moderate"
        assert _ncloc_level(300) == "moderate"
        assert _ncloc_level(400) == "high"
        assert _ncloc_level(500) == "high"
        assert _ncloc_level(800) == "very_high"

    def test_halstead_levels(self):
        assert _halstead_level(100.0) == "low"
        assert _halstead_level(500.0) == "low"
        assert _halstead_level(800.0) == "moderate"
        assert _halstead_level(2000.0) == "high"
        assert _halstead_level(5000.0) == "very_high"


class TestScoreToGrade:
    """Tests de la conversion score → grade."""

    def test_grade_a(self):
        assert _score_to_grade(100) == "A"
        assert _score_to_grade(85) == "A"

    def test_grade_b(self):
        assert _score_to_grade(80) == "B"
        assert _score_to_grade(70) == "B"

    def test_grade_c(self):
        assert _score_to_grade(60) == "C"
        assert _score_to_grade(55) == "C"

    def test_grade_d(self):
        assert _score_to_grade(45) == "D"
        assert _score_to_grade(40) == "D"

    def test_grade_e(self):
        assert _score_to_grade(30) == "E"
        assert _score_to_grade(0) == "E"


class TestCommentFile:
    """Tests de la génération de commentaires."""

    def _make_file(self, name, ncloc=20, volume=100.0,
                    cc_decisions=1, cog_struct=2, cog_nest=0,
                    understandability_high=False):
        from kodoneko_metrics import (
            CombinedMetrics, LineCounts, HalsteadMetrics,
            McCabeMetrics, UnderstandabilityMetrics,
        )
        # Understandability cohérente avec les autres métriques.
        # Par défaut : low. Si understandability_high=True, on force
        # plusieurs dimensions pour atteindre un score composite haut.
        cognitive_total = cog_struct + cog_nest
        if understandability_high:
            u_params = dict(
                cognitive=cognitive_total,
                function_length_max=80, function_length_avg=50.0,
                nesting_depth_max=5, parameter_count_max=8,
                line_density_avg=100.0, identifier_length_avg=3.0,
            )
        else:
            u_params = dict(
                cognitive=cognitive_total,
                function_length_max=10, function_length_avg=10.0,
                nesting_depth_max=1, parameter_count_max=2,
                line_density_avg=40.0, identifier_length_avg=8.0,
            )
        m = CombinedMetrics(
            lines=LineCounts(total=ncloc, blank=0, comment=0,
                              sloc=ncloc, ncloc=ncloc,
                              language="python", backend="mock"),
            halstead=HalsteadMetrics(n1=5, n2=8,
                                       N1=int(volume/3), N2=int(volume/3),
                                       language="python", backend="mock"),
            mccabe=McCabeMetrics.from_decision_count(
                cc_decisions, language="python", backend="mock"),
            understandability=UnderstandabilityMetrics.from_components(
                functions=[], language="python", backend="mock",
                **u_params,
            ),
            language="python",
        )
        return FileReport(
            path=f"/test/{name}", relative_path=name,
            language="python", size_bytes=ncloc*20, metrics=m,
        )

    def test_healthy_file(self):
        f = self._make_file("ok.py", ncloc=20, cog_struct=2)
        comment = comment_file(f)
        assert "✅" in comment
        assert "bonne santé" in comment

    def test_moderate_file(self):
        # cognitive=10 → moderate
        f = self._make_file("mid.py", ncloc=150, cc_decisions=12, cog_struct=10)
        comment = comment_file(f)
        assert "ℹ️" in comment
        assert "À surveiller" in comment

    def test_high_file(self):
        # Paramètres calibrés pour produire un risk dans la plage 'high' (35-60)
        # avec les seuils révisés v2.2.
        from kodoneko_metrics import (
            CombinedMetrics, LineCounts, HalsteadMetrics,
            McCabeMetrics, UnderstandabilityMetrics,
        )
        m = CombinedMetrics(
            lines=LineCounts(total=35, blank=0, comment=0, sloc=35, ncloc=35,
                             language="python", backend="mock"),
            halstead=HalsteadMetrics(n1=5, n2=8, N1=30, N2=30,
                                       language="python", backend="mock"),
            mccabe=McCabeMetrics.from_decision_count(15, language="python", backend="mock"),
            understandability=UnderstandabilityMetrics.from_components(
                cognitive=15,
                function_length_max=35, function_length_avg=30.0,
                nesting_depth_max=3, parameter_count_max=5,
                line_density_avg=50.0, identifier_length_avg=6.0,
                functions=[], language="python", backend="mock",
            ),
            language="python",
        )
        f = FileReport(path="/test/warn.py", relative_path="warn.py",
                       language="python", size_bytes=400, metrics=m)
        # Sanity check : on est bien sur "high" et pas "very_high"
        assert m.understandability.level == "high"
        comment = comment_file(f)
        assert "⚠️" in comment
        assert "Refactoring conseillé" in comment

    def test_very_high_file(self):
        # Dimensions saturées + ncloc et cognitive élevés → very_high
        f = self._make_file("crit.py", ncloc=400, cog_struct=40, cog_nest=30,
                              understandability_high=True)
        comment = comment_file(f)
        assert "🔥" in comment
        assert "fortement conseillé" in comment

    def test_error_file(self):
        f = FileReport(
            path="/err.py", relative_path="err.py",
            language="python", size_bytes=0, metrics=None,
            error="SyntaxError",
        )
        comment = comment_file(f)
        assert "⚪" in comment
        assert "SyntaxError" in comment

    def test_comment_contains_metrics(self):
        f = self._make_file("mid.py", cc_decisions=12, cog_struct=10)
        comment = comment_file(f)
        # Doit contenir les chiffres
        assert "cognitive=" in comment
        assert "mccabe=" in comment
        assert "ncloc=" in comment


class TestComputePrimaryScore:
    """Tests du calcul de l'indicateur synthétique."""

    def _make_file(self, name, **kwargs):
        # Réutilise le helper de TestCommentFile
        return TestCommentFile._make_file(self, name, **kwargs)

    def test_empty_report(self):
        """Un rapport sans fichier → score 0, grade E."""
        report = RepoMetrics(repo_path="/empty")
        hi = compute_primary_quality_score(report)
        assert hi.score == 0.0
        assert hi.grade == "E"
        assert hi.files_total == 0

    def test_all_healthy_score_high(self):
        """Que des fichiers sains → score élevé (proche de 100)."""
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file(f"f{i}.py", ncloc=20, cog_struct=2)
            for i in range(5)
        ]
        hi = compute_primary_quality_score(report)
        assert hi.score >= 95  # quasi-parfait
        assert hi.grade == "A"
        assert hi.files_critical == 0
        assert hi.files_warning == 0

    def test_all_critical_score_low(self):
        """Que des fichiers critiques → score bas."""
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file(f"f{i}.py", ncloc=600,
                             cog_struct=40, cog_nest=30,
                             cc_decisions=60, understandability_high=True)
            for i in range(3)
        ]
        hi = compute_primary_quality_score(report)
        assert hi.score < 30
        assert hi.grade in ("D", "E")
        assert hi.files_critical == 3

    def test_mixed_score_medium(self):
        """Mélange → grade C ou D."""
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file("ok1.py", ncloc=20, cog_struct=2),
            self._make_file("ok2.py", ncloc=20, cog_struct=2),
            self._make_file("warn.py", cc_decisions=15, cog_struct=20,
                              cog_nest=15, understandability_high=True),
            self._make_file("crit.py", ncloc=400, cog_struct=40,
                              cog_nest=30, understandability_high=True),
        ]
        hi = compute_primary_quality_score(report)
        assert 30 <= hi.score <= 80
        assert hi.grade in ("B", "C", "D")
        assert hi.files_critical >= 1

    def test_breakdown_structure(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [self._make_file("ok.py", ncloc=20, cog_struct=2)]
        hi = compute_primary_quality_score(report)
        # Le breakdown doit contenir les 4 métriques
        for metric in ("ncloc", "halstead", "mccabe", "understandability"):
            assert metric in hi.breakdown
            assert "weight" in hi.breakdown[metric]
            assert "penalty_avg" in hi.breakdown[metric]
            assert "percentages" in hi.breakdown[metric]

    def test_to_dict_serializable(self):
        import json
        report = RepoMetrics(repo_path="/test")
        report.by_file = [self._make_file("ok.py", ncloc=20, cog_struct=2)]
        hi = compute_primary_quality_score(report)
        d = hi.to_dict()
        # Doit être JSON-sérialisable
        json_str = json.dumps(d)
        assert "score" in json_str
        assert "grade" in json_str

    def test_primary_score_frozen(self):
        hi = PrimaryQualityScore(
            score=80.0, grade="B", breakdown={},
            files_critical=0, files_warning=0, files_total=10,
            summary="Test",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            hi.score = 0


class TestFormatPrimaryReport:
    """Tests du formatage texte global."""

    def _make_file(self, name, **kwargs):
        return TestCommentFile._make_file(self, name, **kwargs)

    def test_format_contains_score_and_grade(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [self._make_file("ok.py", ncloc=20, cog_struct=2)]
        text = format_primary_report(report, hotspot_count=0)
        assert "/100" in text
        # Le grade doit être présent
        assert any(g in text for g in ("A", "B", "C", "D", "E"))

    def test_format_with_hotspots(self):
        report = RepoMetrics(repo_path="/test")
        report.by_file = [
            self._make_file("ok.py", ncloc=20, cog_struct=2),
            self._make_file("warn.py", cc_decisions=15, cog_struct=20, cog_nest=15),
        ]
        text = format_primary_report(report, hotspot_count=2)
        assert "hotspots" in text.lower() or "warn.py" in text
