"""Select entities: next injection site and chart range."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .calc import next_site
from .const import CHART_RANGES
from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    tracker = entry.runtime_data
    async_add_entities([SiteSelect(tracker), ChartRangeSelect(tracker)])


class SiteSelect(GLP1Entity, SelectEntity):
    """Where the next injection goes. Defaults to the site used longest ago."""

    _attr_icon = "mdi:human-handsdown"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "volgende_prikplek", "select")

    @property
    def options(self) -> list[str]:
        return self.tracker.sites

    @property
    def current_option(self) -> str | None:
        return next_site(self.tracker.records, self.tracker.sites)

    async def async_select_option(self, option: str) -> None:
        await self.tracker.async_set(next_site=option)


class ChartRangeSelect(GLP1Entity, SelectEntity):
    """Period shown in the dashboard weight chart."""

    _attr_options = CHART_RANGES
    _attr_icon = "mdi:calendar-range"

    def __init__(self, tracker: GLP1Tracker) -> None:
        super().__init__(tracker, "grafiekperiode", "select")

    @property
    def current_option(self) -> str:
        return self.tracker.records.chart_range

    async def async_select_option(self, option: str) -> None:
        await self.tracker.async_set(chart_range=option)
