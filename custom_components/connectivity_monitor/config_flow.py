# custom_components/connectivity_monitor/config_flow.py
"""Config flow for Connectivity Monitor integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_PROTOCOL, DEFAULT_INTERVAL, CONF_PROTOCOL, CONF_INTERVAL

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(["TCP", "UDP"]),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)

class ConnectivityMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Connectivity Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        return self.async_create_entry(
            title=f"Connectivity Monitor - {user_input[CONF_HOST]}",
            data=user_input,
        )