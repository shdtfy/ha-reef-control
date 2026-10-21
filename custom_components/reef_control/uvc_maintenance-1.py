"""Persistent UV-C lamp runtime and maintenance accounting for Reef Control.

The measurement source is the ON state of a configured UV-C switch, not the
controller's requested state. This remains useful when UV-C automatic control
is disabled or a device is operated manually.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from homeassistant.const import STATE_ON
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_UVC_ENTITIES,
    CONF_UVC_ENTITY,
    CONF_UVC_LAMP_MAINTENANCE,
    DEFAULT_UVC_LAMP_INTERVAL_DAYS,
    DEFAULT_UVC_LAMP_INTERVAL_HOURS,
    DEFAULT_UVC_LAMP_METHOD,
    DEFAULT_UVC_LAMP_WARNING_DAYS,
    DEFAULT_UVC_LAMP_WARNING_HOURS,
    DOMAIN,
    EVENT_UVC_LAMP_MAINTENANCE,
    get_entity_list,
)


def uvc_maintenance_key(entity_id: str) -> str:
    """A stable identifier independent of display-name changes."""
    return sha256(entity_id.encode("utf-8")).hexdigest()[:12]


def _utc_now():
    return dt_util.utcnow()


def _parse_timestamp(value, fallback):
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return fallback


class ReefControlUvcMaintenance:
    """Track switch-on periods, document changes, and report service due."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, 1, f"{DOMAIN}_uvc_maintenance_{entry.entry_id}")
        self._records = {}
        self._last_tick = None
        self._last_states = {}
        self._remove_state_listener = None
        self._remove_timer = None

    def _entities(self):
        return get_entity_list(self.entry.options, CONF_UVC_ENTITIES, CONF_UVC_ENTITY)

    def _options(self, entity_id):
        mapping = self.entry.options.get(CONF_UVC_LAMP_MAINTENANCE, {}) or {}
        options = mapping.get(entity_id, {}) if isinstance(mapping, dict) else {}
        options = options if isinstance(options, dict) else {}
        method = options.get("method", DEFAULT_UVC_LAMP_METHOD)
        method = method if method in ("hours", "days") else DEFAULT_UVC_LAMP_METHOD
        default_interval = DEFAULT_UVC_LAMP_INTERVAL_DAYS if method == "days" else DEFAULT_UVC_LAMP_INTERVAL_HOURS
        default_warning = DEFAULT_UVC_LAMP_WARNING_DAYS if method == "days" else DEFAULT_UVC_LAMP_WARNING_HOURS
        try:
            interval = max(1, int(options.get("interval", default_interval)))
            warning = max(0, min(interval - 1, int(options.get("warning", default_warning))))
        except (ValueError, TypeError):
            interval, warning = default_interval, default_warning
        state = self.hass.states.get(entity_id)
        fallback_name = state.attributes.get("friendly_name", entity_id) if state else entity_id
        return {
            "name": str(options.get("name") or fallback_name)[:100],
            "enabled": bool(options.get("enabled", True)),
            "method": method,
            "interval": interval,
            "warning": warning,
        }

    @staticmethod
    def _blank_record(now):
        return {
            "installed_at": now.isoformat(),
            "seconds": 0.0,
            "history": [],
            "last_notified_level": "ok",
        }

    def _payload(self):
        return {"devices": self._records}

    def _schedule_save(self):
        # Storage writes are debounced; the latest snapshot is written on unload.
        self._store.async_delay_save(self._payload, 15)

    async def async_start(self):
        data = await self._store.async_load() or {}
        devices = data.get("devices", {})
        if isinstance(devices, dict):
            self._records = devices
        now = _utc_now()
        for entity_id in self._entities():
            if entity_id not in self._records or not isinstance(self._records[entity_id], dict):
                self._records[entity_id] = self._blank_record(now)
            state = self.hass.states.get(entity_id)
            self._last_states[entity_id] = state.state == STATE_ON if state is not None else False
        self._last_tick = now
        if self._entities():
            self._remove_state_listener = async_track_state_change_event(
                self.hass, self._entities(), self._on_state_change,
            )
        self._remove_timer = async_track_time_interval(
            self.hass, self._on_timer, timedelta(seconds=30),
        )
        self._check_warnings(now)
        self._schedule_save()

    def _accrue(self, now):
        """Count elapsed time only while the last observed state was on."""
        if self._last_tick is None:
            self._last_tick = now
            return
        delta = max(0.0, (now - self._last_tick).total_seconds())
        # If the host slept or HA stopped for a long time, physical lamp state
        # cannot be proven. Do not invent a full offline period.
        delta = min(delta, 90.0)
        if delta:
            for entity_id in self._entities():
                if self._last_states.get(entity_id):
                    record = self._records.get(entity_id)
                    if record is not None:
                        record["seconds"] = max(0.0, float(record.get("seconds", 0.0))) + delta
        self._last_tick = now

    async def _on_state_change(self, event):
        now = _utc_now()
        self._accrue(now)
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        # unknown/unavailable are never counted as ON.
        self._last_states[entity_id] = bool(new_state is not None and new_state.state == STATE_ON)
        self._check_warnings(now)
        self._schedule_save()

    async def _on_timer(self, now):
        current = _utc_now()
        self._accrue(current)
        self._check_warnings(current)
        self._schedule_save()

    def summary(self, entity_id: str, now=None):
        """Expose per-device lifetime and history for Home Assistant sensors."""
        current = now or _utc_now()
        record = self._records.get(entity_id) or self._blank_record(current)
        options = self._options(entity_id)
        installed = _parse_timestamp(record.get("installed_at"), current)
        age_days = max(0, (dt_util.as_local(current).date() - dt_util.as_local(installed).date()).days)
        hours = max(0.0, float(record.get("seconds", 0.0))) / 3600.0
        measure = hours if options["method"] == "hours" else age_days
        remaining = options["interval"] - measure
        if not options["enabled"]:
            status = "Deaktiviert"
        elif measure >= options["interval"]:
            status = "Überfällig"
        elif remaining <= options["warning"]:
            status = "Bald fällig"
        else:
            status = "OK"
        return {
            "uvc_entity_id": entity_id,
            "name": options["name"],
            "enabled": options["enabled"],
            "method": options["method"],
            "interval": options["interval"],
            "warning": options["warning"],
            "hours": round(hours, 3),
            "age_days": age_days,
            "remaining": round(remaining, 2),
            "progress_percent": round(min(100.0, max(0.0, measure / options["interval"] * 100)), 1),
            "installed_at": installed.isoformat(),
            "last_changed_at": installed.isoformat(),
            "status": status,
            "history": list(record.get("history", []))[-30:],
        }

    def _check_warnings(self, now):
        for entity_id in self._entities():
            record = self._records.get(entity_id)
            if record is None:
                continue
            info = self.summary(entity_id, now)
            level = info["status"]
            if level not in ("Bald fällig", "Überfällig"):
                # Re-arm if interval changes or lamp was physically replaced.
                if record.get("last_notified_level") != "ok":
                    record["last_notified_level"] = "ok"
                continue
            if level == record.get("last_notified_level"):
                continue
            record["last_notified_level"] = level
            self.hass.bus.async_fire(EVENT_UVC_LAMP_MAINTENANCE, {
                "entry_id": self.entry.entry_id,
                "uvc_entity_id": entity_id,
                "name": info["name"],
                "status": level,
                "remaining": info["remaining"],
                "method": info["method"],
                "interval": info["interval"],
            })

    async def async_record_replacement(self, entity_id: str):
        """Only called after a user confirms a physical lamp replacement."""
        if entity_id not in self._entities():
            return
        now = _utc_now()
        self._accrue(now)
        record = self._records.setdefault(entity_id, self._blank_record(now))
        old = self.summary(entity_id, now)
        history = list(record.get("history", []))
        history.append({
            "installed_at": old["installed_at"],
            "replaced_at": now.isoformat(),
            "operating_hours": old["hours"],
            "calendar_days": old["age_days"],
            "method": old["method"],
            "interval": old["interval"],
        })
        record.update({
            "installed_at": now.isoformat(),
            "seconds": 0.0,
            "history": history[-30:],
            "last_notified_level": "ok",
        })
        # Give UI sensors time to update; cannot rely on a state change alone.
        await self._store.async_save(self._payload())

    async def async_stop(self):
        self._accrue(_utc_now())
        if self._remove_state_listener:
            self._remove_state_listener()
            self._remove_state_listener = None
        if self._remove_timer:
            self._remove_timer()
            self._remove_timer = None
        await self._store.async_save(self._payload())
