"""Config flow for Reef Control."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AQUARIUM_NAME,
    CONF_ATO_ENTITY,
    CONF_FLOW_PUMP_ENTITY,
    CONF_HEATER_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_PH_ENTITY,
    CONF_REEF_METHOD,
    CONF_RETURN_PUMP_ENTITY,
    CONF_SALINITY_ENTITY,
    CONF_SKIMMER_ENTITY,
    CONF_SUPPLY_SYSTEM,
    CONF_TANK_TYPE,
    CONF_TEMPERATURE_ENTITY,
    CONF_VOLUME,
    DEFAULT_AQUARIUM_NAME,
    DOMAIN,
)


class ReefControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Reef Control."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> FlowResult:
        """Handle the initial setup step."""

        if user_input is not None:
            aquarium_name = user_input[CONF_AQUARIUM_NAME].strip()

            await self.async_set_unique_id(aquarium_name.lower())
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=aquarium_name,
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AQUARIUM_NAME,
                    default=DEFAULT_AQUARIUM_NAME,
                ): str,
                vol.Required(CONF_VOLUME): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=1),
                ),
                vol.Optional(CONF_TANK_TYPE, default="mixed_reef"): vol.In(
                    {
                        "mixed_reef": "Mixed Reef",
                        "sps": "SPS Reef",
                        "lps": "LPS Reef",
                        "soft_coral": "Soft Coral Reef",
                        "fish_only": "Fish Only",
                        "other": "Other",
                    }
                ),
                vol.Optional(CONF_SUPPLY_SYSTEM, default="none"): vol.In(
                    {
                        "none": "None / Other",
                        "fauna_marin_balling_light": "Fauna Marin Balling Light",
                        "ati_essentials": "ATI Essentials",
                        "oceamo_duo": "Oceamo DUO",
                        "triton": "Triton Method",
                        "other": "Other",
                    }
                ),
                vol.Optional(CONF_REEF_METHOD, default="none"): vol.In(
                    {
                        "none": "None",
                        "berlin": "Berlin Method",
                        "triton": "Triton Method",
                        "dsr": "DSR",
                        "other": "Other",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ReefControlOptionsFlow:
        """Return the options flow."""
        return ReefControlOptionsFlow(config_entry)


class ReefControlOptionsFlow(config_entries.OptionsFlow):
    """Handle Reef Control options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize Reef Control options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict | None = None,
    ) -> FlowResult:
        """Manage Reef Control entity assignments."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        options = self._config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TEMPERATURE_ENTITY,
                    description={"suggested_value": options.get(CONF_TEMPERATURE_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_PH_ENTITY,
                    description={"suggested_value": options.get(CONF_PH_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_SALINITY_ENTITY,
                    description={"suggested_value": options.get(CONF_SALINITY_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_SKIMMER_ENTITY,
                    description={"suggested_value": options.get(CONF_SKIMMER_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Optional(
                    CONF_RETURN_PUMP_ENTITY,
                    description={"suggested_value": options.get(CONF_RETURN_PUMP_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Optional(
                    CONF_FLOW_PUMP_ENTITY,
                    description={"suggested_value": options.get(CONF_FLOW_PUMP_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Optional(
                    CONF_LIGHT_ENTITY,
                    description={"suggested_value": options.get(CONF_LIGHT_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["light", "switch", "input_boolean"])
                ),
                vol.Optional(
                    CONF_HEATER_ENTITY,
                    description={"suggested_value": options.get(CONF_HEATER_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
                vol.Optional(
                    CONF_ATO_ENTITY,
                    description={"suggested_value": options.get(CONF_ATO_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
