"""Reef Control integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .equipment_control import ReefControlEquipmentController


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Reef Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry}

    equipment_controller = ReefControlEquipmentController(hass, entry)
    hass.data[DOMAIN][entry.entry_id]["equipment_controller"] = equipment_controller

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await equipment_controller.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Reef Control config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    controller = runtime.get("equipment_controller")
    if controller:
        await controller.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
