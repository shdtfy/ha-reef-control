"""Reef Control integration for Home Assistant."""
from __future__ import annotations
from pathlib import Path
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS
from .equipment_control import ReefControlEquipmentController
from .safety_control import ReefControlSafetyController
from .uvc_control import ReefControlUvcController
from .alarm_control import ReefControlAlarmController

CARD_VERSION="0.1.5"
CARD_URL="/reef_control/reef-control-card.js"
CARD_RESOURCE_URL=f"{CARD_URL}?v={CARD_VERSION}"
CARD_FILE=Path(__file__).parent/"www"/"reef-control-card.js"

async def _register_card(hass):
    lovelace=hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode!=MODE_STORAGE:return
    resources=lovelace.resources
    if not isinstance(resources,ResourceStorageCollection):return
    await resources.async_get_info()
    existing=next((x for x in resources.async_items() or [] if str(x.get("url","")).split("?",1)[0]==CARD_URL),None)
    if existing is None: await resources.async_create_item({"res_type":"module","url":CARD_RESOURCE_URL})
    elif existing.get("url")!=CARD_RESOURCE_URL or existing.get("type")!="module":
        await resources.async_update_item(existing["id"],{"res_type":"module","url":CARD_RESOURCE_URL})

async def async_setup(hass:HomeAssistant,config:dict)->bool:
    await hass.http.async_register_static_paths([StaticPathConfig(url_path=CARD_URL,path=str(CARD_FILE),cache_headers=False)])
    add_extra_js_url(hass,CARD_RESOURCE_URL);await _register_card(hass);return True

async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    hass.data.setdefault(DOMAIN,{})[entry.entry_id]={"entry":entry}
    equipment=ReefControlEquipmentController(hass,entry);safety=ReefControlSafetyController(hass,entry);uvc=ReefControlUvcController(hass,entry);alarm=ReefControlAlarmController(hass,entry)
    hass.data[DOMAIN][entry.entry_id].update({"equipment_controller":equipment,"safety_controller":safety,"uvc_controller":uvc,"alarm_controller":alarm})
    await hass.config_entries.async_forward_entry_setups(entry,PLATFORMS)
    await equipment.async_start();await safety.async_start();await uvc.async_start();await alarm.async_start();return True

async def async_unload_entry(hass:HomeAssistant,entry:ConfigEntry)->bool:
    runtime=hass.data.get(DOMAIN,{}).get(entry.entry_id,{})
    for key in ("alarm_controller","uvc_controller","safety_controller","equipment_controller"):
        controller=runtime.get(key)
        if controller:await controller.async_stop()
    ok=await hass.config_entries.async_unload_platforms(entry,PLATFORMS)
    if ok:hass.data[DOMAIN].pop(entry.entry_id,None)
    return ok
