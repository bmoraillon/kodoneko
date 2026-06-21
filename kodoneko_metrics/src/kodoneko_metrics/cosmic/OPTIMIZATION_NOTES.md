# Notes d'optimisation — v2.9.0 → v2.9.1

**Date :** mai 2026
**Auteur :** Benoît Moraillon
**Objet :** Nettoyage qualité code + robustesse, sans changement de comportement métier.

## Priorités traitées (dans l'ordre demandé)

1. ✅ Qualité code (dette, duplication)
2. ✅ Robustesse (edge cases, tests)
3. ⏸️ Précision COSMIC (non touchée — déjà à 95.2 %)
4. ⏸️ Perf (mesurée, non prioritaire)

## 1. Qualité code

### Suppression de code mort : `python.py` (-765 lignes)

Le fichier `patterns/python.py` (stub tree-sitter Python, 765 lignes) était
importé dans `analyzer.py` mais **jamais exécuté** : le dispatch passe
systématiquement par `_DETECTORS_NATIVE["python"]` (qui appelle `python_ast.py`)
avant d'atteindre `_DETECTORS_TS["python"]`.

Actions :
- Suppression de `patterns/python.py`
- Retrait de l'import et de l'entrée `_DETECTORS_TS["python"]` dans `analyzer.py`
- Correction de la référence docstring pendante dans `python_ast.py`

Impact : −765 lignes, aucune régression (le code n'était pas atteignable).

### Fusion des pré-passes AST (3 passes → 2)

Les détecteurs JS/TS et Java effectuaient **trois traversées complètes** de
l'AST :
1. Marquage des décorateurs/annotations à skip
2. Identification des body de fonctions endpoint (D-JS9 / D-JAVA14)
3. Passe principale de détection

Les passes (1) et (2) sont indépendantes de la passe principale et peuvent
être fusionnées en une seule traversée.

Actions :
- JS/TS : `_mark_decorator_calls` + `_collect_endpoint_method_bodies`
  → `_prepass` (une seule fonction, une seule descente)
- Java : `_mark_annotation_calls` + `_collect_endpoint_method_bodies_java`
  → `_prepass_java` + helper `_collect_endpoint_bodies_in_class`

Impact : −33 % de traversées AST sur JS/Java (3→2). Réduit le coût sur les
gros fichiers proportionnellement.

### Centralisation des constantes véritablement transverses

`HTTP_VERBS` (get/post/put/delete/patch/head/options/request) était dupliqué
identiquement entre `python_ast.py` (`HTTP_CLIENT_METHODS`) et `javascript.py`
(`HTTP_METHODS_LIB`).

Action : définition unique `HTTP_VERBS` dans `_common.py`, référencée par les
deux détecteurs.

**Choix délibéré de NON-centralisation :** les whitelists d'exceptions HTTP
(NESTJS_HTTP_EXCEPTIONS, SPRING_HTTP_EXCEPTIONS, HTTP_EXCEPTION_CLASSES) ne
sont PAS centralisées car elles sont spécifiques à chaque framework. Les
mutualiser créerait un faux couplage (les noms de classes NestJS n'ont rien
à voir avec ceux de Spring ou Werkzeug).

## 2. Robustesse

### 9 tests d'edge cases ajoutés (`TestPythonRobustness`)

Verrouillage de la dégradation gracieuse du détecteur Python sur :
- Fichier vide / commentaires uniquement
- Erreur de syntaxe (→ 0 CFP, pas de crash)
- Imbrication profonde (20 niveaux) — read détecté
- Identifiants unicode (café, résumé)
- Opérateur walrus `:=` dans une route
- Fonctions imbriquées (read dans inner())
- Générateurs async
- Lambda avec appel ORM

Un de ces tests a révélé une subtilité saine : le détecteur traite une
indentation malformée comme non-parsable (0 CFP) plutôt que de deviner —
comportement correct et désormais verrouillé.

## 3. Précision COSMIC

Non touchée. Le coefficient ×1.05 (95.2 % du compte FUR sur 13 exemples
manuel) reste valable : aucune logique de détection métier n'a été modifiée.

## 4. Performance

Mesurée pour référence : ~40 ms pour 200 routes Python (×10 runs). Le path
Python utilise `ast` stdlib (non affecté par la fusion des pré-passes, qui
ne concerne que JS/Java via tree-sitter). Non prioritaire selon le classement.

## Bilan

| Métrique | Avant | Après |
|---|---|---|
| Lignes de code (patterns/) | 4606 | ~3850 |
| Fichiers patterns | 6 | 5 |
| Passes AST (JS/Java) | 3 | 2 |
| Tests kodoneko_metrics | 106 | 115 |
| Constantes HTTP dupliquées | 2 copies | 1 source |
| Comportement métier | — | inchangé |

**Aucune régression.** 327 tests passing (115 + 56 + 156). Notebook 07 : 21/21.

---

# Validation sur repos publics réels (v2.9.2 → v2.9.3)

Tests menés sur du vrai code open-source (et non plus seulement des exemples
canoniques contrôlés). A révélé 3 bugs réels d'heuristique, tous corrigés.

## Repos testés

| Repo | Langage | Verdict |
|---|---|---|
| spring-petclinic-rest | Java | Atypique (3 implémentations du domaine) + bug OpenAPI |
| spring-projects/spring-petclinic | Java | Bug repository injecté sous nom métier → corrigé |
| fastapi/full-stack-fastapi-template | Python + TS | Bugs render + sequelize → corrigés |

## Bugs corrigés

### D-JAVA2 fix — repository injecté sous nom métier

`private final OwnerRepository owners;` puis `this.owners.findById(...)`.
L'heuristique exigeait le mot "repository" dans le NOM de variable. Or le
pattern idiomatique Spring nomme le champ d'après le métier (`owners`, `vets`).

Fix : la pré-passe Java collecte les champs/paramètres dont le TYPE finit par
Repository/Repo/Dao (`collector.repository_vars`), et D-JAVA2 accepte les
appels sur ces variables. Validé sur PetClinic canonique : OwnerController
passe de 19 à 24 CFP, les 4 appels ORM (findById ×2, save ×2) + 1 query method
dérivée (findByLastNameStartingWith) tous détectés.

### D-PY11 fix — `render()` ambigu (Django vs Jinja2/template engine)

`Template(s).render(content)` (Jinja2, email templating) était compté comme
exit Django. Or Django render() est une FONCTION nue dont le 1er arg est
`request` ; Jinja2 render() est une MÉTHODE (chain avec point).

Fix : pour `render`, si la chaîne contient un point → méthode template engine,
ignorée. Si appel nu → exiger `request` comme 1er argument (signature Django).
Validé : Template().render() → 0, render(request,...) → 1 exit django.

### D-JS10 fix — verbes Sequelize ambigus (create/update/save)

`RouteImport.update({...})` dans `routeTree.gen.ts` (TanStack Router généré)
était compté comme write Sequelize. L'heuristique "base capitalisée = Model"
est trop faible pour les verbes courants (update/create/save existent sur
des configs de route, factories, builders).

Fix : séparation méthodes distinctives (findAll, findByPk, bulkCreate, upsert,
destroy, findOrCreate — base capitalisée suffit) vs ambiguës (create, update,
save, count, sum, min, max, scope — exigent un token sequelize/model/db dans
la base). Validé : RouteImport.update() → 0, models.User.create() → 1 write.

## Découvertes non-bug

- **SQLModel passe par le détecteur SQLAlchemy** : `session.get/add/exec` captés
  via la couche SQLAlchemy sous-jacente. Pas de détecteur dédié nécessaire.
- **PetClinic-rest = 3 implémentations** (JDBC + JPA + Spring Data JPA) du même
  domaine : le total gonflé n'était pas un bug mais une particularité du repo.
  Leçon : pour calibrer, choisir un repo à une seule couche de persistance.

## Limites restantes (non corrigées, documentées)

- **Controllers OpenAPI** (`implements XxxApi` avec annotations HTTP sur
  l'interface générée) : non détectés. Analyse inter-fichiers requise. À traiter
  si scan de projets générés depuis OpenAPI (L-OAPI, P2).
- **Mongoose create/save ambigus** : même classe de problème que D-JS10 mais
  non observé en pratique. Les méthodes distinctives Mongoose (findById,
  updateOne, deleteOne...) couvrent l'essentiel. À resserrer si faux positif
  constaté.
- **Fichiers générés** (*.gen.ts, *.gen.js) et tests analysés comme code normal
  (L4). Mitigation : excluded_dirs au niveau scan. Un filtre exclude_globs
  natif serait un plus (non implémenté).

---

# v2.9.3 → v2.9.4 : OpenAPI controllers + exclusions par défaut

## L-OAPI fix — Controllers à interface OpenAPI générée

Découvert sur spring-petclinic-rest : `class OwnerRestController implements OwnersApi`
où les annotations HTTP (@GetMapping, etc.) sont sur l'interface `OwnersApi`
générée depuis la spec OpenAPI, pas sur le controller. Résultat : `entry:1`
sur tout le repo (aucun endpoint détecté).

Fix (heuristique, confidence medium) : si une classe est @RestController/
@Controller ET implémente une interface dont le nom finit par "Api"/"Controller",
alors les méthodes publiques @Override retournant ResponseEntity<...> sont
traitées comme endpoints.

Helpers ajoutés :
- `_implements_openapi_interface` : inspecte super_interfaces, cherche suffixe Api/Controller
- `_is_openapi_endpoint_method` : @Override + retour ResponseEntity
- `_iter_type_identifiers` : parcours robuste des type_identifier

Limite assumée : on ne peut PAS connaître le verbe HTTP exact (GET vs POST)
ni la route sans lire l'interface générée (analyse inter-fichiers, hors scope
Calibrix). On compte 1 Entry + les Exits du corps, en `spring_openapi_impl`,
confidence medium. Le throw detection (D-JAVA14) fonctionne aussi dans ces
méthodes (body enregistré dans endpoint_method_bodies).

## Exclusions par défaut (Option A — déterministe)

Problème : `scan_repo_cosmic` avait un set d'exclusion inline plus pauvre que
`DEFAULT_EXCLUDED_DIRS`, forçant l'utilisateur à passer excluded_dirs à la main.
De plus, les fichiers générés (*.gen.ts) et tests polluaient le comptage.

Fix (source unique de vérité, tout déterministe et inspectable) :
- `DEFAULT_EXCLUDED_DIRS` enrichi (34 répertoires : ajout .svelte-kit, .angular,
  vendor, out, .gradle, bower_components, .yarn, site-packages...)
- `DEFAULT_TEST_DIRS` (nouveau) : test, tests, __tests__, spec, e2e, fixtures...
- `DEFAULT_EXCLUDED_FILE_GLOBS` (nouveau, 25 patterns) : *.gen.ts, *.min.js,
  *.test.ts, test_*.py, *Tests.java, *_pb2.py...
- `scan_repo_cosmic` : nouveaux paramètres `excluded_file_globs` et
  `include_tests=False`. Source unique (plus de duplication inline).

Choix de conception : exclusions DÉTERMINISTES, jamais d'heuristique silencieuse
(option C rejetée). Les constantes sont publiques et inspectables ; le rapport
liste les fichiers exclus (motif "excluded:file_glob"). Essentiel pour un audit
COSMIC formel : on peut toujours expliquer pourquoi un fichier n'est pas compté.

`include_tests=True` réintègre tests/specs (pour mesurer l'effort de test).

---

# v2.10.0 → v2.10.1 : passe qualité/robustesse sur l'analyse enrichie

Cible : les modules `analysis_report.py` et `table_formatter.py` (écrits
rapidement lors de l'implémentation de l'intervalle de confiance).
Aucun changement de comportement métier.

## Qualité

- **Imports hissés** : `re` et `dataclasses` au niveau module (étaient
  importés à chaque appel de fonction).
- **Constantes au niveau module** : regex PascalCase compilée une fois
  (`_PASCAL_RE`), set de bruit OOI gelé (`_OOI_NOISE`), suffixes de data
  group (`_DATA_GROUP_SUFFIX`) — au lieu d'être reconstruits par appel.
- **`_is_error_confirmation` promu en fonction module** : utilisé à la fois
  par `FunctionalProcessView` et par l'inférence des data groups ; le
  staticmethod de la classe délègue (rétrocompat conservée).
- **Enrichissement en une passe** : `analyze_enriched` faisait deux
  `dataclasses.replace` par mouvement (OOI/DG puis nom du FP). Fusionné en
  un seul replace — moitié moins d'objets créés.
- **Accents réparés** dans `render_repo_markdown` (texte inséré par script
  en ASCII lors de la création).

## Robustesse

6 tests d'edge cases ajoutés (`TestRobustness` dans test_analysis_report) :
fichier vide, FP préambule (mouvement avant tout Entry), excerpt unicode,
syntaxe invalide, rendu sur analyse vide, label d'intervalle exact.
Tous dégradent gracieusement (0 CFP, jamais de crash).

## Performance (mesure, non prioritaire)

`analyze_enriched` sur 200 FP à returns multiples : ~7,6 ms — négligeable
face au parsing (~40 ms). Pas d'optimisation nécessaire.

## Bilan

| Métrique | Avant | Après |
|---|---|---|
| Tests kodoneko_metrics | 125 | 131 |
| Tests totaux | 337 | 343 |
| Replace par mouvement | 2 | 1 |
| Regex/sets par appel | recréés | module-level |
| Comportement métier | — | inchangé |
