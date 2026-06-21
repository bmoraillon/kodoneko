"""
Détecteur COSMIC pour Python utilisant le module ``ast`` de la stdlib.

Sert de fallback quand tree-sitter n'est pas installé, ou comme
implémentation principale puisque le module ``ast`` est natif et donne
déjà la précision nécessaire pour Python.

Conventions et patterns identiques à ``patterns/python.py`` (qui utilise
tree-sitter). Les deux implémentations doivent produire des résultats
équivalents sur le même code source.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import ast
from typing import Optional

from ..models import CosmicMovement, CosmicMode
from . import _common as C


# Reprise des constantes depuis patterns/python.py
DJANGO_READ_METHODS = {
    "get", "filter", "all", "exclude", "first", "last",
    "values", "values_list", "annotate", "aggregate",
    "count", "exists", "in_bulk", "earliest", "latest",
    "select_related", "prefetch_related",
}
DJANGO_WRITE_METHODS = {
    "save", "create", "update", "delete", "bulk_create",
    "bulk_update", "get_or_create", "update_or_create",
}
SQLALCHEMY_READ_METHODS = {
    "query", "scalar", "scalar_one", "scalar_one_or_none",
    "scalars", "first", "one", "one_or_none", "all",
    # D-PY9 (validation exemples manuel COSMIC 2.1.6) :
    # session.get(Model, pk) est le raccourci SQLAlchemy 1.4+ pour lookup
    # par primary key. Très courant en code idiomatique moderne.
    "get",
}
SQLALCHEMY_WRITE_METHODS = {"add", "add_all", "merge", "delete"}
# D-PY8 (validation exemples manuel COSMIC 2.1.4) :
# `session.flush()` et `session.commit()` ne sont PAS des mouvements de
# données distincts — ce sont des opérations transactionnelles qui
# persistent les writes déjà comptés via add()/delete()/merge().
# Compter commit() après add() créerait un double-comptage du même write.
# Cohérent avec la philosophie COSMIC d'acte syntaxique unique (D-T3) :
# `add(); flush(); commit()` représente UN write fonctionnel.
PYMONGO_READ_METHODS = {
    "find", "find_one", "aggregate", "count_documents",
    "distinct", "find_one_and_update",
}
PYMONGO_WRITE_METHODS = {
    "insert_one", "insert_many", "update_one", "update_many",
    "delete_one", "delete_many", "replace_one", "bulk_write",
}
REDIS_READ_METHODS = {
    "get", "mget", "hget", "hmget", "hgetall", "hvals", "hkeys",
    "lrange", "lindex", "llen", "smembers", "sismember", "scard",
    "zrange", "zrangebyscore", "zscore", "zcard", "exists", "keys", "type",
}
REDIS_WRITE_METHODS = {
    "set", "mset", "setex", "hset", "hmset", "hdel",
    "lpush", "rpush", "lpop", "rpop",
    "sadd", "srem", "zadd", "zrem",
    "delete", "expire", "rename", "incr", "decr",
}
HTTP_RESPONSE_FUNCTIONS = {
    "JsonResponse", "HttpResponse", "HttpResponseRedirect",
    "render", "redirect", "jsonify", "make_response", "Response",
}
WEB_ROUTE_METHODS = {"route", "get", "post", "put", "delete", "patch", "head", "options"}
HTTP_CLIENT_METHODS = C.HTTP_VERBS  # verbes HTTP partagés (voir _common.py)

# D-PY10 (L9 fix, validation manuel COSMIC) : classes d'exception qui émettent
# un error/confirmation message HTTP vers l'utilisateur. Le manuel COSMIC
# (section 2.6.1) compte UN Exit par functional process pour ces messages,
# même si plusieurs raises différents apparaissent dans le même endpoint
# (frequency rule).
#
# Détecté uniquement dans le contexte d'une fonction identifiée comme endpoint
# (route web, controller, handler) pour éviter les faux positifs sur les
# `raise ValueError` d'utilitaires internes.
HTTP_EXCEPTION_CLASSES = {
    # FastAPI / Starlette
    "HTTPException", "RequestValidationError", "WebSocketException",
    # Django
    "Http404", "PermissionDenied", "SuspiciousOperation",
    "DisallowedHost", "DisallowedRedirect",
    # Werkzeug (Flask)
    "BadRequest", "Unauthorized", "Forbidden", "NotFound",
    "MethodNotAllowed", "NotAcceptable", "RequestTimeout", "Conflict",
    "Gone", "LengthRequired", "PreconditionFailed", "RequestEntityTooLarge",
    "RequestURITooLarge", "UnsupportedMediaType", "RequestedRangeNotSatisfiable",
    "ExpectationFailed", "ImATeapot", "UnprocessableEntity", "Locked",
    "FailedDependency", "PreconditionRequired", "TooManyRequests",
    "RequestHeaderFieldsTooLarge", "UnavailableForLegalReasons",
    "InternalServerError", "NotImplemented", "BadGateway",
    "ServiceUnavailable", "GatewayTimeout", "HTTPVersionNotSupported",
    "HTTPException",  # werkzeug.exceptions.HTTPException
}

# Fonctions Flask qui émettent un error (équivalent raise mais en appel)
HTTP_ABORT_FUNCTIONS = {"abort"}

# D-PY7 : factories de clients HTTP — utilisé pour identifier les variables
# qui contiennent un client HTTP. Chaînes telles que reconnues par
# _attribute_chain. Le chain peut être un suffixe (httpx.AsyncClient,
# Client, AsyncClient si import direct).
HTTP_CLIENT_FACTORIES = {
    # httpx
    "httpx.AsyncClient", "httpx.Client",
    "AsyncClient", "Client",  # ambigu sans contexte — voir _is_http_client_factory
    # requests
    "requests.Session",
    "Session",  # ambigu
    # aiohttp
    "aiohttp.ClientSession",
    "ClientSession",  # ambigu
}

# Factories non-ambiguës (acceptées telles quelles)
HTTP_CLIENT_FACTORIES_UNAMBIGUOUS = {
    "httpx.AsyncClient", "httpx.Client",
    "requests.Session",
    "aiohttp.ClientSession",
}
SQL_READ_PREFIX = ("SELECT", "WITH ")
SQL_WRITE_PREFIX = ("INSERT", "UPDATE", "DELETE", "MERGE")


def _excerpt(text: str, max_len: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def _attribute_chain(node: ast.AST) -> str:
    """Reconstruit la chaîne d'attributs d'un Call.

    Ex: ``User.objects.filter`` pour l'appel ``User.objects.filter(...)``.
    """
    if isinstance(node, ast.Call):
        return _attribute_chain(node.func)
    if isinstance(node, ast.Attribute):
        return _attribute_chain(node.value) + "." + node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return ""


def _short_name(chain: str) -> str:
    return chain.rsplit(".", 1)[-1] if "." in chain else chain


def _base(chain: str) -> str:
    return chain.rsplit(".", 1)[0] if "." in chain else ""


def _decorator_chain(decorator: ast.AST) -> str:
    """Récupère le nom d'un décorateur Python (ex: app.route, click.command)."""
    if isinstance(decorator, ast.Call):
        return _attribute_chain(decorator.func)
    if isinstance(decorator, ast.Attribute):
        return _attribute_chain(decorator)
    if isinstance(decorator, ast.Name):
        return decorator.id
    return ""


# ===========================================================================
# Détecteurs
# ===========================================================================

class CosmicVisitor(ast.NodeVisitor):
    """Visiteur ast.NodeVisitor qui détecte les mouvements COSMIC."""

    def __init__(self, source: str, file_path: str, mode: CosmicMode):
        self.source = source
        self.source_lines = source.splitlines()
        self.file_path = file_path
        self.mode = mode
        self.movements: list[CosmicMovement] = []
        self._seen: set[tuple[int, str, str]] = set()
        self._inner_calls: set[int] = set()  # IDs des Call à sauter (chains)
        self._decorator_calls: set[int] = set()  # IDs des Call qui SONT des décorateurs
        # D-PY6 : profondeur de contexte "vue Django" (1er param = request).
        # Incrémenté à l'entrée d'une fonction vue, décrémenté à la sortie.
        # Utilisé pour activer la détection des related managers (cart.items.X).
        self._django_view_depth = 0
        # D-PY7 : noms de variables identifiées comme HTTP clients par
        # instanciation. Permet de détecter `client.post(...)` quand
        # `client = httpx.AsyncClient()` ou `with httpx.Client() as client`.
        self._http_client_vars: set[str] = set()
        # D-PY10 (L9 fix) : tracker l'endpoint actuel pour appliquer la
        # frequency rule sur les error messages (1 Exit error par FP, peu
        # importe combien de raises HTTPException). La clé est l'id du
        # noeud fonction de l'endpoint en cours. Une fois un raise détecté,
        # on l'ajoute pour ne pas re-compter dans la même fonction.
        self._endpoint_func_stack: list = []  # pile de FunctionDef nodes
        self._endpoint_error_emitted: set[int] = set()  # ids des fonctions endpoint avec error déjà émis

    @property
    def _in_django_view_context(self) -> bool:
        return self._django_view_depth > 0

    def _add(self, m: CosmicMovement) -> None:
        key = (m.line, m.type, m.detector)
        if key in self._seen:
            return
        self._seen.add(key)
        self.movements.append(m)

    def _line_text(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    # -- Function definitions & decorators ----------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)
        # Si c'est un endpoint web, les `return` directs sont des Exits implicites
        is_web = self._is_web_endpoint(node)
        if is_web:
            self._scan_returns_as_exits(node)
        # D-PY6 : tracker la profondeur de contexte Django view pour activer
        # la détection des related managers (cart.items.create, etc.)
        is_django_view = self._is_django_view(node)
        if is_django_view:
            self._django_view_depth += 1
        # D-PY10 : tracker la pile des endpoints pour la frequency rule sur
        # les error messages (raise HTTPException → 1 Exit par FP)
        if is_web:
            self._endpoint_func_stack.append(node)
        self.generic_visit(node)
        if is_web:
            self._endpoint_func_stack.pop()
        if is_django_view:
            self._django_view_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)
        is_web = self._is_web_endpoint(node)
        if is_web:
            self._scan_returns_as_exits(node)
        is_django_view = self._is_django_view(node)
        if is_django_view:
            self._django_view_depth += 1
        if is_web:
            self._endpoint_func_stack.append(node)
        self.generic_visit(node)
        if is_web:
            self._endpoint_func_stack.pop()
        if is_django_view:
            self._django_view_depth -= 1

    def _is_django_view(self, node) -> bool:
        """True si la fonction est une vue Django (1er param = `request`)."""
        return bool(
            node.args.args
            and node.args.args[0].arg == "request"
            and not any(_decorator_chain(d).split(".")[0] in
                          ("app", "router", "api", "blueprint", "bp",
                           "click", "task", "celery")
                          for d in node.decorator_list)
        )

    def _is_web_endpoint(self, node) -> bool:
        """True si la fonction est décorée comme route web ou suit le pattern
        Django view (premier param == request)."""
        for deco in node.decorator_list:
            chain = _decorator_chain(deco)
            short = _short_name(chain) if chain else ""
            if short in WEB_ROUTE_METHODS:
                base = _base(chain).lower()
                if short == "route" or any(b in base for b in ("app", "router", "api",
                                                                "blueprint", "bp")):
                    return True
        # Django view : 1er param "request" + pas de décorateur explicite
        if (node.args.args and node.args.args[0].arg == "request"
                and not node.decorator_list):
            return True
        return False

    def _scan_returns_as_exits(self, func_node) -> None:
        """Pour chaque Return dans la fonction (sans descendre dans des fonctions
        imbriquées), ajoute un Exit si pas déjà détecté ailleurs (ex: JsonResponse).
        """
        for inner in ast.walk(func_node):
            # Ne pas inclure les returns de fonctions imbriquées
            if inner is func_node:
                continue
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)) and inner is not func_node:
                continue
            if not isinstance(inner, ast.Return):
                continue
            # Si le Return retourne un Call à une fonction de réponse explicite,
            # _detect_http_response s'en occupera déjà.
            # On gère aussi `return jsonify(...), 404` (Tuple dont le 1er élément
            # est un Call) — pattern Flask classique.
            value = inner.value
            call_to_check = None
            if isinstance(value, ast.Call):
                call_to_check = value
            elif isinstance(value, ast.Tuple) and value.elts \
                    and isinstance(value.elts[0], ast.Call):
                # return jsonify({}), 404 → on regarde le 1er élément
                call_to_check = value.elts[0]
            if call_to_check is not None:
                chain = _attribute_chain(call_to_check)
                if _short_name(chain) in HTTP_RESPONSE_FUNCTIONS:
                    continue  # déjà compté par _detect_http_response
            # Exit implicite
            self._add(CosmicMovement(
                type="exit", file=self.file_path, line=inner.lineno,
                code_excerpt=_excerpt(self._line_text(inner.lineno)),
                detector="web_implicit_return", framework="web",
                confidence="medium",
            ))

    def _handle_function(self, node) -> None:
        # Marquer les Call qui sont des décorateurs pour ne pas les compter
        # comme des appels normaux. Un décorateur peut être un Call (ex:
        # @app.route("/path")) ou un simple Attribute/Name.
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call):
                self._decorator_calls.add(id(deco))

        # Décorateurs : routes web, celery tasks, click commands
        for deco in node.decorator_list:
            chain = _decorator_chain(deco)
            if not chain:
                continue

            # Routes web
            short = _short_name(chain)
            if short in WEB_ROUTE_METHODS:
                base = _base(chain).lower()
                # Détection framework :
                # - "route" → Flask (méthode propre à Flask)
                # - "router" ou "api" dans la base → FastAPI
                # - sinon (app.get/post/...) : ambigu Flask/FastAPI →
                #   on regarde si la fonction est async (forte indication FastAPI)
                if short == "route":
                    framework = "flask"
                elif any(b in base for b in ("router", "api")):
                    framework = "fastapi"
                elif any(b in base for b in ("app", "blueprint", "bp")):
                    # Discriminant : FastAPI utilise async/await massivement
                    framework = "fastapi" if isinstance(node, ast.AsyncFunctionDef) else "flask"
                else:
                    continue  # peut être un appel get() d'autre chose
                self._add(CosmicMovement(
                    type="entry", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(f"@{chain} def {node.name}(...)"),
                    detector=f"{framework}_route", framework=framework,
                ))

            # Celery task
            elif "task" in chain and ("app.task" in chain or "celery.task" in chain
                                       or chain == "task" or chain.endswith(".task")):
                self._add(CosmicMovement(
                    type="entry", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(f"@{chain} def {node.name}(...)"),
                    detector="celery_task", framework="celery",
                ))

            # Click command
            elif chain in ("click.command", "click.group") or chain.endswith(".command") \
                 or chain.endswith(".group"):
                if "click" in chain:
                    self._add(CosmicMovement(
                        type="entry", file=self.file_path, line=node.lineno,
                        code_excerpt=_excerpt(f"@{chain} def {node.name}(...)"),
                        detector="click_command", framework="click",
                    ))

        # Django view : 1er paramètre nommé "request"
        if (node.args.args and node.args.args[0].arg == "request"
                and not node.decorator_list):
            # On évite de double-compter si déjà détecté comme route Flask/FastAPI
            self._add(CosmicMovement(
                type="entry", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(f"def {node.name}(request, ...)"),
                detector="django_view", framework="django",
            ))

    # -- HTTP client tracking (D-PY7) ----------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        """Détecte `client = httpx.AsyncClient()` et marque la variable."""
        if isinstance(node.value, ast.Call):
            chain = _attribute_chain(node.value)
            if self._is_http_client_factory(chain):
                # Pour chaque cible Name, marquer comme HTTP client
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._http_client_vars.add(target.id)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Détecte `with httpx.Client() as client:` et marque la variable."""
        self._track_with_items(node.items)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        """Détecte `async with httpx.AsyncClient() as client:` et marque."""
        self._track_with_items(node.items)
        self.generic_visit(node)

    def _track_with_items(self, items) -> None:
        for item in items:
            ctx = item.context_expr
            optional_vars = item.optional_vars
            if isinstance(ctx, ast.Call) and optional_vars is not None:
                chain = _attribute_chain(ctx)
                if self._is_http_client_factory(chain):
                    if isinstance(optional_vars, ast.Name):
                        self._http_client_vars.add(optional_vars.id)

    def _is_http_client_factory(self, chain: str) -> bool:
        """True si la chaîne désigne une factory de client HTTP non-ambiguë."""
        if chain in HTTP_CLIENT_FACTORIES_UNAMBIGUOUS:
            return True
        # Forme courte (`AsyncClient()` après `from httpx import AsyncClient`)
        # — ambiguë, on accepte uniquement les noms très spécifiques
        VERY_SPECIFIC_CLIENT_NAMES = {"AsyncClient"}  # rare hors httpx
        return chain in VERY_SPECIFIC_CLIENT_NAMES

    # -- Function calls -----------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        # Si ce Call est un décorateur, on ne le compte pas comme un mouvement.
        # (Les décorateurs sont déjà traités dans _handle_function pour
        # identifier le pattern de route/task/command.)
        if id(node) in self._decorator_calls:
            self.generic_visit(node)
            return

        # Si ce Call est une étape intermédiaire d'un autre Call chaîné
        # ORM (ex: User.objects.filter(...).first() — l'inner filter est
        # enfant de l'outer first), on saute la détection ORM pour éviter
        # de double-compter (le mouvement terminal `.first()` représente
        # le seul acte de lecture réel).
        is_inner_chain = self._is_inner_orm_chain(node)

        self._detect_http_response(node)
        if not is_inner_chain:
            self._detect_orm_django(node)
            self._detect_orm_sqlalchemy(node)
            self._detect_pymongo(node)
            self._detect_redis(node)
        self._detect_raw_sql(node)
        self._detect_file_io(node)
        self._detect_http_client(node)
        # D-PY10 (L9 fix) : détecter abort(...) Flask comme error message
        self._detect_http_abort(node)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        """D-PY10 (L9 fix) : détecter les raises d'exceptions HTTP dans
        contexte endpoint comme Exit error message.

        Frequency rule COSMIC (section 2.6.1) : 1 Exit error par functional
        process, peu importe combien de raises différents dans le même endpoint.
        """
        self._detect_http_raise(node)
        self.generic_visit(node)

    def _detect_http_raise(self, node: ast.Raise) -> None:
        """Détecte raise HTTPException, raise Http404, etc."""
        if not self._endpoint_func_stack:
            return  # pas dans un endpoint → ignorer

        exc = node.exc
        if exc is None:
            # bare `raise` (re-raise dans except) — pas un message HTTP
            return

        # Cas 1: raise X(...) — l'exception est un Call
        # Cas 2: raise X — l'exception est un Name (instance déjà créée)
        if isinstance(exc, ast.Call):
            exc_name_node = exc.func
        else:
            exc_name_node = exc

        # Extraire le nom de la classe
        exc_name = ""
        if isinstance(exc_name_node, ast.Name):
            exc_name = exc_name_node.id
        elif isinstance(exc_name_node, ast.Attribute):
            # exceptions.NotFound, werkzeug.exceptions.BadRequest, etc.
            exc_name = exc_name_node.attr

        if exc_name not in HTTP_EXCEPTION_CLASSES:
            return

        # Frequency rule : 1 seul error Exit par endpoint, même si plusieurs raises
        current_endpoint = self._endpoint_func_stack[-1]
        endpoint_id = id(current_endpoint)
        if endpoint_id in self._endpoint_error_emitted:
            return  # déjà émis pour cet endpoint
        self._endpoint_error_emitted.add(endpoint_id)

        self._add(CosmicMovement(
            type="exit", file=self.file_path, line=node.lineno,
            code_excerpt=_excerpt(self._line_text(node.lineno)),
            detector=f"http_raise_{exc_name}", framework="web",
            confidence="medium",
        ))

    def _detect_http_abort(self, node: ast.Call) -> None:
        """Détecte abort(400, ...) (Flask) dans contexte endpoint.

        abort() est techniquement une fonction qui raise en interne, mais le
        développeur l'appelle comme un Call. Frequency rule appliquée comme
        pour raise.
        """
        if not self._endpoint_func_stack:
            return
        chain = _attribute_chain(node)
        func_name = _short_name(chain) if chain else ""
        if func_name not in HTTP_ABORT_FUNCTIONS:
            return

        current_endpoint = self._endpoint_func_stack[-1]
        endpoint_id = id(current_endpoint)
        if endpoint_id in self._endpoint_error_emitted:
            return
        self._endpoint_error_emitted.add(endpoint_id)

        self._add(CosmicMovement(
            type="exit", file=self.file_path, line=node.lineno,
            code_excerpt=_excerpt(self._line_text(node.lineno)),
            detector="http_abort", framework="flask",
            confidence="medium",
        ))

    def _is_inner_orm_chain(self, node: ast.Call) -> bool:
        """True si ce Call est imbriqué dans un autre Call (chaîne d'appels).

        Détection : la fonction appelée est un Attribute dont la `value`
        est elle-même un Call. Exemple : .first() sur queryset.filter()
        → la racine du .filter() est un Call qui contient .first().
        Mais en parcours descendant, on visite d'abord .first() (le plus
        externe), donc lorsqu'on rencontre .filter() en interne, il faut
        le marquer comme inner.

        Approche concrète : on regarde si node.func.value est un Call.
        Si oui, ce node EST l'outer (le 1er du chain). On veut au contraire
        détecter qu'un node a un parent Call dans sa chaîne d'appels.

        Heuristique simple : on enregistre les bornes (lineno, col_offset)
        des chaînes déjà émises ; si un Call partage la même lineno qu'un
        Call externe déjà visité avec la même base, on saute.

        Alternative plus propre : on traverse les Call sans descendre dans
        les Call enfants pour l'ORM. C'est ce qu'on fait : pour Django ORM,
        si le `func` est `Attribute(value=Call(...), attr=...)`, alors ce
        Call EST l'outer, et son inner ne sera pas visité car generic_visit
        le visiterait mais on a `is_inner_chain` marqué.

        On simplifie en regardant le PARENT — mais ast ne donne pas le
        parent. On utilise un set d'IDs déjà classés comme "inner".
        """
        # node.func est-il un Attribute dont .value est un Call ?
        # Si oui, le Call enfant (node.func.value) sera visité après ce
        # node-ci → on doit le marquer comme inner.
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            self._inner_calls.add(id(node.func.value))
        # Ce node est-il marqué comme inner ?
        return id(node) in self._inner_calls

    def _detect_http_response(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        short = _short_name(chain)
        if short in HTTP_RESPONSE_FUNCTIONS:
            # D-PY11 fix (validation FastAPI template) : `render` est ambigu.
            # Django render(request, template, ...) est un APPEL DE FONCTION nu
            # dont le 1er arg est `request`. Jinja2/Mako Template(x).render(y)
            # est un APPEL DE MÉTHODE (chain contient un point) → pas Django.
            if short == "render":
                # Si la chaîne contient un point, c'est xxx.render(...) → méthode
                # de template engine, pas la fonction Django render(). On skip.
                if "." in chain:
                    return
                # Appel nu render(...) : exiger que le 1er arg soit `request`
                # (signature Django) pour confirmer.
                if not (node.args and isinstance(node.args[0], ast.Name)
                        and node.args[0].id == "request"):
                    return
            if short in ("JsonResponse", "HttpResponse", "HttpResponseRedirect",
                          "render", "redirect"):
                fw = "django"
                det = f"{fw}_response"
            elif short in ("jsonify", "make_response"):
                fw = "flask"
                det = f"{fw}_response"
            else:
                fw = "fastapi"
                det = "http_response"
            self._add(CosmicMovement(
                type="exit", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=det, framework=fw,
            ))

    def _detect_orm_django(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        if not chain or "." not in chain:
            return
        method = _short_name(chain)
        base = _base(chain)

        # xxx.objects.METHOD()
        if base.endswith(".objects") or ".objects." in (base + "."):
            if method in DJANGO_READ_METHODS:
                self._add(CosmicMovement(
                    type="read", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector=f"django_orm_{method}", framework="django",
                ))
            elif method in DJANGO_WRITE_METHODS:
                self._add(CosmicMovement(
                    type="write", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector=f"django_orm_{method}", framework="django",
                ))
            return
        # instance.save() / instance.delete() — heuristique défensive :
        # On SKIPPE si la base évoque clairement un autre type de client
        # (session SQLAlchemy, Redis client, etc.) pour éviter le
        # double-comptage avec _detect_orm_sqlalchemy et _detect_redis.
        if method in ("save", "delete") and base:
            base_lower = base.lower()
            NON_DJANGO_HINTS = (
                "session",      # SQLAlchemy session.delete()
                "redis", "cache",  # Redis cache.delete()
                "mongo", "collection",
                "client",        # divers clients
                "file", "path",  # file.delete(), path.delete()
                "kafka", "queue",
            )
            if any(h in base_lower for h in NON_DJANGO_HINTS):
                return
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"django_orm_{method}_instance",
                framework="django", confidence="medium",
            ))
            return

        # D-PY6 : Related Managers Django (relation inverse FK).
        # Cas : `cart.items.create(...)`, `user.orders.filter(...)`, etc.
        # En Django, une ForeignKey crée un manager inverse accessible via
        # l'attribut `<lower_model_name>_set` ou via `related_name`.
        # Chain format : `instance.relation.METHOD` (2 niveaux).
        # On accepte uniquement si on est dans un contexte "vue Django"
        # (fonction ancêtre avec `request` comme 1er param), pour éviter
        # les faux positifs sur d'autres contextes.
        if self._in_django_view_context and base and "." in base:
            # La chaîne a au moins 2 niveaux : foo.bar.METHOD
            # On vérifie qu'il n'y a pas plus de tokens "techniques"
            # qui pourraient indiquer autre chose (objects déjà exclu).
            if method in DJANGO_READ_METHODS:
                self._add(CosmicMovement(
                    type="read", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector=f"django_orm_{method}_related",
                    framework="django", confidence="medium",
                ))
            elif method in DJANGO_WRITE_METHODS:
                self._add(CosmicMovement(
                    type="write", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector=f"django_orm_{method}_related",
                    framework="django", confidence="medium",
                ))

    def _detect_orm_sqlalchemy(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        if not chain or "." not in chain:
            return
        method = _short_name(chain)
        base = _base(chain)

        # Le « root » de la chaîne (avant le premier point) doit être session-like.
        # Couvre `session.X.X.METHOD()` (chaînes query/filter/first)
        # autant que `session.METHOD()`.
        chain_root = chain.split(".")[0]
        is_session_root = chain_root in ("session", "Session", "db")
        is_session_attr = base.endswith("session") or base.endswith(".session")

        if not (is_session_root or is_session_attr):
            return

        # D-PY9 garde-fou (validation manuel COSMIC, archétype 08) :
        # `session.get(...)` est ambigu entre SQLAlchemy 1.4+ et aiohttp/httpx
        # client HTTP. La signature SQLAlchemy moderne est
        # `session.get(Model, pk)` (2 args), tandis que `client.get(url)`
        # n'a typiquement qu'1 arg.
        # Décision : pour `get`, exiger 2+ args (signature SQLA 1.4+).
        # `session.get(pk)` (1 arg, signature legacy 0.x) n'est plus reconnu.
        # Acceptable car ce code legacy est rare dans le moderne, et le
        # bénéfice (pas de faux positifs sur aiohttp/requests) compense.
        if method == "get":
            if chain_root in self._http_client_vars:
                return  # session HTTP confirmée, pas SQLAlchemy
            if len(node.args) < 2:
                return  # `session.get(url)` ou `session.get(pk)` 1-arg → trop ambigu

        if method in SQLALCHEMY_READ_METHODS:
            self._add(CosmicMovement(
                type="read", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"sqlalchemy_{method}", framework="sqlalchemy",
            ))
        elif method in SQLALCHEMY_WRITE_METHODS:
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"sqlalchemy_{method}", framework="sqlalchemy",
            ))

    def _detect_pymongo(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        if not chain or "." not in chain:
            return
        method = _short_name(chain)
        base = _base(chain).lower()

        # Méthodes très spécifiques pymongo : OK même sans contexte
        PYMONGO_SPECIFIC = {
            "find_one", "find_one_and_update", "insert_one", "insert_many",
            "update_one", "update_many", "delete_one", "delete_many",
            "replace_one", "bulk_write", "count_documents",
        }
        # Méthodes ambiguës : "find", "aggregate", "distinct" peuvent
        # exister sur strings/listes. On exige un contexte explicite.
        PYMONGO_AMBIGUOUS = {"find", "aggregate", "distinct"}
        MONGO_CONTEXT = ("mongo", "collection", "_db", ".db", "db.", "coll")
        is_mongo_context = any(m in base for m in MONGO_CONTEXT)

        if method in PYMONGO_AMBIGUOUS and not is_mongo_context:
            return  # éviter les faux positifs sur str.find, list.aggregate, etc.

        if method in PYMONGO_READ_METHODS:
            self._add(CosmicMovement(
                type="read", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"pymongo_{method}", framework="pymongo",
                confidence="high" if method in PYMONGO_SPECIFIC else "medium",
            ))
        elif method in PYMONGO_WRITE_METHODS:
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"pymongo_{method}", framework="pymongo",
                confidence="high",
            ))

    def _detect_redis(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        if not chain or "." not in chain:
            return
        method = _short_name(chain)
        base = _base(chain).lower()
        is_redis_context = any(b in base for b in ("redis", "cache"))

        # Méthodes très spécifiques Redis : OK même sans contexte évident
        REDIS_SPECIFIC = {"hgetall", "hmset", "zadd", "zrange", "zrangebyscore",
                          "lrange", "smembers", "hkeys", "hvals", "sadd",
                          "lpush", "rpush", "lpop", "rpop", "srem", "zrem", "zscore"}
        ambiguous = method not in REDIS_SPECIFIC

        if not is_redis_context and ambiguous:
            return

        if method in REDIS_READ_METHODS:
            self._add(CosmicMovement(
                type="read", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"redis_{method}", framework="redis",
                confidence="high" if is_redis_context else "low",
            ))
        elif method in REDIS_WRITE_METHODS:
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"redis_{method}", framework="redis",
                confidence="high" if is_redis_context else "low",
            ))

    def _detect_raw_sql(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        method = _short_name(chain)
        if method not in ("execute", "executemany"):
            return

        # Premier arg = SQL string
        if not node.args:
            return
        first = node.args[0]
        sql_str = ""
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            sql_str = first.value
        elif isinstance(first, ast.JoinedStr):  # f-string
            # On prend la 1re partie statique
            for part in first.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    sql_str += part.value
                    break

        if not sql_str:
            return
        sql_upper = sql_str.strip().upper()

        for prefix in SQL_READ_PREFIX:
            if sql_upper.startswith(prefix):
                self._add(CosmicMovement(
                    type="read", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector="raw_sql_select", framework="sql",
                ))
                return
        for prefix in SQL_WRITE_PREFIX:
            if sql_upper.startswith(prefix):
                self._add(CosmicMovement(
                    type="write", file=self.file_path, line=node.lineno,
                    code_excerpt=_excerpt(self._line_text(node.lineno)),
                    detector=f"raw_sql_{prefix.lower()}", framework="sql",
                ))
                return

    def _detect_file_io(self, node: ast.Call) -> None:
        chain = _attribute_chain(node)
        short = _short_name(chain)

        # pathlib
        if short == "read_text" or short == "read_bytes":
            self._add(CosmicMovement(
                type="read", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"pathlib_{short}", framework="stdlib",
            ))
            return
        if short == "write_text" or short == "write_bytes":
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)),
                detector=f"pathlib_{short}", framework="stdlib",
            ))
            return

        # builtin open()
        if short != "open" or "." in chain:
            return

        # Récupérer mode
        mode_str = "r"
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                and isinstance(node.args[1].value, str):
            mode_str = node.args[1].value
        else:
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    mode_str = kw.value.value
                    break

        is_write = any(c in mode_str for c in ("w", "a", "x", "+"))
        self._add(CosmicMovement(
            type="write" if is_write else "read",
            file=self.file_path, line=node.lineno,
            code_excerpt=_excerpt(self._line_text(node.lineno)),
            detector=f"builtin_open_{'write' if is_write else 'read'}",
            framework="stdlib",
        ))

    def _detect_http_client(self, node: ast.Call) -> None:
        if self.mode != "practical":
            return
        chain = _attribute_chain(node)
        if not chain or "." not in chain:
            return
        method = _short_name(chain)
        if method not in HTTP_CLIENT_METHODS:
            return
        base = _base(chain)

        # D-PY7 : si la base est une variable identifiée comme HTTP client
        # par instanciation (`client = httpx.AsyncClient()` ou
        # `async with httpx.Client() as client`), on émet le mouvement
        # directement, sans passer par les heuristiques tokenisées.
        # Cas typique : `client.post(url)` après l'instanciation.
        base_root = base.split(".")[0] if base else ""
        if base_root in self._http_client_vars:
            self._add(CosmicMovement(
                type="write", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)) + " [req]",
                detector=f"http_client_{method}", framework="http_client",
            ))
            self._add(CosmicMovement(
                type="read", file=self.file_path, line=node.lineno,
                code_excerpt=_excerpt(self._line_text(node.lineno)) + " [resp]",
                detector=f"http_client_{method}_resp", framework="http_client",
            ))
            return

        base = base.lower()

        # Tokenize la base par séparateurs courants pour des comparaisons mot-à-mot
        tokens = set()
        for tok in base.replace(".", " ").replace("_", " ").split():
            tokens.add(tok)

        # Si la base contient un mot évoquant un client de stockage,
        # on n'est pas en présence d'un appel HTTP sortant.
        STORAGE_TOKENS = {"redis", "mongo", "mongodb", "db", "cache",
                          "elastic", "elasticsearch", "kafka", "rabbit", "rabbitmq"}
        if tokens & STORAGE_TOKENS:
            return

        # Marqueurs positifs HTTP (mots clés, pas sous-chaînes)
        HTTP_TOKENS = {"requests", "httpx", "urllib", "http", "rest",
                       "api", "client", "webhook"}
        # "client" et "session" seuls sont ambigus, on exige un autre marqueur
        AMBIGUOUS = {"client", "session"}

        positive_tokens = tokens & HTTP_TOKENS
        if not positive_tokens:
            return
        if positive_tokens <= AMBIGUOUS:
            # Seulement "client" ou "session" trouvé : pas assez
            return

        self._add(CosmicMovement(
            type="write", file=self.file_path, line=node.lineno,
            code_excerpt=_excerpt(self._line_text(node.lineno)) + " [req]",
            detector=f"http_client_{method}", framework="http_client",
        ))
        self._add(CosmicMovement(
            type="read", file=self.file_path, line=node.lineno,
            code_excerpt=_excerpt(self._line_text(node.lineno)) + " [resp]",
            detector=f"http_client_{method}_resp", framework="http_client",
        ))


def detect_python_movements_ast(
    source: bytes | str,
    file_path: str,
    *,
    mode: CosmicMode = "practical",
) -> list[CosmicMovement]:
    """Détecte les mouvements COSMIC dans du code Python via ``ast`` stdlib.

    Compatible signature avec les détecteurs tree-sitter (javascript, java)
    mais sans tree-sitter. Plus simple à déployer (pas de dépendance externe).
    """
    if isinstance(source, bytes):
        source = source.decode("utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    visitor = CosmicVisitor(source, file_path, mode)
    visitor.visit(tree)
    return visitor.movements
