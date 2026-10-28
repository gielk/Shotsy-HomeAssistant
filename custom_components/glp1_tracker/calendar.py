"""Calendar entity: injections, the planned injection and daily notes."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .calc import next_dose, next_site
from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker

INJECTION_DURATION = timedelta(minutes=15)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([InjectionCalendar(entry.runtime_data)])


def _fmt(mg: float) -> str:
    return f"{mg:g}"


class InjectionCalendar(GLP1Entity, CalendarEntity):
    _attr_icon = "mdi:calendar-heart"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "agenda", "calendar")

    def _events(self) -> list[CalendarEvent]:
        tracker, records = self.tracker, self.tracker.records
        events: list[CalendarEvent] = []
        for n, inj in enumerate(records.injections, start=1):
            details = [f"Injectie {n}"]
            if inj.site:
                details.append(inj.site)
            if inj.pain:
                details.append(f"Pijn {inj.pain:g}/10")
            if inj.notes:
                details.append(inj.notes)
            events.append(
                CalendarEvent(
                    start=inj.time,
                    end=inj.time + INJECTION_DURATION,
                    summary=f"{tracker.medication_name} {_fmt(inj.dose_mg)} mg",
                    description="\n".join(details),
                    uid=inj.id,
                )
            )
        if due := tracker.next_due():
            dose = next_dose(records, tracker.default_dose)
            site = next_site(records, tracker.sites)
            events.append(
                CalendarEvent(
                    start=due,
                    end=due + INJECTION_DURATION,
                    summary=f"Gepland: {tracker.medication_name} {_fmt(dose)} mg"
                    if dose
                    else f"Gepland: {tracker.medication_name}",
                    description=f"Injectie {len(records.injections) + 1}" + (f"\n{site}" if site else ""),
                    uid="planned",
                )
            )
        for day, log in records.days.items():
            if log.is_empty():
                continue
            lines = [f"{name}: {value:g}/10" for name, value in log.side_effects.items()]
            if log.calories:
                lines.append(f"Calorieën: {log.calories:g} kcal")
            if log.protein:
                lines.append(f"Eiwitten: {log.protein:g} g")
            if log.notes:
                lines.append(log.notes)
            events.append(
                CalendarEvent(
                    start=day,
                    end=day + timedelta(days=1),
                    summary="Bijwerkingen" if log.side_effects else "Notitie",
                    description="\n".join(lines),
                    uid=f"day-{day.isoformat()}",
                )
            )
        return events

    @staticmethod
    def _bounds(event: CalendarEvent) -> tuple[datetime, datetime]:
        start, end = event.start, event.end
        if not isinstance(start, datetime):
            start = dt_util.start_of_local_day(start)
            end = dt_util.start_of_local_day(end)
        return start, end

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next injection event."""
        now = dt_util.now()
        upcoming = [e for e in self._events() if isinstance(e.start, datetime) and self._bounds(e)[1] > now]
        return min(upcoming, key=lambda e: e.start, default=None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        out = []
        for event in self._events():
            start, end = self._bounds(event)
            if start < end_date and end > start_date:
                out.append(event)
        return sorted(out, key=lambda e: self._bounds(e)[0])
