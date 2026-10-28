"""Number entities: next dose, interval, weight goals and the agenda day's log."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .calc import next_dose
from .const import SIDE_EFFECT_MAX
from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker


@dataclass(frozen=True, kw_only=True)
class GLP1NumberDescription(NumberEntityDescription):
    value_fn: Callable[[GLP1Tracker], float | None]
    set_fn: Callable[[GLP1Tracker, float], Awaitable[None]]


NUMBERS: tuple[GLP1NumberDescription, ...] = (
    GLP1NumberDescription(
        key="volgende_dosis",
        native_unit_of_measurement=UnitOfMass.MILLIGRAMS,
        native_min_value=0,
        native_max_value=50,
        native_step=0.25,
        mode=NumberMode.BOX,
        value_fn=lambda t: next_dose(t.records, t.default_dose),
        set_fn=lambda t, v: t.async_set(next_dose=v),
    ),
    GLP1NumberDescription(
        key="interval",
        native_unit_of_measurement=UnitOfTime.DAYS,
        native_min_value=1,
        native_max_value=28,
        native_step=0.5,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda t: t.interval_days,
        set_fn=lambda t, v: t.async_set(interval_days=v),
    ),
    GLP1NumberDescription(
        key="doelgewicht",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        native_min_value=0,
        native_max_value=400,
        native_step=0.1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda t: t.records.goal_weight,
        set_fn=lambda t, v: t.async_set(goal_weight=v or None),
    ),
    GLP1NumberDescription(
        key="startgewicht",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        native_min_value=0,
        native_max_value=400,
        native_step=0.1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda t: t.records.start_weight or (t.records.weights[0].kg if t.records.weights else None),
        set_fn=lambda t, v: t.async_set(start_weight=v or None),
    ),
    GLP1NumberDescription(
        key="calorieen",
        native_unit_of_measurement="kcal",
        native_min_value=0,
        native_max_value=10000,
        native_step=10,
        mode=NumberMode.BOX,
        value_fn=lambda t: t.records.day(t.day).calories,
        set_fn=lambda t, v: t.async_log_day(t.day, calories=v),
    ),
    GLP1NumberDescription(
        key="eiwitten",
        native_unit_of_measurement="g",
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda t: t.records.day(t.day).protein,
        set_fn=lambda t, v: t.async_log_day(t.day, protein=v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    tracker = entry.runtime_data
    entities: list[NumberEntity] = [GLP1Number(tracker, d) for d in NUMBERS]
    entities.extend(SideEffectNumber(tracker, name) for name in tracker.side_effects)
    async_add_entities(entities)


class GLP1Number(GLP1Entity, NumberEntity):
    entity_description: GLP1NumberDescription

    def __init__(self, tracker: GLP1Tracker, description: GLP1NumberDescription) -> None:
        super().__init__(tracker, description.key, "number")
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.tracker)

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.tracker, value)


class SideEffectNumber(GLP1Entity, NumberEntity):
    """Severity of one side effect on the agenda day (0 = none)."""

    _attr_native_min_value = 0
    _attr_native_max_value = SIDE_EFFECT_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:emoticon-sick-outline"

    def __init__(self, tracker: GLP1Tracker, side_effect: str) -> None:
        super().__init__(tracker, f"bijwerking_{slugify(side_effect)}", "number")
        self._attr_translation_key = "bijwerking"
        self._attr_translation_placeholders = {"name": side_effect}
        self._side_effect = side_effect

    @property
    def native_value(self) -> float:
        return self.tracker.records.day(self.tracker.day).side_effects.get(self._side_effect, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"side_effect": self._side_effect, "date": self.tracker.day.isoformat()}

    async def async_set_native_value(self, value: float) -> None:
        await self.tracker.async_log_day(self.tracker.day, side_effects={self._side_effect: value})
