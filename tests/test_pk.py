"""Tests for the medication level models."""

import math

import pytest

from custom_components.glp1_tracker.pk import (
    RETATRUTIDE,
    BatemanModel,
    LevelCalculator,
    absorption_rate,
)

DAY = 86400


def test_profile_shape():
    assert RETATRUTIDE.unit(0) == 0
    assert RETATRUTIDE.unit(-1) == 0
    # Peak about 1.5 days after the injection.
    peak_t = max((t / 10 for t in range(1, 100)), key=RETATRUTIDE.unit)
    assert 1.0 <= peak_t <= 2.0
    assert RETATRUTIDE.unit(peak_t) == pytest.approx(0.825, abs=0.01)
    # Interpolates between points and decays with a 7 day half-life afterwards.
    assert RETATRUTIDE.unit(0.75) == pytest.approx((0.694 + 0.804) / 2)
    assert RETATRUTIDE.unit(21) == pytest.approx(RETATRUTIDE.unit(14) / 2)
    assert RETATRUTIDE.unit(RETATRUTIDE.cutoff_days) == pytest.approx(1e-4, rel=1e-3)


@pytest.mark.parametrize(("half_life", "tmax"), [(5.0, 1.0), (7.0, 2.0), (6.0, 0.25)])
def test_bateman_peaks_at_tmax(half_life, tmax):
    model = BatemanModel(half_life=half_life, tmax=tmax)
    times = [i / 100 for i in range(1, 2000)]
    peak_t = max(times, key=model.unit)
    assert peak_t == pytest.approx(tmax, abs=0.01)
    # Long after the peak only elimination is left.
    assert model.unit(40 + half_life) / model.unit(40) == pytest.approx(0.5, rel=1e-3)


def test_absorption_rate_round_trip():
    ke = math.log(2) / 6
    ka = absorption_rate(ke, 1.5)
    assert math.log(ka / ke) / (ka - ke) == pytest.approx(1.5, rel=1e-6)


def test_levels_add_up():
    t0 = 1_700_000_000
    calc = LevelCalculator(RETATRUTIDE, [(t0, 2.0), (t0 + 7 * DAY, 4.0)])
    assert calc.at(t0) == 0
    assert calc.at(t0 + DAY) == pytest.approx(2 * RETATRUTIDE.unit(1))
    expected = 2 * RETATRUTIDE.unit(9) + 4 * RETATRUTIDE.unit(2)
    assert calc.at(t0 + 9 * DAY) == pytest.approx(expected)
    # A dose far in the past no longer counts.
    assert LevelCalculator(RETATRUTIDE, [(t0, 2.0)]).at(t0 + 400 * DAY) == 0


def test_average_and_series():
    t0 = 1_700_000_000
    calc = LevelCalculator(RETATRUTIDE, [(t0, 1.0)])
    avg = calc.average(t0 + 2 * DAY, t0 + 3 * DAY, samples=200)
    assert RETATRUTIDE.unit(3) < avg < RETATRUTIDE.unit(2)
    series = calc.series(t0, t0 + DAY, 3600 * 6)
    assert [t for t, _ in series] == [t0 + i * 6 * 3600 for i in range(5)]
