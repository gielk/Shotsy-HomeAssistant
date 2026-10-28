"""Tests for the integration running in Home Assistant."""

from datetime import datetime, timedelta

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.glp1_tracker.const import DOMAIN


@pytest.fixture
async def entry(hass: HomeAssistant, enable_custom_integrations, freezer) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to("2025-01-14 12:00:00+01:00")
    hass.states.async_set("sensor.phone_weight", "118.0", {"unit_of_measurement": "kg", "device_class": "weight"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Retatrutide",
        unique_id="retatrutide",
        data={
            "medication": "retatrutide",
            "name": "Retatrutide",
            "interval_days": 7,
            "height_cm": 203,
            "weight_entity": "sensor.phone_weight",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _import(hass: HomeAssistant, sample_csv: str) -> dict:
    response = await hass.services.async_call(
        DOMAIN, "import_shotsy_csv", {"csv_text": sample_csv}, blocking=True, return_response=True
    )
    await hass.async_block_till_done()
    return response


async def test_config_flow(hass: HomeAssistant, enable_custom_integrations) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"medication": "custom", "name": "Mijn medicijn", "interval_days": 7}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "model"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"half_life_days": 5, "tmax_hours": 24})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mijn medicijn"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mijn_medicijn_medicatieniveau").state == "0.0"

    # The same name can't be added twice.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"medication": "custom", "name": "Mijn medicijn", "interval_days": 7}
    )
    assert result["type"] is FlowResultType.ABORT


async def test_entities_and_import(hass: HomeAssistant, entry, sample_csv) -> None:
    for entity_id in (
        "sensor.retatrutide_medicatieniveau",
        "sensor.retatrutide_volgende_injectie",
        "sensor.retatrutide_gewicht",
        "number.retatrutide_volgende_dosis",
        "number.retatrutide_bijwerking_misselijkheid",
        "select.retatrutide_volgende_prikplek",
        "select.retatrutide_grafiekperiode",
        "datetime.retatrutide_volgende_injectie",
        "date.retatrutide_agendadag",
        "text.retatrutide_dagnotitie",
        "button.retatrutide_injectie_registreren",
        "calendar.retatrutide_agenda",
    ):
        assert hass.states.get(entity_id), entity_id

    # The weight sensor value was stored at startup.
    assert hass.states.get("sensor.retatrutide_gewicht").state == "118.0"

    response = await _import(hass, sample_csv)
    assert response["injections"] == 3
    assert response["weights"] == 4

    assert hass.states.get("sensor.retatrutide_aantal_injecties").state == "3"
    assert hass.states.get("sensor.retatrutide_laatste_dosis").state == "0.5"
    level = hass.states.get("sensor.retatrutide_medicatieniveau")
    assert 1.0 < float(level.state) < 4.0
    assert level.attributes["series"] and level.attributes["daily"]
    # With the planned injection on 20 January the forecast rises again.
    planned = dict(level.attributes["planned"])
    series = dict(level.attributes["series"])
    after_due = int(dt_util.parse_datetime("2025-01-22T00:00:00+00:00").timestamp() * 1000)
    assert planned[after_due] > series[after_due]
    due = dt_util.parse_datetime(hass.states.get("sensor.retatrutide_volgende_injectie").state)
    assert due == dt_util.parse_datetime("2025-01-20T20:30:00+00:00")
    # Sites never used come first, in the configured order.
    assert hass.states.get("select.retatrutide_volgende_prikplek").state == "Buik - Midden Boven"

    weight = hass.states.get("sensor.retatrutide_gewicht")
    # Imported weights plus the sensor value of today.
    assert weight.state == "118.0"
    assert [kg for _, kg in weight.attributes["history"]] == [120.5, 119.8, 119.1, 118.4, 118.0]
    assert hass.states.get("sensor.retatrutide_gewicht_verandering").state == "-2.5"
    assert hass.states.get("sensor.retatrutide_bmi").state == "28.6"

    # "Food Noise" from the CSV matches the default side effect.
    assert hass.states.get("number.retatrutide_bijwerking_food_noise")


async def test_log_and_delete_injection(hass: HomeAssistant, entry, sample_csv, freezer) -> None:
    await _import(hass, sample_csv)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.retatrutide_volgende_dosis", "value": 3}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.retatrutide_injectie_registreren"}, blocking=True
    )
    await hass.async_block_till_done()
    last = hass.states.get("sensor.retatrutide_laatste_injectie")
    assert last.attributes["dose_mg"] == 3
    assert last.attributes["site"] == "Buik - Midden Boven"
    assert hass.states.get("sensor.retatrutide_aantal_injecties").state == "4"
    # Next site moves on, the dose stays.
    assert hass.states.get("select.retatrutide_volgende_prikplek").state == "Buik - Rechts Boven"
    assert hass.states.get("number.retatrutide_volgende_dosis").state == "3.0"

    response = await hass.services.async_call(
        DOMAIN,
        "log_injection",
        {"dose_mg": 4, "time": "2025-01-14 08:00:00", "site": "Dij - Rechts", "pain": 2},
        blocking=True,
        return_response=True,
    )
    assert response["number"] == 5
    await hass.services.async_call(
        DOMAIN, "update_injection", {"injection_id": response["injection_id"], "notes": "test"}, blocking=True
    )
    injections = hass.states.get("sensor.retatrutide_aantal_injecties").attributes["injections"]
    # Newest first; the 08:00 injection comes before the one logged at 12:00.
    assert [i["dose"] for i in injections[:2]] == [3, 4]
    assert injections[1]["notes"] == "test"

    await hass.services.async_call(DOMAIN, "delete_injection", {"injection_id": "last"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "delete_injection", {"injection_id": response["injection_id"]}, blocking=True
    )
    assert hass.states.get("sensor.retatrutide_aantal_injecties").state == "3"


async def test_agenda_day(hass: HomeAssistant, entry, sample_csv) -> None:
    await _import(hass, sample_csv)
    await hass.services.async_call(
        "date", "set_value", {"entity_id": "date.retatrutide_agendadag", "date": "2025-01-07"}, blocking=True
    )
    assert hass.states.get("number.retatrutide_bijwerking_misselijkheid").state == "3.0"
    assert hass.states.get("text.retatrutide_dagnotitie").state == "Bit queasy"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.retatrutide_bijwerking_misselijkheid", "value": 5},
        blocking=True,
    )
    await hass.services.async_call(
        "text", "set_value", {"entity_id": "text.retatrutide_dagnotitie", "value": "Moe"}, blocking=True
    )
    day = hass.states.get("sensor.retatrutide_dagoverzicht")
    assert day.attributes["date"] == "2025-01-07"
    assert day.attributes["side_effects"] == {"Misselijkheid": 5.0}
    assert day.attributes["notes"] == "Moe"
    assert float(day.state) > 0
    month = day.attributes["month"]
    assert len(month) == 31
    assert month[5]["dose"] == 2.0 and month[6]["log"] is True

    await hass.services.async_call(
        DOMAIN, "log_day", {"date": "2025-01-10", "side_effects": {"Vermoeidheid": 2}, "calories": 1800}, blocking=True
    )
    await hass.services.async_call(
        "date", "set_value", {"entity_id": "date.retatrutide_agendadag", "date": "2025-01-10"}, blocking=True
    )
    assert hass.states.get("number.retatrutide_bijwerking_vermoeidheid").state == "2.0"
    assert hass.states.get("number.retatrutide_calorieen").state == "1800.0"

    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.retatrutide_agenda",
            "start_date_time": "2025-01-01 00:00:00",
            "duration": {"days": 30},
        },
        blocking=True,
        return_response=True,
    )
    summaries = [e["summary"] for e in events["calendar.retatrutide_agenda"]["events"]]
    assert "Retatrutide 2 mg" in summaries
    assert "Gepland: Retatrutide 0.5 mg" in summaries
    assert summaries.count("Bijwerkingen") == 3


async def test_schedule_override_and_persistence(hass: HomeAssistant, entry, sample_csv) -> None:
    await _import(hass, sample_csv)
    await hass.services.async_call(
        "datetime",
        "set_value",
        {"entity_id": "datetime.retatrutide_volgende_injectie", "datetime": "2025-01-19 11:00:00"},
        blocking=True,
    )
    due = dt_util.parse_datetime(hass.states.get("sensor.retatrutide_volgende_injectie").state)
    assert due == datetime(2025, 1, 19, 10, 0, tzinfo=dt_util.UTC)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.retatrutide_doelgewicht", "value": 100}, blocking=True
    )
    assert hass.states.get("sensor.retatrutide_tot_doel").state == "18.0"

    # Data survives a reload.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.retatrutide_aantal_injecties").state == "3"
    due = dt_util.parse_datetime(hass.states.get("sensor.retatrutide_volgende_injectie").state)
    assert due == datetime(2025, 1, 19, 10, 0, tzinfo=dt_util.UTC)
    assert hass.states.get("sensor.retatrutide_tot_doel").state == "18.0"

    export = await hass.services.async_call(DOMAIN, "export_data", {}, blocking=True, return_response=True)
    assert len(export["injections"]) == 3
    assert export["goal_weight"] == 100


async def test_options_add_side_effect(hass: HomeAssistant, entry) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "interval_days": 6,
            "height_cm": 203,
            "sites": ["Buik - Links Boven", "Buik - Rechts Boven"],
            "side_effects": ["Misselijkheid", "Hoofdpijn"],
            "weekday": "5",
            "injection_time": "11:00:00",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("number.retatrutide_bijwerking_hoofdpijn")
    assert hass.states.get("number.retatrutide_interval").state == "6.0"
    assert hass.states.get("select.retatrutide_volgende_prikplek").attributes["options"] == [
        "Buik - Links Boven",
        "Buik - Rechts Boven",
    ]
    # The weight sensor was cleared in the options.
    assert entry.runtime_data.weight_entity is None
    assert entry.runtime_data.weekday == 5


async def test_level_updates_over_time(hass: HomeAssistant, entry, sample_csv, freezer) -> None:
    await _import(hass, sample_csv)
    before = float(hass.states.get("sensor.retatrutide_medicatieniveau").state)
    freezer.tick(timedelta(days=3))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    after = float(hass.states.get("sensor.retatrutide_medicatieniveau").state)
    assert after < before
