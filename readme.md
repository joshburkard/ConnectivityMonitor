# Connectivity Monitor

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Adds a Connectivity Monitor to Home assistant. This integration requires [HACS](https://hacs.xyz).

## Features

this features are already integrated:

- Sensor-Types:
  - TCP
  - UDP
  - ICMP
  - RPC
- supports targets with IP-Address or FQDN
- allows to add later more targets or remove them again
- allows to use a custom DNS server to resolve FQDN

## Setup

Recommended to be installed via [HACS](https://github.com/hacs/integration)

1. Go to HACS -> Integrations
2. [Add this repo to your HACS custom repositories](https://hacs.xyz/docs/faq/custom_repositories)
3. Search for "Connectivity Monitor" and install.
4. Restart Home Assistant
5. Open Home Assistant Settings -> Devices & Serivces
6. Shift+reload your browser to clear config flow caches.
7. Click ADD INTEGRATION
8. Search for "Connectivity Monitor"
9. Define the DNS Server to use
10. Define the Target Host to monitor, the needed protocol and port and click on `Submit`
11. if you want to monitor additional targets check the checkbox `another` and click on `Submit`
12. configure the interval and click on `Submit`
13. done, if you want to edit your settings, you can click on your integration on on `CONFIGURE`

## more documentation

you can find more documentation [here](doc/examples.md)

## Change Log

here you will find the [Change Log](changelog.md)

## Notes

This custom component was created without any knowledge of Python but with use of Claude AI
