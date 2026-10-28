"""Constants for the GLP-1 Tracker integration."""

from __future__ import annotations

DOMAIN = "glp1_tracker"
STORAGE_VERSION = 1

CONF_MEDICATION = "medication"
CONF_NAME = "name"
CONF_WEIGHT_ENTITY = "weight_entity"
CONF_HEIGHT_ENTITY = "height_entity"
CONF_HEIGHT_CM = "height_cm"
CONF_INTERVAL_DAYS = "interval_days"
CONF_DEFAULT_DOSE = "default_dose"
CONF_SITES = "sites"
CONF_SIDE_EFFECTS = "side_effects"
CONF_HALF_LIFE = "half_life_days"
CONF_TMAX_HOURS = "tmax_hours"
CONF_WEEKDAY = "weekday"
CONF_INJECTION_TIME = "injection_time"

MEDICATION_CUSTOM = "custom"
MEDICATIONS = ["retatrutide", "tirzepatide", "semaglutide", MEDICATION_CUSTOM]
MEDICATION_NAMES = {
    "retatrutide": "Retatrutide",
    "tirzepatide": "Tirzepatide",
    "semaglutide": "Semaglutide",
    MEDICATION_CUSTOM: "Medicatie",
}

DEFAULT_INTERVAL_DAYS = 7
DEFAULT_HALF_LIFE = 6.0
DEFAULT_TMAX_HOURS = 36.0

ALL_SITES = [
    "Buik - Links Boven",
    "Buik - Midden Boven",
    "Buik - Rechts Boven",
    "Buik - Links Midden",
    "Buik - Rechts Midden",
    "Buik - Links Onder",
    "Buik - Midden Onder",
    "Buik - Rechts Onder",
    "Dij - Links",
    "Dij - Rechts",
    "Arm - Links",
    "Arm - Rechts",
    "Bil - Links",
    "Bil - Rechts",
]
DEFAULT_SITES = [
    "Buik - Links Boven",
    "Buik - Midden Boven",
    "Buik - Rechts Boven",
    "Buik - Links Onder",
    "Buik - Midden Onder",
    "Buik - Rechts Onder",
]

# Site names as they appear in a Shotsy CSV export.
SHOTSY_SITES = {
    "stomach - upper left": "Buik - Links Boven",
    "stomach - upper mid": "Buik - Midden Boven",
    "stomach - upper right": "Buik - Rechts Boven",
    "stomach - left mid": "Buik - Links Midden",
    "stomach - right mid": "Buik - Rechts Midden",
    "stomach - lower left": "Buik - Links Onder",
    "stomach - lower mid": "Buik - Midden Onder",
    "stomach - lower right": "Buik - Rechts Onder",
    "thigh - left": "Dij - Links",
    "thigh - right": "Dij - Rechts",
    "arm - left": "Arm - Links",
    "arm - right": "Arm - Rechts",
    "buttock - left": "Bil - Links",
    "buttock - right": "Bil - Rechts",
}

DEFAULT_SIDE_EFFECTS = [
    "Food Noise",
    "Misselijkheid",
    "Brandend maagzuur",
    "Verminderde eetlust",
    "Vermoeidheid",
    "Constipatie",
]
SIDE_EFFECT_MAX = 10

CHART_RANGES = ["1m", "3m", "6m", "all"]
# "none" plans by interval only; "0" is Monday.
WEEKDAY_OPTIONS = ["none", "0", "1", "2", "3", "4", "5", "6"]

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_INJECTION_ID = "injection_id"
ATTR_DOSE = "dose_mg"
ATTR_TIME = "time"
ATTR_SITE = "site"
ATTR_PAIN = "pain"
ATTR_NOTES = "notes"
ATTR_DATE = "date"
ATTR_SIDE_EFFECTS = "side_effects"
ATTR_CALORIES = "calories"
ATTR_PROTEIN = "protein"
ATTR_WEIGHT = "weight_kg"
ATTR_FILE_PATH = "file_path"
ATTR_CSV_TEXT = "csv_text"
ATTR_REPLACE = "replace"

SERVICE_LOG_INJECTION = "log_injection"
SERVICE_UPDATE_INJECTION = "update_injection"
SERVICE_DELETE_INJECTION = "delete_injection"
SERVICE_LOG_DAY = "log_day"
SERVICE_LOG_WEIGHT = "log_weight"
SERVICE_IMPORT_SHOTSY = "import_shotsy_csv"
SERVICE_EXPORT_DATA = "export_data"

UPDATE_INTERVAL_MINUTES = 10
