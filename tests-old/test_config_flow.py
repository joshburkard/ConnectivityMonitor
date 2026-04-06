from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST, CONF_PORT

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.connectivity_monitor.const import (
    CONF_DNS_SERVER,
    CONF_INTERVAL,
    CONF_PROTOCOL,
    CONF_TARGETS,
    DEFAULT_DNS_SERVER,
    DEFAULT_INTERVAL,
    DOMAIN,
    PROTOCOL_ICMP,
    PROTOCOL_TCP,
)


async def test_user_step_shows_device_type_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_network_icmp_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"device_type": "network"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "network"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "router.local",
            CONF_PROTOCOL: PROTOCOL_ICMP,
            "device_name": "Router",
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "dns"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DNS_SERVER: "1.1.1.1"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "interval"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_INTERVAL: 120},
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Network Monitor"
    assert result["data"] == {
        CONF_TARGETS: [
            {
                CONF_HOST: "router.local",
                CONF_PROTOCOL: PROTOCOL_ICMP,
                "device_name": "Router",
                "alert_group": None,
                "alert_delay": 15,
                "alert_action": "",
                "alert_action_delay": 30,
            }
        ],
        CONF_INTERVAL: 120,
        CONF_DNS_SERVER: "1.1.1.1",
    }


async def test_dns_step_rejects_invalid_ipv4(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"device_type": "network"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "router.local",
            CONF_PROTOCOL: PROTOCOL_ICMP,
            "device_name": "Router",
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DNS_SERVER: "not-an-ip"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "dns"
    assert result["errors"] == {"base": "invalid_dns_server"}


async def test_network_tcp_adds_target_to_existing_network_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Network Monitor",
        unique_id="connectivity_monitor_network",
        data={
            CONF_TARGETS: [
                {
                    CONF_HOST: "router.local",
                    CONF_PROTOCOL: PROTOCOL_ICMP,
                    "device_name": "Router",
                    "alert_group": None,
                    "alert_delay": 15,
                    "alert_action": "",
                    "alert_action_delay": 30,
                }
            ],
            CONF_INTERVAL: DEFAULT_INTERVAL,
            CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
        },
    )
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as mock_reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"device_type": "network"},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "switch.local",
                CONF_PROTOCOL: PROTOCOL_TCP,
                "device_name": "Switch",
            },
        )

        assert result["type"] is data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "port"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PORT: 443},
        )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "device_added"
    assert entry.data == {
        CONF_TARGETS: [
            {
                CONF_HOST: "router.local",
                CONF_PROTOCOL: PROTOCOL_ICMP,
                "device_name": "Router",
                "alert_group": None,
                "alert_delay": 15,
                "alert_action": "",
                "alert_action_delay": 30,
            },
            {
                CONF_HOST: "switch.local",
                CONF_PROTOCOL: PROTOCOL_TCP,
                CONF_PORT: 443,
                "device_name": "Switch",
                "alert_group": None,
                "alert_delay": 15,
                "alert_action": "",
                "alert_action_delay": 30,
            },
        ],
        CONF_INTERVAL: DEFAULT_INTERVAL,
        CONF_DNS_SERVER: DEFAULT_DNS_SERVER,
    }
    mock_reload.assert_awaited_once_with(entry.entry_id)
