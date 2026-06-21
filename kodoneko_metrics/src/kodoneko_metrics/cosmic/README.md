# kodoneko_metrics.cosmic

Mesure **COSMIC Function Points** (ISO/IEC 19761) sur du code source. Compte les mouvements de données unitaires entre le système et ses utilisateurs fonctionnels ou ses stockages persistants.

**Auteur :** Benoît Moraillon — **Licence :** AGPL-3.0

## Langages supportés

| Langage | Statut | Mécanisme |
|---|:---:|---|
| **Python** | ✅ Production | Module `ast` stdlib (zero-dep) |
| **JavaScript** | ✅ Production | tree-sitter |
| **TypeScript** | ✅ Production | tree-sitter |
| **TSX (React)** | ✅ Production | tree-sitter |
| **Java** | ✅ Production | tree-sitter |
| C# | 🚧 Phase 2a | tree-sitter |
| Go | 🚧 Phase 2b | tree-sitter |

Tree-sitter et les grammaires `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java` sont installés automatiquement avec `pip install kodoneko-metrics`. Les langages des phases futures nécessiteront `pip install kodoneko-metrics[dotnet]`, `[systems]`, etc.

## Documentation des décisions de design

Toutes les décisions de design — **pourquoi** tel pattern est détecté de telle manière, **pourquoi** tel cas est sciemment exclu — sont consolidées dans **[`DESIGN_DECISIONS.md`](DESIGN_DECISIONS.md)**.

Chaque décision a un identifiant unique :
- `D-T*` : décisions transverses (toutes phases)
- `D-PY*` : décisions Python
- `D-JS*` : décisions JavaScript / TypeScript
- `D-JAVA*` : décisions Java

Ces identifiants sont référencés dans les docstrings des modules de patterns (`patterns/python_ast.py`, `patterns/javascript.py`, `patterns/java.py`) pour traçabilité.

## Principe

COSMIC compte 4 types de **mouvements de données**, chacun valant 1 CFP (COSMIC Function Point) :

| Mouvement | Définition |
|---|---|
| `entry` | Donnée reçue depuis un utilisateur fonctionnel (HTTP request, queue message, CLI input) |
| `exit` | Donnée envoyée vers un utilisateur fonctionnel (HTTP response, publish, stdout) |
| `read` | Lecture depuis un stockage persistant (BDD, fichier, cache distribué) |
| `write` | Écriture dans un stockage persistant |

Pas de pondération de complexité. Un `cursor.execute("SELECT id FROM users")` et un `cursor.execute("WITH RECURSIVE ... complex ...")` valent tous les deux 1 CFP.

## Deux modes de comptage

| Mode | Comportement |
|---|---|
| `strict` | Aligné avec la spec ISO/IEC 19761. Les calls HTTP sortants (`requests.get`, etc.) ne sont **pas** comptés car ils ne représentent pas un mouvement vers un utilisateur fonctionnel du système. |
| `practical` (défaut) | Compte les calls HTTP sortants comme **1 Write + 1 Read** vers un EIF (External Interface File). Diverge de la spec stricte, mais reflète l'effort technique réel d'intégration. **Le mode doit être documenté dans tout rapport publié.** |

## Usage

### Analyse d'un fichier

```python
from kodoneko_metrics.cosmic import CosmicAnalyzer

analyzer = CosmicAnalyzer(mode="practical")
report = analyzer.analyze_file("src/api.py")

print(f"{report.total_cfp} CFP")
print(report.by_type)        # {'entry': 2, 'exit': 2, 'read': 3, 'write': 1}
print(report.by_framework)   # {'fastapi': 4, 'sqlalchemy': 3, 'redis': 1}
```

### Scan d'un repo

```python
from kodoneko_scanner import scan_repo_cosmic

report = scan_repo_cosmic("/path/to/repo", mode="practical")
print(f"Total : {report.total_cfp} CFP")
for fr in report.top_files(10):
    print(f"  {fr.total_cfp:3d}  {fr.path}")
```

### Delta d'un commit

```python
from kodoneko_temporal import compute_cosmic_delta_for_commit

delta = compute_cosmic_delta_for_commit("/path/to/repo", "abc123")
print(f"CFP avant : {delta.before.total_cfp}")
print(f"CFP après : {delta.after.total_cfp}")
print(f"Delta     : {delta.cfp_added:+d}")
```

### Delta entre deux versions

```python
from kodoneko_temporal import compute_cosmic_delta_for_range
from datetime import date

# Par tags
d = compute_cosmic_delta_for_range(repo, since="v1.0.0", until="v2.0.0")

# Par dates
d = compute_cosmic_delta_for_range(repo,
    since=date(2025, 1, 1), until=date(2025, 6, 30))
```

## Frameworks et bibliothèques détectés

### Python (via stdlib ast)

**Web (Entry + Exit)** : Flask `@app.route`, FastAPI `@api.get/post/...`, Django views (`(request, ...)`), retours `JsonResponse`/`HttpResponse`/`jsonify`, retours implicites pour FastAPI.

**ORM** : Django ORM (`.objects.get/filter/save/create/delete/...`), SQLAlchemy (`session.scalar/add/commit/...`), pymongo (`find_one/insert_one/...` avec heuristique de contexte).

**Cache** : Redis (`get/set/hset/zadd/...` avec heuristique tokenisée).

**Raw SQL** : `cursor.execute(SELECT/INSERT/UPDATE/DELETE/MERGE/WITH)`.

**File I/O** : `open(mode)`, `pathlib.Path.read_text/write_text`.

**HTTP client** (mode practical) : `requests`, `httpx` (avec exclusion des storage clients comme `redis_client.get`).

**Tasks/CLI** : Celery `@task`, Click `@command/group`.

### JavaScript / TypeScript / TSX (via tree-sitter)

**Backend (Entry + Exit)** :
- **Express** : `app.get/post/...`, `router.get/...`
- **Fastify** : `fastify.get/post/...`, `fastify.route(...)`
- **NestJS** : décorateurs `@Get/@Post/@Put/@Delete/@Patch/@All`, `@MessagePattern`, `@EventPattern`, `@SubscribeMessage`
- **Next.js Pages Router** : `pages/api/**/*.ts` → `export default function handler(req, res)`
- **Next.js App Router** : `app/**/route.ts` → exports nommés `GET/POST/PUT/DELETE/PATCH`
- **Remix** : `app/routes/*.ts` → exports `loader`/`action`
- **SvelteKit** : `+server.ts` → exports `GET/POST/...`

**ORM SQL** :
- **Prisma** : `prisma.<model>.findMany/findUnique/create/update/upsert/delete/...`
- **TypeORM** : `repository.find/findOne/save/insert/delete/...`, `manager.query`
- **Sequelize** : `Model.findAll/findOne/findByPk/create/destroy/...`
- **Drizzle** : `db.select/insert/update/delete`

**NoSQL** : Mongoose (`Model.find/findOne/save/create/deleteOne/...`).

**Cache** : node-redis, ioredis (mêmes patterns que Python Redis, avec heuristique tokenisée).

**HTTP client** (mode practical) : `fetch()` global, `axios.get/post/...`, `got.get/...` (avec exclusion des storage clients).

**File I/O Node.js** : `fs.readFile/writeFile`, `fs/promises`, `readFileSync/writeFileSync`, `createReadStream/createWriteStream`.

**Persistence frontend** :
- `localStorage.getItem/setItem/removeItem/clear`
- `sessionStorage.getItem/setItem/removeItem/clear`
- `document.cookie` (read et write par assignment_expression)
- IndexedDB via `idb` (`db.get/put/add/delete`)
- IndexedDB via Dexie (`table.get/put/add/where/...`)

**WebSocket** : `new WebSocket.Server`, `socket.on('message', ...)`, `socket.send/emit`.

**Queue** : BullMQ `queue.add(...)`, `new Worker(...)`.

**CLI** : Commander `program.command(...)`.

### Java (via tree-sitter)

**Spring REST controllers (Entry + Exit)** :
- `@RestController` / `@Controller` au niveau classe
- Méthodes décorées : `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`, `@RequestMapping`
- Returns implicites dans les endpoints comptés comme Exits

**Spring Data JPA (Read/Write)** :
- Heuristique préfixe sur les méthodes de repository
- Préfixes read : `find*/get*/read*/query*/count*/exists*/stream*`
- Préfixes write : `save*/insert*/update*/delete*/remove*/persist*/merge*`
- Activation : base contient `repository/repo/dao` ou se termine par `Repository/Repo/Dao/DAO`

**JPA EntityManager / Hibernate Session (Read/Write)** :
- Read : `find/getReference/createQuery/createNamedQuery/createNativeQuery/getResultList/getSingleResult`
- Write : `persist/merge/remove/refresh/flush/detach`

**JDBC (Read/Write)** :
- `PreparedStatement.executeQuery` (read), `executeUpdate` (write)
- Spring `JdbcTemplate.query/queryForObject/queryForList` (read), `update/batchUpdate` (write)

**Messaging (Entry + Exit)** :
- Entry : `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener`, `@StreamListener`
- Exit : `kafkaTemplate.send`, `rabbitTemplate.convertAndSend`, `jmsTemplate.send`

**HTTP client** (mode practical) :
- `RestTemplate.getForObject/postForObject/exchange/...`
- `WebClient.get/post/...retrieve()` (réactif)
- Java 11+ `HttpClient.send/sendAsync`
- OkHttp `call.execute/enqueue`

**Redis (Spring RedisTemplate)** : `opsForValue/opsForHash/opsForList/opsForSet/opsForZSet` + `get/set/put/leftPush/add/...`

**File I/O** :
- `Files.readString/readAllLines/readAllBytes/lines/newBufferedReader` (read)
- `Files.write/writeString/writeBytes/newBufferedWriter/createFile/delete/copy/move` (write)
- Constructeurs : `new FileReader/BufferedReader/Scanner/FileInputStream/...` (read), `new FileWriter/BufferedWriter/PrintWriter/...` (write)

**CLI** : picocli `@Command`

## Conventions de comptage

### Granularité = acte syntaxique

Un mouvement = un acte syntaxique d'I/O dans le code, peu importe la cardinalité runtime.

```python
for user_id in user_ids:                      # boucle de N itérations
    User.objects.get(id=user_id)              # = 1 read (1 acte syntaxique)
```

Cette convention est conforme à l'esprit COSMIC : on mesure le travail conceptuel livré, pas l'exécution runtime. Si l'effort de réécriture diffère (batch vs N+1), c'est mesuré ailleurs (par VTA Performance).

### Déduplication des chaînes ORM

`User.objects.filter(...).first()` compte **1 read**, pas 2. Le mouvement terminal `.first()` représente le seul acte de lecture réel.

### Returns implicites dans les routes web

Dans une fonction décorée comme route, tout `return` qui n'est pas un appel à une fonction de réponse explicite (`jsonify`, `JsonResponse`, ...) compte comme **1 exit implicite**. Permet de couvrir FastAPI/Starlette qui retournent des dicts/listes directement.

### Décorateurs ne sont pas comptés comme calls

`@app.get("/users")` : le `app.get(...)` du décorateur est ignoré par les détecteurs (sinon, faux positif HTTP client).

## Modèles d'agrégation

```python
from kodoneko_metrics.cosmic import (
    CosmicMovement,      # un mouvement individuel
    CosmicFileReport,    # tous les mouvements d'un fichier
    CosmicScanReport,    # tous les fichiers d'un scan (repo, ref git, etc.)
    CosmicDelta,         # différence entre deux CosmicScanReport
)
```

Chaque modèle expose `to_dict()` pour sérialisation JSON.

## Limites connues

### Limites de la détection automatique

- **Faux positifs résiduels** sur méthodes ambiguës (`find`, `get`, `delete`, `save`). Les heuristiques de contexte (tokens dans le nom de la base) limitent mais n'éliminent pas. La `confidence` de chaque mouvement reflète cette incertitude.
- **Frameworks rares non couverts** : Tornado, aiohttp, Bottle, CherryPy, Pyramid, peewee, Tortoise ORM, etc. Patterns extensibles dans `cosmic/patterns/python_ast.py`.
- **Code dynamique** : appels via `getattr`, `__getattr__`, `eval`, ou indirections lourdes échappent à l'analyse statique. Sous-comptage possible sur architectures très dynamiques (rare).
- **Sérialisation ORM auto** : un `User.objects.get()` qui retourne 8 attributs compte 1 read, comme un cursor SQL qui retourne 8 colonnes. La cardinalité des attributs n'est pas capturée par COSMIC (elle l'est dans le modèle TUF étendu, non implémenté ici).

### Limites du modèle COSMIC lui-même

- COSMIC mesure le **volume** de mouvements, pas la **complexité** algorithmique. C'est volontaire et c'est la philosophie de la norme.
- COSMIC ne mesure pas la **valeur technique** ajoutée à un patrimoine existant (performance, robustesse, sécurité, observabilité, etc.). Ces aspects relèvent du modèle VTA, séparé.
- Un **refactoring pur** qui ne change ni les attributs ni les frontières du système donne un delta CFP = 0. C'est volontaire.

## Performance

| Taille du repo | Temps de scan |
|---|---|
| 10 k lignes | < 100 ms |
| 100 k lignes | 1–3 secondes |
| 1 M lignes | 15–30 secondes |

Le scan d'un commit prend environ 2× le temps du scan d'un état (un avant + un après), plus le coût d'un `git worktree`. Compter ~5 secondes pour un commit sur un repo de 100k lignes.

## Tests

```bash
cd kodoneko_metrics
python run_tests.py
```

Les tests Python (`test_cosmic.py`) couvrent : web frameworks, ORM, Redis, raw SQL, file I/O, HTTP client, Celery/Click, agrégations, modes strict/practical, et un scénario intégration multi-frameworks.

Les tests JavaScript/TypeScript (`test_cosmic_js.py`) couvrent : Express, Fastify, NestJS, Next.js Pages/App Router, Remix, SvelteKit, Prisma, TypeORM, Sequelize, Drizzle, Mongoose, Redis, fetch, axios, fs, localStorage/sessionStorage/cookie, WebSocket, et un scénario intégration NestJS+Prisma+Redis. Ils se skip automatiquement si `tree-sitter-javascript`/`tree-sitter-typescript` ne sont pas installés.

## Roadmap

- ✅ **Phase 1a** (livrée) : Python, JavaScript, TypeScript, TSX
- ✅ **Phase 1b** (livrée) : Java (Spring Boot, JPA, JDBC, RestTemplate, WebClient, Spring AMQP/Kafka)
- 📋 **Phase 2a** : C# (.NET Core/ASP.NET Core, EF Core, Dapper)
- 📋 **Phase 2b** : Go (Gin, Echo, Fiber, GORM, sqlx, mongo-go-driver)
- 📋 **Phase 3** : Kotlin (réutilise Spring), PHP (Symfony, Laravel), Ruby (Rails)
- 📋 **Plus tard** : Configuration TOML `[kodoneko.cosmic]`, sortie SARIF pour CI, filtres par pattern de chemin
