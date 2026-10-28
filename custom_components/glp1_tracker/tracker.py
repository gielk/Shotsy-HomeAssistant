"""Runtime object for one medication: stored data plus calculated values."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfLength, UnitOfMass
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, MassConverter

from .calc import (
    daily_levels,
    dose_stats,
    due_after,
    month_overview,
    ms,
    next_dose,
    next_due,
    next_site,
    suggest_site,
    weight_stats,
)
from .const import (
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
    MEDICATION_NAMES,
    STORAGE_VERSION,
    UPDATE_INTERVAL_MINUTES,
)
from .models import DayLog, Injection, TrackerData, WeightEntry
from .pk import PRESET_MODELS, BatemanModel, LevelCalculator, Model
from .shotsy_csv import ShotsyExport

_LOGGER = logging.getLogger(__name__)

# Chart window around now for the level graph.
SERIES_PAST_DAYS = 35
SERIES_FUTURE_DAYS = 21
SERIES_STEP_HOURS = 3

type GLP1ConfigEntry = ConfigEntry[GLP1Tracker]


class GLP1Tracker(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the injection log for one medication and computes the derived values."""

    def __init__(self, hass: HomeAssistant, entry: GLP1ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )
        self.entry = entry
        self._storage: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.records = TrackerData()
        self.selected_day: date | None = None
        self._calc = LevelCalculator(self.model, [])
        self._daily_cache: dict[date, float] = {}

    # ----- configuration -------------------------------------------------

    def _conf(self, key: str, default: Any = None) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def medication(self) -> str:
        return self._conf(CONF_MEDICATION, "retatrutide")

    @property
    def medication_name(self) -> str:
        return self._conf(CONF_NAME) or MEDICATION_NAMES.get(self.medication, "Medicatie")

    @property
    def model(self) -> Model:
        if preset := PRESET_MODELS.get(self.medication):
            return preset
        return BatemanModel(
            half_life=float(self._conf(CONF_HALF_LIFE, DEFAULT_HALF_LIFE)),
            tmax=float(self._conf(CONF_TMAX_HOURS, DEFAULT_TMAX_HOURS)) / 24,
        )

    @property
    def sites(self) -> list[str]:
        return list(self._conf(CONF_SITES) or DEFAULT_SITES)

    @property
    def side_effects(self) -> list[str]:
        value = self._conf(CONF_SIDE_EFFECTS)
        if value is None:
            return list(DEFAULT_SIDE_EFFECTS)
        if isinstance(value, str):
            value = value.split(",")
        return [v.strip() for v in value if v.strip()]

    @property
    def interval_days(self) -> float:
        if self.records.interval_days:
            return self.records.interval_days
        return float(self._conf(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS))

    @property
    def weekday(self) -> int | None:
        value = self._conf(CONF_WEEKDAY)
        return int(value) if value not in (None, "", "none") else None

    @property
    def injection_time(self) -> time | None:
        value = self._conf(CONF_INJECTION_TIME)
        return time.fromisoformat(value) if value else None

    def next_due(self) -> datetime | None:
        return next_due(
            self.records,
            self.interval_days,
            self.weekday,
            self.injection_time,
            dt_util.get_default_time_zone(),
        )

    @property
    def default_dose(self) -> float | None:
        value = self._conf(CONF_DEFAULT_DOSE)
        return float(value) if value else None

    @property
    def weight_entity(self) -> str | None:
        return self._conf(CONF_WEIGHT_ENTITY) or None

    @property
    def height_cm(self) -> float | None:
        if entity_id := self._conf(CONF_HEIGHT_ENTITY):
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                try:
                    value = float(state.state)
                except ValueError:
                    value = None
                if value:
                    unit = state.attributes.get("unit_of_measurement") or UnitOfLength.CENTIMETERS
                    try:
                        return DistanceConverter.convert(value, unit, UnitOfLength.CENTIMETERS)
                    except Exception:  # noqa: BLE001 - unknown unit, use as-is
                        return value
        value = self._conf(CONF_HEIGHT_CM)
        return float(value) if value else None

    @property
    def day(self) -> date:
        return self.selected_day or dt_util.now().date()

    # ----- lifecycle -----------------------------------------------------

    async def async_load(self) -> None:
        self.records = TrackerData.from_dict(await self._storage.async_load())
        self._rebuild_calc()
        if self.weight_entity:
            self.entry.async_on_unload(
                async_track_state_change_event(self.hass, [self.weight_entity], self._weight_changed)
            )
            if self._record_weight_state(self.hass.states.get(self.weight_entity)):
                self._save()

    @callback
    def _weight_changed(self, event: Event[EventStateChangedData]) -> None:
        if self._record_weight_state(event.data["new_state"]):
            self._save()
            self.hass.async_create_task(self.async_request_refresh())

    def _record_weight_state(self, state) -> bool:
        """Store the sensor's weight if it differs from the last stored weight."""
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return False
        try:
            kg = float(state.state)
        except ValueError:
            return False
        unit = state.attributes.get("unit_of_measurement") or UnitOfMass.KILOGRAMS
        if unit != UnitOfMass.KILOGRAMS:
            try:
                kg = MassConverter.convert(kg, unit, UnitOfMass.KILOGRAMS)
            except Exception:  # noqa: BLE001
                return False
        if kg <= 0:
            return False
        weights = self.records.weights
        if weights and abs(weights[-1].kg - kg) < 0.01:
            return False
        weights.append(WeightEntry(time=dt_util.now(), kg=round(kg, 2), source="sensor"))
        return True

    def _rebuild_calc(self) -> None:
        self._calc = LevelCalculator(self.model, [(i.time.timestamp(), i.dose_mg) for i in self.records.injections])
        # A new dict, so a calculation still running keeps its own cache.
        self._daily_cache = {}

    def _save(self) -> None:
        self._storage.async_delay_save(self.records.to_dict, 1)

    async def _async_changed(self, injections: bool = False) -> None:
        self.records.sort()
        if injections:
            self._rebuild_calc()
        self._save()
        await self.async_refresh()

    async def async_flush(self) -> None:
        await self._storage.async_save(self.records.to_dict())

    # ----- calculations --------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        tz = dt_util.get_default_time_zone()
        context = {
            "now": dt_util.now(),
            "tz": tz,
            "day": self.day,
            "height_cm": self.height_cm,
            "interval": self.interval_days,
            "weekday": self.weekday,
            "at": self.injection_time,
            "model": self.model,
            "sites": self.sites,
            "default_dose": self.default_dose,
            # Copies, so changes made meanwhile in the event loop don't interfere.
            "data": TrackerData(
                injections=list(self.records.injections),
                weights=list(self.records.weights),
                days=dict(self.records.days),
                next_dose=self.records.next_dose,
                next_site=self.records.next_site,
                next_due_override=self.records.next_due_override,
                start_weight=self.records.start_weight,
                goal_weight=self.records.goal_weight,
            ),
            "calc": self._calc,
            "cache": self._daily_cache,
        }
        return await self.hass.async_add_executor_job(self._compute, context)

    def _compute(self, ctx: dict[str, Any]) -> dict[str, Any]:
        data, calc = ctx["data"], ctx["calc"]
        now: datetime = ctx["now"]
        tz = ctx["tz"]
        today = now.astimezone(tz).date()
        now_ts = now.timestamp()

        # Level graph: past weeks plus forecast, on a 3-hour grid.
        step = SERIES_STEP_HOURS * 3600
        start = (now_ts - SERIES_PAST_DAYS * 86400) // step * step
        end = now_ts + SERIES_FUTURE_DAYS * 86400
        series = calc.series(start, end, step)

        # The same forecast if the planned injections are taken on time.
        due = next_due(data, ctx["interval"], ctx["weekday"], ctx["at"], tz)
        dose = next_dose(data, ctx["default_dose"])
        planned_doses: list[tuple[float, float]] = []
        at = due
        while at and dose and at.timestamp() <= end:
            planned_doses.append((at.timestamp(), dose))
            at = due_after(at, ctx["interval"], ctx["weekday"], ctx["at"], tz)
        planned_calc = LevelCalculator(
            ctx["model"], [(i.time.timestamp(), i.dose_mg) for i in data.injections] + planned_doses
        )
        planned = planned_calc.series(start + (now_ts - start) // step * step, end, step)
        upcoming = [p for p in planned if now_ts < p[0] <= now_ts + 7 * 86400]
        peak = max(upcoming, key=lambda p: p[1]) if upcoming else None

        first_day = data.injections[0].time.astimezone(tz).date() if data.injections else today
        last_day = max(today + timedelta(days=SERIES_FUTURE_DAYS), ctx["day"])
        levels = daily_levels(calc, min(first_day, ctx["day"]), last_day, tz, ctx["cache"], today)

        injections = data.injections
        last = injections[-1] if injections else None
        weights = data.weights
        stats = weight_stats(weights, data.start_weight, data.goal_weight, ctx["height_cm"])

        selected = ctx["day"]
        log = data.day(selected)
        day_weights = [w for w in weights if w.time.astimezone(tz).date() == selected]

        return {
            "level": {
                "now": round(calc.at(now_ts), 2),
                "today_avg": round(levels.get(today, 0.0), 2),
                "peak": round(peak[1], 2) if peak else None,
                "peak_time": dt_util.utc_from_timestamp(peak[0]) if peak else None,
                "series": [[int(t * 1000), round(v, 2)] for t, v in series],
                "planned": [[int(t * 1000), round(v, 2)] for t, v in planned],
                "daily": [
                    [ms(datetime.combine(d, datetime.min.time(), tz)), round(v, 2)]
                    for d, v in levels.items()
                    if d <= today
                ],
                "half_life_days": self.model.half_life_days,
            },
            "count": len(injections),
            "last": last,
            "injections": [
                {
                    "id": inj.id,
                    "n": n,
                    "t": ms(inj.time),
                    "time": inj.time.isoformat(),
                    "dose": inj.dose_mg,
                    "site": inj.site,
                    "pain": inj.pain,
                    "notes": inj.notes,
                }
                for n, inj in reversed(list(enumerate(injections, start=1)))
            ],
            "next": {
                "due": due,
                "dose": dose,
                "site": next_site(data, ctx["sites"]),
                "suggested_site": suggest_site(injections, ctx["sites"]),
                "number": len(injections) + 1,
                "interval": ctx["interval"],
            },
            "weight": {
                "stats": stats,
                "history": [[ms(w.time), w.kg] for w in weights],
                "dose_stats": dose_stats(injections, weights),
            },
            "day": {
                "date": selected,
                "is_today": selected == today,
                "level": round(levels[selected], 2) if selected in levels else None,
                "injections": [
                    {"time": i.time.isoformat(), "dose": i.dose_mg, "site": i.site, "pain": i.pain, "notes": i.notes}
                    for i in injections
                    if i.time.astimezone(tz).date() == selected
                ],
                "weight": day_weights[-1].kg if day_weights else None,
                "side_effects": dict(log.side_effects),
                "notes": log.notes,
                "calories": log.calories,
                "protein": log.protein,
            },
            "month": month_overview(data, selected, tz, levels),
        }

    # ----- mutations -----------------------------------------------------

    def find(self, injection_id: str) -> Injection | None:
        if injection_id == "last":
            return self.records.injections[-1] if self.records.injections else None
        return next((i for i in self.records.injections if i.id == injection_id), None)

    async def async_log_injection(
        self,
        dose_mg: float | None = None,
        when: datetime | None = None,
        site: str | None = None,
        pain: float | None = None,
        notes: str = "",
    ) -> Injection:
        data = self.records
        dose = dose_mg if dose_mg is not None else next_dose(data, self.default_dose)
        if dose is None:
            raise ValueError("no dose")
        injection = Injection(
            time=when or dt_util.now(),
            dose_mg=float(dose),
            site=site if site is not None else next_site(data, self.sites),
            pain=pain,
            notes=notes or "",
        )
        data.injections.append(injection)
        # The schedule continues from this injection, with the same dose.
        data.next_due_override = None
        data.next_site = None
        data.next_dose = None
        await self._async_changed(injections=True)
        return injection

    async def async_update_injection(self, injection: Injection, **changes: Any) -> None:
        for key, value in changes.items():
            if value is not None:
                setattr(injection, key, value)
        await self._async_changed(injections=True)

    async def async_delete_injection(self, injection: Injection) -> None:
        self.records.injections.remove(injection)
        await self._async_changed(injections=True)

    async def async_set(self, **values: Any) -> None:
        """Set schedule or goal fields on the stored data."""
        for key, value in values.items():
            setattr(self.records, key, value)
        await self._async_changed()

    async def async_select_day(self, day: date | None) -> None:
        self.selected_day = None if day == dt_util.now().date() else day
        await self.async_refresh()

    async def async_log_day(
        self,
        day: date,
        side_effects: dict[str, float] | None = None,
        notes: str | None = None,
        calories: float | None = None,
        protein: float | None = None,
    ) -> None:
        log = self.records.days.setdefault(day, DayLog())
        for name, value in (side_effects or {}).items():
            if value:
                log.side_effects[name] = float(value)
            else:
                log.side_effects.pop(name, None)
        if notes is not None:
            log.notes = notes
        if calories is not None:
            log.calories = calories or None
        if protein is not None:
            log.protein = protein or None
        if log.is_empty():
            self.records.days.pop(day, None)
        await self._async_changed()

    async def async_log_weight(self, kg: float, when: datetime | None = None) -> None:
        self.records.weights.append(WeightEntry(time=when or dt_util.now(), kg=round(kg, 2), source="manual"))
        await self._async_changed()

    async def async_import(self, export: ShotsyExport, replace: bool) -> dict[str, int]:
        data = self.records
        # Use the configured spelling of side effects that only differ in case.
        known = {name.lower(): name for name in self.side_effects}
        for log in export.days.values():
            log.side_effects = {known.get(k.lower(), k): v for k, v in log.side_effects.items()}
        if replace:
            data.injections = list(export.injections)
            data.days = dict(export.days)
            kept = [w for w in data.weights if w.source != "shotsy"]
        else:
            logged = {(i.time, i.dose_mg) for i in data.injections}
            data.injections.extend(i for i in export.injections if (i.time, i.dose_mg) not in logged)
            for day, log in export.days.items():
                data.days.setdefault(day, log)
            kept = [w for w in data.weights if w.source != "shotsy"]
        data.weights = sorted(kept + list(export.weights), key=lambda w: w.time)
        # The weight sensor only reports changes, so drop repeats of the same value.
        deduped: list[WeightEntry] = []
        for entry in data.weights:
            if deduped and abs(deduped[-1].kg - entry.kg) < 0.01:
                continue
            deduped.append(entry)
        data.weights = deduped
        if data.start_weight is None and data.weights:
            data.start_weight = data.weights[0].kg
        data.next_due_override = None
        data.next_site = None
        data.next_dose = None
        await self._async_changed(injections=True)
        new_side_effects = [n for n in export.side_effect_names if n.lower() not in known]
        if new_side_effects:
            # Adds the entities for them; the options update reloads the entry.
            self.hass.config_entries.async_update_entry(
                self.entry,
                options={**self.entry.options, CONF_SIDE_EFFECTS: [*self.side_effects, *new_side_effects]},
            )
        return {
            "injections": len(export.injections),
            "weights": len(export.weights),
            "days": len(export.days),
        }

    def export(self) -> dict[str, Any]:
        return self.records.to_dict()
