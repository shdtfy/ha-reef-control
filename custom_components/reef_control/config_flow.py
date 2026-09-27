"""Config flow for Reef Control."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_AQUARIUM_NAME,
    CONF_REEF_METHOD,
    CONF_SUPPLY_SYSTEM,
    CONF_TANK_TYPE,
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
