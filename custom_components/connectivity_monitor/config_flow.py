"""Config flow for Connectivity Monitor integration."""
from __future__ import annotations

import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from ipaddress import ip_address, IPv4Address

from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

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
    """Handle a config flow for Connectivity Monitor."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._data = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        # Check if we already have an entry
        entries = self._async_current_entries()
        if entries:
            # Get the first entry and use its configuration
            entry = entries[0]
            existing_data = dict(entry.data)
            existing_targets = list(existing_data[CONF_TARGETS])

            # Pass the existing configuration to next step
            self._data = {
                CONF_INTERVAL: existing_data[CONF_INTERVAL],
                CONF_DNS_SERVER: existing_data[CONF_DNS_SERVER],
                CONF_TARGETS: existing_targets
            }

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
        elif not entries:  # Only ask for DNS and interval if this is first device
            return await self.async_step_dns()
        else:
            return await self.async_step_finish()

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
        if user_input is not None:
            self._data[CONF_INTERVAL] = user_input[CONF_INTERVAL]
            return await self.async_step_finish()

        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema({
                vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
            })
        )

    async def async_step_port(self, user_input=None):
        """Handle port configuration."""
        if user_input is not None:
            self._data.update(user_input)
            if not self._async_current_entries():
                return await self.async_step_dns()
            return await self.async_step_finish()

        return self.async_show_form(
            step_id="port",
            data_schema=vol.Schema({
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            })
        )

    async def async_step_finish(self, user_input=None):
        """Create or update the config entry."""
        device_name = self._data.get("device_name", "").strip() or self._data[CONF_HOST]

        # Get or create targets list
        targets = self._data.get(CONF_TARGETS, [])

        # Create new target(s)
        if self._data[CONF_PROTOCOL] == PROTOCOL_AD_DC:
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

        data = {
            CONF_TARGETS: targets,
            CONF_INTERVAL: self._data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
            CONF_DNS_SERVER: self._data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)
        }

        # If we have an existing entry, update it
        entries = self._async_current_entries()
        if entries:
            entry = entries[0]
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="device_added")

        # Otherwise create new entry
        return self.async_create_entry(
            title="Connectivity Monitor",
            data=data
        )

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.config_data = dict(config_entry.data)
        self._targets = list(self.config_data[CONF_TARGETS])

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        """Show the menu."""
        if user_input is not None:
            if user_input["next_step"] == "add_device":
                return await self.async_step_user()
            elif user_input["next_step"] == "remove_device":
                return await self.async_step_remove_device()
            elif user_input["next_step"] == "remove_sensor":
                return await self.async_step_remove_sensor()
            elif user_input["next_step"] == "settings":
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema({
                vol.Required("next_step"): vol.In({
#                     "add_device": "Add New Device",
                    "remove_device": "Remove Device",
                    "remove_sensor": "Remove Single Sensor",
                    "settings": "Change Settings"
                })
            })
        )

    async def async_step_remove_device(self, user_input=None):
        """Handle removing a complete device."""
        entity_registry = async_get_entity_registry(self.hass)
        device_registry = async_get_device_registry(self.hass)

        if user_input is not None:
            device_host = user_input["device"]

            # Remove all targets for this device
            self._targets = [t for t in self._targets if t[CONF_HOST] != device_host]

            # Find and remove all entities for this device
            entry_entities = async_entries_for_config_entry(entity_registry, self.config_entry.entry_id)
            for entity_entry in entry_entities:
                # Check if entity belongs to this device
                if entity_entry.unique_id.startswith(f"{device_host}_"):
                    entity_registry.async_remove(entity_entry.entity_id)

            # Find and remove the device
            device_id = None
            for device_entry in device_registry.devices.values():
                for identifier in device_entry.identifiers:
                    if identifier[0] == DOMAIN and identifier[1] == device_host:
                        device_id = device_entry.id
                        break
                if device_id:
                    device_registry.async_remove_device(device_id)
                    break

            # Update config entry
            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )

            # Reload the config entry
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        # Get unique devices
        devices = {}
        for target in self._targets:
            device_name = target.get("device_name", target[CONF_HOST])
            devices[target[CONF_HOST]] = device_name

        if not devices:
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In(
                    {host: f"{name} ({host})" for host, name in devices.items()}
                )
            })
        )

    async def async_step_remove_sensor(self, user_input=None):
        """Handle removing a single sensor."""
        entity_registry = async_get_entity_registry(self.hass)

        if user_input is not None:
            sensor_id = user_input["sensor"]

            # Find and remove the specific sensor from targets
            for i, target in enumerate(self._targets):
                current_id = f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}"
                if current_id == sensor_id:
                    self._targets.pop(i)
                    break

            # Get all entities for this config entry
            entry_entities = async_entries_for_config_entry(entity_registry, self.config_entry.entry_id)

            # Find and remove the entity
            for entity_entry in entry_entities:
                if entity_entry.unique_id == sensor_id:
                    entity_registry.async_remove(entity_entry.entity_id)

            # Update config entry
            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )

            # Reload the config entry
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        # Create list of sensors with readable names
        sensors = {}
        for target in self._targets:
            device_name = target.get("device_name", target[CONF_HOST])
            if target[CONF_PROTOCOL] in [PROTOCOL_TCP, PROTOCOL_UDP]:
                sensor_name = f"{device_name} - {target[CONF_PROTOCOL]} {target[CONF_PORT]}"
            else:
                sensor_name = f"{device_name} - {target[CONF_PROTOCOL]}"

            sensor_id = f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}"
            sensors[sensor_id] = sensor_name

        if not sensors:
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="remove_sensor",
            data_schema=vol.Schema({
                vol.Required("sensor"): vol.In(sensors)
            })
        )

    async def async_step_settings(self, user_input=None):
        """Handle changing settings."""
        if user_input is not None:
            self.config_data[CONF_INTERVAL] = user_input[CONF_INTERVAL]
            self.config_data[CONF_DNS_SERVER] = user_input[CONF_DNS_SERVER]

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Required(CONF_INTERVAL,
                           default=self.config_data[CONF_INTERVAL]): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Required(CONF_DNS_SERVER,
                           default=self.config_data[CONF_DNS_SERVER]): str,
            })
        )
