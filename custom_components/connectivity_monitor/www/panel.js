(() => {
  if (customElements.get("connectivity-monitor-panel")) return;

  const esc = (s) =>
    String(s == null ? "" : s).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const STATUS_ORDER = {
    Disconnected: 0,
    "Not Connected": 1,
    "Partially Connected": 2,
    Connected: 3,
  };

  const STATUS_META = {
    Disconnected:          { label: "Disconnected",        css: "error",   icon: "\u2717" },
    "Not Connected":       { label: "Not Connected",       css: "error",   icon: "\u2717" },
    "Partially Connected": { label: "Partially Connected", css: "warning", icon: "\u26a0" },
    Connected:             { label: "Connected",           css: "ok",      icon: "\u2713" },
    Unknown:               { label: "Unknown",             css: "unknown", icon: "?" },
  };

  class ConnectivityMonitorPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._lastFingerprint = null;
      // Delegated click handler wired once
      this.shadowRoot.addEventListener("click", (e) => {
        // Device header → navigate to device page
        const deviceEl = e.target.closest("[data-device]");
        if (deviceEl) {
          e.stopPropagation();
          history.pushState(null, "", "/config/devices/device/" + deviceEl.dataset.device);
          window.dispatchEvent(new CustomEvent("location-changed"));
          return;
        }
        // Sensor row → open more-info dialog
        const entityEl = e.target.closest("[data-entity]");
        if (entityEl) {
          e.stopPropagation();
          this.dispatchEvent(new CustomEvent("hass-more-info", {
            bubbles: true,
            composed: true,
            detail: { entityId: entityEl.dataset.entity },
          }));
        }
      });
    }

    set hass(hass) {
      this._hass = hass;
      // Only re-render when a connectivity_monitor sensor state actually changed.
      // HA calls set hass() on every state change in the whole system, so without
      // this guard the DOM is replaced mid-click, breaking the event handler.
      const fingerprint = Object.entries(hass.states)
        .filter(([id]) => id.startsWith("sensor.connectivity_monitor_"))
        .map(([id, s]) => id + "=" + s.state)
        .sort()
        .join("|");
      if (fingerprint === this._lastFingerprint) return;
      this._lastFingerprint = fingerprint;
      this._render();
    }

    set panel(panel) {
      this._panel = panel;
    }

    connectedCallback() {
      this._render();
    }

    _getDeviceData() {
      if (!this._hass) return { groups: [], totalDevices: 0 };

      const states = this._hass.states;
      const devices = [];

      for (const [entityId, state] of Object.entries(states)) {
        if (
          !entityId.startsWith("sensor.connectivity_monitor_") ||
          !entityId.endsWith("_overall")
        ) continue;

        const host          = state.attributes.host || "";
        const deviceName    = state.attributes.device_name || host;
        const overallStatus = state.state || "Unknown";
        const overallEntityId = entityId;

        const sensors = Object.values(states).filter((s) => {
          const id = s.entity_id;
          return (
            id.startsWith("sensor.connectivity_monitor_") &&
            !id.endsWith("_overall") &&
            !id.endsWith("_ad") &&
            s.attributes.host === host
          );
        });

        // Sort sensors: failing first, then alphabetically by entity_id
        sensors.sort((a, b) => {
          const aFail = a.state === "Disconnected" || a.state === "Not Connected" ? 0 : 1;
          const bFail = b.state === "Disconnected" || b.state === "Not Connected" ? 0 : 1;
          return aFail !== bFail ? aFail - bFail : a.entity_id.localeCompare(b.entity_id);
        });

        devices.push({ host, deviceName, overallStatus, overallEntityId, sensors });
      }

      const groupMap = {};
      for (const device of devices) {
        const key = device.overallStatus;
        if (!groupMap[key]) groupMap[key] = [];
        groupMap[key].push(device);
      }

      const groups = Object.entries(groupMap)
        .sort(([a], [b]) => (STATUS_ORDER[a] ?? 99) - (STATUS_ORDER[b] ?? 99))
        .map(([status, devs]) => ({
          status,
          devices: devs.sort((a, b) => a.deviceName.localeCompare(b.deviceName)),
        }));

      return { groups, totalDevices: devices.length };
    }

    _renderSensor(sensor) {
      const st      = sensor.state;
      const isError = st === "Disconnected" || st === "Not Connected";
      const isWarn  = st === "Partially Connected";
      const dotCss  = isError ? "error" : isWarn ? "warning" : "ok";

      const proto   = sensor.attributes.protocol || "ICMP";
      const port    = sensor.attributes.port;
      const service = sensor.attributes.service;
      let protoLabel;
      if (service)   protoLabel = esc(proto) + " \u2013 " + esc(service) + " (" + esc(port) + ")";
      else if (port) protoLabel = esc(proto) + ":" + esc(port);
      else           protoLabel = esc(proto);

      const latencyHtml = sensor.attributes.latency_ms != null
        ? "<span class=\"sensor-latency\">" + esc(sensor.attributes.latency_ms) + "&nbsp;ms</span>"
        : "";

      return "<div class=\"sensor-row clickable\" data-entity=\"" + esc(sensor.entity_id) + "\">" +
        "<span class=\"sensor-dot dot-" + dotCss + "\"></span>" +
        "<span class=\"sensor-proto\">" + protoLabel + "</span>" +
        "<span class=\"sensor-state label-" + dotCss + "\">" + esc(st) + "</span>" +
        latencyHtml +
        "<span class=\"row-arrow\">\u203a</span>" +
        "</div>";
    }

    _renderDevice(device) {
      const meta        = STATUS_META[device.overallStatus] || STATUS_META.Unknown;
      const sensorsHtml = device.sensors.map((s) => this._renderSensor(s)).join("");
      const failCount   = device.sensors.filter(
        (s) => s.state === "Disconnected" || s.state === "Not Connected"
      ).length;
      const badgeHtml = failCount > 0
        ? "<span class=\"device-badge badge-error\">" + esc(failCount) + "&nbsp;failed</span>"
        : "<span class=\"device-badge badge-ok\">OK</span>";

      // Resolve device_id via hass.entities (available in HA 2022+)
      let deviceAttr = "data-entity=\"" + esc(device.overallEntityId) + "\"";
      if (this._hass && this._hass.entities) {
        const entry = this._hass.entities[device.overallEntityId];
        if (entry && entry.device_id) {
          deviceAttr = "data-device=\"" + esc(entry.device_id) + "\"";
        }
      }

      return "<div class=\"device-card card-" + meta.css + "\">" +
        "<div class=\"device-header clickable\" " + deviceAttr + ">" +
          "<div class=\"device-info\">" +
            "<div class=\"device-name\">" + esc(device.deviceName) + "</div>" +
            "<div class=\"device-host\">" + esc(device.host) + "</div>" +
          "</div>" +
          badgeHtml +
        "</div>" +
        "<div class=\"sensor-list\">" + sensorsHtml + "</div>" +
        "</div>";
    }

    _renderGroup(group) {
      const meta    = STATUS_META[group.status] || STATUS_META.Unknown;
      const devHtml = group.devices.map((d) => this._renderDevice(d)).join("");
      return "<div class=\"group\">" +
        "<div class=\"group-header group-header-" + meta.css + "\">" +
          "<span class=\"group-icon\">" + meta.icon + "</span>" +
          "<span class=\"group-label\">" + esc(meta.label) + "</span>" +
          "<span class=\"group-count\">" + esc(group.devices.length) + "</span>" +
        "</div>" +
        devHtml +
        "</div>";
    }

    _render() {
      if (!this.shadowRoot) return;
      try {
        const { groups, totalDevices } = this._getDeviceData();

        const bodyHtml = totalDevices === 0
          ? "<div class=\"no-devices\">No devices are being monitored yet.</div>"
          : groups.map((g) => this._renderGroup(g)).join("");

        // Re-set innerHTML but keep the listener (it was attached in constructor, survives innerHTML changes)
        const container = this.shadowRoot.querySelector("#cm-root");
        const root = container || document.createElement("div");
        root.id = "cm-root";
        root.innerHTML =
          "<style>" +
          "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }" +
          ":host { display: block; padding: 16px; background: var(--primary-background-color); min-height: 100%; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); color: var(--primary-text-color); }" +
          ".page-header { padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.12)); }" +
          ".page-title { font-size: 1.5rem; font-weight: 400; }" +
          ".page-subtitle { font-size: 0.85rem; color: var(--secondary-text-color); margin-top: 4px; }" +
          ".group { margin-bottom: 20px; }" +
          ".group-header { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 6px 6px 0 0; font-size: 0.82rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }" +
          ".group-header-error   { background: rgba(244,67,54,.15);   color: var(--error-color,   #f44336); }" +
          ".group-header-warning { background: rgba(255,152,0,.15);   color: var(--warning-color, #ff9800); }" +
          ".group-header-ok      { background: rgba(76,175,80,.12);   color: var(--success-color, #4caf50); }" +
          ".group-header-unknown { background: rgba(128,128,128,.12); color: var(--secondary-text-color); }" +
          ".group-icon { font-size: 0.95rem; } .group-label { flex: 1; }" +
          ".group-count { background: rgba(0,0,0,.12); border-radius: 10px; padding: 1px 8px; font-size: 0.78rem; }" +
          ".device-card { background: var(--card-background-color, #fff); margin-bottom: 4px; box-shadow: var(--ha-card-box-shadow, 0 1px 4px rgba(0,0,0,.08)); overflow: hidden; border-left: 4px solid transparent; }" +
          ".device-card:last-child { margin-bottom: 0; border-radius: 0 0 6px 6px; }" +
          ".card-error   { border-left-color: var(--error-color,   #f44336); }" +
          ".card-warning { border-left-color: var(--warning-color, #ff9800); }" +
          ".card-ok      { border-left-color: var(--success-color, #4caf50); }" +
          ".card-unknown { border-left-color: var(--secondary-text-color); }" +
          ".device-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: var(--secondary-background-color, rgba(0,0,0,.03)); border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08)); }" +
          ".device-name { font-size: 0.92rem; font-weight: 500; }" +
          ".device-host { font-size: 0.75rem; color: var(--secondary-text-color); margin-top: 1px; }" +
          ".device-badge { border-radius: 20px; padding: 2px 10px; font-size: 0.73rem; font-weight: 600; white-space: nowrap; flex-shrink: 0; }" +
          ".badge-error { background: var(--error-color, #f44336); color: #fff; }" +
          ".badge-ok    { background: var(--success-color, #4caf50); color: #fff; }" +
          ".sensor-list { padding: 2px 0; }" +
          ".sensor-row { display: flex; align-items: center; padding: 5px 14px; gap: 10px; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.06)); }" +
          ".sensor-row:last-child { border-bottom: none; }" +
          ".sensor-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }" +
          ".dot-error   { background: var(--error-color,   #f44336); }" +
          ".dot-warning { background: var(--warning-color, #ff9800); }" +
          ".dot-ok      { background: var(--success-color, #4caf50); }" +
          ".sensor-proto { font-size: 0.85rem; font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" +
          ".sensor-state { font-size: 0.8rem; white-space: nowrap; flex-shrink: 0; }" +
          ".label-error   { color: var(--error-color,   #f44336); }" +
          ".label-warning { color: var(--warning-color, #ff9800); }" +
          ".label-ok      { color: var(--success-color, #4caf50); }" +
          ".sensor-latency { font-size: 0.75rem; color: var(--secondary-text-color); white-space: nowrap; flex-shrink: 0; }" +
          ".clickable { cursor: pointer; transition: background 0.15s; }" +
          ".clickable:hover { background: var(--secondary-background-color, rgba(0,0,0,.05)) !important; }" +
          ".row-arrow { font-size: 1rem; color: var(--secondary-text-color); flex-shrink: 0; margin-left: auto; padding-left: 4px; }" +
          ".no-devices { padding: 40px 20px; text-align: center; color: var(--secondary-text-color); font-size: 0.95rem; }" +
          ".error-msg { padding: 20px; color: var(--error-color, #f44336); font-size: 0.85rem; white-space: pre-wrap; }" +
          "</style>" +
          "<div class=\"page-header\">" +
            "<div class=\"page-title\">Connectivity Monitor</div>" +
            "<div class=\"page-subtitle\">Monitoring " + esc(totalDevices) + " device" + (totalDevices !== 1 ? "s" : "") + "</div>" +
          "</div>" +
          bodyHtml;

        if (!container) this.shadowRoot.appendChild(root);
      } catch (err) {
        this.shadowRoot.innerHTML = "<div class=\"error-msg\">Panel error: " + esc(String(err)) + "</div>";
      }
    }
  }

  customElements.define("connectivity-monitor-panel", ConnectivityMonitorPanel);
})();
