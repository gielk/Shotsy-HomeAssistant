"""Pharmacokinetic models for estimating the amount of medication in the body.

Pure Python, no Home Assistant imports, so it can be tested on its own.

Every model exposes ``unit(t_days)``: the fraction of one dose that is still
in the body ``t_days`` after the injection. The estimated level at a moment
is the sum of ``dose_mg * unit(t)`` over all earlier injections.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import math

SECONDS_PER_DAY = 86400.0
# Contributions below this fraction of a dose are ignored.
NEGLIGIBLE = 1e-4


@dataclass(frozen=True)
class ProfileModel:
    """Dose-response curve given as points, with an exponential tail.

    Between the points the curve is interpolated linearly. After the last
    point it decays with ``tail_half_life`` days.
    """

    knots: tuple[float, ...]
    values: tuple[float, ...]
    tail_half_life: float

    @property
    def _ke(self) -> float:
        return math.log(2) / self.tail_half_life

    @property
    def cutoff_days(self) -> float:
        """Days after which a dose no longer counts."""
        last = self.values[-1]
        if last <= NEGLIGIBLE:
            return self.knots[-1]
        return self.knots[-1] + math.log(last / NEGLIGIBLE) / self._ke

    def unit(self, t_days: float) -> float:
        if t_days <= 0:
            return 0.0
        knots = self.knots
        if t_days >= knots[-1]:
            return self.values[-1] * math.exp(-self._ke * (t_days - knots[-1]))
        i = bisect_right(knots, t_days) - 1
        t0, t1 = knots[i], knots[i + 1]
        v0, v1 = self.values[i], self.values[i + 1]
        return v0 + (v1 - v0) * (t_days - t0) / (t1 - t0)

    @property
    def half_life_days(self) -> float:
        return self.tail_half_life


@dataclass(frozen=True)
class BatemanModel:
    """One-compartment model with first-order absorption and elimination."""

    half_life: float  # elimination half-life in days
    tmax: float  # time of peak level after one dose, in days

    @property
    def _ke(self) -> float:
        return math.log(2) / self.half_life

    @property
    def _ka(self) -> float:
        return absorption_rate(self._ke, self.tmax)

    @property
    def cutoff_days(self) -> float:
        return math.log(1 / NEGLIGIBLE) / self._ke + 2 * self.tmax

    def unit(self, t_days: float) -> float:
        if t_days <= 0:
            return 0.0
        ka, ke = self._ka, self._ke
        return ka / (ka - ke) * (math.exp(-ke * t_days) - math.exp(-ka * t_days))

    @property
    def half_life_days(self) -> float:
        return self.half_life


def absorption_rate(ke: float, tmax: float) -> float:
    """Return the absorption rate ka (per day) that peaks at ``tmax`` days.

    For first-order absorption tmax = ln(ka/ke) / (ka - ke). That function
    falls as ka grows (for ka > ke), so bisection finds ka.
    """
    # The peak can't come later than 1/ke (the limit for ka -> ke).
    tmax = min(tmax, 0.999 / ke)

    def peak(ka: float) -> float:
        return math.log(ka / ke) / (ka - ke)

    lo, hi = ke * 1.000001, ke + 1.0
    while peak(hi) > tmax:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if peak(mid) > tmax:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


Model = ProfileModel | BatemanModel


# Retatrutide: dose-response curve fitted to 13 months of Shotsy exports
# (75 injections, 406 daily averages). It matches Shotsy's own estimate within
# about 0.12 mg. Peak about 1.5 days after the injection, then a tail with a
# half-life of 7 days. Published half-life is about 6 days (Urva et al.,
# Lancet 2022).
RETATRUTIDE = ProfileModel(
    knots=(0, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8, 9, 10, 12, 14),
    values=(
        0.0, 0.544, 0.694, 0.804, 0.825, 0.804, 0.794, 0.776, 0.741, 0.674,
        0.584, 0.503, 0.441, 0.414, 0.372, 0.326, 0.293, 0.257, 0.207, 0.176,
    ),
    tail_half_life=7.0,
)

# Values from the product labels: tirzepatide (Mounjaro) peak 8-72 h,
# half-life about 5 days; semaglutide (Ozempic/Wegovy) peak 1-3 days,
# half-life about 7 days.
TIRZEPATIDE = BatemanModel(half_life=5.0, tmax=1.0)
SEMAGLUTIDE = BatemanModel(half_life=7.0, tmax=2.0)

PRESET_MODELS: dict[str, Model] = {
    "retatrutide": RETATRUTIDE,
    "tirzepatide": TIRZEPATIDE,
    "semaglutide": SEMAGLUTIDE,
}


class LevelCalculator:
    """Sum the contributions of all injections for a model."""

    def __init__(self, model: Model, doses: list[tuple[float, float]]) -> None:
        """``doses`` is a list of (unix timestamp, mg)."""
        self.model = model
        ordered = sorted(doses)
        self._times = [t for t, _ in ordered]
        self._mg = [mg for _, mg in ordered]
        self._window = model.cutoff_days * SECONDS_PER_DAY

    def at(self, ts: float) -> float:
        """Estimated amount in mg at unix timestamp ``ts``."""
        lo = bisect_left(self._times, ts - self._window)
        hi = bisect_left(self._times, ts)
        unit = self.model.unit
        total = 0.0
        for i in range(lo, hi):
            total += self._mg[i] * unit((ts - self._times[i]) / SECONDS_PER_DAY)
        return total

    def average(self, start_ts: float, end_ts: float, samples: int = 48) -> float:
        """Mean level over [start_ts, end_ts), sampled at interval midpoints."""
        step = (end_ts - start_ts) / samples
        return sum(self.at(start_ts + (i + 0.5) * step) for i in range(samples)) / samples

    def series(self, start_ts: float, end_ts: float, step_s: float) -> list[tuple[float, float]]:
        out = []
        ts = start_ts
        while ts <= end_ts:
            out.append((ts, self.at(ts)))
            ts += step_s
        return out
