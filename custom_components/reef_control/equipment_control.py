"""Equipment dependency control for Reef Control."""
from __future__ import annotations

import asyncio
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.event import async_track_state_change_event
from .const import *

class ReefControlEquipmentController:
    """Coordinate equipment that depends on the return pump."""
    def __init__(self,hass,entry):
        self.hass=hass; self.entry=entry; self._remove_listener=None
        self._restart_tasks={}; self._paused_by_controller=set(); self._status="Deaktiviert"
    @property
    def enabled(self): return bool(self.entry.options.get(CONF_EQUIPMENT_CONTROL_ENABLED,DEFAULT_EQUIPMENT_CONTROL_ENABLED))
    def _runtime(self): return self.hass.data.setdefault(DOMAIN,{}).setdefault(self.entry.entry_id,{"entry":self.entry})
    async def async_start(self):
        r=self._runtime(); r["equipment_controller"]=self; r["equipment_control_status"]="Deaktiviert"; r["equipment_paused_entities"]=[]
        watched=[x for x in (self.entry.options.get(CONF_RETURN_PUMP_ENTITY),self.entry.options.get(CONF_SKIMMER_ENTITY),self.entry.options.get(CONF_UVC_ENTITY),self.entry.options.get(CONF_ATO_ENTITY),self.entry.options.get(CONF_FLOW_PUMP_ENTITY)) if x]
        if watched:self._remove_listener=async_track_state_change_event(self.hass,watched,self._state_changed)
        if self.enabled:await self.async_evaluate()
    async def async_stop(self):
        if self._remove_listener:self._remove_listener(); self._remove_listener=None
        self._cancel_restart_tasks()
    async def _state_changed(self,event):
        if not self.enabled:return
        eid=event.data.get("entity_id")
        if eid==self.entry.options.get(CONF_RETURN_PUMP_ENTITY):await self.async_evaluate(); return
        if eid in self._paused_by_controller and not self._return_is_on():
            st=self.hass.states.get(eid)
            if st and st.state==STATE_ON:await self._set(eid,False)
    def _return_is_on(self):
        eid=self.entry.options.get(CONF_RETURN_PUMP_ENTITY); st=self.hass.states.get(eid) if eid else None
        return bool(st and st.state==STATE_ON)
    async def _set(self,eid,on):
        st=self.hass.states.get(eid)
        if not st or st.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):return
        await self.hass.services.async_call(eid.split('.',1)[0],"turn_on" if on else "turn_off",{"entity_id":eid},blocking=True)
    def _set_status(self,status):
        self._status=status; r=self._runtime(); r["equipment_control_status"]=status; r["return_pump_available"]=self._return_is_on(); r["equipment_paused_entities"]=sorted(self._paused_by_controller)
    def _cancel_restart_tasks(self):
        for t in self._restart_tasks.values():
            if t and not t.done():t.cancel()
        self._restart_tasks.clear()
    async def _pause_dependency(self,eid):
        if not eid:return
        st=self.hass.states.get(eid)
        if st and st.state==STATE_ON:self._paused_by_controller.add(eid); await self._set(eid,False)
    async def _restart_after(self,key,eid,seconds):
        try:
            if seconds>0:await asyncio.sleep(seconds)
            r=self._runtime()
            if not self.enabled or not self._return_is_on() or r.get("maintenance_active") or r.get("feeding_active"):return
            if eid in self._paused_by_controller:await self._set(eid,True); self._paused_by_controller.discard(eid)
        except asyncio.CancelledError:pass
        finally:
            self._restart_tasks.pop(key,None); self._set_status("Normalbetrieb" if not self._restart_tasks and self._return_is_on() else "Wiederanlauf")
    def _schedule(self,key,eid,minutes):
        if not eid or eid not in self._paused_by_controller:return
        old=self._restart_tasks.pop(key,None)
        if old and not old.done():old.cancel()
        self._restart_tasks[key]=self.hass.async_create_task(self._restart_after(key,eid,float(minutes)*60))
    async def async_evaluate(self):
        if not self.enabled:self._cancel_restart_tasks(); self._set_status("Deaktiviert"); return
        rid=self.entry.options.get(CONF_RETURN_PUMP_ENTITY)
        if not rid:self._set_status("Nicht konfiguriert"); return
        st=self.hass.states.get(rid)
        if st is None or st.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):self._cancel_restart_tasks(); self._set_status("Rückförderpumpenfehler"); return
        o=self.entry.options
        deps=((CONF_RETURN_MASTER_SKIMMER,DEFAULT_RETURN_MASTER_SKIMMER,CONF_SKIMMER_ENTITY),(CONF_RETURN_MASTER_UVC,DEFAULT_RETURN_MASTER_UVC,CONF_UVC_ENTITY),(CONF_RETURN_MASTER_ATO,DEFAULT_RETURN_MASTER_ATO,CONF_ATO_ENTITY),(CONF_RETURN_MASTER_FLOW,DEFAULT_RETURN_MASTER_FLOW,CONF_FLOW_PUMP_ENTITY))
        if st.state!=STATE_ON:
            self._cancel_restart_tasks()
            for flag,default,e_key in deps:
                if o.get(flag,default):await self._pause_dependency(o.get(e_key))
            self._set_status("Rückförderpumpe aus"); return
        self._set_status("Wiederanlauf")
        if o.get(CONF_RETURN_MASTER_SKIMMER,DEFAULT_RETURN_MASTER_SKIMMER):self._schedule("skimmer",o.get(CONF_SKIMMER_ENTITY),o.get(CONF_EQUIPMENT_SKIMMER_DELAY,DEFAULT_EQUIPMENT_SKIMMER_DELAY))
        if o.get(CONF_RETURN_MASTER_UVC,DEFAULT_RETURN_MASTER_UVC):self._schedule("uvc",o.get(CONF_UVC_ENTITY),o.get(CONF_EQUIPMENT_UVC_DELAY,DEFAULT_EQUIPMENT_UVC_DELAY))
        if o.get(CONF_RETURN_MASTER_FLOW,DEFAULT_RETURN_MASTER_FLOW):self._schedule("flow",o.get(CONF_FLOW_PUMP_ENTITY),o.get(CONF_EQUIPMENT_FLOW_DELAY,DEFAULT_EQUIPMENT_FLOW_DELAY))
        ato=o.get(CONF_ATO_ENTITY)
        if o.get(CONF_RETURN_MASTER_ATO,DEFAULT_RETURN_MASTER_ATO) and ato in self._paused_by_controller:
            self._paused_by_controller.discard(ato); ac=self._runtime().get("ato_control_switch")
            if ac and ac.is_on:await ac.async_evaluate()
        if not self._restart_tasks:self._set_status("Normalbetrieb")
