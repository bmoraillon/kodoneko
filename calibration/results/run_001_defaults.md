# Rapport de calibration KodoNeko

**Date :** 2026-05-18 04:31 UTC
**Configuration :** `defaults v2.0/v2.1 (seuils d'origine, pré-calibration)`
**Dataset :** 45 cas annotés (45 évalués avec succès)

## Résumé global

| Métrique | Valeur | Objectif | Statut |
|---|---|---|---|
| Accord catégoriel (niveau) | 40.0% | ≥ 70 % | ✗ |
| RMSE sur risk (0-100) | 23.0 | ≤ 15 | ✗ |
| Corrélation Spearman | 0.909 | ≥ 0.80 | ✓ |
| Biais signé moyen | -20.9 | — | sous-estime |
| Distance moyenne en rang | 0.67 | ≤ 0.5 | ✗ |

## Par langage

| Langage | n | Accord | RMSE | Biais | Spearman |
|---|---|---|---|---|---|
| python | 15 | 46.7% | 21.5 | -19.0 | 0.880 |
| typescript | 15 | 40.0% | 23.1 | -21.2 | 0.961 |
| java | 15 | 33.3% | 24.3 | -22.4 | 0.920 |

## Matrice de confusion (niveaux)

Lignes = niveau **attendu**, colonnes = niveau **prédit par KodoNeko**.
Les valeurs sur la diagonale (`▣`) sont les bonnes prédictions.

| Attendu \ Prédit | low | moderate | high | very_high |
|---|---|---|---|---|
| **low** | 9 ▣ | 0 | 0 | 0 |
| **moderate** | 11 | 6 ▣ | 0 | 0 |
| **high** | 3 | 7 | 2 ▣ | 0 |
| **very_high** | 0 | 0 | 6 | 1 ▣ |

## Détail par cas

| ID | Lang | Attendu (level/risk) | Prédit (level/risk) | Δ risk | Statut |
|---|---|---|---|---|---|
| java_001 | jav | low / 5 | low / 0.6 | -4.4 | ✓ |
| java_002 | jav | low / 10 | low / 1.7 | -8.3 | ✓ |
| java_003 | jav | low / 14 | low / 1.1 | -12.9 | ✓ |
| java_004 | jav | moderate / 22 | low / 0.6 | -21.4 | ✗ (moderate→low) |
| java_005 | jav | moderate / 28 | low / 5.4 | -22.6 | ✗ (moderate→low) |
| java_006 | jav | moderate / 32 | moderate / 14.9 | -17.1 | ✓ |
| java_007 | jav | high / 45 | moderate / 21.7 | -23.3 | ✗ (high→moderate) |
| java_008 | jav | high / 52 | moderate / 16.9 | -35.1 | ✗ (high→moderate) |
| java_009 | jav | very_high / 72 | high / 48.6 | -23.4 | ✗ (very_high→high) |
| java_010 | jav | very_high / 76 | high / 36.3 | -39.7 | ✗ (very_high→high) |
| java_011 | jav | moderate / 18 | low / 0.0 | -18.0 | ✗ (moderate→low) |
| java_012 | jav | high / 40 | low / 6.9 | -33.1 | ✗ (high→low) |
| java_013 | jav | moderate / 20 | low / 1.8 | -18.2 | ✗ (moderate→low) |
| java_014 | jav | high / 60 | high / 31.9 | -28.1 | ✓ |
| java_015 | jav | moderate / 32 | low / 2.0 | -30.0 | ✗ (moderate→low) |
| py_001 | pyt | low / 3 | low / 1.1 | -1.9 | ✓ |
| py_002 | pyt | low / 8 | low / 2.2 | -5.8 | ✓ |
| py_003 | pyt | low / 12 | low / 1.1 | -10.9 | ✓ |
| py_004 | pyt | moderate / 22 | moderate / 13.8 | -8.2 | ✓ |
| py_005 | pyt | moderate / 28 | moderate / 10.1 | -17.9 | ✓ |
| py_006 | pyt | moderate / 32 | moderate / 18.2 | -13.8 | ✓ |
| py_007 | pyt | high / 45 | moderate / 22.9 | -22.1 | ✗ (high→moderate) |
| py_008 | pyt | high / 50 | high / 30.0 | -20.0 | ✓ |
| py_009 | pyt | very_high / 72 | high / 47.5 | -24.5 | ✗ (very_high→high) |
| py_010 | pyt | very_high / 78 | high / 42.9 | -35.1 | ✗ (very_high→high) |
| py_011 | pyt | moderate / 16 | low / 2.2 | -13.8 | ✗ (moderate→low) |
| py_012 | pyt | high / 38 | low / 6.1 | -31.9 | ✗ (high→low) |
| py_013 | pyt | moderate / 18 | low / 0.7 | -17.3 | ✗ (moderate→low) |
| py_014 | pyt | high / 58 | moderate / 21.6 | -36.4 | ✗ (high→moderate) |
| py_015 | pyt | moderate / 33 | low / 8.2 | -24.8 | ✗ (moderate→low) |
| ts_001 | typ | low / 4 | low / 1.1 | -2.9 | ✓ |
| ts_002 | typ | low / 10 | low / 1.7 | -8.3 | ✓ |
| ts_003 | typ | low / 14 | low / 1.7 | -12.3 | ✓ |
| ts_004 | typ | moderate / 24 | low / 3.6 | -20.4 | ✗ (moderate→low) |
| ts_005 | typ | moderate / 30 | moderate / 11.1 | -18.9 | ✓ |
| ts_006 | typ | moderate / 34 | moderate / 11.7 | -22.3 | ✓ |
| ts_007 | typ | high / 48 | moderate / 26.7 | -21.3 | ✗ (high→moderate) |
| ts_008 | typ | high / 55 | moderate / 23.0 | -32.0 | ✗ (high→moderate) |
| ts_009 | typ | very_high / 75 | very_high / 53.6 | -21.4 | ✓ |
| ts_010 | typ | very_high / 70 | high / 33.7 | -36.3 | ✗ (very_high→high) |
| ts_011 | typ | moderate / 17 | low / 1.7 | -15.3 | ✗ (moderate→low) |
| ts_012 | typ | high / 40 | moderate / 13.5 | -26.5 | ✗ (high→moderate) |
| ts_013 | typ | moderate / 19 | low / 1.5 | -17.5 | ✗ (moderate→low) |
| ts_014 | typ | very_high / 62 | high / 27.0 | -35.0 | ✗ (very_high→high) |
| ts_015 | typ | high / 36 | low / 7.9 | -28.1 | ✗ (high→low) |

## Cas problématiques (|Δ risk| > 15)

### `py_005` (python)

- **Attendu** : risk=28, level=`moderate`, cognitive≈8
- **Prédit**  : risk=10.1, level=`moderate`, cognitive=9
- **Δ risk** : -17.9
- **Raison annotation** : Style requests/urllib, parsing d'URL avec plusieurs cas conditionnels en cascade. 30 lignes, imbrication modérée, identifiants corrects.
- **Décomposition mesurée** : fn_len_max=24, depth=3, params=1, density=32.0, id_len=5.5

### `py_007` (python)

- **Attendu** : risk=45, level=`high`, cognitive≈18
- **Prédit**  : risk=22.9, level=`moderate`, cognitive=17
- **Δ risk** : -22.1
- **Raison annotation** : Imbrication profonde (4 niveaux), nombreuses conditions, identifiants courts. Typique d'un code à refactorer.
- **Décomposition mesurée** : fn_len_max=27, depth=5, params=2, density=30.0, id_len=5.5

### `py_008` (python)

- **Attendu** : risk=50, level=`high`, cognitive≈20
- **Prédit**  : risk=30.0, level=`high`, cognitive=20
- **Δ risk** : -20.0
- **Raison annotation** : Style legacy CPython, machine à état avec beaucoup de branches conditionnelles imbriquées. ~50 lignes, plusieurs niveaux de boucle/if, hard à suivre sans contexte.
- **Décomposition mesurée** : fn_len_max=40, depth=5, params=1, density=32.0, id_len=4.0

### `py_009` (python)

- **Attendu** : risk=72, level=`very_high`, cognitive≈32
- **Prédit**  : risk=47.5, level=`high`, cognitive=28
- **Δ risk** : -24.5
- **Raison annotation** : Toutes dimensions dégradées : 60 lignes, 7 paramètres, imbrication 5 niveaux, identifiants 1 caractère, beaucoup de conditions. Refactoring urgent.
- **Décomposition mesurée** : fn_len_max=29, depth=6, params=7, density=25.0, id_len=1.0

### `py_010` (python)

- **Attendu** : risk=78, level=`very_high`, cognitive≈38
- **Prédit**  : risk=42.9, level=`high`, cognitive=32
- **Δ risk** : -35.1
- **Raison annotation** : Style legacy Python 2 numerical code : 80 lignes, double boucle imbriquée avec conditions branchées, beaucoup de variables courtes, expressions denses. Code typique à refactorer.
- **Décomposition mesurée** : fn_len_max=39, depth=6, params=2, density=30.0, id_len=1.5

### `py_012` (python)

- **Attendu** : risk=38, level=`high`, cognitive≈14
- **Prédit**  : risk=6.1, level=`low`, cognitive=10
- **Δ risk** : -31.9
- **Raison annotation** : Cas-frontière moderate/high : list comprehension imbriquée non triviale, double itération, condition non évidente. Court mais cognitivement dense (piégeux).
- **Décomposition mesurée** : fn_len_max=12, depth=2, params=3, density=35.0, id_len=7.0

### `py_013` (python)

- **Attendu** : risk=18, level=`moderate`, cognitive≈6
- **Prédit**  : risk=0.7, level=`low`, cognitive=5
- **Δ risk** : -17.3
- **Raison annotation** : Cas piégeux : fonction longue (~30 lignes) mais bien découpée mentalement par étapes commentées, identifiants explicites. Style propre flask/django. La longueur seule ne suffit pas à dégrader le risk si la structure est claire.
- **Décomposition mesurée** : fn_len_max=23, depth=2, params=1, density=28.0, id_len=8.5

### `py_014` (python)

- **Attendu** : risk=58, level=`high`, cognitive≈24
- **Prédit**  : risk=21.6, level=`moderate`, cognitive=18
- **Δ risk** : -36.4
- **Raison annotation** : Cas-frontière high/very_high : context manager async avec gestion d'erreurs en cascade, plusieurs niveaux d'imbrication, identifiants OK mais densité visuelle élevée.
- **Décomposition mesurée** : fn_len_max=34, depth=4, params=3, density=32.0, id_len=6.5

### `py_015` (python)

- **Attendu** : risk=33, level=`moderate`, cognitive≈11
- **Prédit**  : risk=8.2, level=`low`, cognitive=8
- **Δ risk** : -24.8
- **Raison annotation** : Cas idiomatique Python : décorateur paramétré (closure à 3 niveaux). Pattern courant en Flask/Django/FastAPI. Imbrication conceptuelle (def dans def dans def) mais structure standard reconnaissable. Demande attention sans être critique.
- **Décomposition mesurée** : fn_len_max=15, depth=3, params=2, density=30.0, id_len=5.5

### `ts_004` (typescript)

- **Attendu** : risk=24, level=`moderate`, cognitive≈7
- **Prédit**  : risk=3.6, level=`low`, cognitive=6
- **Δ risk** : -20.4
- **Raison annotation** : Reducer Redux-style avec switch sur 5 actions. Plat mais long et répétitif, demande attention.
- **Décomposition mesurée** : fn_len_max=22, depth=2, params=2, density=35.0, id_len=6.0

### `ts_005` (typescript)

- **Attendu** : risk=30, level=`moderate`, cognitive≈10
- **Prédit**  : risk=11.1, level=`moderate`, cognitive=8
- **Δ risk** : -18.9
- **Raison annotation** : Style VSCode, parsing d'options CLI avec plusieurs branches. ~35 lignes, imbrication modérée.
- **Décomposition mesurée** : fn_len_max=27, depth=4, params=1, density=30.0, id_len=6.5

### `ts_006` (typescript)

- **Attendu** : risk=34, level=`moderate`, cognitive≈12
- **Prédit**  : risk=11.7, level=`moderate`, cognitive=11
- **Δ risk** : -22.3
- **Raison annotation** : Logique métier avec plusieurs conditions et boucles. ~40 lignes, identifiants ok mais densité visuelle assez haute.
- **Décomposition mesurée** : fn_len_max=30, depth=3, params=2, density=32.0, id_len=7.0

### `ts_007` (typescript)

- **Attendu** : risk=48, level=`high`, cognitive≈22
- **Prédit**  : risk=26.7, level=`moderate`, cognitive=21
- **Δ risk** : -21.3
- **Raison annotation** : Algorithme de validation complexe, imbrication 4-5 niveaux, beaucoup de branchements. Difficile à suivre.
- **Décomposition mesurée** : fn_len_max=46, depth=4, params=3, density=35.0, id_len=6.0

### `ts_008` (typescript)

- **Attendu** : risk=55, level=`high`, cognitive≈26
- **Prédit**  : risk=23.0, level=`moderate`, cognitive=16
- **Δ risk** : -32.0
- **Raison annotation** : Style VSCode renderer, machine à état pour layout avec calculs géométriques. ~60 lignes, imbrication marquée, plusieurs sous-cas.
- **Décomposition mesurée** : fn_len_max=44, depth=4, params=3, density=33.0, id_len=6.0

### `ts_009` (typescript)

- **Attendu** : risk=75, level=`very_high`, cognitive≈34
- **Prédit**  : risk=53.6, level=`very_high`, cognitive=33
- **Δ risk** : -21.4
- **Raison annotation** : Toutes dimensions saturent : ~70 lignes, 6 paramètres, imbrication très profonde, identifiants 1 caractère, beaucoup de branches. Refactoring urgent.
- **Décomposition mesurée** : fn_len_max=50, depth=7, params=6, density=28.0, id_len=1.0

### `ts_010` (typescript)

- **Attendu** : risk=70, level=`very_high`, cognitive≈30
- **Prédit**  : risk=33.7, level=`high`, cognitive=28
- **Δ risk** : -36.3
- **Raison annotation** : Style React legacy avec multiples conditions imbriquées, gestion d'état mutable et effets de bord. ~65 lignes, hard à suivre.
- **Décomposition mesurée** : fn_len_max=55, depth=5, params=3, density=35.0, id_len=7.5

### `ts_011` (typescript)

- **Attendu** : risk=17, level=`moderate`, cognitive≈5
- **Prédit**  : risk=1.7, level=`low`, cognitive=4
- **Δ risk** : -15.3
- **Raison annotation** : Cas-frontière low/moderate : fonction de 15 lignes avec switch sur 4 cas + paramètres typés. Lisible mais demande attention au type discriminant.
- **Décomposition mesurée** : fn_len_max=11, depth=1, params=1, density=35.0, id_len=6.5

### `ts_012` (typescript)

- **Attendu** : risk=40, level=`high`, cognitive≈16
- **Prédit**  : risk=13.5, level=`moderate`, cognitive=13
- **Δ risk** : -26.5
- **Raison annotation** : Cas-frontière moderate/high : Promise chaining avec gestion d'erreurs dense. Court (~25 lignes) mais cognitivement chargé : async, race conditions, fallback. Piégeux pour le lecteur.
- **Décomposition mesurée** : fn_len_max=23, depth=3, params=4, density=38.0, id_len=8.0

### `ts_013` (typescript)

- **Attendu** : risk=19, level=`moderate`, cognitive≈5
- **Prédit**  : risk=1.5, level=`low`, cognitive=4
- **Δ risk** : -17.5
- **Raison annotation** : Cas piégeux : fonction longue (~30 lignes) mais structure linéaire bien découpée en étapes commentées, identifiants explicites. Style React component classique.
- **Décomposition mesurée** : fn_len_max=27, depth=1, params=3, density=30.0, id_len=8.0

### `ts_014` (typescript)

- **Attendu** : risk=62, level=`very_high`, cognitive≈28
- **Prédit**  : risk=27.0, level=`high`, cognitive=22
- **Δ risk** : -35.0
- **Raison annotation** : Cas-frontière high/very_high : reducer complexe avec branches imbriquées, traitement de state nested mutable, plusieurs niveaux d'action. Demande une carte mentale lourde.
- **Décomposition mesurée** : fn_len_max=46, depth=4, params=2, density=42.0, id_len=6.5

### `ts_015` (typescript)

- **Attendu** : risk=36, level=`high`, cognitive≈12
- **Prédit**  : risk=7.9, level=`low`, cognitive=9
- **Δ risk** : -28.1
- **Raison annotation** : Cas idiomatique TS : pattern observer avec generic + cleanup fonction. Pattern courant en RxJS/Zustand. Closure imbriquée, type system non trivial. Demande attention mais structure reconnaissable.
- **Décomposition mesurée** : fn_len_max=24, depth=3, params=1, density=30.0, id_len=7.5

### `java_004` (java)

- **Attendu** : risk=22, level=`moderate`, cognitive≈7
- **Prédit**  : risk=0.6, level=`low`, cognitive=4
- **Δ risk** : -21.4
- **Raison annotation** : Calcul un peu long avec quelques branches. Plat, identifiants OK, mais 25 lignes de logique séquentielle.
- **Décomposition mesurée** : fn_len_max=19, depth=1, params=3, density=32.0, id_len=7.5

### `java_005` (java)

- **Attendu** : risk=28, level=`moderate`, cognitive≈9
- **Prédit**  : risk=5.4, level=`low`, cognitive=8
- **Δ risk** : -22.6
- **Raison annotation** : Style Spring Bean, méthode de configuration avec plusieurs branches conditionnelles. Lisible mais demande attention au contexte.
- **Décomposition mesurée** : fn_len_max=26, depth=2, params=1, density=38.0, id_len=7.0

### `java_006` (java)

- **Attendu** : risk=32, level=`moderate`, cognitive≈11
- **Prédit**  : risk=14.9, level=`moderate`, cognitive=0
- **Δ risk** : -17.1
- **Raison annotation** : Méthode longue (~40 lignes) avec calculs en chaîne et variables courtes. Cognitive faible, mais lecture pénible.
- **Décomposition mesurée** : fn_len_max=19, depth=0, params=6, density=22.0, id_len=1.5

### `java_007` (java)

- **Attendu** : risk=45, level=`high`, cognitive≈18
- **Prédit**  : risk=21.7, level=`moderate`, cognitive=18
- **Δ risk** : -23.3
- **Raison annotation** : Validation avec imbrication 3-4 niveaux et branches multiples. Identifiants OK mais code dense.
- **Décomposition mesurée** : fn_len_max=32, depth=4, params=2, density=38.0, id_len=6.0

### `java_008` (java)

- **Attendu** : risk=52, level=`high`, cognitive≈22
- **Prédit**  : risk=16.9, level=`moderate`, cognitive=16
- **Δ risk** : -35.1
- **Raison annotation** : Style Eclipse JDT, parser AST simplifié avec multiples branches selon le type de token. ~55 lignes, imbrication marquée.
- **Décomposition mesurée** : fn_len_max=30, depth=3, params=0, density=32.0, id_len=6.5

### `java_009` (java)

- **Attendu** : risk=72, level=`very_high`, cognitive≈32
- **Prédit**  : risk=48.6, level=`high`, cognitive=30
- **Δ risk** : -23.4
- **Raison annotation** : Toutes dimensions dégradées : ~65 lignes, 6 paramètres, imbrication 5 niveaux, identifiants 1 caractère.
- **Décomposition mesurée** : fn_len_max=38, depth=6, params=6, density=28.0, id_len=1.5

### `java_010` (java)

- **Attendu** : risk=76, level=`very_high`, cognitive≈36
- **Prédit**  : risk=36.3, level=`high`, cognitive=28
- **Δ risk** : -39.7
- **Raison annotation** : Style legacy enterprise Java : long, imbrication profonde, gestion mixte d'état, plusieurs niveaux de boucle avec branches. Code typique à refactorer.
- **Décomposition mesurée** : fn_len_max=44, depth=5, params=5, density=42.0, id_len=8.0

### `java_011` (java)

- **Attendu** : risk=18, level=`moderate`, cognitive≈5
- **Prédit**  : risk=0.0, level=`low`, cognitive=5
- **Δ risk** : -18.0
- **Raison annotation** : Cas-frontière low/moderate : méthode courte avec switch sur enum (pattern moderne Java 17+). Lisible mais switch sur 5 cas + arrow form.
- **Décomposition mesurée** : fn_len_max=10, depth=1, params=2, density=38.0, id_len=8.0

### `java_012` (java)

- **Attendu** : risk=40, level=`high`, cognitive≈15
- **Prédit**  : risk=6.9, level=`low`, cognitive=12
- **Δ risk** : -33.1
- **Raison annotation** : Cas-frontière moderate/high : Stream API en chaîne avec collecte par groupBy + filtre + mapping. Court mais cognitivement dense (programmation fonctionnelle Java). Piégeux.
- **Décomposition mesurée** : fn_len_max=19, depth=2, params=3, density=40.0, id_len=9.5

### `java_013` (java)

- **Attendu** : risk=20, level=`moderate`, cognitive≈6
- **Prédit**  : risk=1.8, level=`low`, cognitive=5
- **Δ risk** : -18.2
- **Raison annotation** : Cas piégeux : méthode longue (~30 lignes) mais bien découpée en étapes avec commentaires. Style Spring service propre, identifiants longs et explicites. La longueur seule ne dégrade pas.
- **Décomposition mesurée** : fn_len_max=28, depth=2, params=2, density=30.0, id_len=8.0

### `java_014` (java)

- **Attendu** : risk=60, level=`high`, cognitive≈26
- **Prédit**  : risk=31.9, level=`high`, cognitive=20
- **Δ risk** : -28.1
- **Raison annotation** : Cas-frontière high/very_high : méthode de traitement transactionnel avec gestion d'exceptions imbriquée, plusieurs branches conditionnelles, rollback manuel. Code legacy enterprise typique.
- **Décomposition mesurée** : fn_len_max=48, depth=4, params=6, density=45.0, id_len=7.5

### `java_015` (java)

- **Attendu** : risk=32, level=`moderate`, cognitive≈10
- **Prédit**  : risk=2.0, level=`low`, cognitive=7
- **Δ risk** : -30.0
- **Raison annotation** : Cas idiomatique Java : Builder pattern avec validation. Long (~40 lignes) mais structure reconnaissable et linéaire. Identifiants longs et explicites. Pattern enterprise standard.
- **Décomposition mesurée** : fn_len_max=8, depth=2, params=1, density=35.0, id_len=8.5

---

*Rapport généré par `calibration/evaluate.py`.*