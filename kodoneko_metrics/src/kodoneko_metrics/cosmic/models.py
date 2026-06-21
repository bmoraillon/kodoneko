"""
Modèles de données pour la mesure COSMIC (ISO/IEC 19761).

Conventions
-----------
Un **mouvement de données** est une opération unitaire qui déplace un
groupe de données entre :
- le système et un utilisateur fonctionnel (Entry / Exit), ou
- le système et un stockage persistant (Read / Write).

Chaque mouvement vaut 1 CFP (COSMIC Function Point), sans pondération.

Deux modes de comptage sont supportés :
- ``strict`` : comportement aligné avec la spec COSMIC ISO/IEC 19761 ;
  les calls HTTP sortants ne sont pas comptés (l'utilisateur fonctionnel
  du système appelant n'est pas un utilisateur du service appelé).
- ``practical`` (défaut) : compte aussi les calls HTTP sortants comme
  1 Read (réponse) + 1 Write (requête) vers un EIF, pour refléter
  l'effort technique réel d'intégration.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# Types de mouvements selon COSMIC
MovementType = Literal["entry", "exit", "read", "write"]
Confidence = Literal["high", "medium", "low"]
CosmicMode = Literal["strict", "practical"]

# Tous les types acceptés
MOVEMENT_TYPES: tuple[MovementType, ...] = ("entry", "exit", "read", "write")


@dataclass(frozen=True)
class CosmicMovement:
    """Un mouvement de données détecté dans le code.

    Attributs
    ---------
    type : MovementType
        entry / exit / read / write
    file : str
        Chemin du fichier (relatif au repo si possible)
    line : int
        Numéro de ligne (1-indexé) où le mouvement a été détecté
    code_excerpt : str
        Extrait textuel du code détecté (80 char max), pour audit
    detector : str
        Nom du pattern qui a détecté ce mouvement (ex: "django_orm_get")
    confidence : Confidence
        Indicateur de fiabilité de la détection
    framework : str
        Famille technique reconnue (ex: "django", "flask", "spring",
        "sqlalchemy", "stdlib"). Permet d'agréger par framework.
    """
    type: MovementType
    file: str
    line: int
    code_excerpt: str
    detector: str
    confidence: Confidence = "high"
    framework: str = ""
    # Champs sémantiques inférés (COSMIC mapping phase). Optionnels car
    # l'analyse statique ne peut PAS toujours les déterminer de façon fiable :
    # ils sont estimés par heuristique et marqués comme tels.
    functional_process: str = ""   # nom du FP auquel ce mouvement est rattaché
    object_of_interest: str = ""   # objet d'intérêt estimé (ex: "Owner")
    data_group: str = ""           # data group estimé (ex: "Owner details")
    inferred: bool = False         # True si OOI/data_group sont des estimations

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "file": self.file,
            "line": self.line,
            "code_excerpt": self.code_excerpt,
            "detector": self.detector,
            "confidence": self.confidence,
            "framework": self.framework,
            "functional_process": self.functional_process,
            "object_of_interest": self.object_of_interest,
            "data_group": self.data_group,
            "inferred": self.inferred,
        }


@dataclass
class CosmicFileReport:
    """Rapport COSMIC pour un fichier unique."""
    path: str
    language: str
    movements: list[CosmicMovement] = field(default_factory=list)

    @property
    def total_cfp(self) -> int:
        return len(self.movements)

    @property
    def by_type(self) -> dict[MovementType, int]:
        result: dict[MovementType, int] = {t: 0 for t in MOVEMENT_TYPES}
        for m in self.movements:
            result[m.type] += 1
        return result

    @property
    def by_framework(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for m in self.movements:
            key = m.framework or "unknown"
            result[key] = result.get(key, 0) + 1
        return result

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "total_cfp": self.total_cfp,
            "by_type": dict(self.by_type),
            "by_framework": dict(self.by_framework),
            "movements": [m.to_dict() for m in self.movements],
        }


@dataclass
class CosmicScanReport:
    """Rapport COSMIC agrégé sur un repo entier ou un sous-ensemble.

    Notes
    -----
    Utilisé par :code:`kodoneko_scanner.scan_repo_cosmic()` pour un scan
    de repo, ou par :code:`kodoneko_temporal.cosmic_delta` pour une
    photographie d'un état git donné (commit, tag, date).
    """
    scope: str  # ex: "repo:/path", "commit:abc123", "tag:v1.2.0"
    mode: CosmicMode
    files: list[CosmicFileReport] = field(default_factory=list)
    skipped_files: list[tuple[str, str]] = field(default_factory=list)
    # (path, raison) : fichiers non analysés (langage non supporté, erreur de parsing, etc.)
    duration_seconds: float = 0.0

    @property
    def total_cfp(self) -> int:
        return sum(f.total_cfp for f in self.files)

    @property
    def by_type(self) -> dict[MovementType, int]:
        result: dict[MovementType, int] = {t: 0 for t in MOVEMENT_TYPES}
        for f in self.files:
            for t, n in f.by_type.items():
                result[t] += n
        return result

    @property
    def by_language(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for f in self.files:
            result[f.language] = result.get(f.language, 0) + f.total_cfp
        return result

    @property
    def by_framework(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for f in self.files:
            for fw, n in f.by_framework.items():
                result[fw] = result.get(fw, 0) + n
        return result

    def top_files(self, n: int = 10) -> list[CosmicFileReport]:
        return sorted(self.files, key=lambda f: f.total_cfp, reverse=True)[:n]

    @property
    def analyzed_files(self) -> list[str]:
        """Chemins des fichiers réellement analysés (comptés).

        Traçabilité : permet de justifier un comptage COSMIC en listant
        exactement ce qui a été inclus. Essentiel pour un audit formel.
        """
        return [f.path for f in self.files]

    @property
    def excluded_files(self) -> list[tuple[str, str]]:
        """Liste (chemin, motif) des fichiers/répertoires exclus.

        Motifs : 'excluded:dir', 'excluded:file_glob', 'language:<lang>',
        ou un message d'erreur de parsing.
        """
        return list(self.skipped_files)

    def exclusion_summary(self) -> dict[str, int]:
        """Compte des exclusions par motif. Vue d'audit synthétique."""
        summary: dict[str, int] = {}
        for _path, reason in self.skipped_files:
            if reason.startswith("excluded:"):
                key = reason
            elif reason.startswith("language:"):
                key = "language_unsupported"
            else:
                key = "error"
            summary[key] = summary.get(key, 0) + 1
        return summary

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "mode": self.mode,
            "total_cfp": self.total_cfp,
            "by_type": dict(self.by_type),
            "by_language": dict(self.by_language),
            "by_framework": dict(self.by_framework),
            "file_count": len(self.files),
            "skipped_count": len(self.skipped_files),
            "exclusion_summary": self.exclusion_summary(),
            "duration_seconds": self.duration_seconds,
            "analyzed_files": self.analyzed_files,
            "excluded_files": [
                {"path": p, "reason": r} for p, r in self.skipped_files
            ],
            "files": [f.to_dict() for f in self.files],
        }


@dataclass
class CosmicDelta:
    """Différence COSMIC entre deux états du code (avant/après).

    Utilisée pour mesurer l'apport CFP d'un commit ou d'une période
    de développement.
    """
    scope: str  # ex: "commit:abc123", "range:v1.0..v1.1"
    mode: CosmicMode
    before: CosmicScanReport
    after: CosmicScanReport

    @property
    def cfp_added(self) -> int:
        """CFP nets ajoutés (peut être négatif si suppression nette)."""
        return self.after.total_cfp - self.before.total_cfp

    @property
    def by_type_delta(self) -> dict[MovementType, int]:
        before = self.before.by_type
        after = self.after.by_type
        return {t: after[t] - before[t] for t in MOVEMENT_TYPES}

    @property
    def by_language_delta(self) -> dict[str, int]:
        before = self.before.by_language
        after = self.after.by_language
        languages = set(before) | set(after)
        return {lang: after.get(lang, 0) - before.get(lang, 0) for lang in languages}

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "mode": self.mode,
            "cfp_before": self.before.total_cfp,
            "cfp_after": self.after.total_cfp,
            "cfp_added": self.cfp_added,
            "by_type_delta": dict(self.by_type_delta),
            "by_language_delta": dict(self.by_language_delta),
        }
