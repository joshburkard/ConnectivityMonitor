# custom_components/connectivity_monitor/const.py
"""Constants for the Connectivity Monitor integration."""
from datetime import timedelta

DOMAIN = "connectivity_monitor"

DEFAULT_PORT = 80
DEFAULT_PROTOCOL = "TCP"
DEFAULT_INTERVAL = 30
DEFAULT_DNS_SERVER = "1.1.1.1"  # Cloudflare DNS as default

CONF_HOST = "host"
CONF_PROTOCOL = "protocol"
CONF_PORT = "port"
CONF_INTERVAL = "interval"
CONF_TARGETS = "targets"
CONF_DNS_SERVER = "dns_server"

PROTOCOL_TCP = "TCP"
PROTOCOL_UDP = "UDP"
PROTOCOL_ICMP = "ICMP"
PROTOCOL_RPC = "RPC"

PROTOCOLS = [PROTOCOL_TCP, PROTOCOL_UDP, PROTOCOL_ICMP, PROTOCOL_RPC]

# Default RPC ports
RPC_DEFAULT_PORTS = [111, 135, 139, 445]

# Default ping timeout in seconds
DEFAULT_PING_TIMEOUT = 2