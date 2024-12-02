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
    PROTOCOL_AD_DC,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    AD_DC_PORTS
)

_LOGGER = logging.getLogger(__name__)

def is_valid_ip(ip: str) -> bool:
    """Check if string is valid IP address."""
    try:
        return isinstance(ip_address(ip), IPv4Address)
    except ValueError:
        return False

class ConnectivityMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
<<<<<<< HEAD
=======
    """Handle a config flow for Connectivity Monitor."""
>>>>>>> b7094e84e6077e1e8ea9d1b5f942f9f8c962446e
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize the config flow."""
        self._data = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_HOST): str,
                    vol.Optional("device_name", description={"suggested_value": ""}): str,
                    vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In({
                        PROTOCOL_TCP: "TCP (Custom Port)",
                        PROTOCOL_UDP: "UDP (Custom Port)",
                        PROTOCOL_ICMP: "ICMP (Ping)",
                        PROTOCOL_AD_DC: "Active Directory DC"
                    }),
                })
            )

        self._data.update(user_input)
        protocol = self._data[CONF_PROTOCOL]

        if protocol in [PROTOCOL_TCP, PROTOCOL_UDP]:
            return await self.async_step_port()

        return await self.async_step_dns()

    async def async_step_port(self, user_input=None):
        """Handle port configuration."""
        if user_input is None:
            return self.async_show_form(
                step_id="port",
                data_schema=vol.Schema({
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                })
            )

        self._data.update(user_input)
        return await self.async_step_dns()

    async def async_step_dns(self, user_input=None):
        """Handle DNS server configuration."""
        errors = {}

        if user_input is not None:
            dns_server = user_input[CONF_DNS_SERVER]
            if is_valid_ip(dns_server):
                self._data[CONF_DNS_SERVER] = dns_server
                return await self.async_step_interval()
            errors["base"] = "invalid_dns_server"

        return self.async_show_form(
            step_id="dns",
            data_schema=vol.Schema({
                vol.Required(CONF_DNS_SERVER, default=DEFAULT_DNS_SERVER): str,
            }),
            errors=errors,
            description_placeholders={
                "default_dns": DEFAULT_DNS_SERVER
            }
        )

    async def async_step_interval(self, user_input=None):
        """Handle setting the update interval."""
        if user_input is None:
            return self.async_show_form(
                step_id="interval",
                data_schema=vol.Schema({
                    vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=300)
                    ),
                })
            )

        self._data[CONF_INTERVAL] = user_input[CONF_INTERVAL]
        return await self.async_step_finish()

    async def async_step_finish(self, user_input=None):
        """Create the config entry."""
        device_name = self._data.get("device_name", "").strip() or self._data[CONF_HOST]

        # Create a list of targets based on protocol
        targets = []
        if self._data[CONF_PROTOCOL] == PROTOCOL_AD_DC:
<<<<<<< HEAD
            from .const import AD_DC_PORTS
=======
>>>>>>> b7094e84e6077e1e8ea9d1b5f942f9f8c962446e
            targets.extend([{
                CONF_HOST: self._data[CONF_HOST],
                CONF_PROTOCOL: PROTOCOL_TCP,
                CONF_PORT: port,
                "device_name": device_name
            } for port in AD_DC_PORTS])
        else:
            target = {
                CONF_HOST: self._data[CONF_HOST],
                CONF_PROTOCOL: self._data[CONF_PROTOCOL],
                "device_name": device_name
            }
            if self._data[CONF_PROTOCOL] in [PROTOCOL_TCP, PROTOCOL_UDP]:
                target[CONF_PORT] = self._data[CONF_PORT]
            targets.append(target)

        return self.async_create_entry(
            title=device_name,
            data={
                CONF_TARGETS: targets,
                CONF_INTERVAL: self._data[CONF_INTERVAL],
                CONF_DNS_SERVER: self._data[CONF_DNS_SERVER]
            }
<<<<<<< HEAD
=======
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
        self._data = dict(config_entry.data)

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            self._data.update(user_input)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self._data
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_DNS_SERVER, default=self._data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)): str,
                vol.Required(CONF_INTERVAL, default=self._data.get(CONF_INTERVAL, DEFAULT_INTERVAL)): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            }),
>>>>>>> b7094e84e6077e1e8ea9d1b5f942f9f8c962446e
        )