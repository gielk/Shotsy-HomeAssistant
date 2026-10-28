"""Date entity: the day shown in the agenda."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AgendaDay(entry.runtime_data)])


class AgendaDay(GLP1Entity, DateEntity):
    """Side effects, notes, calories and protein entities follow this day."""

    _attr_icon = "mdi:calendar-today"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "agendadag", "date")

    @property
    def native_value(self) -> date:
        return self.tracker.day

    async def async_set_value(self, value: date) -> None:
        await self.tracker.async_select_day(value)
