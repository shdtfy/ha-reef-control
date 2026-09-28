"""Reef Control integration for Home Assistant."""
from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS
from .equipment_control import ReefControlEquipmentController
from .safety_control import ReefControlSafetyController
from .uvc_control import ReefControlUvcController
from .alarm_control import ReefControlAlarmController

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"entry": entry}
    equipment = ReefControlEquipmentController(hass, entry)
    safety = ReefControlSafetyController(hass, entry)
    uvc = ReefControlUvcController(hass, entry)
    alarm = ReefControlAlarmController(hass, entry)
    hass.data[DOMAIN][entry.entry_id].update({
        "equipment_controller": equipment,
        "safety_controller": safety,
        "uvc_controller": uvc,
        "alarm_controller": alarm,
    })
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await equipment.async_start()
    await safety.async_start()
    await uvc.async_start()
    await alarm.async_start()
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    for key in ("alarm_controller", "uvc_controller", "safety_controller", "equipment_controller"):
        controller = runtime.get(key)
        if controller:
            await controller.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
