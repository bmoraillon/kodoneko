"""
Découpage temporel de l'historique d'un dépôt en fenêtres d'analyse.

Stratégies supportées :

- ``monthly`` (défaut) : mois calendaire strict (1er au dernier jour du mois).
  C'est le rythme naturel des revues de pilotage logiciel et celui qui produit
  les labels les plus lisibles pour un humain ("2025-11" = novembre 2025).

- ``weekly`` : semaines ISO 8601 (lundi au dimanche). Label "2025-W47".

- ``fixed`` : fenêtres de durée fixe en jours (ex: 30 jours) glissantes
  à partir d'une date d'ancrage. Label "2025-10-15→2025-11-13".

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

from .models import TemporalWindow


VALID_STRATEGIES = ("monthly", "weekly", "fixed")


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _last_of_month(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _next_month(d: date) -> date:
    """Retourne le 1er du mois suivant."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _monday_of_week(d: date) -> date:
    """Retourne le lundi de la semaine ISO contenant d."""
    return d - timedelta(days=d.weekday())


def _iso_week_label(d: date) -> str:
    """Label semaine ISO type 2025-W47."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def iter_windows(
    start: date,
    end: date,
    *,
    strategy: str = "monthly",
    fixed_days: int = 30,
) -> Iterator[TemporalWindow]:
    """Génère les fenêtres temporelles couvrant [start, end].

    Paramètres
    ----------
    start, end : date
        Bornes inclusives du période à découper.
    strategy : str
        "monthly" (défaut), "weekly" ou "fixed".
    fixed_days : int
        Taille des fenêtres en jours si strategy="fixed".

    Yields
    ------
    TemporalWindow
        Fenêtres successives. Les bornes sont restreintes par [start, end]
        (par exemple si start tombe au milieu d'un mois, la première
        fenêtre commence à start et non au 1er du mois).

    Lève
    ----
    ValueError si strategy invalide ou si start > end.
    """
    if strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"Stratégie inconnue : {strategy!r}. "
            f"Valides : {VALID_STRATEGIES}"
        )
    if start > end:
        raise ValueError(f"start ({start}) > end ({end})")
    if fixed_days <= 0:
        raise ValueError(f"fixed_days doit être > 0, got {fixed_days}")

    if strategy == "monthly":
        yield from _iter_monthly(start, end)
    elif strategy == "weekly":
        yield from _iter_weekly(start, end)
    elif strategy == "fixed":
        yield from _iter_fixed(start, end, fixed_days)


def _iter_monthly(start: date, end: date) -> Iterator[TemporalWindow]:
    """Découpe en mois calendaires."""
    current = start
    while current <= end:
        month_end = _last_of_month(current)
        window_end = min(month_end, end)
        label = f"{current.year}-{current.month:02d}"
        yield TemporalWindow(start=current, end=window_end, label=label)
        # Passer au mois suivant
        if window_end >= end:
            break
        current = _next_month(current)


def _iter_weekly(start: date, end: date) -> Iterator[TemporalWindow]:
    """Découpe en semaines ISO 8601 (lundi-dimanche)."""
    current = start
    while current <= end:
        # Fin de semaine : dimanche
        monday = _monday_of_week(current)
        sunday = monday + timedelta(days=6)
        window_end = min(sunday, end)
        label = _iso_week_label(current)
        yield TemporalWindow(start=current, end=window_end, label=label)
        if window_end >= end:
            break
        current = sunday + timedelta(days=1)


def _iter_fixed(start: date, end: date, days: int) -> Iterator[TemporalWindow]:
    """Découpe en fenêtres de taille fixe."""
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=days - 1), end)
        label = f"{current.isoformat()}→{window_end.isoformat()}"
        yield TemporalWindow(start=current, end=window_end, label=label)
        if window_end >= end:
            break
        current = window_end + timedelta(days=1)
