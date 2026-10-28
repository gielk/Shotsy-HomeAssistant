"""Generate the GLP-1 Tracker dashboard.

Usage: python generate_dashboard.py [--prefix retatrutide] [--json out.json] [--yaml out.yaml]

Needs these HACS cards: button-card, apexcharts-card, simple-tabs, expander-card,
stack-in-card and config-template-card.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SIDE_EFFECTS = [
    "Food Noise",
    "Misselijkheid",
    "Brandend maagzuur",
    "Verminderde eetlust",
    "Vermoeidheid",
    "Constipatie",
]
# Stomach sites as a 3 x 2 grid, seen from above: left is your left.
SITE_GRID = [
    ("Buik - Links Boven", "Links boven"),
    ("Buik - Midden Boven", "Midden boven"),
    ("Buik - Rechts Boven", "Rechts boven"),
    ("Buik - Links Onder", "Links onder"),
    ("Buik - Midden Onder", "Midden onder"),
    ("Buik - Rechts Onder", "Rechts onder"),
]
# Health card: companion app sensors as (suffix, label, unit, decimals). The
# entity is "<health prefix>_<suffix>", e.g. sensor.iphone_van_jan_body_fat_percentage.
HEALTH = [
    ("body_fat_percentage", "Vetpercentage", "%", 1),
    ("lean_body_mass", "Vetvrije massa", "kg", 1),
    ("resting_heart_rate", "Rusthartslag", "bpm", 0),
    ("vo2_max", "VO₂ max", "", 1),
]
REMINDER = "automation.medicatie_injectie_herinnering"

ACCENT = "#A21CAF"  # medication level
WEIGHT = "#DA7756"
GOAL = "#F5B82E"

# Shared JavaScript for button-card templates. "@P" becomes the entity prefix.
# Each template gets only the helpers it uses (and what those need).
HELPERS = {
    "st": ("const st = (e) => states[e]?.state;", []),
    "ok": (
        "const ok = (e) => { const s = st(e); return s !== undefined && s !== 'unknown' && s !== 'unavailable' && s !== ''; };",
        ["st"],
    ),
    "num": (
        "const num = (e) => { const v = Number(st(e)); return ok(e) && Number.isFinite(v) ? v : null; };",
        ["ok", "st"],
    ),
    "at": ("const at = (e, a) => states[e]?.attributes?.[a];", []),
    "nl": (
        "const nl = (x, d = 1) => x === null || x === undefined || x === '' || Number.isNaN(Number(x)) ? '—'"
        " : Number(x).toLocaleString('nl-NL', {minimumFractionDigits: d, maximumFractionDigits: d});",
        [],
    ),
    "dosis": ("const dosis = (x) => Number(x).toLocaleString('nl-NL', {maximumFractionDigits: 2});", []),
    "kleur": (
        "const kleur = (d) => ['#F9A8D4', '#F472B6', '#EC4899', '#DB2777', '#C026D3', '#A21CAF', '#7E22CE', '#6B21A8',"
        " '#4C1D95'][Math.max(0, Math.min(8, Math.round(Number(d)) - 1))];",
        [],
    ),
    "pil": (
        'const pil = (d) => `<span style="display:inline-flex;align-items:center;padding:1px 9px;border-radius:10px;'
        'background:${kleur(d)};color:#fff;font-size:12px;font-weight:600;line-height:20px;white-space:nowrap">${dosis(d)} mg</span>`;',
        ["kleur", "dosis"],
    ),
    "dag": (
        "const dag = (t) => new Date(t).toLocaleDateString('nl-NL', {weekday: 'short', day: 'numeric', month: 'short'});",
        [],
    ),
    "tijd": ("const tijd = (t) => new Date(t).toLocaleTimeString('nl-NL', {hour: '2-digit', minute: '2-digit'});", []),
    "iso": (
        "const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;",
        [],
    ),
    "sub": ("const sub = 'color:var(--secondary-text-color)';", []),
}


def _needed(body: str) -> list[str]:
    found: list[str] = []

    def add(name: str) -> None:
        for dep in HELPERS[name][1]:
            add(dep)
        if name not in found:
            found.append(name)

    for name in HELPERS:
        if re.search(rf"(?<![\w.']){name}\b(?!:)", body):
            add(name)
    return [n for n in HELPERS if n in found]


def js(body: str) -> str:
    """A button-card JavaScript template with the helpers it uses."""
    body = body.strip()
    prelude = "\n".join(HELPERS[name][0] for name in _needed(body))
    return "[[[\n" + (prelude + "\n" if prelude else "") + body + "\n]]]"


def css(**props: str) -> list[dict]:
    return [{k.replace("_", "-"): v} for k, v in props.items()]


# ----- templates ---------------------------------------------------------

TEMPLATES = {
    "glp1_kaart": {
        "show_icon": True,
        "show_name": True,
        "show_label": True,
        "show_state": False,
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(padding="16px"),
            "img_cell": css(
                width="44px",
                height="44px",
                border_radius="50%",
                background="color-mix(in srgb, var(--primary-color) 18%, transparent)",
                align_self="center",
            ),
            "icon": css(width="24px", color="var(--primary-color)"),
            "name": css(justify_self="start", align_self="end", font_size="15px", font_weight="600", text_align="left"),
            "label": css(
                justify_self="start",
                align_self="start",
                font_size="12.5px",
                color="var(--secondary-text-color)",
                text_align="left",
                white_space="normal",
                margin_top="2px",
            ),
        },
    },
    "glp1_rond": {
        "show_name": False,
        "show_state": False,
        "show_label": False,
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(
                width="44px",
                height="44px",
                border_radius="50%",
                padding="0",
                background="color-mix(in srgb, var(--primary-text-color) 8%, transparent)",
                box_shadow="none",
                border="none",
            ),
            "icon": css(width="22px", color="var(--primary-text-color)"),
        },
    },
    "glp1_pil": {
        "show_state": False,
        "show_label": False,
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(
                height="36px",
                padding="0 14px 0 10px",
                border_radius="18px",
                background="color-mix(in srgb, var(--primary-color) 18%, transparent)",
                box_shadow="none",
                border="none",
            ),
            "grid": css(grid_template_areas='"i n"', grid_template_columns="auto auto", column_gap="6px"),
            "icon": css(width="18px", color="var(--primary-color)"),
            "name": css(font_size="13px", font_weight="600", color="var(--primary-color)"),
        },
    },
    "glp1_actie": {
        "show_state": False,
        "show_label": False,
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(
                height="44px",
                padding="0 18px",
                border_radius="22px",
                background="var(--primary-color)",
                box_shadow="none",
                border="none",
            ),
            "grid": css(grid_template_areas='"i n"', grid_template_columns="auto auto", column_gap="8px"),
            "icon": css(width="20px", color="#fff"),
            "name": css(font_size="14px", font_weight="600", color="#fff"),
        },
    },
    "glp1_segment": {
        "entity": "select.@P_grafiekperiode",
        "show_icon": False,
        "show_name": True,
        "show_label": False,
        "show_state": False,
        "tap_action": {
            "action": "perform-action",
            "perform_action": "select.select_option",
            "target": {"entity_id": "select.@P_grafiekperiode"},
            "data": {"option": "[[[ return variables.optie; ]]]"},
        },
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(
                padding="9px 4px",
                border_radius="12px",
                box_shadow="none",
                border="none",
                background="[[[ return entity?.state === variables.optie ? 'var(--primary-color)' : 'color-mix(in srgb, var(--primary-text-color) 8%, transparent)'; ]]]",
            ),
            "name": css(
                font_size="13px",
                font_weight="600",
                color="[[[ return entity?.state === variables.optie ? '#fff' : 'var(--primary-text-color)'; ]]]",
            ),
        },
    },
    "glp1_rij": {
        "show_icon": True,
        "show_name": True,
        "show_label": True,
        "show_state": False,
        "hold_action": {"action": "none"},
        "styles": {
            "card": css(padding="12px 14px"),
            "grid": css(
                grid_template_areas='"i n right" "i l right"',
                grid_template_columns="40px 1fr auto",
                grid_template_rows="auto auto",
                column_gap="12px",
            ),
            "img_cell": css(
                width="40px",
                height="40px",
                border_radius="12px",
                align_self="center",
                background="color-mix(in srgb, var(--primary-color) 18%, transparent)",
            ),
            "icon": css(width="22px", color="var(--primary-color)"),
            "name": css(justify_self="start", align_self="end", font_size="14px", font_weight="600"),
            "label": css(
                justify_self="start",
                align_self="start",
                font_size="12px",
                color="var(--secondary-text-color)",
                text_align="left",
                white_space="normal",
            ),
            "custom_fields": {"right": css(align_self="center", display="flex", gap="8px")},
        },
    },
}


def rond(icon: str, action: str, entity: str, value_js: str) -> dict:
    return {
        "card": {
            "type": "custom:button-card",
            "template": "glp1_rond",
            "icon": icon,
            "tap_action": {
                "action": "perform-action",
                "perform_action": action,
                "target": {"entity_id": entity},
                "data": {"value": value_js},
            },
        }
    }


def stepper(entity: str, step: float, minimum: float, maximum: float) -> dict[str, dict]:
    value = f"(Number(states['{entity}'].state) || 0)"
    return {
        "minus": rond(
            "mdi:minus",
            "number.set_value",
            entity,
            f"[[[ return Math.max({minimum}, Math.round(({value} - {step}) / {step}) * {step}); ]]]",
        ),
        "plus": rond(
            "mdi:plus",
            "number.set_value",
            entity,
            f"[[[ return Math.min({maximum}, Math.round(({value} + {step}) / {step}) * {step}); ]]]",
        ),
    }


def log_button(label: str = "Injectie gezet") -> dict:
    return {
        "card": {
            "type": "custom:button-card",
            "template": "glp1_actie",
            "icon": "mdi:check",
            "name": label,
            "tap_action": {
                "action": "perform-action",
                "perform_action": "button.press",
                "target": {"entity_id": "button.@P_injectie_registreren"},
                "confirmation": {
                    "text": js(
                        """
const e = 'sensor.@P_volgende_injectie';
return `Injectie ${at(e, 'number')} registreren: ${dosis(at(e, 'dose_mg'))} mg in ${at(e, 'site') || 'geen plek'}, nu?`;
"""
                    )
                },
            },
        }
    }


def pil(icon: str, name: str, tap_action: dict) -> dict:
    return {
        "card": {
            "type": "custom:button-card",
            "template": "glp1_pil",
            "icon": icon,
            "name": name,
            "tap_action": tap_action,
        }
    }


def more_info(entity: str) -> dict:
    return {"action": "more-info", "entity": entity}


# ----- Overzicht -----------------------------------------------------------

NEXT_VARIABLES = js(
    """
const e = 'sensor.@P_volgende_injectie', l = 'sensor.@P_laatste_injectie';
const due = ok(e) ? new Date(st(e)) : null;
const last = ok(l) ? new Date(st(l)) : null;
const now = new Date();
const start = new Date(now); start.setHours(0, 0, 0, 0);
const days = due ? Math.round((new Date(due).setHours(0, 0, 0, 0) - start) / 864e5) : null;
return {due, last, now, days, late: due ? now > due : false, dose: at(e, 'dose_mg'), site: at(e, 'site'), n: at(e, 'number')};
"""
)

next_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "sensor.@P_volgende_injectie",
    "icon": "mdi:needle",
    "triggers_update": ["sensor.@P_laatste_injectie", "sensor.@P_volgende_injectie"],
    "variables": {"v": NEXT_VARIABLES},
    "name": js(
        """
const v = variables.v;
if (!v.due) return 'Nog geen injectie gepland';
if (v.late) {
  const d = Math.floor((v.now - v.due) / 864e5);
  return d >= 1 ? `${d} ${d === 1 ? 'dag' : 'dagen'} te laat` : 'Tijd voor je injectie';
}
if (v.days === 0) return 'Vandaag';
if (v.days === 1) return 'Morgen';
return `Over ${v.days} dagen`;
"""
    ),
    "label": js(
        """
const v = variables.v;
if (!v.due) return 'Registreer je eerste injectie';
return `Injectie ${v.n}, ${dag(v.due)} om ${tijd(v.due)}${v.site ? ' · ' + v.site : ''}`;
"""
    ),
    "custom_fields": {
        "val": js(
            """
const d = variables.v.dose;
return d ? `${dosis(d)}<span style="font-size:17px;font-weight:600;margin-left:2px">mg</span>` : '';
"""
        ),
        "bar": js(
            """
const v = variables.v;
if (!v.due || !v.last) return '';
const pct = Math.max(0, Math.min(100, (v.now - v.last) / (v.due - v.last) * 100));
const col = v.late ? 'var(--error-color, #e45649)' : 'var(--primary-color)';
return `<div style="position:relative;height:10px;border-radius:5px;background:color-mix(in srgb, var(--primary-text-color) 10%, transparent);overflow:hidden">
<div style="position:absolute;top:0;bottom:0;left:0;width:${pct}%;background:${col};border-radius:5px"></div></div>
<div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;${sub}"><span>Vorige <b style="color:var(--primary-text-color)">${dag(v.last)}</b></span><span>Volgende <b style="color:var(--primary-text-color)">${dag(v.due)}</b></span></div>`;
"""
        ),
        "knop": log_button(),
        "wijzig": pil("mdi:calendar-edit", "Datum", more_info("datetime.@P_volgende_injectie")),
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n val" "i l val" "bar bar bar" "knop knop wijzig"',
            grid_template_columns="44px 1fr auto",
            grid_template_rows="auto auto auto auto",
            column_gap="12px",
        ),
        "img_cell": [
            {
                "background": "[[[ return variables.v.late ? 'color-mix(in srgb, var(--error-color, #e45649) 18%, transparent)' : 'color-mix(in srgb, var(--primary-color) 18%, transparent)'; ]]]"
            }
        ],
        "icon": [
            {"color": "[[[ return variables.v.late ? 'var(--error-color, #e45649)' : 'var(--primary-color)'; ]]]"}
        ],
        "custom_fields": {
            "val": css(align_self="center", justify_self="end", font_size="34px", font_weight="700", line_height="1"),
            "bar": css(margin_top="16px", justify_self="stretch"),
            "knop": css(margin_top="14px", justify_self="start"),
            "wijzig": css(margin_top="14px", justify_self="end", align_self="center"),
        },
    },
}

level_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "sensor.@P_medicatieniveau",
    "icon": "mdi:chart-bell-curve-cumulative",
    "tap_action": {"action": "more-info"},
    "name": "Geschat medicatieniveau",
    "label": js(
        """
const e = 'sensor.@P_medicatieniveau';
const peak = at(e, 'peak_next_7_days'), pt = at(e, 'peak_time');
const parts = [`Vandaag gemiddeld ${nl(at(e, 'today_average'), 2)} mg`];
if (peak && pt) parts.push(`piek ${nl(peak, 1)} mg op ${dag(pt)}`);
return parts.join(' · ');
"""
    ),
    "custom_fields": {
        "val": js(
            """
return `${nl(num('sensor.@P_medicatieniveau'), 2)}<span style="font-size:17px;font-weight:600;margin-left:2px">mg</span>`;
"""
        )
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n val" "i l val"', grid_template_columns="44px 1fr auto", column_gap="12px"
        ),
        "custom_fields": {"val": css(align_self="center", font_size="30px", font_weight="700", line_height="1")},
    },
}

level_chart = {
    "type": "custom:apexcharts-card",
    "graph_span": "35d",
    "span": {"offset": "+14d"},
    "update_interval": "10min",
    "now": {"show": True, "label": "Nu", "color": "#8a8a8a"},
    "header": {"show": True, "title": "Niveau, 3 weken terug en 2 vooruit", "show_states": False},
    "apex_config": {
        "chart": {"height": 200},
        "legend": {"show": True, "position": "top", "horizontalAlign": "left", "fontSize": "12px"},
        "grid": {"strokeDashArray": 3, "borderColor": "rgba(127,127,127,0.18)"},
        "tooltip": {"x": {"format": "ddd d MMM HH:mm"}},
    },
    "yaxis": [{"min": 0, "decimals": 0, "apex_config": {"tickAmount": 4}}],
    "series": [
        {
            "entity": "sensor.@P_medicatieniveau",
            "name": "Niveau",
            "type": "area",
            "color": ACCENT,
            "opacity": 0.2,
            "stroke_width": 2,
            "unit": "mg",
            "float_precision": 2,
            "data_generator": "return (entity.attributes.series || []).filter((p) => p[0] <= Date.now());",
        },
        {
            "entity": "sensor.@P_medicatieniveau",
            "name": "Met geplande prik",
            "type": "line",
            "color": ACCENT,
            "stroke_width": 2,
            "stroke_dash": 4,
            "unit": "mg",
            "float_precision": 2,
            "data_generator": "return (entity.attributes.planned || []).filter((p) => p[0] >= Date.now() - 3 * 36e5);",
        },
    ],
}

summary_card = {
    "type": "custom:button-card",
    "show_icon": False,
    "show_name": False,
    "show_state": False,
    "show_label": False,
    "tap_action": {"action": "none"},
    "hold_action": {"action": "none"},
    "triggers_update": [
        "sensor.@P_aantal_injecties",
        "sensor.@P_laatste_dosis",
        "sensor.@P_gewicht",
        "sensor.@P_gewicht_verandering",
    ],
    "custom_fields": {
        "tegels": js(
            """
const tile = (icon, label, value, extra) => `<div style="padding:12px 10px;border-radius:14px;background:color-mix(in srgb, var(--primary-text-color) 5%, transparent);text-align:left">
<div style="display:flex;align-items:center;gap:6px;font-size:12px;${sub}"><ha-icon icon="${icon}" style="--mdc-icon-size:16px;color:var(--primary-color)"></ha-icon>${label}</div>
<div style="font-size:22px;font-weight:700;margin-top:6px;line-height:1.1">${value}</div>
<div style="font-size:11.5px;${sub};margin-top:3px">${extra}</div></div>`;
const change = num('sensor.@P_gewicht_verandering');
const last = num('sensor.@P_laatste_dosis');
return `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
${tile('mdi:needle', 'Injecties', st('sensor.@P_aantal_injecties') ?? '—', 'genomen')}
${tile('mdi:eyedropper', 'Laatste dosis', last === null ? '—' : dosis(last) + '<span style="font-size:13px"> mg</span>', ok('sensor.@P_laatste_injectie') ? dag(st('sensor.@P_laatste_injectie')) : '')}
${tile('mdi:scale-bathroom', 'Gewicht', nl(num('sensor.@P_gewicht'), 1) + '<span style="font-size:13px"> kg</span>', change === null ? '' : `${change > 0 ? '+' : ''}${nl(change, 1)} kg sinds start`)}
</div>`;
"""
        )
    },
    "styles": {
        "card": css(padding="12px"),
        "grid": css(grid_template_areas='"tegels"', grid_template_columns="1fr"),
        "custom_fields": {"tegels": css(justify_self="stretch")},
    },
}

# ----- Injecties -------------------------------------------------------------

plan_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "number.@P_volgende_dosis",
    "icon": "mdi:eyedropper",
    "triggers_update": ["sensor.@P_volgende_injectie"],
    "name": js("return `Injectie ${at('sensor.@P_volgende_injectie', 'number') ?? ''}`;"),
    "label": js(
        """
const e = 'sensor.@P_volgende_injectie';
if (!ok(e)) return 'Nog niet gepland';
return `Gepland ${dag(st(e))} om ${tijd(st(e))}`;
"""
    ),
    "custom_fields": {
        "val": js(
            """
const d = num('number.@P_volgende_dosis');
return d === null ? '—' : `${dosis(d)}<span style="font-size:17px;font-weight:600;margin-left:2px">mg</span>`;
"""
        ),
        **stepper("number.@P_volgende_dosis", 0.5, 0, 50),
        "datum": pil("mdi:calendar-edit", "Datum en tijd", more_info("datetime.@P_volgende_injectie")),
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n n val val" "i l l val val" "datum datum datum minus plus"',
            grid_template_columns="44px 1fr auto 44px 44px",
            grid_template_rows="auto auto auto",
            column_gap="12px",
        ),
        "custom_fields": {
            "val": css(align_self="center", justify_self="end", font_size="34px", font_weight="700", line_height="1"),
            "datum": css(margin_top="14px", justify_self="start", align_self="center"),
            "minus": css(margin_top="14px"),
            "plus": css(margin_top="14px"),
        },
    },
}


PLEK_TEMPLATE = {
    "entity": "select.@P_volgende_prikplek",
    "show_icon": False,
    "show_name": True,
    "show_label": True,
    "show_state": False,
    "triggers_update": ["sensor.@P_aantal_injecties"],
    "label": js(
        """
const used = (at('sensor.@P_aantal_injecties', 'injections') || []).find((i) => i.site === variables.plek);
if (!used) return 'nooit';
const d = Math.floor((Date.now() - used.t) / 864e5);
return d === 0 ? 'vandaag' : (d === 1 ? 'gisteren' : `${d} dagen`);
"""
    ),
    "tap_action": {
        "action": "perform-action",
        "perform_action": "select.select_option",
        "target": {"entity_id": "select.@P_volgende_prikplek"},
        "data": {"option": "[[[ return variables.plek; ]]]"},
    },
    "hold_action": {"action": "none"},
    "styles": {
        "card": css(
            padding="10px 4px",
            border_radius="14px",
            box_shadow="none",
            border="[[[ return entity?.attributes?.options?.includes(variables.plek) ? 'none' : '1px dashed var(--divider-color)'; ]]]",
            background="[[[ return entity?.state === variables.plek ? 'var(--primary-color)' : 'color-mix(in srgb, var(--primary-text-color) 6%, transparent)'; ]]]",
        ),
        "name": css(
            font_size="13px",
            font_weight="600",
            color="[[[ return entity?.state === variables.plek ? '#fff' : 'var(--primary-text-color)'; ]]]",
        ),
        "label": css(
            font_size="11px",
            color="[[[ return entity?.state === variables.plek ? 'rgba(255,255,255,.85)' : 'var(--secondary-text-color)'; ]]]",
        ),
    },
}


def site_cell(site: str, label: str) -> dict:
    return {"type": "custom:button-card", "template": "glp1_plek", "name": label, "variables": {"plek": site}}


site_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "select.@P_volgende_prikplek",
    "icon": "mdi:human-handsdown",
    "triggers_update": ["sensor.@P_volgende_injectie"],
    "name": "Prikplek",
    "label": js(
        """
const sel = st('select.@P_volgende_prikplek');
const sug = at('sensor.@P_volgende_injectie', 'suggested_site');
if (!sel) return 'Kies een plek';
return sel === sug ? `${sel}, langst niet gebruikt` : `${sel} · voorstel: ${sug}`;
"""
    ),
    "custom_fields": {
        # Three equal columns, seen from above: left is your left.
        "cellen": {
            "card": {
                "type": "grid",
                "columns": 3,
                "square": False,
                "cards": [site_cell(site, label) for site, label in SITE_GRID],
            }
        },
        "anders": pil("mdi:dots-horizontal", "Andere plek", more_info("select.@P_volgende_prikplek")),
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n" "i l" "cellen cellen" "anders anders"',
            grid_template_columns="44px 1fr",
            grid_template_rows="auto auto auto auto",
            column_gap="12px",
        ),
        "custom_fields": {
            "cellen": css(justify_self="stretch", margin_top="12px"),
            "anders": css(justify_self="start", margin_top="10px"),
        },
    },
}

HISTORY_JS = """
const list = at('sensor.@P_aantal_injecties', 'injections') || [];
const name = states['sensor.@P_laatste_injectie']?.attributes?.friendly_name?.split(' ')[0] || 'Injectie';
if (!list.length) return `<div style="${sub};font-size:13px">Nog geen injecties</div>`;
let month = '', out = '';
for (const i of list.slice(0, LIMIT)) {
  const m = new Date(i.t).toLocaleDateString('nl-NL', {month: 'long', year: 'numeric'}).toUpperCase();
  if (m !== month) {
    month = m;
    out += `<div style="font-size:12px;letter-spacing:.04em;${sub};margin:${out ? 14 : 0}px 0 6px">${m}</div>`;
  }
  const extra = [i.site, i.pain ? `pijn ${i.pain}/10` : '', i.notes].filter(Boolean).join(' · ');
  out += `<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--divider-color)">
<div style="text-align:left;min-width:0"><div style="font-size:11.5px;${sub}">Injectie ${i.n}</div>
<div style="display:flex;align-items:center;gap:8px;margin-top:2px;font-size:14px;font-weight:600">${name} ${pil(i.dose)}</div>
<div style="font-size:12px;${sub};margin-top:2px;white-space:normal">${extra}</div></div>
<div style="font-size:12.5px;${sub};text-align:right;white-space:nowrap">${dag(i.t)}<br>${tijd(i.t)}</div></div>`;
}
return out;
"""


def history_card(limit: int, scroll: bool) -> dict:
    return {
        "type": "custom:button-card",
        "show_icon": False,
        "show_name": False,
        "show_state": False,
        "show_label": False,
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "triggers_update": ["sensor.@P_aantal_injecties"],
        "custom_fields": {"lijst": js(HISTORY_JS.replace("LIMIT", str(limit)))},
        "styles": {
            "card": css(padding="12px 16px", box_shadow="none" if scroll else "var(--ha-card-box-shadow, none)")
            + ([{"background": "none"}, {"border": "none"}] if scroll else []),
            "grid": css(grid_template_areas='"lijst"', grid_template_columns="1fr"),
            "custom_fields": {
                "lijst": css(justify_self="stretch")
                + ([{"max-height": "480px"}, {"overflow-y": "auto"}] if scroll else [])
            },
        },
    }


history_recent = history_card(6, False)
history_all = {
    "type": "custom:expander-card",
    "expanded": False,
    "title-card-button-overlay": True,
    "padding": "0px",
    "title-card-padding": "0px",
    "child-padding": "0px",
    "gap": "0px",
    "title-card": {
        "type": "custom:button-card",
        "template": "glp1_rij",
        "icon": "mdi:history",
        "name": "Alle injecties",
        "label": js("return `${st('sensor.@P_aantal_injecties') ?? 0} injecties sinds de start`;"),
        "tap_action": {"action": "none"},
        "styles": {"card": [{"background": "none"}, {"box-shadow": "none"}, {"border": "none"}]},
    },
    "cards": [
        history_card(1000, True),
        {
            "type": "custom:button-card",
            "template": "glp1_rij",
            "icon": "mdi:delete-outline",
            "name": "Laatste injectie verwijderen",
            "label": js(
                """
const l = 'sensor.@P_laatste_injectie';
return ok(l) ? `Injectie ${at(l, 'number')}: ${dosis(at(l, 'dose_mg'))} mg op ${dag(st(l))}` : 'Geen injecties';
"""
            ),
            "tap_action": {
                "action": "perform-action",
                "perform_action": "glp1_tracker.delete_injection",
                "data": {"injection_id": "last"},
                "confirmation": {"text": "De laatste injectie verwijderen?"},
            },
            "styles": {
                "card": [{"background": "none"}, {"box-shadow": "none"}, {"border": "none"}],
                "img_cell": [{"background": "color-mix(in srgb, var(--error-color, #e45649) 15%, transparent)"}],
                "icon": [{"color": "var(--error-color, #e45649)"}],
            },
        },
    ],
}

# ----- Resultaten ------------------------------------------------------------

range_buttons = {
    "type": "grid",
    "columns": 4,
    "square": False,
    "cards": [
        {"type": "custom:button-card", "template": "glp1_segment", "name": name, "variables": {"optie": key}}
        for key, name in (("1m", "1 maand"), ("3m", "3 maanden"), ("6m", "6 maanden"), ("all", "Altijd"))
    ],
}

stats_card = {
    "type": "custom:button-card",
    "show_icon": False,
    "show_name": False,
    "show_state": False,
    "show_label": False,
    "tap_action": {"action": "more-info", "entity": "sensor.@P_gewicht"},
    "hold_action": {"action": "none"},
    "triggers_update": [
        "sensor.@P_gewicht",
        "sensor.@P_gewicht_verandering",
        "sensor.@P_gewicht_verandering_procent",
        "sensor.@P_bmi",
        "sensor.@P_gewicht_per_week",
        "sensor.@P_tot_doel",
    ],
    "custom_fields": {
        "tegels": js(
            """
const tile = (icon, label, value, unit) => `<div style="padding:12px 10px;border-radius:14px;background:color-mix(in srgb, var(--primary-text-color) 5%, transparent);text-align:left">
<div style="display:flex;align-items:center;gap:6px;font-size:12px;${sub}"><ha-icon icon="${icon}" style="--mdc-icon-size:16px;color:var(--primary-color)"></ha-icon>${label}</div>
<div style="font-size:22px;font-weight:700;margin-top:6px;line-height:1.1;white-space:nowrap">${value}<span style="font-size:12px;font-weight:500;${sub}"> ${unit}</span></div></div>`;
const signed = (x, d) => x === null ? '—' : `${x > 0 ? '+' : ''}${nl(x, d)}`;
const goalPct = at('sensor.@P_tot_doel', 'to_goal_percent');
return `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
${tile('mdi:scale-unbalanced', 'Totale verandering', signed(num('sensor.@P_gewicht_verandering'), 1), 'kg')}
${tile('mdi:human', 'BMI', nl(num('sensor.@P_bmi'), 1), '')}
${tile('mdi:scale-bathroom', 'Gewicht', nl(num('sensor.@P_gewicht'), 1), 'kg')}
${tile('mdi:percent-outline', 'Procent', signed(num('sensor.@P_gewicht_verandering_procent'), 1), '%')}
${tile('mdi:timer-sand', 'Per week', signed(num('sensor.@P_gewicht_per_week'), 2), 'kg')}
${tile('mdi:flag-checkered', 'Naar doel', nl(num('sensor.@P_tot_doel'), 1), goalPct === null || goalPct === undefined ? 'kg' : `kg (${Math.round(goalPct)}%)`)}
</div>`;
"""
        )
    },
    "styles": {
        "card": css(padding="12px"),
        "grid": css(grid_template_areas='"tegels"', grid_template_columns="1fr"),
        "custom_fields": {"tegels": css(justify_self="stretch")},
    },
}

weight_chart = {
    "type": "custom:config-template-card",
    "entities": [
        "select.@P_grafiekperiode",
        "sensor.@P_gewicht",
        "sensor.@P_aantal_injecties",
        "number.@P_doelgewicht",
    ],
    "variables": {
        "SPAN": (
            "(() => { const r = states['select.@P_grafiekperiode']?.state;"
            " if (r === '1m') return '31d'; if (r === '3m') return '92d'; if (r === '6m') return '183d';"
            " const h = states['sensor.@P_gewicht']?.attributes?.history || [];"
            " const first = h.length ? h[0][0] : Date.now();"
            " return Math.max(31, Math.ceil((Date.now() - first) / 864e5) + 7) + 'd'; })()"
        ),
    },
    "card": {
        "type": "custom:apexcharts-card",
        "graph_span": "${SPAN}",
        "update_interval": "1h",
        "header": {"show": True, "title": "Gewicht en dosis", "show_states": False},
        "apex_config": {
            "chart": {"height": 240},
            "legend": {"show": True, "position": "top", "horizontalAlign": "left", "fontSize": "12px"},
            "grid": {"strokeDashArray": 3, "borderColor": "rgba(127,127,127,0.18)"},
            "tooltip": {"x": {"format": "ddd d MMM yyyy"}},
            "markers": {"size": 0},
        },
        "yaxis": [
            {"id": "kg", "decimals": 0, "apex_config": {"tickAmount": 4}},
            {"id": "mg", "opposite": True, "min": 0, "decimals": 0, "apex_config": {"tickAmount": 4}},
        ],
        "series": [
            {
                "entity": "sensor.@P_aantal_injecties",
                "name": "Dosis",
                "type": "area",
                "curve": "stepline",
                "yaxis_id": "mg",
                "color": ACCENT,
                "opacity": 0.15,
                "stroke_width": 1.5,
                "unit": "mg",
                "data_generator": (
                    "const l = [...(entity.attributes.injections || [])].reverse().map((i) => [i.t, i.dose]);"
                    " if (l.length) l.push([Date.now(), l[l.length - 1][1]]); return l;"
                ),
            },
            {
                "entity": "sensor.@P_gewicht",
                "name": "Gewicht",
                "type": "line",
                "yaxis_id": "kg",
                "color": WEIGHT,
                "stroke_width": 2.5,
                "unit": "kg",
                "float_precision": 1,
                "data_generator": "return entity.attributes.history || [];",
            },
            {
                "entity": "number.@P_doelgewicht",
                "name": "Doel",
                "type": "line",
                "yaxis_id": "kg",
                "color": GOAL,
                "stroke_width": 2,
                "stroke_dash": 4,
                "unit": "kg",
                "data_generator": (
                    "const g = Number(entity.state); if (!Number.isFinite(g) || g <= 0) return [];"
                    " return [[Date.now() - 2000 * 864e5, g], [Date.now(), g]];"
                ),
            },
        ],
    },
}

progress_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "sensor.@P_tot_doel",
    "icon": "mdi:flag-checkered",
    "triggers_update": ["sensor.@P_gewicht", "number.@P_doelgewicht", "number.@P_startgewicht"],
    "name": js(
        """
const m = at('sensor.@P_tot_doel', 'next_milestone');
return m ? `Volgend tussendoel ${dosis(m)} kg` : 'Voortgang';
"""
    ),
    "label": js(
        """
const goal = at('sensor.@P_tot_doel', 'goal');
const togo = num('sensor.@P_tot_doel');
if (!goal) return 'Stel een doelgewicht in bij Instellingen';
return togo === 0 ? `Doel van ${dosis(goal)} kg bereikt` : `Nog ${nl(togo, 1)} kg tot je doel van ${dosis(goal)} kg`;
"""
    ),
    "custom_fields": {
        "val": js(
            """
const m = at('sensor.@P_tot_doel', 'next_milestone'), w = num('sensor.@P_gewicht');
if (!m || w === null) return '';
return `${nl(w - m, 1)}<span style="font-size:15px;font-weight:600;margin-left:2px">kg</span><div style="font-size:11.5px;font-weight:400;${sub};text-align:right;margin-top:2px">te gaan</div>`;
"""
        ),
        "bar": js(
            """
const start = num('number.@P_startgewicht'), goal = at('sensor.@P_tot_doel', 'goal'), w = num('sensor.@P_gewicht');
if (!start || !goal || w === null || start <= goal) return '';
const pct = (x) => Math.max(0, Math.min(100, (start - x) / (start - goal) * 100));
let ticks = '';
for (let k = Math.ceil(goal / 5) * 5; k < start; k += 5) {
  ticks += `<div style="position:absolute;top:0;bottom:0;left:calc(${pct(k)}% - 1px);width:2px;background:var(--card-background-color, #fff);opacity:.6"></div>`;
}
return `<div style="position:relative;height:10px;border-radius:5px;background:color-mix(in srgb, var(--primary-text-color) 10%, transparent);overflow:hidden">
<div style="position:absolute;top:0;bottom:0;left:0;width:${pct(w)}%;background:var(--primary-color);border-radius:5px"></div>${ticks}</div>
<div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;${sub}"><span>Start <b style="color:var(--primary-text-color)">${nl(start, 1)} kg</b></span><span><b style="color:var(--primary-text-color)">${Math.round(pct(w))}%</b> van je doel</span><span>Doel <b style="color:var(--primary-text-color)">${nl(goal, 1)} kg</b></span></div>`;
"""
        ),
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n val" "i l val" "bar bar bar"',
            grid_template_columns="44px 1fr auto",
            grid_template_rows="auto auto auto",
            column_gap="12px",
        ),
        "custom_fields": {
            "val": css(align_self="center", font_size="26px", font_weight="700", line_height="1"),
            "bar": css(margin_top="16px", justify_self="stretch"),
        },
    },
}

dose_stats_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "sensor.@P_gewicht_per_week",
    "icon": "mdi:chart-timeline-variant",
    "name": "Gewichtsverlies per dosis",
    "label": "Elke periode tussen twee injecties telt voor de dosis van de eerste",
    "custom_fields": {
        "tabel": js(
            """
const rows = at('sensor.@P_gewicht_per_week', 'dose_stats') || [];
if (!rows.length) return `<div style="${sub};font-size:13px">Nog te weinig metingen</div>`;
return rows.map((r) => {
  const v = r.kg_per_week;
  const col = v === null ? 'var(--secondary-text-color)' : (v < 0 ? 'var(--success-color, #4caf50)' : 'var(--error-color, #e45649)');
  return `<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--divider-color)">
<div style="display:flex;align-items:center;gap:10px">${pil(r.dose_mg)}<span style="font-size:12.5px;${sub}">${r.injections}× · ${nl(r.weeks, 1)} wk</span></div>
<div style="font-size:14px;font-weight:600;color:${col}">${v === null ? '—' : `${v > 0 ? '+' : ''}${nl(v, 2)} kg/wk`}</div></div>`;
}).join('');
"""
        )
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n" "i l" "tabel tabel"',
            grid_template_columns="44px 1fr",
            grid_template_rows="auto auto auto",
            column_gap="12px",
        ),
        "custom_fields": {"tabel": css(justify_self="stretch", margin_top="12px")},
    },
}


def health_card(prefix: str) -> dict:
    entities = [(f"{prefix}_{suffix}", label, unit, decimals) for suffix, label, unit, decimals in HEALTH]
    tiles = [f"tile('{entity}', '{label}', '{unit}', {decimals})" for entity, label, unit, decimals in entities]
    return {
        "type": "custom:button-card",
        "template": "glp1_kaart",
        "icon": "mdi:heart-pulse",
        "name": "Gezondheid",
        "label": "Uit Apple Gezondheid via je iPhone",
        "triggers_update": [entity for entity, *_ in entities],
        "custom_fields": {
            "tegels": js(
                """
const tile = (e, label, unit, d) => `<div style="padding:10px;border-radius:14px;background:color-mix(in srgb, var(--primary-text-color) 5%, transparent);text-align:left">
<div style="font-size:12px;${sub}">${label}</div>
<div style="font-size:19px;font-weight:700;margin-top:4px;white-space:nowrap">${nl(num(e), d)}<span style="font-size:12px;font-weight:500;${sub}"> ${unit}</span></div></div>`;
return `<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px">${[TILES].join('')}</div>`;
""".replace("TILES", ", ".join(tiles))
            )
        },
        "styles": {
            "grid": css(
                grid_template_areas='"i n" "i l" "tegels tegels"',
                grid_template_columns="44px 1fr",
                grid_template_rows="auto auto auto",
                column_gap="12px",
            ),
            "custom_fields": {"tegels": css(justify_self="stretch", margin_top="12px")},
        },
    }


# ----- Agenda ----------------------------------------------------------------

SELECTED = "states['date.@P_agendadag']?.state"


def month_step(icon: str, delta: int) -> dict:
    return {
        "card": {
            "type": "custom:button-card",
            "template": "glp1_rond",
            "icon": icon,
            "tap_action": {
                "action": "perform-action",
                "perform_action": "date.set_value",
                "target": {"entity_id": "date.@P_agendadag"},
                "data": {
                    "date": js(
                        f"""
const [y, m, d] = ({SELECTED} || iso(new Date())).split('-').map(Number);
const last = new Date(y, m - 1 + ({delta}) + 1, 0).getDate();
return iso(new Date(y, m - 1 + ({delta}), Math.min(d, last)));
"""
                    )
                },
            },
        }
    }


month_header = {
    "type": "custom:button-card",
    "entity": "date.@P_agendadag",
    "show_icon": False,
    "show_name": True,
    "show_label": False,
    "show_state": False,
    "tap_action": {"action": "more-info"},
    "hold_action": {"action": "none"},
    "name": js(
        """
const [y, m] = (st('date.@P_agendadag') || iso(new Date())).split('-').map(Number);
return new Date(y, m - 1, 1).toLocaleDateString('nl-NL', {month: 'long', year: 'numeric'});
"""
    ),
    "custom_fields": {
        "terug": month_step("mdi:chevron-left", -1),
        "vooruit": month_step("mdi:chevron-right", 1),
        "vandaag": pil(
            "mdi:calendar-today",
            "Vandaag",
            {
                "action": "perform-action",
                "perform_action": "date.set_value",
                "target": {"entity_id": "date.@P_agendadag"},
                "data": {"date": js("return iso(new Date());")},
            },
        ),
        "weekdagen": (
            '<div style="display:grid;grid-template-columns:repeat(7,1fr);font-size:12px;'
            'color:var(--secondary-text-color);text-align:center">'
            + "".join(f"<span>{d}</span>" for d in ("ma", "di", "wo", "do", "vr", "za", "zo"))
            + "</div>"
        ),
    },
    "styles": {
        "card": css(padding="14px 14px 6px", background="none", box_shadow="none", border="none"),
        "grid": css(
            grid_template_areas='"n vandaag terug vooruit" "weekdagen weekdagen weekdagen weekdagen"',
            grid_template_columns="1fr auto 44px 44px",
            column_gap="8px",
        ),
        "name": css(justify_self="start", font_size="20px", font_weight="700", text_transform="capitalize"),
        "custom_fields": {"weekdagen": css(justify_self="stretch", margin_top="12px")},
    },
}

DAY_VARIABLES = js(
    """
const sel = st('date.@P_agendadag') || iso(new Date());
const [y, m] = sel.split('-').map(Number);
const offset = (new Date(y, m - 1, 1).getDay() + 6) % 7;
const n = variables.cel - offset + 1;
if (n < 1 || n > new Date(y, m, 0).getDate()) return {n: null, iso: sel};
const day = iso(new Date(y, m - 1, n));
const info = (at('sensor.@P_dagoverzicht', 'month') || [])[n - 1] || {};
return {n, iso: day, info, selected: day === sel, today: day === iso(new Date())};
"""
)


DAY_TEMPLATE = {
    "show_icon": False,
    "show_name": True,
    "show_label": False,
    "show_state": False,
    "triggers_update": ["date.@P_agendadag", "sensor.@P_dagoverzicht"],
    "variables": {"dag": DAY_VARIABLES},
    "name": "[[[ return variables.dag.n ? String(variables.dag.n) : ''; ]]]",
    "custom_fields": {
        "stip": js(
            """
const d = variables.dag;
if (!d.n || !d.info.log) return '';
return `<div style="width:5px;height:5px;border-radius:50%;background:${d.info.dose ? '#fff' : '#F5B82E'};margin:0 auto"></div>`;
"""
        )
    },
    "tap_action": {
        "action": "perform-action",
        "perform_action": "date.set_value",
        "target": {"entity_id": "date.@P_agendadag"},
        "data": {"date": "[[[ return variables.dag.iso; ]]]"},
    },
    "hold_action": {"action": "none"},
    "styles": {
        "card": css(
            height="40px",
            width="40px",
            padding="0",
            margin="0 auto",
            border_radius="50%",
            box_shadow="none",
            border=js(
                "const d = variables.dag; return d.selected ? '2px solid var(--primary-text-color)' : '2px solid transparent';"
            ),
            background=js(
                """
const d = variables.dag;
if (!d.n) return 'none';
if (d.info.dose) return kleur(d.info.dose);
if (d.today) return 'color-mix(in srgb, var(--primary-text-color) 14%, transparent)';
return 'none';
"""
            ),
        ),
        "grid": css(grid_template_areas='"n" "stip"', grid_template_rows="1fr 6px"),
        "name": css(
            font_size="15px",
            align_self="end",
            font_weight="[[[ return variables.dag.today || variables.dag.selected ? '700' : '400'; ]]]",
            color="[[[ return variables.dag.info?.dose ? '#fff' : 'var(--primary-text-color)'; ]]]",
        ),
        "custom_fields": {"stip": css(align_self="start")},
    },
}


month_grid = {
    "type": "custom:stack-in-card",
    "mode": "vertical",
    "cards": [
        month_header,
        {
            "type": "grid",
            "columns": 7,
            "square": False,
            "cards": [
                {"type": "custom:button-card", "template": "glp1_dag", "variables": {"cel": i}} for i in range(42)
            ],
        },
    ],
}

day_card = {
    "type": "custom:button-card",
    "template": "glp1_kaart",
    "entity": "sensor.@P_dagoverzicht",
    "icon": "mdi:calendar-text",
    "name": js(
        """
const a = states['sensor.@P_dagoverzicht']?.attributes || {};
if (!a.date) return '';
const [y, m, d] = a.date.split('-').map(Number);
const text = new Date(y, m - 1, d).toLocaleDateString('nl-NL', {weekday: 'long', day: 'numeric', month: 'long'});
return a.is_today ? `Vandaag, ${text.split(' ').slice(1).join(' ')}` : text.charAt(0).toUpperCase() + text.slice(1);
"""
    ),
    "label": js(
        """
const a = states['sensor.@P_dagoverzicht']?.attributes || {};
const n = Object.keys(a.side_effects || {}).length;
return n ? `${n} ${n === 1 ? 'bijwerking' : 'bijwerkingen'} genoteerd` : 'Geen bijwerkingen genoteerd';
"""
    ),
    "custom_fields": {
        "tegels": js(
            """
const a = states['sensor.@P_dagoverzicht']?.attributes || {};
const tile = (icon, color, label, value, wide) => `<div style="padding:10px 12px;border-radius:14px;background:color-mix(in srgb, var(--primary-text-color) 5%, transparent);text-align:left;${wide ? 'grid-column:span 2' : ''}">
<div style="display:flex;align-items:center;gap:6px;font-size:12px;${sub}"><ha-icon icon="${icon}" style="--mdc-icon-size:16px;color:${color}"></ha-icon>${label}</div>
<div style="font-size:16px;font-weight:600;margin-top:6px;white-space:normal">${value}</div></div>`;
const inj = (a.injections || []).map((i) => `${pil(i.dose)} <span style="font-size:12.5px;font-weight:400;${sub}">${tijd(i.time)}${i.site ? ' · ' + i.site : ''}</span>`).join('<br>') || '—';
return `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
${tile('mdi:needle', 'var(--primary-color)', 'Injectie', inj, true)}
${tile('mdi:chart-bell-curve-cumulative', 'ACCENT', 'Gesch. niveau', `${nl(states['sensor.@P_dagoverzicht']?.state, 2)} mg`)}
${tile('mdi:scale-bathroom', '#F5B82E', 'Gewicht', a.weight ? `${nl(a.weight, 1)} kg` : '—')}
${tile('mdi:food-apple', '#F97316', 'Calorieën', a.calories ? `${Math.round(a.calories)} kcal` : '—')}
${tile('mdi:food-steak', '#EF4444', 'Eiwitten', a.protein ? `${Math.round(a.protein)} g` : '—')}
</div>`;
""".replace("ACCENT", ACCENT)
        )
    },
    "styles": {
        "grid": css(
            grid_template_areas='"i n" "i l" "tegels tegels"',
            grid_template_columns="44px 1fr",
            grid_template_rows="auto auto auto",
            column_gap="12px",
        ),
        "name": css(text_transform="none"),
        "custom_fields": {"tegels": css(justify_self="stretch", margin_top="12px")},
    },
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


BIJWERKING_TEMPLATE = {
    "template": "glp1_rij",
    "icon": "mdi:emoticon-sick-outline",
    "label": js(
        """
const v = Number(entity?.state) || 0;
const words = ['Geen', 'Licht', 'Licht', 'Licht', 'Matig', 'Matig', 'Matig', 'Ernstig', 'Ernstig', 'Ernstig', 'Heel ernstig'];
const dots = Array.from({length: 10}, (_, k) => `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:3px;background:${k < v ? (v >= 7 ? 'var(--error-color, #e45649)' : (v >= 4 ? '#F5B82E' : 'var(--success-color, #4caf50)')) : 'color-mix(in srgb, var(--primary-text-color) 15%, transparent)'}"></span>`).join('');
return `${words[Math.round(v)]}${v ? ' · ' + v + '/10' : ''}<div style="margin-top:5px">${dots}</div>`;
"""
    ),
    "tap_action": {"action": "more-info"},
    "styles": {
        "img_cell": [
            {
                "background": "[[[ const v = Number(entity?.state) || 0; return v >= 7 ? 'color-mix(in srgb, var(--error-color, #e45649) 18%, transparent)' : (v >= 4 ? 'color-mix(in srgb, #F5B82E 22%, transparent)' : (v > 0 ? 'color-mix(in srgb, var(--success-color, #4caf50) 18%, transparent)' : 'color-mix(in srgb, var(--primary-text-color) 8%, transparent)')); ]]]"
            }
        ],
        "icon": [
            {
                "color": "[[[ const v = Number(entity?.state) || 0; return v >= 7 ? 'var(--error-color, #e45649)' : (v >= 4 ? '#F5B82E' : (v > 0 ? 'var(--success-color, #4caf50)' : 'var(--secondary-text-color)')); ]]]"
            }
        ],
    },
}


def side_effect_row(name: str) -> dict:
    entity = f"number.@P_bijwerking_{slug(name)}"
    return {
        "type": "custom:button-card",
        "template": "glp1_bijwerking",
        "entity": entity,
        "name": name,
        "custom_fields": {
            "right": {
                "card": {
                    "type": "custom:button-card",
                    "show_icon": False,
                    "show_name": False,
                    "show_state": False,
                    "custom_fields": stepper(entity, 1, 0, 10),
                    "styles": {
                        "card": css(padding="0", background="none", box_shadow="none", border="none"),
                        "grid": css(
                            grid_template_areas='"minus plus"', grid_template_columns="44px 44px", column_gap="8px"
                        ),
                    },
                }
            }
        },
    }


side_effects_card = {
    "type": "custom:stack-in-card",
    "mode": "vertical",
    "cards": [
        {
            "type": "heading",
            "heading": "Bijwerkingen",
            "heading_style": "subtitle",
            "icon": "mdi:emoticon-sick-outline",
        },
        *[side_effect_row(name) for name in SIDE_EFFECTS],
    ],
}

food_card = {
    "type": "grid",
    "columns": 2,
    "square": False,
    "cards": [
        {
            "type": "tile",
            "entity": "number.@P_calorieen",
            "name": "Calorieën",
            "features": [{"type": "numeric-input", "style": "buttons"}],
            "features_position": "bottom",
        },
        {
            "type": "tile",
            "entity": "number.@P_eiwitten",
            "name": "Eiwitten",
            "features": [{"type": "numeric-input", "style": "buttons"}],
            "features_position": "bottom",
        },
    ],
}

note_card = {
    "type": "entities",
    "entities": [{"entity": "text.@P_dagnotitie", "name": "Notitie voor de dag"}],
}

# ----- Instellingen -----------------------------------------------------------


def value_row(
    entity: str, icon: str, name: str, label: str, unit: str, step: float, minimum: float, maximum: float, decimals: int
) -> dict:
    """A setting with -/+ buttons. ``decimals`` 0 shows the value without trailing zeros."""
    shown = "dosis(v)" if decimals == 0 else f"nl(v, {decimals})"
    return {
        "type": "custom:button-card",
        "template": "glp1_rij",
        "entity": entity,
        "icon": icon,
        "name": name,
        "label": label,
        "tap_action": {"action": "more-info"},
        "custom_fields": {
            "right": {
                "card": {
                    "type": "custom:button-card",
                    "entity": entity,
                    "show_icon": False,
                    "show_name": False,
                    "show_state": False,
                    "custom_fields": {
                        "val": js(
                            f"const v = num('{entity}'); return v === null ? '—' : `${{{shown}}}<span style=\"font-size:12px;font-weight:500;${{sub}}\"> {unit}</span>`;"
                        ),
                        **stepper(entity, step, minimum, maximum),
                    },
                    "styles": {
                        "card": css(padding="0", background="none", box_shadow="none", border="none"),
                        "grid": css(
                            grid_template_areas='"val minus plus"',
                            grid_template_columns="auto 44px 44px",
                            column_gap="8px",
                        ),
                        "custom_fields": {
                            "val": css(font_size="18px", font_weight="700", margin_right="4px", white_space="nowrap")
                        },
                    },
                }
            }
        },
    }


settings_cards = [
    value_row(
        "number.@P_interval",
        "mdi:calendar-sync",
        "Dagen tussen injecties",
        "Plant de volgende na de vorige",
        "d",
        0.5,
        1,
        28,
        0,
    ),
    value_row(
        "number.@P_doelgewicht", "mdi:flag", "Doelgewicht", "Voor 'Naar doel' en de voortgang", "kg", 0.5, 0, 400, 1
    ),
    value_row(
        "number.@P_startgewicht", "mdi:flag-outline", "Startgewicht", "Standaard je eerste meting", "kg", 0.5, 0, 400, 1
    ),
    {
        "type": "tile",
        "entity": "datetime.@P_volgende_injectie",
        "name": "Volgende injectie handmatig",
        "icon": "mdi:calendar-edit",
        "tap_action": {"action": "more-info"},
    },
    {
        "type": "tile",
        "entity": REMINDER,
        "name": "Herinnering op iPhone",
        "icon": "mdi:bell-ring-outline",
        "features": [{"type": "toggle"}],
        "features_position": "inline",
    },
    {
        "type": "custom:button-card",
        "template": "glp1_rij",
        "icon": "mdi:cog-outline",
        "name": "Meer instellingen",
        "label": "Prikplekken, bijwerkingen, vaste weekdag, sensoren",
        "tap_action": {"action": "navigate", "navigation_path": "/config/integrations/integration/glp1_tracker"},
        "custom_fields": {
            "right": '<ha-icon icon="mdi:chevron-right" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>'
        },
    },
    {
        "type": "custom:expander-card",
        "expanded": False,
        "title-card-button-overlay": True,
        "padding": "0px",
        "title-card-padding": "0px",
        "child-padding": "0px 16px 14px 16px",
        "gap": "0px",
        "title-card": {
            "type": "custom:button-card",
            "template": "glp1_rij",
            "icon": "mdi:help-circle-outline",
            "name": "Hoe werkt het?",
            "label": "Niveau, planning, gewicht en je gegevens",
            "tap_action": {"action": "none"},
            "styles": {"card": [{"background": "none"}, {"box-shadow": "none"}, {"border": "none"}]},
        },
        "cards": [
            {
                "type": "markdown",
                "text_only": True,
                "content": (
                    "**Niveau.** Per injectie telt een curve die na ongeveer anderhalve dag piekt en daarna met een "
                    "halfwaardetijd van ongeveer {{ state_attr('sensor.@P_medicatieniveau', 'half_life_days') }} dagen afneemt. "
                    "Alle injecties samen geven het geschatte niveau. Voor retatrutide is de curve afgeleid van je "
                    "Shotsy-export, zodat de getallen vrijwel gelijk zijn. Het is een schatting, geen bloedwaarde.\n\n"
                    "**Planning.** De volgende injectie komt het aantal dagen na de vorige, of op de vaste weekdag als "
                    "die is ingesteld. Met *Datum en tijd* zet je hem eenmalig anders. Na een registratie gaat de "
                    "planning weer vanzelf.\n\n"
                    "**Prikplek.** Standaard de plek die het langst niet is gebruikt.\n\n"
                    "**Gewicht.** Elke nieuwe waarde van je gewichtsensor wordt bewaard, ook als Home Assistant "
                    "de geschiedenis al heeft opgeruimd.\n\n"
                    "**Gegevens.** Alles staat lokaal in Home Assistant. Back-up via de actie *Gegevens exporteren*."
                ),
            }
        ],
    },
]

# ----- dashboard -------------------------------------------------------------


def build(prefix: str, health_prefix: str | None = None) -> dict:
    tabs = [
        {
            "title": "Overzicht",
            "icon": "mdi:clipboard-text-outline",
            "cards": [next_card, level_card, level_chart, summary_card],
        },
        {"title": "Injecties", "icon": "mdi:needle", "cards": [plan_card, site_card, history_recent, history_all]},
        {
            "title": "Resultaten",
            "icon": "mdi:chart-bar",
            "cards": [range_buttons, stats_card, weight_chart, progress_card, dose_stats_card]
            + ([health_card(health_prefix)] if health_prefix else []),
        },
        {
            "title": "Agenda",
            "icon": "mdi:calendar-month",
            "cards": [month_grid, day_card, side_effects_card, food_card, note_card],
        },
        {"title": "Instellingen", "icon": "mdi:cog", "cards": settings_cards},
    ]
    config = {
        "title": "Medicatie",
        "button_card_templates": {
            **TEMPLATES,
            "glp1_dag": DAY_TEMPLATE,
            "glp1_plek": PLEK_TEMPLATE,
            "glp1_bijwerking": BIJWERKING_TEMPLATE,
        },
        "views": [
            {
                "title": "Medicatie",
                "path": "medicatie",
                "icon": "mdi:needle",
                "type": "sections",
                "max_columns": 1,
                "badges": [],
                "sections": [
                    {
                        "type": "grid",
                        "cards": [
                            {"type": "heading", "heading": "Retatrutide", "icon": "mdi:needle"},
                            {
                                "type": "custom:simple-tabs",
                                "tabs_alignment": "start",
                                "remember_tab": True,
                                "tabs": tabs,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    text = json.dumps(config, ensure_ascii=False).replace("@P", prefix)
    return json.loads(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="retatrutide", help="entity ID prefix: the medication name as a slug")
    parser.add_argument(
        "--health-prefix",
        help="companion app sensor prefix for the health card, e.g. sensor.iphone_van_jan (leave out to skip the card)",
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument("--yaml", type=Path)
    args = parser.parse_args()
    config = build(args.prefix, args.health_prefix)
    config["views"][0]["sections"][0]["cards"][0]["heading"] = args.prefix.replace("_", " ").title()
    if args.json:
        args.json.write_text(json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.yaml:
        import yaml  # noqa: PLC0415 - only needed for this output

        class Dumper(yaml.SafeDumper):
            pass

        def text(dumper, data):
            style = "|" if "\n" in data else None
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

        Dumper.add_representer(str, text)
        args.yaml.write_text(
            yaml.dump(config, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
