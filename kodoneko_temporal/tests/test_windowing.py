"""Tests du découpage temporel (windowing) : mensuel, hebdomadaire, fixe."""

from datetime import date
from kodoneko_temporal import iter_windows


class TestMonthly:
    def test_three_months(self):
        w = list(iter_windows(date(2025, 1, 1), date(2025, 3, 31), strategy="monthly"))
        assert len(w) == 3
        assert w[0].label == "2025-01"
        assert w[-1].label == "2025-03"

    def test_window_bounds_within_month(self):
        w = list(iter_windows(date(2025, 1, 10), date(2025, 1, 20), strategy="monthly"))
        assert len(w) == 1
        # La fenêtre couvre le mois entier
        assert w[0].start <= date(2025, 1, 10)
        assert w[0].end >= date(2025, 1, 20)


class TestWeekly:
    def test_weekly_count(self):
        # ~2 semaines
        w = list(iter_windows(date(2025, 1, 1), date(2025, 1, 14), strategy="weekly"))
        assert len(w) >= 2
        # Les labels hebdo suivent le format ISO semaine
        assert "W" in w[0].label


class TestFixed:
    def test_fixed_10_days(self):
        # 30 jours en fenêtres de 10 -> 3 fenêtres
        w = list(iter_windows(date(2025, 1, 1), date(2025, 1, 30),
                              strategy="fixed", fixed_days=10))
        assert len(w) == 3

    def test_fixed_window_size(self):
        w = list(iter_windows(date(2025, 1, 1), date(2025, 1, 20),
                              strategy="fixed", fixed_days=10))
        # Première fenêtre = 10 jours
        delta = (w[0].end - w[0].start).days
        assert 9 <= delta <= 10


class TestEdgeCases:
    def test_single_day(self):
        w = list(iter_windows(date(2025, 1, 1), date(2025, 1, 1), strategy="monthly"))
        assert len(w) == 1

    def test_labels_unique(self):
        w = list(iter_windows(date(2025, 1, 1), date(2025, 6, 30), strategy="monthly"))
        labels = [x.label for x in w]
        assert len(labels) == len(set(labels))  # tous distincts
