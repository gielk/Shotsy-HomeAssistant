"""Base entity for GLP-1 Tracker."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .tracker import GLP1Tracker


class GLP1Entity(CoordinatorEntity[GLP1Tracker]):
    """Entity that belongs to one medication."""

    _attr_has_entity_name = True

    def __init__(self, tracker: GLP1Tracker, key: str, domain: str) -> None:
        super().__init__(tracker)
        self._attr_unique_id = f"{tracker.entry.entry_id}_{key}"
        self._attr_translation_key = key
        # Fixed entity IDs, so the dashboard can rely on them in any language.
        self.entity_id = f"{domain}.{slugify(tracker.medication_name)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, tracker.entry.entry_id)},
            name=tracker.medication_name,
            manufacturer="GLP-1 Tracker",
            model=tracker.medication.capitalize(),
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def tracker(self) -> GLP1Tracker:
        return self.coordinator
