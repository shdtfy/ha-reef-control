"""Equipment dependency control for Reef Control."""
from __future__ import annotations

import asyncio

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event

from .const import *


class ReefControlEquipmentController:
    """Coordinate equipment that depends on the return-pump group."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove_listener = None
        self._restart_tasks = {}
        self._paused_by_controller = set()
        self._status = "Deaktiviert"

    @property
    def enabled(self):
        return bool(
            self.entry.options.get(
                CONF_EQUIPMENT_CONTROL_ENABLED, DEFAULT_EQUIPMENT_CONTROL_ENABLED
            )
        )

    def _runtime(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self.entry.entry_id, {"entry": self.entry}
        )

    def _entities(self, plural_key, legacy_key=None):
        return get_entity_list(self.entry.options, plural_key, legacy_key)

    def _return_entities(self):
        return self._entities(CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY)

    def _return_is_on(self):
        for entity_id in self._return_entities():
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                return True
        return False

    def _return_is_available(self):
        ids = self._return_entities()
        if not ids:
            return False
        return any(
            (state := self.hass.states.get(entity_id)) is not None
            and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            for entity_id in ids
        )

    async def async_start(self):
        r = self._runtime()
        r["equipment_controller"] = self
        r["equipment_control_status"] = "Deaktiviert"
        r["equipment_paused_entities"] = []

        watched = []
        for plural_key, legacy_key in (
            (CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY),
            (CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY),
            (CONF_UVC_ENTITIES, CONF_UVC_ENTITY),
            (CONF_ATO_ENTITIES, CONF_ATO_ENTITY),
            (CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY),
        ):
            watched.extend(self._entities(plural_key, legacy_key))
        watched = list(dict.fromkeys(watched))

        if watched:
            self._remove_listener = async_track_state_change_event(
                self.hass, watched, self._state_changed
            )
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
        if entity_id in self._return_entities():
            await self.async_evaluate()
            return
        if entity_id in self._paused_by_controller and not self._return_is_on():
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                await self._set(entity_id, False)

    async def _set(self, entity_id, on):
        state = self.hass.states.get(entity_id)
        if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            "turn_on" if on else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    def _set_status(self, status):
        self._status = status
        r = self._runtime()
        r["equipment_control_status"] = status
        r["return_pump_available"] = self._return_is_available()
        r["return_pump_running"] = self._return_is_on()
        r["return_pump_entities"] = self._return_entities()
        r["equipment_paused_entities"] = sorted(self._paused_by_controller)

    def _cancel_restart_tasks(self):
        for task in self._restart_tasks.values():
            if task and not task.done():
                task.cancel()
        self._restart_tasks.clear()

    async def _pause_dependencies(self, entity_ids):
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state and state.state == STATE_ON:
                self._paused_by_controller.add(entity_id)
                await self._set(entity_id, False)

    async def _restart_after(self, key, entity_ids, seconds):
        try:
            if seconds > 0:
                await asyncio.sleep(seconds)
            r = self._runtime()
            if (
                not self.enabled
                or not self._return_is_on()
                or r.get("maintenance_active")
                or r.get("feeding_active")
            ):
                return
            for entity_id in entity_ids:
                if entity_id in self._paused_by_controller:
                    await self._set(entity_id, True)
                    self._paused_by_controller.discard(entity_id)
        except asyncio.CancelledError:
            pass
        finally:
            self._restart_tasks.pop(key, None)
            self._set_status(
                "Normalbetrieb"
                if not self._restart_tasks and self._return_is_on()
                else "Wiederanlauf"
            )

    def _schedule(self, key, entity_ids, minutes):
        pending = [eid for eid in entity_ids if eid in self._paused_by_controller]
        if not pending:
            return
        old = self._restart_tasks.pop(key, None)
        if old and not old.done():
            old.cancel()
        self._restart_tasks[key] = self.hass.async_create_task(
            self._restart_after(key, pending, float(minutes) * 60)
        )

    async def async_evaluate(self):
        if not self.enabled:
            self._cancel_restart_tasks()
            self._set_status("Deaktiviert")
            return

        return_ids = self._return_entities()
        if not return_ids:
            self._set_status("Nicht konfiguriert")
            return
        if not self._return_is_available():
            self._cancel_restart_tasks()
            self._set_status("Rückförderpumpenfehler")
            return

        o = self.entry.options
        dependencies = (
            (
                CONF_RETURN_MASTER_SKIMMER,
                DEFAULT_RETURN_MASTER_SKIMMER,
                self._entities(CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY),
            ),
            (
                CONF_RETURN_MASTER_UVC,
                DEFAULT_RETURN_MASTER_UVC,
                self._entities(CONF_UVC_ENTITIES, CONF_UVC_ENTITY),
            ),
            (
                CONF_RETURN_MASTER_ATO,
                DEFAULT_RETURN_MASTER_ATO,
                self._entities(CONF_ATO_ENTITIES, CONF_ATO_ENTITY),
            ),
            (
                CONF_RETURN_MASTER_FLOW,
                DEFAULT_RETURN_MASTER_FLOW,
                self._entities(CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY),
            ),
        )

        if not self._return_is_on():
            self._cancel_restart_tasks()
            for flag, default, entity_ids in dependencies:
                if o.get(flag, default):
                    await self._pause_dependencies(entity_ids)
            self._set_status("Rückförderpumpe aus")
            return

        self._set_status("Wiederanlauf")

        if o.get(CONF_RETURN_MASTER_SKIMMER, DEFAULT_RETURN_MASTER_SKIMMER):
            self._schedule(
                "skimmer",
                self._entities(CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY),
                o.get(CONF_EQUIPMENT_SKIMMER_DELAY, DEFAULT_EQUIPMENT_SKIMMER_DELAY),
            )
        if o.get(CONF_RETURN_MASTER_UVC, DEFAULT_RETURN_MASTER_UVC):
            self._schedule(
                "uvc",
                self._entities(CONF_UVC_ENTITIES, CONF_UVC_ENTITY),
                o.get(CONF_EQUIPMENT_UVC_DELAY, DEFAULT_EQUIPMENT_UVC_DELAY),
            )
        if o.get(CONF_RETURN_MASTER_FLOW, DEFAULT_RETURN_MASTER_FLOW):
            self._schedule(
                "flow",
                self._entities(CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY),
                o.get(CONF_EQUIPMENT_FLOW_DELAY, DEFAULT_EQUIPMENT_FLOW_DELAY),
            )

        ato_ids = self._entities(CONF_ATO_ENTITIES, CONF_ATO_ENTITY)
        if o.get(CONF_RETURN_MASTER_ATO, DEFAULT_RETURN_MASTER_ATO):
            released = False
            for entity_id in ato_ids:
                if entity_id in self._paused_by_controller:
                    self._paused_by_controller.discard(entity_id)
                    released = True
            if released:
                ato_controller = self._runtime().get("ato_control_switch")
                if ato_controller and ato_controller.is_on:
                    await ato_controller.async_evaluate()

        if not self._restart_tasks:
            self._set_status("Normalbetrieb")
