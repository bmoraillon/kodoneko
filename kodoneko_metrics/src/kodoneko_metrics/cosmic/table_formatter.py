"""Rendu tabulaire de l'analyse COSMIC enrichie, façon manuel COSMIC.

Reproduit le format des case studies officielles (C-REG, Web Advice Module) :
un tableau par functional process listant chaque data movement avec son type,
son objet d'intérêt, son data group et son CFP.

Deux sorties : texte (console / Markdown) et dict (pour notebook / JSON).
"""

from __future__ import annotations

from .analysis_report import EnrichedFileAnalysis, FunctionalProcessView


_TYPE_SYMBOL = {"entry": "E", "read": "R", "write": "W", "exit": "X"}


def render_markdown(analysis: EnrichedFileAnalysis) -> str:
    """Rend l'analyse en Markdown, façon tableau de manuel COSMIC."""
    lines: list[str] = []
    lines.append(f"# Analyse COSMIC — {analysis.path}")
    lines.append("")
    lines.append(f"**Langage** : {analysis.language}  ")
    lines.append(f"**Taille estimée** : {analysis.interval.label()}  ")
    lines.append(
        f"**Plancher haute confiance** : "
        f"{analysis.interval.high_confidence_floor} CFP"
    )
    lines.append("")
    lines.append(
        "> ⚠️ Les objets d'intérêt et data groups sont **estimés** par "
        "analyse statique. Un comptage COSMIC certifié requiert l'analyse "
        "des FUR par un mesureur. La valeur est un estimateur avec intervalle."
    )
    lines.append("")

    for fp in analysis.functional_processes:
        lines.append(f"## {fp.name}")
        lines.append("")
        lines.append(
            "| Ligne | Type | Objet d'intérêt | Data group | Détecteur | Conf. | CFP |"
        )
        lines.append(
            "|------:|:----:|-----------------|------------|-----------|:-----:|:---:|"
        )
        for m in fp.movements:
            sym = _TYPE_SYMBOL.get(m.type, m.type)
            ooi = m.object_of_interest or "—"
            dg = m.data_group or "—"
            conf = {"high": "●", "medium": "◐", "low": "○"}.get(m.confidence, "?")
            lines.append(
                f"| {m.line} | {sym} | {ooi} | {dg} | "
                f"`{m.detector}` | {conf} | 1 |"
            )
        bt = fp.by_type()
        lines.append(
            f"| | | | | **Sous-total** | | "
            f"**{fp.raw_cfp}** |"
        )
        # Ligne frequency-rule si différence
        if fp.strict_cfp != fp.raw_cfp:
            lines.append(
                f"| | | | | _après fusion des messages_ | | "
                f"_{fp.strict_cfp}_ |"
            )
        lines.append("")
        lines.append(
            f"_E={bt['entry']} R={bt['read']} W={bt['write']} X={bt['exit']}_"
        )
        lines.append("")

    # Récapitulatif
    lines.append("## Récapitulatif")
    lines.append("")
    lines.append("| Functional process | CFP brut | CFP strict | E | R | W | X |")
    lines.append("|--------------------|:--------:|:----------:|:-:|:-:|:-:|:-:|")
    for fp in analysis.functional_processes:
        bt = fp.by_type()
        lines.append(
            f"| {fp.name} | {fp.raw_cfp} | {fp.strict_cfp} | "
            f"{bt['entry']} | {bt['read']} | {bt['write']} | {bt['exit']} |"
        )
    iv = analysis.interval
    lines.append(
        f"| **Total** | **{iv.high}** | **{iv.central}** | | | | |"
    )
    lines.append("")
    lines.append(
        f"**Intervalle de confiance** : {iv.label()}  "
    )
    lines.append(
        f"(borne basse {iv.low} = min entre comptage strict {iv.central} "
        f"et plancher haute-confiance {iv.high_confidence_floor} ; "
        f"borne haute {iv.high} = comptage brut)"
    )
    return "\n".join(lines)


def render_repo_markdown(repo_analysis) -> str:
    """Rend l'analyse enrichie d'un repo entier en Markdown.

    Vue de synthèse : intervalle global, liste des FP incertains, puis
    le détail par fichier (tableaux façon manuel).
    """
    lines: list[str] = []
    iv = repo_analysis.interval
    lines.append(f"# Analyse COSMIC — {repo_analysis.scope}")
    lines.append("")
    lines.append(f"**Taille estimée du repo** : {iv.label()}")
    lines.append("")
    lines.append("| Borne | CFP | Signification |")
    lines.append("|-------|----:|---------------|")
    lines.append(f"| Basse | {iv.low} | fusion maximale + détecteurs sûrs |")
    lines.append(f"| Centrale | {iv.central} | messages fusionnés (estimation) |")
    lines.append(f"| Haute | {iv.high} | comptage brut (chaque mouvement) |")
    lines.append(f"| Plancher HC | {iv.high_confidence_floor} | détecteurs 'high' seuls |")
    lines.append("")
    lines.append(f"**Fichiers analysés** : {len(repo_analysis.files)}")
    lines.append("")

    uncertain = repo_analysis.uncertain_fps
    if uncertain:
        lines.append(
            f"## ⚠️ {len(uncertain)} functional process avec incertitude "
            f"de comptage (sorties multiples)"
        )
        lines.append("")
        lines.append(
            "Ces FP ont plusieurs sorties (returns/redirects) après une action. "
            "Le comptage exact dépend du jugement COSMIC sur la fusion des "
            "messages erreur/confirmation — d'où l'écart entre bornes."
        )
        lines.append("")
        for f, n in uncertain:
            lines.append(f"- `{f}` :: {n}")
        lines.append("")

    lines.append("---")
    lines.append("")
    for fa in sorted(repo_analysis.files, key=lambda x: x.interval.high, reverse=True):
        lines.append(render_markdown(fa))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def render_text(analysis: EnrichedFileAnalysis) -> str:
    """Rend l'analyse en texte simple (console)."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"Analyse COSMIC : {analysis.path}")
    lines.append(f"Langage : {analysis.language}")
    lines.append(f"Taille estimée : {analysis.interval.label()}")
    lines.append("=" * 70)

    for fp in analysis.functional_processes:
        lines.append("")
        lines.append(f"### {fp.name}")
        for m in fp.movements:
            sym = _TYPE_SYMBOL.get(m.type, m.type)
            ooi = m.object_of_interest or "—"
            lines.append(
                f"  L{m.line:4d}  {sym}  {ooi:20s}  "
                f"{m.data_group:25s}  [{m.confidence}]  {m.detector}"
            )
        bt = fp.by_type()
        line = (f"  → brut={fp.raw_cfp}  strict={fp.strict_cfp}  "
                f"(E={bt['entry']} R={bt['read']} W={bt['write']} X={bt['exit']})")
        lines.append(line)

    iv = analysis.interval
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"TOTAL : {iv.label()}")
    lines.append(f"  borne basse  : {iv.low} CFP")
    lines.append(f"  central      : {iv.central} CFP (messages fusionnés)")
    lines.append(f"  borne haute  : {iv.high} CFP (comptage brut)")
    lines.append(f"  plancher HC  : {iv.high_confidence_floor} CFP (détecteurs 'high')")
    return "\n".join(lines)
