"""Central safety interlocks for Reef Control."""
from __future__ import annotations
from homeassistant.const import STATE_ON, STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.helpers.event import async_track_state_change_event
from .const import *

class ReefControlSafetyController:
    def __init__(self,hass,entry): self.hass=hass; self.entry=entry; self._remove=None
    def _r(self): return self.hass.data.setdefault(DOMAIN,{}).setdefault(self.entry.entry_id,{"entry":self.entry})
    @property
    def enabled(self): return bool(self.entry.options.get(CONF_SAFETY_CONTROL_ENABLED,DEFAULT_SAFETY_CONTROL_ENABLED))
    async def async_start(self):
        r=self._r(); r["safety_controller"]=self; r["safety_status"]="Bereit" if self.enabled else "Deaktiviert"; r["safety_reasons"]=[]
        temp=self.entry.options.get(CONF_TEMPERATURE_ENTITY)
        if temp:self._remove=async_track_state_change_event(self.hass,[temp],self._changed)
        await self.async_evaluate()
    async def async_stop(self):
        if self._remove:self._remove(); self._remove=None
    async def _changed(self,event): await self.async_evaluate()
    async def _heater_off(self):
        eid=self.entry.options.get(CONF_HEATER_ENTITY); st=self.hass.states.get(eid) if eid else None
        if st and st.state==STATE_ON:await self.hass.services.async_call(eid.split('.',1)[0],"turn_off",{"entity_id":eid},blocking=True)
    async def async_evaluate(self):
        r=self._r(); reasons=[]
        if not self.enabled:r["safety_status"]="Deaktiviert"; r["safety_reasons"]=[]; return
        temp_id=self.entry.options.get(CONF_TEMPERATURE_ENTITY); st=self.hass.states.get(temp_id) if temp_id else None
        if temp_id and (st is None or st.state in (STATE_UNKNOWN,STATE_UNAVAILABLE)):
            reasons.append("Temperatursensor nicht verfügbar")
            if self.entry.options.get(CONF_SAFETY_HEATER_SENSOR_FAIL,DEFAULT_SAFETY_HEATER_SENSOR_FAIL):await self._heater_off()
        elif st is not None:
            try:
                value=float(str(st.state).replace(',','.')); critical=float(self.entry.options.get(CONF_TEMPERATURE_CRITICAL_MAX,DEFAULT_TEMPERATURE_CRITICAL_MAX))
                if value>=critical:
                    reasons.append(f"Temperatur kritisch hoch ({value:g} °C)")
                    if self.entry.options.get(CONF_SAFETY_HEATER_HIGH_TEMP,DEFAULT_SAFETY_HEATER_HIGH_TEMP):await self._heater_off()
            except (TypeError,ValueError):
                reasons.append("Temperatursensor ungültig")
                if self.entry.options.get(CONF_SAFETY_HEATER_SENSOR_FAIL,DEFAULT_SAFETY_HEATER_SENSOR_FAIL):await self._heater_off()
        ato=r.get("ato_control_switch")
        if ato and getattr(ato,"_locked",False):reasons.append("ATO Sicherheitsstopp")
        eq=r.get("equipment_control_status")
        if eq=="Rückförderpumpenfehler":reasons.append("Rückförderpumpe nicht verfügbar")
        r["safety_reasons"]=reasons; r["safety_status"]="Sicherheitsstopp" if reasons else "Bereit"
