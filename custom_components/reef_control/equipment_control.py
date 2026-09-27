"""Equipment dependency control for Reef Control."""
from __future__ import annotations

import asyncio
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event

from .const import *


class ReefControlEquipmentController:
    """Coordinate equipment that depends on the return pump."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove_listener = None
        self._restart_tasks = {}
        self._paused_by_controller = set()
        self._status = "Deaktiviert"

    @property
    def enabled(self):
        return bool(self.entry.options.get(CONF_EQUIPMENT_CONTROL_ENABLED, DEFAULT_EQUIPMENT_CONTROL_ENABLED))

    def _runtime(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(self.entry.entry_id, {"entry": self.entry})

    async def async_start(self):
        runtime = self._runtime()
        runtime["equipment_controller"] = self
        runtime["equipment_control_status"] = "Deaktiviert"
        watched = [
            eid for eid in (
                self.entry.options.get(CONF_RETURN_PUMP_ENTITY),
                self.entry.options.get(CONF_SKIMMER_ENTITY),
                self.entry.options.get(CONF_UVC_ENTITY),
                self.entry.options.get(CONF_ATO_ENTITY),
            ) if eid
        ]
        if watched:
            self._remove_listener = async_track_state_change_event(self.hass, watched, self._state_changed)
        if self.enabled:
            await self.async_evaluate()

    async def async_stop(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        self._cancel_restart_tasks()

    async def _state_changed(self, event):
        if not self.enabled:
            return
        entity_id = event.data.get("entity_id")
        if entity_id == self.entry.options.get(CONF_RETURN_PUMP_ENTITY):
            await self.async_evaluate()
            return
        if entity_id in self._paused_by_controller and not self._return_is_on():
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                await self._set(entity_id, False)

    def _return_is_on(self):
        entity_id = self.entry.options.get(CONF_RETURN_PUMP_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        return bool(state and state.state == STATE_ON)

    async def _set(self, entity_id, on):
        state = self.hass.states.get(entity_id)
        if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        domain = entity_id.split(".", 1)[0]
        await self.hass.services.async_call(
            domain, "turn_on" if on else "turn_off",
            {"entity_id": entity_id}, blocking=True
        )

    def _set_status(self, status):
        self._status = status
        runtime = self._runtime()
        runtime["equipment_control_status"] = status
        runtime["return_pump_available"] = self._return_is_on()

    def _cancel_restart_tasks(self):
        for task in self._restart_tasks.values():
            if task and not task.done():
                task.cancel()
        self._restart_tasks.clear()

    async def _pause_dependency(self, entity_id):
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if state and state.state == STATE_ON:
            self._paused_by_controller.add(entity_id)
            await self._set(entity_id, False)

    async def _restart_after(self, key, entity_id, delay_seconds):
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            if not self.enabled or not self._return_is_on():
                return
            runtime = self._runtime()
            if runtime.get("maintenance_active") or runtime.get("feeding_active"):
                return
            if entity_id in self._paused_by_controller:
                await self._set(entity_id, True)
                self._paused_by_controller.discard(entity_id)
        except asyncio.CancelledError:
            pass
        finally:
            self._restart_tasks.pop(key, None)
            if not self._restart_tasks and self._return_is_on():
                self._set_status("Normalbetrieb")

    def _schedule_restart(self, key, entity_id, delay_minutes):
        if not entity_id or entity_id not in self._paused_by_controller:
            return
        old = self._restart_tasks.pop(key, None)
        if old and not old.done():
            old.cancel()
        self._restart_tasks[key] = self.hass.async_create_task(
            self._restart_after(key, entity_id, delay_minutes * 60)
        )

    async def async_evaluate(self):
        if not self.enabled:
            self._cancel_restart_tasks()
            self._set_status("Deaktiviert")
            return

        return_id = self.entry.options.get(CONF_RETURN_PUMP_ENTITY)
        if not return_id:
            self._set_status("Nicht konfiguriert")
            return

        state = self.hass.states.get(return_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._cancel_restart_tasks()
            self._set_status("Rückförderpumpenfehler")
            return

        o = self.entry.options
        skimmer = o.get(CONF_SKIMMER_ENTITY)
        uvc = o.get(CONF_UVC_ENTITY)
        ato = o.get(CONF_ATO_ENTITY)

        if state.state != STATE_ON:
            self._cancel_restart_tasks()
            if o.get(CONF_RETURN_MASTER_SKIMMER, DEFAULT_RETURN_MASTER_SKIMMER):
                await self._pause_dependency(skimmer)
            if o.get(CONF_RETURN_MASTER_UVC, DEFAULT_RETURN_MASTER_UVC):
                await self._pause_dependency(uvc)
            if o.get(CONF_RETURN_MASTER_ATO, DEFAULT_RETURN_MASTER_ATO):
                await self._pause_dependency(ato)
            self._set_status("Rückförderpumpe aus")
            return

        self._set_status("Wiederanlauf")
        if o.get(CONF_RETURN_MASTER_SKIMMER, DEFAULT_RETURN_MASTER_SKIMMER):
            self._schedule_restart(
                "skimmer", skimmer,
                float(o.get(CONF_EQUIPMENT_SKIMMER_DELAY, DEFAULT_EQUIPMENT_SKIMMER_DELAY))
            )
        if o.get(CONF_RETURN_MASTER_UVC, DEFAULT_RETURN_MASTER_UVC):
            self._schedule_restart(
                "uvc", uvc,
                float(o.get(CONF_EQUIPMENT_UVC_DELAY, DEFAULT_EQUIPMENT_UVC_DELAY))
            )

        if o.get(CONF_RETURN_MASTER_ATO, DEFAULT_RETURN_MASTER_ATO) and ato in self._paused_by_controller:
            self._paused_by_controller.discard(ato)
            ato_controller = self._runtime().get("ato_control_switch")
            if ato_controller and ato_controller.is_on:
                await ato_controller.async_evaluate()

        if not self._restart_tasks:
            self._set_status("Normalbetrieb")
