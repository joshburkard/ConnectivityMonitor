from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
import socket
from typing import Any

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

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PROTOCOL,
    CONF_PORT,
    CONF_INTERVAL,
    CONF_TARGETS,
    CONF_DNS_SERVER,
    PROTOCOL_ICMP,
    PROTOCOL_AD_DC,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_DNS_SERVER,
    DEFAULT_INTERVAL,
    AD_DC_PORTS
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    update_interval = entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
    dns_server = entry.data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)

    coordinators = {}
    entities = []
    targets = entry.data[CONF_TARGETS]
    current_hosts = {target[CONF_HOST] for target in targets}

    # Create sensors for each target
    for target in targets:
        host = target[CONF_HOST]
        coordinator = ConnectivityCoordinator(hass, target, update_interval, dns_server)
        await coordinator.async_config_entry_first_refresh()

        if host not in coordinators:
            coordinators[host] = []
        coordinators[host].append(coordinator)
        entities.append(ConnectivitySensor(coordinator, target))

    # Create overview sensors
    for host, host_coordinators in coordinators.items():
        base_target = next(target for target in targets if target[CONF_HOST] == host)
        overview_coordinator = ConnectivityCoordinator(hass, base_target, update_interval, dns_server)
        await overview_coordinator.async_config_entry_first_refresh()
        entities.append(OverviewSensor(overview_coordinator, base_target, host_coordinators))

    # Clean up unused entities
    current_unique_ids = set()
    for target in targets:
        current_unique_ids.add(f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}")
        current_unique_ids.add(f"{target[CONF_HOST]}_overview")

    entity_entries = async_entries_for_config_entry(entity_registry, entry.entry_id)
    for entity_entry in entity_entries:
        if entity_entry.unique_id not in current_unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)

    async_add_entities(entities)

class ConnectivityCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, target: dict, update_interval: int, dns_server: str) -> None:
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
                return hostname
            except (socket.error, ValueError):
                pass

            try:
                socket.inet_pton(socket.AF_INET6, hostname)
                return hostname
            except (socket.error, ValueError):
                pass

            # DNS resolution using configured DNS server
            import dns.resolver
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [self._dns_server]
            resolver.timeout = 2
            resolver.lifetime = 4

            def _do_resolve():
                answers = resolver.resolve(hostname, "A")
                if answers:
                    return str(answers[0])
                return None

            result = await self.hass.async_add_executor_job(_do_resolve)
            if result:
                return result

            _LOGGER.warning("Could not resolve %s using DNS server %s", hostname, self._dns_server)
            return hostname

        except Exception as err:
            _LOGGER.error("Error resolving hostname %s: %s", hostname, err)
            return hostname

    async def _async_update_data(self) -> dict[str, Any]:
        protocol = self.target[CONF_PROTOCOL]
        host = self.target[CONF_HOST]
        result = {"connected": False, "latency": None, "resolved_ip": None}

        try:
            if not self._resolved_ip:
                self._resolved_ip = await self._resolve_host(host)
                if not self._resolved_ip:
                    _LOGGER.error("Could not resolve hostname %s", host)
                    return result

            resolved_host = self._resolved_ip
            result["resolved_ip"] = resolved_host

            if protocol == PROTOCOL_TCP:
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
    def __init__(self, coordinator: ConnectivityCoordinator, target: dict) -> None:
        super().__init__(coordinator)
        self.target = target

        device_name = target.get("device_name", target[CONF_HOST])
        formatted_host = target[CONF_HOST].replace('.', '_')

        if target[CONF_PROTOCOL] == PROTOCOL_ICMP:
            self._attr_name = "ICMP (Ping)"
            entity_id_suffix = f"{formatted_host}_icmp"
        elif target[CONF_PROTOCOL] == PROTOCOL_AD_DC:
            self._attr_name = "Active Directory DC"
            entity_id_suffix = f"{formatted_host}_ad_dc"
        else:
            self._attr_name = f"{target[CONF_PROTOCOL]} {target[CONF_PORT]}"
            entity_id_suffix = f"{formatted_host}_{target[CONF_PROTOCOL].lower()}_{target[CONF_PORT]}"

        self.entity_id = f"sensor.connectivity_monitor_{entity_id_suffix}"

        self._attr_unique_id = f"{target[CONF_HOST]}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}"

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
        if not self.coordinator._available:
            return "Not Connected"
        return "Connected" if self.coordinator.data["connected"] else "Disconnected"

    @property
    def icon(self):
        if not self.coordinator._available or not self.coordinator.data["connected"]:
            return "mdi:lan-disconnect"
        return "mdi:lan-connect"

    @property
    def extra_state_attributes(self):
        attrs = {
            "host": self.target[CONF_HOST],
            "protocol": self.target[CONF_PROTOCOL],
            "dns_server": self.coordinator._dns_server,
        }

        if self.target[CONF_PROTOCOL] not in [PROTOCOL_ICMP, PROTOCOL_AD_DC]:
            attrs["port"] = self.target[CONF_PORT]

        if self.coordinator.data.get("latency") is not None:
            attrs["latency_ms"] = self.coordinator.data["latency"]

        if self.coordinator.data.get("resolved_ip") is not None:
            attrs["resolved_ip"] = self.coordinator.data["resolved_ip"]

        return attrs

class OverviewSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator: ConnectivityCoordinator, target: dict, all_coordinators: list) -> None:
        super().__init__(coordinator)
        self.target = target
        self._coordinators = all_coordinators

        device_name = target.get("device_name", target[CONF_HOST])
        formatted_host = target[CONF_HOST].replace('.', '_')

        self._attr_name = "Overall"
        self.entity_id = f"sensor.connectivity_monitor_{formatted_host}_overall"
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
        if not self._coordinators:
            return "Unknown"

        return "Connected" if all(
            coord.data and coord.data.get("connected", False)
            for coord in self._coordinators
        ) else "Disconnected"

    @property
    def icon(self):
        if self.native_value == "Connected":
            return "mdi:check-network"
        return "mdi:close-network"

    @property
    def extra_state_attributes(self):
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