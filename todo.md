# ToDo

- [ ] additional device types
  - [ ] High value — native HA integrations (same approach as ZHA/Matter):
    - [x] 1. **ESPHome** — Huge HA community footprint. ESPHome devices expose an api_connected binary attribute on their device entity, making reachability trivial to read. No new protocol needed — just device-registry lookup.
    - [x] 2. **Bluetooth / BLE — HA** has a built-in bluetooth domain since 2022. Devices have a last_seen timestamp just like ZHA, so your inactivity-timeout model maps directly.
    - [ ] 3. **Z-Wave (zwave_js)** — The most natural next step. Z-Wave is as popular as ZigBee; devices are queryable via the zwave_js domain in the device registry with node IDs and node_status (alive/dead/asleep).
  - Medium value — protocol-level monitors:
    - [ ] 4. **HTTP/HTTPS health check** — Extend the network monitor with a new protocol type. Sends a GET request and checks for HTTP 2xx. Useful for local NAS, cameras, and self-hosted services.
      - [ ] Result check
      - [ ] Certificate check
      - [ ] Authentication check
      - [ ] Content Check
    - [ ] 5. **MQTT Last Will & Testament (LWT)** — Many DIY devices (Tasmota, custom firmware) publish an availability topic. Monitor the payload of a configurable MQTT topic (online/offline).
  - [ ] Lower priority:
    - [ ] 6. **Thread / OpenThread border router**  — Growing protocol (used by Apple devices, Google Nest); HA has partial support but it's still maturing.
    - [ ] 7. **Lutron / KNX** — Niche but have HA integrations with device registries.
- [ ] Integration Maturity:
    - [x] Replace panel_custom panel with a standard Lovelace card or remove it
    - [x] Replace ping3 with a built-in ICMP approach
    - [x] Introduce DataUpdateCoordinator to centralize all polling
    - [ ] Write tests:
      - [x] config flow first
      - [x] options flow tests
      - [ ] then sensors
      - [ ] then protocol modules:
        - [ ] Network
        - [ ] Matter
        - [ ] ESP32
        - [ ] ZigBee
        - [ ] Bluetooth

      - Alert handler tests
    - [ ] Run hassfest locally: python -m script.hassfest (from HA core checkout)
    - [ ] Apply for review via a draft PR to homeassistant/core — maintainers will give feedback before full review


# Config / Option flow tests

Yes. The current flow coverage is good enough as a baseline, but it is not complete yet.

For config flow, the highest-value missing cases are:

- TCP or UDP creation path, so you cover the extra port step instead of only ICMP.
- Active Directory path, because it fans out one device into multiple target ports and is easy to break.
- “All devices already added” branches for ZHA, Matter, ESPHome, and Bluetooth.
- One happy-path device add for at least one shared-device protocol such as ZHA or Matter, not just the “no devices found” case.

For options flow, the most useful missing cases are:

- Rename device flow for network targets, since it updates host, name, and removes old device-registry entries.
- Remove device flow for network targets.
- Remove single sensor flow for network targets.
- Cleanup orphans flow from the settings menu.
- One protocol-specific options flow, such as Matter or Bluetooth alert configuration, to prove those branches really update entry data correctly.

So the answer is: yes, there are still worthwhile flow tests to add, but they are now in the “improve coverage and regression resistance” category, not “missing basic test coverage.” If your immediate goal is Bronze-quality confidence, I would prioritize:

TCP or UDP config flow
AD config flow
Rename device option flow
Remove device option flow
Cleanup orphans option flow
After that, I would move to protocol-specific sensor and alert tests rather than keep expanding flow tests first.