"""Binary sensors for Reef Control safety diagnostics."""
from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import *


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            ReefControlSafetyAlert(hass, entry),
            ReefControlEquipmentInterlock(hass, entry),
            ReefControlLeakAlert(hass, entry),
            ReefControlTc420BridgeConnected(hass, entry),
        ]
    )


class _Base(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._remove = None

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    def _r(self):
        return self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {})

    async def async_added_to_hass(self):
        @callback
        def upd(_now=None):
            self.async_write_ha_state()

        self._remove = async_track_time_interval(
            self.hass,
            upd,
            timedelta(seconds=2),
        )

    async def async_will_remove_from_hass(self):
        if self._remove:
            self._remove()
            self._remove = None


class ReefControlSafetyAlert(_Base):
    _attr_name = "Sicherheitsalarm"
    _attr_icon = "mdi:shield-alert"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_safety_alert"

    @property
    def is_on(self):
        return bool(self._r().get("safety_reasons"))

    @property
    def extra_state_attributes(self):
        return {
            "status": self._r().get("safety_status", "Unbekannt"),
            "reasons": self._r().get("safety_reasons", []),
        }


class ReefControlEquipmentInterlock(_Base):
    _attr_name = "Techniksperre"
    _attr_icon = "mdi:cog-pause"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_equipment_interlock"

    @property
    def is_on(self):
        return bool(self._r().get("equipment_paused_entities"))

    @property
    def extra_state_attributes(self):
        return {
            "status": self._r().get("equipment_control_status", "Deaktiviert"),
            "paused_entities": self._r().get("equipment_paused_entities", []),
            "return_pump_on": self._r().get("return_pump_available"),
        }


class ReefControlLeakAlert(_Base):
    _attr_name = "Leckagealarm"
    _attr_icon = "mdi:water-alert"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_leak_alert"

    @property
    def is_on(self):
        runtime = self._r()
        return bool(runtime.get("leak_detected") or runtime.get("leak_latched"))

    @property
    def extra_state_attributes(self):
        runtime = self._r()
        return {
            "leak_detected": bool(runtime.get("leak_detected")),
            "latched": bool(runtime.get("leak_latched")),
            "source_entity": self.entry.options.get(CONF_LEAK_ENTITY),
            "source_state": runtime.get("leak_source_state"),
            "active_state": self.entry.options.get(
                CONF_LEAK_ACTIVE_STATE,
                DEFAULT_LEAK_ACTIVE_STATE,
            ),
        }


class ReefControlTc420BridgeConnected(_Base):
    """Reports whether the TC420 bridge is actively communicating."""

    _attr_name = "TC420 Bridge"
    _attr_icon = "mdi:usb"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_tc420_bridge_connected"

    @property
    def is_on(self):
        runtime = self._r()
        last_seen = runtime.get("tc420_bridge_last_seen")
        if not runtime.get("tc420_bridge_connected") or last_seen is None:
            return False
        return (dt_util.utcnow() - last_seen).total_seconds() <= 12

    @property
    def extra_state_attributes(self):
        runtime = self._r()
        last_seen = runtime.get("tc420_bridge_last_seen")
        return {
            "status": runtime.get("tc420_bridge_status", "waiting"),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "last_error": runtime.get("tc420_bridge_last_error"),
            "active_channels": runtime.get(
                "tc420_bridge_active_channels",
                [0.0] * TC420_CHANNEL_COUNT,
            ),
            "channel_count": TC420_CHANNEL_COUNT,
            "profile": "SEA WATER",
        }
