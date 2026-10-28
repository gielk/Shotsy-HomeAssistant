"""Derived values: next injection, site rotation, weight statistics.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

from bisect import bisect_left
import calendar
from datetime import date, datetime, time, timedelta, tzinfo
import math

from .models import Injection, TrackerData, WeightEntry
from .pk import LevelCalculator


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def suggest_site(injections: list[Injection], sites: list[str]) -> str | None:
    """Return the site that was used longest ago (never used comes first)."""
    if not sites:
        return None
    last_used: dict[str, datetime] = {}
    for inj in injections:
        if inj.site:
            last_used[inj.site] = inj.time
    never = [s for s in sites if s not in last_used]
    if never:
        return never[0]
    return min(sites, key=lambda s: last_used[s])


def due_after(
    last: datetime,
    interval_days: float,
    weekday: int | None = None,
    at: time | None = None,
    tz: tzinfo | None = None,
) -> datetime:
    """When the injection after one at ``last`` is due.

    Normally ``interval_days`` later. With a fixed ``weekday`` (0 = Monday) it is
    the nearest such weekday to that moment, so an injection a day late doesn't
    shift the schedule. With ``at`` set, that time of day is used.
    """
    if tz is not None:
        # Stored times have a fixed UTC offset; in the local zone adding days
        # keeps the time of day across daylight saving changes.
        last = last.astimezone(tz)
    target = last + timedelta(days=interval_days)
    if weekday is None and at is None:
        return target
    day = target.date()
    if weekday is not None:
        ahead = (weekday - day.weekday()) % 7
        day += timedelta(days=ahead if ahead <= 3 else ahead - 7)
    return datetime.combine(day, at or target.time(), target.tzinfo)


def next_due(
    data: TrackerData,
    interval_days: float,
    weekday: int | None = None,
    at: time | None = None,
    tz: tzinfo | None = None,
) -> datetime | None:
    if data.next_due_override:
        return data.next_due_override
    if not data.injections:
        return None
    return due_after(data.injections[-1].time, interval_days, weekday, at, tz)


def next_dose(data: TrackerData, default_dose: float | None) -> float | None:
    if data.next_dose is not None:
        return data.next_dose
    if data.injections:
        return data.injections[-1].dose_mg
    return default_dose


def next_site(data: TrackerData, sites: list[str]) -> str | None:
    if data.next_site and data.next_site in sites:
        return data.next_site
    return suggest_site(data.injections, sites)


def _weight_at(weights: list[WeightEntry], at: datetime) -> float | None:
    """Linear interpolation of the weight at ``at``; None outside the data."""
    if not weights or at < weights[0].time or at > weights[-1].time:
        return None
    times = [w.time for w in weights]
    i = bisect_left(times, at)
    if times[i] == at:
        return weights[i].kg
    w0, w1 = weights[i - 1], weights[i]
    frac = (at - w0.time) / (w1.time - w0.time)
    return w0.kg + (w1.kg - w0.kg) * frac


def dose_stats(injections: list[Injection], weights: list[WeightEntry]) -> list[dict]:
    """Weight change per dose: each interval between injections counts for the dose given at its start."""
    if not injections or len(weights) < 2:
        return []
    end = weights[-1].time
    per_dose: dict[float, dict] = {}
    for i, inj in enumerate(injections):
        start = inj.time
        stop = injections[i + 1].time if i + 1 < len(injections) else end
        stop = min(stop, end)
        stats = per_dose.setdefault(inj.dose_mg, {"dose_mg": inj.dose_mg, "injections": 0, "days": 0.0, "kg": 0.0})
        stats["injections"] += 1
        if stop <= start:
            continue
        w_start, w_stop = _weight_at(weights, start), _weight_at(weights, stop)
        if w_start is None or w_stop is None:
            continue
        stats["days"] += (stop - start).total_seconds() / 86400
        stats["kg"] += w_stop - w_start
    out = []
    for dose in sorted(per_dose):
        s = per_dose[dose]
        out.append(
            {
                "dose_mg": dose,
                "injections": s["injections"],
                "weeks": round(s["days"] / 7, 1),
                "kg_change": round(s["kg"], 1),
                "kg_per_week": round(s["kg"] / s["days"] * 7, 2) if s["days"] >= 1 else None,
            }
        )
    return out


def weight_stats(
    weights: list[WeightEntry],
    start_weight: float | None,
    goal_weight: float | None,
    height_cm: float | None,
) -> dict:
    """Statistics as shown on the Shotsy results screen."""
    if not weights:
        return {}
    first, last = weights[0], weights[-1]
    start = start_weight if start_weight else first.kg
    current = last.kg
    change = current - start
    days = (last.time - first.time).total_seconds() / 86400
    stats: dict = {
        "current": round(current, 2),
        "measured_at": last.time,
        "start": round(start, 2),
        "start_date": first.time.date().isoformat(),
        "change": round(change, 1),
        "percent": round(change / start * 100, 1) if start else None,
        "per_week": round(change / days * 7, 2) if days >= 7 else None,
        "lowest": round(min(w.kg for w in weights), 2),
        "bmi": None,
        "goal": goal_weight,
        "to_goal": None,
        "to_goal_percent": None,
        "progress_percent": None,
        "next_milestone": (math.ceil(current / 5) - 1) * 5,
    }
    if height_cm:
        stats["bmi"] = round(current / (height_cm / 100) ** 2, 1)
    if goal_weight and start > goal_weight:
        to_goal = max(current - goal_weight, 0.0)
        stats["to_goal"] = round(to_goal, 1)
        stats["to_goal_percent"] = round(to_goal / (start - goal_weight) * 100, 1)
        stats["progress_percent"] = round(100 - stats["to_goal_percent"], 1)
    return stats


def local_day_bounds(day: date, tz: tzinfo) -> tuple[float, float]:
    start = datetime.combine(day, time(0), tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tz)
    return start.timestamp(), end.timestamp()


def daily_levels(
    calc: LevelCalculator,
    first_day: date,
    last_day: date,
    tz: tzinfo,
    cache: dict[date, float],
    today: date,
) -> dict[date, float]:
    """Average level per local day. Days before ``today`` are cached."""
    out: dict[date, float] = {}
    day = first_day
    while day <= last_day:
        if day < today and day in cache:
            out[day] = cache[day]
        else:
            value = calc.average(*local_day_bounds(day, tz))
            if day < today:
                cache[day] = value
            out[day] = value
        day += timedelta(days=1)
    return out


def month_overview(
    data: TrackerData,
    month_of: date,
    tz: tzinfo,
    levels: dict[date, float],
) -> list[dict]:
    """One entry per day of the month of ``month_of`` for the agenda grid."""
    first = month_of.replace(day=1)
    days_in_month = calendar.monthrange(first.year, first.month)[1]
    doses: dict[date, float] = {}
    for inj in data.injections:
        local_day = inj.time.astimezone(tz).date()
        doses[local_day] = doses.get(local_day, 0) + inj.dose_mg
    weighed = {w.time.astimezone(tz).date() for w in data.weights}
    out = []
    for n in range(days_in_month):
        day = first + timedelta(days=n)
        log = data.days.get(day)
        out.append(
            {
                "date": day.isoformat(),
                "dose": doses.get(day),
                "level": round(levels[day], 2) if day in levels else None,
                "log": bool(log and not log.is_empty()),
                "weight": day in weighed,
            }
        )
    return out
