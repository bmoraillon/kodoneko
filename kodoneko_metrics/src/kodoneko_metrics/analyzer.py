"""
Classe CodeAnalyzer — unifie comptage de lignes, Halstead et McCabe
via tree-sitter.

API publique :

    analyzer = CodeAnalyzer()
    result = analyzer.analyze(source, language=None)
    # result.lines, result.halstead, result.mccabe

Méthodes disponibles :

- analyze(source, ...) → CombinedMetrics : tout en un, parsing mutualisé
- count_lines(source, ...) → LineCounts
- count_halstead(source, ...) → HalsteadMetrics
- count_mccabe(source, ...) → McCabeMetrics
- count_lines_from_tree(text, tree, language) → LineCounts
- count_halstead_from_tree(text, tree, language) → HalsteadMetrics
- count_mccabe_from_tree(text, tree, language) → McCabeMetrics
- parse(source, language) → tree (objet tree-sitter)
- supported_languages() → list[str]

L'instance garde un cache des grammaires tree-sitter chargées (coûteux à
instancier mais réutilisable entre fichiers). Pour les analyses ponctuelles,
utiliser les fonctions de convenance définies dans __init__.py.

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

from typing import Optional

from ._input import SourceInput, normalize_input
from .detect import detect_language
from .models import (
    CombinedMetrics,
    FunctionUnderstandability,
    HalsteadMetrics,
    LanguageDetectionFailed,
    LanguageNotSupported,
    LineCounts,
    McCabeMetrics,
    UnderstandabilityMetrics,
)


# ---------------------------------------------------------------------------
# Résultat interne de l'algorithme Campbell (cognitive complexity)
# ---------------------------------------------------------------------------
# Depuis v2.0 la complexité cognitive n'est plus une métrique de premier
# niveau ; elle est intégrée à UnderstandabilityMetrics. Cette structure
# privée sert uniquement à transporter les composantes du calcul (value,
# structural, nesting_bonus) au sein de l'analyzer.

from collections import namedtuple

_CognitiveResult = namedtuple("_CognitiveResult", ["value", "structural", "nesting_bonus"])


# ---------------------------------------------------------------------------
# Tables de configuration tree-sitter
# ---------------------------------------------------------------------------

# Mapping nom canonique → (nom du module, nom de la fonction `language()`)
_TS_LANGUAGE_LOADERS: dict[str, tuple[str, str]] = {
    "python":     ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx":        ("tree_sitter_typescript", "language_tsx"),
    "rust":       ("tree_sitter_rust", "language"),
    "go":         ("tree_sitter_go", "language"),
    "java":       ("tree_sitter_java", "language"),
    "cpp":        ("tree_sitter_cpp", "language"),
    "c":          ("tree_sitter_c", "language"),
    "ruby":       ("tree_sitter_ruby", "language"),
    "bash":       ("tree_sitter_bash", "language"),
}


# Types de nœuds tree-sitter à classer comme COMMENTAIRES
_COMMENT_NODE_TYPES = frozenset({
    "comment", "line_comment", "block_comment",
    "shebang", "hash_bang_line",
    "documentation_comment", "doc_comment",
})


# Types de nœuds IGNORÉS pour le NCLOC (conteneurs + ponctuation pure)
_EXCLUDED_NODE_TYPES = frozenset({
    "program", "module", "source_file", "translation_unit", "compilation_unit",
    ",", ";", "(", ")", "{", "}", "[", "]", ":",
})


# Types de nœuds à classer comme IDENTIFIANTS (opérandes Halstead)
_IDENTIFIER_TYPES = frozenset({
    "identifier", "property_identifier", "type_identifier",
    "shorthand_property_identifier", "shorthand_property_identifier_pattern",
    "namespace_identifier", "field_identifier",
})


# Types de nœuds STRING
_STRING_TYPES = frozenset({
    "string", "string_literal", "template_string", "string_fragment",
    "regex", "regex_pattern",
})


# Types de nœuds NUMÉRIQUES
_NUMBER_TYPES = frozenset({
    "number", "integer", "float", "decimal_integer_literal",
    "hex_integer_literal", "octal_integer_literal", "binary_integer_literal",
})


# Types LITTÉRAUX (opérandes)
_LITERAL_TYPES = _STRING_TYPES | _NUMBER_TYPES | frozenset({
    "true", "false", "null", "undefined", "this", "super", "none", "True", "False",
})


# Types de nœuds OPÉRATEURS (structures de contrôle, déclarations, opérations)
_OPERATOR_NODE_TYPES = frozenset({
    # Contrôle de flux
    "if_statement", "for_statement", "for_in_statement", "for_of_statement",
    "while_statement", "do_statement", "switch_statement", "case_statement",
    "default_statement", "return_statement", "break_statement",
    "continue_statement", "throw_statement", "try_statement",
    "catch_clause", "finally_clause",
    "elif_clause", "else_clause", "with_statement",  # Python
    # Déclarations
    "function_declaration", "function_expression", "arrow_function",
    "method_definition", "class_declaration", "interface_declaration",
    "type_alias_declaration", "enum_declaration",
    "function_definition", "class_definition",  # Python
    "lambda",
    # Opérations
    "binary_expression", "unary_expression", "update_expression",
    "assignment_expression", "augmented_assignment_expression",
    "ternary_expression", "logical_expression", "instanceof_expression",
    "in_expression", "typeof_expression", "await_expression",
    "yield_expression", "spread_element",
    "binary_operator", "unary_operator", "boolean_operator", "comparison_operator",
    "assignment", "augmented_assignment", "conditional_expression",
    # Appels et accès
    "call_expression", "member_expression", "subscript_expression",
    "new_expression",
    "call", "attribute", "subscript",  # Python
    # Modules
    "import_statement", "import_specifier", "import_from_statement",
    "export_statement", "export_default_declaration",
    # Compréhensions Python
    "list_comprehension", "set_comprehension", "dictionary_comprehension",
    "generator_expression",
    # JSX
    "jsx_element", "jsx_self_closing_element",
    "jsx_opening_element", "jsx_closing_element", "jsx_expression",
})


# Opérateurs textuels (nœuds anonymes représentant l'opérateur lui-même)
_TEXTUAL_OPERATORS = frozenset({
    "+", "-", "*", "/", "%", "**", "//",
    "==", "!=", "===", "!==", "<", "<=", ">", ">=",
    "&&", "||", "!", "&", "|", "^", "~", "<<", ">>", ">>>",
    "=", "+=", "-=", "*=", "/=", "%=", "**=",
    "&=", "|=", "^=", "<<=", ">>=", "&&=", "||=", "??=",
    "??", "?.", "?",
    "and", "or", "not", "is",  # Python booleans
    "async", "await", "yield", "return", "throw", "new", "delete",
    "typeof", "instanceof", "in", "of",
    "if", "else", "elif", "for", "while", "do", "switch", "case", "default",
    "try", "catch", "finally", "except", "raise",
    "function", "class", "extends", "implements",
    "def", "lambda", "pass", "break", "continue",
    "import", "from", "as", "export",
    "const", "let", "var",
})


# Types de nœuds qui ouvrent une "fonction-ou-classe Python" (pour la
# détection de docstrings : on regarde le premier statement du body)
_PYTHON_DOCSTRING_PARENTS = frozenset({
    "function_definition", "class_definition", "module",
})


# Types de nœuds qui peuvent porter une docstring TypeScript/JS (JSDoc-like)
# — pour l'instant on traite seulement Python. Extension possible plus tard.


# ---------------------------------------------------------------------------
# Tables McCabe
# ---------------------------------------------------------------------------

# Types de nœuds tree-sitter qui constituent des "points de décision".
# Chaque occurrence ajoute +1 à la complexité cyclomatique.
#
# La table unifie les langages supportés (Python, JS, TS, Rust, Go, Java,
# C/C++). En pratique beaucoup de noms se chevauchent — c'est ce qui rend
# l'approche viable sans table par langage.
#
# Note : un `else` n'ajoute PAS à la complexité (déjà compté par le `if`
# correspondant). De même, `else_clause` n'est pas compté.
_DECISION_NODE_TYPES = frozenset({
    # === Branchements ===
    # Python
    "if_statement",       # if + elif compteront chacun ; on filtre `else` plus bas
    "elif_clause",        # chaque elif ajoute un branchement
    "conditional_expression",  # x if cond else y (Python ternaire)
    # JS / TS / Rust / Go / Java
    "if_statement",       # idem (déjà dans le set)
    "ternary_expression", # cond ? a : b
    # Rust
    "if_let_expression",
    "match_expression",   # un match = au moins 1 chemin, donc +1 par match
    "match_arm",          # chaque arm supplémentaire = +1
    # === Boucles ===
    "for_statement",
    "for_in_statement",   # JS/TS
    "for_of_statement",   # JS/TS
    "for_each_statement",
    "while_statement",
    "do_statement",
    "loop_expression",    # Rust
    # === Switch / case ===
    "switch_case",        # JS/TS — chaque case
    "case_statement",     # variantes
    "case_clause",
    # === Exceptions ===
    "except_clause",      # Python
    "catch_clause",       # JS/TS/Java
    # === Opérateurs booléens court-circuit ===
    # Compte les chaînes `a and b and c` : 2 décisions supplémentaires
    "boolean_operator",   # Python (couvre `and` et `or`)
    "logical_expression", # JS/TS — `&&`, `||`, `??`
    # === Compréhensions Python ===
    # Une listcomp avec `if` à l'intérieur est un point de décision
    # additionnel
})


# Types de nœuds à NE PAS compter (peuvent ressembler à des points de
# décision mais ne le sont pas). Ces noms apparaissent parfois dans les
# arbres tree-sitter et sont EXCLUS explicitement.
_NON_DECISION_NODE_TYPES = frozenset({
    "else_clause",        # déjà compté via le if
    "default_clause",     # default d'un switch — pas un point de décision
    "default_statement",
})


# Texte des opérateurs textuels considérés comme points de décision
# (uniquement quand le nœud est PURE TEXTE, pas un parent qui a un type).
# Pour ces opérateurs, on évite le double comptage : on les ne comptera
# que s'ils ne sont PAS déjà dans un `boolean_operator` / `logical_expression`.
# En pratique, tree-sitter regroupe ces opérateurs sous des nœuds parents,
# donc on n'a pas besoin de les recompter via leur texte.
_DECISION_TEXTUAL_OPS: frozenset = frozenset()  # vide — sécurité contre double comptage


# ---------------------------------------------------------------------------
# Tables Cognitive Complexity (Campbell, 2017)
# ---------------------------------------------------------------------------
#
# Trois familles de nœuds dans la méthode Campbell :
#
# 1. INCREMENTING_AND_NESTING : structure de contrôle qui contribue +1 ET
#    augmente le niveau d'imbrication pour ses enfants (if, for, while,
#    switch, catch, ternaire).
#
# 2. INCREMENTING_NO_NESTING : structure qui contribue +1 mais sans bonus
#    d'imbrication (else, elif, opérateurs booléens mixtes).
#
# 3. NESTING_ONLY : conteneur qui n'incrémente pas mais qui compte pour
#    le niveau d'imbrication (lambdas et fonctions imbriquées).
#
# Note importante : `else if` (en C/JS) ou `elif` (Python) ne crée PAS un
# nouveau niveau d'imbrication. C'est ce qui distingue cognitive de
# McCabe : sur une chaîne `if/elif/elif/elif`, McCabe compte 4 décisions
# mais cognitive compte 1 + 1 + 1 + 1 = 4 (sans bonus) alors que pour
# `if { if { if { if { ... } } } }` cognitive donne 1+2+3+4 = 10.

_COGNITIVE_INCREMENT_AND_NEST = frozenset({
    # Branchements
    "if_statement",
    "ternary_expression",
    "conditional_expression",  # Python `x if cond else y`
    "if_let_expression",       # Rust
    "match_expression",        # Rust (chaque match incrémente)
    # Boucles
    "for_statement",
    "for_in_statement",
    "for_of_statement",
    "for_each_statement",
    "while_statement",
    "do_statement",
    "loop_expression",         # Rust
    # Exceptions
    "catch_clause",
    "except_clause",           # Python
    # Switch
    "switch_statement",
})


_COGNITIVE_INCREMENT_NO_NEST = frozenset({
    # elif/else if : continuation, pas nouveau niveau
    "elif_clause",
    "else_if_clause",
    # Opérateurs booléens (compté une fois par séquence, voir _walk)
    # NB : on ne les ajoute pas ici, on les traite spécialement dans
    # le walker pour gérer le cas des séquences `a && b && c` (1 point)
    # vs `a && b || c` (2 points pour changement d'opérateur).
    # Les `break`/`continue` avec label : +1 (rare en Python)
})


_COGNITIVE_NESTING_ONLY = frozenset({
    # Fonctions et lambdas imbriquées : augmentent le niveau de nesting
    # mais ne contribuent pas elles-mêmes au score
    "lambda",
    "function_definition",  # quand imbriqué dans une autre fonction
    "function_expression",
    "arrow_function",
    "method_definition",
    "class_definition",     # Python (méthode interne d'une classe)
})


# Types qu'on considère comme conteneurs neutres : ne contribuent ni à
# l'incrément ni au nesting (ex. expression_statement, block, etc.)
_COGNITIVE_NEUTRAL = frozenset({
    "block", "statement_block", "module", "program",
    "source_file", "compilation_unit",
})


# ---------------------------------------------------------------------------
# Tables Understandability (fonctions et imbrication)
# ---------------------------------------------------------------------------
#
# Nœuds tree-sitter qui définissent une "fonction" au sens large.
# On exclut les lambdas dans certains contextes pour éviter le bruit, mais
# on les inclut comme fonctions à part entière car elles peuvent être
# complexes.
_FUNCTION_NODE_TYPES = frozenset({
    # Python
    "function_definition",   # def
    # JavaScript / TypeScript
    "function_declaration",  # function name() {}
    "function_expression",   # const f = function() {}
    "method_definition",     # méthodes de classe
    "arrow_function",        # () => {}
    "generator_function",
    "generator_function_declaration",
    # Rust
    "function_item",         # fn name() {}
    # Go
    "function_declaration",  # déjà inclus
    "method_declaration",    # méthodes Go
    # Java
    "method_declaration",    # déjà inclus
    "constructor_declaration",
    # C / C++
    "function_definition",   # déjà inclus
})


# Types de nœuds qui augmentent la profondeur d'imbrication structurelle
# (similaire à _COGNITIVE_INCREMENT_AND_NEST mais plus restrictif :
# uniquement le contrôle de flux, pas les exceptions ni les opérateurs)
_NESTING_NODE_TYPES = frozenset({
    "if_statement",
    "for_statement", "for_in_statement", "for_of_statement", "for_each_statement",
    "while_statement", "do_statement",
    "switch_statement",
    "match_expression",       # Rust
    "try_statement", "try_expression",
    "with_statement",         # Python (gestion de contexte)
})


# Champs tree-sitter contenant les paramètres d'une fonction selon le langage
# (utilisé via child_by_field_name)
_PARAMETER_FIELDS = ("parameters", "parameter_list", "formal_parameters")


# Types de nœuds qui SONT des paramètres individuels dans une liste de
# paramètres tree-sitter
_PARAMETER_NODE_TYPES = frozenset({
    # Python
    "identifier",                   # def f(x, y) → x et y
    "typed_parameter",              # def f(x: int)
    "default_parameter",            # def f(x=1)
    "typed_default_parameter",      # def f(x: int = 1)
    "list_splat_pattern",           # def f(*args)
    "dictionary_splat_pattern",     # def f(**kwargs)
    # JavaScript / TypeScript
    "required_parameter",
    "optional_parameter",
    "rest_pattern",
    "object_pattern",               # destructuring
    "array_pattern",
    # Rust
    "parameter",
    "self_parameter",
    # Go / Java
    "parameter_declaration",
    "formal_parameter",
})


# Types d'identifiants qu'on prend en compte pour la longueur moyenne
_IDENTIFIER_NODE_TYPES = frozenset({
    "identifier",
    "property_identifier",
    "type_identifier",
    "field_identifier",
    "shorthand_property_identifier",
})


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class CodeAnalyzer:
    """Analyseur de code unifié — comptage de lignes ET Halstead.

    Utilise tree-sitter pour parser, avec un cache des grammaires chargées
    (coûteux à instancier mais réutilisable entre appels).

    Usage typique :

        analyzer = CodeAnalyzer()
        r = analyzer.analyze("def f(): return 1", language="python")
        print(r.lines.ncloc, r.halstead.volume)

    Pour une analyse unique sans réutilisation, on peut aussi utiliser les
    fonctions de convenance `analyze()`, `count_lines()`, `count_halstead()`
    exposées par le module.
    """

    def __init__(
        self,
        *,
        understandability_weights: Optional[dict] = None,
        understandability_thresholds: Optional[dict] = None,
    ):
        """Crée un analyzer. Le cache des grammaires tree-sitter est local
        à l'instance.

        Paramètres optionnels :

        - ``understandability_weights`` : dict des 6 poids des sous-métriques
          d'Understandability. Si None, utilise les défauts (cf. models.py).
        - ``understandability_thresholds`` : dict imbriqué metric →
          {low, high, very_high}. Si None, utilise les défauts.

        Ces deux paramètres permettent d'injecter une configuration
        externe (typiquement depuis kodoneko.toml via la classe
        ``KodoNekoConfig``).
        """
        self._language_cache: dict[str, "Language"] = {}  # noqa: F821
        self._parser_cache: dict[str, "Parser"] = {}      # noqa: F821
        self._u_weights = understandability_weights
        self._u_thresholds = understandability_thresholds

    # -------------------------------------------------------------------
    # Chargement des grammaires (paresseux + caché)
    # -------------------------------------------------------------------

    def _get_parser(self, language: str):
        """Retourne un parser tree-sitter pour le langage donné.

        Charge la grammaire à la demande et la met en cache.
        """
        if language in self._parser_cache:
            return self._parser_cache[language]

        try:
            from tree_sitter import Language, Parser
        except ImportError as e:
            raise ImportError(
                "tree-sitter n'est pas installé. Installer avec :\n"
                "    pip install tree-sitter tree-sitter-python "
                "tree-sitter-typescript tree-sitter-javascript"
            ) from e

        if language not in _TS_LANGUAGE_LOADERS:
            raise LanguageNotSupported(
                f"Langage {language!r} non supporté. Langages disponibles : "
                f"{sorted(_TS_LANGUAGE_LOADERS.keys())}"
            )

        module_name, func_name = _TS_LANGUAGE_LOADERS[language]
        try:
            ts_module = __import__(module_name)
        except ImportError as e:
            raise ImportError(
                f"Module {module_name} non installé. "
                f"Installer avec : pip install {module_name.replace('_', '-')}"
            ) from e

        ts_lang = Language(getattr(ts_module, func_name)())
        parser = Parser(ts_lang)
        self._language_cache[language] = ts_lang
        self._parser_cache[language] = parser
        return parser

    def supported_languages(self) -> list[str]:
        """Liste des langages pour lesquels une grammaire tree-sitter est
        configurée (sans vérifier l'installation effective de chacune)."""
        return sorted(_TS_LANGUAGE_LOADERS.keys())

    def get_parser(self, language: str):
        """API publique : retourne un parser tree-sitter pour le langage.

        Wrapper public sur :meth:`_get_parser`. Utilisé notamment par le
        sous-module ``cosmic`` pour réutiliser le système de cache de
        parsers de CodeAnalyzer sans dupliquer la logique de chargement
        des grammaires.
        """
        return self._get_parser(language)

    # -------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------

    def parse(self, source: SourceInput, *, language: Optional[str] = None,
              hint_path: Optional[str] = None, encoding: str = "utf-8"):
        """Parse une source et retourne (text, tree, language).

        Détecte le langage automatiquement si non fourni. Utile pour
        mutualiser le parsing avant plusieurs analyses.
        """
        text, detected_path = normalize_input(
            source, encoding=encoding, treat_str_as="auto",
        )
        if language is None:
            language = detect_language(
                text, hint_path=hint_path or detected_path,
                encoding=encoding,
            )
            if language is None:
                raise LanguageDetectionFailed(
                    "Impossible de détecter le langage. Spécifier "
                    "`language=...` explicitement."
                )

        parser = self._get_parser(language)
        tree = parser.parse(text.encode("utf-8"))
        return text, tree, language

    # -------------------------------------------------------------------
    # API publique : analyse tout-en-un (parsing mutualisé en interne)
    # -------------------------------------------------------------------

    def analyze(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
        exclude_docstrings: bool = True,
    ) -> CombinedMetrics:
        """Calcule NCLOC + Halstead + McCabe en une seule passe.

        C'est l'API recommandée quand on a besoin de plusieurs métriques.
        Économise les parsings (le coût dominant).

        Paramètres
        ----------
        source : SourceInput
            Source à analyser.
        language : str | None
            Si None, détection automatique.
        hint_path : str | None
            Indication de chemin pour détection par extension.
        encoding : str
            Encodage de décodage.
        exclude_docstrings : bool
            Si True (DÉFAUT depuis v1.1), les docstrings Python sont
            comptées comme commentaires plutôt que comme code. Cohérent
            avec la spec UO KodoNeko. Passer `False` pour reproduire le
            comportement cloc/SonarQube.
        """
        text, tree, language = self.parse(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )

        # Pré-calcul des lignes de docstring (Python uniquement)
        docstring_lines = (
            self._collect_docstring_lines(tree.root_node)
            if language == "python" else frozenset()
        )

        lines = self._count_lines_impl(
            text, tree.root_node, language,
            docstring_lines=docstring_lines,
            exclude_docstrings=exclude_docstrings,
        )
        halstead = self._count_halstead_impl(tree.root_node, language)
        mccabe = self._count_mccabe_impl(tree.root_node, language)
        understandability = self._count_understandability_impl(
            text, tree.root_node, language,
            weights=self._u_weights, thresholds=self._u_thresholds,
        )

        return CombinedMetrics(
            lines=lines, halstead=halstead, mccabe=mccabe,
            understandability=understandability,
            language=language,
        )

    def count_lines(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
        exclude_docstrings: bool = True,
    ) -> LineCounts:
        """Compte les lignes (total, blank, comment, sloc, ncloc).

        Par défaut, les docstrings Python sont comptées comme commentaires
        (convention KodoNeko). Passer `exclude_docstrings=False` pour le
        comportement cloc-like.
        """
        text, tree, language = self.parse(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )
        docstring_lines = (
            self._collect_docstring_lines(tree.root_node)
            if language == "python" else frozenset()
        )
        return self._count_lines_impl(
            text, tree.root_node, language,
            docstring_lines=docstring_lines,
            exclude_docstrings=exclude_docstrings,
        )

    def count_halstead(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> HalsteadMetrics:
        """Calcule les métriques Halstead."""
        text, tree, language = self.parse(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )
        return self._count_halstead_impl(tree.root_node, language)

    def count_mccabe(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> McCabeMetrics:
        """Calcule la complexité cyclomatique de McCabe.

        Définition : CC = 1 + (nombre de points de décision).

        Points de décision comptés : if, elif, for, while, case, except,
        and/&&, or/||, ternaire, match (Rust), compréhensions.
        """
        text, tree, language = self.parse(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )
        return self._count_mccabe_impl(tree.root_node, language)

    # -------------------------------------------------------------------
    # API publique : variantes prenant un arbre déjà parsé
    # -------------------------------------------------------------------

    def count_lines_from_tree(
        self,
        text: str,
        tree,
        *,
        language: str,
        exclude_docstrings: bool = True,
    ) -> LineCounts:
        """Compte les lignes à partir d'un arbre déjà parsé.

        Permet de mutualiser le parsing avec d'autres analyses.
        Par défaut `exclude_docstrings=True` (docstrings = commentaires).
        """
        root = tree.root_node if hasattr(tree, "root_node") else tree
        docstring_lines = (
            self._collect_docstring_lines(root)
            if language == "python" else frozenset()
        )
        return self._count_lines_impl(
            text, root, language,
            docstring_lines=docstring_lines,
            exclude_docstrings=exclude_docstrings,
        )

    def count_halstead_from_tree(
        self,
        text: str,
        tree,
        *,
        language: str,
    ) -> HalsteadMetrics:
        """Compte Halstead à partir d'un arbre déjà parsé."""
        root = tree.root_node if hasattr(tree, "root_node") else tree
        return self._count_halstead_impl(root, language)

    def count_mccabe_from_tree(
        self,
        text: str,
        tree,
        *,
        language: str,
    ) -> McCabeMetrics:
        """Compte la complexité cyclomatique à partir d'un arbre déjà parsé."""
        root = tree.root_node if hasattr(tree, "root_node") else tree
        return self._count_mccabe_impl(root, language)

    # -------------------------------------------------------------------
    # API publique : compréhensibilité (understandability)
    # -------------------------------------------------------------------

    def count_understandability(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> UnderstandabilityMetrics:
        """Calcule la compréhensibilité du code (ISO/IEC 25010).

        Retourne un ``UnderstandabilityMetrics`` dont l'attribut ``.risk``
        donne le niveau de risque composite 0-100 (plus haut = plus dur
        à comprendre). À ne pas confondre avec ``PrimaryQualityScore.score``
        (qui est inversement orienté : plus haut = mieux).

        Combine 6 sous-métriques : cognitive (Campbell), longueur des
        fonctions, profondeur d'imbrication, nombre de paramètres,
        densité visuelle, brièveté des identifiants.

        La valeur cognitive brute (Campbell) reste accessible via
        `result.cognitive`.
        """
        text, tree, language = self.parse(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )
        return self._count_understandability_impl(
            text, tree.root_node, language,
            weights=self._u_weights, thresholds=self._u_thresholds,
        )

    def count_understandability_from_tree(
        self,
        text: str,
        tree,
        *,
        language: str,
    ) -> UnderstandabilityMetrics:
        """Variante from_tree pour mutualiser le parsing."""
        root = tree.root_node if hasattr(tree, "root_node") else tree
        return self._count_understandability_impl(
            text, root, language,
            weights=self._u_weights, thresholds=self._u_thresholds,
        )

    def count_understandability_by_function(
        self,
        source: SourceInput,
        *,
        language: Optional[str] = None,
        hint_path: Optional[str] = None,
        encoding: str = "utf-8",
    ) -> list[FunctionUnderstandability]:
        """Retourne UNIQUEMENT le détail par fonction (sans agrégat fichier).

        Utile pour identifier rapidement les fonctions à refactorer dans
        un fichier globalement bon. La liste est triée par **risque
        décroissant** (les fonctions les plus difficiles en premier).
        """
        r = self.count_understandability(
            source, language=language, hint_path=hint_path, encoding=encoding,
        )
        return list(r.functions)

    # ===================================================================
    # IMPLÉMENTATION : comptage de lignes
    # ===================================================================

    def _count_lines_impl(
        self,
        text: str,
        root_node,
        language: str,
        *,
        docstring_lines: frozenset,
        exclude_docstrings: bool = False,
    ) -> LineCounts:
        """Compte les lignes à partir d'un arbre tree-sitter parsé.

        Méthode : on construit deux ensembles de numéros de ligne (0-based) :
        - code_lines : lignes contenant au moins un nœud non-commentaire
        - comment_lines : lignes contenant un nœud commentaire

        Une ligne est "commentaire seul" si elle est dans comment_lines
        mais PAS dans code_lines.

        Si exclude_docstrings=True (Python uniquement), les lignes de
        docstring sont déplacées de code_lines vers comment_lines.
        """
        lines = text.splitlines()
        total = len(lines)
        if total == 0:
            return LineCounts(0, 0, 0, 0, 0, language, "tree-sitter")

        blank = sum(1 for line in lines if not line.strip())

        code_lines: set[int] = set()
        comment_lines: set[int] = set()
        self._walk_for_lines(root_node, code_lines, comment_lines)

        # Si exclude_docstrings demandé et qu'on est en Python :
        # déplacer les lignes de docstring vers les commentaires
        if exclude_docstrings and docstring_lines:
            comment_lines |= docstring_lines
            code_lines -= docstring_lines

        ncloc = len(code_lines)
        comments_only = len(comment_lines - code_lines)
        sloc = total - blank

        return LineCounts(
            total=total,
            blank=blank,
            comment=comments_only,
            sloc=sloc,
            ncloc=ncloc,
            language=language,
            backend="tree-sitter",
        )

    def _walk_for_lines(self, node, code_lines: set, comment_lines: set) -> None:
        """Parcours récursif pour classer chaque nœud par ligne."""
        t = node.type

        if t in _COMMENT_NODE_TYPES:
            # Un commentaire bloc peut couvrir plusieurs lignes
            start, end = node.start_point[0], node.end_point[0]
            for ln in range(start, end + 1):
                comment_lines.add(ln)
            return  # ne pas descendre dans un commentaire

        if t not in _EXCLUDED_NODE_TYPES:
            code_lines.add(node.start_point[0])

        for child in node.children:
            self._walk_for_lines(child, code_lines, comment_lines)

    # -------------------------------------------------------------------
    # Détection des docstrings Python (côté tree-sitter)
    # -------------------------------------------------------------------

    def _collect_docstring_lines(self, root_node) -> frozenset:
        """Retourne l'ensemble des lignes (0-based) couvertes par des
        docstrings dans le code Python.

        Définition : une docstring est une `expression_statement` dont le
        seul enfant nommé est un `string`, et qui est le PREMIER statement
        d'un `module`, d'un `function_definition` ou d'un `class_definition`.

        Cette logique est spécifique à Python — c'est ce qui justifie la
        séparation entre `_walk_for_lines` (générique) et cette méthode
        (Python uniquement).
        """
        lines: set[int] = set()
        self._collect_docstring_lines_recursive(root_node, lines)
        return frozenset(lines)

    def _collect_docstring_lines_recursive(self, node, lines: set) -> None:
        """Parcours récursif à la recherche de docstrings.

        On regarde si le nœud est un parent potentiel de docstring
        (module / function_definition / class_definition). Si oui, on
        examine le premier statement de son `body`.
        """
        if node.type in _PYTHON_DOCSTRING_PARENTS:
            # Le body est dans le champ "body" (function/class) ou bien c'est
            # le module lui-même
            if node.type == "module":
                body_children = list(node.named_children)
            else:
                body_node = node.child_by_field_name("body")
                if body_node is None:
                    body_children = []
                else:
                    body_children = list(body_node.named_children)

            # Premier statement nommé = candidat docstring
            if body_children:
                first = body_children[0]
                if self._is_docstring_node(first):
                    start = first.start_point[0]
                    end = first.end_point[0]
                    for ln in range(start, end + 1):
                        lines.add(ln)

        # Récursion dans les enfants
        for child in node.children:
            self._collect_docstring_lines_recursive(child, lines)

    @staticmethod
    def _is_docstring_node(node) -> bool:
        """Vrai si node est un `expression_statement` dont le seul enfant
        nommé est un `string`.
        """
        if node.type != "expression_statement":
            return False
        named = node.named_children
        if len(named) != 1:
            return False
        return named[0].type == "string"

    # ===================================================================
    # IMPLÉMENTATION : Halstead
    # ===================================================================

    def _count_halstead_impl(self, root_node, language: str) -> HalsteadMetrics:
        """Calcule les métriques Halstead à partir d'un arbre tree-sitter."""
        operators: dict[str, int] = {}
        operands: dict[str, int] = {}
        self._walk_for_halstead(root_node, operators, operands)
        return HalsteadMetrics(
            n1=len(operators),
            n2=len(operands),
            N1=sum(operators.values()),
            N2=sum(operands.values()),
            language=language,
            backend="tree-sitter",
        )

    def _walk_for_halstead(self, node, operators: dict, operands: dict) -> None:
        """Parcours récursif pour collecter opérateurs et opérandes."""
        # Commentaires : ignorés
        if node.type in _COMMENT_NODE_TYPES:
            return

        cat, key = self._classify_node_halstead(node)
        if cat == "operator":
            operators[key] = operators.get(key, 0) + 1
        elif cat == "operand":
            operands[key] = operands.get(key, 0) + 1

        for child in node.children:
            self._walk_for_halstead(child, operators, operands)

    @staticmethod
    def _classify_node_halstead(node) -> tuple[str, str]:
        """Classe un nœud en opérateur / opérande / ignore."""
        t = node.type

        # Identifiants → opérandes
        if t in _IDENTIFIER_TYPES:
            try:
                text = node.text.decode("utf-8", errors="replace")
            except Exception:
                text = "<?>"
            return ("operand", f"id:{text}")

        # Littéraux → opérandes
        if t in _LITERAL_TYPES:
            try:
                text = node.text.decode("utf-8", errors="replace")
            except Exception:
                text = "<?>"
            if t in _STRING_TYPES and len(text) > 50:
                text = text[:50]
            return ("operand", f"const:{t}:{text}")

        # Structures / mots-clés → opérateurs
        if t in _OPERATOR_NODE_TYPES or t in _TEXTUAL_OPERATORS:
            return ("operator", f"op:{t}")

        return ("ignore", "")

    # ===================================================================
    # IMPLÉMENTATION : McCabe (complexité cyclomatique)
    # ===================================================================

    def _count_mccabe_impl(self, root_node, language: str) -> McCabeMetrics:
        """Calcule la complexité cyclomatique à partir d'un arbre tree-sitter.

        Méthode : on parcourt l'arbre et on compte les nœuds de type
        "point de décision" (voir _DECISION_NODE_TYPES). La complexité
        finale est `1 + decision_count`.

        Cas particulier des opérateurs booléens : un nœud `boolean_operator`
        (Python) ou `logical_expression` (JS/TS) peut représenter une
        chaîne `a and b and c`. On compte le nœud lui-même (+1), pas le
        nombre d'opérateurs internes. C'est conservateur mais cohérent
        avec radon. La précision exacte demanderait de compter les
        opérateurs textuels, ce qui est sensible aux variations de
        grammaire entre versions tree-sitter.
        """
        decision_count = self._walk_for_mccabe(root_node)
        return McCabeMetrics.from_decision_count(
            decision_count,
            language=language,
            backend="tree-sitter",
        )

    def _walk_for_mccabe(self, node) -> int:
        """Parcours récursif. Retourne le nombre de points de décision
        dans le sous-arbre enraciné en `node`.
        """
        # Commentaires : ignorés
        if node.type in _COMMENT_NODE_TYPES:
            return 0

        count = 0
        t = node.type

        # Compte ce nœud s'il est un point de décision
        if t in _DECISION_NODE_TYPES and t not in _NON_DECISION_NODE_TYPES:
            count += 1

        # Récursion dans les enfants
        for child in node.children:
            count += self._walk_for_mccabe(child)

        return count

    # ===================================================================
    # IMPLÉMENTATION : complexité cognitive (Campbell, 2017)
    # ===================================================================
    #
    # Note : depuis v2.0, la complexité cognitive n'est plus exposée comme
    # métrique de premier niveau (la classe CognitiveMetrics a été fusionnée
    # dans UnderstandabilityMetrics). Cette méthode reste utilisée en interne
    # pour alimenter `understandability.cognitive` et le calcul par fonction.

    def _count_cognitive_impl(self, root_node, language: str):
        """Calcule la complexité cognitive à partir d'un arbre tree-sitter.

        Implémentation d'après le white paper public de G. Ann Campbell,
        "Cognitive Complexity — A new way of measuring understandability".

        Retourne un objet avec les attributs `value`, `structural`,
        `nesting_bonus` (namedtuple-like, immutable).
        """
        structural, nesting_bonus = self._walk_for_cognitive(
            root_node, nesting=0,
        )
        return _CognitiveResult(
            value=structural + nesting_bonus,
            structural=structural,
            nesting_bonus=nesting_bonus,
        )

    def _walk_for_cognitive(self, node, *, nesting: int) -> tuple[int, int]:
        """Parcours récursif. Retourne (structural, nesting_bonus) pour
        le sous-arbre enraciné en `node`, avec `nesting` comme niveau
        d'imbrication courant pour ce nœud.

        Logique de comptage :

        - Si le nœud est dans `_COGNITIVE_INCREMENT_AND_NEST` :
              structural += 1
              nesting_bonus += nesting    (le bonus est le niveau actuel)
              les enfants seront traités avec nesting + 1

        - Si le nœud est dans `_COGNITIVE_INCREMENT_NO_NEST` (elif, else-if) :
              structural += 1
              pas de bonus, pas d'augmentation de nesting pour les enfants

        - Si le nœud est dans `_COGNITIVE_NESTING_ONLY` (fonctions imbriquées) :
              pas de contribution propre
              MAIS les enfants seront traités avec nesting + 1, à condition
              que le nœud soit lui-même imbriqué (pas top-level)

        - Sinon : pas de contribution propre, on récurse avec le même nesting.
        """
        # Commentaires : ignorés
        if node.type in _COMMENT_NODE_TYPES:
            return 0, 0

        t = node.type
        structural = 0
        nesting_bonus = 0
        child_nesting = nesting  # niveau passé aux enfants par défaut

        if t in _COGNITIVE_INCREMENT_AND_NEST:
            structural += 1
            nesting_bonus += nesting  # bonus = niveau actuel
            child_nesting = nesting + 1
        elif t in _COGNITIVE_INCREMENT_NO_NEST:
            structural += 1
            # Pas de bonus, pas d'augmentation de nesting
        elif t in _COGNITIVE_NESTING_ONLY:
            # Augmente le nesting pour les enfants uniquement si on est
            # déjà imbriqué (= ce n'est pas la fonction top-level)
            if nesting > 0:
                child_nesting = nesting + 1
            # Sinon : nesting reste à 0 pour le corps de la fonction

        # Récursion
        for child in node.children:
            s, n = self._walk_for_cognitive(child, nesting=child_nesting)
            structural += s
            nesting_bonus += n

        return structural, nesting_bonus

    # ===================================================================
    # IMPLÉMENTATION : compréhensibilité (understandability)
    # ===================================================================

    def _count_understandability_impl(
        self, text: str, root_node, language: str,
        *, weights=None, thresholds=None,
    ) -> UnderstandabilityMetrics:
        """Calcule UnderstandabilityMetrics : agrégat fichier + détail par fonction.

        Méthode :
        1. Parcours global : récolte des identifiants pour identifier_length_avg.
        2. Mesure de la densité de ligne (caractères/ligne non-vide).
        3. Énumération des fonctions : pour chaque, calcule cognitive,
           profondeur d'imbrication, nb paramètres, longueur.
        4. Agrégation au niveau fichier (max/avg) + score composite.

        Les arguments ``weights`` et ``thresholds`` permettent d'injecter
        une configuration externe (cf. kodoneko_scanner.config).
        """
        # 1) Métriques globales (sur tout le fichier)
        id_lengths = self._collect_identifier_lengths(root_node)
        id_avg = (sum(id_lengths) / len(id_lengths)) if id_lengths else 8.0

        # 2) Densité visuelle : caractères non-blancs par ligne non-vide
        density = self._compute_line_density(text)

        # 3) Énumérer les fonctions et calculer leurs métriques
        functions_data = self._collect_functions(root_node, language)

        # 4) Agrégation fichier
        if functions_data:
            length_max = max(f["length"] for f in functions_data)
            length_avg = sum(f["length"] for f in functions_data) / len(functions_data)
            depth_max = max(f["nesting_depth"] for f in functions_data)
            params_max = max(f["parameter_count"] for f in functions_data)
            cog_max = max(f["cognitive_value"] for f in functions_data)
        else:
            length_max = 0
            length_avg = 0.0
            depth_max = 0
            params_max = 0
            cog_max = 0

        # Calcul du niveau de risque d'understandability pour chaque fonction
        func_objects = []
        for f in functions_data:
            risk_f = self._compute_function_risk(
                f, id_avg, density,
                weights=weights, thresholds=thresholds,
            )
            level_f = _risk_to_level_local(risk_f)
            func_objects.append(FunctionUnderstandability(
                name=f["name"],
                start_line=f["start_line"],
                end_line=f["end_line"],
                length=f["length"],
                nesting_depth=f["nesting_depth"],
                parameter_count=f["parameter_count"],
                cognitive=f["cognitive_value"],
                risk=round(risk_f, 1),
                level=level_f,
            ))
        # Tri : les plus difficiles en premier (risque le plus élevé d'abord)
        func_objects.sort(key=lambda f: f.risk, reverse=True)

        return UnderstandabilityMetrics.from_components(
            cognitive=cog_max,  # on prend le max sur les fonctions
            function_length_max=length_max,
            function_length_avg=length_avg,
            nesting_depth_max=depth_max,
            parameter_count_max=params_max,
            line_density_avg=density,
            identifier_length_avg=id_avg,
            functions=func_objects,
            language=language,
            backend="tree-sitter",
            weights=weights,
            thresholds=thresholds,
        )

    def _compute_function_risk(
        self, f: dict, id_avg: float, density: float,
        *, weights=None, thresholds=None,
    ) -> float:
        """Calcule le niveau de risque d'understandability d'UNE fonction.

        Réutilise les seuils et pondérations (overridables via weights/
        thresholds).
        """
        from .models import _normalize_component, _UNDERSTANDABILITY_WEIGHTS

        w = weights or _UNDERSTANDABILITY_WEIGHTS

        c_cog = _normalize_component(f["cognitive_value"], "cognitive", thresholds=thresholds)
        c_len = _normalize_component(f["length"], "function_length", thresholds=thresholds)
        c_depth = _normalize_component(f["nesting_depth"], "nesting_depth", thresholds=thresholds)
        c_params = _normalize_component(f["parameter_count"], "parameter_count", thresholds=thresholds)
        c_density = _normalize_component(density, "line_density", thresholds=thresholds)
        c_id = _normalize_component(id_avg, "identifier_length", inverted=True, thresholds=thresholds)

        return (
            w["cognitive"]         * c_cog
            + w["function_length"]   * c_len
            + w["nesting_depth"]     * c_depth
            + w["parameter_count"]   * c_params
            + w["line_density"]      * c_density
            + w["identifier_length"] * c_id
        )

    def _compute_line_density(self, text: str) -> float:
        """Caractères non-blancs / ligne non-vide."""
        non_empty_lines = [line for line in text.splitlines() if line.strip()]
        if not non_empty_lines:
            return 0.0
        total_chars = sum(len(line.rstrip()) for line in non_empty_lines)
        return total_chars / len(non_empty_lines)

    def _collect_identifier_lengths(self, node) -> list:
        """Collecte la longueur de tous les identifiants du sous-arbre."""
        lengths = []
        if node.type in _COMMENT_NODE_TYPES:
            return lengths
        if node.type in _IDENTIFIER_NODE_TYPES:
            try:
                name = node.text.decode("utf-8", errors="replace")
                # Filtre des noms réservés courts comme self, this, _
                if name and not name.startswith("_") and len(name) > 0:
                    lengths.append(len(name))
            except Exception:
                pass
        for child in node.children:
            lengths.extend(self._collect_identifier_lengths(child))
        return lengths

    def _collect_functions(self, root_node, language: str) -> list:
        """Énumère les fonctions du fichier avec leurs métriques.

        Retourne une liste de dicts avec :
          name, start_line, end_line, length, nesting_depth,
          parameter_count, cognitive_value
        """
        functions = []
        self._find_functions_recursive(root_node, functions, language)
        return functions

    def _find_functions_recursive(self, node, functions: list, language: str):
        """Parcours récursif pour trouver les fonctions.

        Une fois qu'on a trouvé une fonction, on calcule ses métriques mais
        on continue à descendre pour trouver les fonctions imbriquées.
        """
        if node.type in _COMMENT_NODE_TYPES:
            return

        if node.type in _FUNCTION_NODE_TYPES:
            # Extraire les métriques de cette fonction
            name = self._extract_function_name(node)
            start_line = node.start_point[0] + 1  # 1-based
            end_line = node.end_point[0] + 1
            length = end_line - start_line + 1

            # Profondeur d'imbrication max DANS cette fonction
            depth = self._compute_max_nesting(node, depth=0)

            # Nombre de paramètres
            param_count = self._count_parameters(node)

            # Complexité cognitive de la fonction
            cog_struct, cog_nest = self._walk_for_cognitive(node, nesting=0)
            cognitive_value = cog_struct + cog_nest

            functions.append({
                "name": name,
                "start_line": start_line,
                "end_line": end_line,
                "length": length,
                "nesting_depth": depth,
                "parameter_count": param_count,
                "cognitive_value": cognitive_value,
            })

        # Continuer à descendre (pour trouver fonctions imbriquées)
        for child in node.children:
            self._find_functions_recursive(child, functions, language)

    def _extract_function_name(self, func_node) -> str:
        """Extrait le nom d'une fonction tree-sitter, ou '<anonymous>'."""
        # Essayer le champ "name" (Python, JS, Rust, Java, Go)
        name_node = func_node.child_by_field_name("name")
        if name_node is not None:
            try:
                return name_node.text.decode("utf-8", errors="replace")
            except Exception:
                pass
        return "<anonymous>"

    def _compute_max_nesting(self, node, *, depth: int) -> int:
        """Profondeur d'imbrication maximale parmi les descendants.

        On compte uniquement les structures de _NESTING_NODE_TYPES.
        Les fonctions imbriquées NE comptent PAS comme niveau (elles
        forment leur propre scope).
        """
        # Ne pas descendre dans une fonction imbriquée
        if node.type in _FUNCTION_NODE_TYPES and depth > 0:
            return depth  # arrêter ici

        current = depth
        if node.type in _NESTING_NODE_TYPES:
            current = depth + 1

        max_seen = current
        for child in node.children:
            if child.type in _COMMENT_NODE_TYPES:
                continue
            child_max = self._compute_max_nesting(child, depth=current)
            if child_max > max_seen:
                max_seen = child_max

        return max_seen

    def _count_parameters(self, func_node) -> int:
        """Compte les paramètres d'une fonction tree-sitter."""
        params_node = None
        for field_name in _PARAMETER_FIELDS:
            params_node = func_node.child_by_field_name(field_name)
            if params_node is not None:
                break

        if params_node is None:
            return 0

        count = 0
        for child in params_node.children:
            if child.type in _PARAMETER_NODE_TYPES:
                count += 1
        return count


# ---------------------------------------------------------------------------
# Helper local (évite import circulaire avec models)
# ---------------------------------------------------------------------------

def _risk_to_level_local(risk: float) -> str:
    """Réimplémentation locale du level mapping pour éviter import circulaire.

    Paliers révisés v2.3 (paliers resserrés post-calibration n=45).
    """
    if risk <= 10:
        return "low"
    if risk <= 27:
        return "moderate"
    if risk <= 50:
        return "high"
    return "very_high"
