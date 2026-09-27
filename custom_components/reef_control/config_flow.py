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
            await self.async_set_unique_id(aquarium_name.lower())
            self._abort_if_unique_id_configured()
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
    def async_get_options_flow(config_entry):
        return ReefControlOptionsFlow(config_entry)

class ReefControlOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry): self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            errors = self._validate_limits(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        else:
            errors = {}
        options = self._config_entry.options
        def suggested(key, default=None): return {"suggested_value": options.get(key, default)}
        def number(key, default, minimum, maximum, step):
            return (vol.Optional(key, description=suggested(key, default)), selector.NumberSelector(selector.NumberSelectorConfig(min=minimum,max=maximum,step=step,mode=selector.NumberSelectorMode.BOX)))
        switch_domains = ["switch", "input_boolean"]
        fields = {}
        for key in (CONF_TEMPERATURE_ENTITY, CONF_PH_ENTITY, CONF_SALINITY_ENTITY):
            fields[vol.Optional(key, description=suggested(key))] = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        for key in (CONF_SKIMMER_ENTITY, CONF_RETURN_PUMP_ENTITY, CONF_FLOW_PUMP_ENTITY, CONF_UVC_ENTITY, CONF_HEATER_ENTITY, CONF_ATO_ENTITY):
            fields[vol.Optional(key, description=suggested(key))] = selector.EntitySelector(selector.EntitySelectorConfig(domain=switch_domains))
        fields[vol.Optional(CONF_LIGHT_ENTITY, description=suggested(CONF_LIGHT_ENTITY))] = selector.EntitySelector(selector.EntitySelectorConfig(domain=["light","switch","input_boolean"]))

        limit_defs = [
            (CONF_TEMPERATURE_MIN,DEFAULT_TEMPERATURE_MIN,0,50,0.1),(CONF_TEMPERATURE_MAX,DEFAULT_TEMPERATURE_MAX,0,50,0.1),(CONF_TEMPERATURE_CRITICAL_MIN,DEFAULT_TEMPERATURE_CRITICAL_MIN,0,50,0.1),(CONF_TEMPERATURE_CRITICAL_MAX,DEFAULT_TEMPERATURE_CRITICAL_MAX,0,50,0.1),
            (CONF_PH_MIN,DEFAULT_PH_MIN,0,14,0.01),(CONF_PH_MAX,DEFAULT_PH_MAX,0,14,0.01),(CONF_PH_CRITICAL_MIN,DEFAULT_PH_CRITICAL_MIN,0,14,0.01),(CONF_PH_CRITICAL_MAX,DEFAULT_PH_CRITICAL_MAX,0,14,0.01),
            (CONF_SALINITY_MIN,DEFAULT_SALINITY_MIN,0,100,0.1),(CONF_SALINITY_MAX,DEFAULT_SALINITY_MAX,0,100,0.1),(CONF_SALINITY_CRITICAL_MIN,DEFAULT_SALINITY_CRITICAL_MIN,0,100,0.1),(CONF_SALINITY_CRITICAL_MAX,DEFAULT_SALINITY_CRITICAL_MAX,0,100,0.1),
        ]
        for args in limit_defs:
            k,v = number(*args); fields[k]=v
        k,v = number(CONF_FEEDING_DURATION,DEFAULT_FEEDING_DURATION,1,120,1); v.config["unit_of_measurement"]="min"; fields[k]=v
        k,v = number(CONF_SKIMMER_DELAY,DEFAULT_SKIMMER_DELAY,0,120,1); v.config["unit_of_measurement"]="min"; fields[k]=v
        bools = {
            CONF_FEEDING_PAUSE_SKIMMER:True, CONF_FEEDING_PAUSE_RETURN_PUMP:False, CONF_FEEDING_PAUSE_FLOW_PUMP:True, CONF_FEEDING_PAUSE_UVC:False, CONF_FEEDING_PAUSE_ATO:True,
            CONF_MAINTENANCE_PAUSE_SKIMMER:True, CONF_MAINTENANCE_PAUSE_RETURN_PUMP:True, CONF_MAINTENANCE_PAUSE_FLOW_PUMP:True, CONF_MAINTENANCE_PAUSE_UVC:True, CONF_MAINTENANCE_PAUSE_ATO:True, CONF_MAINTENANCE_PAUSE_HEATER:True, CONF_MAINTENANCE_PAUSE_LIGHT:False,
        }
        for key, default in bools.items(): fields[vol.Optional(key, default=options.get(key, default))] = bool
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)

    @staticmethod
    def _validate_limits(data):
        errors = {}
        groups = [
            (CONF_TEMPERATURE_CRITICAL_MIN,CONF_TEMPERATURE_MIN,CONF_TEMPERATURE_MAX,CONF_TEMPERATURE_CRITICAL_MAX),
            (CONF_PH_CRITICAL_MIN,CONF_PH_MIN,CONF_PH_MAX,CONF_PH_CRITICAL_MAX),
            (CONF_SALINITY_CRITICAL_MIN,CONF_SALINITY_MIN,CONF_SALINITY_MAX,CONF_SALINITY_CRITICAL_MAX),
        ]
        defaults = [(DEFAULT_TEMPERATURE_CRITICAL_MIN,DEFAULT_TEMPERATURE_MIN,DEFAULT_TEMPERATURE_MAX,DEFAULT_TEMPERATURE_CRITICAL_MAX),(DEFAULT_PH_CRITICAL_MIN,DEFAULT_PH_MIN,DEFAULT_PH_MAX,DEFAULT_PH_CRITICAL_MAX),(DEFAULT_SALINITY_CRITICAL_MIN,DEFAULT_SALINITY_MIN,DEFAULT_SALINITY_MAX,DEFAULT_SALINITY_CRITICAL_MAX)]
        for keys, defs in zip(groups, defaults):
            vals=[float(data.get(k,d)) for k,d in zip(keys,defs)]
            if not vals[0] <= vals[1] < vals[2] <= vals[3]: errors["base"]="invalid_limits"
        return errors
