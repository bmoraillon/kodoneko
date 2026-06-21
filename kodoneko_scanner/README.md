# kodoneko-scanner

**Scanner de dépôt utilisant kodoneko-metrics**

**Auteur :** Benoît Moraillon — **Licence :** AGPL-3.0 — **Version :** 0.9.0

Module Python qui parcourt un dépôt (Git ou répertoire) et applique
`kodoneko-metrics` sur chaque fichier source. Produit un **BaselineQualityScore
synthétique 0-100 + grade A-E**, des **hotspots** classés, et accepte
une **configuration TOML** pour personnaliser poids et seuils.

## Nouveautés v0.9 — Paliers de level resserrés (calibration n=45)

Suite à l'extension du dataset de calibration à 45 cas, les **paliers
de level** (qui qualifient le risk numérique en low/moderate/high/
very_high) ont été resserrés en v2.3 de kodoneko-metrics : 10/27/50
au lieu de 15/35/60.

Aucun changement d'API. Les seuils de sous-métriques (cognitive,
function_length, etc.) restent inchangés. Seule l'interprétation
qualitative du risk est plus stricte. Cf. `calibration/README.md` du
projet pour la méthode et les chiffres complets.

## Nouveautés v0.8 — Renommage BaselineScore → BaselineQualityScore

La classe ``BaselineScore`` a été renommée en ``BaselineQualityScore`` et
la fonction ``compute_baseline_score`` en ``compute_baseline_quality_score``,
afin de souligner que le score est une **note de qualité** (plus c'est
haut, mieux c'est), à l'opposé d'un score de risque.

**Migration** :

```python
# Avant (v0.7)
from kodoneko_scanner import BaselineScore, compute_baseline_score
bs = compute_baseline_score(report)

# Après (v0.8)
from kodoneko_scanner import BaselineQualityScore, compute_baseline_quality_score
bs = compute_baseline_quality_score(report)

# bs.score, bs.grade, bs.summary inchangés
```

L'attribut ``.score`` du résultat est conservé. Pour rappel, KodoNeko
distingue désormais sans ambiguïté :

| Indicateur | Orientation | Localisation |
|---|---|---|
| ``UnderstandabilityMetrics.risk`` | *Pire si plus haut* | Fichier |
| ``BaselineQualityScore.score`` | *Mieux si plus haut* | Dépôt |

## Nouveautés v0.7 — Seuils calibrés

Les **seuils par défaut d'Understandability** dans le module `config`
(et donc dans le template `kodoneko.toml` généré par `--init-config`)
ont été mis à jour pour refléter la calibration pilote effectuée en
amont. Cf. `calibration/README.md` au niveau du projet pour la méthode
et les chiffres complets.

Aucun changement d'API : si tu utilises déjà une config TOML
personnalisée, elle continue de fonctionner. Le seul changement est
le contenu du template `--init-config`.

## Nouveautés v0.6

- **Configuration via fichier TOML** : tous les poids du BaselineQualityScore,
  tous les poids des sous-métriques d'Understandability, et tous les
  seuils sont surchargeables. Format TOML (standard Python depuis
  PEP 518/621, lecture native via `tomllib` en 3.11+).
- **Nouvelle pondération par défaut du BaselineQualityScore** :
  ncloc 10 % / halstead 5 % / mccabe 15 % / **understandability 70 %**.
- **CLI enrichie** : options `--config` et `--init-config`.

### Migration depuis v0.5

| v0.4 | v0.5 |
|---|---|
| Poids défaut 10/15/30/45 | **10/5/15/70** (understandability domine) |
| Pas de config externalisée | Fichier `kodoneko.toml` optionnel |

L'API Python reste compatible : tous les appels v0.4 continuent à
fonctionner. Les changements sont purement additifs (`config=` est
optionnel partout).

## Installation

```bash
pip install kodoneko-scanner

# Ne pas oublier les grammaires tree-sitter nécessaires
pip install tree-sitter tree-sitter-python tree-sitter-typescript tree-sitter-javascript
```

## Usage Python

### Scan basique

```python
from kodoneko_scanner import scan_repo, compute_baseline_quality_score

report = scan_repo("/path/to/myproject")
bs = compute_baseline_quality_score(report)
print(f"{bs.score:.1f}/100 — grade {bs.grade}")     # 72.4/100 — grade B
```

### Avec configuration personnalisée

```python
from kodoneko_scanner import scan_repo, compute_baseline_quality_score, load_config

# Chargement auto (cherche ./kodoneko.toml ou prend les défauts)
cfg = load_config()

# Ou chargement explicite
cfg = load_config("/path/to/my-config.toml")

report = scan_repo("/path/to/repo", config=cfg)
bs = compute_baseline_quality_score(report, config=cfg)
```

### Hotspots

```python
# Tri par défaut : understandability
for f in report.hotspots(top=10, by="understandability"):
    u = f.metrics.understandability
    print(f"{f.relative_path}: risk={u.risk:.0f} ({u.level}), "
          f"cognitive={u.cognitive}")

# Autres critères disponibles : "cognitive", "mccabe", "ncloc",
# "volume", "effort"
```

## Usage CLI

```bash
# Rapport texte lisible
python -m kodoneko_scanner /path/to/repo

# Sortie JSON (pour pipelines)
python -m kodoneko_scanner /path/to/repo --json > report.json

# Filtrer par langage
python -m kodoneko_scanner /path/to/repo --languages python typescript

# Avec config personnalisée
python -m kodoneko_scanner /path/to/repo --config ./kodoneko.toml

# Générer un fichier de config commenté
python -m kodoneko_scanner --init-config > kodoneko.toml
```

## Configuration TOML

### Recherche du fichier

Sans argument explicite, le scanner cherche `kodoneko.toml` dans cet
ordre :

1. Argument CLI `--config /chemin/vers/kodoneko.toml`
2. Variable d'environnement `KODONEKO_CONFIG`
3. `./kodoneko.toml` (répertoire courant)
4. `~/.config/kodoneko/kodoneko.toml` (config utilisateur)
5. Valeurs par défaut intégrées (si rien trouvé)

### Format

Génère un template avec `python -m kodoneko_scanner --init-config`.
Extrait :

```toml
# Pondérations du BaselineQualityScore (somme = 1.0)
[baseline_score.weights]
ncloc             = 0.10
halstead          = 0.05
mccabe            = 0.15
understandability = 0.70

# Pondérations internes du score Understandability (somme = 1.0)
[understandability.weights]
cognitive         = 0.30
function_length   = 0.20
nesting_depth     = 0.15
parameter_count   = 0.15
line_density      = 0.10
identifier_length = 0.10

# Seuils des sous-métriques (low / high / very_high)
[understandability.thresholds.cognitive]
low       = 5
high      = 15
very_high = 30
```

**Config partielle** : toute section absente reprend les défauts. Tu peux
ne surcharger qu'un seul poids ou qu'un seul seuil — le reste reste
intact.

### Validation

Le chargement vérifie :

- somme des poids = 1.0 (tolérance ε)
- pas de poids négatif
- pas de clé inconnue, pas de clé manquante après merge avec les défauts
- monotonie des seuils (low < high < very_high, sauf identifier_length
  qui est inversé)

Toute violation lève une `ConfigError` parlante.

## Le BaselineQualityScore

Indicateur synthétique 0-100 + grade A-E qui résume l'état de santé
d'un dépôt.

### Pondération par défaut

| Métrique | Poids | Justification |
|---|---|---|
| `understandability` | **70 %** | Composite ISO/IEC 25010 le plus riche (6 dimensions). Reflète directement la maintenabilité ressentie. |
| `mccabe` | 15 % | Complexité cyclomatique, signal indépendant et complémentaire |
| `ncloc` | 10 % | Taille brute, utile pour repérer les fichiers démesurés |
| `halstead` | 5 % | Densité d'information, indicateur secondaire (contesté dans la littérature moderne) |

### Grades

| Score | Grade | Interprétation |
|---|---|---|
| ≥ 85 | A | Code en excellent état général |
| 70-84 | B | Code globalement sain |
| 55-69 | C | État acceptable |
| 40-54 | D | État préoccupant |
| < 40 | E | État critique |

### Commentaires de hotspots

`comment_file(file_report)` produit un verdict humain avec icône :

```
✅ Code en bonne santé (risk=12, cognitive=4, mccabe=3, ncloc=45).
ℹ️  À surveiller (risk=28, cognitive=18, mccabe=12, ncloc=120).
⚠️ Refactoring conseillé (risk=47, cognitive=35, mccabe=22, ncloc=240).
🔥 Refactoring fortement conseillé (risk=72, cognitive=58, mccabe=45, ncloc=480).
```

## Licence

**AGPL-3.0** © 2026 Benoît Moraillon.

Dépend de `kodoneko-metrics` v2.0+ (AGPL-3.0, même auteur).

## Tests

```bash
# Avec pytest
pytest

# Sans pytest (runner intégré)
python run_tests.py
```

**56 tests** au total (36 scanner + 20 config), 2 skipped sans
tree-sitter installé.
