"""
Helpers tree-sitter partagés entre détecteurs JS, TS, et autres langages.

Fournit :
- Extraction de texte depuis un noeud
- Navigation dans l'AST (parents, enfants nommés)
- Reconstruction de chaînes d'appels (a.b.c)
- Déduplication de mouvements (par ligne + type + détecteur)

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from typing import Iterator, Optional

from ..models import CosmicMovement, MovementType


# ===========================================================================
# Constantes véritablement transverses (identiques entre tous les langages)
# ===========================================================================

# Verbes HTTP standard. Identiques quel que soit le langage : ce sont les
# méthodes RFC 7231. Utilisés pour la détection des clients HTTP (axios.get,
# httpx.post, etc.) dans tous les détecteurs.
# NOTE : les whitelists d'exceptions HTTP (NestJS, Spring, Werkzeug) ne sont
# PAS ici car elles sont spécifiques à chaque framework — les centraliser
# serait une fausse mutualisation.
HTTP_VERBS = frozenset({
    "get", "post", "put", "delete", "patch", "head", "options", "request",
})


def node_text(node, source_bytes: bytes) -> str:
    """Extrait le texte d'un noeud tree-sitter."""
    if node is None:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def excerpt(text: str, max_len: int = 80) -> str:
    """Tronque un excerpt pour la lisibilité (espace normalisé)."""
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def line_of(node) -> int:
    """Numéro de ligne 1-indexé d'un noeud."""
    return node.start_point[0] + 1


def walk(node, visit, depth: int = 0):
    """Parcours pré-ordre de l'AST avec callback.

    Le callback peut retourner :
    - ``None`` ou ``True`` : continue la descente dans les enfants
    - ``False`` : skip les enfants (utile pour les chaînes déjà traitées)
    """
    cont = visit(node)
    if cont is False:
        return
    for child in node.children:
        walk(child, visit, depth + 1)


def named_children(node) -> Iterator:
    """Itère sur les enfants nommés (skip les tokens comme ponctuation)."""
    for child in node.children:
        if child.is_named:
            yield child


def field(node, name: str):
    """Raccourci pour ``node.child_by_field_name(name)``."""
    if node is None:
        return None
    return node.child_by_field_name(name)


# ---------------------------------------------------------------------------
# Reconstruction de chaînes d'appels JS/TS
# ---------------------------------------------------------------------------

def call_chain(node, source_bytes: bytes) -> str:
    """Reconstruit la chaîne d'appel d'un noeud ``call_expression``.

    Exemples :
    - ``foo()`` → "foo"
    - ``obj.method()`` → "obj.method"
    - ``a.b.c.method()`` → "a.b.c.method"
    - ``foo().bar()`` → ".bar"  (préfixe vide si chaîné depuis un call)
    - ``new Foo()`` → "Foo"
    """
    if node is None:
        return ""

    if node.type == "call_expression":
        # tree-sitter-javascript : function field
        callee = field(node, "function")
        if callee is None:
            # Fallback : 1er enfant nommé
            for c in named_children(node):
                callee = c
                break
        return _chain_expr(callee, source_bytes)

    if node.type == "new_expression":
        # new Foo(...) — récupérer le constructeur
        constructor = field(node, "constructor")
        return _chain_expr(constructor, source_bytes)

    return _chain_expr(node, source_bytes)


def _chain_expr(node, source_bytes: bytes) -> str:
    """Récursif : reconstruit la représentation textuelle d'une expression d'accès."""
    if node is None:
        return ""

    # member_expression : obj.prop
    if node.type == "member_expression":
        obj = field(node, "object")
        prop = field(node, "property")
        obj_str = _chain_expr(obj, source_bytes)
        prop_str = node_text(prop, source_bytes) if prop is not None else ""
        if obj_str:
            return f"{obj_str}.{prop_str}"
        return prop_str

    # subscript_expression : obj["x"] — on ne reconstruit pas le subscript dynamique
    if node.type == "subscript_expression":
        obj = field(node, "object")
        return _chain_expr(obj, source_bytes)

    # identifier simple
    if node.type in ("identifier", "property_identifier", "type_identifier"):
        return node_text(node, source_bytes)

    # this
    if node.type == "this":
        return "this"

    # super
    if node.type == "super":
        return "super"

    # call_expression imbriqué (foo().bar) → on ignore le call pour ne garder
    # que la chaîne de membres
    if node.type == "call_expression":
        return _chain_expr(field(node, "function"), source_bytes)

    # await expression : on traverse
    if node.type == "await_expression":
        for c in named_children(node):
            return _chain_expr(c, source_bytes)

    return ""


def short_name(chain: str) -> str:
    """Dernière partie d'une chaîne d'attributs."""
    return chain.rsplit(".", 1)[-1] if "." in chain else chain


def base_of(chain: str) -> str:
    """Base d'une chaîne d'attributs (tout sauf le dernier segment)."""
    return chain.rsplit(".", 1)[0] if "." in chain else ""


# ---------------------------------------------------------------------------
# Tokenisation de la base (pour heuristiques de contexte)
# ---------------------------------------------------------------------------

def tokenize_base(base: str) -> set[str]:
    """Découpe une base en tokens minuscules pour matching heuristique.

    >>> tokenize_base("redisClient.cache")
    {'redisclient', 'cache', 'redis', 'client'}

    On fait deux découpes :
    - par séparateurs (.,_)
    - en camelCase pour chaque segment
    """
    tokens: set[str] = set()
    for piece in base.replace(".", " ").replace("_", " ").split():
        low = piece.lower()
        tokens.add(low)
        # Découpe camelCase : redisClient → redis, client
        for sub in _split_camel(piece):
            tokens.add(sub.lower())
    return tokens


def _split_camel(s: str) -> list[str]:
    """Découpe camelCase / PascalCase en parties."""
    if not s:
        return []
    out: list[str] = []
    cur = s[0]
    for ch in s[1:]:
        if ch.isupper() and cur and not cur[-1].isupper():
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# Déduplication
# ---------------------------------------------------------------------------

class MovementCollector:
    """Collecte les mouvements détectés et dédoublonne par (ligne, type, détecteur).

    Gère aussi :
    - les Call enfants d'une chaîne déjà traitée (skip pour éviter le double comptage)
    - les Call à l'intérieur d'un décorateur (skip)
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.movements: list[CosmicMovement] = []
        self._seen: set[tuple[int, str, str]] = set()
        # IDs de noeuds à skip (chaînes, décorateurs)
        self._skip: set[int] = set()
        # Noms de variables identifiées comme HTTP clients via factory.
        # D-JS8 (équivalent D-PY7 Python).
        # Cas typique : `const client = axios.create()` → on marque `client`.
        self.http_client_vars: set[str] = set()
        # D-JS9 / D-JAVA14 (L9 fix) : IDs des noeuds body de fonctions endpoint
        # (NestJS methods, Express handlers, Spring controller methods, etc.).
        # Permet de détecter si un `throw new HttpException` est dans un
        # endpoint pour le compter comme Exit error (avec frequency rule).
        self.endpoint_method_bodies: set[int] = set()
        # IDs des body de fonctions endpoint ayant déjà émis un Exit error
        # (frequency rule : 1 seul Exit error par endpoint).
        self.endpoint_error_emitted: set[int] = set()
        # D-JAVA2 (fix validation PetClinic) : noms de variables/champs dont le
        # TYPE est un repository (`OwnerRepository owners` → "owners"). Permet
        # de détecter `this.owners.findById(...)` même si le nom de variable
        # ne contient pas "repository". Le type est le signal fiable, pas le nom.
        self.repository_vars: set[str] = set()

    def add(
        self,
        type: MovementType,
        line: int,
        code_excerpt: str,
        detector: str,
        *,
        framework: str = "",
        confidence: str = "high",
    ) -> None:
        key = (line, type, detector)
        if key in self._seen:
            return
        self._seen.add(key)
        self.movements.append(CosmicMovement(
            type=type, file=self.file_path, line=line,
            code_excerpt=excerpt(code_excerpt),
            detector=detector, framework=framework, confidence=confidence,
        ))

    def mark_skip(self, node) -> None:
        """Marque un noeud comme à sauter lors du parcours."""
        if node is not None:
            self._skip.add(id(node))

    def should_skip(self, node) -> bool:
        return id(node) in self._skip
