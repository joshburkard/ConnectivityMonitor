"""Constants for the Connectivity Monitor integration."""
from datetime import timedelta

DOMAIN = "connectivity_monitor"

DEFAULT_PORT = 80
DEFAULT_PROTOCOL = "TCP"
DEFAULT_INTERVAL = 300
DEFAULT_PING_TIMEOUT = 2
DEFAULT_DNS_SERVER = "1.1.1.1"
DEFAULT_ALERT_DELAY = 15
DEFAULT_ALERT_GROUP = None

CONF_HOST = "host"
CONF_PROTOCOL = "protocol"
CONF_PORT = "port"
CONF_INTERVAL = "interval"
CONF_TARGETS = "targets"
CONF_DNS_SERVER = "dns_server"
CONF_ALERT_GROUP = "alert_group"
CONF_ALERT_DELAY = "alert_delay"

PROTOCOL_TCP = "TCP"
PROTOCOL_UDP = "UDP"
PROTOCOL_ICMP = "ICMP"
PROTOCOL_RPC = "RPC"
PROTOCOL_AD_DC = "AD_DC"

PROTOCOLS = [PROTOCOL_TCP, PROTOCOL_UDP, PROTOCOL_ICMP, PROTOCOL_AD_DC]

# Default RPC ports
RPC_DEFAULT_PORTS = [111, 135, 139, 445]

# Default Active Directory ports
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
