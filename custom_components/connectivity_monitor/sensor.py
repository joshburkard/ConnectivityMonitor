# custom_components/connectivity_monitor/sensor.py
"""Support for Connectivity Monitor sensors."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import socket

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PROTOCOL,
    CONF_PORT,
    CONF_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Connectivity Monitor sensor."""
    coordinator = ConnectivityCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([ConnectivitySensor(coordinator)], True)

class ConnectivityCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Connectivity Monitor data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=config_entry.data[CONF_INTERVAL]),
        )
        self.config_entry = config_entry

    async def _async_update_data(self):
        """Fetch data from the target."""
        host = self.config_entry.data[CONF_HOST]
        port = self.config_entry.data[CONF_PORT]
        protocol = self.config_entry.data[CONF_PROTOCOL]

        try:
            if protocol == "TCP":
                reader, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                return True
            else:  # UDP
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.close()
                return True
        except Exception as err:
            _LOGGER.debug("Connection failed: %s", err)
            return False

class ConnectivitySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Connectivity Monitor sensor."""

    def __init__(self, coordinator: ConnectivityCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Connectivity to {coordinator.config_entry.data[CONF_HOST]}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_connectivity"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return "Connected" if self.coordinator.data else "Disconnected"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:lan-connect" if self.coordinator.data else "mdi:lan-disconnect"
