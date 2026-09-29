"""Sensor platform for Reef Control."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_interval

from .const import *


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            ReefControlAquariumSensor(entry),
            ReefControlOperatingStatusSensor(hass, entry),
            ReefControlTemperatureControlStatusSensor(hass, entry),
            ReefControlRemainingTimeSensor(hass, entry),
            ReefControlParameterStatusSensor(hass, entry, "temperature"),
            ReefControlParameterStatusSensor(hass, entry, "ph"),
            ReefControlParameterStatusSensor(hass, entry, "salinity"),
            ReefControlParameterStatusSensor(hass, entry, "redox"),
            ReefControlConductivitySensor(hass, entry),
            ReefControlIcpConnectionSensor(hass, entry),
            ReefControlIcpSensor(hass, entry),
            ReefControlWaterValuesSensor(hass, entry),
            ReefControlOverallStatusSensor(hass, entry),
            ReefControlActiveAlarmsSensor(hass, entry),
            ReefControlAtoStatisticsSensor(hass, entry),
            ReefControlWaterLevelSensor(hass, entry),
        ]
    )


class ReefControlBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry):
        self._entry = entry

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=get_aquarium_name(self._entry),
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )


class ReefControlAquariumSensor(ReefControlBaseSensor):
    _attr_icon = "mdi:fishbowl-outline"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_aquarium"
        self._attr_name = "Aquarium"

    @property
    def native_value(self):
        return get_aquarium_name(self._entry)

    @property
    def extra_state_attributes(self):
        options = self._entry.options
        groups = {
            "return_pumps": get_entity_list(
                options, CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY
            ),
            "skimmers": get_entity_list(
                options, CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY
            ),
            "flow_pumps": get_entity_list(
                options, CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY
            ),
            "uvc_devices": get_entity_list(
                options, CONF_UVC_ENTITIES, CONF_UVC_ENTITY
            ),
            "heaters": get_entity_list(
                options, CONF_HEATER_ENTITIES, CONF_HEATER_ENTITY
            ),
            "ato_pumps": get_entity_list(
                options, CONF_ATO_ENTITIES, CONF_ATO_ENTITY
            ),
            "lights": get_entity_list(
                options, CONF_LIGHT_ENTITIES, CONF_LIGHT_ENTITY
            ),
            "calcium_reactors": get_entity_list(
                options, CONF_CALCIUM_REACTOR_ENTITIES
            ),
            "leak_sensors": get_entity_list(
                options, CONF_LEAK_ENTITIES, CONF_LEAK_ENTITY
            ),
        }

        # Keep the old singular attributes for existing cards/automations while
        # exposing the complete v0.12.1 groups at the same time.
        equipment_entities = {
            **{key: value for key, value in groups.items() if value},
            "return_pump": groups["return_pumps"][0]
            if groups["return_pumps"]
            else None,
            "skimmer": groups["skimmers"][0] if groups["skimmers"] else None,
            "flow_pump": groups["flow_pumps"][0]
            if groups["flow_pumps"]
            else None,
            "uvc": groups["uvc_devices"][0] if groups["uvc_devices"] else None,
            "heater": groups["heaters"][0] if groups["heaters"] else None,
            "ato": groups["ato_pumps"][0] if groups["ato_pumps"] else None,
            "light": groups["lights"][0] if groups["lights"] else None,
            "leak": groups["leak_sensors"][0] if groups["leak_sensors"] else None,
        }
        equipment_entities = {
            key: value for key, value in equipment_entities.items() if value
        }

        volume = get_profile_value(self._entry, CONF_VOLUME, 1.0)
        tank_type = get_profile_value(
            self._entry, CONF_TANK_TYPE, DEFAULT_TANK_TYPE
        )
        supply_system = get_profile_value(
            self._entry, CONF_SUPPLY_SYSTEM, DEFAULT_SUPPLY_SYSTEM
        )
        reef_method = get_profile_value(
            self._entry, CONF_REEF_METHOD, DEFAULT_REEF_METHOD
        )

        recommendations = recommended_modules(
            reef_method,
            supply_system,
            bool(groups["calcium_reactors"])
            or bool(options.get(CONF_CALCIUM_REACTOR_PH_ENTITY))
            or bool(options.get(CONF_CALCIUM_REACTOR_CO2_ENTITY)),
        )

        refugium_lights = get_entity_list(
            options, CONF_REFUGIUM_LIGHT_ENTITIES
        )
        refugium_pumps = get_entity_list(
            options, CONF_REFUGIUM_PUMP_ENTITIES
        )
        dosing_pumps = get_entity_list(
            options, CONF_DOSING_PUMP_ENTITIES
        )
        trace_dosing = get_entity_list(
            options, CONF_TRACE_DOSING_ENTITIES
        )

        if refugium_lights:
            equipment_entities["refugium_lights"] = refugium_lights
        if refugium_pumps:
            equipment_entities["refugium_pumps"] = refugium_pumps

        system_modules = {
            "refugium": {
                "recommended": "refugium" in recommendations,
                "enabled": bool(
                    options.get(
                        CONF_REFUGIUM_MODULE_ENABLED,
                        DEFAULT_REFUGIUM_MODULE_ENABLED,
                    )
                ),
                "configured": bool(refugium_lights or refugium_pumps),
                "light_entities": refugium_lights,
                "pump_entities": refugium_pumps,
                "light_start": options.get(
                    CONF_REFUGIUM_LIGHT_START, DEFAULT_REFUGIUM_LIGHT_START
                ),
                "light_end": options.get(
                    CONF_REFUGIUM_LIGHT_END, DEFAULT_REFUGIUM_LIGHT_END
                ),
                "automatic_control": False,
            },
            "dosing": {
                "recommended": "dosing" in recommendations,
                "enabled": bool(
                    options.get(
                        CONF_DOSING_MODULE_ENABLED,
                        DEFAULT_DOSING_MODULE_ENABLED,
                    )
                ),
                "configured": bool(dosing_pumps or trace_dosing),
                "dosing_pump_entities": dosing_pumps,
                "trace_dosing_entities": trace_dosing,
                "automatic_control": False,
            },
            "calcium_reactor": {
                "recommended": "calcium_reactor" in recommendations,
                "enabled": bool(
                    options.get(
                        CONF_CALCIUM_REACTOR_MODULE_ENABLED,
                        DEFAULT_CALCIUM_REACTOR_MODULE_ENABLED,
                    )
                ),
                "configured": bool(
                    groups["calcium_reactors"]
                    or options.get(CONF_CALCIUM_REACTOR_PH_ENTITY)
                    or options.get(CONF_CALCIUM_REACTOR_CO2_ENTITY)
                ),
                "component_entities": groups["calcium_reactors"],
                "ph_entity": options.get(CONF_CALCIUM_REACTOR_PH_ENTITY),
                "co2_entity": options.get(CONF_CALCIUM_REACTOR_CO2_ENTITY),
                "automatic_co2_control": False,
            },
            "reef_icp": {
                "recommended": "reef_icp" in recommendations,
                "linked": bool(options.get(CONF_REEF_ICP_ENTRY)),
            },
        }

        return {
            "volume_l": volume,
            "tank_type": tank_type,
            "supply_system": supply_system,
            "reef_method": reef_method,
            "reef_control_version": VERSION,
            "equipment_entities": equipment_entities,
            "system_profile": {
                "aquarium_name": get_aquarium_name(self._entry),
                "volume_l": volume,
                "tank_type": tank_type,
                "supply_system": supply_system,
                "reef_method": reef_method,
            },
            "recommended_modules": recommendations,
            "system_modules": system_modules,
        }


class ReefControlRuntimeSensor(ReefControlBaseSensor):
    def __init__(self, hass, entry):
        super().__init__(entry)
        self.hass = hass
        self._remove_interval = None

    async def async_added_to_hass(self):
        @callback
        def _update(_now=None):
            self.async_write_ha_state()

        self._remove_interval = async_track_time_interval(
            self.hass, _update, timedelta(seconds=2)
        )

    async def async_will_remove_from_hass(self):
        if self._remove_interval:
            self._remove_interval()
            self._remove_interval = None

    def _runtime(self):
        return self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})


class ReefControlOperatingStatusSensor(ReefControlRuntimeSensor):
    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_status"
        self._attr_name = "Betriebsstatus"

    @property
    def native_value(self):
        runtime = self._runtime()
        if runtime.get("maintenance_active"):
            return "Wartung"
        if runtime.get("feeding_active"):
            return "Fütterung"

        ato_status = str(runtime.get("ato_control_status", "")).strip().lower()
        if ato_status in ("nachfüllen", "nachfullen", "refilling", "filling"):
            return "Nachfüllung"

        temp_status = str(runtime.get("temperature_control_status", "")).strip().lower()
        if temp_status in ("heizen", "heating", "heizbetrieb"):
            return "Heizbetrieb"

        until = runtime.get("skimmer_delay_until")
        if until and until > datetime.now().astimezone():
            return "Abschäumer-Verzögerung"
        return "Normalbetrieb"

    @property
    def icon(self):
        return {
            "Wartung": "mdi:tools",
            "Fütterung": "mdi:fish",
            "Nachfüllung": "mdi:water-plus",
            "Heizbetrieb": "mdi:radiator",
            "Abschäumer-Verzögerung": "mdi:timer-sand",
        }.get(self.native_value, "mdi:check-circle-outline")


class ReefControlTemperatureControlStatusSensor(ReefControlRuntimeSensor):
    _attr_name = "Temperaturregelung Status"
    _attr_icon = "mdi:thermostat"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_temperature_control_status"

    @property
    def native_value(self):
        return self._runtime().get("temperature_control_status", "Deaktiviert")

    @property
    def extra_state_attributes(self):
        controller = self._runtime().get("temperature_control_switch")
        return controller.extra_state_attributes if controller else {}


class ReefControlRemainingTimeSensor(ReefControlRuntimeSensor):
    _attr_icon = "mdi:timer-outline"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_remaining"
        self._attr_name = "Restzeit"

    @property
    def native_value(self):
        runtime = self._runtime()
        if runtime.get("maintenance_active"):
            return "00:00"
        target = (
            runtime.get("feeding_until")
            if runtime.get("feeding_active")
            else runtime.get("skimmer_delay_until")
        )
        if not target:
            return "00:00"
        remaining = max(
            0, int((target - datetime.now().astimezone()).total_seconds())
        )
        minutes, seconds = divmod(remaining, 60)
        return f"{minutes:02d}:{seconds:02d}"


PARAMS = {
    "temperature": (
        CONF_TEMPERATURE_ENTITY,
        "Temperatur",
        "mdi:thermometer",
        CONF_TEMPERATURE_MIN,
        CONF_TEMPERATURE_MAX,
        CONF_TEMPERATURE_CRITICAL_MIN,
        CONF_TEMPERATURE_CRITICAL_MAX,
        DEFAULT_TEMPERATURE_MIN,
        DEFAULT_TEMPERATURE_MAX,
        DEFAULT_TEMPERATURE_CRITICAL_MIN,
        DEFAULT_TEMPERATURE_CRITICAL_MAX,
    ),
    "ph": (
        CONF_PH_ENTITY,
        "pH",
        "mdi:ph",
        CONF_PH_MIN,
        CONF_PH_MAX,
        CONF_PH_CRITICAL_MIN,
        CONF_PH_CRITICAL_MAX,
        DEFAULT_PH_MIN,
        DEFAULT_PH_MAX,
        DEFAULT_PH_CRITICAL_MIN,
        DEFAULT_PH_CRITICAL_MAX,
    ),
    "salinity": (
        CONF_SALINITY_ENTITY,
        "Salinität",
        "mdi:waves",
        CONF_SALINITY_MIN,
        CONF_SALINITY_MAX,
        CONF_SALINITY_CRITICAL_MIN,
        CONF_SALINITY_CRITICAL_MAX,
        DEFAULT_SALINITY_MIN,
        DEFAULT_SALINITY_MAX,
        DEFAULT_SALINITY_CRITICAL_MIN,
        DEFAULT_SALINITY_CRITICAL_MAX,
    ),
    "redox": (
        CONF_REDOX_ENTITY,
        "Redox",
        "mdi:flash-outline",
        CONF_REDOX_MIN,
        CONF_REDOX_MAX,
        CONF_REDOX_CRITICAL_MIN,
        CONF_REDOX_CRITICAL_MAX,
        DEFAULT_REDOX_MIN,
        DEFAULT_REDOX_MAX,
        DEFAULT_REDOX_CRITICAL_MIN,
        DEFAULT_REDOX_CRITICAL_MAX,
    ),
}


def _state_number(hass, entity_id):
    if not entity_id:
        return None, None, None
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None, None, state
    try:
        return (
            float(str(state.state).replace(",", ".")),
            state.attributes.get("unit_of_measurement"),
            state,
        )
    except (TypeError, ValueError):
        return None, state.attributes.get("unit_of_measurement"), state


def _conductivity_ms_cm(value, unit):
    """Normalize conductivity to mS/cm."""
    if value is None:
        return None
    normalized = (
        str(unit or "")
        .replace("µ", "u")
        .replace("μ", "u")
        .replace(" ", "")
        .lower()
    )
    if normalized in ("us/cm", "uscm"):
        return value / 1000.0
    if normalized in ("s/cm", "scm"):
        return value * 1000.0
    return value


def _pss78_salinity(conductivity_ms_cm, temperature_c):
    """Practical Salinity (PSS-78) from conductivity at atmospheric pressure."""
    if conductivity_ms_cm is None or temperature_c is None:
        return None
    if conductivity_ms_cm <= 0 or not (-2.0 <= temperature_c <= 40.0):
        return None

    ratio = conductivity_ms_cm / 42.914
    temperature = temperature_c
    rt = (
        0.6766097
        + 0.0200564 * temperature
        + 0.0001104259 * temperature * temperature
        - 6.9698e-7 * temperature**3
        + 1.0031e-9 * temperature**4
    )
    if rt <= 0:
        return None
    rt_ratio = ratio / rt
    if rt_ratio <= 0:
        return None
    x = rt_ratio**0.5
    a = (0.0080, -0.1692, 25.3851, 14.0941, -7.0261, 2.7081)
    b = (0.0005, -0.0056, -0.0066, -0.0375, 0.0636, -0.0144)
    base = sum(a[i] * x**i for i in range(6))
    delta = (
        (temperature - 15.0) / (1.0 + 0.0162 * (temperature - 15.0))
    ) * sum(b[i] * x**i for i in range(6))
    salinity = base + delta
    if not (0.0 <= salinity <= 50.0):
        return None
    return salinity


def _calculated_salinity(hass, entry):
    conductivity_id = entry.options.get(CONF_CONDUCTIVITY_ENTITY)
    temperature_id = entry.options.get(CONF_TEMPERATURE_ENTITY)
    conductivity, conductivity_unit, _ = _state_number(hass, conductivity_id)
    temperature, temperature_unit, _ = _state_number(hass, temperature_id)
    conductivity_ms = _conductivity_ms_cm(conductivity, conductivity_unit)
    salinity = _pss78_salinity(conductivity_ms, temperature)
    if salinity is None:
        return None, {
            "source": "calculated",
            "calculation": "PSS-78",
            "conductivity_entity": conductivity_id,
            "temperature_entity": temperature_id,
        }
    return salinity, {
        "source": "calculated",
        "calculation": "PSS-78",
        "conductivity": round(conductivity_ms, 3),
        "conductivity_unit": "mS/cm",
        "temperature": round(temperature, 2),
        "temperature_unit": temperature_unit or "°C",
        "conductivity_entity": conductivity_id,
        "temperature_entity": temperature_id,
    }


def evaluate(hass, entry, param):
    (
        entity_key,
        name,
        icon,
        min_key,
        max_key,
        critical_min_key,
        critical_max_key,
        default_min,
        default_max,
        default_critical_min,
        default_critical_max,
    ) = PARAMS[param]
    entity_id = entry.options.get(entity_key)
    attrs = {"name": name}

    if param == "salinity":
        source = entry.options.get(CONF_SALINITY_SOURCE, DEFAULT_SALINITY_SOURCE)
        use_calculated = source == "calculated" or (source == "auto" and not entity_id)
        if use_calculated:
            value, calc_attrs = _calculated_salinity(hass, entry)
            attrs.update(calc_attrs)
            if value is None:
                return "Nicht verfügbar", None, attrs
            entity_id = None
        else:
            if not entity_id:
                return "Nicht konfiguriert", None, attrs
            state = hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                attrs.update({"source_entity": entity_id, "source": "direct"})
                return "Nicht verfügbar", None, attrs
            try:
                value = float(str(state.state).replace(",", "."))
            except (ValueError, TypeError):
                attrs.update(
                    {
                        "source_entity": entity_id,
                        "raw_state": state.state,
                        "source": "direct",
                    }
                )
                return "Nicht verfügbar", None, attrs
            attrs.update(
                {
                    "source_entity": entity_id,
                    "source": "direct",
                    "unit": state.attributes.get("unit_of_measurement"),
                }
            )
    else:
        if not entity_id:
            return "Nicht konfiguriert", None, attrs
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            attrs["source_entity"] = entity_id
            return "Nicht verfügbar", None, attrs
        try:
            value = float(str(state.state).replace(",", "."))
        except (ValueError, TypeError):
            attrs.update({"source_entity": entity_id, "raw_state": state.state})
            return "Nicht verfügbar", None, attrs
        attrs.update(
            {
                "source_entity": entity_id,
                "unit": state.attributes.get("unit_of_measurement"),
            }
        )

    minimum = float(entry.options.get(min_key, default_min))
    maximum = float(entry.options.get(max_key, default_max))
    critical_minimum = float(
        entry.options.get(critical_min_key, default_critical_min)
    )
    critical_maximum = float(
        entry.options.get(critical_max_key, default_critical_max)
    )

    if value < critical_minimum:
        status = "Kritisch niedrig"
    elif value > critical_maximum:
        status = "Kritisch hoch"
    elif value < minimum:
        status = "Zu niedrig"
    elif value > maximum:
        status = "Zu hoch"
    else:
        status = "Normal"

    attrs.update(
        {
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "critical_minimum": critical_minimum,
            "critical_maximum": critical_maximum,
        }
    )
    if param == "salinity" and attrs.get("source") == "calculated":
        attrs["unit"] = "PSU"
    return status, value, attrs


class ReefControlParameterStatusSensor(ReefControlRuntimeSensor):
    def __init__(self, hass, entry, param):
        super().__init__(hass, entry)
        self.param = param
        self._attr_unique_id = f"{entry.entry_id}_{param}_status"
        self._attr_name = PARAMS[param][1]

    @property
    def native_value(self):
        value = evaluate(self.hass, self._entry, self.param)[1]
        if value is None:
            return None
        if self.param in ("temperature", "salinity"):
            return round(value, 1)
        if self.param == "redox":
            return round(value, 0)
        return value

    @property
    def native_unit_of_measurement(self):
        return evaluate(self.hass, self._entry, self.param)[2].get("unit")

    @property
    def extra_state_attributes(self):
        status, value, attrs = evaluate(self.hass, self._entry, self.param)
        if status in ("Kritisch niedrig", "Zu niedrig"):
            display_status = "Zu niedrig"
        elif status in ("Kritisch hoch", "Zu hoch"):
            display_status = "Zu hoch"
        elif status == "Normal":
            display_status = "OK"
        else:
            display_status = status
        return {**attrs, "status": display_status}

    @property
    def icon(self):
        status = evaluate(self.hass, self._entry, self.param)[0]
        if status.startswith("Kritisch"):
            return "mdi:alert-octagon"
        if status in ("Zu niedrig", "Zu hoch"):
            return "mdi:alert"
        if status == "Normal":
            return PARAMS[self.param][2]
        return "mdi:help-circle-outline"


class ReefControlConductivitySensor(ReefControlRuntimeSensor):
    _attr_name = "Leitfähigkeit"
    _attr_icon = "mdi:lightning-bolt-outline"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_conductivity"

    @property
    def native_value(self):
        value, unit, _ = _state_number(
            self.hass, self._entry.options.get(CONF_CONDUCTIVITY_ENTITY)
        )
        value = _conductivity_ms_cm(value, unit)
        return round(value, 1) if value is not None else None

    @property
    def native_unit_of_measurement(self):
        return "mS/cm"

    @property
    def extra_state_attributes(self):
        entity_id = self._entry.options.get(CONF_CONDUCTIVITY_ENTITY)
        value, unit, state = _state_number(self.hass, entity_id)
        normalized = _conductivity_ms_cm(value, unit)
        return {
            "source_entity": entity_id,
            "source_unit": unit,
            "normalized_unit": "mS/cm",
            "valid": normalized is not None and normalized >= 0,
        }


def _icp_snapshot(hass, entry):
    """Return only the important summary data from the linked Reef ICP aquarium."""
    selected = entry.options.get(CONF_REEF_ICP_ENTRY)
    if not selected:
        return {
            "connected": False,
            "status": "Nicht konfiguriert",
            "aquarium": None,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    icp_entry = hass.config_entries.async_get_entry(selected)
    if icp_entry is None:
        return {
            "connected": False,
            "status": "Nicht verfügbar",
            "aquarium": None,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, selected)

    report_state = None
    for reg in registry_entries:
        if reg.unique_id == f"{selected}_report":
            report_state = hass.states.get(reg.entity_id)
            break

    if report_state is None:
        for reg in registry_entries:
            state = hass.states.get(reg.entity_id)
            if state is None:
                continue
            attrs = state.attributes
            if "status_counts" in attrs and "measurements" in attrs:
                report_state = state
                break

    if report_state is None:
        return {
            "connected": True,
            "status": "Keine Analyse",
            "entry_id": selected,
            "aquarium": icp_entry.title,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    if report_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return {
            "connected": True,
            "status": "Nicht verfügbar",
            "entry_id": selected,
            "aquarium": icp_entry.title,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    attrs = report_state.attributes
    analysis_date = attrs.get("analysis_date")
    analysis_age_days = None
    if analysis_date:
        try:
            parsed_date = datetime.fromisoformat(str(analysis_date)).date()
            analysis_age_days = max(
                0, (datetime.now().astimezone().date() - parsed_date).days
            )
        except (TypeError, ValueError):
            analysis_age_days = None

    raw_status = str(report_state.state).lower()
    status = {
        "ok": "Gut",
        "good": "Gut",
        "warning": "Auffällig",
        "critical": "Kritisch",
        "unknown": "Unklar",
    }.get(raw_status, str(report_state.state))
    status_counts = attrs.get("status_counts") or {}
    try:
        issue_count = int(status_counts.get("warning", 0) or 0) + int(
            status_counts.get("critical", 0) or 0
        )
    except (TypeError, ValueError):
        issue_count = 0

    affected = []
    for measurement in attrs.get("measurements") or []:
        if not isinstance(measurement, dict):
            continue
        measurement_status = measurement.get("status") or {}
        severity = (
            str(measurement_status.get("severity") or "").lower()
            if isinstance(measurement_status, dict)
            else str(measurement_status).lower()
        )
        if severity not in ("warning", "critical"):
            continue
        name = measurement.get("name") or measurement.get("key")
        if name and str(name) not in affected:
            affected.append(str(name))

    return {
        "connected": True,
        "status": status,
        "entry_id": selected,
        "aquarium": icp_entry.title,
        "provider": attrs.get("provider_name") or attrs.get("provider"),
        "analysis_date": analysis_date,
        "analysis_age_days": analysis_age_days,
        "issue_count": issue_count,
        "affected": affected,
        "measurements": attrs.get("measurements") or [],
    }


def _manual_measurement_snapshot(hass, entry):
    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    result = {}
    for key, definition in MANUAL_MEASUREMENTS.items():
        unique_id = f"{entry.entry_id}_manual_{key}"
        state = None
        for reg in registry_entries:
            if reg.unique_id == unique_id:
                state = hass.states.get(reg.entity_id)
                break
        item = {
            "value": None,
            "unit": definition["unit"],
            "source": "manual",
            "last_measurement": None,
            "age_days": None,
            "freshness": "missing",
        }
        if state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                item["value"] = float(str(state.state).replace(",", "."))
            except (TypeError, ValueError):
                item["value"] = None
            item["last_measurement"] = state.attributes.get("last_measurement")
            item["age_days"] = state.attributes.get("measurement_age_days")
            item["freshness"] = state.attributes.get(
                "measurement_freshness", "missing"
            )
        result[key] = item
    return result


ICP_MEASUREMENT_KEYS = {
    "kh": {"kh", "alkalinity", "alkalinitat", "alkalinität", "carbonate_hardness"},
    "calcium": {"calcium", "ca"},
    "magnesium": {"magnesium", "mg"},
    "nitrate": {"nitrate", "nitrat", "no3"},
    "phosphate": {
        "phosphate",
        "phosphat",
        "po4",
        "phosphate_photometric",
        "phosphat_photometrisch",
    },
}
ICP_ENTITY_SUFFIXES = {
    "kh": ("_alkalinitat", "_alkalinity", "_kh"),
    "calcium": ("_calcium",),
    "magnesium": ("_magnesium",),
    "nitrate": ("_nitrat", "_nitrate"),
    "phosphate": (
        "_phosphat_photometrisch",
        "_phosphate_photometric",
        "_phosphat",
        "_phosphate",
    ),
}


def _normalized_measurement_key(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("ß", "ss")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
    )


def _reef_icp_entity_values(hass, entry):
    selected = entry.options.get(CONF_REEF_ICP_ENTRY)
    if not selected:
        return {}
    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, selected)
    result = {}
    for reg in registry_entries:
        state = hass.states.get(reg.entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            continue
        object_id = _normalized_measurement_key(reg.entity_id.split(".", 1)[-1])
        target = None
        for key, suffixes in ICP_ENTITY_SUFFIXES.items():
            if any(object_id.endswith(suffix) for suffix in suffixes):
                target = key
                break
        if target is None:
            continue
        try:
            value = float(str(state.state).replace(",", "."))
        except (TypeError, ValueError):
            continue
        result[target] = {
            "value": value,
            "unit": state.attributes.get("unit_of_measurement")
            or MANUAL_MEASUREMENTS[target]["unit"],
            "status": state.attributes.get("status"),
            "source_entity": reg.entity_id,
        }
    return result


def _icp_measurement_snapshot(hass, entry):
    snap = _icp_snapshot(hass, entry)
    result = {}
    for key, definition in MANUAL_MEASUREMENTS.items():
        result[key] = {
            "value": None,
            "unit": definition["unit"],
            "source": "reef_icp",
            "analysis_date": snap.get("analysis_date"),
            "age_days": snap.get("analysis_age_days"),
            "freshness": "missing",
            "status": None,
        }
    if not snap.get("connected"):
        return result

    age = snap.get("analysis_age_days")
    freshness = (
        "unknown"
        if age is None
        else ("fresh" if age <= 30 else ("aging" if age <= 90 else "stale"))
    )
    aliases = {
        alias: target
        for target, alias_set in ICP_MEASUREMENT_KEYS.items()
        for alias in alias_set
    }
    for measurement in snap.get("measurements") or []:
        if not isinstance(measurement, dict):
            continue
        if str(measurement.get("category") or "").lower() == "osmosis":
            continue
        target = aliases.get(
            _normalized_measurement_key(measurement.get("key"))
        ) or aliases.get(_normalized_measurement_key(measurement.get("name")))
        if target is None:
            continue
        value = measurement.get("value")
        if isinstance(value, bool):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        status = measurement.get("status")
        severity = status.get("severity") if isinstance(status, dict) else status
        result[target] = {
            "value": value,
            "unit": measurement.get("unit") or MANUAL_MEASUREMENTS[target]["unit"],
            "source": "reef_icp",
            "analysis_date": snap.get("analysis_date"),
            "age_days": age,
            "freshness": freshness,
            "status": severity,
        }

    for target, entity_value in _reef_icp_entity_values(hass, entry).items():
        if result[target].get("value") is not None:
            continue
        result[target] = {
            "value": entity_value["value"],
            "unit": entity_value["unit"],
            "source": "reef_icp",
            "analysis_date": snap.get("analysis_date"),
            "age_days": age,
            "freshness": freshness,
            "status": entity_value.get("status"),
            "source_entity": entity_value.get("source_entity"),
        }
    return result


def _preferred_water_values(hass, entry):
    manual = _manual_measurement_snapshot(hass, entry)
    icp = _icp_measurement_snapshot(hass, entry)
    merged = {}
    for key in MANUAL_MEASUREMENTS:
        manual_item = manual[key]
        icp_item = icp[key]
        manual_has = manual_item.get("value") is not None
        icp_has = icp_item.get("value") is not None
        if manual_has and manual_item.get("freshness") in ("fresh", "aging"):
            selected = dict(manual_item)
            reason = "manual_current"
        elif icp_has and icp_item.get("freshness") in ("fresh", "aging"):
            selected = dict(icp_item)
            reason = "icp_current"
        elif manual_has:
            selected = dict(manual_item)
            reason = "manual_fallback"
        elif icp_has:
            selected = dict(icp_item)
            reason = "icp_fallback"
        else:
            selected = {
                "value": None,
                "unit": MANUAL_MEASUREMENTS[key]["unit"],
                "source": None,
                "age_days": None,
                "freshness": "missing",
            }
            reason = "missing"
        selected["selection_reason"] = reason
        selected["manual"] = manual_item
        selected["reef_icp"] = icp_item
        merged[key] = selected
    return merged


class ReefControlWaterValuesSensor(ReefControlRuntimeSensor):
    _attr_name = "Wasserwerte"
    _attr_icon = "mdi:water-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_water_values"

    @property
    def native_value(self):
        values = _preferred_water_values(self.hass, self._entry)
        available = [item for item in values.values() if item.get("value") is not None]
        if not available:
            return "Keine Messwerte"
        stale = sum(1 for item in available if item.get("freshness") == "stale")
        aging = sum(1 for item in available if item.get("freshness") == "aging")
        if stale:
            return f"{stale} veraltet"
        if aging:
            return f"{aging} älter"
        return "Aktuell"

    @property
    def extra_state_attributes(self):
        values = _preferred_water_values(self.hass, self._entry)
        available = {
            key: item for key, item in values.items() if item.get("value") is not None
        }
        return {
            "available_count": len(available),
            "fresh_count": sum(
                1 for item in available.values() if item.get("freshness") == "fresh"
            ),
            "aging_count": sum(
                1 for item in available.values() if item.get("freshness") == "aging"
            ),
            "stale_count": sum(
                1 for item in available.values() if item.get("freshness") == "stale"
            ),
            "manual_source_count": sum(
                1 for item in available.values() if item.get("source") == "manual"
            ),
            "reef_icp_source_count": sum(
                1 for item in available.values() if item.get("source") == "reef_icp"
            ),
            "values": values,
            "source_priority": "manual_current > reef_icp_current > manual_fallback > reef_icp_fallback",
        }


class ReefControlIcpConnectionSensor(ReefControlRuntimeSensor):
    _attr_name = "Reef ICP"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_reef_icp_connection"

    @property
    def native_value(self):
        return (
            "Verbunden"
            if _icp_snapshot(self.hass, self._entry)["connected"]
            else "Nicht verbunden"
        )

    @property
    def icon(self):
        return (
            "mdi:link-variant"
            if self.native_value == "Verbunden"
            else "mdi:link-variant-off"
        )

    @property
    def extra_state_attributes(self):
        snap = _icp_snapshot(self.hass, self._entry)
        return {
            "aquarium": snap.get("aquarium"),
            "entry_id": snap.get("entry_id"),
            "status": snap.get("status"),
            "provider": snap.get("provider"),
            "analysis_date": snap.get("analysis_date"),
        }


class ReefControlIcpSensor(ReefControlRuntimeSensor):
    _attr_name = "ICP"
    _attr_icon = "mdi:flask-outline"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_reef_icp"

    @property
    def native_value(self):
        return _icp_snapshot(self.hass, self._entry)["status"]

    @property
    def extra_state_attributes(self):
        snap = _icp_snapshot(self.hass, self._entry)
        return {
            "aquarium": snap.get("aquarium"),
            "provider": snap.get("provider"),
            "analysis_date": snap.get("analysis_date"),
            "analysis_age_days": snap.get("analysis_age_days"),
            "issue_count": snap.get("issue_count", 0),
            "affected": snap.get("affected", []),
        }


class ReefControlOverallStatusSensor(ReefControlRuntimeSensor):
    _attr_name = "Gesamtstatus"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_overall_status"

    def _results(self):
        return {param: evaluate(self.hass, self._entry, param)[0] for param in PARAMS}

    @property
    def native_value(self):
        values = list(self._results().values())
        active = [value for value in values if value != "Nicht konfiguriert"]
        snap = _icp_snapshot(self.hass, self._entry)
        icp = snap["status"] if snap["connected"] else "Nicht konfiguriert"
        icp_age = snap.get("analysis_age_days")
        icp_stale = icp_age is not None and icp_age > 90
        if not active and icp == "Nicht konfiguriert":
            return "Keine Messwerte"
        if any(value.startswith("Kritisch") for value in active) or (
            icp == "Kritisch" and not icp_stale
        ):
            return "Kritisch"
        if any(
            value in ("Zu niedrig", "Zu hoch", "Nicht verfügbar")
            for value in active
        ) or (icp in ("Auffällig", "Nicht verfügbar") and not icp_stale):
            return "Warnung"
        return "OK"

    @property
    def icon(self):
        return {
            "OK": "mdi:check-circle",
            "Warnung": "mdi:alert",
            "Kritisch": "mdi:alert-octagon",
            "Keine Messwerte": "mdi:gauge-empty",
        }.get(self.native_value, "mdi:gauge")

    @property
    def extra_state_attributes(self):
        results = self._results()
        snap = _icp_snapshot(self.hass, self._entry)
        icp = snap["status"] if snap["connected"] else "Nicht konfiguriert"
        labels = {
            "temperature": "Temperatur",
            "ph": "pH",
            "salinity": "Salinität",
            "redox": "Redox",
        }
        issues = [
            f"{labels.get(param, param)}: {status}"
            for param, status in results.items()
            if status not in ("Normal", "Nicht konfiguriert")
        ]
        icp_age = snap.get("analysis_age_days")
        icp_stale = icp_age is not None and icp_age > 90
        if icp not in ("Gut", "Nicht konfiguriert", "Keine Analyse") and not icp_stale:
            issues.append(f"ICP: {icp}")
        active_sources = sum(
            1 for status in results.values() if status != "Nicht konfiguriert"
        )
        if snap["connected"]:
            active_sources += 1
        return {
            "temperature": results["temperature"],
            "ph": results["ph"],
            "salinity": results["salinity"],
            "redox": results["redox"],
            "icp": icp,
            "icp_connected": snap["connected"],
            "icp_provider": snap.get("provider"),
            "icp_analysis_date": snap.get("analysis_date"),
            "icp_analysis_age_days": snap.get("analysis_age_days"),
            "icp_stale": icp_stale,
            "icp_issue_count": snap.get("issue_count", 0),
            "active_status_sources": active_sources,
            "issue_count": len(issues),
            "issues": issues,
        }


class ReefControlActiveAlarmsSensor(ReefControlRuntimeSensor):
    _attr_name = "Aktive Alarme"
    _attr_icon = "mdi:alarm-light-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_active_alarms"

    @property
    def native_value(self):
        return len(self._runtime().get("active_alarms", []))

    @property
    def extra_state_attributes(self):
        runtime = self._runtime()
        return {
            "alarms": runtime.get("active_alarms", []),
            "history": runtime.get("alarm_history", []),
        }


class ReefControlAtoStatisticsSensor(ReefControlRuntimeSensor):
    _attr_name = "ATO Statistik"
    _attr_icon = "mdi:water-plus-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_ato_statistics"

    @property
    def native_value(self):
        return int(self._runtime().get("ato_statistics", {}).get("fills_today", 0))

    @property
    def extra_state_attributes(self):
        return self._runtime().get("ato_statistics", {})


class ReefControlWaterLevelSensor(ReefControlRuntimeSensor):
    _attr_name = "Wasserstand"
    _attr_icon = "mdi:waves-arrow-up"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_water_level"

    @property
    def native_value(self):
        water_level = self._runtime().get("water_level", {})
        value = water_level.get("value")
        if isinstance(value, (int, float)):
            return value
        return water_level.get("status", "Nicht konfiguriert")

    @property
    def native_unit_of_measurement(self):
        water_level = self._runtime().get("water_level", {})
        return (
            water_level.get("unit")
            if isinstance(water_level.get("value"), (int, float))
            else None
        )

    @property
    def extra_state_attributes(self):
        water_level = dict(self._runtime().get("water_level", {}))
        water_level.pop("value", None)
        water_level.pop("unit", None)
        return water_level
