"""Config flow for Reef Control."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from .const import *

class ReefControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            aquarium_name = user_input[CONF_AQUARIUM_NAME].strip()
            await self.async_set_unique_id(aquarium_name.lower()); self._abort_if_unique_id_configured()
            return self.async_create_entry(title=aquarium_name, data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_AQUARIUM_NAME, default=DEFAULT_AQUARIUM_NAME): str,
            vol.Required(CONF_VOLUME): vol.All(vol.Coerce(float), vol.Range(min=1)),
            vol.Optional(CONF_TANK_TYPE, default="mixed_reef"): vol.In({"mixed_reef":"Mixed Reef","sps":"SPS Reef","lps":"LPS Reef","soft_coral":"Soft Coral Reef","fish_only":"Fish Only","other":"Other"}),
            vol.Optional(CONF_SUPPLY_SYSTEM, default="none"): vol.In({"none":"None / Other","fauna_marin_balling_light":"Fauna Marin Balling Light","ati_essentials":"ATI Essentials","oceamo_duo":"Oceamo DUO","triton":"Triton Method","other":"Other"}),
            vol.Optional(CONF_REEF_METHOD, default="none"): vol.In({"none":"None","berlin":"Berlin Method","triton":"Triton Method","dsr":"DSR","other":"Other"}),
        })
        return self.async_show_form(step_id="user", data_schema=schema)
    @staticmethod
    @callback
    def async_get_options_flow(config_entry): return ReefControlOptionsFlow(config_entry)

class ReefControlOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry): self._config_entry=config_entry
    @property
    def _options(self): return self._config_entry.options
    def _suggested(self,key,default=None): return {"suggested_value":self._options.get(key,default)}
    def _number(self,key,default,minimum,maximum,step,unit=None):
        config={"min":minimum,"max":maximum,"step":step,"mode":selector.NumberSelectorMode.BOX}
        if unit is not None: config["unit_of_measurement"]=unit
        return (vol.Optional(key,description=self._suggested(key,default)),selector.NumberSelector(selector.NumberSelectorConfig(**config)))
    async def _save(self,changes,remove_keys=()):
        data=dict(self._options)
        for key in remove_keys: data.pop(key,None)
        data.update(changes); return self.async_create_entry(title="",data=data)
    async def async_step_init(self,user_input=None)->FlowResult:
        return self.async_show_menu(step_id="init",menu_options=["entities","water_values","limits","operating_modes","temperature_control","ato_control","uvc_control","equipment_control","safety_control","reef_icp"])
    async def async_step_entities(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        switch_domains=["switch","input_boolean"]; fields={}
        for key in (CONF_SKIMMER_ENTITY,CONF_RETURN_PUMP_ENTITY,CONF_FLOW_PUMP_ENTITY,CONF_UVC_ENTITY,CONF_HEATER_ENTITY,CONF_ATO_ENTITY):
            fields[vol.Optional(key,description=self._suggested(key))]=selector.EntitySelector(selector.EntitySelectorConfig(domain=switch_domains))
        fields[vol.Optional(CONF_LIGHT_ENTITY,description=self._suggested(CONF_LIGHT_ENTITY))]=selector.EntitySelector(selector.EntitySelectorConfig(domain=["light","switch","input_boolean"]))
        return self.async_show_form(step_id="entities",data_schema=vol.Schema(fields))
    async def async_step_water_values(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={}
        for key in (CONF_TEMPERATURE_ENTITY,CONF_PH_ENTITY,CONF_SALINITY_ENTITY,CONF_CONDUCTIVITY_ENTITY,CONF_REDOX_ENTITY):
            fields[vol.Optional(key,description=self._suggested(key))]=selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        fields[vol.Optional(CONF_SALINITY_SOURCE,default=self._options.get(CONF_SALINITY_SOURCE,DEFAULT_SALINITY_SOURCE))]=selector.SelectSelector(
            selector.SelectSelectorConfig(options=[
                selector.SelectOptionDict(value="auto",label="Automatisch"),
                selector.SelectOptionDict(value="direct",label="Direkter Salinitätssensor"),
                selector.SelectOptionDict(value="calculated",label="Aus Leitfähigkeit + Temperatur berechnen"),
            ],mode=selector.SelectSelectorMode.DROPDOWN)
        )
        fields[vol.Optional(CONF_WATER_LEVEL_ENTITY,description=self._suggested(CONF_WATER_LEVEL_ENTITY))]=selector.EntitySelector(selector.EntitySelectorConfig(domain=["binary_sensor","input_boolean"]))
        return self.async_show_form(step_id="water_values",data_schema=vol.Schema(fields))
    async def async_step_temperature_control(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={vol.Optional(CONF_TEMPERATURE_CONTROL_ENABLED,default=self._options.get(CONF_TEMPERATURE_CONTROL_ENABLED,DEFAULT_TEMPERATURE_CONTROL_ENABLED)):bool}
        key,value=self._number(CONF_TEMPERATURE_TARGET,DEFAULT_TEMPERATURE_TARGET,15,35,0.1,"°C"); fields[key]=value
        key,value=self._number(CONF_TEMPERATURE_HYSTERESIS,DEFAULT_TEMPERATURE_HYSTERESIS,0.1,2.0,0.1,"°C"); fields[key]=value
        key,value=self._number(CONF_TEMPERATURE_MIN_ON_TIME,DEFAULT_TEMPERATURE_MIN_ON_TIME,0,30,1,"min"); fields[key]=value
        key,value=self._number(CONF_TEMPERATURE_MIN_OFF_TIME,DEFAULT_TEMPERATURE_MIN_OFF_TIME,0,30,1,"min"); fields[key]=value
        return self.async_show_form(step_id="temperature_control",data_schema=vol.Schema(fields))
    async def async_step_ato_control(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={
            vol.Optional(CONF_ATO_CONTROL_ENABLED,default=self._options.get(CONF_ATO_CONTROL_ENABLED,DEFAULT_ATO_CONTROL_ENABLED)):bool,
            vol.Optional(CONF_ATO_LOW_STATE,default=self._options.get(CONF_ATO_LOW_STATE,DEFAULT_ATO_LOW_STATE)):selector.SelectSelector(
                selector.SelectSelectorConfig(options=[selector.SelectOptionDict(value="on",label="ON"),selector.SelectOptionDict(value="off",label="OFF")],mode=selector.SelectSelectorMode.DROPDOWN)
            ),
        }
        key,value=self._number(CONF_ATO_CONFIRM_DELAY,DEFAULT_ATO_CONFIRM_DELAY,0,30,1,"s"); fields[key]=value
        key,value=self._number(CONF_ATO_MAX_RUNTIME,DEFAULT_ATO_MAX_RUNTIME,5,600,1,"s"); fields[key]=value
        key,value=self._number(CONF_ATO_COOLDOWN,DEFAULT_ATO_COOLDOWN,0,60,1,"min"); fields[key]=value
        return self.async_show_form(step_id="ato_control",data_schema=vol.Schema(fields))
    async def async_step_uvc_control(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        mode_options=[
            selector.SelectOptionDict(value="continuous",label="Dauerbetrieb"),
            selector.SelectOptionDict(value="schedule",label="Zeitplan"),
            selector.SelectOptionDict(value="off",label="Aus"),
        ]
        fields={
            vol.Optional(CONF_UVC_CONTROL_ENABLED,default=self._options.get(CONF_UVC_CONTROL_ENABLED,DEFAULT_UVC_CONTROL_ENABLED)):bool,
            vol.Optional(CONF_UVC_MODE,default=self._options.get(CONF_UVC_MODE,DEFAULT_UVC_MODE)):selector.SelectSelector(
                selector.SelectSelectorConfig(options=mode_options,mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_UVC_START_TIME,default=self._options.get(CONF_UVC_START_TIME,DEFAULT_UVC_START_TIME)):selector.TimeSelector(),
            vol.Optional(CONF_UVC_END_TIME,default=self._options.get(CONF_UVC_END_TIME,DEFAULT_UVC_END_TIME)):selector.TimeSelector(),
        }
        return self.async_show_form(step_id="uvc_control",data_schema=vol.Schema(fields))
    async def async_step_equipment_control(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={
            vol.Optional(CONF_EQUIPMENT_CONTROL_ENABLED,default=self._options.get(CONF_EQUIPMENT_CONTROL_ENABLED,DEFAULT_EQUIPMENT_CONTROL_ENABLED)):bool,
            vol.Optional(CONF_RETURN_MASTER_SKIMMER,default=self._options.get(CONF_RETURN_MASTER_SKIMMER,DEFAULT_RETURN_MASTER_SKIMMER)):bool,
            vol.Optional(CONF_RETURN_MASTER_UVC,default=self._options.get(CONF_RETURN_MASTER_UVC,DEFAULT_RETURN_MASTER_UVC)):bool,
            vol.Optional(CONF_RETURN_MASTER_ATO,default=self._options.get(CONF_RETURN_MASTER_ATO,DEFAULT_RETURN_MASTER_ATO)):bool,
            vol.Optional(CONF_RETURN_MASTER_FLOW,default=self._options.get(CONF_RETURN_MASTER_FLOW,DEFAULT_RETURN_MASTER_FLOW)):bool,
        }
        key,value=self._number(CONF_EQUIPMENT_SKIMMER_DELAY,DEFAULT_EQUIPMENT_SKIMMER_DELAY,0,30,1,"min"); fields[key]=value
        key,value=self._number(CONF_EQUIPMENT_UVC_DELAY,DEFAULT_EQUIPMENT_UVC_DELAY,0,30,1,"min"); fields[key]=value
        key,value=self._number(CONF_EQUIPMENT_FLOW_DELAY,DEFAULT_EQUIPMENT_FLOW_DELAY,0,30,1,"min"); fields[key]=value
        return self.async_show_form(step_id="equipment_control",data_schema=vol.Schema(fields))
    async def async_step_safety_control(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={
            vol.Optional(CONF_SAFETY_CONTROL_ENABLED,default=self._options.get(CONF_SAFETY_CONTROL_ENABLED,DEFAULT_SAFETY_CONTROL_ENABLED)):bool,
            vol.Optional(CONF_SAFETY_HEATER_HIGH_TEMP,default=self._options.get(CONF_SAFETY_HEATER_HIGH_TEMP,DEFAULT_SAFETY_HEATER_HIGH_TEMP)):bool,
            vol.Optional(CONF_SAFETY_HEATER_SENSOR_FAIL,default=self._options.get(CONF_SAFETY_HEATER_SENSOR_FAIL,DEFAULT_SAFETY_HEATER_SENSOR_FAIL)):bool,
        }
        return self.async_show_form(step_id="safety_control",data_schema=vol.Schema(fields))
    async def async_step_reef_icp(self,user_input=None)->FlowResult:
        if user_input is not None:
            selected=user_input.get(CONF_REEF_ICP_ENTRY)
            if selected=="__none__" or not selected:return await self._save({},remove_keys=(CONF_REEF_ICP_ENTRY,))
            return await self._save({CONF_REEF_ICP_ENTRY:selected})
        entries=self.hass.config_entries.async_entries(REEF_ICP_DOMAIN)
        options=[selector.SelectOptionDict(value="__none__",label="Keine Verknüpfung")]
        options.extend(selector.SelectOptionDict(value=e.entry_id,label=e.title or f"Reef ICP ({e.entry_id[:8]})") for e in entries)
        current=self._options.get(CONF_REEF_ICP_ENTRY)
        if current and not any(e.entry_id==current for e in entries):current="__none__"
        return self.async_show_form(step_id="reef_icp",data_schema=vol.Schema({vol.Required(CONF_REEF_ICP_ENTRY,default=current or "__none__"):selector.SelectSelector(selector.SelectSelectorConfig(options=options,mode=selector.SelectSelectorMode.DROPDOWN))}))
    async def async_step_reef_icp_unavailable(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save({},remove_keys=(CONF_REEF_ICP_ENTRY,))
        return self.async_show_form(step_id="reef_icp_unavailable",data_schema=vol.Schema({}))
    async def async_step_limits(self,user_input=None)->FlowResult:
        return self.async_show_menu(step_id="limits",menu_options=["temperature_limits","ph_limits","salinity_limits","redox_limits"])
    async def async_step_temperature_limits(self,user_input=None)->FlowResult:
        definitions=[(CONF_TEMPERATURE_MIN,DEFAULT_TEMPERATURE_MIN,0,50,0.1,"°C"),(CONF_TEMPERATURE_MAX,DEFAULT_TEMPERATURE_MAX,0,50,0.1,"°C"),(CONF_TEMPERATURE_CRITICAL_MIN,DEFAULT_TEMPERATURE_CRITICAL_MIN,0,50,0.1,"°C"),(CONF_TEMPERATURE_CRITICAL_MAX,DEFAULT_TEMPERATURE_CRITICAL_MAX,0,50,0.1,"°C")]
        return await self._limits_form("temperature_limits",user_input,definitions,(CONF_TEMPERATURE_CRITICAL_MIN,CONF_TEMPERATURE_MIN,CONF_TEMPERATURE_MAX,CONF_TEMPERATURE_CRITICAL_MAX),(DEFAULT_TEMPERATURE_CRITICAL_MIN,DEFAULT_TEMPERATURE_MIN,DEFAULT_TEMPERATURE_MAX,DEFAULT_TEMPERATURE_CRITICAL_MAX))
    async def async_step_ph_limits(self,user_input=None)->FlowResult:
        definitions=[(CONF_PH_MIN,DEFAULT_PH_MIN,0,14,0.01,None),(CONF_PH_MAX,DEFAULT_PH_MAX,0,14,0.01,None),(CONF_PH_CRITICAL_MIN,DEFAULT_PH_CRITICAL_MIN,0,14,0.01,None),(CONF_PH_CRITICAL_MAX,DEFAULT_PH_CRITICAL_MAX,0,14,0.01,None)]
        return await self._limits_form("ph_limits",user_input,definitions,(CONF_PH_CRITICAL_MIN,CONF_PH_MIN,CONF_PH_MAX,CONF_PH_CRITICAL_MAX),(DEFAULT_PH_CRITICAL_MIN,DEFAULT_PH_MIN,DEFAULT_PH_MAX,DEFAULT_PH_CRITICAL_MAX))
    async def async_step_salinity_limits(self,user_input=None)->FlowResult:
        definitions=[(CONF_SALINITY_MIN,DEFAULT_SALINITY_MIN,0,100,0.1,"ppt"),(CONF_SALINITY_MAX,DEFAULT_SALINITY_MAX,0,100,0.1,"ppt"),(CONF_SALINITY_CRITICAL_MIN,DEFAULT_SALINITY_CRITICAL_MIN,0,100,0.1,"ppt"),(CONF_SALINITY_CRITICAL_MAX,DEFAULT_SALINITY_CRITICAL_MAX,0,100,0.1,"ppt")]
        return await self._limits_form("salinity_limits",user_input,definitions,(CONF_SALINITY_CRITICAL_MIN,CONF_SALINITY_MIN,CONF_SALINITY_MAX,CONF_SALINITY_CRITICAL_MAX),(DEFAULT_SALINITY_CRITICAL_MIN,DEFAULT_SALINITY_MIN,DEFAULT_SALINITY_MAX,DEFAULT_SALINITY_CRITICAL_MAX))
    async def async_step_redox_limits(self,user_input=None)->FlowResult:
        definitions=[(CONF_REDOX_MIN,DEFAULT_REDOX_MIN,-1000,1000,1,"mV"),(CONF_REDOX_MAX,DEFAULT_REDOX_MAX,-1000,1000,1,"mV"),(CONF_REDOX_CRITICAL_MIN,DEFAULT_REDOX_CRITICAL_MIN,-1000,1000,1,"mV"),(CONF_REDOX_CRITICAL_MAX,DEFAULT_REDOX_CRITICAL_MAX,-1000,1000,1,"mV")]
        return await self._limits_form("redox_limits",user_input,definitions,(CONF_REDOX_CRITICAL_MIN,CONF_REDOX_MIN,CONF_REDOX_MAX,CONF_REDOX_CRITICAL_MAX),(DEFAULT_REDOX_CRITICAL_MIN,DEFAULT_REDOX_MIN,DEFAULT_REDOX_MAX,DEFAULT_REDOX_CRITICAL_MAX))
    async def _limits_form(self,step_id,user_input,definitions,keys,defaults):
        errors={}
        if user_input is not None:
            values=[float(user_input.get(k,d)) for k,d in zip(keys,defaults)]
            if values[0]<=values[1]<values[2]<=values[3]:return await self._save(user_input)
            errors["base"]="invalid_limits"
        fields={}
        for args in definitions:
            key,value=self._number(*args); fields[key]=value
        return self.async_show_form(step_id=step_id,data_schema=vol.Schema(fields),errors=errors)
    async def async_step_operating_modes(self,user_input=None)->FlowResult:
        if user_input is not None:return await self._save(user_input)
        fields={}
        key,value=self._number(CONF_FEEDING_DURATION,DEFAULT_FEEDING_DURATION,1,120,1,"min"); fields[key]=value
        key,value=self._number(CONF_SKIMMER_DELAY,DEFAULT_SKIMMER_DELAY,0,120,1,"min"); fields[key]=value
        bools={CONF_FEEDING_PAUSE_SKIMMER:True,CONF_FEEDING_PAUSE_RETURN_PUMP:False,CONF_FEEDING_PAUSE_FLOW_PUMP:True,CONF_FEEDING_PAUSE_UVC:False,CONF_FEEDING_PAUSE_ATO:True,CONF_MAINTENANCE_PAUSE_SKIMMER:True,CONF_MAINTENANCE_PAUSE_RETURN_PUMP:True,CONF_MAINTENANCE_PAUSE_FLOW_PUMP:True,CONF_MAINTENANCE_PAUSE_UVC:True,CONF_MAINTENANCE_PAUSE_ATO:True,CONF_MAINTENANCE_PAUSE_HEATER:True,CONF_MAINTENANCE_PAUSE_LIGHT:False}
        for key,default in bools.items():fields[vol.Optional(key,default=self._options.get(key,default))]=bool
        return self.async_show_form(step_id="operating_modes",data_schema=vol.Schema(fields))
