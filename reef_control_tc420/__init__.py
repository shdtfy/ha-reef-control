"""Reef Control integration for Home Assistant."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .alarm_control import ReefControlAlarmController
from .const import DOMAIN, PLATFORMS, TC420_CHANNEL_COUNT
from .equipment_control import ReefControlEquipmentController
from .safety_control import ReefControlSafetyController
from .uvc_control import ReefControlUvcController

CARD_VERSION = "0.1.6"
CARD_URL = "/reef_control/reef-control-card.js"
CARD_RESOURCE_URL = f"{CARD_URL}?v={CARD_VERSION}"
CARD_FILE = Path(__file__).parent / "www" / "reef-control-card.js"


def _first_runtime(hass: HomeAssistant, entry_id: str | None = None):
    domain_data = hass.data.get(DOMAIN, {})
    if entry_id:
        runtime = domain_data.get(entry_id)
        if isinstance(runtime, dict) and runtime.get("entry") is not None:
            return entry_id, runtime
    for candidate_id, runtime in domain_data.items():
        if isinstance(runtime, dict) and runtime.get("entry") is not None:
            return candidate_id, runtime
    return None, None


class ReefControlTc420BridgeView(HomeAssistantView):
    """Internal API used by the Reef Control TC420 Home Assistant app."""

    url = "/api/reef_control/tc420/bridge"
    name = "api:reef_control:tc420:bridge"
    requires_auth = True

    async def get(self, request):
        hass: HomeAssistant = request.app[KEY_HASS]
        entry_id, runtime = _first_runtime(hass)
        if runtime is None:
            return self.json(
                {"error": "No loaded Reef Control aquarium found"},
                status_code=503,
            )

        channels = runtime.setdefault(
            "tc420_channels",
            {channel: 0.0 for channel in range(1, TC420_CHANNEL_COUNT + 1)},
        )

        return self.json(
            {
                "entry_id": entry_id,
                "channel_count": TC420_CHANNEL_COUNT,
                "channels": [
                    float(channels.get(channel, 0.0))
                    for channel in range(1, TC420_CHANNEL_COUNT + 1)
                ],
            }
        )

    async def post(self, request):
        hass: HomeAssistant = request.app[KEY_HASS]
        try:
            payload = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)

        entry_id, runtime = _first_runtime(
            hass,
            str(payload.get("entry_id") or "") or None,
        )
        if runtime is None:
            return self.json(
                {"error": "No loaded Reef Control aquarium found"},
                status_code=503,
            )

        runtime["tc420_bridge_connected"] = bool(payload.get("connected", False))
        runtime["tc420_bridge_status"] = str(payload.get("status", "unknown"))
        runtime["tc420_bridge_last_error"] = payload.get("last_error")
        runtime["tc420_bridge_last_seen"] = dt_util.utcnow()

        active = payload.get("active_channels")
        if isinstance(active, list):
            runtime["tc420_bridge_active_channels"] = active[:TC420_CHANNEL_COUNT]

        return self.json({"ok": True, "entry_id": entry_id})


async def _register_card(hass):
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
        return
    resources = lovelace.resources
    if not isinstance(resources, ResourceStorageCollection):
        return
    await resources.async_get_info()
    existing = next(
        (
            item
            for item in resources.async_items() or []
            if str(item.get("url", "")).split("?", 1)[0] == CARD_URL
        ),
        None,
    )
    if existing is None:
        await resources.async_create_item(
            {"res_type": "module", "url": CARD_RESOURCE_URL}
        )
    elif existing.get("url") != CARD_RESOURCE_URL or existing.get("type") != "module":
        await resources.async_update_item(
            existing["id"],
            {"res_type": "module", "url": CARD_RESOURCE_URL},
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                url_path=CARD_URL,
                path=str(CARD_FILE),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, CARD_RESOURCE_URL)
    await _register_card(hass)
    hass.http.register_view(ReefControlTc420BridgeView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "tc420_channels": {
            channel: 0.0 for channel in range(1, TC420_CHANNEL_COUNT + 1)
        },
        "tc420_bridge_connected": False,
        "tc420_bridge_status": "waiting",
        "tc420_bridge_last_error": None,
        "tc420_bridge_last_seen": None,
        "tc420_bridge_active_channels": [0.0] * TC420_CHANNEL_COUNT,
    }

    equipment = ReefControlEquipmentController(hass, entry)
    safety = ReefControlSafetyController(hass, entry)
    uvc = ReefControlUvcController(hass, entry)
    alarm = ReefControlAlarmController(hass, entry)

    hass.data[DOMAIN][entry.entry_id].update(
        {
            "equipment_controller": equipment,
            "safety_controller": safety,
            "uvc_controller": uvc,
            "alarm_controller": alarm,
        }
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await equipment.async_start()
    await safety.async_start()
    await uvc.async_start()
    await alarm.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    for key in (
        "alarm_controller",
        "uvc_controller",
        "safety_controller",
        "equipment_controller",
    ):
        controller = runtime.get(key)
        if controller:
            await controller.async_stop()

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
