# custom_components/connectivity_monitor/config_flow.py
"""Config flow for Connectivity Monitor integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL,
    DEFAULT_INTERVAL,
    CONF_PROTOCOL,
    CONF_INTERVAL,
    CONF_TARGETS,
    PROTOCOLS,
    PROTOCOL_ICMP,
    PROTOCOL_RPC
)

_LOGGER = logging.getLogger(__name__)

def create_schema(protocol_default=DEFAULT_PROTOCOL):
    """Create a schema based on selected protocol."""
    schema = {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PROTOCOL, default=protocol_default): vol.In(PROTOCOLS),
    }

    # Only add port field if not ICMP
    if protocol_default not in [PROTOCOL_ICMP, PROTOCOL_RPC]:
        schema[vol.Required(CONF_PORT, default=DEFAULT_PORT)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        )

    return vol.Schema(schema)

class ConnectivityMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Connectivity Monitor."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._targets = []
        self._interval = DEFAULT_INTERVAL
        self._protocol = DEFAULT_PROTOCOL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return await self.async_step_add_target()

    async def async_step_add_target(self, user_input=None):
        """Handle adding a target."""
        errors = {}

        if user_input is not None:
            target = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PROTOCOL: user_input[CONF_PROTOCOL],
            }

            # Add port if not ICMP or RPC
            if user_input[CONF_PROTOCOL] not in [PROTOCOL_ICMP, PROTOCOL_RPC]:
                target[CONF_PORT] = int(user_input[CONF_PORT])
            elif user_input[CONF_PROTOCOL] == PROTOCOL_RPC:
                # For RPC, we'll create multiple targets for standard ports
                from .const import RPC_DEFAULT_PORTS
                self._targets.extend([
                    {
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PROTOCOL: "TCP",  # RPC uses TCP
                        CONF_PORT: port
                    }
                    for port in RPC_DEFAULT_PORTS
                ])
                return await self.async_step_another()

            self._targets.append(target.copy())
            self._protocol = user_input[CONF_PROTOCOL]  # Remember protocol for next target
            return await self.async_step_another()

        return self.async_show_form(
            step_id="add_target",
            data_schema=create_schema(self._protocol),
            errors=errors,
        )

    async def async_step_another(self, user_input=None):
        """Handle adding another target or finishing setup."""
        if user_input is not None:
            if user_input.get("another"):
                return await self.async_step_add_target()
            return await self.async_step_interval()

        return self.async_show_form(
            step_id="another",
            data_schema=vol.Schema({
                vol.Required("another", default=True): bool,
            }),
            description_placeholders={
                "target_count": len(self._targets),
            }
        )

    async def async_step_interval(self, user_input=None):
        """Handle setting the update interval."""
        if user_input is not None:
            self._interval = user_input[CONF_INTERVAL]

            data = {
                CONF_TARGETS: [target.copy() for target in self._targets],
                CONF_INTERVAL: self._interval
            }

            return self.async_create_entry(
                title=f"Connectivity Monitor ({len(self._targets)} targets)",
                data=data
            )

        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema({
                vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Connectivity Monitor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._targets = [target.copy() for target in config_entry.data[CONF_TARGETS]]
        self._interval = config_entry.data[CONF_INTERVAL]
        self._protocol = DEFAULT_PROTOCOL

    async def async_step_init(self, user_input=None):
        """Handle the initial step."""
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        """Handle the menu step."""
        if user_input is not None:
            if user_input["next_step"] == "add_target":
                return await self.async_step_add_target()
            elif user_input["next_step"] == "remove_target":
                return await self.async_step_remove_target()
            elif user_input["next_step"] == "set_interval":
                return await self.async_step_interval()
            else:  # finish
                # Update the configuration entry with new data
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_TARGETS: [target.copy() for target in self._targets],
                        CONF_INTERVAL: self._interval,
                    }
                )

                # Reload the config entry to apply changes
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema({
                vol.Required("next_step"): vol.In({
                    "add_target": "Add New Target",
                    "remove_target": "Remove Target",
                    "set_interval": "Set Update Interval",
                    "finish": "Save Changes"
                })
            }),
            description_placeholders={
                "target_count": len(self._targets),
                "interval": self._interval,
            }
        )

    async def async_step_add_target(self, user_input=None):
        """Handle adding a target."""
        if user_input is not None:
            target = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PROTOCOL: user_input[CONF_PROTOCOL],
            }

            # Add port if not ICMP or RPC
            if user_input[CONF_PROTOCOL] not in [PROTOCOL_ICMP, PROTOCOL_RPC]:
                target[CONF_PORT] = int(user_input[CONF_PORT])
            elif user_input[CONF_PROTOCOL] == PROTOCOL_RPC:
                # For RPC, create multiple targets for standard ports
                from .const import RPC_DEFAULT_PORTS
                self._targets.extend([
                    {
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PROTOCOL: "TCP",  # RPC uses TCP
                        CONF_PORT: port
                    }
                    for port in RPC_DEFAULT_PORTS
                ])
                return await self.async_step_menu()

            self._targets.append(target.copy())
            self._protocol = user_input[CONF_PROTOCOL]
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="add_target",
            data_schema=create_schema(self._protocol),
        )

    async def async_step_remove_target(self, user_input=None):
        """Handle removing a target."""
        if user_input is not None:
            target_index = user_input["target_index"]
            if target_index < len(self._targets):
                self._targets.pop(target_index)
            return await self.async_step_menu()

        target_names = [
            f"{t[CONF_HOST]} - {t[CONF_PROTOCOL]} {t.get(CONF_PORT, 'ping')}"
            for t in self._targets
        ]

        if not target_names:
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="remove_target",
            data_schema=vol.Schema({
                vol.Required("target_index"): vol.In(
                    {i: name for i, name in enumerate(target_names)}
                ),
            }),
        )

    async def async_step_interval(self, user_input=None):
        """Handle setting the update interval."""
        if user_input is not None:
            self._interval = user_input[CONF_INTERVAL]
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema({
                vol.Required(CONF_INTERVAL, default=self._interval): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            }),
        )