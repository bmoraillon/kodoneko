"""
Tests pour kodoneko_metrics.

Tests organisés en deux familles :
- Tests universels (mocks tree-sitter, ne nécessitent rien d'installé)
- Tests d'intégration (skippés si tree-sitter pas installé)
"""
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import pytest

from kodoneko_metrics import (
    CodeAnalyzer,
    CombinedMetrics,
    FunctionUnderstandability,
    HalsteadMetrics,
    LanguageDetectionFailed,
    LanguageNotSupported,
    LineCounts,
    McCabeMetrics,
    UnderstandabilityMetrics,
    analyze,
    count_halstead,
    count_lines,
    count_mccabe,
    count_understandability,
    count_understandability_by_function,
    detect_language,
    supported_languages,
)
from _mock_tree_sitter import MockNode, MockTree, node, ident, num, string, comment


def _try_import_tree_sitter() -> bool:
    try:
        import tree_sitter
        import tree_sitter_python
        return True
    except ImportError:
        return False


HAS_TREE_SITTER = _try_import_tree_sitter()
TS_SKIP = pytest.mark.skipif(
    not HAS_TREE_SITTER, reason="tree-sitter non installé"
)


# ===========================================================================
# Modèles de données
# ===========================================================================

class TestModels:
    """Tests des dataclasses."""

    def test_line_counts_to_dict(self):
        lc = LineCounts(10, 2, 3, 8, 5, "python", "tree-sitter")
        d = lc.to_dict()
        assert d["ncloc"] == 5
        assert d["language"] == "python"

    def test_halstead_derived_properties(self):
        h = HalsteadMetrics(n1=2, n2=3, N1=2, N2=3)
        assert h.vocabulary == 5
        assert h.length == 5
        assert math.isclose(h.volume, 5 * math.log2(5))

    def test_halstead_zero_division_safe(self):
        h = HalsteadMetrics(n1=2, n2=0, N1=2, N2=0)
        # difficulty doit être 0 (n2=0 → division évitée)
        assert h.difficulty == 0.0
        # effort = difficulty * volume = 0 (peu importe volume)
        assert h.effort == 0.0

    def test_halstead_volume_zero_when_vocabulary_one(self):
        # Avec vocabulary == 1, log2(1) == 0 → V = 0
        h = HalsteadMetrics(n1=1, n2=0, N1=5, N2=0)
        assert h.vocabulary == 1
        assert h.volume == 0.0

    def test_combined_metrics_to_dict(self):
        lc = LineCounts(10, 2, 0, 8, 8, "python", "tree-sitter")
        h = HalsteadMetrics(n1=3, n2=3, N1=4, N2=5, language="python", backend="tree-sitter")
        m = McCabeMetrics.from_decision_count(5, language="python", backend="tree-sitter")
        u = UnderstandabilityMetrics.from_components(
            cognitive=5,
            function_length_max=10, function_length_avg=10.0,
            nesting_depth_max=1, parameter_count_max=2,
            line_density_avg=40.0, identifier_length_avg=8.0,
            functions=[],
            language="python", backend="tree-sitter",
        )
        cm = CombinedMetrics(
            lines=lc, halstead=h, mccabe=m,
            understandability=u, language="python",
        )
        d = cm.to_dict()
        assert "lines" in d
        assert "halstead" in d
        assert "mccabe" in d
        assert "understandability" in d
        assert d["mccabe"]["value"] == 6
        assert d["understandability"]["cognitive"] == 5
        assert d["language"] == "python"

    def test_frozen(self):
        lc = LineCounts(10, 2, 3, 8, 5, "python", "tree-sitter")
        with pytest.raises(Exception):
            lc.ncloc = 100


# ===========================================================================
# Détection de langage (réutilise la logique testée précédemment)
# ===========================================================================

class TestDetectLanguage:
    def test_python_by_extension(self):
        assert detect_language("/path/to/file.py") == "python"

    def test_typescript_by_extension(self):
        assert detect_language("/path/to/file.tsx") == "tsx"

    def test_python_by_content(self):
        assert detect_language("def foo(): pass") == "python"

    def test_returns_none_when_unclear(self):
        assert detect_language("abc def ghi") is None

    def test_supported_languages_returns_list(self):
        langs = supported_languages()
        assert "python" in langs
        assert "typescript" in langs
        assert len(langs) > 5


# ===========================================================================
# Logique interne du parcours d'arbre (testée via mocks)
# ===========================================================================

class TestLinesWalk:
    """Tests du parcours d'arbre pour comptage de lignes via mocks."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_empty_module(self):
        root = node("module")
        code_lines, comment_lines = set(), set()
        self.analyzer._walk_for_lines(root, code_lines, comment_lines)
        assert code_lines == set()
        assert comment_lines == set()

    def test_simple_identifier(self):
        x = ident("x", line=2)
        root = node("module", x)
        code_lines, comment_lines = set(), set()
        self.analyzer._walk_for_lines(root, code_lines, comment_lines)
        assert code_lines == {2}
        assert comment_lines == set()

    def test_comment_ignored_for_code(self):
        c = comment("# foo", line=1)
        root = node("module", c)
        code_lines, comment_lines = set(), set()
        self.analyzer._walk_for_lines(root, code_lines, comment_lines)
        assert code_lines == set()
        assert comment_lines == {1}

    def test_multiline_comment(self):
        c = comment("/* multi\nline */", line=2, end_line=3)
        root = node("module", c)
        code_lines, comment_lines = set(), set()
        self.analyzer._walk_for_lines(root, code_lines, comment_lines)
        assert comment_lines == {2, 3}
        assert code_lines == set()

    def test_code_and_comment_on_different_lines(self):
        # x sur ligne 2, # foo sur ligne 1
        x = ident("x", line=2)
        c = comment("# foo", line=1)
        root = node("module", c, x)
        code_lines, comment_lines = set(), set()
        self.analyzer._walk_for_lines(root, code_lines, comment_lines)
        assert code_lines == {2}
        assert comment_lines == {1}


class TestHalsteadWalk:
    """Tests du parcours d'arbre pour Halstead via mocks."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_empty_module(self):
        root = node("module")
        ops, operands = {}, {}
        self.analyzer._walk_for_halstead(root, ops, operands)
        assert ops == {}
        assert operands == {}

    def test_simple_identifier_is_operand(self):
        x = ident("x")
        root = node("module", x)
        ops, operands = {}, {}
        self.analyzer._walk_for_halstead(root, ops, operands)
        assert len(operands) == 1
        assert "x" in next(iter(operands.keys()))

    def test_number_is_operand(self):
        n = num(42)
        root = node("module", n)
        ops, operands = {}, {}
        self.analyzer._walk_for_halstead(root, ops, operands)
        assert len(operands) == 1
        assert "42" in next(iter(operands.keys()))

    def test_distinct_vs_total(self):
        """x + x + x : 1 opérande distinct, 3 occurrences."""
        x1 = ident("x", line=0)
        x2 = ident("x", line=0)
        x3 = ident("x", line=0)
        binop1 = node("binary_expression", x1, x2)
        binop2 = node("binary_expression", binop1, x3)
        root = node("module", binop2)
        ops, operands = {}, {}
        self.analyzer._walk_for_halstead(root, ops, operands)
        # 1 opérande distinct (x), 3 occurrences
        assert len(operands) == 1
        assert sum(operands.values()) == 3
        # 1 opérateur distinct (binary_expression), 2 occurrences
        assert len(ops) == 1
        assert sum(ops.values()) == 2

    def test_comment_not_counted(self):
        c = comment("# x + y")
        root = node("module", c)
        ops, operands = {}, {}
        self.analyzer._walk_for_halstead(root, ops, operands)
        assert ops == {}
        assert operands == {}


class TestMcCabeWalk:
    """Tests du parcours d'arbre pour McCabe via mocks."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_no_decision_returns_one(self):
        """Code sans branchement : CC = 1."""
        # Juste une assignation
        x = ident("x")
        root = node("module", x)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.value == 1
        assert m.decision_count == 0
        assert m.level == "low"

    def test_single_if(self):
        """Un if = +1 → CC = 2."""
        if_stmt = node("if_statement")
        root = node("module", if_stmt)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.value == 2
        assert m.decision_count == 1

    def test_if_elif_else(self):
        """if + elif (else ne compte pas) → 2 décisions → CC = 3."""
        if_stmt = node("if_statement")
        elif_clause = node("elif_clause")
        else_clause = node("else_clause")
        root = node("module", if_stmt, elif_clause, else_clause)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.decision_count == 2
        assert m.value == 3

    def test_loops(self):
        """for + while → 2 décisions → CC = 3."""
        for_stmt = node("for_statement")
        while_stmt = node("while_statement")
        root = node("module", for_stmt, while_stmt)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.decision_count == 2
        assert m.value == 3

    def test_boolean_operator(self):
        """`a and b` est un boolean_operator → +1 décision."""
        bool_op = node("boolean_operator")
        root = node("module", bool_op)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.decision_count == 1
        assert m.value == 2

    def test_except_clause(self):
        """try/except : except_clause = +1."""
        try_stmt = node("try_statement", node("except_clause"))
        root = node("module", try_stmt)
        m = self.analyzer._count_mccabe_impl(root, "python")
        # try_statement n'est PAS dans la table de décisions (juste le except)
        assert m.decision_count == 1

    def test_nested_branchings(self):
        """Branchements imbriqués : tous comptés."""
        inner_if = node("if_statement")
        outer_if = node("if_statement", inner_if)
        root = node("module", outer_if)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.decision_count == 2
        assert m.value == 3

    def test_comment_node_ignored(self):
        """Les commentaires ne comptent pas."""
        c = comment("# if False: ...")  # contient le mot "if" textuellement
        root = node("module", c)
        m = self.analyzer._count_mccabe_impl(root, "python")
        assert m.decision_count == 0
        assert m.value == 1

    def test_threshold_low(self):
        # CC ≤ 10 → low
        from kodoneko_metrics.models import McCabeMetrics
        m = McCabeMetrics.from_decision_count(0)
        assert m.value == 1 and m.level == "low"
        m = McCabeMetrics.from_decision_count(9)
        assert m.value == 10 and m.level == "low"

    def test_threshold_moderate(self):
        # 11 ≤ CC ≤ 20 → moderate
        from kodoneko_metrics.models import McCabeMetrics
        m = McCabeMetrics.from_decision_count(10)
        assert m.value == 11 and m.level == "moderate"
        m = McCabeMetrics.from_decision_count(19)
        assert m.value == 20 and m.level == "moderate"

    def test_threshold_high(self):
        # 21 ≤ CC ≤ 50 → high
        from kodoneko_metrics.models import McCabeMetrics
        m = McCabeMetrics.from_decision_count(20)
        assert m.value == 21 and m.level == "high"
        m = McCabeMetrics.from_decision_count(49)
        assert m.value == 50 and m.level == "high"

    def test_threshold_very_high(self):
        # CC > 50 → very_high
        from kodoneko_metrics.models import McCabeMetrics
        m = McCabeMetrics.from_decision_count(50)
        assert m.value == 51 and m.level == "very_high"


class TestDocstringDetection:
    """Tests de la détection de docstrings Python via mocks."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_module_docstring(self):
        # module:
        #   expression_statement:
        #     string ("doc.")  ← docstring
        s = string("doc.", line=0)
        expr_stmt = node("expression_statement", s, line=0)
        root = node("module", expr_stmt, line=0)
        lines = self.analyzer._collect_docstring_lines(root)
        assert 0 in lines

    def test_function_docstring(self):
        # function_definition (body=block):
        #   block:
        #     expression_statement:
        #       string  ← docstring
        s = string("func doc", line=2)
        expr_stmt = node("expression_statement", s, line=2)
        body = node("block", expr_stmt)
        func = node("function_definition")
        func.fields = {"body": body}
        root = node("module", func)
        lines = self.analyzer._collect_docstring_lines(root)
        assert 2 in lines

    def test_non_docstring_string_not_detected(self):
        # module:
        #   assignment: ...
        #   expression_statement: string  ← orpheline, mais PAS en première position
        s_attr = ident("x", line=0)
        eq = node("=", line=0)
        s_val = num(1, line=0)
        assign = node("assignment", s_attr, eq, s_val, line=0)

        s_orphan = string("not a docstring", line=1)
        expr = node("expression_statement", s_orphan, line=1)

        root = node("module", assign, expr)
        lines = self.analyzer._collect_docstring_lines(root)
        # La string orpheline n'est PAS la première instruction du module → pas une docstring
        assert 1 not in lines


# ===========================================================================
# API publique : intégration (nécessite tree-sitter)
# ===========================================================================

@TS_SKIP
class TestCodeAnalyzerPython:
    """Tests d'intégration de CodeAnalyzer avec tree-sitter Python."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_supported_languages(self):
        langs = self.analyzer.supported_languages()
        assert "python" in langs

    def test_simple_python(self):
        r = self.analyzer.analyze("def f(): return 1", language="python")
        assert r.language == "python"
        assert r.lines.ncloc >= 1
        assert r.halstead.n1 > 0
        assert r.halstead.n2 > 0

    def test_count_lines_only(self):
        r = self.analyzer.count_lines("def f(): return 1\n", language="python")
        assert r.language == "python"
        assert r.ncloc == 1
        assert r.backend == "tree-sitter"

    def test_count_halstead_only(self):
        r = self.analyzer.count_halstead("x = 1", language="python")
        assert r.language == "python"
        assert r.n1 >= 1  # au moins un opérateur
        assert r.n2 >= 1  # au moins un opérande

    def test_parse_returns_tree(self):
        text, tree, lang = self.analyzer.parse("x = 1", language="python")
        assert lang == "python"
        assert hasattr(tree, "root_node")

    def test_mutualized_parsing(self):
        """Parser une fois, calculer deux fois avec from_tree."""
        text, tree, lang = self.analyzer.parse(
            "def f(x): return x + 1", language="python",
        )
        lines = self.analyzer.count_lines_from_tree(text, tree, language=lang)
        halstead = self.analyzer.count_halstead_from_tree(text, tree, language=lang)
        assert lines.ncloc >= 1
        assert halstead.n1 > 0

    def test_docstring_excluded_by_default(self):
        """v1.1+ : par défaut, les docstrings sont comptées comme commentaires."""
        code = '''def f():
    """A docstring."""
    return 1
'''
        r = self.analyzer.count_lines(code, language="python")
        # docstring exclue de NCLOC (défaut), comptée comme commentaire
        assert r.ncloc == 2
        assert r.comment >= 1

    def test_docstring_included_when_requested(self):
        """Passer exclude_docstrings=False pour le comportement cloc-like."""
        code = '''def f():
    """A docstring."""
    return 1
'''
        r = self.analyzer.count_lines(
            code, language="python", exclude_docstrings=False,
        )
        # docstring comptée comme code (cloc-like)
        assert r.ncloc == 3


@TS_SKIP
class TestPolymorphicInput:
    """Tests des types d'entrée acceptés."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_string_input(self):
        r = self.analyzer.analyze("x = 1", language="python")
        assert r.lines.ncloc == 1

    def test_bytes_input(self):
        r = self.analyzer.analyze(b"x = 1\n", language="python")
        assert r.lines.ncloc == 1

    def test_stream_input(self):
        r = self.analyzer.analyze(io.StringIO("x = 1\n"), language="python")
        assert r.lines.ncloc == 1

    def test_file_input(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 1\n")
        r = self.analyzer.analyze(f)  # détection auto
        assert r.language == "python"


@TS_SKIP
class TestConvenienceFunctions:
    """Tests des fonctions de convenance (analyze, count_lines, count_halstead)."""

    def test_analyze_function(self):
        r = analyze("def f(): return 1", language="python")
        assert isinstance(r, CombinedMetrics)
        assert r.lines.ncloc >= 1

    def test_count_lines_function(self):
        r = count_lines("def f(): return 1", language="python")
        assert isinstance(r, LineCounts)

    def test_count_halstead_function(self):
        r = count_halstead("def f(): return 1", language="python")
        assert isinstance(r, HalsteadMetrics)


@TS_SKIP
class TestErrors:
    """Tests des cas d'erreur."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_unknown_language(self):
        with pytest.raises(LanguageNotSupported):
            self.analyzer.count_lines("foo", language="brainfuck")

    def test_detection_failure(self):
        with pytest.raises(LanguageDetectionFailed):
            self.analyzer.analyze("abc def ghi")


@TS_SKIP
class TestCache:
    """Test que le cache des grammaires fonctionne."""

    def test_parser_reused(self):
        analyzer = CodeAnalyzer()
        analyzer.count_lines("x = 1", language="python")
        # Le parser doit être en cache après le premier appel
        assert "python" in analyzer._parser_cache
        # Deuxième appel : doit réutiliser le parser, pas en créer un nouveau
        parser_id_1 = id(analyzer._parser_cache["python"])
        analyzer.count_lines("y = 2", language="python")
        parser_id_2 = id(analyzer._parser_cache["python"])
        assert parser_id_1 == parser_id_2


# ===========================================================================
# Tests algorithme Campbell (cognitive complexity, intégrée à Understandability)
# ===========================================================================

class TestCognitiveWalk:
    """Tests de l'algorithme Campbell (cognitive complexity).

    Depuis v2.0, la cognitive n'est plus une métrique de premier niveau
    mais reste calculée en interne pour alimenter UnderstandabilityMetrics.
    Ces tests valident toujours l'algorithme via _count_cognitive_impl
    qui retourne un namedtuple (value, structural, nesting_bonus).
    """

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_empty_module(self):
        root = node("module")
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 0

    def test_single_if(self):
        """Un if isolé → +1 (structural)."""
        if_stmt = node("if_statement")
        root = node("module", if_stmt)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 1
        assert m.structural == 1
        assert m.nesting_bonus == 0

    def test_nested_if(self):
        """if dans if : structural=2, bonus=1 (le if intérieur est à nesting 1)."""
        inner = node("if_statement")
        outer = node("if_statement", inner)
        root = node("module", outer)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.structural == 2
        assert m.nesting_bonus == 1
        assert m.value == 3

    def test_triple_nested(self):
        """Triple imbrication : structural=3, bonus=0+1+2=3, total=6."""
        l2 = node("if_statement")
        l1 = node("for_statement", l2)
        l0 = node("if_statement", l1)
        root = node("module", l0)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 6
        assert m.structural == 3
        assert m.nesting_bonus == 3

    def test_elif_chain(self):
        """if + elif + elif : 3 incréments sans bonus (continuation)."""
        elif1 = node("elif_clause")
        elif2 = node("elif_clause")
        if_stmt = node("if_statement", elif1, elif2)
        root = node("module", if_stmt)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.structural == 3
        assert m.nesting_bonus == 0
        assert m.value == 3

    def test_else_does_not_count(self):
        """else seul ne contribue rien (n'est ni IncrementAndNest ni IncrementNoNest)."""
        else_cl = node("else_clause")
        if_stmt = node("if_statement", else_cl)
        root = node("module", if_stmt)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 1  # seulement le if

    def test_comment_ignored(self):
        comment_node = node("comment")
        if_stmt = node("if_statement")
        root = node("module", comment_node, if_stmt)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 1

    def test_for_with_if_inside(self):
        """Cas Campbell de référence : for + if imbriqué → CCog = 3."""
        if_inner = node("if_statement")
        for_loop = node("for_statement", if_inner)
        root = node("module", for_loop)
        m = self.analyzer._count_cognitive_impl(root, "python")
        assert m.value == 3


class TestCognitiveRemovedFromAPI:
    """Vérifie que CognitiveMetrics et count_cognitive ont bien été retirés
    de l'API publique en v2.0 (fusionnés dans Understandability)."""

    def test_cognitive_metrics_no_longer_exported(self):
        import kodoneko_metrics
        assert not hasattr(kodoneko_metrics, "CognitiveMetrics")
        assert "CognitiveMetrics" not in kodoneko_metrics.__all__

    def test_count_cognitive_no_longer_exported(self):
        import kodoneko_metrics
        assert not hasattr(kodoneko_metrics, "count_cognitive")
        assert "count_cognitive" not in kodoneko_metrics.__all__

    def test_cognitive_available_via_understandability(self):
        """La valeur cognitive reste accessible via understandability.cognitive."""
        u = UnderstandabilityMetrics.from_components(
            cognitive=10,
            function_length_max=10, function_length_avg=10.0,
            nesting_depth_max=1, parameter_count_max=2,
            line_density_avg=40.0, identifier_length_avg=8.0,
            functions=[], language="python", backend="mock",
        )
        assert u.cognitive == 10


# ===========================================================================
# Tests Understandability (ISO/IEC 25010)
# ===========================================================================

class TestUnderstandabilityModels:
    """Tests des modèles UnderstandabilityMetrics et FunctionUnderstandability."""

    def test_function_understandability_basic(self):
        f = FunctionUnderstandability(
            name="my_func",
            start_line=1, end_line=10, length=10,
            nesting_depth=2, parameter_count=3,
            cognitive=5, risk=15.0, level="low",
        )
        assert f.name == "my_func"
        assert f.length == 10
        assert f.cognitive == 5
        d = f.to_dict()
        assert d["name"] == "my_func"
        assert d["cognitive"] == 5

    def test_understandability_metrics_low(self):
        """Une fonction simple et courte donne un score bas."""
        u = UnderstandabilityMetrics.from_components(
            cognitive=2,
            function_length_max=10, function_length_avg=10.0,
            nesting_depth_max=1, parameter_count_max=2,
            line_density_avg=30.0, identifier_length_avg=10.0,
            functions=[],
            language="python", backend="mock",
        )
        assert u.risk < 15
        assert u.level == "low"
        assert u.cognitive == 2

    def test_understandability_metrics_high(self):
        """Une fonction longue et complexe donne un score haut."""
        u = UnderstandabilityMetrics.from_components(
            cognitive=25,
            function_length_max=80, function_length_avg=60.0,
            nesting_depth_max=5, parameter_count_max=8,
            line_density_avg=100.0, identifier_length_avg=2.5,
            functions=[],
            language="python", backend="mock",
        )
        assert u.risk > 35
        assert u.level in ("high", "very_high")

    def test_normalize_component_standard(self):
        """La fonction de normalisation respecte les paliers."""
        from kodoneko_metrics.models import _normalize_component
        # Cognitive : low=3, high=10, very_high=20 (seuils révisés v2.2)
        assert _normalize_component(0, "cognitive") == 0.0
        assert _normalize_component(3, "cognitive") == 0.0
        assert _normalize_component(10, "cognitive") == 33.0
        assert _normalize_component(20, "cognitive") == 66.0

    def test_normalize_component_inverted(self):
        """Pour identifier_length, plus c'est court, plus la pénalité est forte."""
        from kodoneko_metrics.models import _normalize_component
        assert _normalize_component(10, "identifier_length", inverted=True) == 0.0
        assert _normalize_component(5, "identifier_length", inverted=True) == 33.0
        assert _normalize_component(3, "identifier_length", inverted=True) == 66.0

    def test_understandability_to_dict_serializable(self):
        import json
        u = UnderstandabilityMetrics.from_components(
            cognitive=2,
            function_length_max=10, function_length_avg=10.0,
            nesting_depth_max=1, parameter_count_max=2,
            line_density_avg=40.0, identifier_length_avg=8.0,
            functions=[FunctionUnderstandability(
                name="f", start_line=1, end_line=10, length=10,
                nesting_depth=1, parameter_count=2,
                cognitive=2, risk=5.0, level="low",
            )],
            language="python", backend="mock",
        )
        d = u.to_dict()
        # Doit être JSON-sérialisable
        json.dumps(d)
        assert d["risk"] == u.risk
        assert d["cognitive"] == 2
        assert len(d["functions"]) == 1
        assert d["functions"][0]["cognitive"] == 2


class TestUnderstandabilityViaMocks:
    """Tests de _count_understandability_impl via mocks tree-sitter."""

    def setup_method(self):
        self.analyzer = CodeAnalyzer()

    def test_empty_module(self):
        root = node("module")
        u = self.analyzer._count_understandability_impl("", root, "python")
        assert u.risk == 0.0
        assert u.level == "low"
        assert len(u.functions) == 0
        assert u.cognitive == 0

    def test_simple_function(self):
        # def simple_func(x): return x + 1
        name_node = node("identifier", text=b"simple_func")
        param_x = node("identifier", text=b"x")
        params_node = node("parameters", param_x)
        body = node("block")
        func = node("function_definition", line=0, end_line=2)
        func.children = [name_node, params_node, body]
        func.fields = {"name": name_node, "parameters": params_node, "body": body}

        text = "def simple_func(x):\n    return x + 1\n"
        root = node("module", func)
        u = self.analyzer._count_understandability_impl(text, root, "python")

        assert len(u.functions) == 1
        f = u.functions[0]
        assert f.name == "simple_func"
        assert f.parameter_count == 1
        assert u.parameter_count_max == 1

    def test_function_with_nested_if(self):
        # Fonction avec un if imbriqué dans un if
        name_node = node("identifier", text=b"f")
        params_node = node("parameters")
        if_inner = node("if_statement")
        if_outer = node("if_statement", if_inner)
        body = node("block", if_outer)
        func = node("function_definition", line=0, end_line=10)
        func.children = [name_node, params_node, body]
        func.fields = {"name": name_node, "parameters": params_node, "body": body}

        text = "def f():\n" + "\n".join(f"    line{i}" for i in range(9)) + "\n"
        root = node("module", func)
        u = self.analyzer._count_understandability_impl(text, root, "python")

        # La profondeur doit être 2 (if dans if)
        assert u.nesting_depth_max == 2

    def test_many_parameters(self):
        """Une fonction avec 8 paramètres → parameter_count_max = 8."""
        params = [node("identifier", text=c.encode()) for c in "abcdefgh"]
        params_node = node("parameters", *params)
        name_node = node("identifier", text=b"big_fn")
        body = node("block")
        func = node("function_definition", line=0, end_line=5)
        func.children = [name_node, params_node, body]
        func.fields = {"name": name_node, "parameters": params_node, "body": body}

        text = "def big_fn(a, b, c, d, e, f, g, h):\n    pass\n"
        root = node("module", func)
        u = self.analyzer._count_understandability_impl(text, root, "python")
        assert u.parameter_count_max == 8

    def test_functions_sorted_by_score_desc(self):
        """Les fonctions doivent être triées par score décroissant."""
        # Fonction simple
        f1_name = node("identifier", text=b"simple")
        f1_params = node("parameters", node("identifier", text=b"x"))
        f1_body = node("block")
        f1 = node("function_definition", line=0, end_line=2)
        f1.children = [f1_name, f1_params, f1_body]
        f1.fields = {"name": f1_name, "parameters": f1_params, "body": f1_body}

        # Fonction complexe
        params2 = [node("identifier", text=c.encode()) for c in "abcdefgh"]
        f2_name = node("identifier", text=b"big")
        f2_params = node("parameters", *params2)
        deep = node("if_statement", node("if_statement", node("if_statement")))
        f2_body = node("block", deep)
        f2 = node("function_definition", line=5, end_line=60)
        f2.children = [f2_name, f2_params, f2_body]
        f2.fields = {"name": f2_name, "parameters": f2_params, "body": f2_body}

        text = "x" * 100  # texte arbitraire
        root = node("module", f1, f2)
        u = self.analyzer._count_understandability_impl(text, root, "python")

        assert len(u.functions) == 2
        # Le plus complexe doit être en premier
        assert u.functions[0].name == "big"
        assert u.functions[0].risk >= u.functions[1].risk


class TestUnderstandabilityExportsAndAPI:
    """Vérifie l'API publique."""

    def test_imports(self):
        from kodoneko_metrics import (
            UnderstandabilityMetrics, FunctionUnderstandability,
            count_understandability, count_understandability_by_function,
        )
        assert UnderstandabilityMetrics is not None
        assert FunctionUnderstandability is not None
        assert count_understandability is not None
        assert count_understandability_by_function is not None

    def test_in_all(self):
        import kodoneko_metrics
        assert "UnderstandabilityMetrics" in kodoneko_metrics.__all__
        assert "FunctionUnderstandability" in kodoneko_metrics.__all__
        assert "count_understandability" in kodoneko_metrics.__all__
        assert "count_understandability_by_function" in kodoneko_metrics.__all__

    def test_old_names_no_longer_exported(self):
        """Les anciens noms (ReadabilityMetrics, FunctionReadability, FRD) ne sont
        plus exportés en v2.0."""
        import kodoneko_metrics
        for old in ("ReadabilityMetrics", "FunctionReadability",
                    "count_readability", "count_readability_by_function"):
            assert not hasattr(kodoneko_metrics, old), f"{old} ne doit plus être exporté"
            assert old not in kodoneko_metrics.__all__
