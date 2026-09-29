"""Central safety interlocks for Reef Control."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import *


class ReefControlSafetyController:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove_state = None
        self._remove_interval = None
        self._leak_latched = False

    def _r(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self.entry.entry_id, {"entry": self.entry}
        )

    @property
    def enabled(self):
        return bool(
            self.entry.options.get(
                CONF_SAFETY_CONTROL_ENABLED, DEFAULT_SAFETY_CONTROL_ENABLED
            )
        )

    async def async_start(self):
        runtime = self._r()
        runtime["safety_controller"] = self
        runtime["safety_status"] = "Bereit" if self.enabled else "Deaktiviert"
        runtime["safety_reasons"] = []
        runtime["leak_detected"] = False
        runtime["leak_latched"] = False

        watched = [
            entity_id
            for entity_id in (self.entry.options.get(CONF_TEMPERATURE_ENTITY),)
            if entity_id
        ]
        watched.extend(
            get_entity_list(self.entry.options, CONF_LEAK_ENTITIES, CONF_LEAK_ENTITY)
        )
        watched = list(dict.fromkeys(watched))
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

    async def _changed(self, event):
        await self.async_evaluate()

    async def _periodic(self, now):
        await self.async_evaluate()

    async def _turn_off(self, entity_id):
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state != STATE_ON:
            return
        domain = entity_id.split(".", 1)[0]
        if domain not in ("switch", "light", "input_boolean"):
            return
        await self.hass.services.async_call(
            domain, "turn_off", {"entity_id": entity_id}, blocking=True
        )

    async def _turn_off_many(self, entity_ids):
        for entity_id in entity_ids:
            await self._turn_off(entity_id)

    async def _heater_off(self):
        await self._turn_off_many(
            get_entity_list(
                self.entry.options, CONF_HEATER_ENTITIES, CONF_HEATER_ENTITY
            )
        )

    def _leak_is_active(self):
        entity_ids = get_entity_list(
            self.entry.options, CONF_LEAK_ENTITIES, CONF_LEAK_ENTITY
        )
        if not entity_ids:
            return False, "Nicht konfiguriert"

        active_state = self.entry.options.get(
            CONF_LEAK_ACTIVE_STATE, DEFAULT_LEAK_ACTIVE_STATE
        )
        expected = STATE_ON if active_state == "on" else STATE_OFF
        states = {}
        valid_seen = False
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            raw = "missing" if state is None else state.state
            states[entity_id] = raw
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue
            valid_seen = True
            if state.state == expected:
                return True, states

        if not valid_seen:
            return False, states
        return False, states

    async def _leak_shutdown(self):
        if not self.entry.options.get(
            CONF_SAFETY_LEAK_SHUTDOWN, DEFAULT_SAFETY_LEAK_SHUTDOWN
        ):
            return

        targets = (
            (
                CONF_SAFETY_LEAK_RETURN_PUMP,
                DEFAULT_SAFETY_LEAK_RETURN_PUMP,
                CONF_RETURN_PUMP_ENTITIES,
                CONF_RETURN_PUMP_ENTITY,
            ),
            (
                CONF_SAFETY_LEAK_SKIMMER,
                DEFAULT_SAFETY_LEAK_SKIMMER,
                CONF_SKIMMER_ENTITIES,
                CONF_SKIMMER_ENTITY,
            ),
            (
                CONF_SAFETY_LEAK_UVC,
                DEFAULT_SAFETY_LEAK_UVC,
                CONF_UVC_ENTITIES,
                CONF_UVC_ENTITY,
            ),
            (
                CONF_SAFETY_LEAK_ATO,
                DEFAULT_SAFETY_LEAK_ATO,
                CONF_ATO_ENTITIES,
                CONF_ATO_ENTITY,
            ),
            (
                CONF_SAFETY_LEAK_HEATER,
                DEFAULT_SAFETY_LEAK_HEATER,
                CONF_HEATER_ENTITIES,
                CONF_HEATER_ENTITY,
            ),
        )
        for option_key, default, plural_key, legacy_key in targets:
            if self.entry.options.get(option_key, default):
                await self._turn_off_many(
                    get_entity_list(self.entry.options, plural_key, legacy_key)
                )

    async def async_evaluate(self):
        runtime = self._r()
        reasons = []

        if not self.enabled:
            # Deliberate safety-control OFF resets the leak latch.
            self._leak_latched = False
            runtime["leak_detected"] = False
            runtime["leak_latched"] = False
            runtime["safety_status"] = "Deaktiviert"
            runtime["safety_reasons"] = []
            return

        leak_active, leak_state = self._leak_is_active()
        runtime["leak_detected"] = leak_active
        runtime["leak_source_state"] = leak_state

        if leak_active:
            self._leak_latched = True

        runtime["leak_latched"] = self._leak_latched

        if leak_active:
            reasons.append("Leckage erkannt")
        elif self._leak_latched:
            reasons.append("Leckage-Sicherheitsstopp verriegelt")

        if self._leak_latched:
            await self._leak_shutdown()

        temp_id = self.entry.options.get(CONF_TEMPERATURE_ENTITY)
        state = self.hass.states.get(temp_id) if temp_id else None
        if temp_id and (
            state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        ):
            reasons.append("Temperatursensor nicht verfügbar")
            if self.entry.options.get(
                CONF_SAFETY_HEATER_SENSOR_FAIL, DEFAULT_SAFETY_HEATER_SENSOR_FAIL
            ):
                await self._heater_off()
        elif state is not None:
            try:
                value = float(str(state.state).replace(",", "."))
                critical = float(
                    self.entry.options.get(
                        CONF_TEMPERATURE_CRITICAL_MAX,
                        DEFAULT_TEMPERATURE_CRITICAL_MAX,
                    )
                )
                if value >= critical:
                    reasons.append(f"Temperatur kritisch hoch ({value:g} °C)")
                    if self.entry.options.get(
                        CONF_SAFETY_HEATER_HIGH_TEMP,
                        DEFAULT_SAFETY_HEATER_HIGH_TEMP,
                    ):
                        await self._heater_off()
            except (TypeError, ValueError):
                reasons.append("Temperatursensor ungültig")
                if self.entry.options.get(
                    CONF_SAFETY_HEATER_SENSOR_FAIL,
                    DEFAULT_SAFETY_HEATER_SENSOR_FAIL,
                ):
                    await self._heater_off()

        ato = runtime.get("ato_control_switch")
        if ato and getattr(ato, "_locked", False):
            reasons.append("ATO Sicherheitsstopp")

        equipment_status = runtime.get("equipment_control_status")
        if equipment_status == "Rückförderpumpenfehler":
            reasons.append("Rückförderpumpe nicht verfügbar")

        runtime["safety_reasons"] = reasons
        runtime["safety_status"] = "Sicherheitsstopp" if reasons else "Bereit"
