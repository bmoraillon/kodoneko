"""
Scanner de dépôt : parcourt un répertoire et applique kodoneko-metrics
sur chaque fichier source.

Fonctionnement
==============

1. Énumération des fichiers via :
   - `git ls-files` si on est dans un dépôt Git (respecte .gitignore)
   - parcours récursif du répertoire sinon

2. Filtres :
   - Langages explicitement demandés (ex : ["python", "typescript"])
   - Taille max (ignore les gros fichiers générés)
   - Dossiers à exclure (node_modules, dist, build, __pycache__...)

3. Analyse :
   - Détection auto du langage par extension (`detect_language`)
   - Si supporté par tree-sitter : `CodeAnalyzer.analyze()`
   - Sinon : fichier sauté

4. Agrégation :
   - Totaux globaux + par langage
   - Liste détaillée par fichier (pour drill-down et hotspots)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, Optional

from kodoneko_metrics import CodeAnalyzer, detect_language

from .models import FileReport, RepoMetrics, Totals


# Dossiers à exclure par défaut — communs aux écosystèmes Python, JS, Rust, etc.
DEFAULT_EXCLUDED_DIRS = frozenset({
    # Python
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".eggs", "*.egg-info", "build", "dist",
    "site-packages",
    # JavaScript / TypeScript
    "node_modules", ".next", ".nuxt", ".svelte-kit", ".angular",
    "coverage", ".turbo", "bower_components", ".yarn",
    # Java / JVM
    "target", "out", ".gradle",
    # Go
    "vendor",
    # Outils / VCS
    ".git", ".hg", ".svn", ".idea", ".vscode", ".DS_Store",
    # Cache divers
    ".cache", ".parcel-cache",
})


# Répertoires de tests, exclus par défaut pour le comptage COSMIC.
# Séparés de DEFAULT_EXCLUDED_DIRS car certains usages veulent les inclure
# (ex : mesurer l'effort de test). Désactivables via include_tests=True.
DEFAULT_TEST_DIRS = frozenset({
    "test", "tests", "__tests__", "spec", "specs", "e2e",
    "testing", "fixtures", "__mocks__", "__fixtures__",
})


# Patterns glob de FICHIERS exclus par défaut : générés, minifiés, tests.
# Filtrage par nom de fichier (pas répertoire) car ces fichiers vivent
# souvent au milieu du code applicatif.
# Déterministe et documenté : l'utilisateur peut inspecter/surcharger.
DEFAULT_EXCLUDED_FILE_GLOBS = frozenset({
    # Fichiers générés
    "*.gen.ts", "*.gen.js", "*.gen.tsx", "*.gen.jsx",
    "*.generated.*", "*_pb2.py", "*_pb2_grpc.py",
    "routeTree.gen.ts",
    # Minifiés / bundles
    "*.min.js", "*.min.css", "*.bundle.js",
    # Tests (par convention de nom)
    "*.test.ts", "*.test.js", "*.test.tsx", "*.test.jsx",
    "*.spec.ts", "*.spec.js", "*.spec.tsx", "*.spec.jsx",
    "test_*.py", "*_test.py", "conftest.py",
    "*Test.java", "*Tests.java", "*IT.java",
})


# Taille max par défaut : 1 Mo. Au-delà, c'est probablement un fichier
# généré ou minifié, sans valeur pour l'analyse.
DEFAULT_MAX_FILE_SIZE = 1_000_000


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def scan_repo(
    path: str,
    *,
    languages: Optional[list[str]] = None,
    max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    excluded_dirs: Optional[Iterable[str]] = None,
    use_git: bool = True,
    exclude_docstrings: bool = True,
    config=None,
) -> RepoMetrics:
    """Scanne un dépôt et retourne un rapport agrégé.

    Paramètres
    ----------
    path : str
        Chemin du répertoire racine à analyser.
    languages : list[str] | None
        Si fourni, n'analyse que les fichiers de ces langages canoniques
        (ex : ["python", "typescript"]). Par défaut, tous les langages
        supportés par CodeAnalyzer.
    max_file_size : int
        Taille max en octets. Les fichiers plus gros sont sautés.
    excluded_dirs : Iterable[str] | None
        Dossiers à ne pas explorer. Si None, utilise DEFAULT_EXCLUDED_DIRS.
    use_git : bool
        Si True (défaut) et qu'on est dans un repo Git, utilise
        `git ls-files` pour respecter le .gitignore. Sinon parcours
        manuel du répertoire.
    exclude_docstrings : bool
        Passé tel quel à `CodeAnalyzer.analyze()`. Par défaut True
        (convention KodoNeko : docstrings = commentaires).
    config : KodoNekoConfig, optional
        Configuration personnalisée (poids et seuils Understandability).
        Si None, utilise les défauts intégrés.

    Retourne
    --------
    RepoMetrics : rapport complet, sérialisable JSON via `.to_dict()`.

    Exemples
    --------
    >>> r = scan_repo("/path/to/excalidraw", languages=["typescript", "tsx"])
    >>> r.files_scanned
    487
    >>> r.totals.ncloc
    23456
    >>> hotspots = r.hotspots(top=10, by="understandability")
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise ValueError(f"Le chemin {path!r} n'est pas un répertoire.")

    excluded = frozenset(excluded_dirs) if excluded_dirs else DEFAULT_EXCLUDED_DIRS

    # 1. Énumération des fichiers
    files = list(_iter_source_files(
        root, use_git=use_git, excluded_dirs=excluded,
    ))

    # 2. Initialisation
    report = RepoMetrics(repo_path=str(root))
    # Construction de l'analyzer avec les overrides de config si fournis
    if config is not None:
        analyzer = CodeAnalyzer(
            understandability_weights=config.understandability_weights,
            understandability_thresholds=config.understandability_thresholds,
        )
    else:
        analyzer = CodeAnalyzer()  # défauts intégrés

    # 3. Analyse fichier par fichier
    for file_path in files:
        rel = file_path.relative_to(root)
        rel_posix = rel.as_posix()

        # Filtre taille
        try:
            size = file_path.stat().st_size
        except OSError as e:
            report.errors.append({"path": rel_posix, "reason": f"stat failed: {e}"})
            report.files_skipped += 1
            continue

        if size > max_file_size:
            report.files_skipped += 1
            continue

        # Détection langage
        lang = detect_language(str(file_path))
        if lang is None:
            report.files_skipped += 1
            continue

        if languages is not None and lang not in languages:
            report.files_skipped += 1
            continue

        # Analyse
        try:
            metrics = analyzer.analyze(
                file_path, language=lang,
                exclude_docstrings=exclude_docstrings,
            )
        except Exception as e:
            report.errors.append({
                "path": rel_posix, "reason": f"{type(e).__name__}: {e}",
            })
            report.files_skipped += 1
            # On garde un FileReport vide pour traçabilité
            report.by_file.append(FileReport(
                path=str(file_path),
                relative_path=rel_posix,
                language=lang,
                size_bytes=size,
                metrics=None,
                error=f"{type(e).__name__}: {e}",
            ))
            continue

        # Succès : on ajoute au rapport
        fr = FileReport(
            path=str(file_path),
            relative_path=rel_posix,
            language=lang,
            size_bytes=size,
            metrics=metrics,
        )
        report.by_file.append(fr)
        report.files_scanned += 1

        # Agrégation globale
        _add_to_totals(report.totals, metrics)
        # Agrégation par langage
        if lang not in report.by_language:
            report.by_language[lang] = Totals()
        _add_to_totals(report.by_language[lang], metrics)

    # 4. Calcul des moyennes finales
    _finalize_averages(report.totals)
    for lang_totals in report.by_language.values():
        _finalize_averages(lang_totals)

    return report


# ---------------------------------------------------------------------------
# Énumération des fichiers
# ---------------------------------------------------------------------------

def _iter_source_files(
    root: Path,
    *,
    use_git: bool,
    excluded_dirs: frozenset,
    excluded_sink: list | None = None,
) -> Iterable[Path]:
    """Énumère les fichiers candidats à l'analyse.

    Stratégie :
    - Si `use_git=True` et qu'on est dans un repo Git : `git ls-files`.
    - Sinon : os.walk filtré.

    Si `excluded_sink` est fourni, les éléments écartés au niveau répertoire
    y sont ajoutés sous forme (chemin, 'excluded:dir') pour la traçabilité.
    """
    if use_git and _is_git_repo(root):
        yield from _git_ls_files(root, excluded_dirs, excluded_sink)
    else:
        yield from _walk_dir(root, excluded_dirs, excluded_sink)


def _is_git_repo(root: Path) -> bool:
    """Vrai si root contient un .git ou est dans un repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root, capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _git_ls_files(root: Path, excluded_dirs: frozenset,
                  excluded_sink: list | None = None) -> Iterable[Path]:
    """Liste les fichiers via `git ls-files` (respecte .gitignore)."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],  # -z pour séparation par \0 (sûr)
            cwd=root, capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return

    if result.returncode != 0:
        return

    output = result.stdout.decode("utf-8", errors="replace")
    for rel_str in output.split("\0"):
        if not rel_str:
            continue
        # Filtre dossiers exclus (même si git ne devrait pas les remonter,
        # par sécurité)
        parts = rel_str.split("/")
        if any(p in excluded_dirs for p in parts):
            if excluded_sink is not None:
                excluded_sink.append((str(root / rel_str), "excluded:dir"))
            continue
        path = root / rel_str
        if path.is_file():
            yield path


def _walk_dir(root: Path, excluded_dirs: frozenset,
              excluded_sink: list | None = None) -> Iterable[Path]:
    """Parcours manuel du répertoire (sans Git)."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Tracer les répertoires exclus avant de les retirer
        if excluded_sink is not None:
            for d in dirnames:
                if d in excluded_dirs:
                    excluded_sink.append(
                        (str(Path(dirpath) / d), "excluded:dir"))
        # Filtrer in-place pour ne pas descendre dans les dossiers exclus
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        for filename in filenames:
            yield Path(dirpath) / filename


# ---------------------------------------------------------------------------
# Agrégations
# ---------------------------------------------------------------------------

def _add_to_totals(totals: Totals, metrics) -> None:
    """Accumule les métriques d'un fichier dans un objet Totals."""
    # Lignes
    totals.total += metrics.lines.total
    totals.blank += metrics.lines.blank
    totals.comment += metrics.lines.comment
    totals.sloc += metrics.lines.sloc
    totals.ncloc += metrics.lines.ncloc
    # Halstead
    totals.halstead_n1 += metrics.halstead.n1
    totals.halstead_n2 += metrics.halstead.n2
    totals.halstead_N1 += metrics.halstead.N1
    totals.halstead_N2 += metrics.halstead.N2
    totals.halstead_volume += metrics.halstead.volume
    totals.halstead_effort += metrics.halstead.effort
    # McCabe
    totals.mccabe_sum += metrics.mccabe.value
    totals.mccabe_max = max(totals.mccabe_max, metrics.mccabe.value)
    # Cognitive (alimenté via m.understandability.cognitive depuis v0.4)
    totals.cognitive_sum += metrics.understandability.cognitive
    totals.cognitive_max = max(totals.cognitive_max, metrics.understandability.cognitive)
    # Understandability (score composite)
    totals.understandability_max = max(
        totals.understandability_max, metrics.understandability.risk,
    )
    # Pour la moyenne, on accumule dans understandability_avg (utilisé comme
    # somme temporaire, finalisé dans _finalize_averages)
    totals.understandability_avg += metrics.understandability.risk
    # Compteur
    totals.files_count += 1


def _finalize_averages(totals: Totals) -> None:
    """Calcule les moyennes après agrégation."""
    if totals.files_count > 0:
        totals.mccabe_avg = totals.mccabe_sum / totals.files_count
        totals.cognitive_avg = totals.cognitive_sum / totals.files_count
        # understandability_avg contient la somme temporaire ; on divise
        totals.understandability_avg = totals.understandability_avg / totals.files_count


# ---------------------------------------------------------------------------
# Scan COSMIC d'un repo
# ---------------------------------------------------------------------------

def scan_repo_cosmic(
    root: str | Path,
    *,
    mode: str = "practical",
    use_git: bool = True,
    excluded_dirs: frozenset = None,
    excluded_file_globs: frozenset = None,
    include_tests: bool = False,
    scope_label: str = None,
):
    """Scan COSMIC complet d'un repo.

    Itère sur les fichiers source (via git ls-files si possible, sinon
    walk) et délègue l'analyse de chaque fichier au CosmicAnalyzer.
    Agrège les résultats en un CosmicScanReport.

    Paramètres
    ----------
    root : str | Path
        Racine du repo à scanner.
    mode : "strict" | "practical"
        Mode de comptage COSMIC. Voir kodoneko_metrics.cosmic.
    use_git : bool
        Si True et root est un repo git, utilise git ls-files (rapide).
    excluded_dirs : frozenset | None
        Répertoires à exclure. Si None, utilise DEFAULT_EXCLUDED_DIRS
        (+ DEFAULT_TEST_DIRS si include_tests est False). Pour SURCHARGER
        complètement le défaut, passer un frozenset explicite.
    excluded_file_globs : frozenset | None
        Patterns glob de fichiers à exclure (générés, minifiés, tests par
        convention de nom). Si None, utilise DEFAULT_EXCLUDED_FILE_GLOBS.
        Passer frozenset() pour ne rien exclure au niveau fichier.
    include_tests : bool
        Si True, inclut les répertoires et fichiers de test dans le comptage
        (utile pour mesurer l'effort de test). Par défaut False : les tests
        sont exclus, car le comptage COSMIC mesure la fonctionnalité livrée.
    scope_label : str
        Étiquette pour le rapport (ex: "repo:/path", "commit:abc123").

    Returns
    -------
    CosmicScanReport

    Notes
    -----
    Toutes les exclusions sont DÉTERMINISTES et inspectables : les constantes
    DEFAULT_EXCLUDED_DIRS, DEFAULT_TEST_DIRS et DEFAULT_EXCLUDED_FILE_GLOBS
    sont publiques. Le rapport liste les fichiers réellement analysés, ce qui
    permet un audit complet (essentiel pour un usage COSMIC formel).
    """
    import time
    import fnmatch
    from kodoneko_metrics.cosmic import CosmicAnalyzer, CosmicScanReport

    root = Path(root).resolve()

    # Construction des exclusions (source unique de vérité)
    if excluded_dirs is None:
        excluded_dirs = DEFAULT_EXCLUDED_DIRS
        if not include_tests:
            excluded_dirs = excluded_dirs | DEFAULT_TEST_DIRS

    if excluded_file_globs is None:
        if include_tests:
            # Garder les globs de fichiers générés/minifiés, retirer ceux de test
            excluded_file_globs = frozenset(
                g for g in DEFAULT_EXCLUDED_FILE_GLOBS
                if not any(t in g.lower() for t in ("test", "spec", "conftest"))
            )
        else:
            excluded_file_globs = DEFAULT_EXCLUDED_FILE_GLOBS

    if scope_label is None:
        scope_label = f"repo:{root}"

    analyzer = CosmicAnalyzer(mode=mode)
    supported = set(analyzer.supported_languages())

    # Extensions à analyser (uniquement les langages supportés par COSMIC)
    SOURCE_EXTENSIONS = {
        ".py",                           # Python
        ".js", ".jsx", ".mjs", ".cjs",   # JavaScript
        ".ts", ".tsx",                   # TypeScript
        ".java",                         # Java
    }

    report = CosmicScanReport(scope=scope_label, mode=mode)

    t0 = time.perf_counter()
    for file_path in _iter_source_files(root, use_git=use_git,
                                        excluded_dirs=excluded_dirs,
                                        excluded_sink=report.skipped_files):
        # Filtrage par extension (gain de temps)
        if Path(file_path).suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        # Filtrage par glob de fichier (générés, minifiés, tests par nom)
        fname = Path(file_path).name
        if any(fnmatch.fnmatch(fname, g) for g in excluded_file_globs):
            report.skipped_files.append((str(file_path), "excluded:file_glob"))
            continue
        try:
            file_report = analyzer.analyze_file(file_path)
        except Exception as e:
            report.skipped_files.append((str(file_path), f"{type(e).__name__}: {e}"))
            continue

        if file_report.language in supported:
            try:
                rel = str(Path(file_path).relative_to(root))
                file_report.path = rel
            except ValueError:
                pass
            report.files.append(file_report)
        else:
            report.skipped_files.append((str(file_path), f"language:{file_report.language}"))

    report.duration_seconds = time.perf_counter() - t0
    return report
