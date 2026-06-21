# kodoneko — Projet Jupyter

**Auteur :** Benoît Moraillon · **Licence :** AGPL-3.0

Suite d'outils pour mesurer le code source et son évolution dans le temps :
métriques de qualité, comptage de taille fonctionnelle COSMIC (ISO/IEC 19761),
et analyse temporelle sur l'historique git.

> kodoneko produit des **mesures objectives et reproductibles** (taille
> fonctionnelle, qualité). Il ne fait aucune estimation d'effort, de coût ou de
> délai.

---

## 🚀 Démarrage rapide

```bash
pip install -e kodoneko_metrics/ kodoneko_scanner/ kodoneko_temporal/
# Pour analyser Java / JS / TS (Python fonctionne sans) :
pip install tree-sitter tree-sitter-java tree-sitter-javascript tree-sitter-typescript

jupyter lab notebooks/   # commencez par 00_index.ipynb
```

---

## 📦 Modules

| Module | Rôle |
|--------|------|
| **`kodoneko_metrics`** | Analyse d'un fichier : lignes (NCLOC), Halstead, McCabe, compréhensibilité (ISO/IEC 25010), et **comptage COSMIC** (ISO/IEC 19761) |
| **`kodoneko_scanner`** | Scan d'un dépôt entier : métriques qualité agrégées + comptage COSMIC, avec configuration TOML |
| **`kodoneko_temporal`** | **Analyse temporelle** : applique n'importe quelle métrique à un commit donné ou par fenêtres (mensuel / hebdo / fixe) |

---

## 📚 Notebooks

Chaque notebook est **autoporteur** : il configure son contexte, et la plupart
incluent un exemple sur un dépôt public réel et une analyse temporelle.

| Notebook | Sujet |
|----------|-------|
| `01_lines` | Comptage de lignes (NCLOC, commentaires, densité) |
| `02_halstead` | Métriques de Halstead (volume, difficulté, effort algorithmique) |
| `03_mccabe` | Complexité cyclomatique de McCabe |
| `04_understandability` | Compréhensibilité composite (ISO/IEC 25010) |
| `05_primary_quality_score` | Scan d'un dépôt + PrimaryQualityScore (santé globale) |
| `07_cosmic` | Comptage COSMIC : méthode, estimation, intervalle de confiance, rendus HTML |

> Le mot « effort » dans le notebook Halstead désigne la métrique algorithmique
> **E = V × D** de Halstead — une propriété intrinsèque du code, sans rapport
> avec une charge de travail humaine.

---

## 🔌 API en bref

### Métriques qualité d'un fichier

```python
from kodoneko_metrics import CodeAnalyzer
r = CodeAnalyzer().analyze('/path/to/file.py')
r.lines.ncloc; r.halstead.volume; r.mccabe.value; r.understandability.risk
```

### Comptage COSMIC

```python
from kodoneko_scanner import scan_repo_cosmic
from kodoneko_metrics.cosmic import analyze_repo_enriched, render_repo_html

report = scan_repo_cosmic('/path/to/repo')
enriched = analyze_repo_enriched(report)
print(enriched.interval.label())          # ex: "142 CFP [118-163]"
html = render_repo_html(enriched, standalone=True)
```

### Analyse temporelle (n'importe quelle métrique)

```python
from kodoneko_temporal import analyze_at_ref, analyze_over_windows
from kodoneko_scanner import scan_repo_cosmic

pt = analyze_at_ref(repo, 'v1.0', analyzer=scan_repo_cosmic)
print(pt.result.total_cfp)

series = analyze_over_windows(repo, analyzer=scan_repo_cosmic, strategy='monthly')
for point in series:
    print(point.label, point.result.total_cfp)
```

Delta COSMIC entre commits/versions :

```python
from kodoneko_temporal import compute_cosmic_delta_for_commit, compute_cosmic_delta_for_range
```

---

## 🏗️ Architecture

```
kodoneko_jupyter/
├── notebooks/                  # 01-05 (qualité) + 07 (COSMIC) + index
├── kodoneko_metrics/           # Analyse fichier + COSMIC
├── kodoneko_scanner/           # Scan de dépôt
└── kodoneko_temporal/          # Analyse temporelle
    └── src/kodoneko_temporal/
        ├── git_extract.py      # extraction de commits / diffs
        ├── windowing.py        # découpage en fenêtres
        ├── temporal_engine.py  # moteur générique (analyseur quelconque)
        └── cosmic_delta.py     # helpers COSMIC (delta commit/version)
```

---

## ✅ Tests

```bash
cd kodoneko_metrics  && python run_tests.py
cd kodoneko_scanner  && python run_tests.py
cd kodoneko_temporal && python run_tests.py
```

---

## 📜 Licence

- **kodoneko_metrics**, **kodoneko_scanner**, **kodoneko_temporal** :
  AGPL-3.0 © Benoît Moraillon, 2026.
- Le comptage COSMIC s'appuie sur la méthode **COSMIC ISO/IEC 19761**
  (référence normative publique). kodoneko en produit une *estimation*
  automatique ; il ne délivre pas de certification.
