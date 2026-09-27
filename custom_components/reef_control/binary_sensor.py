"""Binary sensors for Reef Control safety diagnostics."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import callback
from datetime import timedelta
from .const import *

async def async_setup_entry(hass,entry,async_add_entities): async_add_entities([ReefControlSafetyAlert(hass,entry),ReefControlEquipmentInterlock(hass,entry)])
class _Base(BinarySensorEntity):
    _attr_has_entity_name=True; _attr_entity_category=EntityCategory.DIAGNOSTIC; _attr_device_class=BinarySensorDeviceClass.PROBLEM
    def __init__(self,hass,entry): self.hass=hass; self.entry=entry; self._remove=None
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self.entry.entry_id)},name=self.entry.data[CONF_AQUARIUM_NAME],manufacturer="Reef Control",model="Reef Aquarium",sw_version=VERSION)
    def _r(self): return self.hass.data.get(DOMAIN,{}).get(self.entry.entry_id,{})
    async def async_added_to_hass(self):
        @callback
        def upd(_now=None): self.async_write_ha_state()
        self._remove=async_track_time_interval(self.hass,upd,timedelta(seconds=2))
    async def async_will_remove_from_hass(self):
        if self._remove:self._remove(); self._remove=None
class ReefControlSafetyAlert(_Base):
    _attr_name="Sicherheitsalarm"; _attr_icon="mdi:shield-alert"
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_safety_alert"
    @property
    def is_on(self): return bool(self._r().get("safety_reasons"))
    @property
    def extra_state_attributes(self): return {"status":self._r().get("safety_status","Unbekannt"),"reasons":self._r().get("safety_reasons",[])}
class ReefControlEquipmentInterlock(_Base):
    _attr_name="Techniksperre"; _attr_icon="mdi:cog-pause"
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_equipment_interlock"
    @property
    def is_on(self): return bool(self._r().get("equipment_paused_entities"))
    @property
    def extra_state_attributes(self): return {"status":self._r().get("equipment_control_status","Deaktiviert"),"paused_entities":self._r().get("equipment_paused_entities",[]),"return_pump_on":self._r().get("return_pump_available")}
