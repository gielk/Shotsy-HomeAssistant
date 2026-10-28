"""Parse a CSV export from the Shotsy app. Pure Python, no Home Assistant imports."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time, tzinfo
import io
import re

from .const import SHOTSY_SITES
from .models import DayLog, Injection, WeightEntry

LBS_TO_KG = 0.45359237
FIXED_COLUMNS = {"date", "shot", "time", "site", "pain level", "taken", "shot notes", "day notes"}
SHOT_RE = re.compile(r"^(?P<med>.*?)\s*(?P<dose>\d+(?:[.,]\d+)?)\s*mg\s*$", re.IGNORECASE)
LEVEL_RE = re.compile(r"^avg .* level", re.IGNORECASE)
WEIGHT_RE = re.compile(r"^(weight|gewicht)\b.*\((?P<unit>kg|lbs?)\)", re.IGNORECASE)
CALORIES_RE = re.compile(r"^(calories|calorie[eë]n)\b", re.IGNORECASE)
PROTEIN_RE = re.compile(r"^(protein|eiwit(ten)?)\b", re.IGNORECASE)
# Weigh-ins have no time in the export; assume a morning weigh-in.
WEIGHT_TIME = time(8, 0)


@dataclass
class ShotsyExport:
    injections: list[Injection] = field(default_factory=list)
    weights: list[WeightEntry] = field(default_factory=list)
    days: dict[date, DayLog] = field(default_factory=dict)
    levels: dict[date, float] = field(default_factory=dict)
    medications: set[str] = field(default_factory=set)
    side_effect_names: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|")]


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def map_site(site: str | None) -> str | None:
    if not site:
        return None
    return SHOTSY_SITES.get(site.strip().lower(), site.strip())


def parse_shotsy_csv(text: str, tz: tzinfo, medication: str | None = None) -> ShotsyExport:
    """Parse the export. Times in the file are local times in ``tz``.

    With ``medication`` set, only shots of that medication are kept, unless
    none of the shots match it.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = reader.fieldnames or []
    weight_col = weight_unit = calories_col = protein_col = None
    level_col = None
    side_cols: list[str] = []
    for header in headers:
        name = header.strip()
        low = name.lower()
        if low in FIXED_COLUMNS:
            continue
        if LEVEL_RE.match(name):
            level_col = header
        elif match := WEIGHT_RE.match(name):
            weight_col, weight_unit = header, match.group("unit").lower()
        elif CALORIES_RE.match(name):
            calories_col = header
        elif PROTEIN_RE.match(name):
            protein_col = header
        elif "(" in name:
            continue  # another metric with a unit, e.g. water or waist
        else:
            side_cols.append(header)

    result = ShotsyExport(side_effect_names=[c.strip() for c in side_cols])
    shots: list[tuple[str, Injection]] = []
    for row in reader:
        try:
            day = date.fromisoformat((row.get("Date") or "").strip())
        except ValueError:
            continue

        if level_col and (level := _number(row.get(level_col))) is not None:
            result.levels[day] = level

        shot_names = _split(row.get("Shot"))
        times = _split(row.get("Time"))
        sites = _split(row.get("Site"))
        pains = _split(row.get("Pain Level"))
        taken = _split(row.get("Taken"))
        notes = _split(row.get("Shot Notes"))
        for i, shot in enumerate(shot_names):
            match = SHOT_RE.match(shot)
            if not match:
                result.skipped.append(f"{day}: {shot}")
                continue
            if i < len(taken) and taken[i].lower() not in ("yes", "ja", "true", "1"):
                continue
            med = match.group("med").strip()
            try:
                hh, mm = (times[i] if i < len(times) else "12:00").split(":")[:2]
                at = datetime.combine(day, time(int(hh), int(mm)), tz)
            except ValueError:
                at = datetime.combine(day, time(12, 0), tz)
            shots.append(
                (
                    med,
                    Injection(
                        time=at,
                        dose_mg=float(match.group("dose").replace(",", ".")),
                        site=map_site(sites[i] if i < len(sites) else None),
                        pain=_number(pains[i]) if i < len(pains) else None,
                        notes=notes[i] if i < len(notes) else "",
                    ),
                )
            )
            result.medications.add(med)

        if weight_col and (kg := _number(row.get(weight_col))) is not None:
            if weight_unit != "kg":
                kg = round(kg * LBS_TO_KG, 2)
            result.weights.append(WeightEntry(time=datetime.combine(day, WEIGHT_TIME, tz), kg=kg, source="shotsy"))

        log = DayLog(
            side_effects={
                col.strip(): value for col in side_cols if (value := _number(row.get(col))) is not None and value > 0
            },
            notes=(row.get("Day Notes") or "").strip(),
            calories=_number(row.get(calories_col)) if calories_col else None,
            protein=_number(row.get(protein_col)) if protein_col else None,
        )
        if not log.is_empty():
            result.days[day] = log

    wanted = medication.strip().lower() if medication else None
    if wanted and any(med.lower() == wanted for med, _ in shots):
        shots = [s for s in shots if s[0].lower() == wanted]
    result.injections = sorted((inj for _, inj in shots), key=lambda i: i.time)
    return result
