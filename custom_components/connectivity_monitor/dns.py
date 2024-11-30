# custom_components/connectivity_monitor/dns.py
"""DNS resolution handling for Connectivity Monitor."""
import logging
import socket
from typing import Optional

import dns.resolver
import dns.exception

_LOGGER = logging.getLogger(__name__)

class DNSResolver:
    """Class to handle DNS resolution with custom DNS server."""

    def __init__(self, dns_server: str):
        """Initialize the DNS resolver."""
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = [dns_server]
        self.resolver.timeout = 2
        self.resolver.lifetime = 4

    async def resolve(self, hostname: str) -> Optional[str]:
        """Resolve hostname to IP address using configured DNS server."""
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

            # Resolve the hostname
            answers = await self.resolver.resolve(hostname, "A")
            if answers:
                return str(answers[0])

            return None

        except dns.exception.DNSException as err:
            _LOGGER.error("DNS resolution failed for %s: %s", hostname, err)
            return None