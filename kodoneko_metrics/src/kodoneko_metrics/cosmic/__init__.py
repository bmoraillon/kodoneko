"""
kodoneko_metrics.cosmic — Mesure COSMIC (ISO/IEC 19761).

Compte les **mouvements de données** (CFP, COSMIC Function Points) dans
le code source. Un CFP = 1 mouvement entry/exit/read/write, sans
pondération de complexité.

Modes
-----
- ``strict`` : aligné avec la spec ISO/IEC 19761
- ``practical`` (défaut) : compte aussi les calls HTTP sortants comme
  1 Write + 1 Read (intégration externe)

Usage
-----
>>> from kodoneko_metrics.cosmic import CosmicAnalyzer
>>> analyzer = CosmicAnalyzer(mode="practical")
>>> report = analyzer.analyze_file("src/views.py")
>>> print(f"{report.total_cfp} CFP")
>>> print(report.by_type)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from .analyzer import CosmicAnalyzer
from .models import (
    MOVEMENT_TYPES,
    CosmicDelta,
    CosmicFileReport,
    CosmicMode,
    CosmicMovement,
    CosmicScanReport,
    MovementType,
)
from .analysis_report import (
    ConfidenceInterval,
    EnrichedFileAnalysis,
    EnrichedRepoAnalysis,
    FunctionalProcessView,
    analyze_enriched,
    analyze_repo_enriched,
)
from .table_formatter import (
    render_markdown,
    render_repo_markdown,
    render_text,
)
from .html_formatter import (
    render_html,
    render_repo_html,
)

__all__ = [
    "CosmicAnalyzer",
    "CosmicDelta",
    "CosmicFileReport",
    "CosmicMode",
    "CosmicMovement",
    "CosmicScanReport",
    "MOVEMENT_TYPES",
    "MovementType",
    # Analyse enrichie (intervalle de confiance + tableau façon manuel)
    "ConfidenceInterval",
    "EnrichedFileAnalysis",
    "EnrichedRepoAnalysis",
    "FunctionalProcessView",
    "analyze_enriched",
    "analyze_repo_enriched",
    "render_markdown",
    "render_repo_markdown",
    "render_text",
    "render_html",
    "render_repo_html",
]
