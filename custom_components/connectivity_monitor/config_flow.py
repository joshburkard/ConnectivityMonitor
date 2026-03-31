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
    DEFAULT_ALERT_DELAY,
    CONF_PROTOCOL,
    CONF_INTERVAL,
    CONF_TARGETS,
    CONF_DNS_SERVER,
    CONF_ALERT_GROUP,
    CONF_ALERT_DELAY,
    CONF_ALERTS_ENABLED,
    CONF_ALERT_ACTION_ENABLED,
    CONF_ALERT_ACTION,
    CONF_ALERT_ACTION_DELAY,
    DEFAULT_ALERT_ACTION_DELAY,
    DEFAULT_DNS_SERVER,
    DEFAULT_ALERT_GROUP,
    PROTOCOLS,
    PROTOCOL_ICMP,
    PROTOCOL_AD_DC,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    PROTOCOL_ZHA,
    PROTOCOL_MATTER,
    CONF_ZHA_IEEE,
    CONF_INACTIVE_TIMEOUT,
    DEFAULT_INACTIVE_TIMEOUT,
    CONF_MATTER_NODE_ID,
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
        # ZHA device selection state (reused across main and options flows)
        self._zha_selected_ieee: str | None = None
        self._zha_selected_name: str | None = None
        self._zha_selected_model: str | None = None
        self._zha_selected_manufacturer: str | None = None
        # Matter device selection state
        self._matter_selected_node_id: str | None = None
        self._matter_selected_name: str | None = None
        self._matter_selected_model: str | None = None
        self._matter_selected_manufacturer: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def _async_get_notify_groups(self):
        """Get list of notification groups from Home Assistant."""
        notify_services = self.hass.services.async_services().get("notify", {})
        groups = {name: name.replace("notify.", "") for name in notify_services.keys()}
        return groups

    async def _async_get_alert_actions(self):
        """Get available automations and scripts that can be triggered as alert actions."""
        actions = {}
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            domain = entity_id.split(".")[0]
            if domain in ("automation", "script"):
                name = state.attributes.get("friendly_name") or entity_id
                actions[entity_id] = f"{name} ({entity_id})"
        return dict(sorted(actions.items(), key=lambda x: x[1].lower()))

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user — choose device type."""
        # Check if we already have an entry and carry its settings forward
        entries = self._async_current_entries()
        if entries:
            entry = entries[0]
            existing_data = dict(entry.data)
            self._data = {
                CONF_INTERVAL: existing_data[CONF_INTERVAL],
                CONF_DNS_SERVER: existing_data[CONF_DNS_SERVER],
                CONF_TARGETS: list(existing_data[CONF_TARGETS]),
            }

        if user_input is not None:
            if user_input["device_type"] == "zha":
                return await self.async_step_zha_device()
            elif user_input["device_type"] == "matter":
                return await self.async_step_matter_device()
            else:
                return await self.async_step_network()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("device_type", default="network"): vol.In({
                    "network": "Network Device (TCP / UDP / ICMP / AD)",
                    "zha": "ZigBee Device (ZHA)",
                    "matter": "Matter Device",
                }),
            }),
        )

    async def async_step_network(self, user_input=None):
        """Configure a network device to monitor."""
        errors = {}
        entries = self._async_current_entries()

        if user_input is not None:
            try:
                self._data.update({
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PROTOCOL: user_input[CONF_PROTOCOL],
                    "device_name": user_input.get("device_name", ""),
                    CONF_ALERTS_ENABLED: user_input.get(CONF_ALERTS_ENABLED, False),
                    CONF_ALERT_GROUP: (
                        user_input.get(CONF_ALERT_GROUP, "") or DEFAULT_ALERT_GROUP
                    ) if user_input.get(CONF_ALERTS_ENABLED) else DEFAULT_ALERT_GROUP,
                    CONF_ALERT_DELAY: user_input.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                    CONF_ALERT_ACTION_ENABLED: user_input.get(CONF_ALERT_ACTION_ENABLED, False),
                    CONF_ALERT_ACTION: (
                        user_input.get(CONF_ALERT_ACTION, "") or ""
                    ) if user_input.get(CONF_ALERT_ACTION_ENABLED) else "",
                    CONF_ALERT_ACTION_DELAY: user_input.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY),
                })

                protocol = self._data[CONF_PROTOCOL]
                if protocol in [PROTOCOL_TCP, PROTOCOL_UDP]:
                    return await self.async_step_port()
                elif not entries:
                    return await self.async_step_dns()
                else:
                    return await self.async_step_finish()
            except Exception as ex:
                _LOGGER.exception("Error in network step: %s", ex)
                errors["base"] = "unknown"

        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()

        schema = {
            vol.Required(CONF_HOST): str,
            vol.Optional("device_name", description={"suggested_value": ""}): str,
            vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In({
                PROTOCOL_TCP: "TCP (Custom Port)",
                PROTOCOL_UDP: "UDP (Custom Port)",
                PROTOCOL_ICMP: "ICMP (Ping)",
                PROTOCOL_AD_DC: "Active Directory DC",
            }),
            vol.Optional(CONF_ALERTS_ENABLED, default=False): bool,
            vol.Required(CONF_ALERT_DELAY, default=DEFAULT_ALERT_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
        }

        if notify_groups:
            notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
            notify_groups_dict[""] = "No alert group"
            schema[vol.Optional(CONF_ALERT_GROUP, default="")] = vol.In(notify_groups_dict)

        schema[vol.Optional(CONF_ALERT_ACTION_ENABLED, default=False)] = bool
        schema[vol.Required(CONF_ALERT_ACTION_DELAY, default=DEFAULT_ALERT_ACTION_DELAY)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        )
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION, default="")] = vol.In(actions_dict)

        return self.async_show_form(
            step_id="network",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_zha_device(self, user_input=None):
        """Select a ZHA device to add to monitoring (main config flow)."""
        from .zha import async_get_zha_devices

        entries = self._async_current_entries()
        existing_ieees = {
            t.get(CONF_ZHA_IEEE)
            for t in self._data.get(CONF_TARGETS, [])
            if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA
        }

        zha_devices = await async_get_zha_devices(self.hass)
        if not zha_devices:
            return self.async_show_form(
                step_id="zha_device",
                errors={"base": "no_zha_devices"},
                data_schema=vol.Schema({}),
            )

        available = [d for d in zha_devices if d["ieee"] not in existing_ieees]
        if not available:
            return self.async_show_form(
                step_id="zha_device",
                errors={"base": "all_zha_devices_added"},
                data_schema=vol.Schema({}),
            )

        if user_input is not None:
            self._zha_selected_ieee = user_input[CONF_ZHA_IEEE]
            matched = next(
                (d for d in zha_devices if d["ieee"] == self._zha_selected_ieee), {}
            )
            self._zha_selected_name = matched.get("name") or self._zha_selected_ieee
            self._zha_selected_model = matched.get("model")
            self._zha_selected_manufacturer = matched.get("manufacturer")
            return await self.async_step_zha_configure()

        device_choices = {
            d["ieee"]: f"{d['name']} ({d['ieee']})"
            for d in sorted(available, key=lambda x: x["name"].lower())
        }
        return self.async_show_form(
            step_id="zha_device",
            data_schema=vol.Schema({
                vol.Required(CONF_ZHA_IEEE): vol.In(device_choices),
            }),
        )

    async def async_step_zha_configure(self, user_input=None):
        """Set device name, inactivity timeout, and alert settings for the selected ZHA device."""
        entries = self._async_current_entries()

        if user_input is not None:
            device_name = (user_input.get("device_name") or "").strip() or self._zha_selected_name
            alerts_enabled = user_input.get(CONF_ALERTS_ENABLED, False)
            action_enabled = user_input.get(CONF_ALERT_ACTION_ENABLED, False)
            new_target = {
                CONF_PROTOCOL: PROTOCOL_ZHA,
                CONF_HOST: f"zha:{self._zha_selected_ieee}",
                CONF_ZHA_IEEE: self._zha_selected_ieee,
                "device_name": device_name,
                CONF_INACTIVE_TIMEOUT: user_input[CONF_INACTIVE_TIMEOUT],
                CONF_ALERT_GROUP: (
                    user_input.get(CONF_ALERT_GROUP, "") or DEFAULT_ALERT_GROUP
                ) if alerts_enabled else DEFAULT_ALERT_GROUP,
                CONF_ALERT_DELAY: user_input.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                CONF_ALERT_ACTION: (
                    user_input.get(CONF_ALERT_ACTION, "") or ""
                ) if action_enabled else "",
                CONF_ALERT_ACTION_DELAY: user_input.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY),
            }
            if self._zha_selected_model:
                new_target["model"] = self._zha_selected_model
            if self._zha_selected_manufacturer:
                new_target["manufacturer"] = self._zha_selected_manufacturer

            targets = list(self._data.get(CONF_TARGETS, []))
            targets.append(new_target)
            self._data[CONF_TARGETS] = targets
            self._data[CONF_PROTOCOL] = PROTOCOL_ZHA  # signal finish() to skip port/DNS

            if not entries:
                # First-ever entry: still need DNS + interval
                return await self.async_step_dns()
            return await self.async_step_finish()

        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()
        schema = {
            vol.Optional("device_name", default=self._zha_selected_name or ""): str,
            vol.Required(CONF_INACTIVE_TIMEOUT, default=DEFAULT_INACTIVE_TIMEOUT): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=1440)
            ),
            vol.Optional(CONF_ALERTS_ENABLED, default=False): bool,
            vol.Required(CONF_ALERT_DELAY, default=DEFAULT_ALERT_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
        }
        if notify_groups:
            notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
            notify_groups_dict[""] = "No alert group"
            schema[vol.Optional(CONF_ALERT_GROUP, default="")] = vol.In(notify_groups_dict)
        schema[vol.Optional(CONF_ALERT_ACTION_ENABLED, default=False)] = bool
        schema[vol.Required(CONF_ALERT_ACTION_DELAY, default=DEFAULT_ALERT_ACTION_DELAY)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        )
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION, default="")] = vol.In(actions_dict)

        return self.async_show_form(
            step_id="zha_configure",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "device_name": self._zha_selected_name or "",
                "ieee": self._zha_selected_ieee or "",
            },
        )

    async def async_step_matter_device(self, user_input=None):
        """Select a Matter device to add to monitoring (main config flow)."""
        from .matter import async_get_matter_devices

        entries = self._async_current_entries()
        existing_node_ids = {
            t.get(CONF_MATTER_NODE_ID)
            for t in self._data.get(CONF_TARGETS, [])
            if t.get(CONF_PROTOCOL) == PROTOCOL_MATTER
        }

        matter_devices = await async_get_matter_devices(self.hass)
        if not matter_devices:
            return self.async_show_form(
                step_id="matter_device",
                errors={"base": "no_matter_devices"},
                data_schema=vol.Schema({}),
            )

        available = [d for d in matter_devices if d["node_id"] not in existing_node_ids]
        if not available:
            return self.async_show_form(
                step_id="matter_device",
                errors={"base": "all_matter_devices_added"},
                data_schema=vol.Schema({}),
            )

        if user_input is not None:
            self._matter_selected_node_id = user_input[CONF_MATTER_NODE_ID]
            matched = next(
                (d for d in matter_devices if d["node_id"] == self._matter_selected_node_id), {}
            )
            self._matter_selected_name = matched.get("name") or self._matter_selected_node_id
            self._matter_selected_model = matched.get("model")
            self._matter_selected_manufacturer = matched.get("manufacturer")
            return await self.async_step_matter_configure()

        device_choices = {
            d["node_id"]: f"{d['name']} ({d['node_id']})"
            for d in sorted(available, key=lambda x: x["name"].lower())
        }
        return self.async_show_form(
            step_id="matter_device",
            data_schema=vol.Schema({
                vol.Required(CONF_MATTER_NODE_ID): vol.In(device_choices),
            }),
        )

    async def async_step_matter_configure(self, user_input=None):
        """Set device name, inactivity timeout, and alert settings for the selected Matter device."""
        entries = self._async_current_entries()

        if user_input is not None:
            device_name = (user_input.get("device_name") or "").strip() or self._matter_selected_name
            alerts_enabled = user_input.get(CONF_ALERTS_ENABLED, False)
            action_enabled = user_input.get(CONF_ALERT_ACTION_ENABLED, False)
            new_target = {
                CONF_PROTOCOL: PROTOCOL_MATTER,
                CONF_HOST: f"matter:{self._matter_selected_node_id}",
                CONF_MATTER_NODE_ID: self._matter_selected_node_id,
                "device_name": device_name,
                CONF_ALERT_GROUP: (
                    user_input.get(CONF_ALERT_GROUP, "") or DEFAULT_ALERT_GROUP
                ) if alerts_enabled else DEFAULT_ALERT_GROUP,
                CONF_ALERT_DELAY: user_input.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                CONF_ALERT_ACTION: (
                    user_input.get(CONF_ALERT_ACTION, "") or ""
                ) if action_enabled else "",
                CONF_ALERT_ACTION_DELAY: user_input.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY),
            }
            if self._matter_selected_model:
                new_target["model"] = self._matter_selected_model
            if self._matter_selected_manufacturer:
                new_target["manufacturer"] = self._matter_selected_manufacturer

            targets = list(self._data.get(CONF_TARGETS, []))
            targets.append(new_target)
            self._data[CONF_TARGETS] = targets
            self._data[CONF_PROTOCOL] = PROTOCOL_MATTER

            if not entries:
                return await self.async_step_dns()
            return await self.async_step_finish()

        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()
        schema = {
            vol.Optional("device_name", default=self._matter_selected_name or ""): str,
            vol.Optional(CONF_ALERTS_ENABLED, default=False): bool,
            vol.Required(CONF_ALERT_DELAY, default=DEFAULT_ALERT_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
        }
        if notify_groups:
            notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
            notify_groups_dict[""] = "No alert group"
            schema[vol.Optional(CONF_ALERT_GROUP, default="")] = vol.In(notify_groups_dict)
        schema[vol.Optional(CONF_ALERT_ACTION_ENABLED, default=False)] = bool
        schema[vol.Required(CONF_ALERT_ACTION_DELAY, default=DEFAULT_ALERT_ACTION_DELAY)] = vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        )
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION, default="")] = vol.In(actions_dict)

        return self.async_show_form(
            step_id="matter_configure",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "device_name": self._matter_selected_name or "",
                "node_id": self._matter_selected_node_id or "",
            },
        )

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
        entries = self._async_current_entries()

        # For ZHA/Matter targets the target was already appended to self._data[CONF_TARGETS]
        # in their configure steps; nothing else to add here.
        if self._data.get(CONF_PROTOCOL) not in (PROTOCOL_ZHA, PROTOCOL_MATTER):
            device_name = self._data.get("device_name", "").strip() or self._data[CONF_HOST]

            if entries:
                entry = entries[0]
                existing_data = dict(entry.data)
                targets = list(existing_data[CONF_TARGETS])
            else:
                targets = []

            base_target = {
                CONF_HOST: self._data[CONF_HOST],
                CONF_PROTOCOL: self._data[CONF_PROTOCOL],
                "device_name": device_name,
                CONF_ALERT_GROUP: self._data.get(CONF_ALERT_GROUP, DEFAULT_ALERT_GROUP),
                CONF_ALERT_DELAY: self._data.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                CONF_ALERT_ACTION: self._data.get(CONF_ALERT_ACTION, ""),
                CONF_ALERT_ACTION_DELAY: self._data.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY),
            }

            if self._data[CONF_PROTOCOL] == PROTOCOL_AD_DC:
                for port in AD_DC_PORTS:
                    target = base_target.copy()
                    target[CONF_PROTOCOL] = PROTOCOL_TCP
                    target[CONF_PORT] = port
                    targets.append(target)
            else:
                if self._data[CONF_PROTOCOL] in [PROTOCOL_TCP, PROTOCOL_UDP]:
                    base_target[CONF_PORT] = self._data[CONF_PORT]
                targets.append(base_target)
        else:
            # ZHA / Matter path: targets list was already updated in the configure step
            targets = list(self._data.get(CONF_TARGETS, []))

        data = {
            CONF_TARGETS: targets,
            CONF_INTERVAL: self._data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
            CONF_DNS_SERVER: self._data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER),
        }

        if entries:
            entry = entries[0]
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="device_added")

        return self.async_create_entry(
            title="Connectivity Monitor",
            data=data,
        )

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self.config_data = {}
        self._targets = []
        self._selected_device = None
        # ZHA device selection state
        self._zha_selected_ieee: str | None = None
        self._zha_selected_name: str | None = None
        self._zha_selected_model: str | None = None
        self._zha_selected_manufacturer: str | None = None
        # Matter device selection state
        self._matter_selected_node_id: str | None = None
        self._matter_selected_name: str | None = None
        self._matter_selected_model: str | None = None
        self._matter_selected_manufacturer: str | None = None

    async def _async_get_notify_groups(self):
        """Get list of notification groups from Home Assistant."""
        notify_services = self.hass.services.async_services().get("notify", {})
        groups = {name: name.replace("notify.", "") for name in notify_services.keys()}
        return groups

    async def _async_get_alert_actions(self):
        """Get available automations and scripts that can be triggered as alert actions."""
        actions = {}
        for state in self.hass.states.async_all():
            entity_id = state.entity_id
            domain = entity_id.split(".")[0]
            if domain in ("automation", "script"):
                name = state.attributes.get("friendly_name") or entity_id
                actions[entity_id] = f"{name} ({entity_id})"
        return dict(sorted(actions.items(), key=lambda x: x[1].lower()))

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        self.config_data = dict(self.config_entry.data)
        self._targets = list(self.config_data[CONF_TARGETS])
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        """Show the top-level category menu."""
        if user_input is not None:
            category = user_input["category"]
            if category == "network":
                return await self.async_step_network_menu()
            elif category == "zha":
                return await self.async_step_zha_menu()
            elif category == "matter":
                return await self.async_step_matter_menu()
            elif category == "settings":
                return await self.async_step_settings()
            elif category == "cleanup":
                return await self.async_step_cleanup_orphans()

        has_network = any(t.get(CONF_PROTOCOL) not in (PROTOCOL_ZHA, PROTOCOL_MATTER) for t in self._targets)
        has_zha = any(t.get(CONF_PROTOCOL) == PROTOCOL_ZHA for t in self._targets)
        has_matter = any(t.get(CONF_PROTOCOL) == PROTOCOL_MATTER for t in self._targets)

        categories = {}
        if has_network:
            categories["network"] = "Network Device"
        if has_zha:
            categories["zha"] = "ZigBee (ZHA) Device"
        if has_matter:
            categories["matter"] = "Matter Device"
        categories["settings"] = "General Settings"
        categories["cleanup"] = "Clean up Orphaned Devices"

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema({
                vol.Required("category"): vol.In(categories),
            }),
        )

    async def async_step_network_menu(self, user_input=None):
        """Show the Network Device sub-menu."""
        if user_input is not None:
            action = user_input["action"]
            if action == "rename":
                return await self.async_step_rename_device_select()
            elif action == "alerts":
                return await self.async_step_device_select()
            elif action == "remove_device":
                return await self.async_step_remove_device()
            elif action == "remove_sensor":
                return await self.async_step_remove_sensor()

        return self.async_show_form(
            step_id="network_menu",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In({
                    "rename": "Change Host / Device Name",
                    "alerts": "Modify Alert Settings",
                    "remove_device": "Remove Device",
                    "remove_sensor": "Remove Single Sensor",
                }),
            }),
        )

    async def async_step_zha_menu(self, user_input=None):
        """Show the ZigBee (ZHA) Device sub-menu."""
        if user_input is not None:
            action = user_input["action"]
            if action == "timeout":
                return await self.async_step_zha_select_for_timeout()
            elif action == "alerts":
                return await self.async_step_zha_alert_select()
            elif action == "remove":
                return await self.async_step_remove_zha_device()

        return self.async_show_form(
            step_id="zha_menu",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In({
                    "timeout": "Change Inactivity Timeout",
                    "alerts": "Modify Alert Settings",
                    "remove": "Remove Device",
                }),
            }),
        )

    async def async_step_matter_menu(self, user_input=None):
        """Show the Matter Device sub-menu."""
        if user_input is not None:
            action = user_input["action"]
            if action == "alerts":
                return await self.async_step_matter_alert_select()
            elif action == "remove":
                return await self.async_step_remove_matter_device()

        return self.async_show_form(
            step_id="matter_menu",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In({
                    "alerts": "Modify Alert Settings",
                    "remove": "Remove Device",
                }),
            }),
        )

    async def async_step_matter_alert_select(self, user_input=None):
        """Select which Matter device to configure alerts for."""
        matter_targets = [t for t in self._targets if t.get(CONF_PROTOCOL) == PROTOCOL_MATTER]
        if not matter_targets:
            return await self.async_step_menu()

        if user_input is not None:
            self._matter_selected_node_id = user_input["node_id"]
            return await self.async_step_matter_alert_config()

        devices = {
            t[CONF_MATTER_NODE_ID]: f"{t.get('device_name', t[CONF_MATTER_NODE_ID])} ({t[CONF_MATTER_NODE_ID]})"
            for t in sorted(matter_targets, key=lambda x: x.get("device_name", ""))
        }
        return self.async_show_form(
            step_id="matter_alert_select",
            data_schema=vol.Schema({
                vol.Required("node_id"): vol.In(devices),
            }),
        )

    async def async_step_matter_alert_config(self, user_input=None):
        """Configure alert settings for the selected Matter device."""
        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()

        current_target = next(
            (t for t in self._targets
             if t.get(CONF_PROTOCOL) == PROTOCOL_MATTER and t.get(CONF_MATTER_NODE_ID) == self._matter_selected_node_id),
            {}
        )
        current_alert_group = current_target.get(CONF_ALERT_GROUP, "")
        current_alert_delay = current_target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
        current_alerts_enabled = bool(current_alert_group)
        current_alert_action = current_target.get(CONF_ALERT_ACTION, "")
        current_action_delay = current_target.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY)
        current_action_enabled = bool(current_alert_action)

        if user_input is not None:
            alerts_enabled = user_input.get(CONF_ALERTS_ENABLED, False)
            alert_group = user_input.get(CONF_ALERT_GROUP, "") if alerts_enabled else ""
            action_enabled = user_input.get(CONF_ALERT_ACTION_ENABLED, False)
            alert_action = user_input.get(CONF_ALERT_ACTION, "") if action_enabled else ""
            for t in self._targets:
                if t.get(CONF_PROTOCOL) == PROTOCOL_MATTER and t.get(CONF_MATTER_NODE_ID) == self._matter_selected_node_id:
                    if alert_group:
                        t[CONF_ALERT_GROUP] = alert_group
                    else:
                        t.pop(CONF_ALERT_GROUP, None)
                    t[CONF_ALERT_DELAY] = user_input[CONF_ALERT_DELAY]
                    if alert_action:
                        t[CONF_ALERT_ACTION] = alert_action
                    else:
                        t.pop(CONF_ALERT_ACTION, None)
                    t[CONF_ALERT_ACTION_DELAY] = user_input[CONF_ALERT_ACTION_DELAY]

            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
        notify_groups_dict[""] = "No alert group"
        schema = {
            vol.Optional(CONF_ALERTS_ENABLED, default=current_alerts_enabled): bool,
            vol.Optional(CONF_ALERT_GROUP, default=current_alert_group): vol.In(notify_groups_dict),
            vol.Required(CONF_ALERT_DELAY, default=current_alert_delay): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
            vol.Optional(CONF_ALERT_ACTION_ENABLED, default=current_action_enabled): bool,
            vol.Required(CONF_ALERT_ACTION_DELAY, default=current_action_delay): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=120)
            ),
        }
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION, default=current_alert_action)] = vol.In(actions_dict)
        return self.async_show_form(
            step_id="matter_alert_config",
            data_schema=vol.Schema(schema),
        )

    async def async_step_remove_matter_device(self, user_input=None):
        """Remove a monitored Matter device."""
        entity_registry = async_get_entity_registry(self.hass)

        matter_targets = [t for t in self._targets if t.get(CONF_PROTOCOL) == PROTOCOL_MATTER]
        if not matter_targets:
            return await self.async_step_menu()

        if user_input is not None:
            node_id = user_input["node_id"]

            # Remove from targets list
            self._targets = [
                t for t in self._targets
                if not (t.get(CONF_PROTOCOL) == PROTOCOL_MATTER and t.get(CONF_MATTER_NODE_ID) == node_id)
            ]

            # Remove only our monitoring entity — the Matter device itself stays
            node_id_clean = node_id.replace("-", "_").replace(":", "_")
            unique_id = f"connectivity_matter_{node_id_clean}"
            entry_entities = async_entries_for_config_entry(
                entity_registry, self.config_entry.entry_id
            )
            for entity_entry in entry_entities:
                if entity_entry.unique_id == unique_id:
                    entity_registry.async_remove(entity_entry.entity_id)
                    break

            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        devices = {
            t[CONF_MATTER_NODE_ID]: f"{t.get('device_name', t[CONF_MATTER_NODE_ID])} ({t[CONF_MATTER_NODE_ID]})"
            for t in sorted(matter_targets, key=lambda x: x.get("device_name", ""))
        }
        return self.async_show_form(
            step_id="remove_matter_device",
            data_schema=vol.Schema({
                vol.Required("node_id"): vol.In(devices),
            }),
        )

    async def async_step_rename_device_select(self, user_input=None):
        """Select which device to rename (network devices only)."""
        devices = {}
        for target in self._targets:
            if target.get(CONF_PROTOCOL) in (PROTOCOL_ZHA, PROTOCOL_MATTER):
                continue  # ZHA and Matter devices don't support host renaming
            device_host = target[CONF_HOST]
            if device_host not in devices:
                device_name = target.get("device_name", device_host)
                devices[device_host] = device_name

        if user_input is not None:
            self._selected_device = user_input["device"]
            return await self.async_step_rename_host()

        return self.async_show_form(
            step_id="rename_device_select",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In(
                    dict(sorted(
                        {host: f"{name} ({host})" for host, name in devices.items()}.items(),
                        key=lambda x: x[1].lower()
                    ))
                )
            })
        )

    async def async_step_rename_host(self, user_input=None):
        """Enter the new host IP/FQDN and device name."""
        errors = {}

        # Find current device name for the selected device
        current_device_name = self._selected_device
        for target in self._targets:
            if target[CONF_HOST] == self._selected_device:
                current_device_name = target.get("device_name", self._selected_device)
                break

        if user_input is not None:
            new_host = user_input[CONF_HOST].strip()
            new_device_name = user_input.get("device_name", "").strip() or new_host

            if not new_host:
                errors[CONF_HOST] = "invalid_host"
            else:
                old_host = self._selected_device
                device_registry = async_get_device_registry(self.hass)

                # Locate device entries via hw_version, which is always set to
                # target[CONF_HOST] in DeviceInfo — works regardless of whether
                # the identifier uses a MAC or the host string.
                old_device_ids = set()
                for device_entry in device_registry.devices.values():
                    if (device_entry.hw_version == old_host and
                            any(i[0] == DOMAIN for i in device_entry.identifiers)):
                        old_device_ids.add(device_entry.id)

                # Update all targets that belong to the old host
                for target in self._targets:
                    if target[CONF_HOST] == old_host:
                        target[CONF_HOST] = new_host
                        target["device_name"] = new_device_name

                # Save updated config
                self.config_data[CONF_TARGETS] = self._targets
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=self.config_data
                )

                # Remove old device registry entries. Entity registry cleanup
                # is handled automatically by sensor.py during the reload below.
                for device_id in old_device_ids:
                    device_registry.async_remove_device(device_id)

                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="rename_host",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._selected_device): str,
                vol.Optional("device_name", default=current_device_name): str,
            }),
            errors=errors
        )

    async def async_step_device_select(self, user_input=None):
        """First step of alert modification - device selection (network only)."""
        # Get unique devices (skip ZHA and Matter targets — they don't use notify groups)
        devices = {}
        for target in self._targets:
            if target.get(CONF_PROTOCOL) in (PROTOCOL_ZHA, PROTOCOL_MATTER):
                continue
            device_host = target[CONF_HOST]
            if device_host not in devices:
                device_name = target.get("device_name", device_host)
                devices[device_host] = {
                    "name": device_name,
                    "alert_group": target.get(CONF_ALERT_GROUP, DEFAULT_ALERT_GROUP),
                    "alert_delay": target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
                }

        if user_input is not None:
            self._selected_device = user_input["device"]
            return await self.async_step_alert_config()

        return self.async_show_form(
            step_id="device_select",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In(
                    dict(sorted(
                        {host: f"{info['name']} ({host})" for host, info in devices.items()}.items(),
                        key=lambda x: x[1].lower()
                    ))
                )
            })
        )

    async def async_step_alert_config(self, user_input=None):
        """Second step of alert modification - alert settings configuration."""
        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()

        # Get current settings for selected device
        current_settings = None
        for target in self._targets:
            if target[CONF_HOST] == self._selected_device:
                current_settings = {
                    "alerts_enabled": bool(target.get(CONF_ALERT_GROUP, "")),
                    "alert_group": target.get(CONF_ALERT_GROUP, ""),
                    "alert_delay": target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY),
                    "alert_action_enabled": bool(target.get(CONF_ALERT_ACTION, "")),
                    "alert_action": target.get(CONF_ALERT_ACTION, ""),
                    "alert_action_delay": target.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY),
                }
                break

        if user_input is not None:
            # Update all targets for the selected device
            alerts_enabled = user_input.get(CONF_ALERTS_ENABLED, False)
            alert_group = user_input.get(CONF_ALERT_GROUP, "") if alerts_enabled else ""
            action_enabled = user_input.get(CONF_ALERT_ACTION_ENABLED, False)
            alert_action = user_input.get(CONF_ALERT_ACTION, "") if action_enabled else ""
            for target in self._targets:
                if target[CONF_HOST] == self._selected_device:
                    if alert_group:
                        target[CONF_ALERT_GROUP] = alert_group
                    else:
                        target.pop(CONF_ALERT_GROUP, None)
                    target[CONF_ALERT_DELAY] = user_input[CONF_ALERT_DELAY]
                    if alert_action:
                        target[CONF_ALERT_ACTION] = alert_action
                    else:
                        target.pop(CONF_ALERT_ACTION, None)
                    target[CONF_ALERT_ACTION_DELAY] = user_input[CONF_ALERT_ACTION_DELAY]

            # Update config entry with modified targets
            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        # Create the selection form
        notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
        notify_groups_dict[""] = "No alert group"

        schema = {
            vol.Optional(CONF_ALERTS_ENABLED,
                        default=current_settings["alerts_enabled"] if current_settings else False): bool,
            vol.Optional(CONF_ALERT_GROUP,
                        default=current_settings["alert_group"] if current_settings else ""): vol.In(
                notify_groups_dict
            ),
            vol.Required(CONF_ALERT_DELAY,
                        default=current_settings["alert_delay"] if current_settings else DEFAULT_ALERT_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
            vol.Optional(CONF_ALERT_ACTION_ENABLED,
                        default=current_settings["alert_action_enabled"] if current_settings else False): bool,
            vol.Required(CONF_ALERT_ACTION_DELAY,
                        default=current_settings["alert_action_delay"] if current_settings else DEFAULT_ALERT_ACTION_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=120)
            ),
        }
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION,
                    default=current_settings["alert_action"] if current_settings else "")] = vol.In(actions_dict)

        return self.async_show_form(
            step_id="alert_config",
            data_schema=vol.Schema(schema)
        )

    async def async_step_remove_device(self, user_input=None):
        """Handle removing a complete device."""
        entity_registry = async_get_entity_registry(self.hass)
        device_registry = async_get_device_registry(self.hass)

        if user_input is not None:
            device_host = user_input["device"]

            # Remove all targets for this device
            self._targets = [t for t in self._targets if t[CONF_HOST] != device_host]

            # Locate device entries via hw_version, which is always set to
            # target[CONF_HOST] in DeviceInfo for every network device — this
            # works regardless of whether the identifier uses a MAC or the host.
            device_ids = set()
            for device_entry in device_registry.devices.values():
                if (device_entry.hw_version == device_host and
                        any(i[0] == DOMAIN for i in device_entry.identifiers)):
                    device_ids.add(device_entry.id)

            # Remove devices — HA automatically removes their associated entities
            # from the entity registry; any remaining stale entities are cleaned up
            # during the reload triggered below.
            for device_id in device_ids:
                device_registry.async_remove_device(device_id)

            # Update config entry
            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )

            # Reload the config entry
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        # Get unique network devices (ZHA/Matter devices are removed via their own step)
        devices = {}
        for target in self._targets:
            if target.get(CONF_PROTOCOL) in (PROTOCOL_ZHA, PROTOCOL_MATTER):
                continue
            device_name = target.get("device_name", target[CONF_HOST])
            devices[target[CONF_HOST]] = device_name

        if not devices:
            return await self.async_step_menu()

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In(
                    dict(sorted(
                        {host: f"{name} ({host})" for host, name in devices.items()}.items(),
                        key=lambda x: x[1].lower()
                    ))
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

        # Create list of sensors with readable names (network sensors only)
        sensors = {}
        for target in self._targets:
            if target.get(CONF_PROTOCOL) in (PROTOCOL_ZHA, PROTOCOL_MATTER):
                continue  # ZHA/Matter devices are removed via their own steps
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
                vol.Required("sensor"): vol.In(
                    dict(sorted(sensors.items(), key=lambda x: x[1].lower()))
                )
            })
        )

    async def async_step_modify_alerts(self, user_input=None):
        """Handle alert modifications."""
        notify_groups = await self._async_get_notify_groups()

        if not notify_groups:
            return self.async_show_form(
                step_id="modify_alerts",
                errors={"base": "no_notify_groups"},
                description_placeholders={
                    "setup_link": "/config/integrations"
                }
            )

        # Get unique devices and their current alert settings
        devices = {}
        for target in self._targets:
            device_host = target[CONF_HOST]
            if device_host not in devices:
                device_name = target.get("device_name", device_host)
                devices[device_host] = {
                    "name": device_name,
                    "alert_group": target.get(CONF_ALERT_GROUP, DEFAULT_ALERT_GROUP),
                    "alert_delay": target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
                }

        if user_input is not None:
            device_host = user_input["device"]
            selected_device = devices[device_host]

            # Update all targets for the selected device
            for target in self._targets:
                if target[CONF_HOST] == device_host:
                    target[CONF_ALERT_GROUP] = user_input[CONF_ALERT_GROUP]
                    target[CONF_ALERT_DELAY] = user_input[CONF_ALERT_DELAY]

            # Update config entry with modified targets
            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        # If no device was selected yet, show the device selection form
        selected_device = None
        if user_input and "device" in user_input:
            selected_device = devices[user_input["device"]]

        schema = {
            vol.Required("device"): vol.In(
                dict(sorted(
                    {host: f"{info['name']} ({host})" for host, info in devices.items()}.items(),
                    key=lambda x: x[1].lower()
                ))
            ),
            vol.Optional(CONF_ALERT_GROUP,
                        default=selected_device["alert_group"] if selected_device else DEFAULT_ALERT_GROUP): vol.In(
                {k: f"notify.{v}" for k, v in notify_groups.items()}
            ),
            vol.Required(CONF_ALERT_DELAY,
                        default=selected_device["alert_delay"] if selected_device else DEFAULT_ALERT_DELAY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            )
        }

        return self.async_show_form(
            step_id="modify_alerts",
            data_schema=vol.Schema(schema)
        )

    async def async_step_zha_alert_select(self, user_input=None):
        """Select which ZHA device to configure alerts for."""
        zha_targets = [t for t in self._targets if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA]
        if not zha_targets:
            return await self.async_step_menu()

        if user_input is not None:
            self._zha_selected_ieee = user_input["ieee"]
            return await self.async_step_zha_alert_config()

        devices = {
            t[CONF_ZHA_IEEE]: f"{t.get('device_name', t[CONF_ZHA_IEEE])} ({t[CONF_ZHA_IEEE]})"
            for t in sorted(zha_targets, key=lambda x: x.get("device_name", ""))
        }
        return self.async_show_form(
            step_id="zha_alert_select",
            data_schema=vol.Schema({
                vol.Required("ieee"): vol.In(devices),
            }),
        )

    async def async_step_zha_alert_config(self, user_input=None):
        """Configure alert settings for the selected ZHA device."""
        notify_groups = await self._async_get_notify_groups()
        alert_actions = await self._async_get_alert_actions()

        current_target = next(
            (t for t in self._targets
             if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA and t.get(CONF_ZHA_IEEE) == self._zha_selected_ieee),
            {}
        )
        current_alert_group = current_target.get(CONF_ALERT_GROUP, "")
        current_alert_delay = current_target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
        current_alerts_enabled = bool(current_alert_group)
        current_alert_action = current_target.get(CONF_ALERT_ACTION, "")
        current_action_delay = current_target.get(CONF_ALERT_ACTION_DELAY, DEFAULT_ALERT_ACTION_DELAY)
        current_action_enabled = bool(current_alert_action)

        if user_input is not None:
            alerts_enabled = user_input.get(CONF_ALERTS_ENABLED, False)
            alert_group = user_input.get(CONF_ALERT_GROUP, "") if alerts_enabled else ""
            action_enabled = user_input.get(CONF_ALERT_ACTION_ENABLED, False)
            alert_action = user_input.get(CONF_ALERT_ACTION, "") if action_enabled else ""
            for t in self._targets:
                if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA and t.get(CONF_ZHA_IEEE) == self._zha_selected_ieee:
                    if alert_group:
                        t[CONF_ALERT_GROUP] = alert_group
                    else:
                        t.pop(CONF_ALERT_GROUP, None)
                    t[CONF_ALERT_DELAY] = user_input[CONF_ALERT_DELAY]
                    if alert_action:
                        t[CONF_ALERT_ACTION] = alert_action
                    else:
                        t.pop(CONF_ALERT_ACTION, None)
                    t[CONF_ALERT_ACTION_DELAY] = user_input[CONF_ALERT_ACTION_DELAY]

            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        notify_groups_dict = {k: f"notify.{v}" for k, v in notify_groups.items()}
        notify_groups_dict[""] = "No alert group"
        schema = {
            vol.Optional(CONF_ALERTS_ENABLED, default=current_alerts_enabled): bool,
            vol.Optional(CONF_ALERT_GROUP, default=current_alert_group): vol.In(notify_groups_dict),
            vol.Required(CONF_ALERT_DELAY, default=current_alert_delay): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
            vol.Optional(CONF_ALERT_ACTION_ENABLED, default=current_action_enabled): bool,
            vol.Required(CONF_ALERT_ACTION_DELAY, default=current_action_delay): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=120)
            ),
        }
        if alert_actions:
            actions_dict = {"" : "No action"}
            actions_dict.update(alert_actions)
            schema[vol.Optional(CONF_ALERT_ACTION, default=current_alert_action)] = vol.In(actions_dict)
        return self.async_show_form(
            step_id="zha_alert_config",
            data_schema=vol.Schema(schema),
        )

    async def async_step_remove_zha_device(self, user_input=None):
        """Remove a monitored ZHA device."""
        entity_registry = async_get_entity_registry(self.hass)

        zha_targets = [t for t in self._targets if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA]
        if not zha_targets:
            return await self.async_step_menu()

        if user_input is not None:
            ieee = user_input["ieee"]

            # Remove from targets list
            self._targets = [
                t for t in self._targets
                if not (t.get(CONF_PROTOCOL) == PROTOCOL_ZHA and t.get(CONF_ZHA_IEEE) == ieee)
            ]

            # Only remove our monitoring entity — the ZHA device itself is
            # owned by the ZHA integration and must NOT be removed.
            ieee_clean = ieee.replace(":", "").replace("-", "")
            unique_id = f"connectivity_zha_{ieee_clean}"
            entry_entities = async_entries_for_config_entry(
                entity_registry, self.config_entry.entry_id
            )
            for entity_entry in entry_entities:
                if entity_entry.unique_id == unique_id:
                    entity_registry.async_remove(entity_entry.entity_id)
                    break

            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        devices = {
            t[CONF_ZHA_IEEE]: f"{t.get('device_name', t[CONF_ZHA_IEEE])} ({t[CONF_ZHA_IEEE]})"
            for t in sorted(zha_targets, key=lambda x: x.get("device_name", ""))
        }
        return self.async_show_form(
            step_id="remove_zha_device",
            data_schema=vol.Schema({
                vol.Required("ieee"): vol.In(devices),
            }),
        )

    async def async_step_zha_select_for_timeout(self, user_input=None):
        """Select which ZHA device to change the inactivity timeout for."""
        zha_targets = [t for t in self._targets if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA]
        if not zha_targets:
            return await self.async_step_menu()

        if user_input is not None:
            self._zha_selected_ieee = user_input["ieee"]
            return await self.async_step_zha_update_timeout()

        devices = {
            t[CONF_ZHA_IEEE]: f"{t.get('device_name', t[CONF_ZHA_IEEE])} ({t[CONF_ZHA_IEEE]})"
            for t in sorted(zha_targets, key=lambda x: x.get("device_name", ""))
        }
        return self.async_show_form(
            step_id="zha_select_for_timeout",
            data_schema=vol.Schema({
                vol.Required("ieee"): vol.In(devices),
            }),
        )

    async def async_step_zha_update_timeout(self, user_input=None):
        """Update the inactivity timeout for the selected ZHA device."""
        current_timeout = DEFAULT_INACTIVE_TIMEOUT
        for t in self._targets:
            if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA and t.get(CONF_ZHA_IEEE) == self._zha_selected_ieee:
                current_timeout = t.get(CONF_INACTIVE_TIMEOUT, DEFAULT_INACTIVE_TIMEOUT)
                break

        if user_input is not None:
            for t in self._targets:
                if t.get(CONF_PROTOCOL) == PROTOCOL_ZHA and t.get(CONF_ZHA_IEEE) == self._zha_selected_ieee:
                    t[CONF_INACTIVE_TIMEOUT] = user_input[CONF_INACTIVE_TIMEOUT]

            self.config_data[CONF_TARGETS] = self._targets
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="zha_update_timeout",
            data_schema=vol.Schema({
                vol.Required(CONF_INACTIVE_TIMEOUT, default=current_timeout): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=1440)
                ),
            }),
        )

    async def async_step_settings(self, user_input=None):
        """Handle changing general settings."""
        if user_input is not None:
            self.config_data[CONF_INTERVAL] = user_input[CONF_INTERVAL]
            self.config_data[CONF_DNS_SERVER] = user_input[CONF_DNS_SERVER]

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self.config_data
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = {
            vol.Required(CONF_INTERVAL,
                        default=self.config_data[CONF_INTERVAL]): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=300)
            ),
            vol.Required(CONF_DNS_SERVER,
                        default=self.config_data[CONF_DNS_SERVER]): str,
        }

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(schema)
        )

    async def async_step_cleanup_orphans(self, user_input=None):
        """Remove devices registered under this integration that have no entities."""
        from homeassistant.helpers.entity_registry import (
            async_entries_for_device,
            async_get as async_get_er,
        )

        entity_registry = async_get_er(self.hass)
        device_registry = async_get_device_registry(self.hass)
        entry_id = self.config_entry.entry_id

        removed = []
        for device_entry in list(device_registry.devices.values()):
            # Only consider devices that list our config entry
            if entry_id not in device_entry.config_entries:
                continue
            # Check whether any entity still belongs to our config entry
            entry_entities = [
                e for e in async_entries_for_device(entity_registry, device_entry.id)
                if e.config_entry_id == entry_id
            ]
            if not entry_entities:
                removed.append(device_entry.name or device_entry.id)
                if device_entry.config_entries == {entry_id}:
                    # Exclusively ours — delete the device entirely
                    device_registry.async_remove_device(device_entry.id)
                else:
                    # Shared with another integration — only remove our association
                    device_registry.async_update_device(
                        device_entry.id, remove_config_entry_id=entry_id
                    )

        if removed:
            _LOGGER.info("Connectivity Monitor: cleaned up orphaned devices: %s", removed)

        return self.async_abort(
            reason="cleanup_done"
        )
