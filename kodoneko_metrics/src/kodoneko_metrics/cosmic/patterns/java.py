"""
Patterns COSMIC pour Java (tree-sitter-java).

Frameworks couverts (P1)
------------------------
**Backend Spring** : @RestController, @Controller + @GetMapping, @PostMapping,
   @PutMapping, @DeleteMapping, @PatchMapping, @RequestMapping
**Spring Data JPA** : repository.findX/getX/saveX/deleteX/... (heuristique préfixe)
**JPA EntityManager** : entityManager.find/persist/merge/remove/createQuery
**JDBC** : PreparedStatement.executeQuery/executeUpdate, Statement.execute*
**Spring JdbcTemplate** : query/queryForObject/queryForList/update/batchUpdate
**Spring Cache via Redis** : redisTemplate.opsForValue/opsForHash + get/set
**Queue (Entry)** : @KafkaListener, @RabbitListener, @JmsListener, @SqsListener
**Queue (Exit)** : kafkaTemplate.send, rabbitTemplate.convertAndSend, jmsTemplate.send
**HTTP client** : RestTemplate, WebClient, HttpClient (Java 11+), OkHttp,
   Apache HttpClient
**File I/O** : Files.readString/readAllLines/readAllBytes/write/writeString,
   BufferedReader/Writer, FileReader/Writer
**CLI** : picocli @Command

Décisions de design Java
------------------------
Voir ``DESIGN_DECISIONS.md`` pour la justification complète. Référentiel
d'identifiants des décisions appliquées dans ce module :

  D-JAVA1  : Détection au niveau **appel**, pas au niveau interface
             Une méthode `findByEmail()` d'une interface Repository est comptée
             quand elle est appelée, pas quand elle est déclarée. Cohérent
             avec D-JS1 (TypeORM/Sequelize).

  D-JAVA2  : Préfixes Spring Data JPA pour classifier les méthodes dérivées
             find/get/read/query/count/exists/stream → read
             save/insert/update/delete/remove/persist → write
             Contexte requis : la base doit être un Repository (tokens
             incluant 'repository', 'repo', 'dao').

  D-JAVA3  : Controllers détectés par annotation au niveau classe
             @RestController ou @Controller sur la classe + @XxxMapping
             sur la méthode = endpoint. Une classe non annotée même avec
             @GetMapping sur méthode ne sera pas détectée (correct selon Spring).

  D-JAVA4  : EntityManager / Session détectés par contexte
             Tokens 'entitymanager', 'em', 'session' déclenchent la détection
             des méthodes JPA standardisées (find, persist, merge, remove).

  D-JAVA5  : Listeners de messagerie = Entry
             @KafkaListener, @RabbitListener, @JmsListener, @SqsListener,
             @StreamListener génèrent un Entry à la méthode décorée.

  D-JAVA6  : Producteurs de messagerie = Exit
             KafkaTemplate.send, RabbitTemplate.convertAndSend, JmsTemplate.send
             génèrent un Exit (sortie vers broker).

  D-JAVA7  : JDBC execute() ambigu → write, medium confidence
             executeQuery → read (high), executeUpdate → write (high),
             execute → write (medium) car polymorphe.

  D-JAVA8  : Spring Cache (@Cacheable, @CacheEvict, @CachePut) NON comptés
             Le cache est transparent côté code applicatif. Pour mesurer le
             cache effectif, compter les patterns RedisTemplate directement.

  D-JAVA9  : Spring Batch reporté à P2
             ItemReader/ItemWriter/Tasklet ont un modèle conceptuel à part,
             trop spécifique pour P1.

  D-JAVA10 : HTTP clients en mode practical uniquement
             RestTemplate, WebClient, HttpClient (Java 11+), OkHttp, Apache
             HttpClient. 1 call = 1 Write (req) + 1 Read (resp).
             En mode strict (ISO 19761), aucun de ces calls n'est compté.

  D-JAVA11 : File I/O — NIO Files + Reader/Writer
             Files.readString/readAllLines/write/writeString comptés.
             Constructeurs BufferedReader/FileReader/etc. comptés
             (medium confidence : peut être chaîné avec d'autres streams).

  D-JAVA12 : picocli @Command = Entry CLI
             Une méthode annotée @Command génère un Entry. Medium confidence
             car @Command peut être utilisé par d'autres frameworks
             (Spring Shell utilise picocli en interne).

  D-JAVA13 : Spring Data JPA scan présence dans la chaîne
             Cas : `repo.findById(id).orElseThrow()`. Reconstruction de la
             chaîne complète sans args, recherche du premier préfixe JPA.
             Cohérent avec D-JS7 (Drizzle).

  D-JAVA14 : Error messages HTTP Spring/JAX-RS (throw ResponseStatusException)
             comme Exit. (Équivalent D-PY10 Python pour Java.)
             Pré-passe pour identifier les body de méthodes endpoint
             (controllers Spring + listeners), puis détection des
             `throw new ResponseStatusException(...)` (26 classes
             SPRING_HTTP_EXCEPTIONS) avec frequency rule.

Limites assumées
----------------
- Code utilisant Spring AOP avec proxies dynamiques peut être manqué
- Classes abstraites annotées dont les sous-classes héritent peuvent
  ne pas être détectées
- Spring Cache (@Cacheable) non compté (D-JAVA8)
- Methods déclarées dans une interface Repository mais jamais appelées
  ne génèrent pas de mouvement (D-JAVA1) — cohérent avec la philosophie
  COSMIC (compter le travail effectif, pas le potentiel)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from typing import Optional

from ..models import CosmicMode, CosmicMovement
from . import _common as C


# ===========================================================================
# Annotations Spring — endpoints HTTP
# ===========================================================================

# Annotations qui marquent une méthode comme endpoint HTTP
SPRING_HTTP_METHOD_ANNOTATIONS = {
    "GetMapping", "PostMapping", "PutMapping", "DeleteMapping",
    "PatchMapping", "RequestMapping",
}

# Annotations qui marquent une classe comme controller
SPRING_CONTROLLER_ANNOTATIONS = {"RestController", "Controller"}

# Annotations queue/messaging (Entry)
SPRING_LISTENER_ANNOTATIONS = {
    "KafkaListener", "RabbitListener", "JmsListener", "SqsListener",
    "StreamListener", "EventListener",
}

# Annotations CLI picocli
PICOCLI_ANNOTATIONS = {"Command"}


# ===========================================================================
# D-JAVA14 (L9 fix pour Java) — Classes d'exception HTTP Spring + JAX-RS
# ===========================================================================

# Classes d'exception HTTP Spring + JAX-RS standard. Détectées comme Exit
# error avec frequency rule (1 par endpoint, même si plusieurs throws).
SPRING_HTTP_EXCEPTIONS = {
    # Spring Web
    "ResponseStatusException",
    # Spring REST client errors
    "HttpClientErrorException", "HttpServerErrorException",
    "RestClientResponseException", "UnknownContentTypeException",
    # Spring Web custom common
    "MethodArgumentNotValidException", "MissingServletRequestParameterException",
    "HttpMessageNotReadableException", "HttpRequestMethodNotSupportedException",
    "HttpMediaTypeNotSupportedException", "ServletRequestBindingException",
    "MissingPathVariableException", "NoHandlerFoundException",
    # JAX-RS / Jakarta REST
    "WebApplicationException", "ClientErrorException", "ServerErrorException",
    "BadRequestException", "ForbiddenException", "NotAcceptableException",
    "NotAllowedException", "NotAuthorizedException", "NotFoundException",
    "NotSupportedException", "RedirectionException",
    "InternalServerErrorException", "ServiceUnavailableException",
}


# ===========================================================================
# Spring Data JPA — heuristique préfixe sur méthode
# ===========================================================================

# Préfixes de méthodes Spring Data JPA → read
JPA_READ_PREFIXES = ("find", "get", "read", "query", "count", "exists", "stream")

# Préfixes → write
JPA_WRITE_PREFIXES = ("save", "insert", "update", "delete", "remove", "persist", "merge")


# Bases qui indiquent qu'on est sur un repository Spring Data
JPA_REPO_HINTS = {"repository", "repo", "dao"}


# ===========================================================================
# JPA EntityManager / Hibernate Session
# ===========================================================================

ENTITY_MANAGER_READ = {"find", "getReference", "createQuery", "createNamedQuery",
                        "createNativeQuery", "createStoredProcedureQuery",
                        "createCriteriaQuery", "getResultList", "getSingleResult",
                        "getResultStream"}
ENTITY_MANAGER_WRITE = {"persist", "merge", "remove", "refresh", "flush", "detach"}

ENTITY_MANAGER_HINTS = {"entitymanager", "em", "session", "sessionfactory"}


# ===========================================================================
# JDBC / Spring JdbcTemplate
# ===========================================================================

JDBC_READ_METHODS = {"executeQuery", "getResultSet"}
JDBC_WRITE_METHODS = {"executeUpdate", "executeLargeUpdate", "addBatch", "executeBatch"}
JDBC_AMBIGUOUS_METHODS = {"execute", "executeLargeBatch"}  # peut être les deux

JDBC_TEMPLATE_READ = {"query", "queryForObject", "queryForList", "queryForMap",
                       "queryForRowSet", "queryForStream"}
JDBC_TEMPLATE_WRITE = {"update", "batchUpdate", "execute"}

JDBC_TEMPLATE_HINTS = {"jdbctemplate", "namedparameterjdbctemplate"}


# ===========================================================================
# Queue (Spring) — Exit côté producteur
# ===========================================================================

# kafkaTemplate.send / rabbitTemplate.send/convertAndSend / jmsTemplate.send
QUEUE_TEMPLATE_SEND = {"send", "convertAndSend", "sendAndReceive", "convertSendAndReceive"}
QUEUE_TEMPLATE_HINTS = {"kafkatemplate", "rabbittemplate", "jmstemplate",
                         "streambridge", "queueclient", "sqstemplate"}


# ===========================================================================
# HTTP client
# ===========================================================================

REST_TEMPLATE_METHODS = {
    "getForObject", "getForEntity", "postForObject", "postForEntity", "postForLocation",
    "put", "delete", "patchForObject", "exchange", "execute",
    "headForHeaders", "optionsForAllow",
}

WEB_CLIENT_TERMINAL = {"retrieve", "exchange", "exchangeToMono", "exchangeToFlux"}

JAVA11_HTTP_METHODS = {"send", "sendAsync"}

OKHTTP_METHODS = {"execute", "enqueue"}

HTTP_CLIENT_HINTS_POSITIVE = {
    "resttemplate", "webclient", "httpclient", "okhttpclient",
    "rest", "api", "http", "https",
}
HTTP_CLIENT_HINTS_NEGATIVE = {
    "jdbctemplate", "rediscache", "kafkatemplate", "rabbittemplate", "jmstemplate",
    "entitymanager", "sessionfactory",
}


# ===========================================================================
# Redis (Spring RedisTemplate ou Jedis)
# ===========================================================================

REDIS_OPS_HINTS = {"redistemplate", "stringredistemplate", "reactiveredistemplate",
                    "jedis", "lettuce"}

REDIS_VALUE_OP_READ = {"get", "multiGet", "size", "getRange"}
REDIS_VALUE_OP_WRITE = {"set", "setIfAbsent", "setIfPresent", "increment",
                         "decrement", "append"}

REDIS_HASH_OP_READ = {"get", "entries", "keys", "values", "size", "hasKey"}
REDIS_HASH_OP_WRITE = {"put", "putAll", "putIfAbsent", "delete", "increment"}

REDIS_LIST_OP_READ = {"range", "index", "size"}
REDIS_LIST_OP_WRITE = {"leftPush", "rightPush", "leftPop", "rightPop", "remove"}

REDIS_SET_OP_READ = {"members", "isMember", "size", "intersect", "union", "difference"}
REDIS_SET_OP_WRITE = {"add", "remove", "pop"}

REDIS_ZSET_OP_READ = {"range", "rangeByScore", "rank", "score", "size"}
REDIS_ZSET_OP_WRITE = {"add", "remove", "incrementScore"}


# ===========================================================================
# File I/O
# ===========================================================================

FILES_READ_METHODS = {"readString", "readAllLines", "readAllBytes", "readAttributes",
                       "lines", "newBufferedReader", "newInputStream",
                       "readSymbolicLink", "list", "walk"}
FILES_WRITE_METHODS = {"writeString", "write", "writeBytes", "createFile",
                        "createDirectory", "createDirectories", "delete",
                        "deleteIfExists", "copy", "move", "newBufferedWriter",
                        "newOutputStream"}

# Constructeurs de Reader/Writer = read/write
READER_CLASSES = {"FileReader", "BufferedReader", "FileInputStream",
                   "InputStreamReader", "Scanner"}
WRITER_CLASSES = {"FileWriter", "BufferedWriter", "FileOutputStream",
                   "OutputStreamWriter", "PrintWriter"}


# ===========================================================================
# Détecteur principal
# ===========================================================================

def detect_java_movements(
    tree,
    source_bytes: bytes,
    file_path: str,
    *,
    mode: CosmicMode = "practical",
) -> list[CosmicMovement]:
    """Détecte les mouvements COSMIC dans un fichier Java via tree-sitter."""
    # Bind source_bytes for annotation helpers that don't pass it
    global _SOURCE_BYTES
    old_source = _SOURCE_BYTES
    _SOURCE_BYTES = source_bytes

    try:
        collector = C.MovementCollector(file_path)

        # Pré-passe unique (fusionnée) : marque les calls d'annotations à skip
        # ET identifie les body de méthodes endpoint. Une seule traversée.
        _prepass_java(tree.root_node, source_bytes, collector)

        # Passe principale
        def visit(node):
            if collector.should_skip(node):
                return False

            # Class declarations : controllers Spring
            if node.type == "class_declaration":
                _detect_spring_controller(node, source_bytes, collector)
                return True

            # Method declarations : listeners standalone
            if node.type == "method_declaration":
                _detect_standalone_listener(node, source_bytes, collector)
                return True

            # Method invocations : ORM, JDBC, HTTP, Redis, file, queue
            if node.type == "method_invocation":
                return _detect_invocation(node, source_bytes, file_path, mode, collector)

            # Object creations : new FileReader, new BufferedWriter, etc.
            if node.type == "object_creation_expression":
                _detect_object_creation(node, source_bytes, collector)
                return True

            # D-JAVA14 (L9 fix) : throw new ResponseStatusException dans endpoint
            if node.type == "throw_statement":
                _detect_http_throw_java(node, source_bytes, collector)
                return True

            return True

        C.walk(tree.root_node, visit)
        return collector.movements
    finally:
        _SOURCE_BYTES = old_source


# ===========================================================================
# Pré-passe unique (fusionnée)
# ===========================================================================

def _prepass_java(node, source_bytes: bytes, collector: C.MovementCollector):
    """Pré-passe unique Java : combine deux responsabilités en une traversée.

    1. Marque les method_invocation dans les annotations (skip).
    2. Identifie les body de méthodes endpoint (controllers Spring + listeners)
       pour D-JAVA14 (L9 : throw ResponseStatusException comme Exit error).

    Fusionner ces deux passes (auparavant `_mark_annotation_calls` +
    `_collect_endpoint_method_bodies_java`) évite une traversée AST redondante.
    """
    ntype = node.type

    # (1) Annotations : marquer les invocations descendantes pour skip
    if ntype in ("annotation", "marker_annotation"):
        for sub in _all_invocation_descendants(node):
            collector.mark_skip(sub)
        # Les enfants d'une annotation ne contiennent pas de classe à traiter
        # mais on continue la descente pour rester simple (peu coûteux).

    # (2) Classes : identifier les méthodes endpoint
    elif ntype == "class_declaration":
        _collect_endpoint_bodies_in_class(node, source_bytes, collector)

    # (3) D-JAVA2 fix : champs/paramètres typés *Repository → variables repo
    elif ntype in ("field_declaration", "formal_parameter"):
        _collect_repository_var(node, source_bytes, collector)

    for child in node.children:
        _prepass_java(child, source_bytes, collector)


def _collect_repository_var(node, source_bytes: bytes,
                              collector: C.MovementCollector):
    """Enregistre le nom d'une variable dont le TYPE est un repository.

    Détecte les patterns :
        private final OwnerRepository owners;        (field_declaration)
        public OwnerController(OwnerRepository owners) (formal_parameter)

    Le signal fiable est le type (suffixe Repository/Repo/Dao), pas le nom
    de la variable. Idiomatique Spring : `private final OwnerRepository owners`.
    """
    type_node = C.field(node, "type")
    if type_node is None:
        return
    type_name = C.node_text(type_node, source_bytes).rsplit(".", 1)[-1]
    # Retirer les génériques : JpaRepository<Owner, Integer> → JpaRepository
    if "<" in type_name:
        type_name = type_name.split("<", 1)[0]
    if not any(type_name.endswith(suffix) for suffix in
               ("Repository", "Repo", "Dao", "DAO")):
        return

    # Extraire le(s) nom(s) de variable déclaré(s)
    # field_declaration : variable_declarator(s) avec field "name"
    # formal_parameter : field "name" direct
    if node.type == "formal_parameter":
        name_node = C.field(node, "name")
        if name_node is not None:
            collector.repository_vars.add(C.node_text(name_node, source_bytes))
    else:  # field_declaration
        for child in C.named_children(node):
            if child.type == "variable_declarator":
                name_node = C.field(child, "name")
                if name_node is not None:
                    collector.repository_vars.add(
                        C.node_text(name_node, source_bytes))


def _all_invocation_descendants(node):
    """Yield tous les method_invocation descendants."""
    if node.type == "method_invocation":
        yield node
    for child in node.children:
        yield from _all_invocation_descendants(child)


def _collect_endpoint_bodies_in_class(class_node, source_bytes: bytes,
                                        collector: C.MovementCollector):
    """Identifie les body de méthodes endpoint d'une classe (D-JAVA14 L9).

    Une méthode est endpoint si :
    - classe @Controller/@RestController + méthode @XxxMapping, OU
    - méthode avec annotation listener (@KafkaListener, etc.)
    """
    class_annotations = _get_annotations(class_node, source_bytes)
    is_controller = any(
        _annotation_short_name(a) in SPRING_CONTROLLER_ANNOTATIONS
        for a in class_annotations
    )
    implements_openapi = is_controller and _implements_openapi_interface(
        class_node, source_bytes)
    body = C.field(class_node, "body")
    if body is None:
        return

    for member in C.named_children(body):
        if member.type != "method_declaration":
            continue
        method_annotations = _get_annotations(member, source_bytes)

        is_endpoint = False
        # Endpoint HTTP : méthode @XxxMapping dans une classe controller
        if is_controller and method_annotations:
            for anno in method_annotations:
                if _annotation_short_name(anno) in SPRING_HTTP_METHOD_ANNOTATIONS:
                    is_endpoint = True
                    break
        # L-OAPI : endpoint OpenAPI implémenté (@Override ResponseEntity)
        if not is_endpoint and implements_openapi:
            if _is_openapi_endpoint_method(member, method_annotations, source_bytes):
                is_endpoint = True
        # Listener (Kafka/Rabbit/JMS/SQS) : endpoint COSMIC indépendamment
        if not is_endpoint and method_annotations:
            for anno in method_annotations:
                if _annotation_short_name(anno) in SPRING_LISTENER_ANNOTATIONS:
                    is_endpoint = True
                    break

        if is_endpoint:
            method_body = C.field(member, "body")
            if method_body is not None:
                collector.endpoint_method_bodies.add(id(method_body))


def _detect_http_throw_java(throw_node, source_bytes: bytes,
                               collector: C.MovementCollector):
    """Détecte `throw new ResponseStatusException(...)` dans un endpoint.

    Frequency rule (D-JAVA14, cohérent avec D-PY10 / D-JS9) : 1 seul Exit
    error par endpoint, même si plusieurs throws différents.
    """
    # Le child principal d'un throw_statement Java est l'expression jetée
    thrown = None
    for child in C.named_children(throw_node):
        thrown = child
        break
    if thrown is None:
        return

    # `throw new XxxException(...)` (object_creation_expression)
    exc_name = ""
    if thrown.type == "object_creation_expression":
        type_node = C.field(thrown, "type")
        if type_node is not None:
            full_name = C.node_text(type_node, source_bytes)
            # `org.springframework.web.server.ResponseStatusException` → "ResponseStatusException"
            exc_name = full_name.rsplit(".", 1)[-1]
            # Gérer aussi les types génériques : ResponseStatusException<...> → ResponseStatusException
            if "<" in exc_name:
                exc_name = exc_name.split("<", 1)[0]

    if exc_name not in SPRING_HTTP_EXCEPTIONS:
        return

    # Remonter vers le block englobant pour trouver le method body
    parent = throw_node.parent
    containing_body = None
    while parent is not None:
        # En tree-sitter-java, le body d'une méthode est un `block`
        if parent.type == "block":
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
        framework="spring", confidence="medium",
    )


# ===========================================================================
# Spring controllers
# ===========================================================================

def _detect_spring_controller(class_node, source_bytes: bytes,
                                collector: C.MovementCollector):
    """Détecte une classe Spring controller et ses endpoints.

    Une classe est considérée comme controller si elle a une annotation
    @RestController ou @Controller (avec ou sans package préfixe).
    Chaque méthode décorée avec @GetMapping/@PostMapping/@PutMapping/
    @DeleteMapping/@PatchMapping/@RequestMapping est un Entry.
    """
    # Vérifier les annotations de la classe
    class_annotations = _get_annotations(class_node, source_bytes)
    is_controller = any(
        _annotation_short_name(a) in SPRING_CONTROLLER_ANNOTATIONS
        for a in class_annotations
    )

    # L-OAPI fix : controller qui implémente une interface OpenAPI générée
    # (`implements OwnersApi`). Les annotations HTTP sont sur l'interface,
    # pas sur cette classe. Heuristique : si controller ET implémente une
    # interface dont le nom finit par "Api"/"Controller", traiter les méthodes
    # publiques @Override retournant ResponseEntity comme endpoints.
    # Confidence medium : on ne peut pas connaître le verbe HTTP exact
    # (GET/POST) sans lire l'interface (analyse inter-fichiers, hors scope).
    implements_openapi = is_controller and _implements_openapi_interface(
        class_node, source_bytes)

    body = C.field(class_node, "body")
    if body is None:
        return

    # Parcourir les méthodes
    for member in C.named_children(body):
        if member.type != "method_declaration":
            continue

        method_annotations = _get_annotations(member, source_bytes)

        # 1. Endpoint HTTP standard (annotation @XxxMapping directe)
        if is_controller and method_annotations:
            matched = False
            for anno in method_annotations:
                anno_name = _annotation_short_name(anno)
                if anno_name in SPRING_HTTP_METHOD_ANNOTATIONS:
                    _emit_entry_with_returns(
                        member, source_bytes, collector,
                        detector=f"spring_{_camel_to_snake(anno_name)}",
                        framework="spring",
                    )
                    matched = True
                    break
            if matched:
                continue

        # 1b. L-OAPI : endpoint OpenAPI (méthode @Override : ResponseEntity)
        if implements_openapi and _is_openapi_endpoint_method(
                member, method_annotations, source_bytes):
            _emit_entry_with_returns(
                member, source_bytes, collector,
                detector="spring_openapi_impl",
                framework="spring",
            )
            continue

        if not method_annotations:
            continue

        # 2. Listener (Kafka/Rabbit/JMS/SQS) — indépendant du fait que ce soit
        #    un controller ou un @Service/@Component
        for anno in method_annotations:
            anno_name = _annotation_short_name(anno)
            if anno_name in SPRING_LISTENER_ANNOTATIONS:
                framework = _listener_framework(anno_name)
                _emit_entry_with_returns(
                    member, source_bytes, collector,
                    detector=f"{framework}_listener",
                    framework=framework,
                )
                break

        # 3. picocli @Command sur méthode (rare mais possible)
        for anno in method_annotations:
            anno_name = _annotation_short_name(anno)
            if anno_name in PICOCLI_ANNOTATIONS:
                _emit_entry_with_returns(
                    member, source_bytes, collector,
                    detector="picocli_command", framework="picocli",
                )
                break


def _implements_openapi_interface(class_node, source_bytes: bytes) -> bool:
    """True si la classe implemente une interface dont le nom suggere une API
    generee (suffixe "Api" ou "Controller").

    En tree-sitter-java, les interfaces implementees sont sous le champ
    interfaces / super_interfaces. On parcourt les descendants pour rester
    robuste aux variations de grammaire.
    """
    for child in class_node.children:
        if child.type in ("super_interfaces", "interfaces"):
            for tname in _iter_type_identifiers(child, source_bytes):
                name = tname.rsplit(".", 1)[-1]
                if "<" in name:
                    name = name.split("<", 1)[0]
                if name.endswith("Api") or name.endswith("Controller"):
                    return True
    return False


def _iter_type_identifiers(node, source_bytes: bytes):
    """Yield les textes des type_identifier descendants d'un noeud."""
    if node.type in ("type_identifier", "scoped_type_identifier"):
        yield C.node_text(node, source_bytes)
    for child in node.children:
        yield from _iter_type_identifiers(child, source_bytes)


def _is_openapi_endpoint_method(method_node, method_annotations,
                                  source_bytes: bytes) -> bool:
    """True si une methode est un endpoint OpenAPI implemente.

    Heuristique (confidence medium) : methode @Override retournant
    ResponseEntity<...> (signature typique des controllers OpenAPI).
    """
    has_override = any(
        _annotation_short_name(a) == "Override" for a in method_annotations
    )
    if not has_override:
        return False
    type_node = C.field(method_node, "type")
    if type_node is None:
        return False
    ret_type = C.node_text(type_node, source_bytes).rsplit(".", 1)[-1]
    if "<" in ret_type:
        ret_type = ret_type.split("<", 1)[0]
    return ret_type == "ResponseEntity"


def _detect_standalone_listener(method_node, source_bytes: bytes,
                                  collector: C.MovementCollector):
    """Détecte les listeners hors classe controller (Service/Component classique)."""
    # Cette fonction est appelée pour TOUTE méthode. On ne traite que les
    # listeners ici car les endpoints HTTP requièrent une classe Controller.
    # Pour éviter le double-traitement avec _detect_spring_controller, on
    # vérifie que le parent direct (class) n'est PAS déjà géré.

    # Trouver la classe englobante
    parent = method_node.parent
    enclosing_class = None
    while parent is not None:
        if parent.type == "class_declaration":
            enclosing_class = parent
            break
        parent = parent.parent

    if enclosing_class is None:
        return

    # Si la classe englobante est un controller, _detect_spring_controller
    # s'occupe déjà des listeners de cette classe → skip ici
    class_annos = _get_annotations(enclosing_class, source_bytes)
    if any(_annotation_short_name(a) in SPRING_CONTROLLER_ANNOTATIONS
            for a in class_annos):
        return

    # Sinon, on traite uniquement les listeners (pas les endpoints HTTP)
    method_annotations = _get_annotations(method_node, source_bytes)
    if not method_annotations:
        return

    for anno in method_annotations:
        anno_name = _annotation_short_name(anno)
        if anno_name in SPRING_LISTENER_ANNOTATIONS:
            framework = _listener_framework(anno_name)
            _emit_entry_with_returns(
                method_node, source_bytes, collector,
                detector=f"{framework}_listener",
                framework=framework,
            )
            break


def _listener_framework(annotation_name: str) -> str:
    """Mappe une annotation de listener à son nom de framework."""
    if "Kafka" in annotation_name:
        return "kafka"
    if "Rabbit" in annotation_name:
        return "rabbitmq"
    if "Jms" in annotation_name:
        return "jms"
    if "Sqs" in annotation_name:
        return "sqs"
    if "Stream" in annotation_name:
        return "spring_cloud_stream"
    return "spring_events"


def _emit_entry_with_returns(method_node, source_bytes: bytes,
                                collector: C.MovementCollector,
                                detector: str, framework: str):
    """Émet 1 Entry pour la méthode + 1 Exit pour chaque `return` interne."""
    name_node = C.field(method_node, "name")
    name = C.node_text(name_node, source_bytes) if name_node else "?"
    collector.add(
        type="entry", line=C.line_of(method_node),
        code_excerpt=f"{name}(...)",
        detector=detector, framework=framework,
    )
    _add_implicit_returns(method_node, source_bytes, collector,
                           detector=f"{detector}_return", framework=framework)


def _add_implicit_returns(method_node, source_bytes: bytes,
                            collector: C.MovementCollector,
                            detector: str, framework: str):
    """Pour chaque return dans la méthode (hors fonctions imbriquées) = 1 Exit."""
    def walk(n, depth=0):
        # Skip les lambdas et classes imbriquées
        if n.type in ("lambda_expression", "method_declaration",
                       "class_declaration") and depth > 0:
            return
        if n.type == "return_statement":
            collector.add(
                type="exit", line=C.line_of(n),
                code_excerpt=C.node_text(n, source_bytes),
                detector=detector, framework=framework,
                confidence="medium",
            )
        for c in n.children:
            walk(c, depth + 1 if n.type in (
                "lambda_expression", "method_declaration",
                "class_declaration") else depth)
    body = C.field(method_node, "body")
    if body is not None:
        walk(body, depth=0)


# ===========================================================================
# Annotations helpers
# ===========================================================================

def _get_annotations(node, source_bytes: bytes) -> list:
    """Récupère les annotations d'une déclaration (class ou method).

    Les annotations sont des enfants frères qui précèdent le node, ou
    des enfants directs des `modifiers`.
    """
    annos = []
    # Tree-sitter-java : les annotations sont dans le bloc `modifiers`
    # qui est un enfant nommé du method_declaration / class_declaration.
    for child in node.children:
        if child.type == "modifiers":
            for sub in child.children:
                if sub.type in ("annotation", "marker_annotation"):
                    annos.append(sub)
    return annos


def _annotation_short_name(anno_node) -> str:
    """Extrait le nom court d'une annotation : @RestController → "RestController".

    Gère :
    - @Marker (marker_annotation, sans paren)
    - @Anno(...) (annotation avec arguments)
    - @com.foo.Anno (annotation qualifiée — on garde le dernier segment)
    """
    name_node = anno_node.child_by_field_name("name")
    if name_node is None:
        # Fallback : parcourir les enfants pour trouver l'identifier
        for child in anno_node.children:
            if child.type in ("identifier", "scoped_identifier"):
                name_node = child
                break
    if name_node is None:
        return ""
    # Pour scoped_identifier (com.foo.Bar), on veut "Bar"
    text = ""
    # _common.node_text n'est pas dispo sans source — on n'a pas accès ici
    # On utilise une astuce : reconstituer à partir des bornes
    # Mais on n'a pas le source_bytes ici → il faut le passer ou bien utiliser
    # le nom du noeud final
    if name_node.type == "scoped_identifier":
        # Le dernier enfant nommé est l'identifier final
        last = None
        for c in name_node.children:
            if c.type == "identifier":
                last = c
        if last is not None:
            return _node_text_via_bytes(last)
    return _node_text_via_bytes(name_node)


# Astuce : pour éviter de passer source_bytes partout, on stocke un getter
# global qui est setté au début du detect. Pas idéal mais évite la verbosité.
_SOURCE_BYTES: bytes = b""


def _node_text_via_bytes(node) -> str:
    return _SOURCE_BYTES[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _camel_to_snake(s: str) -> str:
    """GetMapping → get_mapping."""
    out = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


# ===========================================================================
# Method invocations — détection ORM / JDBC / HTTP / Redis / queue / file
# ===========================================================================

def _reconstruct_java_chain(node, source_bytes: bytes) -> str:
    """Reconstruit la chaîne complète d'un method_invocation Java.

    Pour `repo.findById(id).orElseThrow()`, retourne ``"repo.findById.orElseThrow"``
    (avec les noms de méthodes mais sans les arguments).

    Utilisé par D-JAVA13 pour identifier un préfixe JPA n'importe où dans la chaîne.
    """
    if node is None:
        return ""

    if node.type == "method_invocation":
        obj = node.child_by_field_name("object")
        name_node = node.child_by_field_name("name")
        method_name = C.node_text(name_node, source_bytes) if name_node else ""
        if obj is not None:
            base_chain = _reconstruct_java_chain(obj, source_bytes)
            return f"{base_chain}.{method_name}" if base_chain else method_name
        return method_name

    if node.type == "field_access":
        obj = node.child_by_field_name("object")
        field = node.child_by_field_name("field")
        field_name = C.node_text(field, source_bytes) if field else ""
        base_chain = _reconstruct_java_chain(obj, source_bytes)
        return f"{base_chain}.{field_name}" if base_chain else field_name

    if node.type == "identifier":
        return C.node_text(node, source_bytes)

    if node.type == "this":
        return "this"

    return ""


def _detect_invocation(node, source_bytes: bytes, file_path: str,
                        mode: CosmicMode, collector: C.MovementCollector) -> bool:
    """Détecte les mouvements liés à un method_invocation."""
    # Skip si c'est dans un call chaîné déjà traité
    if not _is_outer_invocation(node):
        return True

    method_node = node.child_by_field_name("name")
    object_node = node.child_by_field_name("object")

    if method_node is None:
        return True

    method = C.node_text(method_node, source_bytes)
    base = C.node_text(object_node, source_bytes) if object_node is not None else ""
    line = C.line_of(node)
    excerpt_text = C.node_text(node, source_bytes)
    base_tokens = C.tokenize_base(base)

    # D-JAVA13 : reconstruction de la chaîne complète pour les patterns
    # qui doivent inspecter toute la chaîne (Spring Data JPA chained).
    full_chain = _reconstruct_java_chain(node, source_bytes)

    # 1. Spring Data JPA (repository.findX/saveX/...)
    _detect_jpa_repository(method, base, base_tokens, line, excerpt_text,
                            collector, full_chain=full_chain)

    # 2. JPA EntityManager
    _detect_entity_manager(method, base, base_tokens, line, excerpt_text, collector)

    # 3. JDBC + JdbcTemplate
    _detect_jdbc(method, base, base_tokens, line, excerpt_text, collector)

    # 4. Queue templates (Exit)
    _detect_queue_send(method, base, base_tokens, line, excerpt_text, collector)

    # 5. HTTP clients (mode practical)
    _detect_http_client(method, base, base_tokens, line, excerpt_text, mode, collector)

    # 6. Redis (RedisTemplate)
    _detect_redis(method, base, base_tokens, line, excerpt_text, collector)

    # 7. File I/O (Files.X)
    _detect_files(method, base, base_tokens, line, excerpt_text, collector)

    return True


def _is_outer_invocation(node) -> bool:
    """True si ce method_invocation est la racine de sa chaîne.

    Pour éviter de double-compter : ``a.b().c().d()`` n'est compté qu'une fois
    (sur le ``.d()`` extérieur). Les inner b() et c() sont des sous-expressions.
    """
    parent = node.parent
    if parent is None:
        return True
    # Si le parent est un method_invocation dont c'est l'objet
    if parent.type == "method_invocation":
        obj = parent.child_by_field_name("object")
        if obj is not None and id(obj) == id(node):
            return False
    return True


def _detect_jpa_repository(method: str, base: str, base_tokens: set,
                            line: int, excerpt_text: str,
                            collector: C.MovementCollector,
                            full_chain: str = ""):
    """Spring Data JPA : userRepository.findById, .save, .deleteByEmail, etc.

    D-JAVA13 (ajouté lors de la revue adversariale) : on cherche un préfixe JPA
    n'importe où dans la chaîne, pas seulement au terminal. Permet de gérer
    `userRepository.findById(id).orElseThrow()` et `repository.findAll().stream().toList()`.

    D-JAVA2 fix (validation PetClinic) : on accepte aussi si la base est une
    variable dont le TYPE est un repository (collectée en pré-passe). Permet
    `this.owners.findById(...)` où `owners` est `private OwnerRepository owners`.
    """
    # Heuristique 1 : le base contient "repository" / "repo" / "dao"
    is_repo_context = any(t in base_tokens for t in JPA_REPO_HINTS)

    # Heuristique 2 : le base est un identifier qui se termine par
    # "Repository"/"Repo"/"Dao" (ex: ownerRepository.findById)
    if not is_repo_context:
        last_token = base.rsplit(".", 1)[-1]
        if any(last_token.endswith(suffix) for suffix in
               ("Repository", "Repo", "Dao", "DAO")):
            is_repo_context = True

    # Heuristique 3 (D-JAVA2 fix) : le dernier segment de la base est une
    # variable typée repository, collectée en pré-passe.
    # `this.owners.findById` → base="this.owners" → segment "owners".
    if not is_repo_context:
        last_segment = base.rsplit(".", 1)[-1]
        if last_segment in collector.repository_vars:
            is_repo_context = True

    if not is_repo_context:
        return

    # D-JAVA13 : chercher le premier maillon JPA dans la chaîne complète
    # (pas seulement le terminal). Cas : findById().orElseThrow().
    # full_chain est typiquement "userRepository.findById.orElseThrow".
    # Si non fourni, on retombe sur le terminal (compatibilité).
    chain_to_search = full_chain if full_chain else method

    chain_parts = chain_to_search.split(".") if "." in chain_to_search else [method]
    detected_method = None
    detected_kind = None  # 'read' ou 'write'

    for part in chain_parts:
        if not part:
            continue
        part_lower = part[0].lower() + part[1:]
        for p in JPA_READ_PREFIXES:
            if part_lower.startswith(p):
                detected_method = part
                detected_kind = "read"
                break
        if detected_method:
            break
        for p in JPA_WRITE_PREFIXES:
            if part_lower.startswith(p):
                detected_method = part
                detected_kind = "write"
                break
        if detected_method:
            break

    if detected_method is None:
        return

    collector.add(
        type=detected_kind, line=line, code_excerpt=excerpt_text,
        detector=f"jpa_repo_{detected_method}", framework="spring_data_jpa",
    )


def _detect_entity_manager(method: str, base: str, base_tokens: set,
                             line: int, excerpt_text: str,
                             collector: C.MovementCollector):
    """JPA EntityManager / Hibernate Session."""
    is_em_context = any(t in base_tokens for t in ENTITY_MANAGER_HINTS)
    # On accepte aussi les méthodes très spécifiques sans contexte fort
    very_specific = method in {"persist", "merge", "remove",
                                 "createNamedQuery", "createNativeQuery"}
    if not is_em_context and not very_specific:
        return

    if method in ENTITY_MANAGER_READ:
        collector.add(
            type="read", line=line, code_excerpt=excerpt_text,
            detector=f"jpa_em_{method}", framework="jpa",
            confidence="high" if is_em_context else "medium",
        )
    elif method in ENTITY_MANAGER_WRITE:
        collector.add(
            type="write", line=line, code_excerpt=excerpt_text,
            detector=f"jpa_em_{method}", framework="jpa",
            confidence="high" if is_em_context else "medium",
        )


def _detect_jdbc(method: str, base: str, base_tokens: set,
                  line: int, excerpt_text: str,
                  collector: C.MovementCollector):
    """JDBC brut + Spring JdbcTemplate."""
    # JDBC brut : PreparedStatement.executeQuery, etc.
    # Les noms de méthodes sont distinctifs, on ne demande pas de contexte fort
    if method in JDBC_READ_METHODS:
        collector.add(
            type="read", line=line, code_excerpt=excerpt_text,
            detector=f"jdbc_{method}", framework="jdbc",
            confidence="high",
        )
        return
    if method in JDBC_WRITE_METHODS:
        collector.add(
            type="write", line=line, code_excerpt=excerpt_text,
            detector=f"jdbc_{method}", framework="jdbc",
            confidence="high",
        )
        return

    # Spring JdbcTemplate
    is_jdbc_template = any(t in base_tokens for t in JDBC_TEMPLATE_HINTS)
    if not is_jdbc_template:
        return
    if method in JDBC_TEMPLATE_READ:
        collector.add(
            type="read", line=line, code_excerpt=excerpt_text,
            detector=f"jdbc_template_{method}", framework="jdbc_template",
        )
    elif method in JDBC_TEMPLATE_WRITE:
        collector.add(
            type="write", line=line, code_excerpt=excerpt_text,
            detector=f"jdbc_template_{method}", framework="jdbc_template",
        )


def _detect_queue_send(method: str, base: str, base_tokens: set,
                        line: int, excerpt_text: str,
                        collector: C.MovementCollector):
    """Producteurs Spring Kafka/RabbitMQ/JMS/SQS."""
    if method not in QUEUE_TEMPLATE_SEND:
        return
    if not any(t in base_tokens for t in QUEUE_TEMPLATE_HINTS):
        return

    # Déterminer le framework
    if "kafkatemplate" in base_tokens:
        framework = "kafka"
    elif "rabbittemplate" in base_tokens:
        framework = "rabbitmq"
    elif "jmstemplate" in base_tokens:
        framework = "jms"
    elif "sqstemplate" in base_tokens or "queueclient" in base_tokens:
        framework = "sqs"
    elif "streambridge" in base_tokens:
        framework = "spring_cloud_stream"
    else:
        framework = "queue"

    collector.add(
        type="exit", line=line, code_excerpt=excerpt_text,
        detector=f"{framework}_{method}", framework=framework,
    )


def _detect_http_client(method: str, base: str, base_tokens: set,
                         line: int, excerpt_text: str, mode: CosmicMode,
                         collector: C.MovementCollector):
    """RestTemplate, WebClient, HttpClient (Java 11+), OkHttp."""
    if mode != "practical":
        return

    # Exclure les hints négatifs (storage clients qui partagent des mots-clés)
    if base_tokens & HTTP_CLIENT_HINTS_NEGATIVE:
        return

    # 1. RestTemplate
    if method in REST_TEMPLATE_METHODS and "resttemplate" in base_tokens:
        _emit_http_pair(method, line, excerpt_text, collector,
                          detector=f"rest_template_{method}",
                          framework="rest_template")
        return

    # 2. WebClient (réactif) — détection sur le terminal (retrieve/exchange)
    if method in WEB_CLIENT_TERMINAL:
        # Le base est une chaîne fluent (webClient.get().uri(...)).
        # On regarde si la chaîne contient "webclient" dans ses tokens.
        if "webclient" in base_tokens or "webclient" in base.lower():
            _emit_http_pair(method, line, excerpt_text, collector,
                              detector=f"web_client_{method}",
                              framework="web_client")
            return

    # 3. Java 11+ HttpClient (httpClient.send(request, handler))
    if method in JAVA11_HTTP_METHODS:
        if "httpclient" in base_tokens and "okhttpclient" not in base_tokens:
            _emit_http_pair(method, line, excerpt_text, collector,
                              detector=f"java11_http_{method}",
                              framework="java_http")
            return

    # 4. OkHttp (call.execute() / call.enqueue())
    if method in OKHTTP_METHODS:
        if "okhttpclient" in base_tokens or "okhttp" in base_tokens \
                or "call" in base_tokens:
            # "call" est ambigu — on n'active que si le mot OkHttp apparaît
            if "okhttpclient" in base_tokens or "okhttp" in base_tokens:
                _emit_http_pair(method, line, excerpt_text, collector,
                                  detector=f"okhttp_{method}",
                                  framework="okhttp")
                return


def _emit_http_pair(method: str, line: int, excerpt_text: str,
                     collector: C.MovementCollector,
                     detector: str, framework: str):
    """Émet 1 Write (req) + 1 Read (resp) pour un appel HTTP sortant."""
    collector.add(
        type="write", line=line, code_excerpt=excerpt_text + " [req]",
        detector=detector + "_req", framework=framework,
    )
    collector.add(
        type="read", line=line, code_excerpt=excerpt_text + " [resp]",
        detector=detector + "_resp", framework=framework,
    )


def _detect_redis(method: str, base: str, base_tokens: set,
                   line: int, excerpt_text: str,
                   collector: C.MovementCollector):
    """RedisTemplate / Jedis : opsForValue().get/set/..., etc.

    Heuristique : on regarde la base. Si elle contient "redistemplate" ou
    "opsForValue/opsForHash/opsForList/opsForSet/opsForZSet" dans son
    sous-chemin, on est dans Redis.
    """
    base_lower = base.lower()
    is_redis = any(t in base_tokens for t in REDIS_OPS_HINTS)
    if not is_redis:
        # Cas : redisTemplate.opsForValue().get(...)
        # Le base est `redisTemplate.opsForValue()` — token "redistemplate" inclus
        if "opsfor" not in base_lower:
            return

    # Classifier selon l'opération
    if "opsforvalue" in base_lower or "valueoperations" in base_lower:
        reads, writes = REDIS_VALUE_OP_READ, REDIS_VALUE_OP_WRITE
        op = "value"
    elif "opsforhash" in base_lower or "hashoperations" in base_lower:
        reads, writes = REDIS_HASH_OP_READ, REDIS_HASH_OP_WRITE
        op = "hash"
    elif "opsforlist" in base_lower or "listoperations" in base_lower:
        reads, writes = REDIS_LIST_OP_READ, REDIS_LIST_OP_WRITE
        op = "list"
    elif "opsforset" in base_lower or "setoperations" in base_lower:
        reads, writes = REDIS_SET_OP_READ, REDIS_SET_OP_WRITE
        op = "set"
    elif "opsforzset" in base_lower or "zsetoperations" in base_lower:
        reads, writes = REDIS_ZSET_OP_READ, REDIS_ZSET_OP_WRITE
        op = "zset"
    else:
        # Cas direct redisTemplate.delete/hasKey/expire/...
        reads = {"hasKey", "keys", "type", "getExpire"}
        writes = {"delete", "expire", "expireAt", "rename", "convertAndSend"}
        op = "core"

    if method in reads:
        collector.add(
            type="read", line=line, code_excerpt=excerpt_text,
            detector=f"redis_{op}_{method}", framework="redis",
        )
    elif method in writes:
        collector.add(
            type="write", line=line, code_excerpt=excerpt_text,
            detector=f"redis_{op}_{method}", framework="redis",
        )


def _detect_files(method: str, base: str, base_tokens: set,
                   line: int, excerpt_text: str,
                   collector: C.MovementCollector):
    """File I/O : java.nio.file.Files.X."""
    # Files.readString(path) / Files.write(...)
    # Le base est "Files" en accès statique
    last_token = base.rsplit(".", 1)[-1]
    if last_token != "Files":
        return

    if method in FILES_READ_METHODS:
        collector.add(
            type="read", line=line, code_excerpt=excerpt_text,
            detector=f"files_{method}", framework="stdlib_java",
        )
    elif method in FILES_WRITE_METHODS:
        collector.add(
            type="write", line=line, code_excerpt=excerpt_text,
            detector=f"files_{method}", framework="stdlib_java",
        )


# ===========================================================================
# Object creations : new FileReader, new BufferedWriter, etc.
# ===========================================================================

def _detect_object_creation(node, source_bytes: bytes,
                              collector: C.MovementCollector):
    """new FileReader(path), new BufferedWriter(writer), etc."""
    type_node = node.child_by_field_name("type")
    if type_node is None:
        return
    class_name = C.node_text(type_node, source_bytes)
    # Garder uniquement le dernier segment
    short = class_name.rsplit(".", 1)[-1]

    if short in READER_CLASSES:
        collector.add(
            type="read", line=C.line_of(node),
            code_excerpt=C.node_text(node, source_bytes),
            detector=f"reader_{short}", framework="stdlib_java",
            confidence="medium",
        )
    elif short in WRITER_CLASSES:
        collector.add(
            type="write", line=C.line_of(node),
            code_excerpt=C.node_text(node, source_bytes),
            detector=f"writer_{short}", framework="stdlib_java",
            confidence="medium",
        )
