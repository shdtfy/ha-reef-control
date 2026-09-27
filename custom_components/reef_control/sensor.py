"""Sensor platform for Reef Control."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

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
        ]
    )


class ReefControlAquariumSensor(SensorEntity):
    """Represent the Reef Control aquarium."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:fishbowl-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the aquarium sensor."""
        self._entry = entry

        self._attr_unique_id = f"{entry.entry_id}_aquarium"
        self._attr_name = "Aquarium"

    @property
    def native_value(self) -> str:
        """Return the aquarium name."""
        return self._entry.data[CONF_AQUARIUM_NAME]

    @property
    def extra_state_attributes(self) -> dict:
        """Return aquarium information."""
        return {
            "volume_l": self._entry.data[CONF_VOLUME],
            "tank_type": self._entry.data.get(CONF_TANK_TYPE, "mixed_reef"),
            "supply_system": self._entry.data.get(CONF_SUPPLY_SYSTEM, "none"),
            "reef_method": self._entry.data.get(CONF_REEF_METHOD, "none"),
            "reef_control_version": VERSION,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        aquarium_name = self._entry.data[CONF_AQUARIUM_NAME]

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=aquarium_name,
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )
