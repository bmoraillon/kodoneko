"""
Configuration paramétrable de KodoNeko via fichier TOML.

Permet d'ajuster sans toucher au code :

- les **poids** des 4 métriques dans le PrimaryQualityScore ;
- les **poids** des 6 sous-métriques dans le score Understandability ;
- les **seuils** (low / high / very_high) des 6 sous-métriques
  d'Understandability.

Format TOML, état de l'art Python depuis PEP 518/621, lisible et
commentable. Lecture via le module standard `tomllib` (Python 3.11+).

Recherche du fichier de configuration, dans l'ordre :

1. Argument explicite ``load_config(path=...)``
2. Variable d'environnement ``KODONEKO_CONFIG``
3. ``./kodoneko.toml`` dans le répertoire courant
4. ``~/.config/kodoneko/kodoneko.toml`` (config utilisateur)
5. Valeurs par défaut intégrées (aucune erreur si rien trouvé)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# tomllib est dans la stdlib depuis Python 3.11
try:
    import tomllib
except ImportError:
    # Fallback pour Python 3.10 : tomli (non utilisé en pratique, on
    # exige 3.10 minimum mais 3.11 recommandé)
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


# ---------------------------------------------------------------------------
# Valeurs par défaut (alignées sur la décision de l'auteur, v0.4)
# ---------------------------------------------------------------------------

DEFAULT_PRIMARY_WEIGHTS = {
    "ncloc":             0.10,
    "halstead":          0.05,
    "mccabe":            0.15,
    "understandability": 0.70,
}

DEFAULT_UNDERSTANDABILITY_WEIGHTS = {
    "cognitive":         0.30,
    "function_length":   0.20,
    "nesting_depth":     0.15,
    "parameter_count":   0.15,
    "line_density":      0.10,
    "identifier_length": 0.10,
}

DEFAULT_UNDERSTANDABILITY_THRESHOLDS = {
    "cognitive":         {"low": 3,  "high": 10, "very_high": 20},
    "function_length":   {"low": 8,  "high": 25, "very_high": 50},
    "nesting_depth":     {"low": 1,  "high": 3,  "very_high": 5},
    "parameter_count":   {"low": 3,  "high": 5,  "very_high": 8},
    "line_density":      {"low": 25, "high": 50, "very_high": 80},
    # identifier_length est inversé : plus c'est court, pire c'est.
    # Les seuils sont donc en ordre décroissant.
    "identifier_length": {"low": 8,  "high": 5,  "very_high": 3},
}
# Seuils révisés en v0.7 (cohérent avec kodoneko_metrics v2.2) suite au run
# de calibration pilote sur 30 cas annotés (n=10 × 3 langages).
# Cf. `calibration/results/run_002_revised_defaults.md`.


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(ValueError):
    """Erreur de configuration (poids invalides, fichier mal formé, etc.)."""


# ---------------------------------------------------------------------------
# Dataclass de configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KodoNekoConfig:
    """Configuration runtime de KodoNeko, chargée depuis TOML ou par défaut.

    Attributs
    ---------
    primary_weights : dict[str, float]
        Poids des 4 métriques (ncloc, halstead, mccabe, understandability)
        dans le PrimaryQualityScore. Somme = 1.0.
    understandability_weights : dict[str, float]
        Poids des 6 sous-métriques dans le score Understandability.
        Somme = 1.0.
    understandability_thresholds : dict[str, dict[str, float]]
        Pour chaque sous-métrique, les 3 seuils (low/high/very_high)
        définissant les paliers de normalisation 0-100.
    source : str
        Pour traçabilité : chemin du fichier chargé, ou "defaults".
    """
    primary_weights: dict = field(default_factory=lambda: dict(DEFAULT_PRIMARY_WEIGHTS))
    understandability_weights: dict = field(
        default_factory=lambda: dict(DEFAULT_UNDERSTANDABILITY_WEIGHTS)
    )
    understandability_thresholds: dict = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_UNDERSTANDABILITY_THRESHOLDS.items()}
    )
    source: str = "defaults"

    def to_dict(self) -> dict:
        return {
            "primary_weights": dict(self.primary_weights),
            "understandability_weights": dict(self.understandability_weights),
            "understandability_thresholds": {
                k: dict(v) for k, v in self.understandability_thresholds.items()
            },
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_WEIGHT_SUM_TOLERANCE = 1e-6


def _validate_weights(weights: dict, expected_keys: set, label: str) -> None:
    """Valide qu'un dict de poids respecte les contraintes :
    - toutes les clés attendues sont présentes
    - aucune clé inconnue
    - toutes les valeurs sont numériques et positives ou nulles
    - la somme vaut 1.0 à epsilon près
    """
    keys = set(weights.keys())
    missing = expected_keys - keys
    extra = keys - expected_keys
    if missing:
        raise ConfigError(
            f"{label} : clés manquantes {sorted(missing)}. "
            f"Attendu : {sorted(expected_keys)}"
        )
    if extra:
        raise ConfigError(
            f"{label} : clés inconnues {sorted(extra)}. "
            f"Autorisé : {sorted(expected_keys)}"
        )
    for k, v in weights.items():
        if not isinstance(v, (int, float)):
            raise ConfigError(
                f"{label}.{k} : valeur {v!r} n'est pas numérique"
            )
        if v < 0:
            raise ConfigError(
                f"{label}.{k} : valeur {v} négative non autorisée"
            )
    total = sum(weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ConfigError(
            f"{label} : la somme des poids doit faire 1.0, "
            f"obtenu {total:.6f}. Pondérations : {weights}"
        )


def _validate_thresholds(thresholds: dict) -> None:
    """Valide la structure et la monotonie des seuils."""
    expected_metrics = set(DEFAULT_UNDERSTANDABILITY_THRESHOLDS.keys())
    keys = set(thresholds.keys())
    missing = expected_metrics - keys
    extra = keys - expected_metrics
    if missing:
        raise ConfigError(
            f"understandability.thresholds : sous-métriques manquantes "
            f"{sorted(missing)}"
        )
    if extra:
        raise ConfigError(
            f"understandability.thresholds : sous-métriques inconnues "
            f"{sorted(extra)}"
        )
    for metric, levels in thresholds.items():
        for lvl in ("low", "high", "very_high"):
            if lvl not in levels:
                raise ConfigError(
                    f"thresholds.{metric}.{lvl} manquant"
                )
            if not isinstance(levels[lvl], (int, float)):
                raise ConfigError(
                    f"thresholds.{metric}.{lvl} = {levels[lvl]!r} non numérique"
                )
        # Monotonie :
        # - cas standard : low < high < very_high
        # - cas inversé (identifier_length) : low > high > very_high
        if metric == "identifier_length":
            if not (levels["low"] > levels["high"] > levels["very_high"]):
                raise ConfigError(
                    f"thresholds.identifier_length : ordre attendu "
                    f"low > high > very_high (inversé), obtenu "
                    f"low={levels['low']}, high={levels['high']}, "
                    f"very_high={levels['very_high']}"
                )
        else:
            if not (levels["low"] < levels["high"] < levels["very_high"]):
                raise ConfigError(
                    f"thresholds.{metric} : ordre attendu "
                    f"low < high < very_high, obtenu "
                    f"low={levels['low']}, high={levels['high']}, "
                    f"very_high={levels['very_high']}"
                )


def _validate_config(cfg: KodoNekoConfig) -> None:
    """Valide une configuration complète."""
    _validate_weights(
        cfg.primary_weights,
        set(DEFAULT_PRIMARY_WEIGHTS.keys()),
        "primary_score.weights",
    )
    _validate_weights(
        cfg.understandability_weights,
        set(DEFAULT_UNDERSTANDABILITY_WEIGHTS.keys()),
        "understandability.weights",
    )
    _validate_thresholds(cfg.understandability_thresholds)


# ---------------------------------------------------------------------------
# Chargement TOML
# ---------------------------------------------------------------------------

def _candidate_paths() -> list[Path]:
    """Liste ordonnée des chemins candidats pour kodoneko.toml.

    Ordre :
    1. Variable d'env KODONEKO_CONFIG
    2. ./kodoneko.toml (répertoire courant)
    3. ~/.config/kodoneko/kodoneko.toml
    """
    paths: list[Path] = []
    env = os.environ.get("KODONEKO_CONFIG")
    if env:
        paths.append(Path(env).expanduser())
    paths.append(Path.cwd() / "kodoneko.toml")
    paths.append(Path.home() / ".config" / "kodoneko" / "kodoneko.toml")
    return paths


def _parse_toml(path: Path) -> dict:
    """Lit et parse un fichier TOML, en levant une ConfigError parlante
    si tomllib n'est pas disponible ou si le fichier est mal formé."""
    if tomllib is None:
        raise ConfigError(
            "Pas de support TOML : Python 3.11+ requis (ou installer 'tomli' "
            "sur Python 3.10)."
        )
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, IOError) as e:
        raise ConfigError(f"Impossible de lire {path} : {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML invalide dans {path} : {e}") from e


def _from_toml_dict(data: dict, source: str) -> KodoNekoConfig:
    """Construit un KodoNekoConfig à partir d'un dict TOML déjà parsé.

    Le TOML peut être partiel : toute section absente reprend les
    valeurs par défaut. Cela permet à l'utilisateur de surcharger
    uniquement ce qu'il veut changer.
    """
    # Section [primary_score.weights]
    primary = dict(DEFAULT_PRIMARY_WEIGHTS)
    if "primary_score" in data and "weights" in data["primary_score"]:
        primary.update(data["primary_score"]["weights"])

    # Section [understandability.weights]
    u_weights = dict(DEFAULT_UNDERSTANDABILITY_WEIGHTS)
    if "understandability" in data and "weights" in data["understandability"]:
        u_weights.update(data["understandability"]["weights"])

    # Section [understandability.thresholds.<metric>]
    u_thresholds = {k: dict(v) for k, v in DEFAULT_UNDERSTANDABILITY_THRESHOLDS.items()}
    if "understandability" in data and "thresholds" in data["understandability"]:
        for metric, levels in data["understandability"]["thresholds"].items():
            if metric in u_thresholds:
                u_thresholds[metric].update(levels)
            else:
                u_thresholds[metric] = dict(levels)

    cfg = KodoNekoConfig(
        primary_weights=primary,
        understandability_weights=u_weights,
        understandability_thresholds=u_thresholds,
        source=source,
    )
    _validate_config(cfg)
    return cfg


def load_config(path: Optional[str] = None) -> KodoNekoConfig:
    """Charge la configuration KodoNeko.

    Paramètres
    ----------
    path : str, optional
        Chemin explicite vers un fichier TOML. Si fourni, c'est ce
        fichier qui est lu (ou erreur s'il n'existe pas). Si None,
        recherche dans la liste de candidats standard.

    Retourne
    --------
    KodoNekoConfig
        Configuration validée. Si aucun fichier n'est trouvé, retourne
        la configuration par défaut avec ``source="defaults"``.

    Lève
    ----
    ConfigError
        Si un fichier explicite n'existe pas, est mal formé, ou si la
        configuration ne respecte pas les contraintes (poids ne
        sommant pas à 1, seuils non monotones, clés inconnues, etc.).
    """
    if path is not None:
        p = Path(path).expanduser()
        if not p.is_file():
            raise ConfigError(f"Fichier de configuration introuvable : {p}")
        data = _parse_toml(p)
        return _from_toml_dict(data, source=str(p))

    # Recherche dans les candidats standard
    for candidate in _candidate_paths():
        if candidate.is_file():
            data = _parse_toml(candidate)
            return _from_toml_dict(data, source=str(candidate))

    # Aucun fichier trouvé : retour aux défauts
    return KodoNekoConfig()


# ---------------------------------------------------------------------------
# Génération d'un fichier de référence
# ---------------------------------------------------------------------------

def example_config_toml() -> str:
    """Retourne un fichier TOML de référence, avec commentaires explicatifs.

    Utile pour générer un ``kodoneko.toml`` initial via la CLI :
    ``python -m kodoneko_scanner --init-config > kodoneko.toml``
    """
    return '''\
# kodoneko.toml — Configuration de KodoNeko
#
# Place ce fichier soit :
#   - à la racine du dépôt analysé (./kodoneko.toml)
#   - dans ~/.config/kodoneko/kodoneko.toml (config utilisateur)
#   - n'importe où, en pointant via la variable KODONEKO_CONFIG ou
#     l'option CLI --config.
#
# Toute section absente reprend les valeurs par défaut : tu peux ne
# surcharger que ce qui t'intéresse.


# ---------------------------------------------------------------------------
# Pondérations des 4 métriques dans le PrimaryQualityScore (somme = 1.0)
# ---------------------------------------------------------------------------
[primary_score.weights]
ncloc             = 0.10   # taille brute
halstead          = 0.05   # densité d'information (indirect, secondaire)
mccabe            = 0.15   # complexité cyclomatique (chemins d'exécution)
understandability = 0.70   # composite ISO/IEC 25010 (rôle principal)


# ---------------------------------------------------------------------------
# Pondérations internes du score Understandability (somme = 1.0)
# Six sous-métriques agrégées en un score composite 0-100.
# ---------------------------------------------------------------------------
[understandability.weights]
cognitive         = 0.30   # complexité cognitive de Campbell
function_length   = 0.20   # longueur maximale des fonctions
nesting_depth     = 0.15   # profondeur d'imbrication
parameter_count   = 0.15   # nombre de paramètres
line_density      = 0.10   # caractères non-blancs / ligne
identifier_length = 0.10   # longueur moyenne des identifiants (inversé)


# ---------------------------------------------------------------------------
# Seuils des sous-métriques (utilisés pour la normalisation 0-100).
# Pour chaque sous-métrique : trois paliers.
#   - en-dessous de "low" : aucune pénalité (contribution = 0)
#   - entre "low" et "high" : pénalité linéaire 0 → 33
#   - entre "high" et "very_high" : pénalité linéaire 33 → 66
#   - au-delà de "very_high" : pénalité 66 → 100 (saturée)
# Pour identifier_length, l'ordre est INVERSÉ (plus c'est court, pire).
#
# Valeurs ci-dessous : seuils révisés v0.7 issus du run de calibration
# pilote (n=30, Python/TypeScript/Java). Cf. calibration/README.md.
# ---------------------------------------------------------------------------
[understandability.thresholds.cognitive]
low       = 3
high      = 10
very_high = 20

[understandability.thresholds.function_length]
low       = 8
high      = 25
very_high = 50

[understandability.thresholds.nesting_depth]
low       = 1
high      = 3
very_high = 5

[understandability.thresholds.parameter_count]
low       = 3
high      = 5
very_high = 8

[understandability.thresholds.line_density]
low       = 25
high      = 50
very_high = 80

# Inversé : seuils décroissants
[understandability.thresholds.identifier_length]
low       = 8   # au-dessus : aucune pénalité
high      = 5   # en-dessous : pénalité modérée
very_high = 3   # en-dessous : pénalité forte
'''
