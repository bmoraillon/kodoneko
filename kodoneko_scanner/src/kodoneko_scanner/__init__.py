"""
kodoneko-scanner — Scanner de dépôt pour métriques code.

Parcourt un répertoire et applique kodoneko-metrics sur chaque fichier
source, puis agrège les résultats (totaux globaux, par langage, et
hotspots).

API publique :

>>> from kodoneko_scanner import scan_repo
>>> r = scan_repo("/path/to/myproject")
>>> r.files_scanned
123
>>> r.totals.ncloc
4567
>>> hotspots = r.hotspots(top=10, by="understandability")

Pour le scan COSMIC (mouvements de données) :

>>> from kodoneko_scanner import scan_repo_cosmic
>>> r = scan_repo_cosmic("/path/to/myproject", mode="practical")
>>> r.total_cfp
1234

Voir la documentation README.md et les notebooks 05/07 pour plus de
détails.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from .config import (
    ConfigError,
    KodoNekoConfig,
    example_config_toml,
    load_config,
)
from .interpret import (
    PrimaryQualityScore,
    LEVEL_INTERPRETATIONS,
    comment_file,
    compute_primary_quality_score,
    format_primary_report,
)
from .models import FileReport, RepoMetrics, Totals
from .scanner import (
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_MAX_FILE_SIZE,
    scan_repo,
    scan_repo_cosmic,
)

__version__ = "0.11.0"

__all__ = [
    # Scan
    "scan_repo",
    "scan_repo_cosmic",
    "DEFAULT_EXCLUDED_DIRS",
    "DEFAULT_MAX_FILE_SIZE",
    # Modèles
    "FileReport",
    "RepoMetrics",
    "Totals",
    # Interprétation et PrimaryQualityScore
    "PrimaryQualityScore",
    "compute_primary_quality_score",
    "comment_file",
    "format_primary_report",
    "LEVEL_INTERPRETATIONS",
    # Configuration
    "KodoNekoConfig",
    "ConfigError",
    "load_config",
    "example_config_toml",
    # Version
    "__version__",
]
