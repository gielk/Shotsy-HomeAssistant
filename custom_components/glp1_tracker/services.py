"""Actions (services) for GLP-1 Tracker."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    ATTR_CALORIES,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CSV_TEXT,
    ATTR_DATE,
    ATTR_DOSE,
    ATTR_FILE_PATH,
    ATTR_INJECTION_ID,
    ATTR_NOTES,
    ATTR_PAIN,
    ATTR_PROTEIN,
    ATTR_REPLACE,
    ATTR_SIDE_EFFECTS,
    ATTR_SITE,
    ATTR_TIME,
    ATTR_WEIGHT,
    DOMAIN,
    SERVICE_DELETE_INJECTION,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_SHOTSY,
    SERVICE_LOG_DAY,
    SERVICE_LOG_INJECTION,
    SERVICE_LOG_WEIGHT,
    SERVICE_UPDATE_INJECTION,
)
from .shotsy_csv import parse_shotsy_csv
from .tracker import GLP1Tracker

ENTRY = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
DOSE = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
PAIN = vol.All(vol.Coerce(float), vol.Range(min=0, max=10))
INJECTION_FIELDS = {
    vol.Optional(ATTR_DOSE): DOSE,
    vol.Optional(ATTR_TIME): cv.datetime,
    vol.Optional(ATTR_SITE): cv.string,
    vol.Optional(ATTR_PAIN): PAIN,
    vol.Optional(ATTR_NOTES): cv.string,
}

LOG_INJECTION_SCHEMA = vol.Schema({**ENTRY, **INJECTION_FIELDS})
UPDATE_INJECTION_SCHEMA = vol.Schema({**ENTRY, vol.Required(ATTR_INJECTION_ID): cv.string, **INJECTION_FIELDS})
DELETE_INJECTION_SCHEMA = vol.Schema({**ENTRY, vol.Required(ATTR_INJECTION_ID): cv.string})
LOG_DAY_SCHEMA = vol.Schema(
    {
        **ENTRY,
        vol.Optional(ATTR_DATE): cv.date,
        vol.Optional(ATTR_SIDE_EFFECTS): {cv.string: vol.All(vol.Coerce(float), vol.Range(min=0, max=10))},
        vol.Optional(ATTR_NOTES): cv.string,
        vol.Optional(ATTR_CALORIES): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(ATTR_PROTEIN): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)
LOG_WEIGHT_SCHEMA = vol.Schema(
    {
        **ENTRY,
        vol.Required(ATTR_WEIGHT): vol.All(vol.Coerce(float), vol.Range(min=1, max=500)),
        vol.Optional(ATTR_TIME): cv.datetime,
    }
)
IMPORT_SCHEMA = vol.Schema(
    {
        **ENTRY,
        vol.Exclusive(ATTR_FILE_PATH, "source"): cv.string,
        vol.Exclusive(ATTR_CSV_TEXT, "source"): cv.string,
        vol.Optional(ATTR_REPLACE, default=True): cv.boolean,
    }
)
EXPORT_SCHEMA = vol.Schema(ENTRY)


def _local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_util.get_default_time_zone())
    return value


def _tracker(hass: HomeAssistant, call: ServiceCall) -> GLP1Tracker:
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
    elif len(entries) != 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_required")
    return entries[0].runtime_data


def _injection(tracker: GLP1Tracker, injection_id: str):
    injection = tracker.find(injection_id)
    if injection is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="injection_not_found",
            translation_placeholders={"injection_id": injection_id},
        )
    return injection


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def log_injection(call: ServiceCall) -> ServiceResponse:
        tracker = _tracker(hass, call)
        try:
            injection = await tracker.async_log_injection(
                dose_mg=call.data.get(ATTR_DOSE),
                when=_local(call.data.get(ATTR_TIME)),
                site=call.data.get(ATTR_SITE),
                pain=call.data.get(ATTR_PAIN),
                notes=call.data.get(ATTR_NOTES, ""),
            )
        except ValueError as err:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="dose_required") from err
        return {"injection_id": injection.id, "number": len(tracker.records.injections)}

    async def update_injection(call: ServiceCall) -> None:
        tracker = _tracker(hass, call)
        injection = _injection(tracker, call.data[ATTR_INJECTION_ID])
        await tracker.async_update_injection(
            injection,
            dose_mg=call.data.get(ATTR_DOSE),
            time=_local(call.data.get(ATTR_TIME)),
            site=call.data.get(ATTR_SITE),
            pain=call.data.get(ATTR_PAIN),
            notes=call.data.get(ATTR_NOTES),
        )

    async def delete_injection(call: ServiceCall) -> None:
        tracker = _tracker(hass, call)
        await tracker.async_delete_injection(_injection(tracker, call.data[ATTR_INJECTION_ID]))

    async def log_day(call: ServiceCall) -> None:
        tracker = _tracker(hass, call)
        day: date = call.data.get(ATTR_DATE) or tracker.day
        await tracker.async_log_day(
            day,
            side_effects=call.data.get(ATTR_SIDE_EFFECTS),
            notes=call.data.get(ATTR_NOTES),
            calories=call.data.get(ATTR_CALORIES),
            protein=call.data.get(ATTR_PROTEIN),
        )

    async def log_weight(call: ServiceCall) -> None:
        tracker = _tracker(hass, call)
        await tracker.async_log_weight(call.data[ATTR_WEIGHT], _local(call.data.get(ATTR_TIME)))

    async def import_shotsy(call: ServiceCall) -> ServiceResponse:
        tracker = _tracker(hass, call)
        text = call.data.get(ATTR_CSV_TEXT)
        if not text and (file_path := call.data.get(ATTR_FILE_PATH)):
            path = Path(hass.config.path(file_path))
            config_dir = Path(hass.config.config_dir).resolve()
            resolved = path.resolve()
            if config_dir not in resolved.parents and not hass.config.is_allowed_path(str(resolved)):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="path_not_allowed",
                    translation_placeholders={"path": str(resolved)},
                )
            try:
                text = await hass.async_add_executor_job(resolved.read_text, "utf-8")
            except OSError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="file_unreadable",
                    translation_placeholders={"path": str(resolved), "error": str(err)},
                ) from err
        if not text:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="csv_required")

        export = parse_shotsy_csv(text, dt_util.get_default_time_zone(), tracker.medication_name)
        if not export.injections and not export.weights:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="csv_empty")
        counts = await tracker.async_import(export, call.data[ATTR_REPLACE])
        return {
            **counts,
            "medications": sorted(export.medications),
            "side_effects": export.side_effect_names,
            "skipped": export.skipped,
        }

    async def export_data(call: ServiceCall) -> ServiceResponse:
        return _tracker(hass, call).export()

    register: list[tuple[str, Any, vol.Schema, SupportsResponse]] = [
        (SERVICE_LOG_INJECTION, log_injection, LOG_INJECTION_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_UPDATE_INJECTION, update_injection, UPDATE_INJECTION_SCHEMA, SupportsResponse.NONE),
        (SERVICE_DELETE_INJECTION, delete_injection, DELETE_INJECTION_SCHEMA, SupportsResponse.NONE),
        (SERVICE_LOG_DAY, log_day, LOG_DAY_SCHEMA, SupportsResponse.NONE),
        (SERVICE_LOG_WEIGHT, log_weight, LOG_WEIGHT_SCHEMA, SupportsResponse.NONE),
        (SERVICE_IMPORT_SHOTSY, import_shotsy, IMPORT_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_EXPORT_DATA, export_data, EXPORT_SCHEMA, SupportsResponse.ONLY),
    ]
    for name, handler, schema, response in register:
        hass.services.async_register(DOMAIN, name, handler, schema=schema, supports_response=response)
