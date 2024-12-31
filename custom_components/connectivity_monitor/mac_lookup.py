# custom_components/connectivity_monitor/mac_lookup.py
"""MAC address lookup functionality for Connectivity Monitor."""
import asyncio
import logging
import re
import socket
import subprocess
from typing import Optional

_LOGGER = logging.getLogger(__name__)

async def get_mac_address(ip_address: str) -> Optional[str]:
    """Get MAC address for an IP address."""
    try:
        # Try ARP table lookup first
        result = await _get_mac_from_arp(ip_address)
        if result:
            return result

        # Try connecting to the host to ensure it's in ARP table
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_address, 80),
            timeout=1
        )
        writer.close()
        await writer.wait_closed()

        # Try ARP lookup again
        result = await _get_mac_from_arp(ip_address)
        if result:
            return result

    except Exception as err:
        _LOGGER.debug("Error getting MAC address for %s: %s", ip_address, err)

    return None

async def _get_mac_from_arp(ip_address: str) -> Optional[str]:
    """Get MAC address from ARP table."""
    try:
        if _is_windows():
            cmd = f"arp -a {ip_address}"
            pattern = re.compile(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})")
        else:
            cmd = f"arp -n {ip_address}"
            pattern = re.compile(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()

        match = pattern.search(output)
        if match:
            return match.group(0).upper().replace('-', ':')

    except Exception as err:
        _LOGGER.debug("Error getting MAC from ARP for %s: %s", ip_address, err)

    return None

def _is_windows() -> bool:
    """Check if running on Windows."""
    return hasattr(socket, 'AF_HYPERV')
