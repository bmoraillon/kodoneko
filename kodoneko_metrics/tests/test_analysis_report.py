"""Tests de l'analyse COSMIC enrichie : FP grouping, intervalle A+B, frequency rule."""

from kodoneko_metrics.cosmic import CosmicAnalyzer
from kodoneko_metrics.cosmic.analysis_report import (
    analyze_enriched, group_by_functional_process, compute_interval,
    enrich_movements,
)
from kodoneko_metrics.cosmic.table_formatter import render_markdown, render_text


def _analyze(code: bytes, path="t.py"):
    return CosmicAnalyzer(mode="practical").analyze_source(code, "python", path)


class TestFunctionalProcessGrouping:

    def test_each_entry_opens_fp(self):
        code = b'''
@app.get("/a")
def a(): return 1

@app.get("/b")
def b(): return 2
'''
        r = _analyze(code)
        fps = group_by_functional_process(enrich_movements(list(r.movements)))
        assert len(fps) == 2

    def test_movements_attached_to_fp(self):
        code = b'''
@app.get("/x")
def x(session=None):
    o = session.get(Owner, 1)
    return o
'''
        r = _analyze(code)
        fps = group_by_functional_process(enrich_movements(list(r.movements)))
        assert len(fps) == 1
        # entry + read + exit = 3 mouvements
        assert len(fps[0].movements) == 3


class TestFrequencyRule:

    def test_multiple_returns_with_write_fuse_in_strict(self):
        # 1 Write + 3 returns → borne haute 5, borne basse fusionne
        code = b'''
@app.post("/edit")
def edit(owner, result, session=None):
    if result.has_errors:
        return "form"
    if owner.bad:
        return "redirect:/x"
    session.add(owner)
    return "redirect:/y"
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        fp = analysis.functional_processes[0]
        assert fp.raw_cfp == 5          # E + 3X + W
        assert fp.strict_cfp == 4       # E + W + 1 data exit + 1 message exit
        assert fp.has_fusion_uncertainty

    def test_single_return_no_fusion(self):
        code = b'''
@app.get("/x")
def x(session=None):
    return session.get(Owner, 1)
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        fp = analysis.functional_processes[0]
        # Pas de returns multiples → pas d'incertitude
        assert not fp.has_fusion_uncertainty


class TestConfidenceInterval:

    def test_interval_brackets_truth(self):
        code = b'''
@app.post("/edit")
def edit(owner, result, session=None):
    if result.has_errors:
        return "form"
    session.add(owner)
    return "redirect:/y"
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        iv = analysis.interval
        assert iv.low <= iv.central <= iv.high

    def test_high_confidence_floor_le_central(self):
        code = b'''
@app.get("/x")
def x(session=None):
    o = session.get(Owner, 1)
    return o
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        iv = analysis.interval
        assert iv.high_confidence_floor <= iv.high


class TestObjectOfInterestInference:

    def test_exception_not_inferred_as_ooi(self):
        code = b'''
@app.get("/x")
def x():
    raise HTTPException(404, "nope")
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        # Aucun mouvement ne doit avoir HTTPException comme OOI
        for fp in analysis.functional_processes:
            for m in fp.movements:
                assert "Exception" not in m.object_of_interest

    def test_model_inferred_as_ooi(self):
        code = b'''
@app.get("/x")
def x(session=None):
    return session.get(Owner, 1)
'''
        r = _analyze(code)
        analysis = analyze_enriched(r)
        reads = [m for fp in analysis.functional_processes
                 for m in fp.movements if m.type == "read"]
        assert any(m.object_of_interest == "Owner" for m in reads)


class TestRendering:

    def test_markdown_renders(self):
        code = b'@app.get("/x")\ndef x(): return 1'
        r = _analyze(code)
        md = render_markdown(analyze_enriched(r))
        assert "Analyse COSMIC" in md
        assert "Functional process" in md or "FP" in md

    def test_text_renders(self):
        code = b'@app.get("/x")\ndef x(): return 1'
        r = _analyze(code)
        txt = render_text(analyze_enriched(r))
        assert "TOTAL" in txt


class TestRobustness:
    """Edge cases verrouillés : dégradation gracieuse, jamais de crash."""

    def _enrich(self, code: bytes):
        r = CosmicAnalyzer(mode="practical").analyze_source(code, "python", "t.py")
        return analyze_enriched(r)

    def test_empty_file(self):
        an = self._enrich(b"")
        assert an.interval.central == 0
        assert an.functional_processes == []

    def test_orphan_read_attaches_to_first_fp(self):
        # Un read partagé (style @ModelAttribute) AVANT le 1er endpoint doit
        # être rattaché au premier FP réel, pas former un FP fantôme.
        code = (b"def find_owner(session):\n"
                b"    return session.get(Owner, 1)\n"
                b"\n"
                b"@app.get('/owners/{id}')\n"
                b"def show(id, session=None):\n"
                b"    return session.get(Owner, id)\n")
        an = self._enrich(code)
        # Un seul FP (l'endpoint), avec le read orphelin rattaché
        assert len(an.functional_processes) == 1
        names = an.functional_processes[0]
        assert "préambule" not in names.name

    def test_pure_utility_file_groups_as_non_endpoint(self):
        # Sans aucun endpoint, les mouvements forment un FP "hors endpoint"
        an = self._enrich(b"def helper(session):\n    return session.get(M, 1)")
        assert len(an.functional_processes) == 1
        assert an.interval.central == 1

    def test_unicode_excerpt(self):
        code = "def caf\u00e9(session=None):\n    return session.get(Mod\u00e8le, 1)".encode()
        an = self._enrich(code)
        assert an.interval.central >= 1

    def test_invalid_syntax_degrades(self):
        an = self._enrich(b"def broken(:")
        assert an.interval.central == 0

    def test_rendering_never_crashes_on_empty(self):
        an = self._enrich(b"")
        assert "Analyse COSMIC" in render_markdown(an)
        assert "TOTAL" in render_text(an)

    def test_interval_label_when_exact(self):
        # low == high → label sans crochets
        an = self._enrich(b"")
        assert an.interval.label() == "0 CFP"


class TestFusionWithoutWrite:
    """Vérifie la correction : la fusion L10 s'applique sans exiger un Write."""

    def _enrich(self, code: bytes):
        r = CosmicAnalyzer(mode="practical").analyze_source(code, "python", "t.py")
        return analyze_enriched(r)

    def test_get_with_multiple_returns_fuses(self):
        # GET recherche : 3 returns alternatifs, AUCUN write → doit fusionner
        code = (b"@app.get('/search')\n"
                b"def search(q, session=None):\n"
                b"    if not q:\n"
                b"        return 'searchForm'\n"
                b"    if q.invalid:\n"
                b"        return 'searchForm'\n"
                b"    return 'resultsList'\n")
        an = self._enrich(code)
        fp = an.functional_processes[0]
        assert fp.raw_cfp == 4       # E + 3X
        assert fp.strict_cfp == 3    # E + 1 data exit + 1 message (fusionnés)
        assert fp.has_fusion_uncertainty

    def test_interval_low_is_maximal_fusion(self):
        # La borne basse = fusion maximale (tous les Exits du FP en 1),
        # donc <= central, et l'intervalle encadre la vérité par le bas.
        code = (b"@app.post('/x')\n"
                b"def x(owner, session=None):\n"
                b"    if owner.bad:\n"
                b"        return 'form'\n"
                b"    session.add(owner)\n"
                b"    return 'redirect:/ok'\n")
        an = self._enrich(code)
        iv = an.interval
        # low (fusion max) <= central (estimation) <= high (brut)
        assert iv.low <= iv.central <= iv.high
        # Ce FP : E + W + (3 returns) ; fusion max = E+W+1X = 3
        fp = an.functional_processes[0]
        assert fp.min_cfp == 3
        assert fp.min_cfp <= fp.strict_cfp <= fp.raw_cfp


class TestHtmlRendering:
    """Vérifie que le rendu HTML pédagogique contient les composants clés."""

    def _enrich(self, code: bytes):
        r = CosmicAnalyzer(mode="practical").analyze_source(code, "python", "t.py")
        return analyze_enriched(r)

    def test_html_has_pedagogical_components(self):
        from kodoneko_metrics.cosmic import render_html
        code = (b"@app.post('/x')\n"
                b"def x(owner, session=None):\n"
                b"    if owner.bad:\n"
                b"        return 'form'\n"
                b"    session.add(owner)\n"
                b"    return 'redirect:/ok'\n")
        html = render_html(self._enrich(code))
        # Composants pédagogiques attendus
        assert "Comment lire cette estimation" in html
        assert "estimation automatique" in html      # avertissement
        assert "Mouvements de données COSMIC" in html  # légende
        assert "Sorties multiples" in html            # bandeau fusion

    def test_html_standalone_is_full_document(self):
        from kodoneko_metrics.cosmic import render_html
        html = render_html(self._enrich(b"@app.get('/x')\ndef x(): return 1"),
                           standalone=True)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_html_fragment_not_full_document(self):
        from kodoneko_metrics.cosmic import render_html
        html = render_html(self._enrich(b"@app.get('/x')\ndef x(): return 1"),
                           standalone=False)
        assert "<!DOCTYPE" not in html

    def test_repo_html_renders(self):
        from kodoneko_metrics.cosmic import (
            analyze_repo_enriched, render_repo_html
        )
        from kodoneko_metrics.cosmic.models import CosmicScanReport
        r = CosmicAnalyzer(mode="practical").analyze_source(
            b"@app.get('/x')\ndef x(session=None): return session.get(M, 1)",
            "python", "a.py")
        scan = CosmicScanReport(scope="repo:/demo", mode="practical")
        scan.files = [r]
        html = render_repo_html(analyze_repo_enriched(scan))
        assert "synthèse du dépôt" in html
        assert "fichiers analysés" in html


class TestFunctionNameAndOOI:
    """Verrouille l'extraction du nom de fonction et l'inférence OOI à 2 niveaux."""

    def _enrich(self, code: bytes, path="t.py"):
        r = CosmicAnalyzer(mode="practical").analyze_source(code, "python", path)
        return analyze_enriched(r)

    def test_function_name_extracted(self):
        an = self._enrich(b'@app.post("/x")\ndef process_creation(o, session=None):\n    return "ok"')
        fp = an.functional_processes[0]
        assert fp.function_name == "process_creation"
        assert "process_creation" in fp.name

    def test_ooi_propagated_within_fp(self):
        # session.get(Owner,...) donne l'OOI ; session.add(owner) doit en hériter
        code = (b'@app.post("/x")\n'
                b'def create(owner, session=None):\n'
                b'    e = session.get(Owner, 1)\n'
                b'    session.add(owner)\n'
                b'    return "ok"')
        an = self._enrich(code)
        movements = an.functional_processes[0].movements
        write = next(m for m in movements if m.type == "write")
        assert write.object_of_interest == "Owner"  # hérité du FP

    def test_ooi_from_filename_fallback(self):
        # Aucun PascalCase dans le code → OOI déduit du nom de fichier
        code = b'@app.get("/list")\ndef listing(session=None):\n    return session.query(x).all()'
        an = self._enrich(code, path="pet_service.py")
        entry = next(m for m in an.functional_processes[0].movements if m.type == "entry")
        assert entry.object_of_interest == "Pet"

    def test_no_design_jargon_in_html(self):
        from kodoneko_metrics.cosmic import render_html
        code = (b'@app.post("/x")\n'
                b'def x(o, session=None):\n'
                b'    if o.bad:\n        return "f"\n'
                b'    session.add(o)\n    return "ok"')
        html = render_html(self._enrich(code))
        # Pas de référence aux noms de règles internes
        assert "16-19" not in html
        assert "frequency rule" not in html.lower()
        # Mais l'explication pédagogique est là
        assert "comptent ensemble" in html
