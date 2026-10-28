"""Stored data for one medication. Pure Python, JSON-serialisable."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Injection:
    time: datetime  # timezone-aware
    dose_mg: float
    site: str | None = None
    pain: float | None = None
    notes: str = ""
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Injection:
        return cls(
            time=datetime.fromisoformat(data["time"]),
            dose_mg=float(data["dose_mg"]),
            site=data.get("site"),
            pain=data.get("pain"),
            notes=data.get("notes") or "",
            id=data.get("id") or new_id(),
        )


@dataclass
class WeightEntry:
    time: datetime  # timezone-aware
    kg: float
    source: str = "manual"  # manual, sensor or shotsy

    def to_dict(self) -> dict:
        return {"time": self.time.isoformat(), "kg": self.kg, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict) -> WeightEntry:
        return cls(
            time=datetime.fromisoformat(data["time"]),
            kg=float(data["kg"]),
            source=data.get("source", "manual"),
        )


@dataclass
class DayLog:
    side_effects: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    calories: float | None = None
    protein: float | None = None

    def is_empty(self) -> bool:
        return (
            not self.side_effects
            and not self.notes
            and self.calories is None
            and self.protein is None
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DayLog:
        return cls(
            side_effects={k: float(v) for k, v in (data.get("side_effects") or {}).items()},
            notes=data.get("notes") or "",
            calories=data.get("calories"),
            protein=data.get("protein"),
        )


@dataclass
class TrackerData:
    injections: list[Injection] = field(default_factory=list)
    weights: list[WeightEntry] = field(default_factory=list)
    days: dict[date, DayLog] = field(default_factory=dict)
    next_dose: float | None = None
    next_site: str | None = None
    next_due_override: datetime | None = None
    interval_days: float | None = None
    goal_weight: float | None = None
    start_weight: float | None = None
    chart_range: str = "3m"

    def sort(self) -> None:
        self.injections.sort(key=lambda i: i.time)
        self.weights.sort(key=lambda w: w.time)

    def day(self, day: date) -> DayLog:
        return self.days.get(day) or DayLog()

    def to_dict(self) -> dict:
        return {
            "injections": [i.to_dict() for i in self.injections],
            "weights": [w.to_dict() for w in self.weights],
            "days": {
                d.isoformat(): log.to_dict() for d, log in sorted(self.days.items()) if not log.is_empty()
            },
            "next_dose": self.next_dose,
            "next_site": self.next_site,
            "next_due_override": self.next_due_override.isoformat() if self.next_due_override else None,
            "interval_days": self.interval_days,
            "goal_weight": self.goal_weight,
            "start_weight": self.start_weight,
            "chart_range": self.chart_range,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> TrackerData:
        if not data:
            return cls()
        override = data.get("next_due_override")
        tracker = cls(
            injections=[Injection.from_dict(i) for i in data.get("injections", [])],
            weights=[WeightEntry.from_dict(w) for w in data.get("weights", [])],
            days={date.fromisoformat(d): DayLog.from_dict(v) for d, v in (data.get("days") or {}).items()},
            next_dose=data.get("next_dose"),
            next_site=data.get("next_site"),
            next_due_override=datetime.fromisoformat(override) if override else None,
            interval_days=data.get("interval_days"),
            goal_weight=data.get("goal_weight"),
            start_weight=data.get("start_weight"),
            chart_range=data.get("chart_range") or "3m",
        )
        tracker.sort()
        return tracker
