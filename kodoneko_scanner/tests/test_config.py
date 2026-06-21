"""Tests pour kodoneko_scanner.config."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "kodoneko_metrics" / "src"))

import pytest

from kodoneko_scanner.config import (
    ConfigError,
    DEFAULT_PRIMARY_WEIGHTS,
    DEFAULT_UNDERSTANDABILITY_THRESHOLDS,
    DEFAULT_UNDERSTANDABILITY_WEIGHTS,
    KodoNekoConfig,
    example_config_toml,
    load_config,
)


class TestDefaults:
    """Vérifie les valeurs par défaut."""

    def test_primary_weights_sum_to_one(self):
        total = sum(DEFAULT_PRIMARY_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6

    def test_understandability_weights_sum_to_one(self):
        total = sum(DEFAULT_UNDERSTANDABILITY_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6

    def test_understandability_weight_dominant(self):
        """L'understandability doit dominer dans le PrimaryQualityScore."""
        assert DEFAULT_PRIMARY_WEIGHTS["understandability"] >= 0.5

    def test_thresholds_standard_monotonic(self):
        """Pour les métriques standard, low < high < very_high."""
        for metric, levels in DEFAULT_UNDERSTANDABILITY_THRESHOLDS.items():
            if metric == "identifier_length":
                continue
            assert levels["low"] < levels["high"] < levels["very_high"]

    def test_thresholds_identifier_length_inverted(self):
        """Pour identifier_length : low > high > very_high (inversé)."""
        levels = DEFAULT_UNDERSTANDABILITY_THRESHOLDS["identifier_length"]
        assert levels["low"] > levels["high"] > levels["very_high"]


class TestLoadConfig:
    """Tests du chargement de configuration."""

    def test_load_defaults_when_no_file(self, tmp_path, monkeypatch):
        """Sans fichier ni env var, retourne les défauts."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KODONEKO_CONFIG", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))  # isole ~/.config
        cfg = load_config()
        assert cfg.source == "defaults"
        assert cfg.primary_weights == DEFAULT_PRIMARY_WEIGHTS

    def test_load_from_explicit_path(self, tmp_path):
        """Avec --config, charge le fichier indiqué."""
        path = tmp_path / "my-config.toml"
        path.write_text(example_config_toml())
        cfg = load_config(str(path))
        assert cfg.source == str(path)

    def test_explicit_path_missing_raises(self, tmp_path):
        """Fichier inexistant explicite → ConfigError."""
        with pytest.raises(ConfigError, match="introuvable"):
            load_config(str(tmp_path / "nope.toml"))

    def test_load_partial_config(self, tmp_path):
        """Une config partielle reprend les défauts pour le reste."""
        path = tmp_path / "partial.toml"
        path.write_text("""
[primary_score.weights]
ncloc = 0.1
halstead = 0.05
mccabe = 0.15
understandability = 0.7
""")
        cfg = load_config(str(path))
        # Les poids understandability restent aux défauts
        assert cfg.understandability_weights == DEFAULT_UNDERSTANDABILITY_WEIGHTS

    def test_load_with_env_variable(self, tmp_path, monkeypatch):
        """KODONEKO_CONFIG est respecté."""
        path = tmp_path / "env-config.toml"
        path.write_text(example_config_toml())
        monkeypatch.setenv("KODONEKO_CONFIG", str(path))
        cfg = load_config()
        assert cfg.source == str(path)

    def test_load_from_cwd(self, tmp_path, monkeypatch):
        """./kodoneko.toml est trouvé automatiquement."""
        path = tmp_path / "kodoneko.toml"
        path.write_text(example_config_toml())
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KODONEKO_CONFIG", raising=False)
        cfg = load_config()
        assert cfg.source == str(path)


class TestValidation:
    """Tests de validation des configurations."""

    def test_weights_dont_sum_to_one(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text("""
[primary_score.weights]
ncloc = 0.5
halstead = 0.5
mccabe = 0.5
understandability = 0.5
""")
        with pytest.raises(ConfigError, match="somme des poids"):
            load_config(str(path))

    def test_partial_config_uses_defaults_for_missing(self, tmp_path):
        """Une clé absente dans primary_score.weights → reprend le défaut.

        C'est le comportement souhaité : pouvoir surcharger juste un poids
        sans devoir tout redéclarer.
        """
        path = tmp_path / "partial.toml"
        # On change uniquement understandability ; les 3 autres doivent
        # garder leurs valeurs par défaut (somme = 1.0 grâce aux défauts).
        path.write_text("""
[primary_score.weights]
understandability = 0.7
""")
        cfg = load_config(str(path))
        # understandability surchargée
        assert cfg.primary_weights["understandability"] == 0.7
        # les autres reprennent les défauts
        assert cfg.primary_weights["ncloc"] == DEFAULT_PRIMARY_WEIGHTS["ncloc"]
        assert cfg.primary_weights["halstead"] == DEFAULT_PRIMARY_WEIGHTS["halstead"]
        assert cfg.primary_weights["mccabe"] == DEFAULT_PRIMARY_WEIGHTS["mccabe"]

    def test_unknown_weight_key(self, tmp_path):
        path = tmp_path / "unknown.toml"
        path.write_text("""
[primary_score.weights]
ncloc = 0.1
halstead = 0.05
mccabe = 0.15
understandability = 0.6
foo = 0.1
""")
        with pytest.raises(ConfigError, match="inconnues"):
            load_config(str(path))

    def test_negative_weight(self, tmp_path):
        path = tmp_path / "negative.toml"
        path.write_text("""
[primary_score.weights]
ncloc = -0.1
halstead = 0.15
mccabe = 0.25
understandability = 0.7
""")
        with pytest.raises(ConfigError, match="négative"):
            load_config(str(path))

    def test_threshold_non_monotonic(self, tmp_path):
        path = tmp_path / "threshold.toml"
        path.write_text("""
[understandability.thresholds.cognitive]
low = 30
high = 15
very_high = 5
""")
        with pytest.raises(ConfigError, match="ordre attendu"):
            load_config(str(path))

    def test_threshold_identifier_length_must_be_inverted(self, tmp_path):
        """identifier_length avec ordre croissant doit échouer."""
        path = tmp_path / "id.toml"
        path.write_text("""
[understandability.thresholds.identifier_length]
low = 3
high = 5
very_high = 8
""")
        with pytest.raises(ConfigError, match="identifier_length"):
            load_config(str(path))


class TestExampleConfig:
    """Vérifie que le TOML de référence généré est valide."""

    def test_example_loads_without_error(self, tmp_path):
        path = tmp_path / "example.toml"
        path.write_text(example_config_toml())
        cfg = load_config(str(path))
        # Identique aux défauts (puisque c'est le template par défaut)
        assert cfg.primary_weights == DEFAULT_PRIMARY_WEIGHTS
        assert cfg.understandability_weights == DEFAULT_UNDERSTANDABILITY_WEIGHTS

    def test_example_is_commented(self):
        """Le template doit contenir des commentaires explicatifs."""
        content = example_config_toml()
        assert "#" in content
        assert "somme = 1.0" in content


class TestApplyConfig:
    """Vérifie que la config impacte effectivement le PrimaryQualityScore."""

    def test_score_changes_with_custom_weights(self, tmp_path):
        """Avec des poids différents, le score change."""
        from kodoneko_metrics import (
            CombinedMetrics, LineCounts, HalsteadMetrics,
            McCabeMetrics, UnderstandabilityMetrics,
        )
        from kodoneko_scanner import (
            FileReport, RepoMetrics, compute_primary_quality_score,
        )

        # Fichier avec McCabe très haut, understandability basse
        m = CombinedMetrics(
            lines=LineCounts(50, 0, 0, 50, 50, "python", "mock"),
            halstead=HalsteadMetrics(n1=5, n2=5, N1=20, N2=20,
                                       language="python", backend="mock"),
            mccabe=McCabeMetrics.from_decision_count(
                60, language="python", backend="mock"),  # very_high
            understandability=UnderstandabilityMetrics.from_components(
                cognitive=2,
                function_length_max=10, function_length_avg=10.0,
                nesting_depth_max=1, parameter_count_max=2,
                line_density_avg=40.0, identifier_length_avg=8.0,
                functions=[],
                language="python", backend="mock",
            ),
            language="python",
        )
        f = FileReport(path="a.py", relative_path="a.py",
                       language="python", size_bytes=100, metrics=m)
        report = RepoMetrics(repo_path="/test", by_file=[f])

        # Config "mccabe-centric"
        path1 = tmp_path / "mccabe.toml"
        path1.write_text("""
[primary_score.weights]
ncloc = 0.0
halstead = 0.0
mccabe = 1.0
understandability = 0.0
""")
        cfg1 = load_config(str(path1))
        bs1 = compute_primary_quality_score(report, config=cfg1)

        # Config "understandability-centric"
        path2 = tmp_path / "u.toml"
        path2.write_text("""
[primary_score.weights]
ncloc = 0.0
halstead = 0.0
mccabe = 0.0
understandability = 1.0
""")
        cfg2 = load_config(str(path2))
        bs2 = compute_primary_quality_score(report, config=cfg2)

        # McCabe est very_high (pénalité 100), understandability est low (0).
        # bs1 (focus mccabe) doit être bien plus bas que bs2 (focus u).
        assert bs1.score < bs2.score
        assert bs1.grade == "E"  # very_high → score 0
        assert bs2.grade == "A"  # low → score 100
