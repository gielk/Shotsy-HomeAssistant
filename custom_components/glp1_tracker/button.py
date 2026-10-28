"""Button entity: log an injection with the planned dose and site."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LogInjectionButton(entry.runtime_data)])


class LogInjectionButton(GLP1Entity, ButtonEntity):
    _attr_icon = "mdi:needle"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "injectie_registreren", "button")

    async def async_press(self) -> None:
        await self.tracker.async_log_injection()
