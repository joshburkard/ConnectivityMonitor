(() => {
  if (customElements.get("connectivity-monitor-panel")) return;

  const esc = (s) =>
    String(s == null ? "" : s).replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  // ── Network tab constants ────────────────────────────────────────────────────
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

  // ── ZigBee tab constants ─────────────────────────────────────────────────────
  const ZHA_STATUS_ORDER = { Inactive: 0, Unknown: 1, Active: 2 };

  const ZHA_STATUS_META = {
    Active:   { label: "Active",   css: "ok",      icon: "\u2713" },
    Inactive: { label: "Inactive", css: "error",   icon: "\u2717" },
    Unknown:  { label: "Unknown",  css: "unknown", icon: "?" },
  };

  // ── Matter tab constants ──────────────────────────────────────────────────────
  const MATTER_STATUS_ORDER = { Inactive: 0, Unknown: 1, Active: 2 };

  const MATTER_STATUS_META = {
    Active:   { label: "Active",   css: "ok",      icon: "\u2713" },
    Inactive: { label: "Inactive", css: "error",   icon: "\u2717" },
    Unknown:  { label: "Unknown",  css: "unknown", icon: "?" },
  };

  // ── Panel component ──────────────────────────────────────────────────────────
  class ConnectivityMonitorPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._lastFingerprint = null;
      this._activeTab = "network";
      // Tracks which device entity-ids are manually collapsed/expanded.
      // null = not yet initialised (use default based on status).
      this._collapsed = null;

      this.shadowRoot.addEventListener("click", (e) => {
        // Tab button → switch active tab
        const tabBtn = e.target.closest(".tab-btn[data-tab]");
        if (tabBtn) {
          e.stopPropagation();
          this._activeTab = tabBtn.dataset.tab;
          this._render();
          return;
        }
        // Configure button → navigate to integration page
        const configBtn = e.target.closest("[data-action='configure']");
        if (configBtn) {
          e.stopPropagation();
          history.pushState(null, "", "/config/integrations/integration/connectivity_monitor");
          window.dispatchEvent(new CustomEvent("location-changed"));
          return;
        }
        // Toggle chevron click - collapse/expand sensor list
        const toggleEl = e.target.closest("[data-toggle]");
        if (toggleEl) {
          e.stopPropagation();
          const key = toggleEl.dataset.toggle;
          this._collapsed.has(key) ? this._collapsed.delete(key) : this._collapsed.add(key);
          this._applyCollapse();
          return;
        }
        // Device header click → navigate to device page
        const deviceEl = e.target.closest("[data-device]");
        if (deviceEl) {
          e.stopPropagation();
          history.pushState(null, "", "/config/devices/device/" + deviceEl.dataset.device);
          window.dispatchEvent(new CustomEvent("location-changed"));
          return;
        }
        // Sensor row / entity click → open more-info dialog
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
      const fingerprint = Object.entries(hass.states)
        .filter(([id]) => id.startsWith("sensor.connectivity_monitor_"))
        .map(([id, s]) => id + "=" + s.state)
        .sort()
        .join("|");
      if (fingerprint === this._lastFingerprint) return;
      this._lastFingerprint = fingerprint;
      this._render();
    }

    set panel(panel) { this._panel = panel; }

    connectedCallback() { this._render(); }

    // ── Network data ───────────────────────────────────────────────────────────
    _getDeviceData() {
      if (!this._hass) return { groups: [], totalDevices: 0 };
      const states = this._hass.states;
      const devices = [];

      for (const [entityId, state] of Object.entries(states)) {
        if (!entityId.startsWith("sensor.connectivity_monitor_") || !entityId.endsWith("_overall")) continue;
        if (state.attributes.monitor_type === "zha") continue;
        if (state.attributes.monitor_type === "matter") continue;

        const host            = state.attributes.host || "";
        const deviceName      = state.attributes.device_name || host;
        const overallStatus   = state.state || "Unknown";
        const overallEntityId = entityId;

        const sensors = Object.values(states).filter((s) => {
          const id = s.entity_id;
          return id.startsWith("sensor.connectivity_monitor_") &&
            !id.endsWith("_overall") && !id.endsWith("_ad") &&
            s.attributes.host === host &&
            s.attributes.monitor_type !== "zha" &&
            s.attributes.monitor_type !== "matter";
        });

        sensors.sort((a, b) => {
          const aFail = (a.state === "Disconnected" || a.state === "Not Connected") ? 0 : 1;
          const bFail = (b.state === "Disconnected" || b.state === "Not Connected") ? 0 : 1;
          return aFail !== bFail ? aFail - bFail : a.entity_id.localeCompare(b.entity_id);
        });

        devices.push({ host, deviceName, overallStatus, overallEntityId, sensors });
      }

      const groupMap = {};
      for (const device of devices) {
        if (!groupMap[device.overallStatus]) groupMap[device.overallStatus] = [];
        groupMap[device.overallStatus].push(device);
      }

      const groups = Object.entries(groupMap)
        .sort(([a], [b]) => (STATUS_ORDER[a] ?? 99) - (STATUS_ORDER[b] ?? 99))
        .map(([status, devs]) => ({
          status,
          devices: devs.sort((a, b) => a.deviceName.localeCompare(b.deviceName)),
        }));

      return { groups, totalDevices: devices.length };
    }

    // ── ZigBee (ZHA) data ──────────────────────────────────────────────────────
    _getZhaData() {
      if (!this._hass) return { groups: [], totalDevices: 0 };
      const states = this._hass.states;
      const devices = [];

      for (const [entityId, state] of Object.entries(states)) {
        if (!entityId.startsWith("sensor.connectivity_monitor_")) continue;
        if (state.attributes.monitor_type !== "zha") continue;

        const ieee       = state.attributes.ieee || "";
        const deviceName = state.attributes.device_name || ieee;
        const status     = state.state || "Unknown";
        const lastSeen   = state.attributes.last_seen || null;
        const minutesAgo = state.attributes.minutes_ago != null ? state.attributes.minutes_ago : null;
        const timeout    = state.attributes.timeout_minutes;
        const alertGroup = state.attributes.alert_group || null;
        const alertDelay = state.attributes.alert_delay != null ? state.attributes.alert_delay : null;
        const alertAction = state.attributes.alert_action || null;
        const alertActionDelay = state.attributes.alert_action_delay != null ? state.attributes.alert_action_delay : null;

        devices.push({ entityId, ieee, deviceName, status, lastSeen, minutesAgo, timeout, alertGroup, alertDelay, alertAction, alertActionDelay });
      }

      const groupMap = {};
      for (const device of devices) {
        if (!groupMap[device.status]) groupMap[device.status] = [];
        groupMap[device.status].push(device);
      }

      const groups = Object.entries(groupMap)
        .sort(([a], [b]) => (ZHA_STATUS_ORDER[a] ?? 99) - (ZHA_STATUS_ORDER[b] ?? 99))
        .map(([status, devs]) => ({
          status,
          devices: devs.sort((a, b) => a.deviceName.localeCompare(b.deviceName)),
        }));

      return { groups, totalDevices: devices.length };
    }

    // ── Matter data ────────────────────────────────────────────────────────────
    _getMatterData() {
      if (!this._hass) return { groups: [], totalDevices: 0 };
      const states = this._hass.states;
      const devices = [];

      for (const [entityId, state] of Object.entries(states)) {
        if (!entityId.startsWith("sensor.connectivity_monitor_")) continue;
        if (state.attributes.monitor_type !== "matter") continue;

        const nodeId     = state.attributes.node_id || "";
        const deviceName = state.attributes.device_name || nodeId;
        const status     = state.state || "Unknown";
        const alertGroup = state.attributes.alert_group || null;
        const alertDelay = state.attributes.alert_delay != null ? state.attributes.alert_delay : null;
        const alertAction = state.attributes.alert_action || null;
        const alertActionDelay = state.attributes.alert_action_delay != null ? state.attributes.alert_action_delay : null;

        devices.push({ entityId, nodeId, deviceName, status, alertGroup, alertDelay, alertAction, alertActionDelay });
      }

      const groupMap = {};
      for (const device of devices) {
        if (!groupMap[device.status]) groupMap[device.status] = [];
        groupMap[device.status].push(device);
      }

      const groups = Object.entries(groupMap)
        .sort(([a], [b]) => (MATTER_STATUS_ORDER[a] ?? 99) - (MATTER_STATUS_ORDER[b] ?? 99))
        .map(([status, devs]) => ({
          status,
          devices: devs.sort((a, b) => a.deviceName.localeCompare(b.deviceName)),
        }));

      return { groups, totalDevices: devices.length };
    }

    // ── Collapse management ────────────────────────────────────────────────────
    _initCollapsed(networkGroups, zhaGroups, matterGroups) {
      if (this._collapsed !== null) return;
      this._collapsed = new Set();
      for (const group of networkGroups) {
        if (group.status === "Connected") {
          for (const device of group.devices) {
            this._collapsed.add(device.overallEntityId);
          }
        }
      }
      for (const group of zhaGroups) {
        if (group.status === "Active") {
          for (const device of group.devices) {
            this._collapsed.add(device.entityId);
          }
        }
      }
      for (const group of matterGroups) {
        if (group.status === "Active") {
          for (const device of group.devices) {
            this._collapsed.add(device.entityId);
          }
        }
      }
    }

    _applyCollapse() {
      if (!this.shadowRoot) return;
      this.shadowRoot.querySelectorAll("[data-toggle]").forEach((btn) => {
        const key       = btn.dataset.toggle;
        const card      = btn.closest(".device-card");
        const list      = card && card.querySelector(".sensor-list");
        const collapsed = this._collapsed.has(key);
        btn.innerHTML   = collapsed ? "\u25b6" : "\u25bc";
        btn.title       = collapsed ? "Expand" : "Collapse";
        if (list) list.style.display = collapsed ? "none" : "";
      });
    }

    // ── Network tab renderers ──────────────────────────────────────────────────
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

      let deviceAttr = "data-entity=\"" + esc(device.overallEntityId) + "\"";
      if (this._hass && this._hass.entities) {
        const entry = this._hass.entities[device.overallEntityId];
        if (entry && entry.device_id) {
          deviceAttr = "data-device=\"" + esc(entry.device_id) + "\"";
        }
      }

      const chevron      = this._collapsed.has(device.overallEntityId) ? "\u25b6" : "\u25bc";
      const chevronTitle = this._collapsed.has(device.overallEntityId) ? "Expand" : "Collapse";

      return "<div class=\"device-card card-" + meta.css + "\">" +
        "<div class=\"device-header\">" +
          "<button class=\"toggle-btn\" data-toggle=\"" + esc(device.overallEntityId) + "\" title=\"" + chevronTitle + "\">" + chevron + "</button>" +
          "<div class=\"device-info clickable\" " + deviceAttr + ">" +
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

    // ── ZigBee tab renderers ───────────────────────────────────────────────────
    _renderZhaDevice(device) {
      const meta      = ZHA_STATUS_META[device.status] || ZHA_STATUS_META.Unknown;
      const toggle    = device.entityId;
      const collapsed = this._collapsed.has(toggle);
      const chevron   = collapsed ? "\u25b6" : "\u25bc";

      let lastSeenLabel = "Never seen";
      if (device.minutesAgo != null) {
        if (device.minutesAgo < 60) {
          lastSeenLabel = esc(device.minutesAgo) + " min ago";
        } else if (device.minutesAgo < 1440) {
          lastSeenLabel = Math.round(device.minutesAgo / 60) + " hr ago";
        } else {
          lastSeenLabel = Math.round(device.minutesAgo / 1440) + " day(s) ago";
        }
      }

      let deviceAttr = "data-entity=\"" + esc(device.entityId) + "\"";
      if (this._hass && this._hass.entities) {
        const entry = this._hass.entities[device.entityId];
        if (entry && entry.device_id) {
          deviceAttr = "data-device=\"" + esc(entry.device_id) + "\"";
        }
      }

      const badgeCss   = meta.css === "ok" ? "badge-ok" : "badge-error";
      const timeoutHtml = device.timeout != null
        ? "<span class=\"sensor-latency\">timeout: " + esc(device.timeout) + " min</span>"
        : "";
      const alertHtml = device.alertGroup
        ? "<span class=\"sensor-latency\">alert: " + esc(device.alertGroup) + " (" + esc(device.alertDelay) + " min)</span>"
        : "";
      const actionHtml = device.alertAction
        ? "<span class=\"sensor-latency\">action: " + esc(device.alertAction.split(".").slice(1).join(".") || device.alertAction) + " (" + esc(device.alertActionDelay) + " min)</span>"
        : "";

      return "<div class=\"device-card card-" + meta.css + "\">" + +
        "<div class=\"device-header\">" +
          "<button class=\"toggle-btn\" data-toggle=\"" + esc(toggle) + "\" title=\"" + (collapsed ? "Expand" : "Collapse") + "\">" + chevron + "</button>" +
          "<div class=\"device-info clickable\" " + deviceAttr + ">" +
            "<div class=\"device-name\">" + esc(device.deviceName) + "</div>" +
            "<div class=\"device-host\">" + esc(device.ieee) + "</div>" +
          "</div>" +
          "<span class=\"device-badge " + badgeCss + "\">" + esc(device.status) + "</span>" +
        "</div>" +
        "<div class=\"sensor-list\">" +
          "<div class=\"sensor-row clickable\" data-entity=\"" + esc(device.entityId) + "\">" +
            "<span class=\"sensor-dot dot-" + meta.css + "\"></span>" +
            "<span class=\"sensor-proto\">Last seen: " + esc(lastSeenLabel) + "</span>" +
            "<span class=\"sensor-state label-" + meta.css + "\">" + esc(device.status) + "</span>" +
            timeoutHtml +
            alertHtml +
            actionHtml +
            "<span class=\"row-arrow\">\u203a</span>" +
          "</div>" +
        "</div>" +
        "</div>";
    }

    _renderZhaGroup(group) {
      const meta    = ZHA_STATUS_META[group.status] || ZHA_STATUS_META.Unknown;
      const devHtml = group.devices.map((d) => this._renderZhaDevice(d)).join("");
      return "<div class=\"group\">" +
        "<div class=\"group-header group-header-" + meta.css + "\">" +
          "<span class=\"group-icon\">" + meta.icon + "</span>" +
          "<span class=\"group-label\">" + esc(meta.label) + "</span>" +
          "<span class=\"group-count\">" + esc(group.devices.length) + "</span>" +
        "</div>" +
        devHtml +
        "</div>";
    }

    // ── Matter tab renderers ───────────────────────────────────────────────────
    _renderMatterDevice(device) {
      const meta      = MATTER_STATUS_META[device.status] || MATTER_STATUS_META.Unknown;
      const toggle    = device.entityId;
      const collapsed = this._collapsed.has(toggle);
      const chevron   = collapsed ? "\u25b6" : "\u25bc";

      let deviceAttr = "data-entity=\"" + esc(device.entityId) + "\"";
      if (this._hass && this._hass.entities) {
        const entry = this._hass.entities[device.entityId];
        if (entry && entry.device_id) {
          deviceAttr = "data-device=\"" + esc(entry.device_id) + "\"";
        }
      }

      const badgeCss  = meta.css === "ok" ? "badge-ok" : "badge-error";
      const alertHtml = device.alertGroup
        ? "<span class=\"sensor-latency\">alert: " + esc(device.alertGroup) + " (" + esc(device.alertDelay) + " min)</span>"
        : "";
      const actionHtml = device.alertAction
        ? "<span class=\"sensor-latency\">action: " + esc(device.alertAction.split(".").slice(1).join(".") || device.alertAction) + " (" + esc(device.alertActionDelay) + " min)</span>"
        : "";

      return "<div class=\"device-card card-" + meta.css + "\">" +
        "<div class=\"device-header\">" +
          "<button class=\"toggle-btn\" data-toggle=\"" + esc(toggle) + "\" title=\"" + (collapsed ? "Expand" : "Collapse") + "\">" + chevron + "</button>" +
          "<div class=\"device-info clickable\" " + deviceAttr + ">" +
            "<div class=\"device-name\">" + esc(device.deviceName) + "</div>" +
            "<div class=\"device-host\">" + esc(device.nodeId) + "</div>" +
          "</div>" +
          "<span class=\"device-badge " + badgeCss + "\">" + esc(device.status) + "</span>" +
        "</div>" +
        "<div class=\"sensor-list\">" +
          "<div class=\"sensor-row clickable\" data-entity=\"" + esc(device.entityId) + "\">" +
            "<span class=\"sensor-dot dot-" + meta.css + "\"></span>" +
            "<span class=\"sensor-proto\">Matter Status</span>" +
            "<span class=\"sensor-state label-" + meta.css + "\">" + esc(device.status) + "</span>" +
            alertHtml +
            actionHtml +
            "<span class=\"row-arrow\">\u203a</span>" +
          "</div>" +
        "</div>" +
        "</div>";
    }

    _renderMatterGroup(group) {
      const meta    = MATTER_STATUS_META[group.status] || MATTER_STATUS_META.Unknown;
      const devHtml = group.devices.map((d) => this._renderMatterDevice(d)).join("");
      return "<div class=\"group\">" +
        "<div class=\"group-header group-header-" + meta.css + "\">" +
          "<span class=\"group-icon\">" + meta.icon + "</span>" +
          "<span class=\"group-label\">" + esc(meta.label) + "</span>" +
          "<span class=\"group-count\">" + esc(group.devices.length) + "</span>" +
        "</div>" +
        devHtml +
        "</div>";
    }

    // ── Main render ────────────────────────────────────────────────────────────
    _render() {
      if (!this.shadowRoot) return;
      try {
        const { groups: networkGroups, totalDevices: totalNetwork } = this._getDeviceData();
        const { groups: zhaGroups,     totalDevices: totalZha     } = this._getZhaData();
        const { groups: matterGroups,  totalDevices: totalMatter  } = this._getMatterData();
        const totalDevices = totalNetwork + totalZha + totalMatter;

        this._initCollapsed(networkGroups, zhaGroups, matterGroups);

        const networkActive = this._activeTab === "network";
        const zhaActive     = this._activeTab === "zha";
        const matterActive  = this._activeTab === "matter";
        const tabBarHtml =
          "<div class=\"tab-bar\">" +
            "<button class=\"tab-btn" + (networkActive ? " tab-active" : "") + "\" data-tab=\"network\">" +
              "Network" + (totalNetwork > 0 ? " (" + esc(totalNetwork) + ")" : "") +
            "</button>" +
            "<button class=\"tab-btn" + (zhaActive ? " tab-active" : "") + "\" data-tab=\"zha\">" +
              "\u26a1 ZigBee" + (totalZha > 0 ? " (" + esc(totalZha) + ")" : "") +
            "</button>" +
            "<button class=\"tab-btn" + (matterActive ? " tab-active" : "") + "\" data-tab=\"matter\">" +
              "\u25c6 Matter" + (totalMatter > 0 ? " (" + esc(totalMatter) + ")" : "") +
            "</button>" +
          "</div>";

        let tabContentHtml;
        if (networkActive) {
          tabContentHtml = totalNetwork === 0
            ? "<div class=\"no-devices\">No network devices are being monitored yet.<br>Use <em>Configure</em> to add a device.</div>"
            : networkGroups.map((g) => this._renderGroup(g)).join("");
        } else if (zhaActive) {
          tabContentHtml = totalZha === 0
            ? "<div class=\"no-devices\">No ZigBee devices are being monitored yet.<br>Use <em>Configure \u2192 Add ZigBee Device (ZHA)</em> to get started.</div>"
            : zhaGroups.map((g) => this._renderZhaGroup(g)).join("");
        } else {
          tabContentHtml = totalMatter === 0
            ? "<div class=\"no-devices\">No Matter devices are being monitored yet.<br>Use <em>Configure \u2192 Add Matter Device</em> to get started.</div>"
            : matterGroups.map((g) => this._renderMatterGroup(g)).join("");
        }

        const container = this.shadowRoot.querySelector("#cm-root");
        const root = container || document.createElement("div");
        root.id = "cm-root";
        root.innerHTML =
          "<style>" +
          "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }" +
          ":host { display: block; padding: 16px; background: var(--primary-background-color); min-height: 100%; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); color: var(--primary-text-color); }" +
          ".page-header { display: flex; align-items: flex-start; justify-content: space-between; padding-bottom: 12px; margin-bottom: 0; border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.12)); }" +
          ".page-title { font-size: 1.5rem; font-weight: 400; }" +
          ".page-subtitle { font-size: 0.85rem; color: var(--secondary-text-color); margin-top: 4px; }" +
          ".configure-btn { display: flex; align-items: center; gap: 6px; background: none; border: 1px solid var(--divider-color, rgba(0,0,0,.2)); border-radius: 6px; padding: 6px 12px; cursor: pointer; color: var(--primary-text-color); font-size: 0.82rem; white-space: nowrap; flex-shrink: 0; margin-top: 2px; }" +
          ".configure-btn:hover { background: var(--secondary-background-color, rgba(0,0,0,.05)); }" +
          ".tab-bar { display: flex; gap: 0; margin-top: 12px; margin-bottom: 16px; border-bottom: 2px solid var(--divider-color, rgba(0,0,0,.12)); }" +
          ".tab-btn { background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -2px; padding: 10px 18px; cursor: pointer; font-size: 0.88rem; font-weight: 500; color: var(--secondary-text-color); transition: color .15s; }" +
          ".tab-btn:hover { color: var(--primary-text-color); }" +
          ".tab-btn.tab-active { color: var(--primary-color, #03a9f4); border-bottom-color: var(--primary-color, #03a9f4); }" +
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
          ".device-header { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: var(--secondary-background-color, rgba(0,0,0,.03)); border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08)); }" +
          ".toggle-btn { background: none; border: none; cursor: pointer; color: var(--secondary-text-color); font-size: 0.7rem; padding: 2px 4px; flex-shrink: 0; line-height: 1; border-radius: 3px; }" +
          ".toggle-btn:hover { background: var(--secondary-background-color, rgba(0,0,0,.08)); }" +
          ".device-info { flex: 1; min-width: 0; cursor: pointer; }" +
          ".device-info:hover .device-name { text-decoration: underline; }" +
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
          ".dot-unknown { background: var(--secondary-text-color); }" +
          ".sensor-proto { font-size: 0.85rem; font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" +
          ".sensor-state { font-size: 0.8rem; white-space: nowrap; flex-shrink: 0; }" +
          ".label-error   { color: var(--error-color,   #f44336); }" +
          ".label-warning { color: var(--warning-color, #ff9800); }" +
          ".label-ok      { color: var(--success-color, #4caf50); }" +
          ".label-unknown { color: var(--secondary-text-color); }" +
          ".sensor-latency { font-size: 0.75rem; color: var(--secondary-text-color); white-space: nowrap; flex-shrink: 0; }" +
          ".clickable { cursor: pointer; }" +
          ".sensor-row.clickable:hover { background: var(--secondary-background-color, rgba(0,0,0,.05)); }" +
          ".row-arrow { font-size: 1rem; color: var(--secondary-text-color); flex-shrink: 0; margin-left: auto; padding-left: 4px; }" +
          ".no-devices { padding: 40px 20px; text-align: center; color: var(--secondary-text-color); font-size: 0.95rem; line-height: 1.6; }" +
          ".error-msg { padding: 20px; color: var(--error-color, #f44336); font-size: 0.85rem; white-space: pre-wrap; }" +
          "</style>" +
          "<div class=\"page-header\">" +
            "<div>" +
              "<div class=\"page-title\">Connectivity Monitor</div>" +
              "<div class=\"page-subtitle\">Monitoring " + esc(totalDevices) + " device" + (totalDevices !== 1 ? "s" : "") + "</div>" +
            "</div>" +
            "<button class=\"configure-btn\" data-action=\"configure\">&#9881;&nbsp;Configure</button>" +
          "</div>" +
          tabBarHtml +
          "<div class=\"tab-content\">" + tabContentHtml + "</div>";

        if (!container) this.shadowRoot.appendChild(root);

        this._applyCollapse();
      } catch (err) {
        this.shadowRoot.innerHTML = "<div class=\"error-msg\">Panel error: " + esc(String(err)) + "</div>";
      }
    }
  }

  customElements.define("connectivity-monitor-panel", ConnectivityMonitorPanel);
})();