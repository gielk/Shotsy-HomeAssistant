"""Sensors for GLP-1 Tracker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import GLP1Entity
from .tracker import GLP1ConfigEntry, GLP1Tracker

Data = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class GLP1SensorDescription(SensorEntityDescription):
    value_fn: Callable[[Data], Any]
    attrs_fn: Callable[[Data], dict[str, Any]] | None = None


def _stat(key: str) -> Callable[[Data], Any]:
    return lambda d: d["weight"]["stats"].get(key)


def _last(d: Data, attr: str) -> Any:
    return getattr(d["last"], attr) if d["last"] else None


SENSORS: tuple[GLP1SensorDescription, ...] = (
    GLP1SensorDescription(
        key="medicatieniveau",
        native_unit_of_measurement=UnitOfMass.MILLIGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d["level"]["now"],
        attrs_fn=lambda d: {
            "today_average": d["level"]["today_avg"],
            "peak_next_7_days": d["level"]["peak"],
            "peak_time": d["level"]["peak_time"],
            "half_life_days": d["level"]["half_life_days"],
            "series": d["level"]["series"],
            "planned": d["level"]["planned"],
            "daily": d["level"]["daily"],
        },
    ),
    GLP1SensorDescription(
        key="laatste_injectie",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _last(d, "time"),
        attrs_fn=lambda d: {
            "dose_mg": _last(d, "dose_mg"),
            "site": _last(d, "site"),
            "pain": _last(d, "pain"),
            "notes": _last(d, "notes"),
            "injection_id": _last(d, "id"),
            "number": d["count"],
        },
    ),
    GLP1SensorDescription(
        key="laatste_dosis",
        native_unit_of_measurement=UnitOfMass.MILLIGRAMS,
        suggested_display_precision=2,
        value_fn=lambda d: _last(d, "dose_mg"),
    ),
    GLP1SensorDescription(
        key="aantal_injecties",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["count"],
        attrs_fn=lambda d: {"injections": d["injections"]},
    ),
    GLP1SensorDescription(
        key="volgende_injectie",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d["next"]["due"],
        attrs_fn=lambda d: {
            "dose_mg": d["next"]["dose"],
            "site": d["next"]["site"],
            "suggested_site": d["next"]["suggested_site"],
            "number": d["next"]["number"],
            "interval_days": d["next"]["interval"],
        },
    ),
    GLP1SensorDescription(
        key="gewicht",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_stat("current"),
        attrs_fn=lambda d: {
            "measured_at": d["weight"]["stats"].get("measured_at"),
            "lowest": d["weight"]["stats"].get("lowest"),
            "history": d["weight"]["history"],
        },
    ),
    GLP1SensorDescription(
        key="gewicht_verandering",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_stat("change"),
        attrs_fn=lambda d: {
            "start_weight": d["weight"]["stats"].get("start"),
            "start_date": d["weight"]["stats"].get("start_date"),
        },
    ),
    GLP1SensorDescription(
        key="gewicht_verandering_procent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_stat("percent"),
    ),
    GLP1SensorDescription(
        key="bmi",
        native_unit_of_measurement="kg/m²",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_stat("bmi"),
    ),
    GLP1SensorDescription(
        key="gewicht_per_week",
        native_unit_of_measurement="kg/wk",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_stat("per_week"),
        attrs_fn=lambda d: {"dose_stats": d["weight"]["dose_stats"]},
    ),
    GLP1SensorDescription(
        key="tot_doel",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_stat("to_goal"),
        attrs_fn=lambda d: {
            "goal": d["weight"]["stats"].get("goal"),
            "to_goal_percent": d["weight"]["stats"].get("to_goal_percent"),
            "progress_percent": d["weight"]["stats"].get("progress_percent"),
            "next_milestone": d["weight"]["stats"].get("next_milestone"),
        },
    ),
    GLP1SensorDescription(
        key="dagoverzicht",
        native_unit_of_measurement=UnitOfMass.MILLIGRAMS,
        suggested_display_precision=2,
        value_fn=lambda d: d["day"]["level"],
        attrs_fn=lambda d: {
            "date": d["day"]["date"].isoformat(),
            "is_today": d["day"]["is_today"],
            "injections": d["day"]["injections"],
            "weight": d["day"]["weight"],
            "side_effects": d["day"]["side_effects"],
            "notes": d["day"]["notes"],
            "calories": d["day"]["calories"],
            "protein": d["day"]["protein"],
            "month": d["month"],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GLP1ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    tracker = entry.runtime_data
    async_add_entities(GLP1Sensor(tracker, description) for description in SENSORS)


class GLP1Sensor(GLP1Entity, SensorEntity):
    entity_description: GLP1SensorDescription
    # Large attributes for the charts; kept out of the recorder database.
    _unrecorded_attributes = frozenset({"series", "planned", "daily", "injections", "history", "month"})

    def __init__(self, tracker: GLP1Tracker, description: GLP1SensorDescription) -> None:
        super().__init__(tracker, description.key, "sensor")
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
