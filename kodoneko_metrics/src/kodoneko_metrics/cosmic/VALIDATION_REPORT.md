# Rapport de validation empirique — Phases 1, 1a, 1b

**Date :** mai 2026
**Auteur :** Benoît Moraillon

## Vue d'ensemble

Validation menée en deux temps :

1. **Python (Phase 1)** : validation empirique sur 8 archétypes exécutables dans le sandbox (Python utilise `ast` stdlib, exécution possible).
2. **JavaScript/TypeScript (Phase 1a) + Java (Phase 1b)** : revue adversariale du code des détecteurs, construction de cas-tests représentatifs, analyse mentale du flux de détection. **Tree-sitter n'étant pas installable dans le sandbox**, validation purement logique.

## Méthodologie

Pour chaque langage, on a :

1. Construit des cas-tests représentatifs (Python : 8 archétypes ; JS/Java : 5 cas chacun)
2. Calculé manuellement les CFP attendus **avant** confrontation au détecteur
3. Identifié les écarts
4. Corrigé les bugs confirmés
5. Documenté les décisions de design émergentes avec un identifiant unique

## Bugs trouvés et corrigés

### Python (Phase 1) — 4 bugs

| ID | Description | Archétype | Statut |
|---|---|---|:---:|
| 1 | Related managers Django (`cart.items.create()`) non détectés hors `.objects.` | 01 Django REST | ✅ Corrigé (D-PY6) |
| 2 | HTTP client via `async with httpx.AsyncClient()` non détecté | 02 FastAPI | ✅ Corrigé (D-PY7) |
| 3 | Double-comptage exits sur `return jsonify(), 404` | 03 Flask+Celery | ✅ Corrigé |
| 4 | Chaînes SQLAlchemy `session.query.X.first` non détectées | 03 Flask+Celery | ✅ Corrigé |

### JavaScript/TypeScript (Phase 1a) — 3 bugs

| ID | Description | Cas | Statut |
|---|---|---|:---:|
| 1 | Méthodes `res.json()`, `res.send()`, etc. non comptées comme Exit | Express | ✅ Corrigé (D-JS6) |
| 2 | Chaînes Drizzle longues (`db.select().from(t).where(eq).limit(N)`) non détectées | Drizzle | ✅ Corrigé (D-JS7) |
| 3 | HTTP client via `axios.create()` non détecté quand variable nommée `client` | axios | ✅ Corrigé (D-JS8) |

### Java (Phase 1b) — 1 bug majeur

| ID | Description | Cas | Statut |
|---|---|---|:---:|
| 1 | Spring Data JPA chaîné (`repo.findById(id).orElseThrow()`) non détecté | Spring | ✅ Corrigé (D-JAVA13) |

## Pattern commun identifié

**Les 3 langages partagent un même problème :** dans une builder API chaînée, le terminal n'est **pas** le mot-clé sémantique.

| Langage | Pattern | Fix |
|---|---|---|
| Python | `session.query(X).filter(...).first()` — terminal `.first` | Scan du root de la chaîne |
| JavaScript | `db.select().from(t).where(eq).limit(N)` — terminal `.limit` | D-JS7 : scan présence dans chaîne |
| Java | `repo.findById(id).orElseThrow()` — terminal `.orElseThrow` | D-JAVA13 : scan présence dans chaîne |

Ce pattern récurrent suggère que **toute future extension à un nouveau langage** devra prendre en compte les builder APIs chaînées dès la conception. **Recommandation pour C# et Go (phases 2a/2b)** : prévoir le scan-de-chaîne dès le premier jet, ne pas reproduire l'erreur.

## Limites identifiées (P2)

Documentées dans `DESIGN_DECISIONS.md` sections L5-L8 :

- **L5** — Tracking HTTP client en paramètre de fonction (faux négatif archétype 8)
- **L6** — aiofiles et IO async non-standard
- **L7** — pandas / polars / dask
- **L8** — Producteurs Celery, SMTP, kafka-python (symétrie avec D-JAVA6)

## Décisions de design ajoutées (du fait de la validation)

| ID | Phase | Description |
|---|---|---|
| **D-PY6** | Python | Related managers Django (`instance.relation.METHOD`) |
| **D-PY7** | Python | Tracking HTTP clients via assignation / `with` |
| **D-JS6** | JS/TS | Méthodes `res.json/send/...` détectées comme Exit |
| **D-JS7** | JS/TS | Drizzle — scan présence dans chaîne |
| **D-JS8** | JS/TS | Tracking HTTP clients via `axios.create()` etc. |
| **D-JAVA13** | Java | Spring Data JPA — scan présence dans chaîne |

Toutes documentées dans `DESIGN_DECISIONS.md` avec mécanique et justification.

## Régression

Les tests existants restent **96 passants, 0 failed** après chaque correction. Aucune régression introduite.

## Limites de la validation actuelle

**À reconnaître explicitement :**

1. **JS/TS et Java n'ont pas été validés empiriquement** dans cette session (sandbox sans tree-sitter). Les corrections sont basées sur une **revue adversariale du code** et une **analyse mentale** des cas-tests. Elles devraient être correctes, mais une validation empirique chez le client (avec tree-sitter installé) reste nécessaire.

2. **Les cas-tests JS/TS et Java sont conceptuels** — pas exécutés. Si un bug est trouvé à l'installation, le pattern de correction est maintenant établi.

3. **Aucun test ajouté pour les fixes JS/Java** dans cette session. À ajouter quand tree-sitter sera disponible.

## Recommandations pour la suite

1. **Avant tout autre langage (Phase 2a C# ou 2b Go) :** valider empiriquement JS/TS et Java sur des repos OSS réels avec tree-sitter installé.

2. **Prendre en compte le pattern « builder API chaînée » dès la conception** des nouveaux détecteurs (C#, Go, Kotlin, PHP, Ruby).

3. **Compléter L5-L8** quand un projet client réel le justifie (par exemple : si Calibrix est utilisé sur un projet Python lourd en pandas, prioriser L7).

4. **Ajouter une suite de tests d'intégration JS/Java** au moment où tree-sitter sera disponible — réutiliser les cas-tests de cette validation comme base.

## Conclusion

**Confiance dans le modèle :**

- **Python** : élevée (validation empirique + corrections de bugs réels)
- **JS/TS** : moyenne-élevée (corrections logiques mais non exécutées)
- **Java** : moyenne-élevée (correction logique, à valider sur un repo Spring réel)

Le modèle COSMIC tient la route sur les patterns canoniques des frameworks couverts. Les écarts résiduels (L5-L8) sont identifiés, documentés, et planifiés.
