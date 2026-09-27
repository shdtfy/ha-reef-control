"""Switch platform for Reef Control."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from .const import *

async def async_setup_entry(hass,entry,async_add_entities):
    feeding=ReefControlFeedingModeSwitch(hass,entry)
    maintenance=ReefControlMaintenanceModeSwitch(hass,entry)
    temperature=ReefControlTemperatureControlSwitch(hass,entry)
    ato=ReefControlAtoControlSwitch(hass,entry)
    r=hass.data.setdefault(DOMAIN,{}).setdefault(entry.entry_id,{"entry":entry})
    r.update({"feeding_switch":feeding,"maintenance_switch":maintenance,"temperature_control_switch":temperature,"ato_control_switch":ato})
    r.setdefault("feeding_active",False); r.setdefault("feeding_until",None); r.setdefault("skimmer_delay_until",None)
    r.setdefault("maintenance_active",False); r.setdefault("temperature_control_status","Deaktiviert"); r.setdefault("ato_control_status","Deaktiviert")
    async_add_entities([feeding,maintenance,temperature,ato])

class ReefControlBaseSwitch(SwitchEntity):
    _attr_has_entity_name=True
    def __init__(self,hass,entry): self.hass=hass; self._entry=entry; self._is_on=False; self._restore_states={}
    @property
    def is_on(self): return self._is_on
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id)},name=self._entry.data[CONF_AQUARIUM_NAME],manufacturer="Reef Control",model="Reef Aquarium",sw_version=VERSION)
    def _runtime(self): return self.hass.data.setdefault(DOMAIN,{}).setdefault(self._entry.entry_id,{"entry":self._entry})
    async def _set(self,eid,on):
        if self.hass.states.get(eid): await self.hass.services.async_call(eid.split('.',1)[0],"turn_on" if on else "turn_off",{"entity_id":eid},blocking=True)
    async def _pause_entities(self,ids,force_restore_on=None):
        force_restore_on=force_restore_on or set(); self._restore_states={}
        for eid in ids:
            st=self.hass.states.get(eid)
            if not st: continue
            was=st.state==STATE_ON or eid in force_restore_on; self._restore_states[eid]=was
            if st.state==STATE_ON: await self._set(eid,False)
    async def _restore_entities(self,skip_ids=None):
        skip_ids=skip_ids or set()
        for eid,was in list(self._restore_states.items()):
            if was and eid not in skip_ids: await self._set(eid,True)
        self._restore_states={}

class ReefControlFeedingModeSwitch(ReefControlBaseSwitch):
    _attr_name="Fütterungsmodus"; _attr_icon="mdi:fish"
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_feeding_mode"; self._auto_off_task=None; self._skimmer_task=None
    async def async_turn_on(self,**kwargs):
        if self._is_on:return
        r=self._runtime(); m=r.get("maintenance_switch")
        if m and m.is_on: await m.async_turn_off()
        pending=self.cancel_skimmer_delay(); self._cancel_auto_off_task(); self._is_on=True
        duration=float(self._entry.options.get(CONF_FEEDING_DURATION,DEFAULT_FEEDING_DURATION)); r["feeding_active"]=True; r["feeding_until"]=datetime.now().astimezone()+timedelta(minutes=duration); r["maintenance_active"]=False; self.async_write_ha_state()
        skimmer=self._entry.options.get(CONF_SKIMMER_ENTITY); force={skimmer} if pending and skimmer else set(); await self._pause_entities(self._feeding_pause_entities(),force); self._auto_off_task=self.hass.async_create_task(self._auto_turn_off(duration*60))
    async def async_turn_off(self,**kwargs):
        if not self._is_on:return
        self._cancel_auto_off_task(); self._is_on=False; r=self._runtime(); r["feeding_active"]=False; r["feeding_until"]=None; self.async_write_ha_state()
        skimmer=self._entry.options.get(CONF_SKIMMER_ENTITY); ato_id=self._entry.options.get(CONF_ATO_ENTITY); ato_controller=r.get("ato_control_switch")
        for eid,was in list(self._restore_states.items()):
            if was and eid!=skimmer and not (eid==ato_id and ato_controller and ato_controller.is_on): await self._set(eid,True)
        if skimmer and self._restore_states.get(skimmer):
            delay=float(self._entry.options.get(CONF_SKIMMER_DELAY,DEFAULT_SKIMMER_DELAY))
            if delay>0: r["skimmer_delay_until"]=datetime.now().astimezone()+timedelta(minutes=delay); self._skimmer_task=self.hass.async_create_task(self._delayed_turn_on(skimmer,delay*60))
            else: r["skimmer_delay_until"]=None; await self._set(skimmer,True)
        else:r["skimmer_delay_until"]=None
        self._restore_states={}
        if ato_controller and ato_controller.is_on: await ato_controller.async_evaluate()
    async def async_will_remove_from_hass(self): self._cancel_auto_off_task(); self.cancel_skimmer_delay()
    def cancel_skimmer_delay(self):
        pending=bool(self._skimmer_task and not self._skimmer_task.done())
        if pending:self._skimmer_task.cancel()
        self._skimmer_task=None; self._runtime()["skimmer_delay_until"]=None; return pending
    def _feeding_pause_entities(self):
        o=self._entry.options; pairs=((CONF_SKIMMER_ENTITY,CONF_FEEDING_PAUSE_SKIMMER,True),(CONF_RETURN_PUMP_ENTITY,CONF_FEEDING_PAUSE_RETURN_PUMP,False),(CONF_FLOW_PUMP_ENTITY,CONF_FEEDING_PAUSE_FLOW_PUMP,True),(CONF_UVC_ENTITY,CONF_FEEDING_PAUSE_UVC,False),(CONF_ATO_ENTITY,CONF_FEEDING_PAUSE_ATO,True)); return [o[k] for k,f,d in pairs if o.get(k) and o.get(f,d)]
    async def _auto_turn_off(self,s):
        try: await asyncio.sleep(s); await self.async_turn_off()
        except asyncio.CancelledError: pass
    async def _delayed_turn_on(self,eid,s):
        try: await asyncio.sleep(s); await self._set(eid,True)
        except asyncio.CancelledError: pass
        finally:self._runtime()["skimmer_delay_until"]=None; self._skimmer_task=None
    def _cancel_auto_off_task(self):
        if self._auto_off_task and not self._auto_off_task.done():self._auto_off_task.cancel()
        self._auto_off_task=None

class ReefControlMaintenanceModeSwitch(ReefControlBaseSwitch):
    _attr_name="Wartungsmodus"; _attr_icon="mdi:tools"
    def __init__(self,hass,entry):super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_maintenance_mode"
    async def async_turn_on(self,**kwargs):
        if self._is_on:return
        r=self._runtime(); f=r.get("feeding_switch")
        if f and f.is_on:await f.async_turn_off()
        pending=f.cancel_skimmer_delay() if f else False; self._is_on=True; r["maintenance_active"]=True; r["feeding_active"]=False; r["feeding_until"]=None; self.async_write_ha_state(); skimmer=self._entry.options.get(CONF_SKIMMER_ENTITY); force={skimmer} if pending and skimmer else set(); await self._pause_entities(self._maintenance_pause_entities(),force)
    async def async_turn_off(self,**kwargs):
        if not self._is_on:return
        self._is_on=False; r=self._runtime(); r["maintenance_active"]=False; self.async_write_ha_state()
        ato=r.get("ato_control_switch"); ato_id=self._entry.options.get(CONF_ATO_ENTITY)
        await self._restore_entities({ato_id} if ato and ato.is_on and ato_id else set())
        controller=r.get("temperature_control_switch")
        if controller and controller.is_on: await controller.async_evaluate()
        if ato and ato.is_on: await ato.async_evaluate()
    def _maintenance_pause_entities(self):
        o=self._entry.options; pairs=((CONF_SKIMMER_ENTITY,CONF_MAINTENANCE_PAUSE_SKIMMER,True),(CONF_RETURN_PUMP_ENTITY,CONF_MAINTENANCE_PAUSE_RETURN_PUMP,True),(CONF_FLOW_PUMP_ENTITY,CONF_MAINTENANCE_PAUSE_FLOW_PUMP,True),(CONF_UVC_ENTITY,CONF_MAINTENANCE_PAUSE_UVC,True),(CONF_ATO_ENTITY,CONF_MAINTENANCE_PAUSE_ATO,True),(CONF_HEATER_ENTITY,CONF_MAINTENANCE_PAUSE_HEATER,True),(CONF_LIGHT_ENTITY,CONF_MAINTENANCE_PAUSE_LIGHT,False)); return [o[k] for k,f,d in pairs if o.get(k) and o.get(f,d)]

class ReefControlTemperatureControlSwitch(ReefControlBaseSwitch):
    _attr_name="Temperaturregelung"; _attr_icon="mdi:thermostat"
    def __init__(self,hass,entry):
        super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_temperature_control"
        self._is_on=bool(entry.options.get(CONF_TEMPERATURE_CONTROL_ENABLED,DEFAULT_TEMPERATURE_CONTROL_ENABLED))
        self._remove_listener=None; self._last_temperature=None; self._last_action="Deaktiviert"
        self._last_switch_at=None; self._last_switch_action=None; self._pending_task=None
    async def async_added_to_hass(self):
        sensor=self._entry.options.get(CONF_TEMPERATURE_ENTITY)
        if sensor:self._remove_listener=async_track_state_change_event(self.hass,[sensor],self._temperature_changed)
        if self._is_on:await self.async_evaluate()
    async def async_will_remove_from_hass(self):
        if self._remove_listener:self._remove_listener(); self._remove_listener=None
        self._cancel_pending()
    async def _temperature_changed(self,event):
        if self._is_on:await self.async_evaluate()
    async def async_turn_on(self,**kwargs):
        self._is_on=True; self.async_write_ha_state(); await self.async_evaluate()
    async def async_turn_off(self,**kwargs):
        self._is_on=False; self._cancel_pending(); self._set_status("Deaktiviert")
    def _cancel_pending(self):
        if self._pending_task and not self._pending_task.done():self._pending_task.cancel()
        self._pending_task=None
    def _set_status(self,status):
        self._last_action=status; self._runtime()["temperature_control_status"]=status; self.async_write_ha_state()
    def _heater_state(self,heater_id):
        state=self.hass.states.get(heater_id)
        if state is None:return "missing"
        if state.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):return state.state
        return state.state
    def _remaining_lockout(self,want_on):
        if not self._last_switch_at:return 0
        minutes=float(self._entry.options.get(CONF_TEMPERATURE_MIN_OFF_TIME if want_on else CONF_TEMPERATURE_MIN_ON_TIME,DEFAULT_TEMPERATURE_MIN_OFF_TIME if want_on else DEFAULT_TEMPERATURE_MIN_ON_TIME))
        elapsed=(datetime.now().astimezone()-self._last_switch_at).total_seconds()
        return max(0,minutes*60-elapsed)
    async def _switch_heater(self,heater_id,on):
        await self._set(heater_id,on); self._last_switch_at=datetime.now().astimezone(); self._last_switch_action="EIN" if on else "AUS"
    async def _delayed_evaluate(self,seconds):
        try:
            await asyncio.sleep(seconds); self._pending_task=None
            if self._is_on:await self.async_evaluate()
        except asyncio.CancelledError:pass
    async def async_evaluate(self):
        self._cancel_pending()
        if not self._is_on:self._set_status("Deaktiviert"); return
        sensor_id=self._entry.options.get(CONF_TEMPERATURE_ENTITY); heater_id=self._entry.options.get(CONF_HEATER_ENTITY)
        if not sensor_id or not heater_id:self._set_status("Nicht konfiguriert"); return
        if self._runtime().get("maintenance_active"):self._set_status("Pausiert"); return
        state=self.hass.states.get(sensor_id)
        if state is None or state.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):self._set_status("Sensorfehler"); return
        try:temperature=float(str(state.state).replace(",","."))
        except (TypeError,ValueError):self._set_status("Sensorfehler"); return
        self._last_temperature=temperature; heater_state=self._heater_state(heater_id)
        if heater_state in ("missing",STATE_UNKNOWN,STATE_UNAVAILABLE):self._set_status("Heizungsfehler"); return
        target=float(self._entry.options.get(CONF_TEMPERATURE_TARGET,DEFAULT_TEMPERATURE_TARGET)); hysteresis=float(self._entry.options.get(CONF_TEMPERATURE_HYSTERESIS,DEFAULT_TEMPERATURE_HYSTERESIS))
        want_on=None
        if temperature<=target-hysteresis and heater_state!=STATE_ON:want_on=True
        elif temperature>=target and heater_state==STATE_ON:want_on=False
        if want_on is not None:
            remaining=self._remaining_lockout(want_on)
            if remaining>0:self._set_status("Warte auf Mindestpause"); self._pending_task=self.hass.async_create_task(self._delayed_evaluate(remaining)); return
            await self._switch_heater(heater_id,want_on); heater_state=STATE_ON if want_on else STATE_OFF
        self._set_status("Heizen" if heater_state==STATE_ON else "Sollbereich")
    @property
    def extra_state_attributes(self):
        target=float(self._entry.options.get(CONF_TEMPERATURE_TARGET,DEFAULT_TEMPERATURE_TARGET)); hysteresis=float(self._entry.options.get(CONF_TEMPERATURE_HYSTERESIS,DEFAULT_TEMPERATURE_HYSTERESIS)); heater_id=self._entry.options.get(CONF_HEATER_ENTITY)
        return {"status":self._last_action,"temperature":self._last_temperature,"target":target,"heating_on_below":round(target-hysteresis,2),"heating_off_at":target,"hysteresis":hysteresis,"temperature_entity":self._entry.options.get(CONF_TEMPERATURE_ENTITY),"heater_entity":heater_id,"heater_state":self._heater_state(heater_id) if heater_id else "not_configured","last_switch_action":self._last_switch_action,"last_switch_at":self._last_switch_at.isoformat() if self._last_switch_at else None,"minimum_on_minutes":float(self._entry.options.get(CONF_TEMPERATURE_MIN_ON_TIME,DEFAULT_TEMPERATURE_MIN_ON_TIME)),"minimum_off_minutes":float(self._entry.options.get(CONF_TEMPERATURE_MIN_OFF_TIME,DEFAULT_TEMPERATURE_MIN_OFF_TIME))}

class ReefControlAtoControlSwitch(ReefControlBaseSwitch):
    _attr_name="Wasserstandsregelung"; _attr_icon="mdi:water-sync"
    def __init__(self,hass,entry):
        super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_ato_control"
        self._is_on=bool(entry.options.get(CONF_ATO_CONTROL_ENABLED,DEFAULT_ATO_CONTROL_ENABLED))
        self._remove_listener=None; self._confirm_task=None; self._max_runtime_task=None; self._cooldown_task=None
        self._locked=False; self._last_fill_started=None; self._last_fill_stopped=None; self._last_fill_duration=None; self._last_action=None
    async def async_added_to_hass(self):
        sensor=self._entry.options.get(CONF_WATER_LEVEL_ENTITY)
        if sensor:self._remove_listener=async_track_state_change_event(self.hass,[sensor],self._level_changed)
        pump=self._entry.options.get(CONF_ATO_ENTITY)
        if pump and self.hass.states.get(pump) and self.hass.states[pump].state==STATE_ON:
            await self._set(pump,False)
        if self._is_on:await self.async_evaluate()
    async def async_will_remove_from_hass(self):
        if self._remove_listener:self._remove_listener(); self._remove_listener=None
        self._cancel_tasks()
        pump=self._entry.options.get(CONF_ATO_ENTITY)
        if pump and self.hass.states.get(pump) and self.hass.states[pump].state==STATE_ON:await self._set(pump,False)
    async def _level_changed(self,event):
        if self._is_on:await self.async_evaluate()
    def _cancel_task(self,name):
        task=getattr(self,name)
        if task and not task.done():task.cancel()
        setattr(self,name,None)
    def _cancel_tasks(self):
        for name in ("_confirm_task","_max_runtime_task","_cooldown_task"):self._cancel_task(name)
    def _set_status(self,status):
        self._last_action=status; self._runtime()["ato_control_status"]=status; self.async_write_ha_state()
    def _pump_state(self,pump):
        state=self.hass.states.get(pump)
        if state is None:return "missing"
        return state.state
    def _is_low(self,state):
        return state==self._entry.options.get(CONF_ATO_LOW_STATE,DEFAULT_ATO_LOW_STATE)
    async def async_turn_on(self,**kwargs):
        self._locked=False; self._is_on=True; self.async_write_ha_state(); await self.async_evaluate()
    async def async_turn_off(self,**kwargs):
        self._is_on=False; self._locked=False; self._cancel_tasks()
        pump=self._entry.options.get(CONF_ATO_ENTITY)
        if pump:await self._stop_pump(pump,record=True)
        self._set_status("Deaktiviert")
    async def _confirm_low(self,seconds):
        try:
            await asyncio.sleep(seconds); self._confirm_task=None
            if self._is_on:await self.async_evaluate(confirmed=True)
        except asyncio.CancelledError:pass
    async def _runtime_limit(self,seconds):
        try:
            await asyncio.sleep(seconds); self._max_runtime_task=None
            pump=self._entry.options.get(CONF_ATO_ENTITY)
            if pump:await self._stop_pump(pump,record=True)
            self._locked=True; self._set_status("Sicherheitsstopp")
        except asyncio.CancelledError:pass
    async def _cooldown_done(self,seconds):
        try:
            await asyncio.sleep(seconds); self._cooldown_task=None
            if self._is_on:await self.async_evaluate()
        except asyncio.CancelledError:pass
    async def _start_pump(self,pump):
        await self._set(pump,True); self._last_fill_started=datetime.now().astimezone(); self._last_action="Nachfüllen"
        self._cancel_task("_max_runtime_task")
        maximum=float(self._entry.options.get(CONF_ATO_MAX_RUNTIME,DEFAULT_ATO_MAX_RUNTIME))
        self._max_runtime_task=self.hass.async_create_task(self._runtime_limit(maximum))
    async def _stop_pump(self,pump,record=True):
        state=self.hass.states.get(pump)
        if state and state.state==STATE_ON:await self._set(pump,False)
        self._cancel_task("_max_runtime_task")
        if record and self._last_fill_started:
            now=datetime.now().astimezone(); self._last_fill_stopped=now; self._last_fill_duration=round((now-self._last_fill_started).total_seconds(),1); self._last_fill_started=None
    async def async_evaluate(self,confirmed=False):
        if not self._is_on:self._set_status("Deaktiviert"); return
        sensor_id=self._entry.options.get(CONF_WATER_LEVEL_ENTITY); pump=self._entry.options.get(CONF_ATO_ENTITY)
        if not sensor_id or not pump:self._set_status("Nicht konfiguriert"); return
        if self._locked:self._set_status("Sicherheitsstopp"); return
        runtime=self._runtime()
        if runtime.get("maintenance_active") or (runtime.get("feeding_active") and self._entry.options.get(CONF_FEEDING_PAUSE_ATO,True)):
            await self._stop_pump(pump,record=True); self._cancel_task("_confirm_task"); self._set_status("Pausiert"); return
        level=self.hass.states.get(sensor_id); pump_state=self._pump_state(pump)
        if level is None or level.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):
            await self._stop_pump(pump,record=True); self._cancel_task("_confirm_task"); self._set_status("Sensorfehler"); return
        if pump_state in ("missing",STATE_UNKNOWN,STATE_UNAVAILABLE):
            self._cancel_tasks(); self._set_status("Pumpenfehler"); return
        low=self._is_low(level.state)
        if not low:
            self._cancel_task("_confirm_task")
            if pump_state==STATE_ON:
                await self._stop_pump(pump,record=True)
                cooldown=float(self._entry.options.get(CONF_ATO_COOLDOWN,DEFAULT_ATO_COOLDOWN))*60
                if cooldown>0:self._set_status("Wartezeit"); self._cooldown_task=self.hass.async_create_task(self._cooldown_done(cooldown)); return
            self._set_status("Bereit"); return
        if pump_state==STATE_ON:self._set_status("Nachfüllen"); return
        if self._cooldown_task and not self._cooldown_task.done():self._set_status("Wartezeit"); return
        delay=float(self._entry.options.get(CONF_ATO_CONFIRM_DELAY,DEFAULT_ATO_CONFIRM_DELAY))
        if not confirmed and delay>0:
            if not self._confirm_task:self._set_status("Wasserstand prüfen"); self._confirm_task=self.hass.async_create_task(self._confirm_low(delay))
            return
        await self._start_pump(pump); self._set_status("Nachfüllen")
    @property
    def extra_state_attributes(self):
        sensor_id=self._entry.options.get(CONF_WATER_LEVEL_ENTITY); pump=self._entry.options.get(CONF_ATO_ENTITY)
        level=self.hass.states.get(sensor_id) if sensor_id else None
        return {
            "status":self._last_action,
            "locked":self._locked,
            "water_level_entity":sensor_id,
            "water_level_state":level.state if level else None,
            "low_level_state":self._entry.options.get(CONF_ATO_LOW_STATE,DEFAULT_ATO_LOW_STATE),
            "ato_entity":pump,
            "ato_state":self._pump_state(pump) if pump else "not_configured",
            "confirm_delay_seconds":float(self._entry.options.get(CONF_ATO_CONFIRM_DELAY,DEFAULT_ATO_CONFIRM_DELAY)),
            "maximum_runtime_seconds":float(self._entry.options.get(CONF_ATO_MAX_RUNTIME,DEFAULT_ATO_MAX_RUNTIME)),
            "cooldown_minutes":float(self._entry.options.get(CONF_ATO_COOLDOWN,DEFAULT_ATO_COOLDOWN)),
            "last_fill_started":self._last_fill_started.isoformat() if self._last_fill_started else None,
            "last_fill_stopped":self._last_fill_stopped.isoformat() if self._last_fill_stopped else None,
            "last_fill_duration_seconds":self._last_fill_duration,
        }
