"""Switch platform for Reef Control."""

from __future__ import annotations

import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_AQUARIUM_NAME,
    CONF_ATO_ENTITY,
    CONF_FEEDING_DURATION,
    CONF_FEEDING_PAUSE_ATO,
    CONF_FEEDING_PAUSE_FLOW_PUMP,
    CONF_FEEDING_PAUSE_RETURN_PUMP,
    CONF_FEEDING_PAUSE_SKIMMER,
    CONF_FLOW_PUMP_ENTITY,
    CONF_RETURN_PUMP_ENTITY,
    CONF_SKIMMER_DELAY,
    CONF_SKIMMER_ENTITY,
    DEFAULT_FEEDING_DURATION,
    DEFAULT_SKIMMER_DELAY,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Reef Control switches."""
    async_add_entities([ReefControlFeedingModeSwitch(hass, entry)])


class ReefControlFeedingModeSwitch(SwitchEntity):
    """Feeding mode for an aquarium."""

    _attr_has_entity_name = True
    _attr_name = "Fütterungsmodus"
    _attr_icon = "mdi:fish-food"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_feeding_mode"
        self._is_on = False
        self._restore_states: dict[str, bool] = {}
        self._auto_off_task: asyncio.Task | None = None
        self._skimmer_task: asyncio.Task | None = None

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    async def async_turn_on(self, **kwargs) -> None:
        if self._is_on:
            return
        self._cancel_tasks()
        self._restore_states = {}
        self._is_on = True
        self.async_write_ha_state()

        for entity_id in self._pause_entities():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            was_on = state.state == STATE_ON
            self._restore_states[entity_id] = was_on
            if was_on:
                await self.hass.services.async_call(
                    entity_id.split(".", 1)[0], "turn_off", {"entity_id": entity_id}, blocking=True
                )

        duration = float(self._entry.options.get(CONF_FEEDING_DURATION, DEFAULT_FEEDING_DURATION))
        self._auto_off_task = self.hass.async_create_task(self._auto_turn_off(duration * 60))

    async def async_turn_off(self, **kwargs) -> None:
        if not self._is_on:
            return
        if self._auto_off_task and self._auto_off_task is not asyncio.current_task():
            self._auto_off_task.cancel()
        self._auto_off_task = None
        self._is_on = False
        self.async_write_ha_state()

        skimmer = self._entry.options.get(CONF_SKIMMER_ENTITY)
        for entity_id, was_on in list(self._restore_states.items()):
            if not was_on or entity_id == skimmer:
                continue
            await self._turn_on_entity(entity_id)

        if skimmer and self._restore_states.get(skimmer):
            delay = float(self._entry.options.get(CONF_SKIMMER_DELAY, DEFAULT_SKIMMER_DELAY))
            if delay > 0:
                self._skimmer_task = self.hass.async_create_task(self._delayed_turn_on(skimmer, delay * 60))
            else:
                await self._turn_on_entity(skimmer)
        self._restore_states = {}

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_tasks()

    def _pause_entities(self) -> list[str]:
        options = self._entry.options
        pairs = (
            (CONF_SKIMMER_ENTITY, CONF_FEEDING_PAUSE_SKIMMER, True),
            (CONF_RETURN_PUMP_ENTITY, CONF_FEEDING_PAUSE_RETURN_PUMP, False),
            (CONF_FLOW_PUMP_ENTITY, CONF_FEEDING_PAUSE_FLOW_PUMP, True),
            (CONF_ATO_ENTITY, CONF_FEEDING_PAUSE_ATO, True),
        )
        return [options[key] for key, flag, default in pairs if options.get(key) and options.get(flag, default)]

    async def _auto_turn_off(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self.async_turn_off()
        except asyncio.CancelledError:
            pass

    async def _delayed_turn_on(self, entity_id: str, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self._turn_on_entity(entity_id)
        except asyncio.CancelledError:
            pass
        finally:
            self._skimmer_task = None

    async def _turn_on_entity(self, entity_id: str) -> None:
        if self.hass.states.get(entity_id) is None:
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0], "turn_on", {"entity_id": entity_id}, blocking=True
        )

    def _cancel_tasks(self) -> None:
        for task in (self._auto_off_task, self._skimmer_task):
            if task and not task.done():
                task.cancel()
        self._auto_off_task = None
        self._skimmer_task = None
