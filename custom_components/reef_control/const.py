"""Constants for Reef Control."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DOMAIN = "reef_control"
VERSION = "0.12.2"

DEFAULT_AQUARIUM_NAME = "My Reef"

CONF_AQUARIUM_NAME = "aquarium_name"
CONF_VOLUME = "volume"
CONF_TANK_TYPE = "tank_type"
CONF_SUPPLY_SYSTEM = "supply_system"
CONF_REEF_METHOD = "reef_method"

DEFAULT_TANK_TYPE = "mixed_reef"
DEFAULT_SUPPLY_SYSTEM = "none"
DEFAULT_REEF_METHOD = "none"

CONF_PROFILE_TITLE_SYNC_PENDING = "_profile_title_sync_pending"

PROFILE_OPTION_KEYS = (
    CONF_AQUARIUM_NAME,
    CONF_VOLUME,
    CONF_TANK_TYPE,
    CONF_SUPPLY_SYSTEM,
    CONF_REEF_METHOD,
)


def get_profile_value(entry: Any, key: str, default: Any = None) -> Any:
    """Read an editable aquarium-profile value.

    v0.12.2 stores profile edits in config-entry options so existing aquariums can
    be changed without creating a new config entry. The original config data is
    kept as a fallback for installations created before v0.12.2.
    """
    if key in entry.options:
        return entry.options.get(key, default)
    return entry.data.get(key, default)


def get_aquarium_name(entry: Any) -> str:
    """Return the current display name without changing the config-entry ID."""
    value = get_profile_value(entry, CONF_AQUARIUM_NAME, DEFAULT_AQUARIUM_NAME)
    return str(value or DEFAULT_AQUARIUM_NAME).strip() or DEFAULT_AQUARIUM_NAME

CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_PH_ENTITY = "ph_entity"
CONF_SALINITY_ENTITY = "salinity_entity"
CONF_CONDUCTIVITY_ENTITY = "conductivity_entity"
CONF_REDOX_ENTITY = "redox_entity"
CONF_SALINITY_SOURCE = "salinity_source"
CONF_WATER_LEVEL_ENTITY = "water_level_entity"
CONF_LEAK_ENTITY = "leak_entity"

# Water-level monitoring
CONF_WATER_LEVEL_MODE = "water_level_mode"
CONF_WATER_LEVEL_LOW_CM = "water_level_low_cm"
CONF_WATER_LEVEL_HIGH_CM = "water_level_high_cm"
DEFAULT_WATER_LEVEL_MODE = "auto"
DEFAULT_WATER_LEVEL_LOW_CM = 15.0
DEFAULT_WATER_LEVEL_HIGH_CM = 25.0

# Alarm system
EVENT_ALARM = "reef_control_alarm"
EVENT_ALARM_CLEARED = "reef_control_alarm_cleared"

CONF_REEF_ICP_ENTRY = "reef_icp_entry"
REEF_ICP_DOMAIN = "reef_icp"

CONF_TEMPERATURE_MIN = "temperature_min"
CONF_TEMPERATURE_MAX = "temperature_max"
CONF_TEMPERATURE_CRITICAL_MIN = "temperature_critical_min"
CONF_TEMPERATURE_CRITICAL_MAX = "temperature_critical_max"
CONF_PH_MIN = "ph_min"
CONF_PH_MAX = "ph_max"
CONF_PH_CRITICAL_MIN = "ph_critical_min"
CONF_PH_CRITICAL_MAX = "ph_critical_max"
CONF_SALINITY_MIN = "salinity_min"
CONF_SALINITY_MAX = "salinity_max"
CONF_SALINITY_CRITICAL_MIN = "salinity_critical_min"
CONF_SALINITY_CRITICAL_MAX = "salinity_critical_max"
CONF_REDOX_MIN = "redox_min"
CONF_REDOX_MAX = "redox_max"
CONF_REDOX_CRITICAL_MIN = "redox_critical_min"
CONF_REDOX_CRITICAL_MAX = "redox_critical_max"

DEFAULT_TEMPERATURE_MIN = 24.0
DEFAULT_TEMPERATURE_MAX = 28.0
DEFAULT_TEMPERATURE_CRITICAL_MIN = 22.0
DEFAULT_TEMPERATURE_CRITICAL_MAX = 30.0
DEFAULT_PH_MIN = 7.8
DEFAULT_PH_MAX = 8.5
DEFAULT_PH_CRITICAL_MIN = 7.5
DEFAULT_PH_CRITICAL_MAX = 8.7
DEFAULT_SALINITY_MIN = 33.0
DEFAULT_SALINITY_MAX = 36.0
DEFAULT_SALINITY_CRITICAL_MIN = 30.0
DEFAULT_SALINITY_CRITICAL_MAX = 39.0
DEFAULT_REDOX_MIN = 250.0
DEFAULT_REDOX_MAX = 450.0
DEFAULT_REDOX_CRITICAL_MIN = 150.0
DEFAULT_REDOX_CRITICAL_MAX = 500.0
DEFAULT_SALINITY_SOURCE = "auto"

# Legacy single-entity option keys. Kept for transparent migration/downgrade
# compatibility. New code stores and consumes the plural keys below.
CONF_SKIMMER_ENTITY = "skimmer_entity"
CONF_RETURN_PUMP_ENTITY = "return_pump_entity"
CONF_FLOW_PUMP_ENTITY = "flow_pump_entity"
CONF_UVC_ENTITY = "uvc_entity"
CONF_LIGHT_ENTITY = "light_entity"
CONF_HEATER_ENTITY = "heater_entity"
CONF_ATO_ENTITY = "ato_entity"

# Multi-entity equipment option keys (v0.12.1+)
CONF_SKIMMER_ENTITIES = "skimmer_entities"
CONF_RETURN_PUMP_ENTITIES = "return_pump_entities"
CONF_FLOW_PUMP_ENTITIES = "flow_pump_entities"
CONF_UVC_ENTITIES = "uvc_entities"
CONF_LIGHT_ENTITIES = "light_entities"
CONF_HEATER_ENTITIES = "heater_entities"
CONF_ATO_ENTITIES = "ato_entities"
CONF_LEAK_ENTITIES = "leak_entities"
CONF_CALCIUM_REACTOR_ENTITIES = "calcium_reactor_entities"


# Adaptive system modules (v0.12.2+)
CONF_REFUGIUM_MODULE_ENABLED = "refugium_module_enabled"
CONF_REFUGIUM_LIGHT_ENTITIES = "refugium_light_entities"
CONF_REFUGIUM_PUMP_ENTITIES = "refugium_pump_entities"
CONF_REFUGIUM_LIGHT_START = "refugium_light_start"
CONF_REFUGIUM_LIGHT_END = "refugium_light_end"
DEFAULT_REFUGIUM_MODULE_ENABLED = False
DEFAULT_REFUGIUM_LIGHT_START = "20:00:00"
DEFAULT_REFUGIUM_LIGHT_END = "08:00:00"

CONF_DOSING_MODULE_ENABLED = "dosing_module_enabled"
CONF_DOSING_PUMP_ENTITIES = "dosing_pump_entities"
CONF_TRACE_DOSING_ENTITIES = "trace_dosing_entities"
DEFAULT_DOSING_MODULE_ENABLED = False

CONF_CALCIUM_REACTOR_MODULE_ENABLED = "calcium_reactor_module_enabled"
CONF_CALCIUM_REACTOR_PH_ENTITY = "calcium_reactor_ph_entity"
CONF_CALCIUM_REACTOR_CO2_ENTITY = "calcium_reactor_co2_entity"
DEFAULT_CALCIUM_REACTOR_MODULE_ENABLED = False

DOSING_SUPPLY_SYSTEMS = {
    "fauna_marin_balling_light",
    "ati_essentials",
    "oceamo_duo",
    "triton",
}


def recommended_modules(
    reef_method: str | None,
    supply_system: str | None,
    calcium_reactor_configured: bool = False,
) -> list[str]:
    """Return adaptive module recommendations for the selected aquarium profile."""
    method = str(reef_method or DEFAULT_REEF_METHOD)
    supply = str(supply_system or DEFAULT_SUPPLY_SYSTEM)
    result: list[str] = []

    if method == "triton" or supply == "triton":
        result.extend(("refugium", "reef_icp"))

    if supply in DOSING_SUPPLY_SYSTEMS or method == "dsr":
        result.append("dosing")

    if supply == "calcium_reactor" or calcium_reactor_configured:
        result.append("calcium_reactor")

    return list(dict.fromkeys(result))

EQUIPMENT_ENTITY_OPTION_PAIRS = (
    (CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY),
    (CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY),
    (CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY),
    (CONF_UVC_ENTITIES, CONF_UVC_ENTITY),
    (CONF_LIGHT_ENTITIES, CONF_LIGHT_ENTITY),
    (CONF_HEATER_ENTITIES, CONF_HEATER_ENTITY),
    (CONF_ATO_ENTITIES, CONF_ATO_ENTITY),
    (CONF_LEAK_ENTITIES, CONF_LEAK_ENTITY),
)


def _normalize_entity_values(raw: Any) -> list[str]:
    """Return a stable, de-duplicated list of entity IDs."""
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        entity_id = value.strip()
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        result.append(entity_id)
    return result


def get_entity_list(
    options: Mapping[str, Any], plural_key: str, legacy_key: str | None = None
) -> list[str]:
    """Read an equipment group, with fallback to a legacy single entity."""
    if plural_key in options:
        return _normalize_entity_values(options.get(plural_key))
    if legacy_key:
        return _normalize_entity_values(options.get(legacy_key))
    return []


def get_first_entity(
    options: Mapping[str, Any], plural_key: str, legacy_key: str | None = None
) -> str | None:
    """Return the first configured entity in a group."""
    values = get_entity_list(options, plural_key, legacy_key)
    return values[0] if values else None


def sync_legacy_entity_options(options: dict[str, Any]) -> dict[str, Any]:
    """Mirror each new equipment list to its old single-entity option key.

    This keeps existing dashboard/card code and older Reef Control versions usable
    with the first selected device while v0.12.1+ uses the full list.
    """
    for plural_key, legacy_key in EQUIPMENT_ENTITY_OPTION_PAIRS:
        if plural_key not in options:
            legacy = _normalize_entity_values(options.get(legacy_key))
            if legacy:
                options[plural_key] = legacy

        values = _normalize_entity_values(options.get(plural_key))
        options[plural_key] = values
        if values:
            options[legacy_key] = values[0]
        else:
            options.pop(legacy_key, None)
    return options


CONF_TEMPERATURE_CONTROL_ENABLED = "temperature_control_enabled"
CONF_TEMPERATURE_TARGET = "temperature_target"
CONF_TEMPERATURE_HYSTERESIS = "temperature_hysteresis"
CONF_TEMPERATURE_MIN_ON_TIME = "temperature_min_on_time"
CONF_TEMPERATURE_MIN_OFF_TIME = "temperature_min_off_time"
DEFAULT_TEMPERATURE_CONTROL_ENABLED = False
DEFAULT_TEMPERATURE_TARGET = 25.0
DEFAULT_TEMPERATURE_HYSTERESIS = 0.3
DEFAULT_TEMPERATURE_MIN_ON_TIME = 2
DEFAULT_TEMPERATURE_MIN_OFF_TIME = 2

CONF_ATO_CONTROL_ENABLED = "ato_control_enabled"
CONF_ATO_LOW_STATE = "ato_low_state"
CONF_ATO_CONFIRM_DELAY = "ato_confirm_delay"
CONF_ATO_MAX_RUNTIME = "ato_max_runtime"
CONF_ATO_COOLDOWN = "ato_cooldown"
DEFAULT_ATO_CONTROL_ENABLED = False
DEFAULT_ATO_LOW_STATE = "on"
DEFAULT_ATO_CONFIRM_DELAY = 3
DEFAULT_ATO_MAX_RUNTIME = 60
DEFAULT_ATO_COOLDOWN = 2

CONF_EQUIPMENT_CONTROL_ENABLED = "equipment_control_enabled"
CONF_RETURN_MASTER_SKIMMER = "return_master_skimmer"
CONF_RETURN_MASTER_UVC = "return_master_uvc"
CONF_RETURN_MASTER_ATO = "return_master_ato"
CONF_EQUIPMENT_SKIMMER_DELAY = "equipment_skimmer_delay"
CONF_EQUIPMENT_UVC_DELAY = "equipment_uvc_delay"
DEFAULT_EQUIPMENT_CONTROL_ENABLED = False
DEFAULT_RETURN_MASTER_SKIMMER = True
DEFAULT_RETURN_MASTER_UVC = True
DEFAULT_RETURN_MASTER_ATO = True
DEFAULT_EQUIPMENT_SKIMMER_DELAY = 5
DEFAULT_EQUIPMENT_UVC_DELAY = 1

CONF_RETURN_MASTER_FLOW = "return_master_flow"
CONF_EQUIPMENT_FLOW_DELAY = "equipment_flow_delay"
DEFAULT_RETURN_MASTER_FLOW = False
DEFAULT_EQUIPMENT_FLOW_DELAY = 0

CONF_SAFETY_CONTROL_ENABLED = "safety_control_enabled"
CONF_SAFETY_HEATER_HIGH_TEMP = "safety_heater_high_temp"
CONF_SAFETY_HEATER_SENSOR_FAIL = "safety_heater_sensor_fail"
DEFAULT_SAFETY_CONTROL_ENABLED = True
DEFAULT_SAFETY_HEATER_HIGH_TEMP = True
DEFAULT_SAFETY_HEATER_SENSOR_FAIL = True

# Leak protection
CONF_LEAK_ACTIVE_STATE = "leak_active_state"
CONF_SAFETY_LEAK_SHUTDOWN = "safety_leak_shutdown"
CONF_SAFETY_LEAK_RETURN_PUMP = "safety_leak_return_pump"
CONF_SAFETY_LEAK_SKIMMER = "safety_leak_skimmer"
CONF_SAFETY_LEAK_UVC = "safety_leak_uvc"
CONF_SAFETY_LEAK_ATO = "safety_leak_ato"
CONF_SAFETY_LEAK_HEATER = "safety_leak_heater"
DEFAULT_LEAK_ACTIVE_STATE = "on"
DEFAULT_SAFETY_LEAK_SHUTDOWN = True
DEFAULT_SAFETY_LEAK_RETURN_PUMP = True
DEFAULT_SAFETY_LEAK_SKIMMER = True
DEFAULT_SAFETY_LEAK_UVC = True
DEFAULT_SAFETY_LEAK_ATO = True
DEFAULT_SAFETY_LEAK_HEATER = True

# UV-C control
CONF_UVC_CONTROL_ENABLED = "uvc_control_enabled"
CONF_UVC_MODE = "uvc_mode"
CONF_UVC_START_TIME = "uvc_start_time"
CONF_UVC_END_TIME = "uvc_end_time"
DEFAULT_UVC_CONTROL_ENABLED = False
DEFAULT_UVC_MODE = "continuous"
DEFAULT_UVC_START_TIME = "08:00:00"
DEFAULT_UVC_END_TIME = "20:00:00"

CONF_FEEDING_DURATION = "feeding_duration"
CONF_SKIMMER_DELAY = "skimmer_delay"
CONF_FEEDING_PAUSE_SKIMMER = "feeding_pause_skimmer"
CONF_FEEDING_PAUSE_RETURN_PUMP = "feeding_pause_return_pump"
CONF_FEEDING_PAUSE_FLOW_PUMP = "feeding_pause_flow_pump"
CONF_FEEDING_PAUSE_UVC = "feeding_pause_uvc"
CONF_FEEDING_PAUSE_ATO = "feeding_pause_ato"
CONF_FEEDING_PAUSE_CALCIUM_REACTOR = "feeding_pause_calcium_reactor"
DEFAULT_FEEDING_DURATION = 10
DEFAULT_SKIMMER_DELAY = 5

CONF_MAINTENANCE_PAUSE_SKIMMER = "maintenance_pause_skimmer"
CONF_MAINTENANCE_PAUSE_RETURN_PUMP = "maintenance_pause_return_pump"
CONF_MAINTENANCE_PAUSE_FLOW_PUMP = "maintenance_pause_flow_pump"
CONF_MAINTENANCE_PAUSE_UVC = "maintenance_pause_uvc"
CONF_MAINTENANCE_PAUSE_ATO = "maintenance_pause_ato"
CONF_MAINTENANCE_PAUSE_HEATER = "maintenance_pause_heater"
CONF_MAINTENANCE_PAUSE_LIGHT = "maintenance_pause_light"
CONF_MAINTENANCE_PAUSE_CALCIUM_REACTOR = "maintenance_pause_calcium_reactor"

# TC420 / SIMU-LUX SEA WATER lighting bridge
TC420_CHANNEL_COUNT = 4

MANUAL_MEASUREMENTS = {
    "kh": {"name": "KH", "icon": "mdi:flask-outline", "unit": "dKH", "min": 0.0, "max": 20.0, "step": 0.1},
    "calcium": {"name": "Calcium", "icon": "mdi:flask-outline", "unit": "mg/L", "min": 0.0, "max": 1000.0, "step": 1.0},
    "magnesium": {"name": "Magnesium", "icon": "mdi:flask-outline", "unit": "mg/L", "min": 0.0, "max": 2500.0, "step": 1.0},
    "nitrate": {"name": "Nitrat", "icon": "mdi:flask-outline", "unit": "mg/L", "min": 0.0, "max": 200.0, "step": 0.1},
    "phosphate": {"name": "Phosphat", "icon": "mdi:flask-outline", "unit": "mg/L", "min": 0.0, "max": 10.0, "step": 0.01},
}

PLATFORMS = ["sensor", "switch", "number", "binary_sensor"]
