"""Alarm, event and ATO statistics controller for Reef Control."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import *
from .sensor import evaluate


class ReefControlAlarmController:
    """Collect alarms, emit HA events and maintain ATO daily statistics."""

    STORAGE_VERSION = 1

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove_state = None
        self._remove_interval = None
        self._active = {}
        self._history = []
        self._store = Store(
            hass, self.STORAGE_VERSION, f"reef_control.{entry.entry_id}.stats"
        )
        self._stats = {}
        self._ato_running_since = None
        self._last_ato_state = None

    def _r(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self.entry.entry_id, {"entry": self.entry}
        )

    def _ato_entities(self):
        return get_entity_list(
            self.entry.options, CONF_ATO_ENTITIES, CONF_ATO_ENTITY
        )

    async def async_start(self):
        saved = await self._store.async_load() or {}
        self._stats = saved.get("ato", {})
        self._roll_day()

        watched = [
            self.entry.options.get(key)
            for key in (
                CONF_TEMPERATURE_ENTITY,
                CONF_PH_ENTITY,
                CONF_SALINITY_ENTITY,
                CONF_CONDUCTIVITY_ENTITY,
                CONF_REDOX_ENTITY,
                CONF_WATER_LEVEL_ENTITY,
            )
        ]
        watched.extend(
            get_entity_list(self.entry.options, CONF_LEAK_ENTITIES, CONF_LEAK_ENTITY)
        )
        watched.extend(self._ato_entities())
        watched = list(dict.fromkeys(entity_id for entity_id in watched if entity_id))
        if watched:
            self._remove_state = async_track_state_change_event(
                self.hass, watched, self._changed
            )
        self._remove_interval = async_track_time_interval(
            self.hass, self._periodic, timedelta(seconds=2)
        )
        await self.async_evaluate()

    async def async_stop(self):
        if self._remove_state:
            self._remove_state()
            self._remove_state = None
        if self._remove_interval:
            self._remove_interval()
            self._remove_interval = None
        await self._save()

    async def _changed(self, event):
        await self.async_evaluate()

    async def _periodic(self, now):
        await self.async_evaluate()

    def _roll_day(self):
        today = datetime.now().astimezone().date().isoformat()
        if self._stats.get("date") != today:
            self._stats = {
                "date": today,
                "fills_today": 0,
                "runtime_today_seconds": 0.0,
                "last_fill_started": self._stats.get("last_fill_started"),
                "last_fill_stopped": self._stats.get("last_fill_stopped"),
                "last_fill_duration_seconds": self._stats.get(
                    "last_fill_duration_seconds"
                ),
            }

    async def _save(self):
        await self._store.async_save({"ato": self._stats})

    def _ato_group_state(self):
        entities = self._ato_entities()
        if not entities:
            return None
        states = [self.hass.states.get(entity_id) for entity_id in entities]
        # Statistics follow the group cycle: if any configured ATO actuator is on,
        # Reef Control considers the top-off system to be running.
        return STATE_ON if any(state and state.state == STATE_ON for state in states) else "off"

    async def _update_ato_stats(self):
        self._roll_day()
        current = self._ato_group_state()
        now = datetime.now().astimezone()
        changed = False

        if current == STATE_ON and self._last_ato_state != STATE_ON:
            self._ato_running_since = now
            self._stats["fills_today"] = int(self._stats.get("fills_today", 0)) + 1
            self._stats["last_fill_started"] = now.isoformat()
            changed = True
        elif (
            current != STATE_ON
            and self._last_ato_state == STATE_ON
            and self._ato_running_since
        ):
            duration = max(0.0, (now - self._ato_running_since).total_seconds())
            self._stats["runtime_today_seconds"] = round(
                float(self._stats.get("runtime_today_seconds", 0.0)) + duration, 1
            )
            self._stats["last_fill_duration_seconds"] = round(duration, 1)
            self._stats["last_fill_stopped"] = now.isoformat()
            self._ato_running_since = None
            changed = True

        self._last_ato_state = current
        runtime = self._r()
        running = (
            (now - self._ato_running_since).total_seconds()
            if self._ato_running_since
            else 0.0
        )
        runtime["ato_statistics"] = {
            **self._stats,
            "current_fill_duration_seconds": round(running, 1),
            "runtime_today_seconds_live": round(
                float(self._stats.get("runtime_today_seconds", 0.0)) + running, 1
            ),
            "ato_entities": self._ato_entities(),
        }
        if changed:
            await self._save()

    def _water_level(self):
        entity_id = self.entry.options.get(CONF_WATER_LEVEL_ENTITY)
        if not entity_id:
            return {
                "status": "Nicht konfiguriert",
                "value": None,
                "unit": None,
                "entity": None,
            }
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return {
                "status": "Nicht verfügbar",
                "value": None,
                "unit": None,
                "entity": entity_id,
            }

        mode = self.entry.options.get(CONF_WATER_LEVEL_MODE, DEFAULT_WATER_LEVEL_MODE)
        unit = state.attributes.get("unit_of_measurement")
        numeric = None
        try:
            numeric = float(str(state.state).replace(",", "."))
        except (TypeError, ValueError):
            pass

        if mode == "level_cm" or (
            mode == "auto"
            and numeric is not None
            and entity_id.split(".", 1)[0] in ("sensor", "input_number")
        ):
            low = float(
                self.entry.options.get(CONF_WATER_LEVEL_LOW_CM, DEFAULT_WATER_LEVEL_LOW_CM)
            )
            high = float(
                self.entry.options.get(CONF_WATER_LEVEL_HIGH_CM, DEFAULT_WATER_LEVEL_HIGH_CM)
            )
            if numeric is None:
                status = "Nicht verfügbar"
            elif numeric <= low:
                status = "Zu niedrig"
            elif numeric >= high:
                status = "Zu hoch"
            else:
                status = "OK"
            return {
                "status": status,
                "value": round(numeric, 1) if numeric is not None else None,
                "unit": unit or "cm",
                "entity": entity_id,
                "low_cm": low,
                "high_cm": high,
            }

        low_state = self.entry.options.get(CONF_ATO_LOW_STATE, DEFAULT_ATO_LOW_STATE)
        status = "Zu niedrig" if state.state == low_state else "OK"
        return {
            "status": status,
            "value": state.state,
            "unit": None,
            "entity": entity_id,
            "low_state": low_state,
        }

    def _collect(self):
        alarms = {}
        now = datetime.now().astimezone().isoformat()
        runtime = self._r()

        for reason in runtime.get("safety_reasons", []):
            alarms[f"safety:{reason}"] = {
                "message": reason,
                "severity": "critical",
                "source": "safety",
                "detected_at": now,
            }

        for param in ("temperature", "ph", "salinity", "redox"):
            status, value, attrs = evaluate(self.hass, self.entry, param)
            if status.startswith("Kritisch"):
                alarms[f"water:{param}"] = {
                    "message": f"{attrs.get('name', param)}: {status}",
                    "severity": "critical",
                    "source": param,
                    "value": value,
                    "detected_at": now,
                }
            elif status in ("Zu niedrig", "Zu hoch"):
                alarms[f"water:{param}"] = {
                    "message": f"{attrs.get('name', param)}: {status}",
                    "severity": "warning",
                    "source": param,
                    "value": value,
                    "detected_at": now,
                }

        water_level = self._water_level()
        if water_level["status"] in ("Zu niedrig", "Zu hoch", "Nicht verfügbar"):
            severity = (
                "warning" if water_level["status"] != "Nicht verfügbar" else "critical"
            )
            alarms["water_level"] = {
                "message": f"Wasserstand: {water_level['status']}",
                "severity": severity,
                "source": "water_level",
                "value": water_level.get("value"),
                "detected_at": now,
            }

        ato = runtime.get("ato_control_switch")
        if ato and getattr(ato, "_locked", False):
            alarms["ato_lock"] = {
                "message": "ATO Sicherheitsstopp",
                "severity": "critical",
                "source": "ato",
                "detected_at": now,
            }
        return alarms, water_level

    async def async_evaluate(self):
        await self._update_ato_stats()
        new, water_level = self._collect()
        old_keys, new_keys = set(self._active), set(new)

        for key in new_keys & old_keys:
            new[key]["detected_at"] = self._active[key].get(
                "detected_at", new[key]["detected_at"]
            )

        for key in new_keys - old_keys:
            item = new[key]
            self.hass.bus.async_fire(
                EVENT_ALARM,
                {
                    "entry_id": self.entry.entry_id,
                    "aquarium": self.entry.title,
                    "alarm_id": key,
                    **item,
                },
            )
            self._history.insert(0, {"alarm_id": key, **item})

        for key in old_keys - new_keys:
            item = self._active[key]
            self.hass.bus.async_fire(
                EVENT_ALARM_CLEARED,
                {
                    "entry_id": self.entry.entry_id,
                    "aquarium": self.entry.title,
                    "alarm_id": key,
                    **item,
                },
            )

        self._history = self._history[:20]
        self._active = new
        runtime = self._r()
        runtime["active_alarms"] = list(new.values())
        runtime["alarm_history"] = self._history
        runtime["water_level"] = water_level
