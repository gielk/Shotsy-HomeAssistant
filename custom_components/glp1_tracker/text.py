"""Text entity: notes for the agenda day."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DayNote(entry.runtime_data)])


class DayNote(GLP1Entity, TextEntity):
    _attr_icon = "mdi:note-text-outline"
    _attr_native_max = 255

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "dagnotitie", "text")

    @property
    def native_value(self) -> str:
        return self.tracker.records.day(self.tracker.day).notes

    async def async_set_value(self, value: str) -> None:
        await self.tracker.async_log_day(self.tracker.day, notes=value.strip())
