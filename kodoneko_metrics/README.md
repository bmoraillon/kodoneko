# kodoneko-metrics

**Métriques de qualité logicielle multi-langages via tree-sitter**

**Auteur :** Benoît Moraillon — **Licence :** AGPL-3.0 — **Version :** 2.3.0

Module Python qui combine quatre familles de métriques dans une seule
classe utilitaire :

- **Comptage de lignes** — NCLOC, SLOC, blank, comment
- **Halstead** — n1, n2, N1, N2, vocabulary, volume, difficulty, effort
- **McCabe** — complexité cyclomatique + qualification de niveau
- **Understandability** *(ISO/IEC 25010)* — **niveau de risque** composite 0-100
  reflétant la compréhensibilité du code

Conçu pour être intégré dans des projets plus larges, en particulier
[KodoNeko](https://github.com/bmoraillon/kodoneko).

## Vocabulaire : risk vs score

Pour éviter toute confusion, KodoNeko distingue strictement :

| Notion | Orientation | Où la trouver |
|---|---|---|
| **risk** | *Pire si plus haut* | `UnderstandabilityMetrics.risk` (ce module) |
| **score** | *Mieux si plus haut* | `BaselineQualityScore.score` (kodoneko-scanner) |

Cette asymétrie est volontaire : un *risque* élevé est mauvais, un *score*
élevé est bon — plus de confusion possible quand les deux nombres voyagent
ensemble dans un JSON.

## Nouveautés v2.3 — Calibration étendue n=45

Le dataset de calibration a été étendu à **45 cas annotés** (15 par
langage). L'expérience a révélé un biais d'indulgence systématique
de −11 points sur les annotations humaines, particulièrement marqué
sur les cas-frontières entre niveaux.

**Solution adoptée** : paliers de level resserrés (10/27/50 au lieu
de 15/35/60), sans toucher aux seuils de sous-métriques de la v2.2.

| Risk | Niveau | Avant (v2.2) | Après (v2.3) |
|---|---|---|---|
| ≤ palier 1 | low | ≤ 15 | **≤ 10** |
| ≤ palier 2 | moderate | ≤ 35 | **≤ 27** |
| ≤ palier 3 | high | ≤ 60 | **≤ 50** |

Sur le dataset enrichi n=45 : accord catégoriel **75.6 %** (objectif ≥
70 % atteint). Cf. `calibration/README.md` du projet.

## Nouveautés v2.2 — Calibration empirique

Les **seuils par défaut d'Understandability** ont été révisés suite à
un run de calibration pilote sur 30 cas annotés (Python + TypeScript +
Java). Sur le dataset pilote, l'accord catégoriel passe de 33 % à
**80 %** avec un RMSE divisé par 2. Méthode et chiffres complets dans
[`calibration/README.md`](../calibration/README.md) du projet.

| Sous-métrique | Avant (v2.1) | Après (v2.2) |
|---|---|---|
| `cognitive` | 5 / 15 / 30 | **3 / 10 / 20** |
| `function_length` | 20 / 50 / 100 | **8 / 25 / 50** |
| `nesting_depth` | 2 / 4 / 6 | **1 / 3 / 5** |
| `line_density` | 40 / 80 / 120 | **25 / 50 / 80** |
| `parameter_count` | 3 / 5 / 8 | inchangé |
| `identifier_length` | 8 / 5 / 3 | inchangé |

Les **pondérations** restent inchangées. **Limites** : pilote n=30,
annotateur unique. Une calibration sérieuse demande n≥150 et un panel
d'annotateurs.

## Nouveautés v2.1

- **Renommage `score` → `risk`** sur `UnderstandabilityMetrics` et
  `FunctionUnderstandability` pour éviter la confusion avec
  `BaselineQualityScore.score`. API breaking, mais le sens devient sans
  ambiguïté.

## Nouveautés v2.0

- `CognitiveMetrics` et `ReadabilityMetrics` fusionnés en
  `UnderstandabilityMetrics`, aligné sur la sous-caractéristique
  *Understandability* d'**ISO/IEC 25010** (Usability).
- La cognitive complexity (Campbell, 2017) est conservée comme
  sous-attribut (`understandability.cognitive`) pour préserver la
  comparabilité avec radon, SonarSource et l'écosystème standard.
- Risque composite 0-100 combinant 6 sous-métriques.
- Détail par fonction trié par risque décroissant.

### Changements rupture par rapport à la v1.3

| v1.3 | v2.x |
|---|---|
| `CognitiveMetrics` | *(supprimé)* — accès via `understandability.cognitive` |
| `ReadabilityMetrics` | `UnderstandabilityMetrics` |
| `FunctionReadability` | `FunctionUnderstandability` |
| `count_cognitive()` | *(supprimé)* |
| `count_readability()` | `count_understandability()` |
| `r.cognitive.value` | `r.understandability.cognitive` |
| `r.readability.frd_score` | `r.understandability.risk` *(v2.1)* |
| `r.readability.level` | `r.understandability.level` |
| `FunctionReadability.frd_score` | `FunctionUnderstandability.risk` *(v2.1)* |
| `FunctionReadability.cognitive_value` | `FunctionUnderstandability.cognitive` |

## Installation

```bash
# Base : tree-sitter + grammaire Python
pip install kodoneko-metrics

# Avec les grammaires web (TS, JS, TSX, JSX)
pip install kodoneko-metrics[web]

# Avec les grammaires de langages systèmes (Rust, Go, C, C++)
pip install kodoneko-metrics[systems]

# Tous langages
pip install kodoneko-metrics[all-languages]

# Mode dev (tests inclus)
pip install -e .[dev]
```

## Usage

### Classe principale

```python
from kodoneko_metrics import CodeAnalyzer

analyzer = CodeAnalyzer()

source = '''
def average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)
'''

r = analyzer.analyze(source, language="python")

print(r.lines.ncloc)                          # 5
print(r.halstead.volume)                      # 22.45
print(r.mccabe.value, r.mccabe.level)         # 2, low
print(r.understandability.risk)               # 0.0 (très lisible)
print(r.understandability.level)              # "low"
print(r.understandability.cognitive)          # 1 (Campbell)
```

### Fonctions de convenance

```python
from kodoneko_metrics import (
    count_lines, count_halstead, count_mccabe,
    count_understandability, count_understandability_by_function,
)

u = count_understandability(source, language="python")
print(u.risk, u.level)
```

### Détail par fonction

Pour repérer une fonction problématique dans un fichier globalement
sain :

```python
funcs = count_understandability_by_function(source, language="python")
for f in funcs:  # déjà trié par risque décroissant
    print(f"{f.name:30s} risk={f.risk:5.1f} ({f.level})")
```

## Le risque d'Understandability

### Référence normative

Le nom et la conception s'inspirent de la sous-caractéristique
**Understandability** de **ISO/IEC 25010:2011** : *« degree to which a
product or system has attributes that enable users to easily understand
whether it is appropriate »*.

### Sous-métriques

| Sous-métrique | Poids | Description |
|---|---|---|
| `cognitive` | 30 % | Complexité cognitive de Campbell (pénalise l'imbrication) |
| `function_length` | 20 % | Longueur maximale des fonctions du fichier |
| `nesting_depth` | 15 % | Profondeur d'imbrication maximale |
| `parameter_count` | 15 % | Nombre maximum de paramètres trouvé |
| `line_density` | 10 % | Caractères non-blancs / ligne (densité visuelle) |
| `identifier_length` | 10 % | Longueur moyenne des identifiants *(inversé)* |

Chaque sous-métrique est normalisée 0-100 selon trois seuils
(`low`, `high`, `very_high`), puis combinée linéairement avec ses poids.

### Niveaux qualitatifs

| Risk | Niveau | Interprétation |
|---|---|---|
| 0-10 | `low` | Code clair, facile à comprendre |
| 11-27 | `moderate` | Lecture attentive nécessaire |
| 28-50 | `high` | Difficile, refactoring conseillé |
| > 50 | `very_high` | Très difficile, refactoring fortement conseillé |

### Pourquoi un risque composite

Avant la v2.0, deux indicateurs séparés (`cognitive` et `readability`)
mesuraient des dimensions partiellement recouvrantes : la cognitive
contribuait à la fois en propre **et** comme composante du score FRD,
ce qui entraînait un double comptage dans les agrégats en aval.

La fusion en un seul indicateur ISO 25010 supprime ce double comptage
**tout en préservant l'accès à la valeur cognitive brute** pour ceux
qui veulent comparer avec radon ou SonarSource.

## Conventions

- **`exclude_docstrings=True`** par défaut : les docstrings Python sont
  comptées comme commentaires (cohérent avec la spec UO KodoNeko).
  Passer `False` pour reproduire le comportement de `cloc`.
- **Tout tree-sitter** depuis la v1.0 : aucun backend Python natif,
  aucune dépendance lourde, parsing rapide et robuste.

## Langages supportés

Python (toujours installé), TypeScript, TSX, JavaScript, Rust, Go,
Java, C, C++, Ruby, Bash — selon les extras installés.

## Licence et propriété intellectuelle

- **Licence : AGPL-3.0** © 2026 Benoît Moraillon.
- **Implémentation de la cognitive complexity** : d'après le *white
  paper public* de G. Ann Campbell (« Cognitive Complexity — A new way
  of measuring understandability », SonarSource, 2017). Code **réécrit
  from scratch**, non dérivé du code LGPL de SonarSource.
- **Conception du risque Understandability** : originale, alignée sur
  ISO/IEC 25010 comme référence normative.
- **Dépendances tree-sitter** : MIT/Apache, compatibles.

## Tests

```bash
# Avec pytest installé
pytest

# Sans pytest (runner intégré)
python run_tests.py
```

61 tests universels (avec mocks tree-sitter) + tests d'intégration
optionnels si tree-sitter est installé.
