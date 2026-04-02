"""The Connectivity Monitor integration."""
from __future__ import annotations

import logging
from pathlib import Path
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_TARGETS, CONF_INTERVAL, CONF_DNS_SERVER,
    PROTOCOL_ZHA, PROTOCOL_MATTER, PROTOCOL_ESPHOME, DEFAULT_INTERVAL, DEFAULT_DNS_SERVER,
)

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old combined entry (v1) into three typed entries (v2)."""
    from homeassistant.config_entries import SOURCE_IMPORT

    if config_entry.version == 1:
        _LOGGER.info(
            "Connectivity Monitor: migrating config entry '%s' from v1 to v2 "
            "(splitting into typed entries)", config_entry.title
        )

        targets = list(config_entry.data.get(CONF_TARGETS, []))
        interval = config_entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        dns_server = config_entry.data.get(CONF_DNS_SERVER, DEFAULT_DNS_SERVER)

        network_targets = [t for t in targets if t.get("protocol") not in (PROTOCOL_ZHA, PROTOCOL_MATTER)]
        zha_targets    = [t for t in targets if t.get("protocol") == PROTOCOL_ZHA]
        matter_targets = [t for t in targets if t.get("protocol") == PROTOCOL_MATTER]

        # Schedule creation of a ZigBee Monitor entry (if ZHA devices exist)
        if zha_targets:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={
                        CONF_TARGETS: zha_targets,
                        CONF_INTERVAL: interval,
                        CONF_DNS_SERVER: dns_server,
                        "entry_type": "zha",
                    },
                )
            )

        # Schedule creation of a Matter Monitor entry (if Matter devices exist)
        if matter_targets:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={
                        CONF_TARGETS: matter_targets,
                        CONF_INTERVAL: interval,
                        CONF_DNS_SERVER: dns_server,
                        "entry_type": "matter",
                    },
                )
            )

        # Convert the current entry into the Network Monitor entry
        hass.config_entries.async_update_entry(
            config_entry,
            title="Network Monitor",
            unique_id="connectivity_monitor_network",
            data={
                CONF_TARGETS: network_targets,
                CONF_INTERVAL: interval,
                CONF_DNS_SERVER: dns_server,
            },
            version=2,
        )

        _LOGGER.info(
            "Connectivity Monitor: migration complete — %d network, %d ZigBee, %d Matter devices",
            len(network_targets), len(zha_targets), len(matter_targets),
        )

    return True

# We only need the sensor platform since alerts are handled within the sensor code
PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Connectivity Monitor component."""
    hass.data.setdefault(DOMAIN, {})

    # Serve www/ folder and inject card script
    try:
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths(
            [StaticPathConfig(
                "/connectivity_monitor_panel",
                str(Path(__file__).parent / "www"),
                cache_headers=False,
            )]
        )
        from homeassistant.components.frontend import add_extra_js_url
        add_extra_js_url(hass, "/connectivity_monitor_panel/connectivity-monitor-card.js")
    except Exception as err:
        _LOGGER.warning("Connectivity Monitor: frontend setup failed: %s", err)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Connectivity Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Clean up alert handler before unloading platforms to stop any
    # in-flight callbacks from firing during teardown.
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    alert_handler = entry_data.get("alert_handler")
    if alert_handler:
        await alert_handler.async_cleanup()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
