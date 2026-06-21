"""
CLI du scanner.

Usage :
    python -m kodoneko_scanner /path/to/repo
    python -m kodoneko_scanner /path/to/repo --languages python typescript
    python -m kodoneko_scanner /path/to/repo --json > report.json
    python -m kodoneko_scanner /path/to/repo --hotspots 20
    python -m kodoneko_scanner /path/to/repo --config ./kodoneko.toml
    python -m kodoneko_scanner --init-config > kodoneko.toml

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, example_config_toml, load_config
from .scanner import scan_repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kodoneko-scanner",
        description="Scanne un dépôt et affiche les métriques agrégées.",
    )
    parser.add_argument(
        "path", nargs="?",
        help="Chemin du dépôt à analyser (optionnel si --init-config)",
    )
    parser.add_argument(
        "--languages", "-l", nargs="+", default=None,
        help="Limiter aux langages indiqués (ex: python typescript)",
    )
    parser.add_argument(
        "--max-size", type=int, default=1_000_000,
        help="Taille max par fichier en octets (défaut 1Mo)",
    )
    parser.add_argument(
        "--no-git", action="store_true",
        help="Ne pas utiliser git ls-files (parcours manuel)",
    )
    parser.add_argument(
        "--include-docstrings", action="store_true",
        help="Compter les docstrings comme code (convention cloc)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON (sinon : résumé texte lisible)",
    )
    parser.add_argument(
        "--hotspots", type=int, default=10,
        help="Nombre de fichiers les plus complexes à afficher (défaut 10)",
    )
    parser.add_argument(
        "--hotspot-by", default="understandability",
        choices=["understandability", "cognitive", "mccabe", "ncloc", "volume", "effort"],
        help="Critère de tri des hotspots (défaut understandability depuis v0.4)",
    )
    parser.add_argument(
        "--config", "-c", default=None,
        help="Chemin explicite vers un fichier kodoneko.toml (sinon : recherche "
             "auto dans ./, $KODONEKO_CONFIG, ~/.config/kodoneko/)",
    )
    parser.add_argument(
        "--init-config", action="store_true",
        help="Imprime un kodoneko.toml de référence sur stdout et quitte.",
    )
    args = parser.parse_args(argv)

    # Mode init-config : on sort tout de suite
    if args.init_config:
        sys.stdout.write(example_config_toml())
        return 0

    if not args.path:
        parser.error("argument 'path' requis (sauf avec --init-config)")

    # Chargement de la configuration (ou défauts)
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Erreur de configuration : {e}", file=sys.stderr)
        return 2

    # Scan
    try:
        report = scan_repo(
            args.path,
            languages=args.languages,
            max_file_size=args.max_size,
            use_git=not args.no_git,
            exclude_docstrings=not args.include_docstrings,
            config=config,
        )
    except ValueError as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1

    if args.json:
        # Enrichir avec primary_score pour les pipelines
        from .interpret import compute_primary_quality_score
        hi = compute_primary_quality_score(report, config=config)
        data = report.to_dict()
        data["primary_score"] = hi.to_dict()
        data["config_source"] = config.source
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _print_text_report(report, hotspots_count=args.hotspots,
                             hotspot_by=args.hotspot_by, config=config)

    return 0


def _print_text_report(report, hotspots_count: int, hotspot_by: str, config=None) -> None:
    """Affiche le rapport sous forme de texte lisible."""
    from .interpret import comment_file, compute_primary_quality_score

    print(f"📊 KodoNeko Scanner — Rapport")
    print(f"{'=' * 60}")
    print(f"Repo       : {report.repo_path}")
    print(f"Fichiers   : {report.files_scanned} analysés, "
          f"{report.files_skipped} sautés")
    if config is not None and config.source != "defaults":
        print(f"Config     : {config.source}")
    if report.errors:
        print(f"Erreurs    : {len(report.errors)}")
    print()

    # Indicateur de santé synthétique
    hi = compute_primary_quality_score(report, config=config)
    print(f"✨ Quality score : {hi.score:.1f}/100 (grade {hi.grade})")
    print(f"   {hi.summary}")
    print(f"   Critiques : {hi.files_critical}  À surveiller : {hi.files_warning}")
    print()

    # Totaux globaux
    t = report.totals
    print("🧮 Totaux globaux")
    print(f"{'-' * 60}")
    print(f"  NCLOC          : {t.ncloc:>10,}")
    print(f"  SLOC           : {t.sloc:>10,}")
    print(f"  Commentaires   : {t.comment:>10,}")
    print(f"  Halstead V     : {t.halstead_volume:>10,.0f}")
    print(f"  Halstead E     : {t.halstead_effort:>10,.0f}")
    print(f"  McCabe (sum)   : {t.mccabe_sum:>10}")
    print(f"  McCabe (avg)   : {t.mccabe_avg:>10.1f}")
    print(f"  McCabe (max)   : {t.mccabe_max:>10}")
    print(f"  Cognitive (sum) : {t.cognitive_sum:>10}")
    print(f"  Cognitive (avg) : {t.cognitive_avg:>10.1f}")
    print(f"  Cognitive (max) : {t.cognitive_max:>10}")
    print(f"  Understandability (avg) : {t.understandability_avg:>6.1f}/100")
    print(f"  Understandability (max) : {t.understandability_max:>6.1f}/100")
    print()

    # Par langage
    if report.by_language:
        print("🌐 Répartition par langage")
        print(f"{'-' * 60}")
        print(f"{'Langage':<14} | {'Fichiers':>8} | {'NCLOC':>8} | "
              f"{'CC max':>6} | {'CCog max':>8}")
        print(f"{'-' * 60}")
        for lang in sorted(report.by_language.keys(),
                            key=lambda l: report.by_language[l].ncloc,
                            reverse=True):
            lt = report.by_language[lang]
            print(f"{lang:<14} | {lt.files_count:>8} | {lt.ncloc:>8,} | "
                  f"{lt.mccabe_max:>6} | {lt.cognitive_max:>8}")
        print()

    # Hotspots avec commentaires humains
    if hotspots_count > 0 and report.by_file:
        hotspots = report.hotspots(top=hotspots_count, by=hotspot_by)
        if hotspots:
            print(f"🔥 Top {len(hotspots)} hotspots (tri : {hotspot_by})")
            print(f"{'-' * 60}")
            for f in hotspots:
                print(f"  • {f.relative_path}")
                print(f"    {comment_file(f)}")


if __name__ == "__main__":
    sys.exit(main())
