"""Editable number entities for Reef Control."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_AQUARIUM_NAME,
    DOMAIN,
    MANUAL_MEASUREMENTS,
    TC420_CHANNEL_COUNT,
    VERSION,
    get_aquarium_name,
)


async def async_setup_entry(hass, entry, async_add_entities):
    entities = [
        ReefControlManualMeasurement(entry, key, definition)
        for key, definition in MANUAL_MEASUREMENTS.items()
    ]
    entities.extend(
        ReefControlLightChannel(hass, entry, channel)
        for channel in range(1, TC420_CHANNEL_COUNT + 1)
    )
    async_add_entities(entities)


class ReefControlManualMeasurement(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, entry, key, definition):
        self._entry = entry
        self._key = key
        self._definition = definition
        self._attr_unique_id = f"{entry.entry_id}_manual_{key}"
        self._attr_translation_key = f"manual_{key}"
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
            name=get_aquarium_name(self._entry),
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    async def async_added_to_hass(self):
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
        self._attr_native_value = float(value)
        self._last_measurement = datetime.now().astimezone()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        if self._last_measurement is None:
            return {
                "last_measurement": None,
                "measurement_age_days": None,
                "measurement_freshness": "missing",
                "manual_measurement": True,
            }
        now = datetime.now().astimezone()
        measured = self._last_measurement
        if measured.tzinfo is None:
            measured = measured.astimezone()
        age_days = max(0, (now.date() - measured.date()).days)
        if age_days <= 3:
            freshness = "fresh"
        elif age_days <= 7:
            freshness = "aging"
        else:
            freshness = "stale"
        return {
            "last_measurement": measured.isoformat(),
            "measurement_age_days": age_days,
            "measurement_freshness": freshness,
            "manual_measurement": True,
        }


class ReefControlLightChannel(NumberEntity, RestoreEntity):
    """Desired TC420 SEA WATER light output."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_icon = "mdi:led-strip-variant"

    def __init__(self, hass, entry, channel: int):
        self.hass = hass
        self._entry = entry
        self._channel = channel
        self._attr_unique_id = f"{entry.entry_id}_tc420_light_channel_{channel}"
        self._attr_name = f"Licht Kanal {channel}"
        self._attr_native_value = 0.0

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=get_aquarium_name(self._entry),
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    def _store_runtime_value(self) -> None:
        runtime = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        channels = runtime.setdefault("tc420_channels", {})
        channels[self._channel] = float(self._attr_native_value or 0.0)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state is not None:
            try:
                restored = float(old_state.state)
            except (TypeError, ValueError):
                restored = 0.0
            self._attr_native_value = max(0.0, min(100.0, restored))
        self._store_runtime_value()

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = max(0.0, min(100.0, float(value)))
        self._store_runtime_value()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {
            "tc420_channel": self._channel,
            "setpoint": True,
            "physical_readback": False,
            "profile": "SEA WATER",
        }
