"""Config flow for GLP-1 Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify
import voluptuous as vol

from .const import (
    ALL_SITES,
    CONF_DEFAULT_DOSE,
    CONF_HALF_LIFE,
    CONF_HEIGHT_CM,
    CONF_HEIGHT_ENTITY,
    CONF_INJECTION_TIME,
    CONF_INTERVAL_DAYS,
    CONF_MEDICATION,
    CONF_NAME,
    CONF_SIDE_EFFECTS,
    CONF_SITES,
    CONF_TMAX_HOURS,
    CONF_WEEKDAY,
    CONF_WEIGHT_ENTITY,
    DEFAULT_HALF_LIFE,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_SIDE_EFFECTS,
    DEFAULT_SITES,
    DEFAULT_TMAX_HOURS,
    DOMAIN,
    MEDICATION_CUSTOM,
    MEDICATION_NAMES,
    MEDICATIONS,
    WEEKDAY_OPTIONS,
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _suggested(key: str, values: dict[str, Any], default: Any = None) -> vol.Optional:
    value = values.get(key, default)
    return vol.Optional(key, description={"suggested_value": value} if value is not None else None)


def _common_fields(values: dict[str, Any]) -> dict:
    return {
        _suggested(CONF_DEFAULT_DOSE, values): _number(0, 100, 0.05, "mg"),
        vol.Required(CONF_INTERVAL_DAYS, default=values.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS)): _number(
            1, 28, 0.5, "d"
        ),
        vol.Required(CONF_WEEKDAY, default=values.get(CONF_WEEKDAY, "none")): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=WEEKDAY_OPTIONS, translation_key=CONF_WEEKDAY, mode=selector.SelectSelectorMode.DROPDOWN
            )
        ),
        _suggested(CONF_INJECTION_TIME, values): selector.TimeSelector(),
        _suggested(CONF_WEIGHT_ENTITY, values): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.WEIGHT)
        ),
        _suggested(CONF_HEIGHT_ENTITY, values): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        _suggested(CONF_HEIGHT_CM, values): _number(50, 250, 1, "cm"),
    }


def _model_fields(values: dict[str, Any]) -> dict:
    return {
        vol.Required(CONF_HALF_LIFE, default=values.get(CONF_HALF_LIFE, DEFAULT_HALF_LIFE)): _number(0.5, 30, 0.1, "d"),
        vol.Required(CONF_TMAX_HOURS, default=values.get(CONF_TMAX_HOURS, DEFAULT_TMAX_HOURS)): _number(1, 240, 1, "h"),
    }


class GLP1TrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GLP1TrackerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            medication = user_input[CONF_MEDICATION]
            name = (user_input.get(CONF_NAME) or MEDICATION_NAMES[medication]).strip()
            await self.async_set_unique_id(slugify(name))
            self._abort_if_unique_id_configured()
            self._data = {**user_input, CONF_NAME: name}
            if medication == MEDICATION_CUSTOM:
                return await self.async_step_model()
            return self.async_create_entry(title=name, data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_MEDICATION, default="retatrutide"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=MEDICATIONS, translation_key=CONF_MEDICATION)
                ),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                **_common_fields({}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_model(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=self._data[CONF_NAME], data={**self._data, **user_input})
        return self.async_show_form(step_id="model", data_schema=vol.Schema(_model_fields({})))


class GLP1TrackerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            # Fields left empty are removed, so they fall back to their defaults.
            options = dict(user_input)
            for key in (CONF_DEFAULT_DOSE, CONF_INJECTION_TIME, CONF_WEIGHT_ENTITY, CONF_HEIGHT_ENTITY, CONF_HEIGHT_CM):
                options.setdefault(key, None)
            return self.async_create_entry(data=options)

        sites = current.get(CONF_SITES) or DEFAULT_SITES
        side_effects = current.get(CONF_SIDE_EFFECTS)
        if side_effects is None:
            side_effects = DEFAULT_SIDE_EFFECTS
        fields = {
            **_common_fields(current),
            vol.Required(CONF_SITES, default=sites): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(dict.fromkeys([*ALL_SITES, *sites])), multiple=True, custom_value=True
                )
            ),
            vol.Optional(CONF_SIDE_EFFECTS, default=side_effects): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(dict.fromkeys([*DEFAULT_SIDE_EFFECTS, *side_effects])),
                    multiple=True,
                    custom_value=True,
                )
            ),
        }
        if current.get(CONF_MEDICATION) == MEDICATION_CUSTOM:
            fields.update(_model_fields(current))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
