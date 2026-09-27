"""Automatic UV-C control for Reef Control."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import *


class ReefControlUvcController:
    """Control UV-C by mode, schedule and aquarium safety state."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove_state_listener = None
        self._remove_time_listener = None
        self._status = "Deaktiviert"
        self._controlled_on = False

    @property
    def enabled(self):
        return bool(
            self.entry.options.get(
                CONF_UVC_CONTROL_ENABLED, DEFAULT_UVC_CONTROL_ENABLED
            )
        )

    def _runtime(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self.entry.entry_id, {"entry": self.entry}
        )

    async def async_start(self):
        runtime = self._runtime()
        runtime["uvc_controller"] = self
        runtime["uvc_control_status"] = "Deaktiviert"

        watched = [
            entity_id
            for entity_id in (
                self.entry.options.get(CONF_UVC_ENTITY),
                self.entry.options.get(CONF_RETURN_PUMP_ENTITY),
            )
            if entity_id
        ]
        if watched:
            self._remove_state_listener = async_track_state_change_event(
                self.hass, watched, self._state_changed
            )

        self._remove_time_listener = async_track_time_interval(
            self.hass, self._time_tick, timedelta(seconds=30)
        )

        await self.async_evaluate()

    async def async_stop(self):
        if self._remove_state_listener:
            self._remove_state_listener()
            self._remove_state_listener = None
        if self._remove_time_listener:
            self._remove_time_listener()
            self._remove_time_listener = None

    async def _state_changed(self, event):
        entity_id = event.data.get("entity_id")
        # Do not fight a deliberate manual UV-C switch while controller is disabled.
        if self.enabled or entity_id == self.entry.options.get(CONF_RETURN_PUMP_ENTITY):
            await self.async_evaluate()

    async def _time_tick(self, now):
        if self.enabled:
            await self.async_evaluate()

    def _set_status(self, status):
        self._status = status
        self._runtime()["uvc_control_status"] = status

    async def _set_uvc(self, on):
        entity_id = self.entry.options.get(CONF_UVC_ENTITY)
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        already_on = state.state == STATE_ON
        if already_on == on:
            self._controlled_on = on
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            "turn_on" if on else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )
        self._controlled_on = on

    def _return_pump_ok(self):
        # Only enforce this interlock when equipment control explicitly makes
        # UV-C dependent on the return pump.
        options = self.entry.options
        if not options.get(
            CONF_EQUIPMENT_CONTROL_ENABLED, DEFAULT_EQUIPMENT_CONTROL_ENABLED
        ):
            return True
        if not options.get(CONF_RETURN_MASTER_UVC, DEFAULT_RETURN_MASTER_UVC):
            return True

        entity_id = options.get(CONF_RETURN_PUMP_ENTITY)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return bool(state and state.state == STATE_ON)

    @staticmethod
    def _parse_time(value, default):
        raw = value or default
        if isinstance(raw, time):
            return raw
        text = str(raw)
        try:
            return time.fromisoformat(text)
        except ValueError:
            return time.fromisoformat(default)

    def _inside_schedule(self):
        options = self.entry.options
        start = self._parse_time(
            options.get(CONF_UVC_START_TIME), DEFAULT_UVC_START_TIME
        )
        end = self._parse_time(
            options.get(CONF_UVC_END_TIME), DEFAULT_UVC_END_TIME
        )
        now = datetime.now().astimezone().time().replace(tzinfo=None)

        if start == end:
            return True
        if start < end:
            return start <= now < end
        # Schedule crosses midnight, e.g. 20:00 -> 08:00.
        return now >= start or now < end

    async def async_evaluate(self):
        options = self.entry.options
        entity_id = options.get(CONF_UVC_ENTITY)

        if not self.enabled:
            self._set_status("Deaktiviert")
            return

        if not entity_id:
            self._set_status("Nicht konfiguriert")
            return

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._set_status("UV-C nicht verfügbar")
            return

        runtime = self._runtime()
        if runtime.get("maintenance_active") and options.get(
            CONF_MAINTENANCE_PAUSE_UVC, True
        ):
            await self._set_uvc(False)
            self._set_status("Pausiert: Wartung")
            return

        if runtime.get("feeding_active") and options.get(
            CONF_FEEDING_PAUSE_UVC, False
        ):
            await self._set_uvc(False)
            self._set_status("Pausiert: Fütterung")
            return

        if not self._return_pump_ok():
            await self._set_uvc(False)
            self._set_status("Rückförderpumpe aus")
            return

        mode = options.get(CONF_UVC_MODE, DEFAULT_UVC_MODE)

        if mode == "off":
            await self._set_uvc(False)
            self._set_status("Aus")
            return

        if mode == "continuous":
            await self._set_uvc(True)
            self._set_status("Dauerbetrieb")
            return

        if mode == "schedule":
            if self._inside_schedule():
                await self._set_uvc(True)
                self._set_status("Zeitplan aktiv")
            else:
                await self._set_uvc(False)
                self._set_status("Außerhalb Zeitplan")
            return

        await self._set_uvc(False)
        self._set_status("Ungültiger Modus")
