"""
Évaluation empirique de KodoNeko sur le dataset de calibration.

Applique KodoNeko sur chaque cas annoté du dataset, compare aux
attentes humaines, calcule des métriques d'accord (catégoriel, RMSE,
Spearman) et produit un rapport markdown détaillé.

Usage :
    python calibration/evaluate.py
    python calibration/evaluate.py --config my-config.toml
    python calibration/evaluate.py --language python
    python calibration/evaluate.py --output calibration/results/run_001.md

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap des chemins (le projet est sans installation pip)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "kodoneko_metrics" / "src"))
sys.path.insert(0, str(ROOT / "kodoneko_scanner" / "src"))


# ---------------------------------------------------------------------------
# Chargement du dataset
# ---------------------------------------------------------------------------

DATASET_DIR = Path(__file__).parent / "dataset"

DATASET_FILES = {
    "python":     DATASET_DIR / "python_cases.jsonl",
    "typescript": DATASET_DIR / "typescript_cases.jsonl",
    "java":       DATASET_DIR / "java_cases.jsonl",
}


def load_dataset(language: str | None = None) -> list[dict]:
    """Charge tous les cas (ou ceux d'un langage donné)."""
    cases = []
    files = (
        {language: DATASET_FILES[language]} if language
        else DATASET_FILES
    )
    for lang, path in files.items():
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
    return cases


# ---------------------------------------------------------------------------
# Évaluation
# ---------------------------------------------------------------------------

LEVELS = ["low", "moderate", "high", "very_high"]
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}


def evaluate_case(case: dict, config=None) -> dict:
    """Applique KodoNeko sur un cas et retourne les valeurs mesurées."""
    from kodoneko_metrics import CodeAnalyzer

    analyzer = CodeAnalyzer(
        understandability_weights=config.understandability_weights if config else None,
        understandability_thresholds=config.understandability_thresholds if config else None,
    )
    try:
        r = analyzer.count_understandability(
            case["source"], language=case["language"],
        )
        return {
            "id": case["id"],
            "ok": True,
            "kodoneko_risk": r.risk,
            "kodoneko_level": r.level,
            "kodoneko_cognitive": r.cognitive,
            "fn_length_max": r.function_length_max,
            "nesting_depth_max": r.nesting_depth_max,
            "parameter_count_max": r.parameter_count_max,
            "line_density_avg": r.line_density_avg,
            "identifier_length_avg": r.identifier_length_avg,
        }
    except Exception as e:
        return {
            "id": case["id"], "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


def spearman_rank_correlation(x: list[float], y: list[float]) -> float:
    """Corrélation de Spearman manuelle (sans scipy).

    Retourne rho ∈ [-1, 1]. Mesure la préservation de l'ordre.
    """
    if len(x) < 2 or len(x) != len(y):
        return 0.0

    def rank(values):
        # Rangs avec moyenne des positions pour les ex-aequo
        n = len(values)
        sorted_idx = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[sorted_idx[j + 1]] == values[sorted_idx[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = rank(x), rank(y)
    n = len(x)
    d_squared = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1.0 - (6.0 * d_squared) / (n * (n * n - 1))


def compute_metrics(results: list[dict], cases: list[dict]) -> dict:
    """Calcule toutes les métriques d'évaluation à partir des résultats."""
    by_id = {c["id"]: c for c in cases}
    paired = [
        (by_id[r["id"]], r)
        for r in results if r.get("ok")
    ]

    if not paired:
        return {"n": 0, "accuracy": 0.0, "rmse": float("inf"), "spearman": 0.0}

    # Accord catégoriel
    matches = sum(1 for c, r in paired if c["expected_level"] == r["kodoneko_level"])
    accuracy = matches / len(paired)

    # RMSE sur risk
    diffs = [(r["kodoneko_risk"] - c["expected_risk"]) for c, r in paired]
    rmse = (sum(d * d for d in diffs) / len(diffs)) ** 0.5

    # Bias signé (KodoNeko sur ou sous-estime ?)
    bias = sum(diffs) / len(diffs)

    # Spearman
    expected = [c["expected_risk"] for c, _ in paired]
    measured = [r["kodoneko_risk"] for _, r in paired]
    spearman = spearman_rank_correlation(expected, measured)

    # Matrice de confusion 4×4 sur les niveaux
    confusion = {a: {p: 0 for p in LEVELS} for a in LEVELS}
    for c, r in paired:
        confusion[c["expected_level"]][r["kodoneko_level"]] += 1

    # Distance moyenne en rang de niveau (ex : low prédit comme moderate = 1)
    rank_diffs = [
        abs(LEVEL_RANK[c["expected_level"]] - LEVEL_RANK[r["kodoneko_level"]])
        for c, r in paired
    ]
    avg_rank_dist = sum(rank_diffs) / len(rank_diffs)

    return {
        "n": len(paired),
        "accuracy": accuracy,
        "rmse": rmse,
        "bias": bias,
        "spearman": spearman,
        "confusion": confusion,
        "avg_rank_distance": avg_rank_dist,
    }


# ---------------------------------------------------------------------------
# Génération du rapport
# ---------------------------------------------------------------------------

def render_report(
    results: list[dict], cases: list[dict],
    metrics: dict, by_language: dict[str, dict],
    config_source: str,
) -> str:
    """Construit un rapport markdown détaillé."""
    by_id = {c["id"]: c for c in cases}
    paired = [(by_id[r["id"]], r) for r in results if r.get("ok")]

    lines = []
    lines.append(f"# Rapport de calibration KodoNeko")
    lines.append("")
    lines.append(f"**Date :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Configuration :** `{config_source}`")
    lines.append(f"**Dataset :** {len(cases)} cas annotés ({len(paired)} évalués avec succès)")
    lines.append("")

    # --- Résumé global ---
    lines.append("## Résumé global")
    lines.append("")
    lines.append(f"| Métrique | Valeur | Objectif | Statut |")
    lines.append(f"|---|---|---|---|")
    acc = metrics["accuracy"]
    rmse = metrics["rmse"]
    sp = metrics["spearman"]
    bias = metrics.get("bias", 0)
    lines.append(f"| Accord catégoriel (niveau) | {acc:.1%} | ≥ 70 % | {'✓' if acc >= 0.7 else '✗'} |")
    lines.append(f"| RMSE sur risk (0-100) | {rmse:.1f} | ≤ 15 | {'✓' if rmse <= 15 else '✗'} |")
    lines.append(f"| Corrélation Spearman | {sp:.3f} | ≥ 0.80 | {'✓' if sp >= 0.8 else '✗'} |")
    lines.append(f"| Biais signé moyen | {bias:+.1f} | — | {'sur-estime' if bias > 5 else ('sous-estime' if bias < -5 else 'OK')} |")
    lines.append(f"| Distance moyenne en rang | {metrics['avg_rank_distance']:.2f} | ≤ 0.5 | {'✓' if metrics['avg_rank_distance'] <= 0.5 else '✗'} |")
    lines.append("")

    # --- Par langage ---
    lines.append("## Par langage")
    lines.append("")
    lines.append("| Langage | n | Accord | RMSE | Biais | Spearman |")
    lines.append("|---|---|---|---|---|---|")
    for lang, m in by_language.items():
        if m["n"] == 0:
            continue
        lines.append(
            f"| {lang} | {m['n']} | {m['accuracy']:.1%} | "
            f"{m['rmse']:.1f} | {m.get('bias', 0):+.1f} | {m['spearman']:.3f} |"
        )
    lines.append("")

    # --- Matrice de confusion ---
    lines.append("## Matrice de confusion (niveaux)")
    lines.append("")
    lines.append("Lignes = niveau **attendu**, colonnes = niveau **prédit par KodoNeko**.")
    lines.append("Les valeurs sur la diagonale (`▣`) sont les bonnes prédictions.")
    lines.append("")
    lines.append("| Attendu \\ Prédit | low | moderate | high | very_high |")
    lines.append("|---|---|---|---|---|")
    conf = metrics["confusion"]
    for expected in LEVELS:
        row = [f"| **{expected}**"]
        for predicted in LEVELS:
            v = conf[expected][predicted]
            marker = " ▣" if expected == predicted else ""
            row.append(f"{v}{marker}")
        lines.append(" | ".join(row) + " |")
    lines.append("")

    # --- Détail par cas ---
    lines.append("## Détail par cas")
    lines.append("")
    lines.append("| ID | Lang | Attendu (level/risk) | Prédit (level/risk) | Δ risk | Statut |")
    lines.append("|---|---|---|---|---|---|")
    for c, r in sorted(paired, key=lambda x: x[0]["id"]):
        delta = r["kodoneko_risk"] - c["expected_risk"]
        match = c["expected_level"] == r["kodoneko_level"]
        statut = "✓" if match else f"✗ ({c['expected_level']}→{r['kodoneko_level']})"
        lines.append(
            f"| {c['id']} | {c['language'][:3]} | "
            f"{c['expected_level']} / {c['expected_risk']} | "
            f"{r['kodoneko_level']} / {r['kodoneko_risk']:.1f} | "
            f"{delta:+.1f} | {statut} |"
        )
    lines.append("")

    # --- Cas qui posent problème (écart > 15) ---
    problematic = [
        (c, r) for c, r in paired
        if abs(r["kodoneko_risk"] - c["expected_risk"]) > 15
    ]
    if problematic:
        lines.append("## Cas problématiques (|Δ risk| > 15)")
        lines.append("")
        for c, r in problematic:
            lines.append(f"### `{c['id']}` ({c['language']})")
            lines.append("")
            lines.append(f"- **Attendu** : risk={c['expected_risk']}, level=`{c['expected_level']}`, cognitive≈{c['expected_cognitive']}")
            lines.append(f"- **Prédit**  : risk={r['kodoneko_risk']:.1f}, level=`{r['kodoneko_level']}`, cognitive={r['kodoneko_cognitive']}")
            lines.append(f"- **Δ risk** : {r['kodoneko_risk'] - c['expected_risk']:+.1f}")
            lines.append(f"- **Raison annotation** : {c['rationale']}")
            lines.append(f"- **Décomposition mesurée** : fn_len_max={r['fn_length_max']}, "
                          f"depth={r['nesting_depth_max']}, "
                          f"params={r['parameter_count_max']}, "
                          f"density={r['line_density_avg']:.1f}, "
                          f"id_len={r['identifier_length_avg']:.1f}")
            lines.append("")

    # --- Erreurs d'exécution ---
    errors = [r for r in results if not r.get("ok")]
    if errors:
        lines.append("## Erreurs d'évaluation")
        lines.append("")
        for r in errors:
            lines.append(f"- `{r['id']}` : {r['error']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Rapport généré par `calibration/evaluate.py`.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Évalue KodoNeko sur le dataset de calibration."
    )
    parser.add_argument(
        "--config", default=None,
        help="Chemin vers un kodoneko.toml (sinon : défauts)",
    )
    parser.add_argument(
        "--language", default=None, choices=list(DATASET_FILES.keys()),
        help="Limiter l'évaluation à un langage",
    )
    parser.add_argument(
        "--output", default=None,
        help="Fichier markdown de sortie (sinon : stdout)",
    )
    args = parser.parse_args(argv)

    # Chargement de la config (ou défauts)
    config = None
    config_source = "defaults"
    if args.config:
        from kodoneko_scanner.config import load_config
        config = load_config(args.config)
        config_source = config.source

    # Chargement du dataset
    cases = load_dataset(args.language)
    if not cases:
        print("Aucun cas trouvé.", file=sys.stderr)
        return 1
    print(f"Chargement de {len(cases)} cas...", file=sys.stderr)

    # Évaluation
    results = [evaluate_case(c, config=config) for c in cases]

    # Métriques globales
    metrics = compute_metrics(results, cases)

    # Métriques par langage
    by_language = {}
    for lang in DATASET_FILES:
        lang_cases = [c for c in cases if c["language"] == lang]
        lang_results = [r for r in results if r["id"] in {c["id"] for c in lang_cases}]
        by_language[lang] = compute_metrics(lang_results, lang_cases)

    # Rapport
    report = render_report(results, cases, metrics, by_language, config_source)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Rapport écrit dans {args.output}", file=sys.stderr)
    else:
        print(report)

    # Code retour : 0 si tous les objectifs atteints, 1 sinon
    if (metrics["accuracy"] >= 0.7 and metrics["rmse"] <= 15
            and metrics["spearman"] >= 0.8):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
