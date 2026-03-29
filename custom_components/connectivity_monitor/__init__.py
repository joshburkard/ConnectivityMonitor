"""The Connectivity Monitor integration."""
from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_TARGETS

_LOGGER = logging.getLogger(__name__)

# We only need the sensor platform since alerts are handled within the sensor code
PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Connectivity Monitor component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the Connectivity Issues sidebar panel (called once per HA startup)."""
    from aiohttp import web
    from homeassistant.components.http import HomeAssistantView
    from homeassistant.components.panel_custom import async_register_panel

    www_path = Path(__file__).parent / "www"

    class ConnectivityMonitorJSView(HomeAssistantView):
        """Serve the panel JS file."""
        url = "/connectivity_monitor_panel/panel.js"
        name = "connectivity_monitor:panel_js"
        requires_auth = False

        async def get(self, request):  # noqa: D102
            js_file = www_path / "panel.js"
            return web.FileResponse(js_file)

    hass.http.register_view(ConnectivityMonitorJSView)

    await async_register_panel(
        hass,
        webcomponent_name="connectivity-monitor-panel",
        frontend_url_path="connectivity_monitor",
        module_url=f"/connectivity_monitor_panel/panel.js?v={datetime.now().strftime('%Y%m%d%H%M%S')}",
        sidebar_title="Connectivity Monitor",
        sidebar_icon="mdi:lan-check",
        require_admin=False,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Connectivity Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    # Register the sidebar panel only once across all config entries
    if not hass.data[DOMAIN].get("_panel_registered"):
        try:
            await _async_register_panel(hass)
            hass.data[DOMAIN]["_panel_registered"] = True
        except Exception as err:
            _LOGGER.warning("Could not register Connectivity Issues sidebar panel: %s", err)

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
