from __future__ import annotations
import asyncio
import re
from datetime import timedelta
import logging
import socket
from typing import Any
from datetime import datetime
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import STATE_UNKNOWN

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

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PROTOCOL,
    CONF_PORT,
    CONF_INTERVAL,
    CONF_TARGETS,
    CONF_DNS_SERVER,
    CONF_ALERT_GROUP,    # Added
    CONF_ALERT_DELAY,    # Added
    DEFAULT_ALERT_DELAY, # Added
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
    """Set up the Connectivity Monitor sensors."""
    _LOGGER.debug("Starting setup of Connectivity Monitor entry with data: %s", entry.data)

    config_data = dict(entry.data)
    targets = config_data[CONF_TARGETS]
    update_interval = config_data[CONF_INTERVAL]
    dns_server = config_data[CONF_DNS_SERVER]

    _LOGGER.debug("Processing configuration - Update interval: %s, DNS Server: %s",
                 update_interval, dns_server)
    _LOGGER.debug("Targets to process: %s", targets)

    # Create alert handler
    alert_handler = AlertHandler(hass)

    # Get existing entities
    entity_registry = async_get_entity_registry(hass)
    existing_entities = async_entries_for_config_entry(entity_registry, entry.entry_id)
    new_unique_ids = set()
    entities = []

    # Group targets by host
    host_targets = {}
    for target in targets:
        host = target[CONF_HOST]
        if host not in host_targets:
            host_targets[host] = []
        host_targets[host].append(target)

    _LOGGER.debug("Grouped targets by host: %s",
                 {host: [t.get(CONF_PROTOCOL) for t in targets] for host, targets in host_targets.items()})

    # Process each host
    for host, host_target_list in host_targets.items():
        _LOGGER.debug("Processing host %s with targets: %s",
                     host, [f"{t[CONF_PROTOCOL]}:{t.get(CONF_PORT, 'N/A')}" for t in host_target_list])

        device_coordinators = []
        ad_coordinators = []

        # Create sensors for each target
        for target in host_target_list:
            try:
                _LOGGER.debug("Creating individual sensor for target: Protocol=%s, Port=%s",
                            target[CONF_PROTOCOL], target.get(CONF_PORT, 'N/A'))

                coordinator = ConnectivityCoordinator(hass, target, update_interval, dns_server)
                await coordinator.async_config_entry_first_refresh()
                device_coordinators.append(coordinator)

                if target[CONF_PROTOCOL] == PROTOCOL_TCP and target.get(CONF_PORT) in AD_DC_PORTS:
                    _LOGGER.debug("Adding coordinator to AD coordinators for port %s", target.get(CONF_PORT))
                    ad_coordinators.append(coordinator)

                sensor = ConnectivitySensor(coordinator, target)
                entities.append(sensor)
                new_unique_ids.add(sensor.unique_id)
                _LOGGER.debug("Created individual sensor: entity_id=%s, unique_id=%s",
                            sensor.entity_id, sensor.unique_id)

            except Exception as err:
                _LOGGER.exception("Error creating individual sensor for target %s: %s", target, err)

        # Create overview sensors
        if device_coordinators:
            try:
                first_target = host_target_list[0]
                device_name = first_target.get("device_name", first_target[CONF_HOST])
                safe_device_name = device_name.lower().replace(' ', '_').replace('-', '_').replace('.', '_')

                _LOGGER.debug("Creating overview sensor for device: %s", device_name)
                overview_coordinator = ConnectivityCoordinator(hass, first_target, update_interval, dns_server)
                await overview_coordinator.async_config_entry_first_refresh()

                overview = OverviewSensor(overview_coordinator, first_target, device_coordinators)
                entities.append(overview)
                new_unique_ids.add(overview.unique_id)
                _LOGGER.debug("Created overview sensor: entity_id=%s, unique_id=%s",
                            overview.entity_id, overview.unique_id)

                # Set up alerts if configured
                if first_target.get(CONF_ALERT_GROUP):
                    entity_id = f"sensor.connectivity_monitor_{safe_device_name}_overall"
                    await alert_handler.async_setup_alerts(entity_id, overview_coordinator)

                # Create AD overview if needed
                if ad_coordinators:
                    _LOGGER.debug("Creating AD overview sensor with %d AD coordinators",
                                len(ad_coordinators))
                    ad_overview = ADOverviewSensor(overview_coordinator, first_target, ad_coordinators)
                    entities.append(ad_overview)
                    new_unique_ids.add(ad_overview.unique_id)
                    _LOGGER.debug("Created AD overview sensor: entity_id=%s, unique_id=%s",
                                ad_overview.entity_id, ad_overview.unique_id)

                    if first_target.get(CONF_ALERT_GROUP):
                        entity_id = f"sensor.connectivity_monitor_{safe_device_name}_ad"
                        await alert_handler.async_setup_alerts(entity_id, overview_coordinator)

            except Exception as err:
                _LOGGER.exception("Error creating overview sensors for host %s: %s", host, err)

        _LOGGER.debug("Completed processing for host %s. Created %d sensors", host, len(entities))

    # Remove old entities
    for entity in existing_entities:
        if entity.unique_id not in new_unique_ids:
            _LOGGER.debug("Removing old entity: %s (unique_id: %s)", entity.entity_id, entity.unique_id)
            entity_registry.async_remove(entity.entity_id)

    _LOGGER.debug("Final entities to be added: %s",
                 [{"entity_id": e.entity_id, "unique_id": e.unique_id} for e in entities])

    if entities:
        _LOGGER.debug("Adding %d entities to Home Assistant", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.error("No entities were created during setup!")

class AlertHandler:
    """Handle alert notifications for connectivity status."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the alert handler."""
        self.hass = hass
        self._last_disconnected = {}
        self._notified = {}
        self._callbacks = {}
        self._targets = {}  # Store target info for each entity
        self._check_timer = None
        self._setup_alert_timer()
        _LOGGER.debug("AlertHandler initialized")

    def _setup_alert_timer(self) -> None:
        """Set up periodic timer to check alerts."""
        async def async_check(_now=None):
            """Wrapper for async check."""
            await self._check_alerts()

        self._check_timer = async_track_time_interval(
            self.hass,
            async_check,
            timedelta(minutes=1)
        )

    async def _check_alerts(self) -> None:
        """Check all monitored entities for alerts."""
        current_time = datetime.now()

        for entity_id, disconnect_time in list(self._last_disconnected.items()):
            # Skip if already notified
            if self._notified.get(entity_id, False):
                continue

            if entity_id not in self._targets:
                continue

            target = self._targets[entity_id]
            alert_delay = target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
            alert_group = target.get(CONF_ALERT_GROUP)
            device_name = target.get("device_name", target[CONF_HOST])

            elapsed_minutes = (current_time - disconnect_time).total_seconds() / 60

            _LOGGER.debug(
                "Timer check for %s: %.1f minutes elapsed of %d minute delay",
                device_name,
                elapsed_minutes,
                alert_delay
            )

            if elapsed_minutes >= alert_delay:
                state = self.hass.states.get(entity_id)
                if state and state.state in ["Disconnected", "Not Connected", "Partially Connected"]:
                    message = (
                        f"❌ Device {device_name} ({target[CONF_HOST]}) has been "
                        f"{state.state.lower()} for {int(elapsed_minutes)} minutes"
                    )
                    await self._async_send_notification(alert_group, message)
                    self._notified[entity_id] = True
                    _LOGGER.debug("Alert sent for %s after %.1f minutes", device_name, elapsed_minutes)

    async def _async_send_notification(self, service: str, message: str) -> None:
        """Send a notification."""
        try:
            # Add 'notify.' prefix if missing
            if not service.startswith("notify."):
                service = f"notify.{service}"

            _LOGGER.debug("Sending notification using service: %s", service)
            _LOGGER.debug("Notification message: %s", message)

            await self.hass.services.async_call(
                "notify",
                service.replace("notify.", ""),
                {"message": message},
                blocking=True,
            )
            _LOGGER.debug("Successfully sent notification")
        except Exception as err:
            _LOGGER.error("Failed to send notification using service %s: %s", service, str(err))

    async def async_setup_alerts(self, entity_id: str, coordinator: ConnectivityCoordinator) -> None:
        """Set up alerts for a sensor."""
        target = coordinator.target
        alert_group = target.get(CONF_ALERT_GROUP)

        if not alert_group:
            return

        _LOGGER.debug(
            "Setting up alerts for %s with group %s and delay %d minutes",
            entity_id,
            alert_group,
            target.get(CONF_ALERT_DELAY, DEFAULT_ALERT_DELAY)
        )

        # Store target info for timer checks
        self._targets[entity_id] = target

        # Remove existing callback if any
        if entity_id in self._callbacks:
            self._callbacks[entity_id]()
            self._callbacks.pop(entity_id)

        async def async_handle_state_change(event) -> None:
            """Handle state changes for an entity."""
            # Handle both real events and our simulated initial state check
            if hasattr(event, 'data'):
                new_state = event.data.get("new_state")
                old_state = event.data.get("old_state")
            else:
                new_state = event.get("new_state")
                old_state = event.get("old_state")

            if new_state is None:
                return

            current_time = datetime.now()
            problem_states = ["Disconnected", "Not Connected", "Partially Connected"]
            device_name = target.get("device_name", target[CONF_HOST])

            # Log state changes
            _LOGGER.debug(
                "State change for %s: %s -> %s",
                device_name,
                old_state.state if old_state else "None",
                new_state.state
            )

            # Device has entered a problem state
            if new_state.state in problem_states:
                # Only start timing if we weren't already in a problem state
                if entity_id not in self._last_disconnected or (
                    old_state and old_state.state not in problem_states
                ):
                    self._last_disconnected[entity_id] = current_time
                    self._notified[entity_id] = False
                    _LOGGER.debug(
                        "Started monitoring %s in %s state at %s",
                        device_name,
                        new_state.state,
                        current_time.strftime("%H:%M:%S")
                    )

            # Device has recovered
            elif new_state.state == "Connected":
                if entity_id in self._last_disconnected:
                    # Send recovery notification if we previously notified
                    if self._notified.get(entity_id):
                        message = f"✅ Device {device_name} ({target[CONF_HOST]}) has recovered and is now connected"
                        await self._async_send_notification(alert_group, message)
                        _LOGGER.debug("Recovery notification sent for %s", device_name)

                    # Clear tracking
                    self._last_disconnected.pop(entity_id, None)
                    self._notified[entity_id] = False
                    _LOGGER.debug("Cleared monitoring for %s after recovery", device_name)

        @callback
        def state_change_callback(event):
            """Callback wrapper for state change handler."""
            self.hass.async_create_task(async_handle_state_change(event))

        # Set up state tracking
        self._callbacks[entity_id] = async_track_state_change_event(
            self.hass, [entity_id], state_change_callback
        )

        # Check initial state
        state = self.hass.states.get(entity_id)
        if state and state.state != STATE_UNKNOWN:
            await async_handle_state_change({"new_state": state, "old_state": None})

class ConnectivityCoordinator(DataUpdateCoordinator):
    """Class to manage fetching connectivity data."""

    def __init__(self, hass: HomeAssistant, target: dict, update_interval: int, dns_server: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.target = target
        self._dns_server = dns_server
        self._resolver = None
        self._resolved_ip = None
        self._mac_address = None
        _LOGGER.debug(
            "Initialized coordinator for target %s with interval %s",
            target.get(CONF_HOST),
            update_interval
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the target."""
        protocol = self.target[CONF_PROTOCOL]
        host = self.target[CONF_HOST]

        _LOGGER.debug("Starting update for %s with protocol %s", host, protocol)

        result = {
            "connected": False,
            "latency": None,
            "resolved_ip": None,
            "mac_address": None
        }

        try:
            # Resolve hostname if needed
            if not self._resolved_ip:
                self._resolved_ip = await self._resolve_host(host)
                if not self._resolved_ip:
                    _LOGGER.error("Could not resolve hostname %s", host)
                    return result

            result["resolved_ip"] = self._resolved_ip

            # Get MAC address if needed
            if not self._mac_address:
                self._mac_address = await self._get_mac_address(self._resolved_ip)
                if self._mac_address:
                    _LOGGER.debug("Found MAC address %s for host %s", self._mac_address, host)

            result["mac_address"] = self._mac_address

            # Test connectivity based on protocol
            if protocol == PROTOCOL_TCP:
                try:
                    start_time = self.hass.loop.time()
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(self._resolved_ip, self.target[CONF_PORT]),
                        timeout=5
                    )
                    latency = (self.hass.loop.time() - start_time) * 1000
                    writer.close()
                    await writer.wait_closed()
                    result.update({
                        "connected": True,
                        "latency": round(latency, 2)
                    })
                except Exception as err:
                    _LOGGER.debug("TCP connection failed: %s", err)

            elif protocol == PROTOCOL_UDP:
                try:
                    start_time = self.hass.loop.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(5)
                    await self.hass.async_add_executor_job(
                        sock.connect,
                        (self._resolved_ip, self.target[CONF_PORT])
                    )
                    latency = (self.hass.loop.time() - start_time) * 1000
                    sock.close()
                    result.update({
                        "connected": True,
                        "latency": round(latency, 2)
                    })
                except Exception as err:
                    _LOGGER.debug("UDP connection failed: %s", err)

            elif protocol == PROTOCOL_ICMP:
                try:
                    response_time = await self.hass.async_add_executor_job(
                        ping, self._resolved_ip, DEFAULT_PING_TIMEOUT, 1
                    )
                    if response_time is not None:
                        result.update({
                            "connected": True,
                            "latency": round(response_time * 1000, 2)
                        })
                except Exception as err:
                    _LOGGER.debug("ICMP ping failed: %s", err)

            return result

        except Exception as err:
            _LOGGER.error(
                "Update failed for %s:%s (%s): %s",
                host,
                self.target.get(CONF_PORT, "N/A"),
                protocol,
                err
            )
            return result

    async def _get_resolver(self):
        """Get a DNS resolver instance."""
        if not self._resolver:
            def _create_resolver():
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [self._dns_server]
                resolver.timeout = 2
                resolver.lifetime = 4
                return resolver

            self._resolver = await self.hass.async_add_executor_job(_create_resolver)
        return self._resolver

    async def _get_mac_address(self, ip: str) -> str | None:
        """Get MAC address for an IP."""
        try:
            # Try ARP table lookup
            cmd = "arp -n" if not hasattr(socket, 'AF_HYPERV') else "arp -a"
            proc = await asyncio.create_subprocess_shell(
                f"{cmd} {ip}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            # Regular expression to match MAC address
            mac_match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})", output)
            if mac_match:
                return mac_match.group(0).upper().replace('-', ':')

            _LOGGER.debug("No MAC address found in ARP for IP %s", ip)
            return None
        except Exception as err:
            _LOGGER.error("Error getting MAC address for %s: %s", ip, err)
            return None

    async def _get_resolver(self):
        """Get a DNS resolver in executor."""
        if not HAVE_DNS:
            return None

        if self._resolver is None:
            def _create_resolver():
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [self._dns_server]
                resolver.timeout = 2
                resolver.lifetime = 4
                return resolver

            self._resolver = await self.hass.async_add_executor_job(_create_resolver)

        return self._resolver

    async def _resolve_host(self, hostname: str) -> str | None:
        """Resolve hostname to IP address using configured DNS server."""
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

            # Get resolver with configured DNS server
            resolver = await self._get_resolver()

            def _do_resolve():
                try:
                    # Use the configured DNS server to resolve
                    answers = resolver.resolve(hostname, "A")
                    if answers:
                        return str(answers[0])
                    return None
                except Exception as err:
                    _LOGGER.debug("DNS resolution failed: %s", err)
                    return None

            result = await self.hass.async_add_executor_job(_do_resolve)

            if result:
                _LOGGER.debug(
                    "Resolved %s to %s using DNS server %s",
                    hostname,
                    result,
                    self._dns_server
                )
                return result

            _LOGGER.warning(
                "Could not resolve %s using DNS server %s",
                hostname,
                self._dns_server
            )
            return None

        except Exception as err:
            _LOGGER.error("Error resolving hostname %s: %s", hostname, err)
            return None

class ConnectivitySensor(CoordinatorEntity, SensorEntity):
    """Connectivity sensor for individual protocols."""

    def __init__(self, coordinator: ConnectivityCoordinator, target: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.target = target
        self._attr_has_entity_name = True
        self._attr_available = True

        device_name = target.get("device_name", target[CONF_HOST])
        safe_device_name = device_name.lower().replace(' ', '_').replace('-', '_').replace('.', '_')

        # Set up sensor name and ID based on protocol
        if target[CONF_PROTOCOL] == PROTOCOL_ICMP:
            self._attr_name = "ICMP (Ping)"
            entity_id_suffix = "icmp"
        elif target[CONF_PROTOCOL] == PROTOCOL_AD_DC:
            port_name = AD_DC_PORTS.get(target[CONF_PORT], str(target[CONF_PORT]))
            self._attr_name = f"AD {port_name}"
            entity_id_suffix = f"ad_{target[CONF_PORT]}"
        else:
            self._attr_name = f"{target[CONF_PROTOCOL]} {target[CONF_PORT]}"
            entity_id_suffix = f"{target[CONF_PROTOCOL].lower()}_{target[CONF_PORT]}"

        # Set entity ID
        self.entity_id = f"sensor.connectivity_monitor_{safe_device_name}_{entity_id_suffix}"

        # Get data from coordinator
        coord_data = coordinator.data or {}
        mac_address = coord_data.get("mac_address")
        ip_address = coord_data.get("resolved_ip")

        # Set unique_id with prefix
        base_id = None
        if mac_address:
            base_id = mac_address.lower().replace(':', '')
        elif ip_address:
            base_id = ip_address.replace('.', '_')
        else:
            base_id = target[CONF_HOST].replace('.', '_')

        self._attr_unique_id = f"connectivity_{base_id}_{target[CONF_PROTOCOL]}_{target.get(CONF_PORT, 'ping')}"

        # Set up device info
        connections = set()
        if mac_address:
            connections.add(("mac", mac_address.lower()))
        if ip_address:
            connections.add(("ip", ip_address))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address.lower().replace(':', '')) if mac_address else (DOMAIN, target[CONF_HOST])},
            name=device_name,
            manufacturer="Connectivity Monitor",
            model="Network Monitor",
            sw_version="0.1.00018",
            connections=connections,
        )

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Unknown"
        return "Connected" if self.coordinator.data.get("connected", False) else "Disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = {
            "host": self.target[CONF_HOST],
            "protocol": self.target[CONF_PROTOCOL],
        }

        if self.target[CONF_PROTOCOL] == PROTOCOL_AD_DC:
            attrs["port"] = self.target[CONF_PORT]
            attrs["service"] = AD_DC_PORTS.get(self.target[CONF_PORT], "Unknown Service")
        elif self.target[CONF_PROTOCOL] not in [PROTOCOL_ICMP]:
            attrs["port"] = self.target[CONF_PORT]

        if self.coordinator.data:
            if self.coordinator.data.get("latency") is not None:
                attrs["latency_ms"] = self.coordinator.data["latency"]
            if self.coordinator.data.get("resolved_ip"):
                attrs["resolved_ip"] = self.coordinator.data["resolved_ip"]
            if self.coordinator.data.get("mac_address"):
                attrs["mac_address"] = self.coordinator.data["mac_address"]

        return attrs

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if not self.coordinator.data or not self.coordinator.data.get("connected", False):
            return "mdi:lan-disconnect"
        return "mdi:lan-connect"

class OverviewSensor(CoordinatorEntity, SensorEntity):
    """Overview sensor showing combined status."""

    def __init__(self, coordinator: ConnectivityCoordinator, target: dict, device_coordinators: list) -> None:
        """Initialize the overview sensor."""
        super().__init__(coordinator)
        self.target = target
        self._device_coordinators = device_coordinators
        self._attr_has_entity_name = True
        self._attr_available = True

        device_name = target.get("device_name", target[CONF_HOST])
        safe_device_name = device_name.lower().replace(' ', '_').replace('-', '_').replace('.', '_')

        self._attr_name = "Overall Status"
        self.entity_id = f"sensor.connectivity_monitor_{safe_device_name}_overall"

        # Get data from coordinator
        coord_data = coordinator.data or {}
        mac_address = coord_data.get("mac_address")
        ip_address = coord_data.get("resolved_ip")

        # Set unique_id with prefix
        if mac_address:
            base_id = mac_address.lower().replace(':', '')
        elif ip_address:
            base_id = ip_address.replace('.', '_')
        else:
            base_id = target[CONF_HOST].replace('.', '_')

        self._attr_unique_id = f"connectivity_{base_id}_overall"

        # Set up device info
        connections = set()
        if mac_address:
            connections.add(("mac", mac_address.lower()))
        if ip_address:
            connections.add(("ip", ip_address))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address.lower().replace(':', '')) if mac_address else (DOMAIN, target[CONF_HOST])},
            name=device_name,
            manufacturer="Connectivity Monitor",
            model="Network Monitor",
            sw_version="0.1.00018",
            connections=connections,
        )

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if not self._device_coordinators:
            return "Unknown"

        all_connected = True
        any_connected = False

        for coord in self._device_coordinators:
            if coord.data and coord.data.get("connected"):
                any_connected = True
            else:
                all_connected = False

        if all_connected:
            return "Connected"
        elif any_connected:
            return "Partially Connected"
        return "Disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = {
            "host": self.target[CONF_HOST],
            "device_name": self.target.get("device_name", self.target[CONF_HOST]),
            "monitored_services": []
        }

        for coord in self._device_coordinators:
            service = {
                "protocol": coord.target[CONF_PROTOCOL],
                "status": "Connected" if coord.data and coord.data.get("connected") else "Disconnected"
            }

            if coord.target[CONF_PROTOCOL] == PROTOCOL_AD_DC:
                service["port"] = coord.target[CONF_PORT]
                service["service"] = AD_DC_PORTS.get(coord.target[CONF_PORT], "Unknown Service")
            elif coord.target[CONF_PROTOCOL] not in [PROTOCOL_ICMP]:
                service["port"] = coord.target[CONF_PORT]

            if coord.data:
                if coord.data.get("latency") is not None:
                    service["latency_ms"] = coord.data["latency"]
                if coord.data.get("mac_address"):
                    service["mac_address"] = coord.data["mac_address"]

            attrs["monitored_services"].append(service)

        return attrs

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.native_value == "Connected":
            return "mdi:check-network"
        elif self.native_value == "Partially Connected":
            return "mdi:network-strength-2"
        return "mdi:close-network"

class ADOverviewSensor(CoordinatorEntity, SensorEntity):
    """Overview sensor specifically for Active Directory status."""

    def __init__(self, coordinator: ConnectivityCoordinator, target: dict, ad_coordinators: list) -> None:
        """Initialize the AD overview sensor."""
        super().__init__(coordinator)
        self.target = target
        self._coordinators = ad_coordinators
        self._attr_has_entity_name = True
        self._attr_available = True

        device_name = target.get("device_name", target[CONF_HOST])
        safe_device_name = device_name.lower().replace(' ', '_').replace('-', '_').replace('.', '_')

        self._attr_name = "Active Directory"
        self.entity_id = f"sensor.connectivity_monitor_{safe_device_name}_ad"

        # Get data from coordinator
        coord_data = coordinator.data or {}
        mac_address = coord_data.get("mac_address")
        ip_address = coord_data.get("resolved_ip")

        # Set unique_id with prefix
        base_id = None
        if mac_address:
            base_id = mac_address.lower().replace(':', '')
        elif ip_address:
            base_id = ip_address.replace('.', '_')
        else:
            base_id = target[CONF_HOST].replace('.', '_')

        self._attr_unique_id = f"connectivity_{base_id}_ad"

        # Set up device info
        connections = set()
        if mac_address:
            connections.add(("mac", mac_address.lower()))
        if ip_address:
            connections.add(("ip", ip_address))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address.lower().replace(':', '')) if mac_address else (DOMAIN, target[CONF_HOST])},
            name=device_name,
            manufacturer="Connectivity Monitor",
            model="Network Monitor",
            sw_version="0.1.00018",
            connections=connections,
        )

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        if not self._coordinators:
            return "Not Connected"

        all_connected = True
        any_connected = False

        for coord in self._coordinators:
            if coord.data and coord.data.get("connected"):
                any_connected = True
            else:
                all_connected = False

        if all_connected:
            return "Connected"
        elif any_connected:
            return "Partially Connected"
        return "Not Connected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        attrs = {
            "host": self.target[CONF_HOST],
            "device_name": self.target.get("device_name", self.target[CONF_HOST]),
            "ad_services": []
        }

        for coord in self._coordinators:
            service = {
                "port": coord.target[CONF_PORT],
                "service": AD_DC_PORTS.get(coord.target[CONF_PORT], "Unknown Service"),
                "status": "Connected" if coord.data and coord.data.get("connected") else "Not Connected"
            }

            if coord.data and coord.data.get("latency") is not None:
                service["latency_ms"] = coord.data["latency"]

            attrs["ad_services"].append(service)

        return attrs

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.native_value == "Connected":
            return "mdi:domain"
        elif self.native_value == "Partially Connected":
            return "mdi:domain-remove"
        return "mdi:domain-off"
