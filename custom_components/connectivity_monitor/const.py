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