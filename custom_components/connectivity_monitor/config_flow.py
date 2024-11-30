"""Config flow for Connectivity Monitor integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from ipaddress import ip_address, IPv4Address

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL,
    DEFAULT_INTERVAL,
    CONF_PROTOCOL,
    CONF_INTERVAL,
    CONF_TARGETS,
    CONF_DNS_SERVER,
    DEFAULT_DNS_SERVER,
    PROTOCOLS,
    PROTOCOL_ICMP,
    PROTOCOL_RPC,
    PROTOCOL_AD_DC,
    PROTOCOL_TCP,
    PROTOCOL_UDP
)

_LOGGER = logging.getLogger(__name__)

def is_valid_ip(ip: str) -> bool:
    """Check if string is valid IP address."""
    try:
        return isinstance(ip_address(ip), IPv4Address)
    except ValueError:
        return False

def create_protocol_schema(protocol: str | None = None) -> vol.Schema:
    """Create a schema based on protocol."""
    schema = {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PROTOCOL, default=protocol or DEFAULT_PROTOCOL): vol.In(
            {
                PROTOCOL_TCP: "TCP (Custom Port)",
                PROTOCOL_UDP: "UDP (Custom Port)",
                PROTOCOL_ICMP: "ICMP (Ping)",
                PROTOCOL_RPC: "RPC (Standard Ports)",
                PROTOCOL_AD_DC: "Active Directory DC"
            }
        ),
    }

    # Only add port field if protocol is TCP or UDP
    if protocol in [PROTOCOL_TCP, PROTOCOL_UDP]:
        schema[vol.Required(CONF_PORT, default=DEFAULT_PORT)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        )

    return vol.Schema(schema)

class ConnectivityMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Connectivity Monitor."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return await self.async_step_dns_server()

    async def async_step_dns_server(self, user_input=None):
        """Handle DNS server configuration."""
        errors = {}

        if user_input is not None:
            dns_server = user_input[CONF_DNS_SERVER]
            if is_valid_ip(dns_server):
                self._dns_server = dns_server
                return await self.async_step_add_target()
            errors["base"] = "invalid_dns_server"

        return self.async_show_form(
            step_id="dns_server",
            data_schema=vol.Schema({
                vol.Required(CONF_DNS_SERVER, default=DEFAULT_DNS_SERVER): str,
            }),
            errors=errors,
            description_placeholders={
                "default_dns": DEFAULT_DNS_SERVER
            }
        )

    async def async_step_add_target(self, user_input=None):
        """Handle adding a target."""
        errors = {}

        if user_input is not None:
            target = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PROTOCOL: user_input[CONF_PROTOCOL],
            }

            # Handle port for TCP/UDP protocols
            if user_input[CONF_PROTOCOL] in [PROTOCOL_TCP, PROTOCOL_UDP]:
                target[CONF_PORT] = int(user_input[CONF_PORT])
                self._targets.append(target.copy())
            elif user_input[CONF_PROTOCOL] == PROTOCOL_RPC:
                # For RPC, create multiple targets for standard ports
                from .const import RPC_DEFAULT_PORTS
                self._targets.extend([
                    {
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PROTOCOL: PROTOCOL_TCP,  # RPC uses TCP
                        CONF_PORT: port
                    }
                    for port in RPC_DEFAULT_PORTS
                ])
            else:  # ICMP or AD_DC
                self._targets.append(target.copy())

            self._protocol = user_input[CONF_PROTOCOL]
            return await self.async_step_another()

        return self.async_show_form(
            step_id="add_target",
            data_schema=create_protocol_schema(self._protocol),
            errors=errors,
        )

    async def async_step_dns_server(self, user_input=None):
        """Handle DNS server configuration."""
        errors = {}

        if user_input is not None:
            dns_server = user_input[CONF_DNS_SERVER]
            if is_valid_ip(dns_server):
                self._dns_server = dns_server
                return await self.async_step_add_target()
            errors["base"] = "invalid_dns_server"

        return self.async_show_form(
            step_id="dns_server",
            data_schema=vol.Schema({
                vol.Required(CONF_DNS_SERVER, default=DEFAULT_DNS_SERVER): str,
            }),
            errors=errors,
            description_placeholders={
                "default_dns": DEFAULT_DNS_SERVER
            }
        )

    def _create_schema_for_protocol(self, protocol: str | None = None) -> vol.Schema:
        """Create a schema based on protocol."""
        schema = {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PROTOCOL, default=protocol or DEFAULT_PROTOCOL): vol.In(
                {
                    PROTOCOL_TCP: "TCP (Custom Port)",
                    PROTOCOL_UDP: "UDP (Custom Port)",
                    PROTOCOL_ICMP: "ICMP (Ping)",
                    PROTOCOL_RPC: "RPC (Standard Ports)",
                    PROTOCOL_AD_DC: "Active Directory DC"
                }
            ),
        }

        # Only add port field if protocol is TCP or UDP
        if protocol in [PROTOCOL_TCP, PROTOCOL_UDP]:
            schema[vol.Required(CONF_PORT, default=DEFAULT_PORT)] = vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            )

        return vol.Schema(schema)

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
                CONF_INTERVAL: self._interval,
                CONF_DNS_SERVER: self._dns_server
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
        self._dns_server = config_entry.data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)
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
            elif user_input["next_step"] == "change_dns":
                return await self.async_step_dns_server()
            else:  # finish
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_TARGETS: [target.copy() for target in self._targets],
                        CONF_INTERVAL: self._interval,
                        CONF_DNS_SERVER: self._dns_server,
                    }
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema({
                vol.Required("next_step"): vol.In({
                    "add_target": "Add New Target",
                    "remove_target": "Remove Target",
                    "set_interval": "Set Update Interval",
                    "change_dns": "Change DNS Server",
                    "finish": "Save Changes"
                })
            }),
            description_placeholders={
                "target_count": len(self._targets),
                "interval": self._interval,
                "dns_server": self._dns_server,
            }
        )

    async def async_step_dns_server(self, user_input=None):
        """Handle DNS server configuration."""
        errors = {}

        if user_input is not None:
            dns_server = user_input[CONF_DNS_SERVER]
            if is_valid_ip(dns_server):
                self._dns_server = dns_server
                return await self.async_step_menu()
            errors["base"] = "invalid_dns_server"

        return self.async_show_form(
            step_id="dns_server",
            data_schema=vol.Schema({
                vol.Required(CONF_DNS_SERVER, default=self._dns_server): str,
            }),
            errors=errors,
            description_placeholders={
                "current_dns": self._dns_server
            }
        )

    async def async_step_add_target(self, user_input=None):
        """Handle adding a target."""
        if user_input is not None:
            target = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PROTOCOL: user_input[CONF_PROTOCOL],
            }

            # Handle port for TCP/UDP protocols
            if user_input[CONF_PROTOCOL] in [PROTOCOL_TCP, PROTOCOL_UDP]:
                target[CONF_PORT] = int(user_input[CONF_PORT])
                self._targets.append(target.copy())
            elif user_input[CONF_PROTOCOL] == PROTOCOL_RPC:
                # For RPC, create multiple targets for standard ports
                from .const import RPC_DEFAULT_PORTS
                self._targets.extend([
                    {
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PROTOCOL: PROTOCOL_TCP,
                        CONF_PORT: port
                    }
                    for port in RPC_DEFAULT_PORTS
                ])
            else:  # ICMP or AD_DC
                self._targets.append(target.copy())

            self._protocol = user_input[CONF_PROTOCOL]
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="add_target",
            data_schema=create_protocol_schema(self._protocol),
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