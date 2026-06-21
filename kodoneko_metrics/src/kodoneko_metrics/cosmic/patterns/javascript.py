"""
Patterns COSMIC pour JavaScript et TypeScript.

Détecte les mouvements de données via tree-sitter (grammaires tree-sitter-javascript
et tree-sitter-typescript). Le détecteur JS est utilisé pour les deux langages,
TypeScript étant un sur-ensemble syntaxique compatible.

Frameworks couverts (P1)
------------------------
**Backend** : Express, NestJS, Fastify, Next.js (Pages + App Router), Remix, SvelteKit
**ORM SQL** : Prisma, TypeORM, Sequelize, Drizzle
**NoSQL** : Mongoose
**Cache** : node-redis, ioredis
**HTTP client** : fetch, axios, got, node-fetch
**Queue** : BullMQ, Bull
**WebSocket** : ws, socket.io
**Frontend persistence** : localStorage, sessionStorage, document.cookie, IndexedDB (idb, Dexie)
**File I/O** : fs, fs/promises
**CLI** : Commander, Yargs

Décisions de design JS/TS
--------------------------
Voir ``DESIGN_DECISIONS.md`` pour la justification complète. Référentiel
d'identifiants des décisions appliquées dans ce module :

  D-JS1 : Détecteur partagé JS/TS/TSX
          TypeScript = JS + annotations de types. Même AST tree-sitter
          (call_expression, member_expression, decorator). Économie de code
          et facilité de maintenance.

  D-JS2 : React state / Redux / Zustand NON comptés
          useState, useReducer, store Redux/Zustand → 0 CFP car états
          in-memory non persistants. Conséquence assumée : frontends
          purs (Excalidraw, figma-clone) sous-comptés.
          Compté à la place : localStorage, sessionStorage, document.cookie,
          IndexedDB (idb, Dexie), fetch, axios, WebSocket.

  D-JS3 : Routes file-based détectées par chemin + signature
          Next.js Pages : pages/api/**/*.ts + export default handler(req, res)
          Next.js App   : app/**/route.ts + exports nommés GET/POST/PUT/...
          Remix         : app/routes/* + exports loader/action
          SvelteKit     : +server.ts + exports GET/POST/...

  D-JS4 : Décorateurs NestJS détectés au niveau classe
          On parcourt les method_definition enfants d'une class_declaration
          et on cherche les décorateurs frères précédents (différent de
          Python où le décorateur est dans decorator_list).

  D-JS5 : HTTP client — tokenisation contextuelle
          La base d'un appel est tokenisée (séparateurs + camelCase) avant
          matching. Évite les faux positifs sur redisClient.get,
          mongoClient.get, etc. (storage clients).
          Tokens HTTP_STORAGE_TOKENS = exclusion.
          Tokens HTTP_POSITIVE_TOKENS = inclusion.

  D-JS6 : Méthodes de réponse Express détectées comme Exit
          (Ajouté lors de la revue adversariale JS/TS.)
          res.json(), res.send(), res.status(N).json(), res.redirect(),
          etc. comptés comme Exit quand la racine de la chaîne est
          res/response/reply/ctx. Sans cette détection, AUCUN endpoint
          Express ne reçoit d'Exit car Express utilise des callbacks
          (pas de return implicit comme FastAPI/NestJS).

  D-JS7 : Drizzle ORM — détection sur présence dans la chaîne
          (Ajouté lors de la revue adversariale JS/TS.)
          Drizzle utilise une builder API chaînée. La chaîne
          db.select().from(t).where(eq).limit(10) a pour terminal .limit
          qui n'est pas un mot-clé Drizzle. On scanne la chaîne pour
          trouver le premier mot-clé (select/insert/update/delete)
          et on classifie selon lui.

  D-JS8 : Tracking de HTTP client factories (équivalent D-PY7 Python)
          (Ajouté lors de la revue adversariale JS/TS.)
          `const client = axios.create()` → variable `client` marquée.
          Permet de détecter `client.get(url)` même quand le seul token
          est "client" (ambigu sans cette information).
          Factories : axios.create, got.extend, ky.create, ky.extend.

  D-JS9 : Error messages HTTP NestJS (throw HttpException) comme Exit
          (Équivalent D-PY10 Python pour JS/TS.)
          Pré-passe pour identifier les body de méthodes endpoint NestJS/
          Express, puis détection des `throw new BadRequestException(...)`
          (22 classes NESTJS_HTTP_EXCEPTIONS) avec frequency rule
          (1 Exit error par endpoint, peu importe combien de throws).

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from typing import Optional

from ..models import CosmicMode, CosmicMovement
from . import _common as C


# ===========================================================================
# Express / Fastify / Koa response methods (Exit)
# ===========================================================================

# Méthodes Express/Fastify de réponse HTTP. Détectées comme Exit quand
# l'objet base est nommé res/response/reply (convention forte).
# D-JS6 (ajouté lors de la revue adversariale) : sans cette détection,
# AUCUN endpoint Express ne reçoit d'Exit (Express utilise des callbacks
# avec res.json, pas de return explicit comme FastAPI).
EXPRESS_RESPONSE_METHODS = {
    "json", "send", "sendFile", "sendStatus", "end", "redirect",
    "render", "download", "jsonp", "type", "format",
}

# Bases connues pour les objets response
EXPRESS_RESPONSE_BASE_TOKENS = {"res", "response", "reply", "ctx"}


# ===========================================================================
# Décorateurs NestJS — Entry HTTP/Queue/WebSocket
# ===========================================================================

# Décorateurs NestJS qui exposent un endpoint HTTP
NEST_HTTP_DECORATORS = {
    "Get", "Post", "Put", "Delete", "Patch", "Options", "Head", "All",
}

# Décorateurs NestJS pour les microservices / queues
NEST_MESSAGE_DECORATORS = {"MessagePattern", "EventPattern"}

# Décorateurs NestJS WebSocket
NEST_WS_DECORATORS = {"SubscribeMessage"}


# ===========================================================================
# D-JS9 (L9 fix pour JS/TS) — Classes d'exception HTTP NestJS et frameworks tiers
# ===========================================================================

# Classes d'exception HTTP NestJS standard. Détectées comme Exit error
# avec frequency rule (1 par endpoint, même si plusieurs throws).
NESTJS_HTTP_EXCEPTIONS = {
    # NestJS @nestjs/common
    "HttpException",  # classe de base, tous les autres en héritent
    "BadRequestException", "UnauthorizedException", "NotFoundException",
    "ForbiddenException", "NotAcceptableException", "RequestTimeoutException",
    "ConflictException", "GoneException", "PayloadTooLargeException",
    "UnsupportedMediaTypeException", "UnprocessableEntityException",
    "InternalServerErrorException", "NotImplementedException",
    "BadGatewayException", "ServiceUnavailableException",
    "GatewayTimeoutException", "HttpVersionNotSupportedException",
    "MethodNotAllowedException", "PreconditionFailedException",
    "MisdirectedException", "ImATeapotException",
}

# Heuristique : classes custom dont le nom suggère une exception HTTP
# (suffixe Exception). Détectées avec confidence medium si le throw
# survient dans un contexte endpoint confirmé.
# (Pas inclus dans D-JS9 P1 pour éviter les faux positifs — réservé à P2)


# ===========================================================================
# Méthodes web (Express, Fastify, etc.)
# ===========================================================================

WEB_ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

# Bases qui évoquent un framework web côté serveur
WEB_FRAMEWORK_BASES = {
    "app", "router", "api", "server", "fastify", "express",
    "blueprint", "bp",
}

# Méthodes Fastify de routing (en plus de get/post/...)
FASTIFY_ROUTE_METHODS = {"route", "register"}


# ===========================================================================
# ORM — Prisma
# ===========================================================================

PRISMA_READ_METHODS = {
    "findUnique", "findUniqueOrThrow", "findFirst", "findFirstOrThrow",
    "findMany", "count", "aggregate", "groupBy",
}
PRISMA_WRITE_METHODS = {
    "create", "createMany", "createManyAndReturn",
    "update", "updateMany", "upsert",
    "delete", "deleteMany",
}

# ORM — TypeORM
TYPEORM_REPO_READ = {
    "find", "findOne", "findOneBy", "findOneOrFail", "findAndCount",
    "findBy", "count", "countBy", "sum", "average", "minimum", "maximum",
    "exist", "exists", "existsBy",
}
TYPEORM_REPO_WRITE = {
    "save", "insert", "update", "delete", "remove", "softDelete",
    "softRemove", "restore", "upsert",
}
TYPEORM_MANAGER_RAW = {"query"}

# ORM — Sequelize
# Méthodes Sequelize distinctives (peu de risque de faux positif : ces noms
# sont quasi-exclusivement Sequelize). Détectées sur une base capitalisée seule.
SEQUELIZE_READ_DISTINCTIVE = {
    "findAll", "findByPk", "findAndCountAll", "findOne",
}
SEQUELIZE_WRITE_DISTINCTIVE = {
    "bulkCreate", "upsert", "findOrCreate", "findCreateFind", "destroy",
}
# Méthodes Sequelize ambiguës : verbes courants qui existent sur des objets
# non-ORM (route configs, builders, classes). Exigent un signal fort :
# un token "sequelize"/"model"/"db" dans la base, sinon ignorées.
# D-JS10 fix (validation FastAPI template) : `SomeImport.update(...)` dans un
# fichier de routes généré ne doit PAS matcher Sequelize.
SEQUELIZE_READ_AMBIGUOUS = {"count", "sum", "min", "max", "scope"}
SEQUELIZE_WRITE_AMBIGUOUS = {"create", "update", "save"}

# Conservés pour compat (union complète)
SEQUELIZE_READ = SEQUELIZE_READ_DISTINCTIVE | SEQUELIZE_READ_AMBIGUOUS
SEQUELIZE_WRITE = SEQUELIZE_WRITE_DISTINCTIVE | SEQUELIZE_WRITE_AMBIGUOUS

# ORM — Drizzle (méthodes terminales sur la query builder chain)
# La détection se fait sur le premier maillon (db.select / db.insert / db.update / db.delete)
DRIZZLE_READ_STARTS = {"select"}
DRIZZLE_WRITE_STARTS = {"insert", "update", "delete"}


# ===========================================================================
# NoSQL — Mongoose
# ===========================================================================

MONGOOSE_READ = {
    "find", "findOne", "findById", "findByIdAndUpdate",
    "countDocuments", "estimatedDocumentCount", "distinct", "aggregate",
    "where", "exists",
}
MONGOOSE_WRITE = {
    "save", "create", "insertMany", "updateOne", "updateMany",
    "findOneAndUpdate", "findOneAndReplace", "findByIdAndDelete",
    "findOneAndDelete", "deleteOne", "deleteMany", "replaceOne",
    "bulkWrite",
}


# ===========================================================================
# Redis (node-redis, ioredis)
# ===========================================================================

REDIS_READ = {
    "get", "mget", "hget", "hmget", "hgetall", "hvals", "hkeys", "hexists",
    "lrange", "lindex", "llen", "smembers", "sismember", "scard",
    "zrange", "zrevrange", "zrangebyscore", "zscore", "zcard",
    "exists", "keys", "type", "ttl", "pttl",
}
REDIS_WRITE = {
    "set", "mset", "setex", "setnx", "psetex",
    "hset", "hmset", "hdel", "hincrby",
    "lpush", "rpush", "lpop", "rpop",
    "sadd", "srem", "zadd", "zrem", "zincrby",
    "del", "expire", "expireat", "rename", "incr", "decr", "incrby", "decrby",
}

# Méthodes très spécifiques Redis (utilisables sans contexte)
REDIS_SPECIFIC = {
    "hgetall", "hmset", "zadd", "zrange", "zrevrange", "zrangebyscore",
    "lrange", "lpush", "rpush", "lpop", "rpop", "smembers", "sadd", "srem",
    "hvals", "hkeys", "zincrby", "zcard", "scard",
}


# ===========================================================================
# HTTP client
# ===========================================================================

HTTP_CLIENT_LIBS = {
    "axios", "got", "fetch", "ky", "needle", "request", "superagent",
}

# Méthodes HTTP standards (sur axios, got, etc.) — verbes partagés (_common.py)
HTTP_METHODS_LIB = C.HTTP_VERBS

# D-JS8 (équivalent D-PY7) : factories qui créent un client HTTP réutilisable.
# Le résultat est typiquement assigné à une variable utilisée pour des calls
# HTTP. Sans tracking, `client = axios.create(); client.get(...)` n'est pas
# détecté car `client` seul est un token ambigu.
HTTP_CLIENT_FACTORY_CALLS = {
    "axios.create", "got.extend", "ky.create", "ky.extend",
}


# ===========================================================================
# Frontend persistence
# ===========================================================================

BROWSER_STORAGE_OBJECTS = {"localStorage", "sessionStorage"}
BROWSER_STORAGE_READ = {"getItem", "key"}
BROWSER_STORAGE_WRITE = {"setItem", "removeItem", "clear"}

# IndexedDB via idb library
IDB_READ = {"get", "getAll", "getKey", "getAllKeys", "count"}
IDB_WRITE = {"put", "add", "delete", "clear"}

# IndexedDB via Dexie
DEXIE_READ = {"get", "where", "toArray", "first", "last", "filter", "count", "each"}
DEXIE_WRITE = {"put", "add", "update", "delete", "bulkPut", "bulkAdd", "bulkDelete"}


# ===========================================================================
# File system (Node.js fs / fs/promises)
# ===========================================================================

FS_READ_FUNCS = {
    "readFile", "readFileSync", "read", "readSync",
    "createReadStream", "readdir", "readdirSync",
}
FS_WRITE_FUNCS = {
    "writeFile", "writeFileSync", "appendFile", "appendFileSync",
    "createWriteStream", "write", "writeSync",
    "unlink", "unlinkSync", "rm", "rmSync", "rmdir", "rmdirSync",
    "mkdir", "mkdirSync", "rename", "renameSync", "copyFile", "copyFileSync",
}


# ===========================================================================
# Queue (BullMQ / Bull)
# ===========================================================================

BULL_QUEUE_WRITE_METHODS = {"add", "addBulk"}
BULL_WORKER_DECORATORS = {"Process", "OnWorkerEvent"}


# ===========================================================================
# Helpers de classification
# ===========================================================================

def _is_decorator_call(node) -> bool:
    """True si ce noeud est un appel à l'intérieur d'un décorateur (@xxx(...))."""
    parent = node.parent
    while parent is not None:
        if parent.type == "decorator":
            return True
        if parent.type in ("class_body", "program", "function_declaration",
                            "function_expression", "arrow_function"):
            return False
        parent = parent.parent
    return False


def _outer_chain_root(node) -> bool:
    """True si ce call_expression est la racine de sa chaîne (.first()).

    Le but : pour ``a.b(...).c(...).d(...)``, seul le call externe ``d(...)`` est
    "racine" ; les autres sont des inner calls qu'on doit skipper pour éviter
    de double-compter.
    """
    parent = node.parent
    if parent is None:
        return True
    # Si le parent est une member_expression dont c'est l'objet
    if parent.type == "member_expression":
        obj = parent.child_by_field_name("object")
        if obj is not None and id(obj) == id(node):
            return False  # ce call sera réutilisé comme base d'un autre call
    # await expression : on est encore une racine
    if parent.type == "await_expression":
        return _outer_chain_root(parent)
    return True


def _is_route_decorator(deco_text: str) -> Optional[str]:
    """Analyse un décorateur NestJS et retourne le framework si pertinent.

    Reconnaît : @Get('/'), @Post(), @Put(), @Delete(), @Patch(), @All,
    @MessagePattern, @EventPattern, @SubscribeMessage.

    Retourne le nom de framework ("nestjs") ou None.
    """
    # Enlever le @ initial
    text = deco_text.lstrip("@").strip()
    # Garder la partie avant ( ou avant fin
    name = text.split("(")[0].strip()
    if name in NEST_HTTP_DECORATORS:
        return "nestjs"
    if name in NEST_MESSAGE_DECORATORS:
        return "nestjs"
    if name in NEST_WS_DECORATORS:
        return "nestjs"
    return None


# ===========================================================================
# Détecteur principal
# ===========================================================================

def detect_javascript_movements(
    tree,
    source_bytes: bytes,
    file_path: str,
    *,
    mode: CosmicMode = "practical",
) -> list[CosmicMovement]:
    """Détecte les mouvements COSMIC dans un fichier JS/TS via tree-sitter.

    Parcourt l'AST une seule fois, en routant chaque type de noeud vers les
    détecteurs concernés. La déduplication est gérée par MovementCollector.
    """
    collector = C.MovementCollector(file_path)

    # Pré-passe unique (fusionnée) : marque les calls de décorateurs à skip
    # ET identifie les body de fonctions endpoint. Une seule traversée de
    # l'arbre au lieu de deux (optimisation qualité/perf).
    _prepass(tree.root_node, source_bytes, file_path, collector)

    # Passe principale : détection
    def visit(node):
        if collector.should_skip(node):
            return False  # skip ce sous-arbre

        # D-JS8 : tracker les HTTP client factories
        # `const client = axios.create()` ou `let api = ky.extend(...)`
        if node.type == "variable_declarator":
            _track_http_client_factory(node, source_bytes, collector)
            return True

        # Décorateurs (classes NestJS, etc.)
        if node.type == "decorator":
            _detect_nest_decorator(node, source_bytes, file_path, collector)
            return True

        # Class declarations (NestJS controllers)
        if node.type == "class_declaration":
            _detect_nest_controller(node, source_bytes, collector)
            return True

        # Function declarations + arrow functions : routes file-based (Next.js, etc.)
        if node.type in ("function_declaration", "function_expression",
                          "arrow_function", "method_definition"):
            _detect_file_based_route(node, source_bytes, file_path, collector)
            return True

        # Call expressions : le coeur de la détection
        if node.type == "call_expression":
            return _detect_call(node, source_bytes, file_path, mode, collector)

        # new_expression : new WebSocket.Server(), new Worker(), etc.
        if node.type == "new_expression":
            _detect_new_expr(node, source_bytes, file_path, collector)
            return True

        # Member access (lecture localStorage.X sans .getItem)
        if node.type == "member_expression":
            _detect_member_storage(node, source_bytes, file_path, collector)
            return True

        # D-JS9 (L9 fix) : throw new HttpException dans contexte endpoint
        if node.type == "throw_statement":
            _detect_http_throw(node, source_bytes, collector)
            return True

        return True

    C.walk(tree.root_node, visit)
    return collector.movements


# ===========================================================================
# D-JS8 : tracking de HTTP client factories
# ===========================================================================

def _track_http_client_factory(node, source_bytes: bytes,
                                 collector: C.MovementCollector):
    """Si la déclaration est `const xxx = axios.create()`, marquer xxx
    comme HTTP client variable.

    Tree-sitter : variable_declarator a fields 'name' et 'value'.
    """
    name_node = C.field(node, "name")
    value_node = C.field(node, "value")
    if name_node is None or value_node is None:
        return

    # value doit être un Call à une factory connue
    if value_node.type == "call_expression":
        chain = C.call_chain(value_node, source_bytes)
        if chain in HTTP_CLIENT_FACTORY_CALLS:
            # name peut être identifier (const x = ...) ou
            # object_pattern (const {a, b} = ...). On gère le cas identifier.
            if name_node.type == "identifier":
                var_name = C.node_text(name_node, source_bytes)
                collector.http_client_vars.add(var_name)


# ===========================================================================
# Pré-passe : marquer les noeuds à skip
# ===========================================================================

def _prepass(node, source_bytes: bytes, file_path: str,
             collector: C.MovementCollector):
    """Pré-passe unique : combine deux responsabilités en une traversée.

    1. Marque les call_expression à l'intérieur des décorateurs (skip).
    2. Identifie les body de fonctions endpoint (D-JS9 L9) :
       - NestJS : méthodes décorées (@Get, @Post, ...) dans une classe
       - Routes file-based (Next.js, Remix, SvelteKit)
       - Express/Fastify : 2e arg d'un appel `app.get('/path', handler)`

    Fusionner ces deux passes (auparavant `_mark_decorator_calls` +
    `_collect_endpoint_method_bodies`) évite une traversée complète
    redondante de l'AST.
    """
    ntype = node.type

    # (1) Décorateurs : marquer les calls descendants pour skip
    if ntype == "decorator":
        for sub in _all_call_descendants(node):
            collector.mark_skip(sub)

    # (2a) NestJS : method_definition décorée endpoint
    elif ntype == "method_definition":
        decos = _decorator_siblings(node, source_bytes)
        for deco_text in decos:
            if _is_route_decorator(deco_text) is not None:
                body = C.field(node, "body")
                if body is not None:
                    collector.endpoint_method_bodies.add(id(body))
                break

    # (2b) Routes file-based : function/arrow
    elif ntype in ("function_declaration", "function_expression",
                   "arrow_function"):
        if _is_file_based_route_function(node, source_bytes, file_path):
            body = C.field(node, "body")
            if body is not None:
                collector.endpoint_method_bodies.add(id(body))

    # (2c) Express/Fastify : handler en 2e arg
    elif ntype == "call_expression":
        _mark_express_handler_body(node, source_bytes, collector)

    for child in node.children:
        _prepass(child, source_bytes, file_path, collector)


def _all_call_descendants(node):
    """Yield tous les noeuds call_expression descendants."""
    if node.type == "call_expression":
        yield node
    for child in node.children:
        yield from _all_call_descendants(child)


# ===========================================================================
# D-JS9 : identification des fonctions endpoint (helpers de _prepass)
# ===========================================================================


def _is_file_based_route_function(node, source_bytes: bytes, file_path: str) -> bool:
    """Heuristique pour reconnaître une fonction de route file-based.

    Patterns reconnus :
    - Next.js Pages API : pages/api/**/*.ts + signature (req, res)
    - Next.js App Router : app/**/route.ts + exports nommés GET/POST/...
    - Remix : app/routes/* + exports loader/action
    - SvelteKit : +server.ts + exports GET/POST/...

    Simplification : on délègue au _detect_file_based_route existant en
    re-inspectant juste les conditions de path et de signature.
    """
    if not file_path:
        return False
    path_norm = file_path.replace("\\", "/").lower()

    # Next.js Pages API
    if "/pages/api/" in path_norm or path_norm.startswith("pages/api/"):
        # Handler (req, res) — vérifier 2 params
        params = C.field(node, "parameters")
        if params is not None:
            param_count = sum(1 for c in C.named_children(params)
                              if c.type in ("identifier", "required_parameter",
                                            "object_pattern", "array_pattern"))
            if param_count >= 2:
                return True

    # Next.js App Router
    if "/app/" in path_norm and (path_norm.endswith("/route.ts") or
                                   path_norm.endswith("/route.js")):
        # Function declaration avec nom GET/POST/PUT/DELETE/PATCH
        if node.type == "function_declaration":
            name_node = C.field(node, "name")
            if name_node is not None:
                name = C.node_text(name_node, source_bytes)
                if name in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    return True

    # Remix routes
    if "/app/routes/" in path_norm or path_norm.startswith("app/routes/"):
        if node.type == "function_declaration":
            name_node = C.field(node, "name")
            if name_node is not None:
                name = C.node_text(name_node, source_bytes)
                if name in ("loader", "action"):
                    return True

    # SvelteKit +server.ts
    if path_norm.endswith("+server.ts") or path_norm.endswith("+server.js"):
        if node.type == "function_declaration":
            name_node = C.field(node, "name")
            if name_node is not None:
                name = C.node_text(name_node, source_bytes)
                if name in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    return True

    return False


def _mark_express_handler_body(call_node, source_bytes: bytes,
                                  collector: C.MovementCollector):
    """Si le call est `app.get('/path', handler)`, marque le body du handler."""
    # Récupérer la fonction appelée
    func_node = C.field(call_node, "function")
    if func_node is None:
        return
    # On veut un member_expression avec une property dans WEB_ROUTE_METHODS
    if func_node.type != "member_expression":
        return
    prop_node = C.field(func_node, "property")
    if prop_node is None:
        return
    method = C.node_text(prop_node, source_bytes)
    if method not in WEB_ROUTE_METHODS and method not in FASTIFY_ROUTE_METHODS:
        return
    # Vérifier que la base est un framework web
    obj_node = C.field(func_node, "object")
    if obj_node is None:
        return
    obj_text = C.node_text(obj_node, source_bytes)
    obj_tokens = C.tokenize_base(obj_text)
    if not _is_web_framework_base(obj_text, obj_tokens):
        return
    # Récupérer les args ; le handler est typiquement le 2e (peut être le 3e
    # si middleware en position 2)
    args_node = C.field(call_node, "arguments")
    if args_node is None:
        return
    for arg in C.named_children(args_node):
        if arg.type in ("arrow_function", "function_expression"):
            body = C.field(arg, "body")
            if body is not None:
                collector.endpoint_method_bodies.add(id(body))


# ===========================================================================
# D-JS9 : détection des throw new HttpException
# ===========================================================================

def _detect_http_throw(throw_node, source_bytes: bytes,
                         collector: C.MovementCollector):
    """Détecte `throw new HttpException(...)` dans un endpoint.

    Frequency rule (cohérent avec D-PY10) : 1 seul Exit error par endpoint,
    même si plusieurs throws différents.
    """
    # Le child principal d'un throw_statement est l'expression jetée
    thrown = None
    for child in C.named_children(throw_node):
        thrown = child
        break
    if thrown is None:
        return

    # Cas 1 : `throw new XxxException(...)` (new_expression)
    # Cas 2 : `throw exception_instance` (identifier ou autre)
    exc_name = ""
    if thrown.type == "new_expression":
        constructor = C.field(thrown, "constructor")
        if constructor is not None:
            full_name = C.node_text(constructor, source_bytes)
            # Pour `new HttpException(...)` → "HttpException"
            # Pour `new common.BadRequestException(...)` → "BadRequestException"
            exc_name = full_name.rsplit(".", 1)[-1]
    elif thrown.type == "identifier":
        # `throw notFoundException` - moins fréquent
        exc_name = C.node_text(thrown, source_bytes)

    if exc_name not in NESTJS_HTTP_EXCEPTIONS:
        return

    # Remonter vers le body englobant et vérifier qu'il est dans le set endpoint
    parent = throw_node.parent
    containing_body = None
    while parent is not None:
        if parent.type == "statement_block":
            if id(parent) in collector.endpoint_method_bodies:
                containing_body = parent
                break
        parent = parent.parent

    if containing_body is None:
        return  # throw hors endpoint → ignoré

    # Frequency rule : 1 seul Exit error par endpoint
    body_id = id(containing_body)
    if body_id in collector.endpoint_error_emitted:
        return
    collector.endpoint_error_emitted.add(body_id)

    excerpt_text = C.node_text(throw_node, source_bytes)
    collector.add(
        type="exit", line=C.line_of(throw_node),
        code_excerpt=excerpt_text,
        detector=f"throw_{exc_name}",
        framework="nestjs", confidence="medium",
    )


# ===========================================================================
# Décorateurs NestJS
# ===========================================================================

def _detect_nest_decorator(node, source_bytes: bytes, file_path: str,
                            collector: C.MovementCollector):
    """Détecte les décorateurs NestJS (@Get, @Post, @MessagePattern, etc.).

    Le décorateur lui-même ne produit pas de mouvement. C'est la fonction qu'il
    décore qui sera comptée comme Entry. La détection est gérée par
    _detect_nest_controller au niveau de la classe.
    """
    pass  # Géré par _detect_nest_controller


def _detect_nest_controller(node, source_bytes: bytes, collector: C.MovementCollector):
    """Détecte les méthodes décorées dans une classe NestJS.

    Pour chaque méthode avec un décorateur NestJS de routing, ajoute un Entry
    + un Exit implicite (NestJS retourne automatiquement la valeur).
    """
    # Récupérer le body de la classe
    body = C.field(node, "body")
    if body is None:
        return

    # Parcourir les méthodes
    for member in C.named_children(body):
        if member.type != "method_definition":
            continue

        # Récupérer les décorateurs (frères précédents de la méthode)
        decos = _decorator_siblings(member, source_bytes)
        if not decos:
            continue

        # Identifier le type de décorateur NestJS
        framework = None
        movement_type_in = "entry"
        for deco_text in decos:
            fw = _is_route_decorator(deco_text)
            if fw is None:
                continue
            framework = fw
            break

        if framework is None:
            continue

        # Récupérer le nom de la méthode
        name_node = C.field(member, "name")
        method_name = C.node_text(name_node, source_bytes) if name_node else "?"

        line = C.line_of(member)
        deco_preview = decos[0] if decos else ""
        collector.add(
            type="entry", line=line,
            code_excerpt=f"{deco_preview} {method_name}(...)",
            detector="nest_route", framework=framework,
        )

        # Exit : un return dans la méthode
        _add_implicit_returns(member, source_bytes, collector, "nest_return")


def _decorator_siblings(method_node, source_bytes: bytes) -> list[str]:
    """Récupère les décorateurs qui précèdent une méthode/classe.

    En tree-sitter-typescript, les décorateurs sont des enfants frères qui
    précèdent ``method_definition`` ou ``class_declaration``.
    """
    parent = method_node.parent
    if parent is None:
        return []

    decos: list[str] = []
    found_self = False
    # On itère à l'envers depuis ``method_node``
    children = list(parent.children)
    idx = None
    for i, c in enumerate(children):
        if id(c) == id(method_node):
            idx = i
            break
    if idx is None:
        return []

    # Remonter et collecter les décorateurs juste avant
    for i in range(idx - 1, -1, -1):
        c = children[i]
        if c.type == "decorator":
            decos.insert(0, C.node_text(c, source_bytes))
        elif c.is_named:
            # On a buté sur un autre élément nommé → on arrête
            break
    return decos


def _add_implicit_returns(func_node, source_bytes: bytes,
                           collector: C.MovementCollector, detector: str):
    """Pour les routes web : chaque return dans la fonction = 1 Exit implicite.

    Skip les returns dans des fonctions imbriquées (callbacks).
    """
    def walk_returns(n, depth=0):
        if n.type in ("function_declaration", "function_expression",
                       "arrow_function", "method_definition") and depth > 0:
            return  # Skip nested functions
        if n.type == "return_statement":
            collector.add(
                type="exit", line=C.line_of(n),
                code_excerpt=C.node_text(n, source_bytes),
                detector=detector, framework="web",
                confidence="medium",
            )
        for c in n.children:
            walk_returns(c, depth + 1 if n.type in (
                "function_declaration", "function_expression",
                "arrow_function", "method_definition") else depth)
    body = C.field(func_node, "body")
    if body is not None:
        walk_returns(body, depth=0)


# ===========================================================================
# Routes file-based (Next.js, Remix, SvelteKit)
# ===========================================================================

def _detect_file_based_route(node, source_bytes: bytes, file_path: str,
                              collector: C.MovementCollector):
    """Détecte les routes définies par convention de fichier.

    Next.js Pages Router : ``pages/api/X.ts`` → export default function handler(req, res)
    Next.js App Router : ``app/X/route.ts`` → exports nommés GET, POST, PUT, DELETE, PATCH
    Remix : ``app/routes/X.ts`` → exports loader, action
    SvelteKit : ``+server.ts`` → exports GET, POST, etc.
    """
    path_norm = file_path.replace("\\", "/").lower()

    # --- SvelteKit ---
    if path_norm.endswith("+server.ts") or path_norm.endswith("+server.js"):
        if node.type == "function_declaration":
            fw = "sveltekit"
            _check_named_export_route(node, source_bytes, collector, fw)
        return

    # --- Next.js App Router ---
    if "/route." in path_norm or path_norm.endswith("/route.ts") or path_norm.endswith("/route.js"):
        if node.type == "function_declaration":
            _check_named_export_route(node, source_bytes, collector, "nextjs")
        return

    # --- Next.js Pages Router ---
    if "/pages/api/" in path_norm:
        # Détecter un `export default function handler(req, res)` ou variante async
        if node.type in ("function_declaration", "function_expression", "arrow_function"):
            if _is_default_export_handler(node, source_bytes):
                line = C.line_of(node)
                collector.add(
                    type="entry", line=line,
                    code_excerpt="export default handler(req, res)",
                    detector="nextjs_pages_api", framework="nextjs",
                )
                _add_implicit_returns(node, source_bytes, collector,
                                       detector="nextjs_pages_api_return")
        return

    # --- Remix ---
    if "/app/routes/" in path_norm and (path_norm.endswith(".ts") or path_norm.endswith(".tsx")
                                          or path_norm.endswith(".js") or path_norm.endswith(".jsx")):
        if node.type == "function_declaration":
            _check_named_export_route(node, source_bytes, collector, "remix",
                                        allowed_names={"loader", "action"})


def _check_named_export_route(node, source_bytes: bytes,
                                collector: C.MovementCollector,
                                framework: str,
                                allowed_names: Optional[set] = None):
    """Vérifie si la fonction est un export nommé de route (GET/POST/...)."""
    if allowed_names is None:
        allowed_names = {"GET", "POST", "PUT", "DELETE", "PATCH",
                          "HEAD", "OPTIONS"}

    name_node = C.field(node, "name")
    if name_node is None:
        return
    fn_name = C.node_text(name_node, source_bytes)
    if fn_name not in allowed_names:
        return

    # Vérifier que c'est bien un export (parent contient "export")
    if not _is_export(node):
        return

    line = C.line_of(node)
    collector.add(
        type="entry", line=line,
        code_excerpt=f"export {fn_name}(...)",
        detector=f"{framework}_{fn_name.lower()}_route",
        framework=framework,
    )
    _add_implicit_returns(node, source_bytes, collector,
                           detector=f"{framework}_route_return")


def _is_export(node) -> bool:
    """True si la fonction est exportée (parent contient export_statement)."""
    parent = node.parent
    while parent is not None:
        if parent.type == "export_statement":
            return True
        if parent.type == "program":
            return False
        parent = parent.parent
    return False


def _is_default_export_handler(node, source_bytes: bytes) -> bool:
    """Détecte ``export default function handler(req, res) {}`` ou variante.

    Cible Next.js Pages Router : la fonction handler exportée par défaut.
    """
    # Doit être enfant d'export_statement avec "default"
    parent = node.parent
    if parent is None:
        return False
    if parent.type != "export_statement":
        # Cas arrow function : on remonte d'un cran
        if parent.type == "variable_declarator":
            decl = parent.parent  # variable_declaration
            if decl is not None and decl.parent is not None:
                export = decl.parent
                if export.type == "export_statement":
                    parent = export
                else:
                    return False
        else:
            return False

    text = C.node_text(parent, source_bytes)
    if "export default" not in text:
        return False

    # Vérifier la signature : 2 paramètres (req, res) ou ressemblant
    params = C.field(node, "parameters")
    if params is None:
        return False
    # Compter les params nommés (pas comma, etc.)
    param_count = sum(1 for c in C.named_children(params))
    if param_count not in (2, 3):  # parfois (req, res, next)
        return False

    # Heuristique optionnelle : noms ressemblant à req/res
    first = next(C.named_children(params), None)
    second = None
    iter_params = list(C.named_children(params))
    if len(iter_params) >= 2:
        second = iter_params[1]
    # On regarde le texte des deux paramètres pour confirmation
    if first is not None and second is not None:
        f_text = C.node_text(first, source_bytes).lower()
        s_text = C.node_text(second, source_bytes).lower()
        if ("req" in f_text or "request" in f_text) and \
           ("res" in s_text or "response" in s_text):
            return True
    return True  # On fait confiance à la convention si la signature a 2-3 params


# ===========================================================================
# Call expressions : routing par chaîne
# ===========================================================================

def _detect_call(node, source_bytes: bytes, file_path: str,
                  mode: CosmicMode, collector: C.MovementCollector) -> bool:
    """Détecte les mouvements liés à un call_expression.

    Retourne ``False`` si les enfants doivent être skip (chaîne déjà traitée).
    """
    # Si on n'est pas la racine de la chaîne, skip (déjà géré par le call externe)
    if not _outer_chain_root(node):
        return True  # On laisse descendre, juste on ne compte pas ce call ici

    # Skip si décorateur (déjà marqué par la pré-passe)
    if collector.should_skip(node):
        return False

    chain = C.call_chain(node, source_bytes)
    if not chain:
        return True

    method = C.short_name(chain)
    base = C.base_of(chain)
    base_tokens = C.tokenize_base(base)
    line = C.line_of(node)
    excerpt_text = C.node_text(node, source_bytes)

    # 1. Express / Fastify route definitions
    if method in WEB_ROUTE_METHODS or method in FASTIFY_ROUTE_METHODS:
        if _is_web_framework_base(base, base_tokens):
            fw = _guess_web_framework(base, base_tokens, method)
            collector.add(
                type="entry", line=line,
                code_excerpt=excerpt_text,
                detector=f"{fw}_route", framework=fw,
            )
            # Le 2e argument est typiquement le handler ; ses returns sont les Exits.
            # On les détectera quand on visitera le handler.
            return True

    # 1bis. Express / Fastify response methods (res.json, res.send, etc.)
    # D-JS6 : indispensable car Express utilise des callbacks, donc pas de
    # return implicit comme FastAPI/NestJS. Sans cette détection, AUCUN
    # endpoint Express n'a d'Exit dans le compte COSMIC.
    if method in EXPRESS_RESPONSE_METHODS:
        # On exige que la racine de la chaîne soit res/response/reply/ctx
        chain_root = chain.split(".")[0] if "." in chain else ""
        if chain_root in EXPRESS_RESPONSE_BASE_TOKENS:
            collector.add(
                type="exit", line=line,
                code_excerpt=excerpt_text,
                detector=f"express_res_{method}", framework="express",
            )
            return True

    # 2. ORM Prisma
    _detect_prisma(chain, method, base, line, excerpt_text, collector)

    # 3. ORM TypeORM
    _detect_typeorm(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 4. ORM Sequelize
    _detect_sequelize(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 5. ORM Drizzle (1er maillon : db.select/insert/update/delete)
    _detect_drizzle(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 6. Mongoose
    _detect_mongoose(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 7. Redis
    _detect_redis(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 8. HTTP client
    _detect_http_client(chain, method, base, base_tokens, line, excerpt_text,
                         mode, collector)

    # 9. fs / fs/promises
    _detect_fs(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 10. localStorage / sessionStorage / IndexedDB
    _detect_browser_storage(chain, method, base, base_tokens, line, excerpt_text,
                             collector)

    # 11. Queue : BullMQ
    _detect_queue(chain, method, base, base_tokens, line, excerpt_text, collector)

    # 12. WebSocket
    _detect_websocket(chain, method, base, base_tokens, line, excerpt_text,
                       collector)

    # 13. CLI (commander / yargs)
    _detect_cli(chain, method, base, base_tokens, line, excerpt_text, collector)

    return True


def _is_web_framework_base(base: str, tokens: set[str]) -> bool:
    """True si la base ressemble à un framework web (Express, Fastify, etc.)."""
    if any(t in WEB_FRAMEWORK_BASES for t in tokens):
        return True
    # Patterns class-method : this.app, this.router
    if base.startswith("this.") and any(t in tokens for t in WEB_FRAMEWORK_BASES):
        return True
    return False


def _guess_web_framework(base: str, tokens: set[str], method: str) -> str:
    """Heuristique pour identifier le framework à partir de la base + méthode."""
    if "fastify" in tokens:
        return "fastify"
    if method in FASTIFY_ROUTE_METHODS and "fastify" in base.lower():
        return "fastify"
    if "express" in tokens:
        return "express"
    # Cas générique
    return "express"


def _detect_prisma(chain: str, method: str, base: str, line: int,
                    excerpt_text: str, collector: C.MovementCollector):
    """Prisma : prisma.<model>.<method> ou ctx.prisma.<model>.<method>."""
    if "prisma" not in base.lower():
        return
    if method in PRISMA_READ_METHODS:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"prisma_{method}", framework="prisma")
    elif method in PRISMA_WRITE_METHODS:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"prisma_{method}", framework="prisma")


def _detect_typeorm(chain: str, method: str, base: str, base_tokens: set,
                     line: int, excerpt_text: str, collector: C.MovementCollector):
    """TypeORM : repository.X ou entityManager.query."""
    if not any(t in base_tokens for t in ("repository", "manager", "datasource")):
        return
    if method in TYPEORM_REPO_READ:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"typeorm_{method}", framework="typeorm")
    elif method in TYPEORM_REPO_WRITE:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"typeorm_{method}", framework="typeorm")
    elif method in TYPEORM_MANAGER_RAW:
        # query("SELECT/INSERT/...") : sans contexte SQL parsé, on suppose read
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector="typeorm_query", framework="typeorm",
                       confidence="medium")


def _detect_sequelize(chain: str, method: str, base: str, base_tokens: set,
                       line: int, excerpt_text: str,
                       collector: C.MovementCollector):
    """Sequelize : Model.X (la classe modèle commence par majuscule).

    D-JS10 fix : les méthodes ambiguës (create/update/save/count/...) ne
    matchent que si un signal fort est présent (token sequelize/model/db),
    pour éviter les faux positifs sur `RouteImport.update(...)` (configs de
    route générées), `SomeClass.create(...)` (factory), etc.
    """
    last = base.rsplit(".", 1)[-1] if base else ""
    if not last or not last[0].isupper():
        return

    strong_signal = bool(base_tokens & {"sequelize", "model", "models", "db"})

    # Méthodes distinctives : base capitalisée suffit
    if method in SEQUELIZE_READ_DISTINCTIVE:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"sequelize_{method}", framework="sequelize",
                       confidence="high" if strong_signal else "medium")
        return
    if method in SEQUELIZE_WRITE_DISTINCTIVE:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"sequelize_{method}", framework="sequelize",
                       confidence="high" if strong_signal else "medium")
        return

    # Méthodes ambiguës : exiger un signal fort
    if not strong_signal:
        return
    if method in SEQUELIZE_READ_AMBIGUOUS:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"sequelize_{method}", framework="sequelize",
                       confidence="medium")
    elif method in SEQUELIZE_WRITE_AMBIGUOUS:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"sequelize_{method}", framework="sequelize",
                       confidence="medium")


def _detect_drizzle(chain: str, method: str, base: str, base_tokens: set,
                     line: int, excerpt_text: str,
                     collector: C.MovementCollector):
    """Drizzle ORM : db.select() / db.insert() / db.update() / db.delete().

    D-JS7 (ajouté lors de la revue adversariale) : Drizzle utilise une
    builder API chaînée. Le terminal peut être .limit() / .orderBy() / etc.,
    pas seulement .select(). On classifie selon la **présence** d'un mot-clé
    Drizzle (select/insert/update/delete) dans la chaîne, pas selon le terminal.
    """
    # Vérifier que la racine est "db" ou "tx" (contexte Drizzle)
    first = chain.split(".", 1)[0] if "." in chain else chain
    chain_root_lower = first.lower()
    if chain_root_lower not in ("db", "tx"):
        # Élargir : this.db, ctx.db (root contient "db")
        if "db" not in base_tokens and "tx" not in base_tokens:
            return

    # Chercher dans la chaîne quel mot-clé Drizzle apparaît en premier
    # (donc le plus proche de la racine, le « premier maillon » sémantique).
    chain_parts = chain.split(".")
    drizzle_keyword = None
    for part in chain_parts:
        if part in DRIZZLE_READ_STARTS:
            drizzle_keyword = ("read", part)
            break
        if part in DRIZZLE_WRITE_STARTS:
            drizzle_keyword = ("write", part)
            break

    if drizzle_keyword is None:
        return

    kind, keyword = drizzle_keyword
    if kind == "read":
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"drizzle_{keyword}", framework="drizzle",
                       confidence="medium")
    else:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"drizzle_{keyword}", framework="drizzle",
                       confidence="medium")


def _detect_mongoose(chain: str, method: str, base: str, base_tokens: set,
                      line: int, excerpt_text: str,
                      collector: C.MovementCollector):
    """Mongoose : Model.find/findOne/save/...

    Heuristique : la base se termine par un identifiant capitalisé (Model)
    OU contient "mongoose"/"model"/"schema".
    """
    if not (any(t in base_tokens for t in ("mongoose", "model", "schema"))):
        # Sans contexte explicite, on n'active que si la base commence par maj
        last = base.rsplit(".", 1)[-1] if base else ""
        if not last or not last[0].isupper():
            return

    if method in MONGOOSE_READ:
        # find/findOne peuvent matcher autre chose, mais "Model.find" est très
        # spécifique. Confiance medium par défaut.
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"mongoose_{method}", framework="mongoose",
                       confidence="medium")
    elif method in MONGOOSE_WRITE:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"mongoose_{method}", framework="mongoose",
                       confidence="medium")


def _detect_redis(chain: str, method: str, base: str, base_tokens: set,
                   line: int, excerpt_text: str,
                   collector: C.MovementCollector):
    """Détecte les opérations Redis avec heuristique de contexte."""
    is_redis_context = any(t in base_tokens for t in ("redis", "cache", "ioredis"))
    ambiguous = method not in REDIS_SPECIFIC

    if not is_redis_context and ambiguous:
        return

    if method in REDIS_READ:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"redis_{method}", framework="redis",
                       confidence="high" if is_redis_context else "low")
    elif method in REDIS_WRITE:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"redis_{method}", framework="redis",
                       confidence="high" if is_redis_context else "low")


# Tokens HTTP positifs / négatifs (mêmes logiques qu'en Python)
HTTP_POSITIVE_TOKENS = {
    "axios", "got", "fetch", "ky", "needle", "http", "https",
    "rest", "api", "webhook", "client", "session",
}
HTTP_AMBIGUOUS = {"client", "session"}
HTTP_STORAGE_TOKENS = {
    "redis", "mongo", "mongodb", "db", "cache",
    "elastic", "elasticsearch", "kafka", "rabbit", "rabbitmq",
}


def _detect_http_client(chain: str, method: str, base: str, base_tokens: set,
                         line: int, excerpt_text: str, mode: CosmicMode,
                         collector: C.MovementCollector):
    """Détecte les appels HTTP sortants (fetch, axios, etc.)."""
    if mode != "practical":
        return

    # fetch() global (sans base)
    if not base and method == "fetch":
        collector.add(type="write", line=line, code_excerpt=excerpt_text + " [req]",
                       detector="http_fetch", framework="http_client")
        collector.add(type="read", line=line, code_excerpt=excerpt_text + " [resp]",
                       detector="http_fetch_resp", framework="http_client")
        return

    # axios.X, got.X, etc.
    if method in HTTP_METHODS_LIB:
        # D-JS8 : si la racine du chain est une variable identifiée comme
        # HTTP client (via `const client = axios.create()`), accepter
        # directement sans heuristique. Bypass les filtres habituels.
        chain_root = chain.split(".")[0] if "." in chain else chain
        if chain_root in collector.http_client_vars:
            collector.add(type="write", line=line,
                           code_excerpt=excerpt_text + " [req]",
                           detector=f"http_{method}", framework="http_client")
            collector.add(type="read", line=line,
                           code_excerpt=excerpt_text + " [resp]",
                           detector=f"http_{method}_resp", framework="http_client")
            return

        # Exclure les storage clients
        if base_tokens & HTTP_STORAGE_TOKENS:
            return
        # Exclure les routes Express/Fastify (déjà traitées plus haut)
        if any(t in WEB_FRAMEWORK_BASES for t in base_tokens):
            return
        positive = base_tokens & HTTP_POSITIVE_TOKENS
        if not positive:
            return
        # Si on n'a que client/session, ce n'est pas suffisant
        if positive <= HTTP_AMBIGUOUS:
            return
        collector.add(type="write", line=line, code_excerpt=excerpt_text + " [req]",
                       detector=f"http_{method}", framework="http_client")
        collector.add(type="read", line=line, code_excerpt=excerpt_text + " [resp]",
                       detector=f"http_{method}_resp", framework="http_client")


def _detect_fs(chain: str, method: str, base: str, base_tokens: set,
                line: int, excerpt_text: str, collector: C.MovementCollector):
    """Détecte les appels au module fs (Node.js)."""
    # Match si base contient "fs" en token, ou si méthode est très spécifique
    is_fs_context = "fs" in base_tokens or "fsp" in base_tokens or "promises" in base_tokens
    very_specific = method in {"readFileSync", "writeFileSync", "appendFileSync",
                                 "createReadStream", "createWriteStream",
                                 "readdirSync", "mkdirSync", "unlinkSync",
                                 "rmSync", "rmdirSync"}

    if not is_fs_context and not very_specific:
        return

    if method in FS_READ_FUNCS:
        collector.add(type="read", line=line, code_excerpt=excerpt_text,
                       detector=f"fs_{method}", framework="stdlib_node")
    elif method in FS_WRITE_FUNCS:
        collector.add(type="write", line=line, code_excerpt=excerpt_text,
                       detector=f"fs_{method}", framework="stdlib_node")


def _detect_browser_storage(chain: str, method: str, base: str, base_tokens: set,
                              line: int, excerpt_text: str,
                              collector: C.MovementCollector):
    """Détecte les accès localStorage / sessionStorage / IndexedDB / cookie."""
    # localStorage.setItem("k", "v")
    if base in BROWSER_STORAGE_OBJECTS or base.endswith("." + "localStorage") \
            or base.endswith(".sessionStorage"):
        storage = "localStorage" if "localStorage" in base else "sessionStorage"
        if method in BROWSER_STORAGE_READ:
            collector.add(type="read", line=line, code_excerpt=excerpt_text,
                           detector=f"{storage}_{method}",
                           framework="browser_storage")
        elif method in BROWSER_STORAGE_WRITE:
            collector.add(type="write", line=line, code_excerpt=excerpt_text,
                           detector=f"{storage}_{method}",
                           framework="browser_storage")
        return

    # IndexedDB via idb : db.get / db.put / db.add / db.delete
    if "db" in base_tokens or "idb" in base_tokens:
        if method in IDB_READ and method != "get":
            # Cas spécifique : getAll, getKey, getAllKeys, count
            collector.add(type="read", line=line, code_excerpt=excerpt_text,
                           detector=f"idb_{method}", framework="indexeddb",
                           confidence="medium")
        elif method in IDB_WRITE:
            collector.add(type="write", line=line, code_excerpt=excerpt_text,
                           detector=f"idb_{method}", framework="indexeddb",
                           confidence="medium")

    # Dexie : table.put(), table.get(), table.where()
    if "dexie" in base_tokens or "table" in base_tokens:
        if method in DEXIE_READ:
            collector.add(type="read", line=line, code_excerpt=excerpt_text,
                           detector=f"dexie_{method}", framework="dexie",
                           confidence="medium")
        elif method in DEXIE_WRITE:
            collector.add(type="write", line=line, code_excerpt=excerpt_text,
                           detector=f"dexie_{method}", framework="dexie",
                           confidence="medium")


def _detect_member_storage(node, source_bytes: bytes, file_path: str,
                            collector: C.MovementCollector):
    """Détecte les accès directs à document.cookie en lecture/écriture.

    document.cookie = "..." (write) ou let c = document.cookie (read).
    Cette détection se fait au niveau du member_expression, pas du call.
    """
    obj = C.field(node, "object")
    prop = C.field(node, "property")
    if obj is None or prop is None:
        return
    obj_text = C.node_text(obj, source_bytes)
    prop_text = C.node_text(prop, source_bytes)
    if obj_text == "document" and prop_text == "cookie":
        # On regarde le parent pour différencier read/write
        parent = node.parent
        if parent is not None and parent.type == "assignment_expression":
            left = C.field(parent, "left")
            if left is not None and id(left) == id(node):
                # document.cookie = "..."
                collector.add(
                    type="write", line=C.line_of(node),
                    code_excerpt=C.node_text(parent, source_bytes),
                    detector="document_cookie_write", framework="browser_storage",
                )
                return
        # Sinon : lecture
        collector.add(
            type="read", line=C.line_of(node),
            code_excerpt=C.node_text(node, source_bytes),
            detector="document_cookie_read", framework="browser_storage",
        )


def _detect_queue(chain: str, method: str, base: str, base_tokens: set,
                   line: int, excerpt_text: str, collector: C.MovementCollector):
    """Détecte les opérations BullMQ / Bull : queue.add(...)."""
    if method not in BULL_QUEUE_WRITE_METHODS:
        return
    # Heuristique : la base ressemble à une queue
    queue_hints = {"queue", "bull", "worker", "job"}
    if not (base_tokens & queue_hints):
        return
    collector.add(
        type="write", line=line, code_excerpt=excerpt_text,
        detector="bullmq_add", framework="bullmq",
        confidence="medium",
    )


def _detect_websocket(chain: str, method: str, base: str, base_tokens: set,
                       line: int, excerpt_text: str,
                       collector: C.MovementCollector):
    """WebSocket : ws.send (Exit), socket.emit (Exit), socket.on (Entry)."""
    ws_hints = {"ws", "socket", "io", "websocket"}
    if not (base_tokens & ws_hints):
        return
    if method == "send" or method == "emit":
        collector.add(
            type="exit", line=line, code_excerpt=excerpt_text,
            detector=f"ws_{method}", framework="websocket",
            confidence="medium",
        )
    elif method == "on":
        # Entry : ws.on("message", handler)
        collector.add(
            type="entry", line=line, code_excerpt=excerpt_text,
            detector="ws_on", framework="websocket",
            confidence="medium",
        )


def _detect_cli(chain: str, method: str, base: str, base_tokens: set,
                 line: int, excerpt_text: str, collector: C.MovementCollector):
    """CLI Commander/Yargs : program.command(...).action(...)."""
    if method == "command" and any(t in base_tokens for t in ("program", "commander")):
        collector.add(
            type="entry", line=line, code_excerpt=excerpt_text,
            detector="commander_command", framework="commander",
            confidence="medium",
        )


# ===========================================================================
# new_expression : new WebSocket.Server, new Worker, etc.
# ===========================================================================

def _detect_new_expr(node, source_bytes: bytes, file_path: str,
                      collector: C.MovementCollector):
    """Détecte les instanciations spéciales (WebSocket Server, BullMQ Worker)."""
    chain = C.call_chain(node, source_bytes)
    last = C.short_name(chain)

    # new WebSocket.Server({...}) → expose un endpoint WS = Entry au niveau application
    if last in ("Server", "WebSocketServer"):
        tokens = C.tokenize_base(chain)
        if "websocket" in tokens or "ws" in tokens:
            collector.add(
                type="entry", line=C.line_of(node),
                code_excerpt=C.node_text(node, source_bytes),
                detector="ws_server", framework="websocket",
            )

    # new Worker("queue-name", handler) → consume queue = Entry
    if last == "Worker":
        tokens = C.tokenize_base(chain)
        if "bullmq" in tokens or "bull" in tokens or "worker" in tokens:
            collector.add(
                type="entry", line=C.line_of(node),
                code_excerpt=C.node_text(node, source_bytes),
                detector="bullmq_worker", framework="bullmq",
                confidence="medium",
            )
