"""Editable manual water measurements for Reef Control."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_AQUARIUM_NAME,
    DOMAIN,
    MANUAL_MEASUREMENTS,
    VERSION,
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up manual Reef Control measurements."""
    async_add_entities(
        ReefControlManualMeasurement(entry, key, definition)
        for key, definition in MANUAL_MEASUREMENTS.items()
    )


class ReefControlManualMeasurement(NumberEntity, RestoreEntity):
    """A manually entered water measurement with persistent history metadata."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, entry, key, definition):
        self._entry = entry
        self._key = key
        self._definition = definition
        self._attr_unique_id = f"{entry.entry_id}_manual_{key}"
        self._attr_name = definition["name"]
        self._attr_icon = definition["icon"]
        self._attr_native_unit_of_measurement = definition["unit"]
        self._attr_native_min_value = definition["min"]
        self._attr_native_max_value = definition["max"]
        self._attr_native_step = definition["step"]
        self._attr_native_value = None
        self._last_measurement = None

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self):
        """Restore the last value and its measurement timestamp."""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state is None:
            return

        try:
            self._attr_native_value = float(old_state.state)
        except (TypeError, ValueError):
            self._attr_native_value = None

        last_measurement = old_state.attributes.get("last_measurement")
        if last_measurement:
            try:
                self._last_measurement = datetime.fromisoformat(str(last_measurement))
            except (TypeError, ValueError):
                self._last_measurement = None

    async def async_set_native_value(self, value: float) -> None:
        """Record a new manual measurement."""
        self._attr_native_value = float(value)
        self._last_measurement = datetime.now().astimezone()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        if self._last_measurement is None:
            return {
                "last_measurement": None,
                "measurement_age_days": None,
                "manual_measurement": True,
            }

        now = datetime.now().astimezone()
        measured = self._last_measurement
        if measured.tzinfo is None:
            measured = measured.astimezone()

        age_days = max(0, (now.date() - measured.date()).days)
        return {
            "last_measurement": measured.isoformat(),
            "measurement_age_days": age_days,
            "manual_measurement": True,
        }
