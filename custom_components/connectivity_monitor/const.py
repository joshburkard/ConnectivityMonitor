# custom_components/connectivity_monitor/const.py
"""Constants for the Connectivity Monitor integration."""
from datetime import timedelta

DOMAIN = "connectivity_monitor"

DEFAULT_PORT = 80
DEFAULT_PROTOCOL = "TCP"
DEFAULT_INTERVAL = 30

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
PROTOCOL_AD_DC = "AD_DC"  # New protocol for Active Directory DC

PROTOCOLS = [PROTOCOL_TCP, PROTOCOL_UDP, PROTOCOL_ICMP, PROTOCOL_RPC, PROTOCOL_AD_DC]

# Default ports for Active Directory DC
AD_DC_PORTS = {
    88: "Kerberos",
    139: "NetBIOS",
    389: "LDAP",
    445: "SMB",
    464: "Kerberos Password Change",
    636: "LDAPS",
    3268: "Global Catalog",
    3269: "Global Catalog SSL"
}

# Default RPC ports
RPC_DEFAULT_PORTS = [111, 135, 139, 445]

# Default ping timeout in seconds
DEFAULT_PING_TIMEOUT = 2
DEFAULT_DNS_SERVER = "1.1.1.1"