# Rapport de calibration KodoNeko

**Date :** 2026-05-18 04:31 UTC
**Configuration :** `defaults v2.3/v0.9 (paliers level resserrés 10/27/50 — adoption finale)`
**Dataset :** 45 cas annotés (45 évalués avec succès)

## Résumé global

| Métrique | Valeur | Objectif | Statut |
|---|---|---|---|
| Accord catégoriel (niveau) | 75.6% | ≥ 70 % | ✓ |
| RMSE sur risk (0-100) | 12.7 | ≤ 15 | ✓ |
| Corrélation Spearman | 0.968 | ≥ 0.80 | ✓ |
| Biais signé moyen | -11.2 | — | sous-estime |
| Distance moyenne en rang | 0.24 | ≤ 0.5 | ✓ |

## Par langage

| Langage | n | Accord | RMSE | Biais | Spearman |
|---|---|---|---|---|---|
| python | 15 | 86.7% | 12.2 | -10.3 | 0.950 |
| typescript | 15 | 66.7% | 11.6 | -10.5 | 0.982 |
| java | 15 | 73.3% | 14.0 | -12.7 | 0.969 |

## Matrice de confusion (niveaux)

Lignes = niveau **attendu**, colonnes = niveau **prédit par KodoNeko**.
Les valeurs sur la diagonale (`▣`) sont les bonnes prédictions.

| Attendu \ Prédit | low | moderate | high | very_high |
|---|---|---|---|---|
| **low** | 9 ▣ | 0 | 0 | 0 |
| **moderate** | 6 | 11 ▣ | 0 | 0 |
| **high** | 0 | 3 | 9 ▣ | 0 |
| **very_high** | 0 | 0 | 2 | 5 ▣ |

## Détail par cas

| ID | Lang | Attendu (level/risk) | Prédit (level/risk) | Δ risk | Statut |
|---|---|---|---|---|---|
| java_001 | jav | low / 5 | low / 0.6 | -4.4 | ✓ |
| java_002 | jav | low / 10 | low / 2.7 | -7.3 | ✓ |
| java_003 | jav | low / 14 | low / 5.0 | -9.0 | ✓ |
| java_004 | jav | moderate / 22 | low / 7.2 | -14.8 | ✗ (moderate→low) |
| java_005 | jav | moderate / 28 | moderate / 19.2 | -8.8 | ✓ |
| java_006 | jav | moderate / 32 | moderate / 19.2 | -12.8 | ✓ |
| java_007 | jav | high / 45 | high / 37.6 | -7.4 | ✓ |
| java_008 | jav | high / 52 | high / 31.3 | -20.7 | ✓ |
| java_009 | jav | very_high / 72 | very_high / 61.1 | -10.9 | ✓ |
| java_010 | jav | very_high / 76 | very_high / 52.6 | -23.4 | ✓ |
| java_011 | jav | moderate / 18 | low / 5.3 | -12.7 | ✗ (moderate→low) |
| java_012 | jav | high / 40 | moderate / 20.6 | -19.4 | ✗ (high→moderate) |
| java_013 | jav | moderate / 20 | moderate / 13.4 | -6.6 | ✓ |
| java_014 | jav | high / 60 | high / 49.7 | -10.3 | ✓ |
| java_015 | jav | moderate / 32 | low / 9.5 | -22.5 | ✗ (moderate→low) |
| py_001 | pyt | low / 3 | low / 1.1 | -1.9 | ✓ |
| py_002 | pyt | low / 8 | low / 2.9 | -5.1 | ✓ |
| py_003 | pyt | low / 12 | low / 4.9 | -7.1 | ✓ |
| py_004 | pyt | moderate / 22 | moderate / 16.1 | -5.9 | ✓ |
| py_005 | pyt | moderate / 28 | moderate / 23.3 | -4.7 | ✓ |
| py_006 | pyt | moderate / 32 | moderate / 22.8 | -9.2 | ✓ |
| py_007 | pyt | high / 45 | high / 37.3 | -7.7 | ✓ |
| py_008 | pyt | high / 50 | high / 46.1 | -3.9 | ✓ |
| py_009 | pyt | very_high / 72 | very_high / 59.6 | -12.4 | ✓ |
| py_010 | pyt | very_high / 78 | very_high / 56.1 | -21.9 | ✓ |
| py_011 | pyt | moderate / 16 | low / 5.4 | -10.6 | ✗ (moderate→low) |
| py_012 | pyt | high / 38 | moderate / 16.3 | -21.7 | ✗ (high→moderate) |
| py_013 | pyt | moderate / 18 | moderate / 11.5 | -6.5 | ✓ |
| py_014 | pyt | high / 58 | high / 36.8 | -21.2 | ✓ |
| py_015 | pyt | moderate / 33 | moderate / 18.1 | -14.9 | ✓ |
| ts_001 | typ | low / 4 | low / 1.1 | -2.9 | ✓ |
| ts_002 | typ | low / 10 | low / 4.8 | -5.2 | ✓ |
| ts_003 | typ | low / 14 | low / 3.2 | -10.8 | ✓ |
| ts_004 | typ | moderate / 24 | moderate / 15.7 | -8.3 | ✓ |
| ts_005 | typ | moderate / 30 | moderate / 23.9 | -6.1 | ✓ |
| ts_006 | typ | moderate / 34 | moderate / 25.8 | -8.2 | ✓ |
| ts_007 | typ | high / 48 | high / 43.4 | -4.6 | ✓ |
| ts_008 | typ | high / 55 | high / 38.1 | -16.9 | ✓ |
| ts_009 | typ | very_high / 75 | very_high / 67.4 | -7.6 | ✓ |
| ts_010 | typ | very_high / 70 | high / 49.5 | -20.5 | ✗ (very_high→high) |
| ts_011 | typ | moderate / 17 | low / 5.5 | -11.5 | ✗ (moderate→low) |
| ts_012 | typ | high / 40 | high / 27.8 | -12.2 | ✓ |
| ts_013 | typ | moderate / 19 | low / 9.2 | -9.8 | ✗ (moderate→low) |
| ts_014 | typ | very_high / 62 | high / 44.3 | -17.7 | ✗ (very_high→high) |
| ts_015 | typ | high / 36 | moderate / 20.9 | -15.1 | ✗ (high→moderate) |

## Cas problématiques (|Δ risk| > 15)

### `py_010` (python)

- **Attendu** : risk=78, level=`very_high`, cognitive≈38
- **Prédit**  : risk=56.1, level=`very_high`, cognitive=32
- **Δ risk** : -21.9
- **Raison annotation** : Style legacy Python 2 numerical code : 80 lignes, double boucle imbriquée avec conditions branchées, beaucoup de variables courtes, expressions denses. Code typique à refactorer.
- **Décomposition mesurée** : fn_len_max=39, depth=6, params=2, density=30.0, id_len=1.5

### `py_012` (python)

- **Attendu** : risk=38, level=`high`, cognitive≈14
- **Prédit**  : risk=16.3, level=`moderate`, cognitive=10
- **Δ risk** : -21.7
- **Raison annotation** : Cas-frontière moderate/high : list comprehension imbriquée non triviale, double itération, condition non évidente. Court mais cognitivement dense (piégeux).
- **Décomposition mesurée** : fn_len_max=12, depth=2, params=3, density=35.0, id_len=7.0

### `py_014` (python)

- **Attendu** : risk=58, level=`high`, cognitive≈24
- **Prédit**  : risk=36.8, level=`high`, cognitive=18
- **Δ risk** : -21.2
- **Raison annotation** : Cas-frontière high/very_high : context manager async avec gestion d'erreurs en cascade, plusieurs niveaux d'imbrication, identifiants OK mais densité visuelle élevée.
- **Décomposition mesurée** : fn_len_max=34, depth=4, params=3, density=32.0, id_len=6.5

### `ts_008` (typescript)

- **Attendu** : risk=55, level=`high`, cognitive≈26
- **Prédit**  : risk=38.1, level=`high`, cognitive=16
- **Δ risk** : -16.9
- **Raison annotation** : Style VSCode renderer, machine à état pour layout avec calculs géométriques. ~60 lignes, imbrication marquée, plusieurs sous-cas.
- **Décomposition mesurée** : fn_len_max=44, depth=4, params=3, density=33.0, id_len=6.0

### `ts_010` (typescript)

- **Attendu** : risk=70, level=`very_high`, cognitive≈30
- **Prédit**  : risk=49.5, level=`high`, cognitive=28
- **Δ risk** : -20.5
- **Raison annotation** : Style React legacy avec multiples conditions imbriquées, gestion d'état mutable et effets de bord. ~65 lignes, hard à suivre.
- **Décomposition mesurée** : fn_len_max=55, depth=5, params=3, density=35.0, id_len=7.5

### `ts_014` (typescript)

- **Attendu** : risk=62, level=`very_high`, cognitive≈28
- **Prédit**  : risk=44.3, level=`high`, cognitive=22
- **Δ risk** : -17.7
- **Raison annotation** : Cas-frontière high/very_high : reducer complexe avec branches imbriquées, traitement de state nested mutable, plusieurs niveaux d'action. Demande une carte mentale lourde.
- **Décomposition mesurée** : fn_len_max=46, depth=4, params=2, density=42.0, id_len=6.5

### `ts_015` (typescript)

- **Attendu** : risk=36, level=`high`, cognitive≈12
- **Prédit**  : risk=20.9, level=`moderate`, cognitive=9
- **Δ risk** : -15.1
- **Raison annotation** : Cas idiomatique TS : pattern observer avec generic + cleanup fonction. Pattern courant en RxJS/Zustand. Closure imbriquée, type system non trivial. Demande attention mais structure reconnaissable.
- **Décomposition mesurée** : fn_len_max=24, depth=3, params=1, density=30.0, id_len=7.5

### `java_008` (java)

- **Attendu** : risk=52, level=`high`, cognitive≈22
- **Prédit**  : risk=31.3, level=`high`, cognitive=16
- **Δ risk** : -20.7
- **Raison annotation** : Style Eclipse JDT, parser AST simplifié avec multiples branches selon le type de token. ~55 lignes, imbrication marquée.
- **Décomposition mesurée** : fn_len_max=30, depth=3, params=0, density=32.0, id_len=6.5

### `java_010` (java)

- **Attendu** : risk=76, level=`very_high`, cognitive≈36
- **Prédit**  : risk=52.6, level=`very_high`, cognitive=28
- **Δ risk** : -23.4
- **Raison annotation** : Style legacy enterprise Java : long, imbrication profonde, gestion mixte d'état, plusieurs niveaux de boucle avec branches. Code typique à refactorer.
- **Décomposition mesurée** : fn_len_max=44, depth=5, params=5, density=42.0, id_len=8.0

### `java_012` (java)

- **Attendu** : risk=40, level=`high`, cognitive≈15
- **Prédit**  : risk=20.6, level=`moderate`, cognitive=12
- **Δ risk** : -19.4
- **Raison annotation** : Cas-frontière moderate/high : Stream API en chaîne avec collecte par groupBy + filtre + mapping. Court mais cognitivement dense (programmation fonctionnelle Java). Piégeux.
- **Décomposition mesurée** : fn_len_max=19, depth=2, params=3, density=40.0, id_len=9.5

### `java_015` (java)

- **Attendu** : risk=32, level=`moderate`, cognitive≈10
- **Prédit**  : risk=9.5, level=`low`, cognitive=7
- **Δ risk** : -22.5
- **Raison annotation** : Cas idiomatique Java : Builder pattern avec validation. Long (~40 lignes) mais structure reconnaissable et linéaire. Identifiants longs et explicites. Pattern enterprise standard.
- **Décomposition mesurée** : fn_len_max=8, depth=2, params=1, density=35.0, id_len=8.5

---

*Rapport généré par `calibration/evaluate.py`.*