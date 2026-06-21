"""Rendu HTML pédagogique de l'analyse COSMIC enrichie.

Contrairement à `render_markdown` (sortie brute façon manuel), ce module
produit un rapport HTML autonome, lisible par un humain non-spécialiste :
explications intégrées, légende des symboles, code couleur par type de
mouvement, encadrés pédagogiques sur l'intervalle de confiance et la
frequency rule, et mise en page soignée.

Destiné à être affiché dans un notebook (via IPython.display.HTML) ou
exporté comme fichier .html autonome pour partage.

Le HTML est volontairement autonome (CSS inline) pour fonctionner partout
sans dépendance externe.
"""

from __future__ import annotations

import html as _html

from .analysis_report import EnrichedFileAnalysis, EnrichedRepoAnalysis


# Couleurs par type de mouvement COSMIC (palette sobre, accessible)
_TYPE_STYLE = {
    "entry": ("E", "Entrée", "#1d4ed8", "#dbeafe"),   # bleu  : données entrantes
    "exit":  ("X", "Sortie", "#9333ea", "#f3e8ff"),   # violet: données sortantes
    "read":  ("R", "Lecture", "#047857", "#d1fae5"),  # vert  : lecture persistance
    "write": ("W", "Écriture", "#b45309", "#fef3c7"), # ambre : écriture persistance
}

_CONF_STYLE = {
    "high":   ("●", "élevée", "#16a34a"),
    "medium": ("◐", "moyenne", "#ca8a04"),
    "low":    ("○", "faible", "#dc2626"),
}


def _esc(s: str) -> str:
    return _html.escape(str(s))


def _movement_badge(mtype: str) -> str:
    sym, label, fg, bg = _TYPE_STYLE.get(mtype, ("?", mtype, "#666", "#eee"))
    return (
        f'<span style="display:inline-block;min-width:1.4em;text-align:center;'
        f'font-weight:700;color:{fg};background:{bg};border-radius:4px;'
        f'padding:1px 6px;" title="{label}">{sym}</span>'
    )


def _conf_badge(conf: str) -> str:
    sym, label, color = _CONF_STYLE.get(conf, ("?", conf, "#666"))
    return f'<span style="color:{color};" title="confiance {label}">{sym}</span>'


# ===========================================================================
# Composants pédagogiques réutilisables
# ===========================================================================

def _legend() -> str:
    """Légende expliquant les symboles, affichée une fois en tête."""
    items = []
    for mtype, (sym, label, fg, bg) in _TYPE_STYLE.items():
        items.append(
            f'<span style="margin-right:14px;white-space:nowrap;">'
            f'{_movement_badge(mtype)} <b>{sym}</b> = {label}</span>'
        )
    conf_items = []
    for conf, (sym, label, color) in _CONF_STYLE.items():
        conf_items.append(
            f'<span style="margin-right:12px;white-space:nowrap;color:{color};">'
            f'{sym} confiance {label}</span>'
        )
    return (
        '<div style="font-size:0.85em;color:#374151;background:#f9fafb;'
        'border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;'
        'margin:10px 0;">'
        '<div style="margin-bottom:6px;"><b>Mouvements de données COSMIC</b> '
        '(un mouvement = 1 CFP) :</div>'
        f'<div style="margin-bottom:8px;">{"".join(items)}</div>'
        '<div style="margin-bottom:6px;"><b>Confiance de détection</b> :</div>'
        f'<div>{"".join(conf_items)}</div>'
        '</div>'
    )


def _interval_explainer(interval) -> str:
    """Encadré expliquant l'intervalle de confiance de façon pédagogique."""
    iv = interval
    has_range = iv.low != iv.high
    if has_range:
        intro = (
            f'L\'estimation se situe entre <b>{iv.low}</b> et <b>{iv.high}</b> '
            f'CFP, avec <b>{iv.central}</b> comme valeur la plus probable.'
        )
    else:
        intro = f'L\'estimation est de <b>{iv.central}</b> CFP (sans ambiguïté de comptage).'

    return (
        '<div style="background:#eff6ff;border-left:4px solid #3b82f6;'
        'border-radius:6px;padding:12px 16px;margin:14px 0;">'
        '<div style="font-weight:700;color:#1e3a8a;margin-bottom:6px;">'
        '📏 Comment lire cette estimation</div>'
        f'<p style="margin:6px 0;color:#1f2937;">{intro}</p>'
        '<table style="border-collapse:collapse;margin-top:8px;font-size:0.9em;">'
        f'<tr><td style="padding:2px 12px 2px 0;color:#6b7280;">Borne basse</td>'
        f'<td style="padding:2px 12px;font-weight:700;">{iv.low} CFP</td>'
        f'<td style="padding:2px 0;color:#6b7280;">fusion maximale des messages '
        f'(hypothèse COSMIC la plus stricte)</td></tr>'
        f'<tr><td style="padding:2px 12px 2px 0;color:#6b7280;">Estimation</td>'
        f'<td style="padding:2px 12px;font-weight:700;color:#1d4ed8;">{iv.central} CFP</td>'
        f'<td style="padding:2px 0;color:#6b7280;">meilleure estimation automatique</td></tr>'
        f'<tr><td style="padding:2px 12px 2px 0;color:#6b7280;">Borne haute</td>'
        f'<td style="padding:2px 12px;font-weight:700;">{iv.high} CFP</td>'
        f'<td style="padding:2px 0;color:#6b7280;">comptage brut (chaque sortie séparée)</td></tr>'
        '</table>'
        '<p style="margin:8px 0 0;font-size:0.85em;color:#6b7280;font-style:italic;">'
        'Le comptage COSMIC exact dépend de l\'interprétation des besoins '
        'fonctionnels (FUR), que l\'analyse statique ne peut pas toujours '
        'trancher. L\'intervalle encadre honnêtement cette incertitude.</p>'
        '</div>'
    )


def _fp_table(fp) -> str:
    """Tableau d'un functional process avec ses mouvements."""
    rows = []
    for m in fp.movements:
        data = _esc(m.object_of_interest) if m.object_of_interest else '<span style="color:#9ca3af;">—</span>'
        rows.append(
            '<tr style="border-bottom:1px solid #f1f5f9;">'
            f'<td style="padding:4px 10px;color:#9ca3af;font-variant-numeric:tabular-nums;">L{m.line}</td>'
            f'<td style="padding:4px 10px;text-align:center;">{_movement_badge(m.type)}</td>'
            f'<td style="padding:4px 10px;">{data}</td>'
            f'<td style="padding:4px 10px;font-family:monospace;font-size:0.85em;color:#6b7280;">{_esc(m.detector)}</td>'
            f'<td style="padding:4px 10px;text-align:center;">{_conf_badge(m.confidence)}</td>'
            '</tr>'
        )

    bt = fp.by_type()
    bt_str = (f'{bt["entry"]}×E &nbsp; {bt["read"]}×R &nbsp; '
              f'{bt["write"]}×W &nbsp; {bt["exit"]}×X')

    # Bandeau de fusion si incertitude
    fusion_note = ""
    if fp.has_fusion_uncertainty:
        fusion_note = (
            '<div style="background:#fffbeb;border:1px solid #fde68a;'
            'border-radius:6px;padding:8px 12px;margin-top:8px;font-size:0.85em;'
            'color:#92400e;">'
            f'⚠️ <b>Sorties multiples détectées</b> : ce processus a plusieurs '
            f'points de sortie ({fp.raw_cfp - fp.min_cfp + 1} sorties). '
            f'Les messages d\'erreur et de confirmation d\'un même processus '
            f'comptent ensemble pour <b>une seule</b> sortie de données. '
            f'L\'estimation se situe donc entre <b>{fp.min_cfp}</b> '
            f'(si toutes les sorties sont des messages) et <b>{fp.raw_cfp}</b> '
            f'CFP (si chaque sortie est distincte).'
            '</div>'
        )

    # En-tête du FP : nom de fonction + ligne de départ + pattern détecteur
    if fp.function_name:
        title = f'{_esc(fp.name)}'
        subtitle = (
            f'<span style="font-weight:400;color:#6b7280;font-size:0.88em;"> — '
            f'début ligne {fp.start_line}, détecté par le pattern '
            f'<code>{_esc(fp.detector)}</code></span>'
        )
    else:
        title = f'{_esc(fp.name)}'
        subtitle = (
            f'<span style="font-weight:400;color:#6b7280;font-size:0.88em;"> — '
            f'détecté par <code>{_esc(fp.detector)}</code></span>'
            if fp.detector else ''
        )

    return (
        f'<div style="margin:18px 0;">'
        f'<div style="font-weight:600;color:#111827;margin-bottom:6px;">'
        f'🔹 {title}{subtitle}</div>'
        '<table style="border-collapse:collapse;width:100%;font-size:0.9em;'
        'background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">'
        '<thead><tr style="background:#f8fafc;text-align:left;color:#475569;">'
        '<th style="padding:6px 10px;font-weight:600;">Ligne</th>'
        '<th style="padding:6px 10px;font-weight:600;text-align:center;">Type</th>'
        '<th style="padding:6px 10px;font-weight:600;">Données manipulées</th>'
        '<th style="padding:6px 10px;font-weight:600;">Détecteur</th>'
        '<th style="padding:6px 10px;font-weight:600;text-align:center;">Conf.</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        f'<div style="font-size:0.82em;color:#6b7280;margin-top:5px;">'
        f'{bt_str} &nbsp;→&nbsp; <b>{fp.strict_cfp} CFP</b> estimés '
        f'(borne {fp.min_cfp}–{fp.raw_cfp})</div>'
        f'{fusion_note}'
        '</div>'
    )


# ===========================================================================
# Rendus publics
# ===========================================================================

def render_html(analysis: EnrichedFileAnalysis, *, standalone: bool = False) -> str:
    """Rend l'analyse d'un fichier en HTML pédagogique.

    Args:
        analysis: l'analyse enrichie d'un fichier.
        standalone: si True, enveloppe dans un document HTML complet
                    (<html><body>...) pour export fichier. Sinon, fragment
                    destiné à IPython.display.HTML dans un notebook.
    """
    iv = analysis.interval
    parts = []
    parts.append(
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
        'Roboto,sans-serif;max-width:900px;color:#111827;line-height:1.5;">'
    )
    # En-tête
    parts.append(
        f'<h2 style="margin:0 0 4px;color:#111827;">Analyse COSMIC</h2>'
        f'<div style="color:#6b7280;font-size:0.9em;margin-bottom:2px;">'
        f'{_esc(analysis.path)}</div>'
        f'<div style="color:#6b7280;font-size:0.9em;">Langage : '
        f'<b>{_esc(analysis.language)}</b></div>'
    )
    # Estimation en grand
    parts.append(
        f'<div style="font-size:1.8em;font-weight:800;color:#1d4ed8;margin:12px 0 4px;">'
        f'{iv.label()}</div>'
    )
    parts.append(_interval_explainer(iv))
    parts.append(_legend())

    # Avertissement estimation
    parts.append(
        '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;'
        'padding:10px 14px;margin:12px 0;font-size:0.85em;color:#7f1d1d;">'
        '<b>⚠️ Ceci est une estimation automatique.</b> Les données manipulées '
        '(objets métier) sont inférées par analyse du code. Un comptage COSMIC '
        'certifié requiert l\'analyse des besoins fonctionnels par un mesureur '
        'qualifié. Cet outil fournit une estimation reproductible et auditable, '
        'utile pour le suivi continu, pas un certificat ISO/IEC 19761.'
        '</div>'
    )

    # Functional processes
    parts.append('<h3 style="margin:18px 0 4px;color:#111827;">Détail par processus fonctionnel</h3>')
    for fp in analysis.functional_processes:
        parts.append(_fp_table(fp))

    parts.append('</div>')
    fragment = "".join(parts)

    if standalone:
        return (
            '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            '<title>Analyse COSMIC</title></head><body style="margin:24px;">'
            f'{fragment}</body></html>'
        )
    return fragment


def render_repo_html(repo_analysis: EnrichedRepoAnalysis, *,
                     standalone: bool = False) -> str:
    """Rend l'analyse d'un repo entier en HTML pédagogique (vue de synthèse)."""
    iv = repo_analysis.interval
    parts = []
    parts.append(
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,'
        'Roboto,sans-serif;max-width:900px;color:#111827;line-height:1.5;">'
    )
    parts.append(
        f'<h2 style="margin:0 0 4px;">Analyse COSMIC — synthèse du dépôt</h2>'
        f'<div style="color:#6b7280;font-size:0.9em;">{_esc(repo_analysis.scope)}</div>'
        f'<div style="font-size:1.8em;font-weight:800;color:#1d4ed8;margin:12px 0 4px;">'
        f'{iv.label()}</div>'
    )
    parts.append(_interval_explainer(iv))

    # Stat de synthèse
    n_files = len(repo_analysis.files)
    n_uncertain = len(repo_analysis.uncertain_fps)
    parts.append(
        f'<div style="display:flex;gap:18px;margin:12px 0;flex-wrap:wrap;">'
        f'<div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;'
        f'padding:10px 18px;"><div style="font-size:1.5em;font-weight:700;">{n_files}</div>'
        f'<div style="color:#6b7280;font-size:0.85em;">fichiers analysés</div></div>'
        f'<div style="background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;'
        f'padding:10px 18px;"><div style="font-size:1.5em;font-weight:700;">{n_uncertain}</div>'
        f'<div style="color:#6b7280;font-size:0.85em;">processus à comptage ambigu</div></div>'
        f'</div>'
    )

    if n_uncertain:
        items = "".join(
            f'<li style="margin:2px 0;"><code>{_esc(f)}</code> :: {_esc(n)}</li>'
            for f, n in repo_analysis.uncertain_fps[:20]
        )
        parts.append(
            '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;'
            'padding:10px 14px;margin:12px 0;font-size:0.88em;color:#92400e;">'
            '<b>Processus où le comptage dépend du jugement COSMIC :</b>'
            f'<ul style="margin:6px 0 0;padding-left:20px;">{items}</ul></div>'
        )

    # Top fichiers par taille
    parts.append('<h3 style="margin:18px 0 8px;">Fichiers par taille estimée</h3>')
    parts.append(
        '<table style="border-collapse:collapse;width:100%;font-size:0.9em;'
        'background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">'
        '<thead><tr style="background:#f8fafc;text-align:left;color:#475569;">'
        '<th style="padding:6px 10px;">Fichier</th>'
        '<th style="padding:6px 10px;text-align:right;">Estimation</th>'
        '<th style="padding:6px 10px;text-align:center;">Intervalle</th>'
        '</tr></thead><tbody>'
    )
    top = sorted(repo_analysis.files, key=lambda x: x.interval.central, reverse=True)
    for fa in top[:25]:
        name = fa.path.split("/")[-1]
        parts.append(
            '<tr style="border-bottom:1px solid #f1f5f9;">'
            f'<td style="padding:4px 10px;font-family:monospace;font-size:0.85em;">{_esc(name)}</td>'
            f'<td style="padding:4px 10px;text-align:right;font-weight:700;color:#1d4ed8;">'
            f'{fa.interval.central}</td>'
            f'<td style="padding:4px 10px;text-align:center;color:#6b7280;">'
            f'[{fa.interval.low}–{fa.interval.high}]</td>'
            '</tr>'
        )
    parts.append('</tbody></table>')
    parts.append('</div>')
    fragment = "".join(parts)

    if standalone:
        return (
            '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            '<title>Analyse COSMIC — dépôt</title></head><body style="margin:24px;">'
            f'{fragment}</body></html>'
        )
    return fragment
