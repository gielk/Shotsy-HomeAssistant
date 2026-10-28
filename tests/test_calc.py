"""Tests for derived values."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.glp1_tracker.calc import dose_stats, due_after, next_due, suggest_site, weight_stats
from custom_components.glp1_tracker.models import Injection, TrackerData, WeightEntry

TZ = ZoneInfo("Europe/Amsterdam")
START = datetime(2025, 9, 18, 8, 0, tzinfo=TZ)


def test_weight_stats_like_shotsy():
    weights = [
        WeightEntry(START, 140.0),
        WeightEntry(START + timedelta(days=100), 120.0),
        WeightEntry(START + timedelta(days=359), 104.9),
    ]
    stats = weight_stats(weights, None, 100.0, 203)
    assert stats["change"] == -35.1
    assert stats["percent"] == -25.1
    assert stats["bmi"] == 25.5
    assert stats["per_week"] == pytest.approx(-0.68, abs=0.01)
    assert stats["to_goal"] == 4.9
    assert stats["to_goal_percent"] == 12.3
    assert stats["next_milestone"] == 100
    # A start weight set by hand wins over the first measurement.
    assert weight_stats(weights, 150.0, None, None)["change"] == -45.1


def test_suggest_site_rotates():
    sites = ["A", "B", "C"]
    assert suggest_site([], sites) == "A"
    used = [Injection(START + timedelta(days=i), 1, site) for i, site in enumerate(["A", "C", "B", "A"])]
    assert suggest_site(used, sites) == "C"
    assert suggest_site(used[:2], sites) == "B"


def test_next_due():
    data = TrackerData(injections=[Injection(START, 2.0)])
    assert next_due(data, 7) == START + timedelta(days=7)
    data.next_due_override = START + timedelta(days=6)
    assert next_due(data, 7) == START + timedelta(days=6)
    assert next_due(TrackerData(), 7) is None


def test_dose_stats():
    injections = [Injection(START, 2.0), Injection(START + timedelta(days=7), 4.0)]
    weights = [WeightEntry(START, 100.0), WeightEntry(START + timedelta(days=14), 98.0)]
    stats = dose_stats(injections, weights)
    assert stats == [
        {"dose_mg": 2.0, "injections": 1, "weeks": 1.0, "kg_change": -1.0, "kg_per_week": -1.0},
        {"dose_mg": 4.0, "injections": 1, "weeks": 1.0, "kg_change": -1.0, "kg_per_week": -1.0},
    ]


@pytest.mark.parametrize(
    ("last", "expected"),
    [
        # Sunday injection: next is the Saturday before the following Sunday.
        (datetime(2026, 10, 25, 11, 0, tzinfo=TZ), datetime(2026, 10, 31, 11, 0, tzinfo=TZ)),
        # Friday: the next day is too soon, so the Saturday after.
        (datetime(2026, 10, 30, 9, 0, tzinfo=TZ), datetime(2026, 11, 7, 11, 0, tzinfo=TZ)),
        # Wednesday: 10 days, not 3.
        (datetime(2026, 10, 28, 9, 0, tzinfo=TZ), datetime(2026, 11, 7, 11, 0, tzinfo=TZ)),
        # On schedule.
        (datetime(2026, 10, 31, 11, 0, tzinfo=TZ), datetime(2026, 11, 7, 11, 0, tzinfo=TZ)),
    ],
)
def test_due_on_weekday(last, expected):
    assert due_after(last, 7, weekday=5, at=time(11, 0), tz=TZ) == expected


def test_due_at_fixed_time():
    last = datetime(2026, 10, 25, 19, 35, tzinfo=TZ)
    assert due_after(last, 7, at=time(11, 0), tz=TZ) == datetime(2026, 11, 1, 11, 0, tzinfo=TZ)
    # Across the switch to winter time the local time stays the same, also for
    # stored times that carry a fixed offset.
    last = datetime.fromisoformat("2026-10-20T11:00:00+02:00")
    assert due_after(last, 7, weekday=1, tz=TZ) == datetime(2026, 10, 27, 11, 0, tzinfo=TZ)
    assert due_after(last, 7, tz=TZ) == datetime(2026, 10, 27, 11, 0, tzinfo=TZ)
