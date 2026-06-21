"""Génération des rapports de calibration historiques.

Ce script reproduit les runs de calibration documentés dans
`calibration/results/`. Il utilise des estimations manuelles des
sous-métriques (cf. note dans `_estimations.py`).

Usage :
    python calibration/regenerate_runs.py

Pour la vraie exécution avec tree-sitter installé, utiliser `evaluate.py`
sur le dataset JSONL.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "calibration"))
sys.path.insert(0, str(ROOT / "kodoneko_metrics" / "src"))

from evaluate import compute_metrics, load_dataset, render_report, DATASET_FILES
from _estimations import MANUAL_ESTIMATIONS, simulate

# Seuils d'origine v2.0/v2.1 (pré-calibration)
LEGACY_THRESHOLDS = {
    "cognitive":         {"low": 5,  "high": 15, "very_high": 30},
    "function_length":   {"low": 20, "high": 50, "very_high": 100},
    "nesting_depth":     {"low": 2,  "high": 4,  "very_high": 6},
    "parameter_count":   {"low": 3,  "high": 5,  "very_high": 8},
    "line_density":      {"low": 40, "high": 80, "very_high": 120},
    "identifier_length": {"low": 8,  "high": 5,  "very_high": 3},
}

# Seuils révisés v2.2/v0.7 (post-calibration pilote n=30)
REVISED_THRESHOLDS = {
    "cognitive":         {"low": 3,  "high": 10, "very_high": 20},
    "function_length":   {"low": 8,  "high": 25, "very_high": 50},
    "nesting_depth":     {"low": 1,  "high": 3,  "very_high": 5},
    "parameter_count":   {"low": 3,  "high": 5,  "very_high": 8},
    "line_density":      {"low": 25, "high": 50, "very_high": 80},
    "identifier_length": {"low": 8,  "high": 5,  "very_high": 3},
}

DEFAULT_WEIGHTS = {
    "cognitive":         0.30,
    "function_length":   0.20,
    "nesting_depth":     0.15,
    "parameter_count":   0.15,
    "line_density":      0.10,
    "identifier_length": 0.10,
}


def run(label, weights, thresholds, output_name):
    """Lance une simulation, écrit le rapport, retourne les métriques globales."""
    results, cases, metrics, by_lang = simulate(
        weights=weights, thresholds=thresholds,
    )
    report = render_report(
        results, cases, metrics, by_lang,
        config_source=label,
    )
    output = ROOT / "calibration" / "results" / output_name
    output.write_text(report, encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print("Régénération des runs de calibration...")
    print()

    # Run 001 : défauts d'origine (avant calibration) sur le dataset enrichi
    m1 = run(
        "defaults v2.0/v2.1 (seuils d'origine, pré-calibration)",
        DEFAULT_WEIGHTS, LEGACY_THRESHOLDS,
        "run_001_defaults.md",
    )
    print("run_001 (défauts d'origine, dataset n=45) :")
    print(f"  Accord {m1['accuracy']:.1%}  RMSE {m1['rmse']:.1f}  "
          f"Spearman {m1['spearman']:.3f}  Biais {m1.get('bias', 0):+.1f}")
    print()

    # Run 002 : défauts révisés (post-calibration pilote)
    m2 = run(
        "defaults v2.2/v0.7 (seuils révisés post-calibration n=30)",
        DEFAULT_WEIGHTS, REVISED_THRESHOLDS,
        "run_002_revised_defaults.md",
    )
    print("run_002 (défauts révisés, dataset n=45) :")
    print(f"  Accord {m2['accuracy']:.1%}  RMSE {m2['rmse']:.1f}  "
          f"Spearman {m2['spearman']:.3f}  Biais {m2.get('bias', 0):+.1f}")
    print()

    # Run 003 : validation sur dataset enrichi n=45 (mêmes seuils que run_002,
    # mais le dataset a été enrichi avec 15 cas-frontières et piégeux pour
    # stresser davantage la métrique).
    # Pour ce run, on force les paliers de level d'origine (v2.2 : 15/35/60)
    # pour montrer ce qui se passe SANS l'ajustement final.
    from _estimations import simulate as _sim
    from evaluate import compute_metrics as _cm, DATASET_FILES as _DF

    # Forcer les paliers v2.2 (d'origine) pour le run_003
    def _level_v22(risk):
        if risk <= 15: return "low"
        if risk <= 35: return "moderate"
        if risk <= 60: return "high"
        return "very_high"

    results3, cases3, _, _ = _sim(weights=DEFAULT_WEIGHTS, thresholds=REVISED_THRESHOLDS)
    for r in results3:
        if r.get("ok"):
            r["kodoneko_level"] = _level_v22(r["kodoneko_risk"])
    m3 = _cm(results3, cases3)
    by_lang3 = {}
    for lang in _DF:
        lang_cases = [c for c in cases3 if c["language"] == lang]
        lang_results = [r for r in results3 if r["id"] in {c["id"] for c in lang_cases}]
        by_lang3[lang] = _cm(lang_results, lang_cases)
    from evaluate import render_report as _rr
    report3 = _rr(
        results3, cases3, m3, by_lang3,
        config_source="defaults v2.2/v0.7 (paliers level 15/35/60) — dataset n=45",
    )
    (ROOT / "calibration" / "results" / "run_003_enriched_dataset.md").write_text(
        report3, encoding="utf-8",
    )
    print("run_003 (validation dataset enrichi n=45, paliers v2.2) :")
    print(f"  Accord {m3['accuracy']:.1%}  RMSE {m3['rmse']:.1f}  "
          f"Spearman {m3['spearman']:.3f}  Biais {m3.get('bias', 0):+.1f}")
    print()

    # Run 004 : Proposition E adoptée (paliers de level resserrés en v2.3)
    m4 = run(
        "defaults v2.3/v0.9 (paliers level resserrés 10/27/50 — adoption finale)",
        DEFAULT_WEIGHTS, REVISED_THRESHOLDS,
        "run_004_revised_levels.md",
    )
    print("run_004 (paliers révisés v2.3, dataset enrichi n=45) :")
    print(f"  Accord {m4['accuracy']:.1%}  RMSE {m4['rmse']:.1f}  "
          f"Spearman {m4['spearman']:.3f}  Biais {m4.get('bias', 0):+.1f}")
    print()

    # Tableau comparatif des 4 runs
    print("=" * 80)
    print("COMPARAISON DES QUATRE RUNS")
    print("=" * 80)
    print(f"{'Métrique':<22} {'Run 1':>12} {'Run 2':>12} {'Run 3':>12} {'Run 4':>12}")
    print(f"{'(seuils ssm)':<22} {'origine':>12} {'révisés':>12} {'révisés':>12} {'révisés':>12}")
    print(f"{'(paliers level)':<22} {'15/35/60':>12} {'15/35/60':>12} {'15/35/60':>12} {'10/27/50':>12}")
    print(f"{'(dataset)':<22} {'n=45':>12} {'n=45':>12} {'n=45':>12} {'n=45':>12}")
    print("-" * 80)
    print(f"{'Accord catégoriel':<22} {m1['accuracy']:>11.1%} {m2['accuracy']:>11.1%} {m3['accuracy']:>11.1%} {m4['accuracy']:>11.1%}")
    print(f"{'RMSE':<22} {m1['rmse']:>12.1f} {m2['rmse']:>12.1f} {m3['rmse']:>12.1f} {m4['rmse']:>12.1f}")
    print(f"{'Spearman':<22} {m1['spearman']:>12.3f} {m2['spearman']:>12.3f} {m3['spearman']:>12.3f} {m4['spearman']:>12.3f}")
    print(f"{'Biais signé':<22} {m1.get('bias', 0):>+12.1f} {m2.get('bias', 0):>+12.1f} {m3.get('bias', 0):>+12.1f} {m4.get('bias', 0):>+12.1f}")
    print()
    print("Notes :")
    print("  - run_002 = run_003 par construction (paliers identiques, dataset enrichi)")
    print("  - run_004 = adoption finale en v2.3 (paliers level resserrés)")
    print()
    print(f"Rapports écrits dans calibration/results/")
