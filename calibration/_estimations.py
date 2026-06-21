"""Estimations manuelles des sous-métriques pour chaque cas du dataset.

Ces estimations sont utilisées par `regenerate_runs.py` pour reproduire
les rapports de calibration historiques sans avoir tree-sitter installé.

Méthodologie d'estimation :

- `cognitive` : nb d'incrémentations Campbell (if/for/while + bonus
  d'imbrication) compté à la main sur le code source de chaque cas.
- `fn_length` : nombre de lignes de la fonction la plus longue.
- `depth` : profondeur d'imbrication maximale.
- `params` : nombre de paramètres max trouvé.
- `density` : caractères non-blancs par ligne non-vide (moyenne fichier).
- `id_len` : longueur moyenne des identifiants (variables, fonctions).

Ces valeurs sont approximatives mais cohérentes avec ce que tree-sitter
calculerait. Pour la vraie évaluation avec tree-sitter, lancer
`evaluate.py`.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "calibration"))
from evaluate import compute_metrics, load_dataset, DATASET_FILES


MANUAL_ESTIMATIONS = {
    # ---- Python ----
    "py_001": {"cognitive": 0, "fn_length": 2,  "depth": 0, "params": 1, "density": 25, "id_len": 7.0},
    "py_002": {"cognitive": 1, "fn_length": 5,  "depth": 1, "params": 1, "density": 30, "id_len": 6.0},
    "py_003": {"cognitive": 2, "fn_length": 5,  "depth": 2, "params": 3, "density": 35, "id_len": 7.0},
    "py_004": {"cognitive": 0, "fn_length": 14, "depth": 0, "params": 5, "density": 16, "id_len": 1.0},
    "py_005": {"cognitive": 9, "fn_length": 24, "depth": 3, "params": 1, "density": 32, "id_len": 5.5},
    "py_006": {"cognitive": 0, "fn_length": 17, "depth": 0, "params": 8, "density": 33, "id_len": 1.5},
    "py_007": {"cognitive": 17, "fn_length": 27, "depth": 5, "params": 2, "density": 30, "id_len": 5.5},
    "py_008": {"cognitive": 20, "fn_length": 40, "depth": 5, "params": 1, "density": 32, "id_len": 4.0},
    "py_009": {"cognitive": 28, "fn_length": 29, "depth": 6, "params": 7, "density": 25, "id_len": 1.0},
    "py_010": {"cognitive": 32, "fn_length": 39, "depth": 6, "params": 2, "density": 30, "id_len": 1.5},
    # Cas-frontière low/moderate : court mais avec qq branches
    "py_011": {"cognitive": 4,  "fn_length": 11, "depth": 1, "params": 1, "density": 30, "id_len": 6.0},
    # Cas piégeux : list comprehension dense, court mais cognitivement chargé
    "py_012": {"cognitive": 10, "fn_length": 12, "depth": 2, "params": 3, "density": 35, "id_len": 7.0},
    # Cas piégeux : long mais bien découpé en étapes
    "py_013": {"cognitive": 5,  "fn_length": 23, "depth": 2, "params": 1, "density": 28, "id_len": 8.5},
    # Cas-frontière high/very_high : async retry, imbrication + branches
    "py_014": {"cognitive": 18, "fn_length": 34, "depth": 4, "params": 3, "density": 32, "id_len": 6.5},
    # Cas idiomatique : décorateur paramétré (closure 3 niveaux)
    "py_015": {"cognitive": 8,  "fn_length": 15, "depth": 3, "params": 2, "density": 30, "id_len": 5.5},

    # ---- TypeScript ----
    "ts_001": {"cognitive": 0, "fn_length": 3,  "depth": 0, "params": 1, "density": 25, "id_len": 7.0},
    "ts_002": {"cognitive": 2, "fn_length": 8,  "depth": 2, "params": 2, "density": 30, "id_len": 6.5},
    "ts_003": {"cognitive": 1, "fn_length": 11, "depth": 1, "params": 2, "density": 28, "id_len": 6.5},
    "ts_004": {"cognitive": 6, "fn_length": 22, "depth": 2, "params": 2, "density": 35, "id_len": 6.0},
    "ts_005": {"cognitive": 8, "fn_length": 27, "depth": 4, "params": 1, "density": 30, "id_len": 6.5},
    "ts_006": {"cognitive": 11, "fn_length": 30, "depth": 3, "params": 2, "density": 32, "id_len": 7.0},
    "ts_007": {"cognitive": 21, "fn_length": 46, "depth": 4, "params": 3, "density": 35, "id_len": 6.0},
    "ts_008": {"cognitive": 16, "fn_length": 44, "depth": 4, "params": 3, "density": 33, "id_len": 6.0},
    "ts_009": {"cognitive": 33, "fn_length": 50, "depth": 7, "params": 6, "density": 28, "id_len": 1.0},
    "ts_010": {"cognitive": 28, "fn_length": 55, "depth": 5, "params": 3, "density": 35, "id_len": 7.5},
    # Cas-frontière low/moderate : switch sur 4 cas
    "ts_011": {"cognitive": 4,  "fn_length": 11, "depth": 1, "params": 1, "density": 35, "id_len": 6.5},
    # Cas piégeux : Promise chaining avec gestion d'erreurs imbriquée
    "ts_012": {"cognitive": 13, "fn_length": 23, "depth": 3, "params": 4, "density": 38, "id_len": 8.0},
    # Cas piégeux : long mais bien découpé en étapes
    "ts_013": {"cognitive": 4,  "fn_length": 27, "depth": 1, "params": 3, "density": 30, "id_len": 8.0},
    # Cas-frontière high/very_high : reducer complexe
    "ts_014": {"cognitive": 22, "fn_length": 46, "depth": 4, "params": 2, "density": 42, "id_len": 6.5},
    # Cas idiomatique : observer generic avec closures
    "ts_015": {"cognitive": 9,  "fn_length": 24, "depth": 3, "params": 1, "density": 30, "id_len": 7.5},

    # ---- Java ----
    "java_001": {"cognitive": 0, "fn_length": 3,  "depth": 0, "params": 1, "density": 25, "id_len": 7.5},
    "java_002": {"cognitive": 2, "fn_length": 9,  "depth": 1, "params": 2, "density": 30, "id_len": 6.5},
    "java_003": {"cognitive": 3, "fn_length": 10, "depth": 2, "params": 1, "density": 30, "id_len": 7.0},
    "java_004": {"cognitive": 4, "fn_length": 19, "depth": 1, "params": 3, "density": 32, "id_len": 7.5},
    "java_005": {"cognitive": 8, "fn_length": 26, "depth": 2, "params": 1, "density": 38, "id_len": 7.0},
    "java_006": {"cognitive": 0, "fn_length": 19, "depth": 0, "params": 6, "density": 22, "id_len": 1.5},
    "java_007": {"cognitive": 18, "fn_length": 32, "depth": 4, "params": 2, "density": 38, "id_len": 6.0},
    "java_008": {"cognitive": 16, "fn_length": 30, "depth": 3, "params": 0, "density": 32, "id_len": 6.5},
    "java_009": {"cognitive": 30, "fn_length": 38, "depth": 6, "params": 6, "density": 28, "id_len": 1.5},
    "java_010": {"cognitive": 28, "fn_length": 44, "depth": 5, "params": 5, "density": 42, "id_len": 8.0},
    # Cas-frontière low/moderate : switch enum moderne
    "java_011": {"cognitive": 5,  "fn_length": 10, "depth": 1, "params": 2, "density": 38, "id_len": 8.0},
    # Cas piégeux : Stream API en chaîne
    "java_012": {"cognitive": 12, "fn_length": 19, "depth": 2, "params": 3, "density": 40, "id_len": 9.5},
    # Cas piégeux : long mais bien découpé en étapes
    "java_013": {"cognitive": 5,  "fn_length": 28, "depth": 2, "params": 2, "density": 30, "id_len": 8.0},
    # Cas-frontière high/very_high : transaction SQL avec rollback
    "java_014": {"cognitive": 20, "fn_length": 48, "depth": 4, "params": 6, "density": 45, "id_len": 7.5},
    # Cas idiomatique : Builder pattern (Java 8+)
    "java_015": {"cognitive": 7,  "fn_length": 8,  "depth": 2, "params": 1, "density": 35, "id_len": 8.5},
}


def normalize_component(value, metric, thresholds, inverted=False):
    """Réimplémentation locale de _normalize_component."""
    t = thresholds[metric]
    low, high, vhigh = t["low"], t["high"], t["very_high"]
    if inverted:
        if value >= low: return 0.0
        if value >= high: return 33.0 * (low - value) / (low - high)
        if value >= vhigh: return 33.0 + 33.0 * (high - value) / (high - vhigh)
        return min(100.0, 66.0 + 34.0 * (vhigh - value) / max(1, vhigh))
    if value <= low: return 0.0
    if value <= high: return 33.0 * (value - low) / (high - low)
    if value <= vhigh: return 33.0 + 33.0 * (value - high) / (vhigh - high)
    return min(100.0, 66.0 + 34.0 * (value - vhigh) / max(1, vhigh))


def risk_to_level(risk):
    # Paliers révisés v2.3 (post-calibration n=45)
    if risk <= 10: return "low"
    if risk <= 27: return "moderate"
    if risk <= 50: return "high"
    return "very_high"


def compute_risk(est, weights, thresholds):
    c_cog   = normalize_component(est["cognitive"],   "cognitive",         thresholds)
    c_len   = normalize_component(est["fn_length"],   "function_length",   thresholds)
    c_depth = normalize_component(est["depth"],       "nesting_depth",     thresholds)
    c_par   = normalize_component(est["params"],      "parameter_count",   thresholds)
    c_den   = normalize_component(est["density"],     "line_density",      thresholds)
    c_id    = normalize_component(est["id_len"],      "identifier_length", thresholds, inverted=True)
    risk = (
        weights["cognitive"]         * c_cog
        + weights["function_length"]   * c_len
        + weights["nesting_depth"]     * c_depth
        + weights["parameter_count"]   * c_par
        + weights["line_density"]      * c_den
        + weights["identifier_length"] * c_id
    )
    return max(0.0, min(100.0, risk))


def simulate(weights, thresholds):
    """Simulation complète : retourne (results, cases, metrics, by_lang)."""
    cases = load_dataset()
    results = []
    for case in cases:
        est = MANUAL_ESTIMATIONS.get(case["id"])
        if not est:
            results.append({"id": case["id"], "ok": False, "error": "no manual estimation"})
            continue
        risk = compute_risk(est, weights, thresholds)
        results.append({
            "id": case["id"], "ok": True,
            "kodoneko_risk": round(risk, 1),
            "kodoneko_level": risk_to_level(risk),
            "kodoneko_cognitive": est["cognitive"],
            "fn_length_max": est["fn_length"],
            "nesting_depth_max": est["depth"],
            "parameter_count_max": est["params"],
            "line_density_avg": float(est["density"]),
            "identifier_length_avg": float(est["id_len"]),
        })
    metrics = compute_metrics(results, cases)
    by_lang = {}
    for lang in DATASET_FILES:
        lang_cases = [c for c in cases if c["language"] == lang]
        lang_results = [r for r in results if r["id"] in {c["id"] for c in lang_cases}]
        by_lang[lang] = compute_metrics(lang_results, lang_cases)
    return results, cases, metrics, by_lang
