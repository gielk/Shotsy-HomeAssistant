"""Tests for the Shotsy CSV parser."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from custom_components.glp1_tracker.shotsy_csv import parse_shotsy_csv

TZ = ZoneInfo("Europe/Amsterdam")


def test_parse_sample(sample_csv):
    export = parse_shotsy_csv(sample_csv, TZ, "Retatrutide")

    # The 3 mg shot was not taken; the tirzepatide shot is another medication.
    assert [(i.time, i.dose_mg, i.site) for i in export.injections] == [
        (datetime(2025, 1, 6, 20, 0, tzinfo=TZ), 2.0, "Buik - Rechts Onder"),
        (datetime(2025, 1, 13, 8, 15, tzinfo=TZ), 2.5, "Buik - Links Boven"),
        (datetime(2025, 1, 13, 21, 30, tzinfo=TZ), 0.5, "Dij - Links"),
    ]
    first, second, third = export.injections
    assert first.pain == 1.0 and first.notes == "first one"
    assert second.notes == "note a" and third.pain == 2.0 and third.notes == ""
    assert export.medications == {"Retatrutide", "Tirzepatide"}

    assert [(w.time.date(), w.kg) for w in export.weights] == [
        (date(2025, 1, 6), 120.5),
        (date(2025, 1, 8), 119.8),
        (date(2025, 1, 11), 119.1),
        (date(2025, 1, 13), 118.4),
    ]
    assert all(w.source == "shotsy" for w in export.weights)

    assert export.side_effect_names == ["Food Noise", "Misselijkheid"]
    assert export.days[date(2025, 1, 7)].side_effects == {"Misselijkheid": 3.0}
    assert export.days[date(2025, 1, 7)].notes == "Bit queasy"
    assert export.days[date(2025, 1, 8)].side_effects == {"Food Noise": 2.0}
    assert export.levels[date(2025, 1, 8)] == 1.6


def test_unknown_medication_keeps_all(sample_csv):
    export = parse_shotsy_csv(sample_csv, TZ, "Something else")
    assert len(export.injections) == 4


def test_pounds_are_converted():
    text = "Date,Shot,Time,Weight (lbs)\n2025-02-01,,,220\n"
    export = parse_shotsy_csv(text, TZ)
    assert export.weights[0].kg == 99.79
