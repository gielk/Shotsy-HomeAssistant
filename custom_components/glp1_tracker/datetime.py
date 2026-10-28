"""Datetime entity: when the next injection is planned."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NextInjectionDateTime(entry.runtime_data)])


class NextInjectionDateTime(GLP1Entity, DateTimeEntity):
    """Last injection plus the interval, unless set by hand."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "volgende_injectie", "datetime")

    @property
    def native_value(self) -> datetime | None:
        return self.tracker.next_due()

    async def async_set_value(self, value: datetime) -> None:
        await self.tracker.async_set(next_due_override=value)
