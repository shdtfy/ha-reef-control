"""Switch platform for Reef Control."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

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
    CONF_FEEDING_PAUSE_UVC,
    CONF_FLOW_PUMP_ENTITY,
    CONF_HEATER_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_MAINTENANCE_PAUSE_ATO,
    CONF_MAINTENANCE_PAUSE_FLOW_PUMP,
    CONF_MAINTENANCE_PAUSE_HEATER,
    CONF_MAINTENANCE_PAUSE_LIGHT,
    CONF_MAINTENANCE_PAUSE_RETURN_PUMP,
    CONF_MAINTENANCE_PAUSE_SKIMMER,
    CONF_MAINTENANCE_PAUSE_UVC,
    CONF_RETURN_PUMP_ENTITY,
    CONF_SKIMMER_DELAY,
    CONF_SKIMMER_ENTITY,
    CONF_UVC_ENTITY,
    DEFAULT_FEEDING_DURATION,
    DEFAULT_SKIMMER_DELAY,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Reef Control switches."""
    feeding_switch = ReefControlFeedingModeSwitch(hass, entry)
    maintenance_switch = ReefControlMaintenanceModeSwitch(hass, entry)

    runtime = hass.data.setdefault(DOMAIN, {}).setdefault(
        entry.entry_id,
        {"entry": entry},
    )
    runtime["feeding_switch"] = feeding_switch
    runtime["maintenance_switch"] = maintenance_switch
    runtime.setdefault("feeding_active", False)
    runtime.setdefault("feeding_until", None)
    runtime.setdefault("skimmer_delay_until", None)
    runtime.setdefault("maintenance_active", False)

    async_add_entities([feeding_switch, maintenance_switch])


class ReefControlBaseSwitch(SwitchEntity):
    """Base switch for Reef Control operating modes."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._is_on = False
        self._restore_states: dict[str, bool] = {}

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

    def _runtime(self) -> dict:
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self._entry.entry_id,
            {"entry": self._entry},
        )

    async def _turn_off_entity(self, entity_id: str) -> None:
        if self.hass.states.get(entity_id) is None:
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def _turn_on_entity(self, entity_id: str) -> None:
        if self.hass.states.get(entity_id) is None:
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def _pause_entities(
        self,
        entity_ids: list[str],
        force_restore_on: set[str] | None = None,
    ) -> None:
        force_restore_on = force_restore_on or set()
        self._restore_states = {}

        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            was_on = state.state == STATE_ON or entity_id in force_restore_on
            self._restore_states[entity_id] = was_on

            if state.state == STATE_ON:
                await self._turn_off_entity(entity_id)

    async def _restore_entities(self) -> None:
        for entity_id, was_on in list(self._restore_states.items()):
            if was_on:
                await self._turn_on_entity(entity_id)
        self._restore_states = {}


class ReefControlFeedingModeSwitch(ReefControlBaseSwitch):
    """Feeding mode for an aquarium."""

    _attr_name = "Fütterungsmodus"
    _attr_icon = "mdi:fish-food"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_mode"
        self._auto_off_task: asyncio.Task | None = None
        self._skimmer_task: asyncio.Task | None = None

    async def async_turn_on(self, **kwargs) -> None:
        if self._is_on:
            return

        runtime = self._runtime()

        maintenance_switch = runtime.get("maintenance_switch")
        if maintenance_switch and maintenance_switch.is_on:
            await maintenance_switch.async_turn_off()

        pending_skimmer_restore = self.cancel_skimmer_delay()
        self._cancel_auto_off_task()

        self._is_on = True
        duration = float(
            self._entry.options.get(
                CONF_FEEDING_DURATION,
                DEFAULT_FEEDING_DURATION,
            )
        )

        runtime["feeding_active"] = True
        runtime["feeding_until"] = datetime.now().astimezone() + timedelta(
            minutes=duration
        )
        runtime["maintenance_active"] = False
        self.async_write_ha_state()

        skimmer = self._entry.options.get(CONF_SKIMMER_ENTITY)
        force_restore_on: set[str] = set()
        if pending_skimmer_restore and skimmer:
            force_restore_on.add(skimmer)

        await self._pause_entities(
            self._feeding_pause_entities(),
            force_restore_on,
        )

        self._auto_off_task = self.hass.async_create_task(
            self._auto_turn_off(duration * 60)
        )

    async def async_turn_off(self, **kwargs) -> None:
        if not self._is_on:
            return

        self._cancel_auto_off_task()

        self._is_on = False
        runtime = self._runtime()
        runtime["feeding_active"] = False
        runtime["feeding_until"] = None
        self.async_write_ha_state()

        skimmer = self._entry.options.get(CONF_SKIMMER_ENTITY)

        for entity_id, was_on in list(self._restore_states.items()):
            if not was_on or entity_id == skimmer:
                continue
            await self._turn_on_entity(entity_id)

        if skimmer and self._restore_states.get(skimmer):
            delay = float(
                self._entry.options.get(
                    CONF_SKIMMER_DELAY,
                    DEFAULT_SKIMMER_DELAY,
                )
            )
            if delay > 0:
                runtime["skimmer_delay_until"] = (
                    datetime.now().astimezone() + timedelta(minutes=delay)
                )
                self._skimmer_task = self.hass.async_create_task(
                    self._delayed_turn_on(skimmer, delay * 60)
                )
            else:
                runtime["skimmer_delay_until"] = None
                await self._turn_on_entity(skimmer)
        else:
            runtime["skimmer_delay_until"] = None

        self._restore_states = {}

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_auto_off_task()
        self.cancel_skimmer_delay()

    def cancel_skimmer_delay(self) -> bool:
        """Cancel a pending skimmer restart and return whether it was pending."""
        pending = bool(self._skimmer_task and not self._skimmer_task.done())

        if pending:
            self._skimmer_task.cancel()

        self._skimmer_task = None
        self._runtime()["skimmer_delay_until"] = None
        return pending

    def _feeding_pause_entities(self) -> list[str]:
        options = self._entry.options
        pairs = (
            (CONF_SKIMMER_ENTITY, CONF_FEEDING_PAUSE_SKIMMER, True),
            (CONF_RETURN_PUMP_ENTITY, CONF_FEEDING_PAUSE_RETURN_PUMP, False),
            (CONF_FLOW_PUMP_ENTITY, CONF_FEEDING_PAUSE_FLOW_PUMP, True),
            (CONF_UVC_ENTITY, CONF_FEEDING_PAUSE_UVC, False),
            (CONF_ATO_ENTITY, CONF_FEEDING_PAUSE_ATO, True),
        )
        return [
            options[key]
            for key, flag, default in pairs
            if options.get(key) and options.get(flag, default)
        ]

    async def _auto_turn_off(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self.async_turn_off()
        except asyncio.CancelledError:
            pass

    async def _delayed_turn_on(
        self,
        entity_id: str,
        seconds: float,
    ) -> None:
        try:
            await asyncio.sleep(seconds)
            await self._turn_on_entity(entity_id)
        except asyncio.CancelledError:
            pass
        finally:
            self._runtime()["skimmer_delay_until"] = None
            self._skimmer_task = None

    def _cancel_auto_off_task(self) -> None:
        if self._auto_off_task and not self._auto_off_task.done():
            self._auto_off_task.cancel()
        self._auto_off_task = None


class ReefControlMaintenanceModeSwitch(ReefControlBaseSwitch):
    """Maintenance mode for an aquarium."""

    _attr_name = "Wartungsmodus"
    _attr_icon = "mdi:tools"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_maintenance_mode"

    async def async_turn_on(self, **kwargs) -> None:
        if self._is_on:
            return

        runtime = self._runtime()
        feeding_switch = runtime.get("feeding_switch")

        if feeding_switch and feeding_switch.is_on:
            await feeding_switch.async_turn_off()

        pending_skimmer_restore = False
        if feeding_switch:
            pending_skimmer_restore = feeding_switch.cancel_skimmer_delay()

        self._is_on = True
        runtime["maintenance_active"] = True
        runtime["feeding_active"] = False
        runtime["feeding_until"] = None
        self.async_write_ha_state()

        skimmer = self._entry.options.get(CONF_SKIMMER_ENTITY)
        force_restore_on: set[str] = set()
        if pending_skimmer_restore and skimmer:
            force_restore_on.add(skimmer)

        await self._pause_entities(
            self._maintenance_pause_entities(),
            force_restore_on,
        )

    async def async_turn_off(self, **kwargs) -> None:
        if not self._is_on:
            return

        self._is_on = False
        self._runtime()["maintenance_active"] = False
        self.async_write_ha_state()

        await self._restore_entities()

    def _maintenance_pause_entities(self) -> list[str]:
        options = self._entry.options
        pairs = (
            (CONF_SKIMMER_ENTITY, CONF_MAINTENANCE_PAUSE_SKIMMER, True),
            (CONF_RETURN_PUMP_ENTITY, CONF_MAINTENANCE_PAUSE_RETURN_PUMP, True),
            (CONF_FLOW_PUMP_ENTITY, CONF_MAINTENANCE_PAUSE_FLOW_PUMP, True),
            (CONF_UVC_ENTITY, CONF_MAINTENANCE_PAUSE_UVC, True),
            (CONF_ATO_ENTITY, CONF_MAINTENANCE_PAUSE_ATO, True),
            (CONF_HEATER_ENTITY, CONF_MAINTENANCE_PAUSE_HEATER, True),
            (CONF_LIGHT_ENTITY, CONF_MAINTENANCE_PAUSE_LIGHT, False),
        )
        return [
            options[key]
            for key, flag, default in pairs
            if options.get(key) and options.get(flag, default)
        ]
