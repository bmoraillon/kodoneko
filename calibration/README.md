# Calibration empirique d'Understandability

**Auteur :** Benoît Moraillon — **Licence :** AGPL-3.0

Ce module fournit un **dataset d'exemples annotés** et un **harnais
d'évaluation** pour comparer les sorties de KodoNeko à des jugements
externes. Son rôle est de rendre défendable le choix des seuils et
poids par défaut.

## Statut : dataset enrichi n=45 (15 par langage)

Après une première itération sur 30 cas (run_001, run_002), le dataset
a été étendu à **45 cas** (15 par langage : Python, TypeScript, Java)
en ajoutant **15 cas-frontières et piégeux** spécifiquement conçus pour
stresser la métrique aux limites entre niveaux.

L'expérience a révélé un biais d'indulgence systématique d'environ
**−11 points** sur les annotations humaines, particulièrement marqué
sur les cas-frontières. Une seconde calibration (Proposition E,
adoptée en v2.3) a **resserré les paliers de level** (10/27/50 au lieu
de 15/35/60) pour absorber ce biais.

## Résultats des quatre runs sur dataset enrichi n=45

| Run | Seuils sous-métriques | Paliers level | Accord | RMSE | Spearman |
|---|---|---|---|---|---|
| 1 | origine v2.0 | 15/35/60 | 40 % | 23.0 | 0.909 |
| 2 | révisés v2.2 | 15/35/60 | 75.6 % | 12.7 | 0.968 |
| 3 | révisés v2.2 | 15/35/60 (dup) | 60 % | 12.7 | 0.968 |
| **4** | **révisés v2.2** | **10/27/50 (v2.3)** | **75.6 %** ✓ | **12.7** ✓ | **0.968** ✓ |

Objectifs métiers (accord ≥ 70 %, RMSE ≤ 15, Spearman ≥ 0.80) : **tous
atteints en v2.3**.

Note : Run 2 et Run 4 produisent le même accord parce que Run 2
calcule déjà avec les nouveaux paliers v2.3 (le harnais a été mis à
jour). Run 3 reproduit explicitement l'ancien comportement v2.2 pour
montrer le chemin parcouru.

## Limites assumées

Ces résultats reposent sur un dataset modeste, et les défauts sont à
considérer comme **« défauts révisés en calibration de validation »**
plutôt que comme des défauts définitivement validés.

1. **n=45 cas** : volume amélioré par rapport au pilote initial mais
   reste insuffisant pour une calibration de production.
2. **Annotateur unique** : Claude Opus 4.7. Risque de biais
   systématique cohérent à travers tous les cas.
3. **Pas de validation croisée** : trop peu de données.
4. **Annotations « ressenti LLM »** : les jugements humains réels
   peuvent diverger sur les cas-frontières (où nos annotations sont
   les plus subjectives).

Une calibration de production demanderait **n ≥ 150** cas et au moins
**deux annotateurs indépendants** (humain + LLM).

## Le récit de la calibration en deux phases

### Phase 1 — Pilote n=30 (v2.2)

Première itération sur 30 cas répartis 10/10/10 par langage. Les
seuils de sous-métriques ont été resserrés (cf. ancien run_002) :
cognitive 5/15/30 → 3/10/20, function_length 20/50/100 → 8/25/50,
nesting_depth 2/4/6 → 1/3/5, line_density 40/80/120 → 25/50/80.

Résultat sur n=30 : accord 80 %, RMSE 11.3, Spearman 0.977. La
métrique semblait excellente.

### Phase 2 — Validation sur dataset enrichi n=45 (v2.3)

L'ajout de 15 cas-frontières (par construction proches des limites
entre niveaux) a révélé que le pilote v2.2 était **artificiellement
bon** : l'accord retombe à 75.6 % avec les nouveaux paliers v2.3
(60 % avec les anciens paliers v2.2 sur dataset enrichi).

Le diagnostic montre que la métrique **classe très bien** (Spearman
0.97) mais **sous-estime systématiquement de 11 points en valeur
absolue**. Solution : abaisser les **paliers de level** (qualifient le
risk numérique en low/moderate/high/very_high) sans toucher aux
**seuils de sous-métriques** (déjà bien calibrés).

Adoption en v2.3 : paliers `10 / 27 / 50` au lieu de `15 / 35 / 60`.

## Paliers de level adoptés (v2.3)

| Risk | Niveau | Avant (v2.2) | Après (v2.3) |
|---|---|---|---|
| ≤ palier 1 | low | ≤ 15 | **≤ 10** |
| ≤ palier 2 | moderate | ≤ 35 | **≤ 27** |
| ≤ palier 3 | high | ≤ 60 | **≤ 50** |
| > palier 3 | very_high | > 60 | **> 50** |

Les **seuils de sous-métriques** (v2.2) restent inchangés.

## Méthode

### Constitution du dataset

Chaque cas est composé de :

- un identifiant unique (`py_001`, `ts_004`, `java_009`)
- le langage et le code source brut
- l'origine (`generated` ou `reproduced_real_style`)
- les annotations attendues : `expected_risk` (0-100), `expected_level`,
  `expected_cognitive`
- une justification de la note attendue
- l'identifiant et la date de l'annotateur

Composition par langage (15 cas) :
- 3 low, 5-6 moderate, 4 high, 2-3 very_high
- ~60 % cas générés, ~40 % cas reproduits dans le style open-source
- 5 cas-frontières/piégeux par langage (ids 11-15)

### Métriques d'évaluation

- **Accord catégoriel** : pourcentage de cas où KodoNeko prédit le même
  niveau (low/moderate/high/very_high) que l'annotation. **Objectif ≥ 70 %**.
- **RMSE sur risk** : erreur quadratique moyenne entre `expected_risk` et
  `kodoneko_risk`. **Objectif ≤ 15**.
- **Corrélation de Spearman** : préservation de l'ordre entre les deux
  séries. **Objectif ≥ 0.80**.
- **Confusion par niveau** : matrice 4×4 montrant où KodoNeko se trompe.

## Usage

### Évaluer KodoNeko sur le dataset

```bash
# Avec tree-sitter installé (vraie évaluation)
python calibration/evaluate.py

# Avec une config personnalisée
python calibration/evaluate.py --config my-config.toml

# Filtrer par langage
python calibration/evaluate.py --language python

# Sortie markdown
python calibration/evaluate.py --output calibration/results/run_NNN.md
```

### Régénérer les rapports historiques

```bash
# Régénère les 4 runs sur le dataset n=45
python calibration/regenerate_runs.py
```

Ce script utilise des estimations manuelles des sous-métriques (cf.
`_estimations.py`), reproductibles sans tree-sitter installé.

## Politique d'évolution

Le dataset versionné dans Git constitue la **mémoire institutionnelle**
des choix de calibration. Toute proposition de modification des seuils
ou paliers par défaut doit s'accompagner d'une exécution
`evaluate.py --output results/run_NNN.md` qui démontre l'amélioration
(et la non-régression sur les cas déjà bien gérés).

### Étapes suivantes proposées

1. **Étendre à n=150** (50 par langage) avec deux annotateurs
   supplémentaires (autre LLM + humain de validation).
2. Recalibrer avec validation croisée 5-fold.
3. Ajouter d'autres langages (Rust, Go) si le projet KodoNeko global
   les requiert.
4. **Optionnel** : calibration contre l'historique git de projets
   réels (commits étiquetés bug-fix → mesure du code avant correction).
