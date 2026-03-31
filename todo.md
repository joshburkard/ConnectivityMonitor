# ToDo

## additional device types

### High value — native HA integrations (same approach as ZHA/Matter):

1. **ESPHome** — Huge HA community footprint. ESPHome devices expose an api_connected binary attribute on their device entity, making reachability trivial to read. No new protocol needed — just device-registry lookup.
2. **Bluetooth / BLE — HA** has a built-in bluetooth domain since 2022. Devices have a last_seen timestamp just like ZHA, so your inactivity-timeout model maps directly.
3. **Z-Wave (zwave_js)** — The most natural next step. Z-Wave is as popular as ZigBee; devices are queryable via the zwave_js domain in the device registry with node IDs and node_status (alive/dead/asleep).

### Medium value — protocol-level monitors:

4. **HTTP/HTTPS health check** — Extend the network monitor with a new protocol type. Sends a GET request and checks for HTTP 2xx. Useful for local NAS, cameras, and self-hosted services.
5. **MQTT Last Will & Testament (LWT)** — Many DIY devices (Tasmota, custom firmware) publish an availability topic. Monitor the payload of a configurable MQTT topic (online/offline).

## Lower priority:

6. **Thread / OpenThread border router**  — Growing protocol (used by Apple devices, Google Nest); HA has partial support but it's still maturing.
7. **Lutron / KNX** — Niche but have HA integrations with device registries.