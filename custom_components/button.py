"""Button platform for Reef Control."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AQUARIUM_NAME,
    CONF_WATER_LEVEL_ENTITY,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ReefControlAlarmResetButton(hass, entry)])


class ReefControlAlarmResetButton(ButtonEntity):
    """Reset latched Reef Control safety alarms when their cause is gone."""

    _attr_has_entity_name = True
    _attr_name = "Alarm zurücksetzen"
    _attr_icon = "mdi:alarm-light-off"

    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_alarm_reset"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    def _runtime(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self._entry.entry_id, {"entry": self._entry}
        )

    @property
    def extra_state_attributes(self):
        runtime = self._runtime()
        ato = runtime.get("ato_control_switch")
        return {
            "reset_available": bool(
                runtime.get("leak_latched")
                or (ato and getattr(ato, "_locked", False))
            ),
            "leak_detected": bool(runtime.get("leak_detected", False)),
            "leak_latched": bool(runtime.get("leak_latched", False)),
            "ato_locked": bool(ato and getattr(ato, "_locked", False)),
            "last_reset_status": runtime.get("alarm_reset_status"),
            "last_reset_at": runtime.get("alarm_reset_at"),
        }

    async def async_press(self) -> None:
        runtime = self._runtime()
        safety = runtime.get("safety_controller")
        ato = runtime.get("ato_control_switch")

        reset_any = False
        blocked = []

        # Leak protection is intentionally latched. It may only be reset after
        # the leak input itself is no longer active.
        if safety and getattr(safety, "_leak_latched", False):
            leak_active, _ = safety._leak_is_active()
            if leak_active:
                blocked.append("Leckage weiterhin aktiv")
            else:
                safety._leak_latched = False
                runtime["leak_latched"] = False
                reset_any = True

        # The ATO runtime safety stop is also a latch. Do not reset it while the
        # water-level input still reports the low state or is unavailable.
        if ato and getattr(ato, "_locked", False):
            sensor_id = self._entry.options.get(CONF_WATER_LEVEL_ENTITY)
            level = self.hass.states.get(sensor_id) if sensor_id else None

            if level is None or level.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                blocked.append("Wasserstand nicht verfügbar")
            elif hasattr(ato, "_is_low") and ato._is_low(level.state):
                blocked.append("Wasserstand weiterhin niedrig")
            else:
                ato._locked = False
                reset_any = True
                if ato.is_on:
                    await ato.async_evaluate()

        # Re-evaluate safety and alarms immediately so the card updates without
        # waiting for the periodic two-second cycle.
        if safety:
            await safety.async_evaluate()

        alarm = runtime.get("alarm_controller")
        if alarm:
            await alarm.async_evaluate()

        if reset_any and blocked:
            status = "Teilweise zurückgesetzt: " + "; ".join(blocked)
        elif reset_any:
            status = "Zurückgesetzt"
        elif blocked:
            status = "Nicht möglich: " + "; ".join(blocked)
        else:
            status = "Kein verriegelter Alarm"

        runtime["alarm_reset_status"] = status
        runtime["alarm_reset_at"] = dt_util.utcnow().isoformat()
        self.async_write_ha_state()
