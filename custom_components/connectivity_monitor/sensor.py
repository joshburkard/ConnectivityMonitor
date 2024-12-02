"""Support for Connectivity Monitor sensors."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import socket
from typing import Any

try:
    import dns.resolver
    import dns.exception
    HAVE_DNS = True
except ImportError:
    HAVE_DNS = False

from ping3 import ping
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get as async_get_entity_registry,
)
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PROTOCOL,
    CONF_PORT,
    CONF_INTERVAL,
    CONF_TARGETS,
    CONF_DNS_SERVER,
    PROTOCOL_ICMP,
    PROTOCOL_RPC,
    PROTOCOL_AD_DC,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    AD_DC_PORTS,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_DNS_SERVER
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Connectivity Monitor sensors."""
    if not HAVE_DNS:
        _LOGGER.error("DNS Python package not found. Please install it.")
        raise ConfigEntryNotReady

    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    targets = entry.data[CONF_TARGETS]
    update_interval = entry.data[CONF_INTERVAL]
    dns_server = entry.data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)

    # Get list of devices first
    device_entries = list(device_registry.devices.values())
    current_hosts = {target[CONF_HOST] for target in targets}

    # Clean up firmware and hardware versions from existing devices
    for device_entry in device_entries:
        for identifier in device_entry.identifiers:
            if identifier[0] == DOMAIN:
                device_registry.async_update_device(
                    device_entry.id,
                    hw_version=None,
                    sw_version=None
                )
                if identifier[1] not in current_hosts:
                    device_registry.async_remove_device(device_entry.id)

    # Create sensors
    coordinators = []
    entities = []

    # Create regular sensors
    for target in targets:
        coordinator = ConnectivityCoordinator(hass, target, update_interval, dns_server)
        await coordinator.async_config_entry_first_refresh()
        coordinators.append(coordinator)
        entities.append(ConnectivitySensor(coordinator, target))

    # Create overview sensors (one per device)
    seen_hosts = set()
    for target in targets:
        host = target[CONF_HOST]
        if host not in seen_hosts:
            seen_hosts.add(host)
            overview_coordinator = ConnectivityCoordinator(hass, target, update_interval, dns_server)
            await overview_coordinator.async_config_entry_first_refresh()
            entities.append(OverAllSensor(overview_coordinator, target, coordinators))

    # Clean up unused entities
    current_unique_ids = {
        f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}"
        for target in targets
    }

    entity_entries = async_entries_for_config_entry(entity_registry, entry.entry_id)
    for entity_entry in entity_entries:
        if entity_entry.unique_id not in current_unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)

    async_add_entities(entities)

class ConnectivityCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Connectivity Monitor data."""

    def __init__(self, hass: HomeAssistant, target: dict, update_interval: int, dns_server: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.target = target
        self._available = False
        self._last_state = False
        self._resolved_ip = None
        self._dns_server = dns_server

    async def _resolve_host(self, hostname: str) -> str | None:
        """Resolve hostname to IP address."""
        try:
            # Check if it's already an IP address
            try:
                socket.inet_pton(socket.AF_INET, hostname)
                return hostname  # It's already an IP address
            except (socket.error, ValueError):
                pass

            try:
                socket.inet_pton(socket.AF_INET6, hostname)
                return hostname  # It's already an IPv6 address
            except (socket.error, ValueError):
                pass

            def _resolve():
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [self._dns_server]
                resolver.timeout = 2
                resolver.lifetime = 4
                try:
                    answers = resolver.resolve(hostname, "A")
                    if answers:
                        return str(answers[0])
                except dns.exception.DNSException as err:
                    _LOGGER.error("DNS resolution failed for %s: %s", hostname, err)
                return None

            return await self.hass.async_add_executor_job(_resolve)

        except Exception as err:
            _LOGGER.error("Error resolving hostname %s: %s", hostname, err)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the target."""
        protocol = self.target[CONF_PROTOCOL]
        host = self.target[CONF_HOST]
        result = {"connected": False, "latency": None, "resolved_ip": None}

        try:
            # Resolve hostname if needed
            if not self._resolved_ip:
                self._resolved_ip = await self._resolve_host(host)
                if not self._resolved_ip:
                    _LOGGER.error("Could not resolve hostname %s", host)
                    return result

            resolved_host = self._resolved_ip
            result["resolved_ip"] = resolved_host

            if protocol == PROTOCOL_AD_DC:
                # Test all AD DC ports
                port_results = {}
                all_connected = True
                total_latency = 0
                ports_checked = 0

                for port, service in AD_DC_PORTS.items():
                    try:
                        start_time = self.hass.loop.time()
                        reader, writer = await asyncio.wait_for(
                            asyncio.open_connection(resolved_host, port),
                            timeout=5
                        )
                        latency = (self.hass.loop.time() - start_time) * 1000
                        writer.close()
                        await writer.wait_closed()
                        port_results[service] = {
                            "port": port,
                            "connected": True,
                            "latency": round(latency, 2)
                        }
                        total_latency += latency
                        ports_checked += 1
                    except Exception as err:
                        _LOGGER.debug(
                            "AD DC port check failed for %s:%s (%s): %s",
                            host, port, service, err
                        )
                        port_results[service] = {
                            "port": port,
                            "connected": False,
                            "latency": None
                        }
                        all_connected = False

                result.update({
                    "connected": all_connected,
                    "latency": round(total_latency / max(ports_checked, 1), 2) if ports_checked > 0 else None,
                    "port_results": port_results
                })

            elif protocol == PROTOCOL_TCP:
                start_time = self.hass.loop.time()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(resolved_host, self.target[CONF_PORT]),
                    timeout=5
                )
                latency = (self.hass.loop.time() - start_time) * 1000
                writer.close()
                await writer.wait_closed()
                result.update({
                    "connected": True,
                    "latency": round(latency, 2)
                })

            elif protocol == PROTOCOL_UDP:
                start_time = self.hass.loop.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                await self.hass.async_add_executor_job(
                    sock.connect,
                    (resolved_host, self.target[CONF_PORT])
                )
                latency = (self.hass.loop.time() - start_time) * 1000
                sock.close()
                result.update({
                    "connected": True,
                    "latency": round(latency, 2)
                })

            elif protocol == PROTOCOL_ICMP:
                response_time = await self.hass.async_add_executor_job(
                    ping, resolved_host, DEFAULT_PING_TIMEOUT, 1
                )
                if response_time is not None:
                    result.update({
                        "connected": True,
                        "latency": round(response_time * 1000, 2)
                    })

        except Exception as err:
            _LOGGER.debug(
                "Connection failed to %s:%s (%s): %s",
                host,
                self.target.get(CONF_PORT, "N/A"),
                protocol,
                err
            )

        self._available = True
        return result

class ConnectivitySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Connectivity Monitor sensor."""

    def __init__(self, coordinator: ConnectivityCoordinator, target: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.target = target

        # Get and sanitize device name for entity_id
        device_name = target.get("device_name", target[CONF_HOST])
        entity_id_name = (device_name.lower()
                         .replace(' ', '_')
                         .replace('-', '_')
                         .replace('.', '_')
                         .replace('(', '')
                         .replace(')', '')
                         .replace('[', '')
                         .replace(']', '')
                         .replace('/', '_')
                         .replace('\\', '_')
                         .replace('@', '_at_')
                         .replace('&', '_and_'))

        # Create name based on protocol
        if target[CONF_PROTOCOL] == PROTOCOL_ICMP:
            self._attr_name = f"{device_name} ICMP (Ping)"
            entity_id_suffix = f"{entity_id_name}_icmp"
        elif target[CONF_PROTOCOL] == PROTOCOL_AD_DC:
            self._attr_name = f"{device_name} Active Directory DC"
            entity_id_suffix = f"{entity_id_name}_ad_dc"
        else:
            self._attr_name = f"{device_name} {target[CONF_PROTOCOL]} {target[CONF_PORT]}"
            entity_id_suffix = f"{entity_id_name}_{target[CONF_PROTOCOL].lower()}_{target[CONF_PORT]}"

        # Set entity_id format
        self.entity_id = f"sensor.connectivity_monitor_{entity_id_suffix}"

        # The unique_id stays the same (using host) to maintain entity identity
        self._attr_unique_id = (
            f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_"
            f"{target.get(CONF_PORT, 'ping')}"
        )

        # Device info with custom name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, target[CONF_HOST])},
            name=device_name,
            manufacturer="Connectivity Monitor",
            model="Network Monitor",
            configuration_url=f"http://{target[CONF_HOST]}",
            suggested_area="Network"
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator._available:
            return "Not Connected"
        return "Connected" if self.coordinator.data["connected"] else "Disconnected"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        if not self.coordinator._available or not self.coordinator.data["connected"]:
            return "mdi:lan-disconnect"
        return "mdi:lan-connect"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            "host": self.target[CONF_HOST],
            "protocol": self.target[CONF_PROTOCOL],
            "dns_server": self.coordinator._dns_server
        }

        # Add port if not ICMP or AD DC
        if self.target[CONF_PROTOCOL] not in [PROTOCOL_ICMP, PROTOCOL_AD_DC]:
            attrs["port"] = self.target[CONF_PORT]

        # Add latency if available
        if self.coordinator.data.get("latency") is not None:
            attrs["latency_ms"] = self.coordinator.data["latency"]

        # Add resolved IP if available
        if self.coordinator.data.get("resolved_ip") is not None:
            attrs["resolved_ip"] = self.coordinator.data["resolved_ip"]

        # Add AD DC port results if available
        if (self.target[CONF_PROTOCOL] == PROTOCOL_AD_DC and
            self.coordinator.data.get("port_results")):
            port_results = self.coordinator.data["port_results"]
            for service, result in port_results.items():
                attrs[f"{service}_port"] = result["port"]
                attrs[f"{service}_connected"] = result["connected"]
                if result["latency"] is not None:
                    attrs[f"{service}_latency_ms"] = result["latency"]

        return attrs

class OverAllSensor(CoordinatorEntity, SensorEntity):
    """Overview sensor representing all sensors for a device."""

    def __init__(self, coordinator: ConnectivityCoordinator, target: dict, all_coordinators: list) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.target = target
        self._coordinators = [coord for coord in all_coordinators
                            if coord.target[CONF_HOST] == target[CONF_HOST]]

        device_name = target.get("device_name", target[CONF_HOST])
        entity_id_name = (device_name.lower()
                         .replace(' ', '_')
                         .replace('-', '_')
                         .replace('.', '_')
                         .replace('(', '')
                         .replace(')', '')
                         .replace('[', '')
                         .replace(']', '')
                         .replace('/', '_')
                         .replace('\\', '_')
                         .replace('@', '_at_')
                         .replace('&', '_and_'))

        self._attr_name = f"{device_name} Overall"
        self.entity_id = f"sensor.connectivity_monitor_{entity_id_name}_overall"
        self._attr_unique_id = f"{target[CONF_HOST]}_overall"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, target[CONF_HOST])},
            name=device_name,
            manufacturer="Connectivity Monitor",
            model="Network Monitor",
            configuration_url=f"http://{target[CONF_HOST]}",
            suggested_area="Network"
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        """Return overall connection status."""
        if not self._coordinators:
            return "Unknown"

        return "Connected" if all(
            coord.data and coord.data.get("connected", False)
            for coord in self._coordinators
        ) else "Disconnected"

    @property
    def icon(self):
        """Return the icon."""
        if self.native_value == "Connected":
            return "mdi:lan-check"
        return "mdi:lan-disconnect"

    @property
    def extra_state_attributes(self):
        """Return overview attributes."""
        attrs = {
            "host": self.target[CONF_HOST],
            "device_name": self.target.get("device_name", self.target[CONF_HOST]),
            "monitored_services": []
        }

        for coord in self._coordinators:
            service = {
                "protocol": coord.target[CONF_PROTOCOL],
                "status": "Connected" if coord.data and coord.data.get("connected") else "Disconnected"
            }

            if coord.target[CONF_PROTOCOL] not in [PROTOCOL_ICMP, PROTOCOL_AD_DC]:
                service["port"] = coord.target[CONF_PORT]

            if coord.data and coord.data.get("latency") is not None:
                service["latency_ms"] = coord.data["latency"]

            attrs["monitored_services"].append(service)

        return attrs
