# Décisions de design — kodoneko_metrics.cosmic

Ce document consolide les décisions de design prises pour le module de mesure COSMIC, par phase de livraison. Il sert de référence pour comprendre **pourquoi** tel pattern est détecté de telle manière, et **pourquoi** tel cas ne l'est pas.

**Auteur :** Benoît Moraillon — **Licence :** AGPL-3.0

---

## Décisions transverses (toutes phases)

### D-T1 : tree-sitter obligatoire (pas de fallback regex)

**Décision :** tree-sitter et les grammaires sont dans les dépendances obligatoires de `kodoneko-metrics`. Pas de fallback regex.

**Justification :**
- Un fallback regex serait beaucoup moins fiable (faux positifs sur strings, commentaires, code mort)
- Doublerait la maintenance (deux implémentations à garder en phase)
- Crédibilité moindre : un auditeur qui voit "fallback regex" doute de la mesure
- Le poids combiné des wheels (~30 MB) est négligeable face aux gains de précision

**Exception :** Python utilise le module `ast` de la stdlib (pas tree-sitter), pour ne pas imposer une dépendance à un utilisateur qui ne ferait que de l'analyse Python.

### D-T2 : Mode `practical` divergent de l'ISO

**Décision :** par défaut, le mode `practical` compte les calls HTTP sortants comme **1 Write + 1 Read** (vers un EIF). La spec ISO/IEC 19761 stricte n'aurait pas compté.

**Justification :**
- Reflète l'effort technique réel d'intégration (parsing de la réponse, gestion d'erreur, retry, timeout)
- En pratique, les calls HTTP sortants représentent une part majeure du travail d'intégration moderne
- Le mode `strict` reste disponible pour les besoins de conformité ISO formelle
- **Le mode utilisé doit être documenté dans tout rapport publié**

### D-T3 : Granularité = acte syntaxique, pas runtime

**Décision :** un mouvement = un acte syntaxique d'I/O dans le code, peu importe la cardinalité runtime.

```python
for user_id in user_ids:                      # boucle de N itérations
    User.objects.get(id=user_id)              # = 1 read, pas N reads
```

**Justification :**
- Conforme à l'esprit COSMIC : on mesure le travail conceptuel livré, pas l'exécution
- Mesurable de façon déterministe par analyse statique (pas d'exécution requise)
- Les questions de performance (N+1, batch) relèvent du modèle **VTA Performance**, séparé

### D-T4 : Refactoring pur = delta CFP = 0

**Décision :** un refactoring qui ne change ni les attributs ni les frontières du système donne un delta COSMIC nul. Volontaire.

**Justification :**
- COSMIC mesure le travail fonctionnel, pas le travail technique d'amélioration
- L'amélioration patrimoniale est mesurée par le modèle **VTA** (Valeur Technique Ajoutée)
- Confondre les deux nuirait à l'interprétabilité

### D-T5 : Confidence levels

**Décision :** chaque mouvement détecté a un niveau de confiance (`high`, `medium`, `low`).

**Justification :**
- Certaines méthodes ont des noms ambigus (`find`, `get`, `delete`, `save`)
- Les heuristiques de contexte (tokens dans le nom de la base) limitent mais n'éliminent pas les faux positifs
- Le niveau de confiance permet à l'utilisateur de filtrer (ex: ne garder que `high` pour un audit conservateur)

---

## Phase 1 — Python (livré en v2.4.0)

### D-PY1 : Détecteur via `ast` stdlib (pas tree-sitter)

**Décision :** Python utilise le module `ast` de la stdlib, pas tree-sitter.

**Justification :**
- Zero-dépendance pour les utilisateurs Python-only
- `ast` est plus rapide que tree-sitter pour Python (~3-5x)
- Précision identique : `ast` parse exactement la même grammaire que CPython lui-même

### D-PY2 : Déduplication des chaînes ORM

**Décision :** `User.objects.filter(...).first()` compte **1 read**, pas 2.

**Justification :**
- Le mouvement terminal `.first()` représente le seul acte de lecture réel
- Compter `filter()` séparément double-comptabiliserait

**Mécanique :** quand on visite le Call externe (`.first()`), on marque le Call enfant (`.filter(...)`) comme « inner chain » à skipper.

### D-PY3 : Décorateurs ne sont pas comptés

**Décision :** `@app.route("/users")` : le `app.route(...)` du décorateur est ignoré par les détecteurs.

**Justification :**
- Sinon, faux positif HTTP client (`app.route` matcherait les méthodes web)
- Le décorateur n'est pas un mouvement de données, c'est une déclaration de mapping

**Mécanique :** pré-passe sur l'AST qui marque tous les Call enfants d'un Decorator node, puis skip à la détection.

### D-PY4 : Returns implicites comptés comme Exit dans les routes web

**Décision :** dans une fonction décorée comme route web, tout `return` qui n'est pas un appel à une fonction de réponse explicite (`jsonify`, `JsonResponse`, ...) compte comme **1 exit implicite**.

**Justification :**
- FastAPI/Starlette retournent souvent des dicts/listes directement (`return {"id": 1}`)
- Sans cette règle, ces endpoints n'auraient pas d'Exit alors qu'ils en font un
- Convention médium-confidence pour signaler la nature heuristique

### D-PY5 : Méthodes ambiguës pymongo / Redis requièrent un contexte

**Décision :** `find/get/set/delete` ne sont détectés qu'avec un indice contextuel (nom de la base contenant `redis`, `mongo`, `cache`, etc.).

**Justification :**
- Sans contexte, `text.find("{")` serait faussement détecté comme `pymongo.find`
- Le contexte est imparfait mais nécessaire pour éviter trop de faux positifs

**Exception :** méthodes très spécifiques (`hgetall`, `zadd`, `find_one`, `insert_one`) sont détectées même sans contexte explicite — leur nom est suffisamment distinctif.

### D-PY6 : Related managers Django (`instance.relation.METHOD`)

**Décision :** dans le contexte d'une vue Django (fonction avec `request` comme 1er param), détecter les appels `cart.items.create(...)`, `user.orders.filter(...)`, etc. comme Django ORM (medium confidence).

**Justification :**
- Découvert lors de la validation empirique sur archétype 1 (e-commerce Django REST)
- Les relations Foreign Key inverses (`related_manager` Django) sont extrêmement courantes et ne passent **pas** par `Model.objects`
- Sans cette détection : faux négatifs significatifs sur tout code Django utilisant des relations

**Mécanique :** le visiteur tracke `_django_view_depth` lorsqu'il entre dans une fonction avec `request` comme 1er param (sans décorateur Flask/FastAPI/Celery/Click). Dans ce contexte, les chaînes à 2+ niveaux (`foo.bar.METHOD`) sont matchées contre les listes ORM read/write.

**Garde-fou :** le matching n'a lieu **que** dans le contexte vue Django identifié. Hors de ce contexte, les chaînes `foo.bar.METHOD` ne déclenchent pas la détection (évite les faux positifs dans des classes/services arbitraires).

**Détecteurs émis :** suffixe `_related` (ex: `django_orm_create_related`) pour distinguer du pattern `Model.objects.X` classique.

### D-PY7 : Tracking d'instances de clients HTTP via assignation / `with`

**Décision :** détecter les variables qui contiennent un client HTTP par leur instanciation (`httpx.AsyncClient()`, `httpx.Client()`, `requests.Session()`, `aiohttp.ClientSession()`) et les utiliser pour valider ensuite `<var>.get/post/...` comme HTTP client.

**Justification :**
- Découvert lors de la validation empirique sur archétype 2 (FastAPI microservice).
- Pattern moderne `async with httpx.AsyncClient() as client: await client.post(...)` est très courant.
- Sans tracking : faux négatifs systématiques sur tous les usages chaînés par `with`.

**Mécanique :**
- Visitor `visit_Assign` : si la valeur est `Call(httpx.AsyncClient)` ou similaire, ajouter la cible Name à `_http_client_vars`.
- Visitors `visit_With` / `visit_AsyncWith` : si un item utilise une factory HTTP, ajouter l'`optional_vars` au set.
- Lors de la détection HTTP, si la racine de la base (`base.split(".")[0]`) est dans `_http_client_vars`, émettre directement la paire Write+Read.

**Limitation assumée :** analyse de flot intra-fichier seulement. Si le client est créé dans un autre module et passé en paramètre, il n'est pas tracké. C'est acceptable pour les patterns idiomatiques courants.

**Factories reconnues :**
- `httpx.AsyncClient`, `httpx.Client`
- `requests.Session`
- `aiohttp.ClientSession`
- `AsyncClient` (forme courte importée — très spécifique à httpx)

### D-PY8 : `session.flush()` et `session.commit()` non comptés comme Write distinct

**Décision :** `session.flush()` et `session.commit()` (SQLAlchemy) ne sont PAS comptés comme mouvements de données distincts.

**Justification :**
- **Découvert lors de la validation contre exemples manuel COSMIC (section 2.1.4).**
- Ces deux méthodes sont des **opérations transactionnelles** qui persistent les writes déjà déclarés via `add()`, `delete()`, `merge()`. Compter `commit()` après `add()` double-comptabilise le même write fonctionnel.
- Cohérent avec D-T3 (acte syntaxique unique) : `session.add(x); session.flush(); session.commit()` représente UN write fonctionnel.

**Avant la correction :** un code typique `add(order); flush(); commit()` comptait 3 writes → sur-comptage de 200%.

**Après :** seul `add()` est compté → 1 write fonctionnel.

### D-PY9 : `session.get(Model, pk)` comme Read SQLAlchemy

**Décision :** `session.get(Entity, pk)` est compté comme Read SQLAlchemy, **uniquement si appel à 2+ arguments**.

**Justification :**
- **Découvert lors de la validation contre exemples manuel COSMIC (section 2.1.6).**
- Raccourci SQLAlchemy 1.4+ pour lookup par primary key, équivalent moderne à `session.query(Model).get(pk)`.
- Très courant en code idiomatique moderne (FastAPI + SQLAlchemy 2.x).
- Sans cette détection : faux négatifs systématiques sur les patterns de validation par ID.

**Garde-fous :**
- Root de la chaîne doit être `session`, `Session`, ou `db` (cohérent avec autres détecteurs SQLAlchemy).
- **Exiger 2+ arguments** (`session.get(Model, pk)`), pour éviter les faux positifs sur `aiohttp.ClientSession().get(url)` ou `requests.Session().get(url)` qui ont une signature à 1 arg.
- Si la variable racine est tracée comme HTTP client via D-PY7, skip immédiat.

**Limitation assumée :** la signature legacy SQLAlchemy 0.x `session.query(Model).get(pk)` (un seul arg sur `.get`) n'est plus détectée. Cas rare en code moderne (acceptable).

### D-PY10 : Error messages HTTP (raise/abort) comptés comme Exit

**Décision :** dans le contexte d'une fonction identifiée comme endpoint web, détecter `raise HTTPException(...)`, `raise Http404(...)`, `abort(400, ...)`, et autres patterns d'exception HTTP comme **1 Exit error** par functional process (frequency rule COSMIC).

**Justification :**
- **Découvert lors de la validation contre exemples manuel COSMIC (sections 2.1.3, 2.1.4, 2.1.6).**
- Le manuel COSMIC compte systématiquement 1 Exit pour les error/confirmation messages dans chaque functional process.
- Sans cette détection : gap structurel d'environ 15 % sous le compte FUR officiel (L9 documentée précédemment).
- L'ajout de D-PY10 a fait passer Calibrix de 77 % à **93.5 %** de coverage sur les 5 exemples canoniques testés.

**Mécanique :**
- Pile `_endpoint_func_stack` : suit l'imbrication des fonctions endpoint via `visit_FunctionDef`/`visit_AsyncFunctionDef`.
- Visitor `visit_Raise` : si l'exception est dans `HTTP_EXCEPTION_CLASSES` et qu'on est dans un endpoint, émettre Exit.
- Set `_endpoint_error_emitted` (frequency rule) : 1 seul Exit error par endpoint, même si plusieurs raises.
- Fonction `_detect_http_abort` : détecte `abort(400, ...)` Flask de la même manière.

**Liste blanche `HTTP_EXCEPTION_CLASSES` :**
- FastAPI/Starlette : `HTTPException`, `RequestValidationError`, `WebSocketException`
- Django : `Http404`, `PermissionDenied`, `SuspiciousOperation`, etc.
- Werkzeug/Flask : `BadRequest`, `NotFound`, `Forbidden`, etc. (~25 classes)

**Garde-fous :**
- **Contexte endpoint requis** : sans `_endpoint_func_stack` non-vide, `raise X` est ignoré. Évite les faux positifs sur les `raise ValueError` d'utilitaires internes.
- **Frequency rule stricte** : un endpoint avec 3 raises HTTP émet quand même **1 seul** Exit error (conformément au manuel COSMIC section 2.6.1).
- **Confidence medium** : reflète l'incertitude sur la qualité de la détection d'endpoint (heuristiques de décorateurs et de signatures).

**Impact mesuré sur les 5 exemples du manuel :**

| Exemple | Avant D-PY10 | Après D-PY10 |
|---|:---:|:---:|
| 2.1.3 Employee enquiry (FUR 5) | 3 | 4 |
| 2.1.4 Multi-item order (FUR 7) | 6 | 7 |
| 2.1.6 Update FP1+FP2+FP3 (FUR 11) | 9 | 12 |
| 2.2.3 Sales by category (FUR 4) | 3 | 3 |
| 3.1.1 Simple enquiry (FUR 4) | 3 | 3 |
| **Total** | **24/31 = 77 %** | **29/31 = 93.5 %** |

**Coefficient de calibration empirique :** passé de **×1.27** à **×1.07**.

---

## Phase 1a — JavaScript / TypeScript (livré en v2.5.0)

### D-JS1 : Détecteur partagé JS/TS/TSX

**Décision :** un seul détecteur `patterns/javascript.py` couvre `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`.

**Justification :**
- TypeScript = JavaScript + annotations de type
- La structure AST tree-sitter est compatible (mêmes noeuds `call_expression`, `member_expression`, etc.)
- Économie de code et facilité de maintenance

### D-JS2 : React state / Redux / Zustand non comptés

**Décision :** `useState`, `useReducer`, store Redux, store Zustand → **0 CFP**.

**Justification :**
- Ce sont des états in-memory, non persistants
- COSMIC ne mesure que les mouvements vers/depuis utilisateurs ou stockages persistants
- Conséquence assumée : les frontends purs (excalidraw, figma-clone) seront sous-comptés

**Compté à la place :**
- `localStorage`, `sessionStorage`, `document.cookie` (persistance navigateur)
- IndexedDB via `idb`, Dexie
- `fetch`, `axios`, WebSocket (mouvements réseau)

### D-JS3 : Routes file-based détectées par chemin + signature

**Décision :** détection des routes Next.js/Remix/SvelteKit par convention de fichier.

**Conventions reconnues :**

| Framework | Chemin | Signature détectée |
|---|---|---|
| Next.js Pages | `pages/api/**/*.ts` | `export default function handler(req, res)` |
| Next.js App | `app/**/route.ts` | exports nommés `GET`, `POST`, `PUT`, `DELETE`, `PATCH` |
| Remix | `app/routes/*` | exports `loader`, `action` |
| SvelteKit | `+server.ts` | exports `GET`, `POST`, etc. |

**Justification :**
- Ces frameworks sont devenus standards (Next.js seul = ~30-40 % des projets TS modernes)
- Sans cette détection, ils donneraient 0 CFP sur leur partie routing

**Mécanique :** la détection lit le `file_path` passé à `analyze_file`, le normalise (slash), et matche contre les patterns. La signature complète l'identification.

### D-JS4 : Décorateurs NestJS détectés au niveau classe

**Décision :** pour NestJS, on parcourt les `method_definition` enfants d'une `class_declaration` et on cherche les décorateurs frères précédents.

**Justification :**
- En tree-sitter-typescript, les décorateurs apparaissent comme frères précédents de la méthode dans le body de la classe
- Détection séparée nécessaire car la structure diffère de Python

### D-JS5 : HTTP client tokenisation contextuelle

**Décision :** la base d'un appel est tokenisée (par séparateurs + camelCase) avant matching contre les listes de tokens HTTP positifs/négatifs.

**Exemple :**
```javascript
redisClient.get(...)   // base="redisClient" → tokens={redisclient, redis, client} → STORAGE → skip HTTP
axiosClient.get(...)   // base="axiosClient" → tokens={axiosclient, axios, client} → HTTP_POSITIVE (axios) → comptez
```

**Justification :**
- Évite les faux positifs sur les storage clients (`redisClient`, `mongoClient`, etc.) qui ont aussi des méthodes `get`/`set`
- Heuristique simple et robuste

### D-JS6 : Méthodes de réponse Express détectées comme Exit

**Décision :** détecter `res.json(...)`, `res.send(...)`, `res.status(N).json(...)`, `res.redirect(...)`, `res.render(...)`, etc. comme Exit quand la racine de la chaîne est `res`, `response`, `reply`, ou `ctx`.

**Justification :**
- **Découvert lors de la revue adversariale JS/TS.** Sans cette détection, **aucun endpoint Express n'a d'Exit** dans le compte COSMIC.
- Express utilise un style callback (`(req, res) => { res.json(...) }`) sans return explicit comme FastAPI/NestJS.
- Cohérent avec D-JS3 (routes file-based où l'on compte les returns).

**Mécanique :** dans `_detect_call`, si le terminal est dans `EXPRESS_RESPONSE_METHODS` et la racine de la chaîne est dans `EXPRESS_RESPONSE_BASE_TOKENS`, émettre un Exit. Retourne `True` pour éviter d'évaluer les autres détecteurs sur le même node.

**Méthodes reconnues :** json, send, sendFile, sendStatus, end, redirect, render, download, jsonp, type, format.

### D-JS7 : Drizzle ORM — détection sur présence dans la chaîne

**Décision :** pour Drizzle ORM, classifier la chaîne en fonction de la **présence** d'un mot-clé Drizzle (`select`, `insert`, `update`, `delete`) dans la chaîne, pas en fonction du terminal.

**Justification :**
- **Découvert lors de la revue adversariale JS/TS.** Drizzle utilise une builder API très chaînée :
  ```typescript
  await db.select().from(users).where(eq(users.id, 1)).limit(10);
  ```
- Le terminal est `.limit(10)`, qui n'est pas un mot-clé Drizzle.
- Sans ce fix : chaînes Drizzle non détectées.

**Mécanique :** dans `_detect_drizzle`, après vérification du contexte (root = `db` ou `tx`), parcourir les segments de la chaîne et émettre le mouvement basé sur le **premier** mot-clé trouvé (le plus proche de la racine).

### D-JS8 : Tracking de HTTP client factories (équivalent D-PY7)

**Décision :** détecter `const xxx = axios.create({...})` et marquer la variable comme HTTP client, pour bypass les heuristiques tokenisées lors de calls `xxx.get(url)`.

**Justification :**
- **Découvert lors de la revue adversariale JS/TS.** Pattern moderne :
  ```typescript
  const apiClient = axios.create({ baseURL: '...' });
  const client = axios.create();  // ❌ token "client" seul = ambigu → rejet
  ```
- Sans tracking, le pattern `const client = axios.create()` puis `client.get(...)` n'est pas détecté.

**Mécanique :**
- Visitor `variable_declarator` : si la valeur est `Call` à une factory dans `HTTP_CLIENT_FACTORY_CALLS`, ajouter le nom de la variable à `MovementCollector.http_client_vars`.
- Lors de la détection HTTP, si la racine de la chaîne est dans `http_client_vars`, accepter directement.

**Factories reconnues :** `axios.create`, `got.extend`, `ky.create`, `ky.extend`.

**Limitation assumée :** intra-fichier seulement (mêmes limites que D-PY7 Python).

### D-JS9 : Error messages HTTP NestJS (throw HttpException) comptés comme Exit

**Décision :** dans le contexte d'une méthode endpoint NestJS (décorée `@Get`, `@Post`, etc.) ou d'un handler Express (`app.get('/path', handler)`), détecter `throw new BadRequestException(...)`, `throw new NotFoundException(...)`, etc. comme **1 Exit error par endpoint** (frequency rule COSMIC).

**Justification :**
- Équivalent de D-PY10 pour JS/TS.
- Sans cette détection, **aucun endpoint NestJS avec exception ne reçoit d'Exit error** dans le compte COSMIC.
- Le manuel COSMIC compte systématiquement 1 Exit error/confirmation par functional process.
- Pour Express, le pattern courant `res.status(400).json({...})` est déjà détecté par D-JS6 ; mais les patterns `throw` dans NestJS et `next(error)` ne sont pas détectés sans D-JS9.

**Mécanique :**
- **Pré-passe** `_collect_endpoint_method_bodies` : identifie les body de :
  - Méthodes NestJS décorées (`@Get`, `@Post`, `@Put`, etc.)
  - Handlers Express/Fastify (2e arg d'un `app.get('/path', handler)`)
  - Routes file-based Next.js/Remix/SvelteKit
- Stocke leurs node IDs dans `collector.endpoint_method_bodies`.
- **Main pass** `_detect_http_throw` : si `throw new XxxException(...)` :
  - extrait le nom de classe (gère les imports qualifiés `common.BadRequestException` → `BadRequestException`)
  - vérifie qu'il est dans `NESTJS_HTTP_EXCEPTIONS` (22 classes)
  - remonte la chaîne parent pour trouver le `statement_block` englobant
  - si ce block est dans `endpoint_method_bodies`, émet **1 Exit** avec frequency rule via `endpoint_error_emitted`.

**Liste blanche `NESTJS_HTTP_EXCEPTIONS` (22 classes) :**
- Base : `HttpException`
- Standard : `BadRequestException`, `UnauthorizedException`, `NotFoundException`, `ForbiddenException`, `NotAcceptableException`, `RequestTimeoutException`, `ConflictException`, `GoneException`, `PayloadTooLargeException`, `UnsupportedMediaTypeException`, `UnprocessableEntityException`, `InternalServerErrorException`, `NotImplementedException`, `BadGatewayException`, `ServiceUnavailableException`, `GatewayTimeoutException`
- Variantes : `HttpVersionNotSupportedException`, `MethodNotAllowedException`, `PreconditionFailedException`, `MisdirectedException`, `ImATeapotException`

**Garde-fous :**
- Contexte endpoint requis : `throw X` hors endpoint = ignoré (évite faux positifs sur services métier).
- Whitelist explicite : `throw new Error()` ou `throw new ValueError()` ignorés.
- Frequency rule stricte : 3 throws = 1 Exit (conforme manuel COSMIC).
- Confidence medium.

**Limitations assumées :**
- Exceptions custom non standard NestJS (héritant ou non de `HttpException`) ne sont pas détectées. Mitigation P2 : reconnaître les classes ayant une `extends HttpException` chaîne.
- Express `next(error)` non détecté (rare en pratique, Express utilise plutôt `res.status(...)`).

---

## Phase 1b — Java (livré en v2.6.0)

### D-JAVA1 : Détection au niveau méthode, pas au niveau interface

**Décision :** pour Spring Data JPA et autres, on détecte les **appels** (`repository.findByEmail(...)`), pas les déclarations d'interface.

**Justification :**
- Cohérent avec les autres détecteurs (Python ORM, TypeORM, Mongoose)
- Une interface déclarée mais jamais appelée ne fait pas de mouvement réel
- Évite l'analyse de signature complexe (génériques, héritage de Repository, etc.)

### D-JAVA2 : Préfixes de méthodes pour Spring Data JPA

**Décision :** une méthode dont le nom commence par un préfixe Spring Data JPA est classée selon ce préfixe.

| Préfixe | Type | Exemples |
|---|---|---|
| `find`, `get`, `read`, `query`, `count`, `exists`, `stream` | **read** | `findByEmail`, `getById`, `countByActive`, `existsByEmail` |
| `save`, `insert`, `update`, `delete`, `remove`, `persist` | **write** | `saveAll`, `deleteByEmail`, `updateName` |

**Justification :**
- Convention Spring Data JPA bien établie et documentée
- Permet de détecter les méthodes dérivées (`findByXxx`) sans inspecter leur déclaration
- Risque résiduel de faux positif (ex: `findById` sur un Map → mais une Map ne s'appelle pas typiquement `repository` ou similaire)

**Contexte requis :** la base de l'appel doit ressembler à un repository (tokens incluant `repository`, `repo`, `dao`).

### D-JAVA3 : Détection des Controllers par annotation au niveau classe

**Décision :** une méthode est un endpoint Spring **si** :
- Sa classe porte `@RestController` ou `@Controller`
- ET la méthode porte `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`, ou `@RequestMapping`

**Justification :**
- Les méthodes avec `@GetMapping` peuvent exister dans une classe non-controller (rare mais possible)
- L'annotation classe est la marque sûre

**Limite assumée :** les controllers qui héritent d'une classe abstraite annotée peuvent être manqués. Cas rare dans Spring moderne.

### D-JAVA4 : EntityManager / Session détectés par contexte

**Décision :** `find`, `persist`, `merge`, `remove`, `createQuery` détectés si la base contient un token parmi `entityManager`, `em`, `session`, `getEntityManager`.

**Justification :**
- Ces méthodes sont génériques (`find` existe partout)
- Le contexte est nécessaire pour discriminer
- `em` est très courant comme nom de variable EntityManager dans la communauté Java

### D-JAVA5 : Listeners Kafka/RabbitMQ/JMS/SQS comptés comme Entry

**Décision :** une méthode annotée `@KafkaListener`, `@RabbitListener`, `@JmsListener`, ou `@SqsListener` compte comme **1 Entry**.

**Justification :**
- Cohérent avec NestJS `@MessagePattern`/`@EventPattern` (Phase 1a)
- Le message broker est l'utilisateur fonctionnel du système
- Les returns dans ces méthodes ne sont pas comptés comme Exit (un listener Kafka ne « retourne » pas typiquement à l'utilisateur)

### D-JAVA6 : Producteurs Kafka/RabbitMQ comptés comme Exit

**Décision :** `kafkaTemplate.send(...)`, `rabbitTemplate.convertAndSend(...)`, `jmsTemplate.send(...)` comptent comme **1 Exit**.

**Justification :**
- Mouvement de données vers utilisateur fonctionnel externe (broker)
- Symétrique de D-JAVA5 (Entry pour consumer = Exit pour producer)

### D-JAVA7 : JDBC `execute` ambigu → medium confidence

**Décision :**
- `preparedStatement.executeQuery()` → **read**, high
- `preparedStatement.executeUpdate()` → **write**, high
- `preparedStatement.execute()` → **write**, medium (peut être SELECT ou UPDATE selon SQL)

**Justification :**
- `execute()` est polymorphe en JDBC : peut exécuter n'importe quel SQL
- Sans parsing du string SQL passé, on classe par défaut en write (cas plus fréquent dans `execute()` standalone)
- Le medium confidence permet à l'utilisateur de filtrer si besoin

### D-JAVA8 : Spring Cache (`@Cacheable`) non compté

**Décision :** les annotations `@Cacheable`, `@CacheEvict`, `@CachePut` **ne sont pas** des mouvements COSMIC.

**Justification :**
- Le cache est transparent côté code applicatif
- Compter `@Cacheable` doublonerait le mouvement réel (l'appel à `redisTemplate.get` interne fait par le proxy Spring)
- L'utilisateur qui veut « mesurer le cache » doit compter les opérations `redisTemplate.opsForValue().get/set/...` directement

### D-JAVA9 : Spring Batch reporté à P2

**Décision :** les patterns Spring Batch (`ItemReader`, `ItemWriter`, `Tasklet`) sont **reportés**.

**Justification :**
- Spring Batch a un modèle conceptuel à part (job, step, chunk)
- Moins courant dans les projets Spring Boot modernes (souvent remplacé par Spring Cloud Data Flow ou des architectures event-driven)
- Si demandé en production, on ajoutera en P2

### D-JAVA10 : HTTP client — RestTemplate, WebClient, HttpClient (Java 11+)

**Décision :** détecter `RestTemplate.getForObject/postForObject/exchange/...`, `WebClient.get().uri(...).retrieve()`, `HttpClient.send(...)`, OkHttp `client.newCall(request).execute()`.

**Justification :**
- Trois clients HTTP majeurs en écosystème Java moderne
- WebClient (réactif) a une chaîne d'appels chainée, on compte au site `.retrieve()` ou `.exchange()`
- OkHttp est utilisé hors Spring (Android, libs)

**Mode** : appliqué uniquement en mode `practical`, conformément à D-T2.

### D-JAVA11 : File I/O — NIO Files + Reader/Writer

**Décision :** détecter `Files.readString/readAllLines/readAllBytes/write/writeString`, et la création de `BufferedReader/Writer`, `FileReader/Writer`.

**Justification :**
- `Files` (NIO) est l'API moderne recommandée
- Les Reader/Writer existent encore beaucoup dans le code legacy
- On ne compte pas les `Stream` (`Files.lines(...)`) qui sont juste de l'ouverture — un lambda derrière fera les actes réels

### D-JAVA12 : picocli `@Command` compté comme Entry (P1)

**Décision :** une méthode annotée `@Command` (picocli) compte comme **1 Entry** CLI.

**Justification :**
- picocli est le framework CLI standard de Spring Shell
- Cohérent avec Click (Python) et Commander (JS)

### D-JAVA13 : Spring Data JPA — détection sur présence dans la chaîne

**Décision :** pour Spring Data JPA, chercher un préfixe JPA (`find`, `save`, etc.) n'importe où dans la chaîne, pas seulement au terminal.

**Justification :**
- **Découvert lors de la revue adversariale Java.** Patterns modernes très courants :
  ```java
  User user = repo.findById(id).orElseThrow();
  List<User> active = repo.findAll().stream().toList();
  ```
- Le terminal `.orElseThrow()` ou `.toList()` n'est pas un préfixe JPA.
- Sans ce fix : chaînes Spring Data JPA chaînées non détectées.

**Mécanique :**
- Reconstruire la chaîne complète via `_reconstruct_java_chain` (noms de méthodes sans arguments).
- Parcourir les segments et émettre le mouvement basé sur le **premier** préfixe JPA trouvé.
- Contexte requis inchangé : la base doit être un Repository.

**Cohérence transverse :** analogue à D-JS7 (Drizzle) et au fix Python sur SQLAlchemy `session.query.X.first`. Tous trois résolvent le même problème : **terminal ≠ sémantique** dans une builder API chaînée.

---

### D-JAVA14 : Error messages HTTP Spring/JAX-RS (throw ResponseStatusException) comptés comme Exit

**Décision :** dans le contexte d'une méthode endpoint Spring (`@RestController/@Controller` + `@GetMapping`/etc.) ou listener (`@KafkaListener`, etc.), détecter `throw new ResponseStatusException(...)`, `throw new WebApplicationException(...)`, et autres exceptions HTTP Spring/JAX-RS comme **1 Exit error par endpoint** (frequency rule COSMIC).

**Justification :**
- Équivalent de D-PY10 (Python) et D-JS9 (NestJS) pour Java.
- Sans cette détection, **aucun endpoint Spring/JAX-RS avec exception ne reçoit d'Exit error** dans le compte COSMIC.
- Le manuel COSMIC compte systématiquement 1 Exit error/confirmation par functional process.

**Mécanique :**
- **Pré-passe** `_collect_endpoint_method_bodies_java` : identifie les body des méthodes :
  - Controllers Spring (`@RestController`/`@Controller` + `@XxxMapping`)
  - Listeners (`@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener`, `@StreamListener`, `@EventListener`)
- Stocke leurs node IDs dans `collector.endpoint_method_bodies`.
- **Main pass** `_detect_http_throw_java` : si `throw new XxxException(...)` :
  - extrait le nom de classe (gère qualifié `org.springframework.web.server.ResponseStatusException` → `ResponseStatusException`)
  - gère les génériques : `XxxException<...>` → `XxxException`
  - vérifie qu'il est dans `SPRING_HTTP_EXCEPTIONS` (26 classes)
  - remonte la chaîne parent pour trouver le `block` englobant
  - si ce block est dans `endpoint_method_bodies`, émet **1 Exit** avec frequency rule via `endpoint_error_emitted`.

**Liste blanche `SPRING_HTTP_EXCEPTIONS` (26 classes) :**
- **Spring Web** : `ResponseStatusException`
- **Spring REST client** : `HttpClientErrorException`, `HttpServerErrorException`, `RestClientResponseException`, `UnknownContentTypeException`
- **Spring Web validation** : `MethodArgumentNotValidException`, `MissingServletRequestParameterException`, `HttpMessageNotReadableException`, `HttpRequestMethodNotSupportedException`, `HttpMediaTypeNotSupportedException`, `ServletRequestBindingException`, `MissingPathVariableException`, `NoHandlerFoundException`
- **JAX-RS / Jakarta REST** : `WebApplicationException`, `ClientErrorException`, `ServerErrorException`, `BadRequestException`, `ForbiddenException`, `NotAcceptableException`, `NotAllowedException`, `NotAuthorizedException`, `NotFoundException`, `NotSupportedException`, `RedirectionException`, `InternalServerErrorException`, `ServiceUnavailableException`

**Garde-fous :**
- Contexte endpoint requis : `throw X` dans `@Service` ou `@Component` non-listener = ignoré.
- Whitelist explicite : `throw new IllegalArgumentException()`, `throw new RuntimeException()` ignorés (même dans un endpoint).
- Frequency rule stricte : 3 throws = 1 Exit.
- Confidence medium.

**Limitations assumées :**
- Exceptions custom annotées `@ResponseStatus(HttpStatus.X)` non détectées. Mitigation P2 : pré-passe pour collecter les classes ayant cette annotation et étendre la whitelist dynamiquement.
- Listeners qui throw une exception spécifique au broker (rare en pratique) : si la classe n'est pas dans la whitelist, ignorée. Pour Kafka/Rabbit, c'est correct car ces brokers gèrent les erreurs au niveau infrastructure.
- Spring `@ExceptionHandler` au niveau controller : non capturé. L'analyse statique d'un dispatch d'exception est hors scope P1.

---

## Limites communes assumées

### L1 : Code dynamique non capturé

Les appels via `getattr`, `reflection`, `Class.forName`, `Method.invoke`, `eval`, ou indirection lourde échappent à l'analyse statique. Sous-comptage possible sur architectures très dynamiques (rare en pratique sur du code applicatif standard).

### L2 : Sérialisation auto non comptée

Un `User.objects.get()` qui retourne 8 attributs compte **1 read**, comme un cursor SQL qui retourne 8 colonnes. La cardinalité des attributs n'est pas capturée par COSMIC. Elle l'est dans le modèle **TUF** étendu (non implémenté ici).

### L3 : Frameworks rares non couverts

Tornado, aiohttp, Bottle (Python) ; Koa, Hapi, Hono (JS) ; Micronaut, Quarkus, Helidon (Java) ne sont pas dans P1. Ajoutables à la demande dans les fichiers de patterns existants.

### L4 : Tests unitaires comptés comme code normal

Les fichiers `test_*.py`, `*.test.ts`, `*Test.java` sont analysés comme du code normal. Conséquence : un test qui mocke un repository générera des mouvements (faux positifs du point de vue « effort fonctionnel »).

**Mitigation :** filtrer les fichiers de test au niveau de `scan_repo_cosmic` via `excluded_dirs` ou un futur paramètre `exclude_tests=True`.

### L5 : Tracking de clients HTTP en paramètres de fonction (D-PY7 limitation)

**Découvert lors de la validation empirique (archétype 8).** Le tracking des clients HTTP via D-PY7 fonctionne pour les variables locales (`client = httpx.AsyncClient()`) et les `with`/`async with` au niveau le plus externe (`async with aiohttp.ClientSession() as session`). Mais si un client est **passé en paramètre** à une autre fonction, le tracking ne le suit pas :

```python
async def fetch_url(session, url):           # session est un paramètre
    async with session.get(url) as resp:     # NON détecté comme HTTP
        ...

async def main():
    async with aiohttp.ClientSession() as session:
        await fetch_url(session, "https://a.com")
```

**Justification :** une analyse inter-procédurale (type inference, taint analysis) doublerait la complexité du détecteur. Pour P1, on accepte ce faux négatif sur le pattern « factory + helper functions ». Mitigation possible en P2 : analyse de signature avec annotations de types Python (PEP 484+).

### L6 : aiofiles, aiocsv, et IO async non-standard

**Découvert lors de la validation empirique (archétype 8).** Les libs async d'I/O fichier (`aiofiles.open`, `aiocsv.AsyncReader`, etc.) ne sont pas détectées. Seul `open()` builtin et `pathlib.Path.read_text/write_text/...` le sont.

**Mitigation prévue (P2) :** ajouter `aiofiles.open` et `anyio.Path` à la liste des patterns file I/O. Effort estimé : ~15 minutes.

### L7 : Bibliothèques d'analyse de données (pandas, polars, dask) non couvertes

**Découvert lors de la validation empirique (archétype 4 — ETL Pandas).** Les opérations pandas suivantes ne sont **pas** comptées :

| Opération pandas | Mouvement COSMIC réel | Détecteur P1 |
|---|---|---|
| `pd.read_csv(path)` | Read fichier | ❌ Non |
| `pd.read_sql(query, conn)` | Read DB | ❌ Non |
| `pd.read_parquet(path)` | Read fichier | ❌ Non |
| `df.to_csv(path)` | Write fichier | ❌ Non |
| `df.to_sql(table, conn)` | Write DB | ❌ Non |
| `df.to_parquet(path)` | Write fichier | ❌ Non |

**Mitigation prévue (P2) :** ajouter une liste explicite de méthodes pandas/polars/dask reconnues, avec contexte (1er argument est un path ou un objet connexion). Effort estimé : ~30 minutes.

### L8 : Producteurs Celery, dispatch SMTP, et autres mouvements non-HTTP

**Découvert lors de la validation empirique (archétype 3 — Flask + Celery).** Les patterns suivants ne sont **pas** détectés actuellement :

- `task.delay(...)` ou `task.apply_async(...)` (dispatch Celery) → devrait être Exit
- `smtp.send_message(...)` (envoi SMTP) → devrait être Exit  
- Producteurs Kafka/RabbitMQ en Python (à l'inverse de Java où c'est couvert)

**Mitigation prévue (P2) :** symétriser avec D-JAVA6 (producteurs Kafka/Rabbit). Effort estimé : ~45 minutes pour couvrir Celery + smtplib + kafka-python + pika.

### L9 : Error/confirmation messages — résolu pour Python, JS/TS, Java

**Résolu par D-PY10, D-JS9, D-JAVA14** (validation manuel COSMIC v0.3.6 + v0.3.8).

Le manuel COSMIC compte systématiquement 1 Exit par functional process pour les error/confirmation messages. En code idiomatique moderne, ces messages sont émis via :
- Python : `raise HTTPException(...)` (FastAPI), `abort(...)` (Flask), `raise Http404` (Django)
- JS/TS : `throw new BadRequestException()` (NestJS), `res.status(400).json(...)` (Express, déjà D-JS6)
- Java : `throw new ResponseStatusException(...)` (Spring), `throw new WebApplicationException()` (JAX-RS)

**Statut par langage :**

| Langage | Status | Décision | Whitelist |
|---|---|---|---|
| Python | ✅ Résolu | D-PY10 | HTTP_EXCEPTION_CLASSES (~30 classes) |
| JavaScript/TypeScript | ✅ Résolu | D-JS9 | NESTJS_HTTP_EXCEPTIONS (22 classes) |
| Java | ✅ Résolu | D-JAVA14 | SPRING_HTTP_EXCEPTIONS (26 classes) |

**Approche transverse** : pré-passe pour identifier les body des fonctions endpoint, puis détection des `raise`/`throw` avec frequency rule (1 Exit error par endpoint). Confidence medium dans les 3 cas.

**Limitations communes (P2) :**
- Exceptions custom héritant de la base (`HttpException`, `ResponseStatusException`, etc.) non détectées
- Express `next(error)` non capturé (rare en moderne)
- Spring `@ResponseStatus` sur classe custom non capturé

### L10 : Frequency rule sur la structure des objets retournés

**Découvert lors de la validation contre exemples manuel COSMIC (sections 2.2.3, 3.1.1).**

COSMIC distingue plusieurs Exits dans un même output si les data groups ont des **frequencies of occurrence** différentes. Exemple typique :

```python
return {
    "period": {"start": d1, "end": d2},          # 1 occurrence
    "sales_per_category": [{...}, {...}, {...}], # N occurrences (1 par catégorie)
    "total_sales": {...},                         # 1 occurrence (différente clé)
}
```

Le manuel compte ici **3 Exits** (frequency rule + key attributes distincts). Calibrix voit **1 Exit** (un seul `return`).

**Décision :** ne pas implémenter d'analyse de structure de dict pour P1. Justifications :
- L'analyse demande une inférence sémantique difficile (savoir que `sales_per_category` est une liste vient soit du type hint, soit du contenu — pas toujours présent)
- Risque élevé de faux positifs (sur-décomposition de dicts qui ne représentent pas des data groups COSMIC distincts)
- Le code source ne porte pas l'intention COSMIC : un développeur peut structurer son JSON librement

**Conséquence :** **gap structurel d'environ -1 CFP par functional process complexe** (avec output multi-niveau) par rapport au compte FUR COSMIC.

**Mitigation (P3) possible :** détecter les `return {key: [...], ...}` où une valeur est une liste/collection identifiable → +1 Exit par sous-collection détectée. Approche prudente nécessaire pour éviter sur-comptage.

### L11 : Pattern `setattr(obj, ...)` + `commit()` non détecté comme Write

**Découvert lors de la validation contre exemples manuel COSMIC (section 2.1.6 FP3).**

En SQLAlchemy ORM, modifier un objet déjà chargé puis commit est un Write fonctionnel :

```python
employee = session.get(Employee, employee_id)     # Read détecté
employee.name = "New Name"                         # Modification non détectée
setattr(employee, "department", "Sales")           # Modification non détectée
session.commit()                                    # Non compté (D-PY8)
# → Calibrix voit 1 Read mais 0 Write, alors qu'il y a bien 1 Write fonctionnel
```

**Justification du non-fix :** détecter ce pattern nécessite une analyse de flot qui suit la durée de vie de l'objet `employee`, ce qui sort du périmètre P1.

**Mitigation (P3) possible :** si une variable est issue de `session.get/scalar/query.X.first()` et qu'on observe `commit()` (ou sortie de fonction sans `add()` explicite après modification d'attributs), inférer un Write avec medium confidence. Complexe : à différer.

---

---

## Roadmap

- ✅ **Phase 1** (v2.4.0) : Python
- ✅ **Phase 1a** (v2.5.0) : JavaScript, TypeScript, TSX
- ✅ **Phase 1b** (v2.6.0) : Java
- 🚧 **Phase 2a** : C# (ASP.NET Core, EF Core, Dapper)
- 📋 **Phase 2b** : Go (Gin, Echo, GORM)
- 📋 **Phase 3** : Kotlin (réutilise Spring), PHP (Symfony, Laravel), Ruby (Rails)
