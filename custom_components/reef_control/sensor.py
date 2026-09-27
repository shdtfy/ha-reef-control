"""Sensor platform for Reef Control."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_AQUARIUM_NAME,
    CONF_REEF_METHOD,
    CONF_SUPPLY_SYSTEM,
    CONF_TANK_TYPE,
    CONF_VOLUME,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Reef Control sensors from a config entry."""
    async_add_entities(
        [
            ReefControlAquariumSensor(entry),
            ReefControlOperatingStatusSensor(hass, entry),
            ReefControlRemainingTimeSensor(hass, entry),
        ]
    )


class ReefControlBaseSensor(SensorEntity):
    """Base class for Reef Control sensors."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )


class ReefControlAquariumSensor(ReefControlBaseSensor):
    """Represent the Reef Control aquarium."""

    _attr_icon = "mdi:fishbowl-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_aquarium"
        self._attr_name = "Aquarium"

    @property
    def native_value(self) -> str:
        return self._entry.data[CONF_AQUARIUM_NAME]

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "volume_l": self._entry.data[CONF_VOLUME],
            "tank_type": self._entry.data.get(CONF_TANK_TYPE, "mixed_reef"),
            "supply_system": self._entry.data.get(CONF_SUPPLY_SYSTEM, "none"),
            "reef_method": self._entry.data.get(CONF_REEF_METHOD, "none"),
            "reef_control_version": VERSION,
        }


class ReefControlRuntimeSensor(ReefControlBaseSensor):
    """Base sensor reading Reef Control runtime data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self.hass = hass
        self._remove_interval = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _update(_now=None) -> None:
            self.async_write_ha_state()

        self._remove_interval = async_track_time_interval(
            self.hass,
            _update,
            timedelta(seconds=1),
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_interval:
            self._remove_interval()
            self._remove_interval = None

    def _runtime(self) -> dict:
        return self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})


class ReefControlOperatingStatusSensor(ReefControlRuntimeSensor):
    """Show the current Reef Control operating status."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_status"
        self._attr_name = "Betriebsstatus"

    @property
    def native_value(self) -> str:
        runtime = self._runtime()

        if runtime.get("maintenance_active"):
            return "Wartung"

        if runtime.get("feeding_active"):
            return "Fütterung"

        skimmer_until = runtime.get("skimmer_delay_until")
        if skimmer_until and skimmer_until > datetime.now().astimezone():
            return "Abschäumer-Verzögerung"

        return "Normalbetrieb"

    @property
    def icon(self) -> str:
        state = self.native_value
        if state == "Wartung":
            return "mdi:tools"
        if state == "Fütterung":
            return "mdi:fish-food"
        if state == "Abschäumer-Verzögerung":
            return "mdi:timer-sand"
        return "mdi:check-circle-outline"


class ReefControlRemainingTimeSensor(ReefControlRuntimeSensor):
    """Show remaining feeding or skimmer delay time."""

    _attr_icon = "mdi:timer-outline"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_remaining"
        self._attr_name = "Restzeit"

    @property
    def native_value(self) -> str:
        runtime = self._runtime()

        if runtime.get("maintenance_active"):
            return "00:00"

        target = (
            runtime.get("feeding_until")
            if runtime.get("feeding_active")
            else runtime.get("skimmer_delay_until")
        )
        if not target:
            return "00:00"

        remaining = max(
            0,
            int((target - datetime.now().astimezone()).total_seconds()),
        )
        minutes, seconds = divmod(remaining, 60)
        return f"{minutes:02d}:{seconds:02d}"
