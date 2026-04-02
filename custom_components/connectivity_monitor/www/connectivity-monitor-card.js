console.log("[CM] script start");

var CM_DEVICE_TYPES = ["ESP32", "Matter", "Network", "ZigBee"];
var CM_STATUS_OPTIONS = {
  ESP32:    ["Active", "Inactive", "All"],
  Matter:   ["Active", "Inactive", "All"],
  ZigBee:   ["Active", "Inactive", "All"],
  Network:  ["Connected", "Disconnected", "Partially Connected",
             "Disconnected & Partially Connected",
             "Connected & Partially Connected", "All"]
};
var CM_DEFAULT_STATUS = { ESP32: "All", Matter: "All", ZigBee: "All", Network: "All" };

var CM_STATUS_META = {
  Connected:             { label: "Connected",            css: "ok",      icon: "\u2713" },
  Disconnected:          { label: "Disconnected",         css: "error",   icon: "\u2717" },
  "Not Connected":       { label: "Not Connected",        css: "error",   icon: "\u2717" },
  "Partially Connected": { label: "Partially Connected",  css: "warning", icon: "\u26a0" },
  Active:                { label: "Active",               css: "ok",      icon: "\u2713" },
  Inactive:              { label: "Inactive",             css: "error",   icon: "\u2717" },
  Unknown:               { label: "Unknown",              css: "unknown", icon: "?" }
};

var CM_STATUS_ORDER = {
  Disconnected: 0, "Not Connected": 0, Inactive: 0,
  "Partially Connected": 2,
  Connected: 3, Active: 3, Unknown: 99
};

function cmEsc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, function(c) {
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
  });
}

// --- Visual editor ---
class ConnectivityMonitorCardEditor extends HTMLElement {
  setConfig(config) {
    var oldConfig = this._config;
    this._config = Object.assign({}, config);
    // Skip full re-render if only the title changed (input field has focus)
    if (oldConfig && this.shadowRoot) {
      var titleEl = this.shadowRoot.getElementById("cm_title");
      if (titleEl && titleEl === this.shadowRoot.activeElement) return;
    }
    this._render();
  }
  set hass(hass) { this._hass = hass; }
  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }
  _render() {
    if (!this.shadowRoot) return;
    if (!this._config) return;
    var dt = this._config.device_type || "Network";
    var sf = this._config.status_filter || CM_DEFAULT_STATUS[dt] || "All";
    var title = this._config.title != null ? this._config.title : "";
    var opts = CM_STATUS_OPTIONS[dt] || CM_STATUS_OPTIONS["Network"];

    var dtOptions = "";
    for (var i = 0; i < CM_DEVICE_TYPES.length; i++) {
      var t = CM_DEVICE_TYPES[i];
      dtOptions += "<option value='" + t + "'" + (t === dt ? " selected" : "") + ">" + t + "</option>";
    }
    var sfOptions = "";
    for (var j = 0; j < opts.length; j++) {
      var s = opts[j];
      sfOptions += "<option value='" + s + "'" + (s === sf ? " selected" : "") + ">" + s + "</option>";
    }

    this.shadowRoot.innerHTML =
      "<style>" +
      ".form { display:flex; flex-direction:column; gap:16px; padding:16px; }" +
      "label { font-size:14px; font-weight:500; color:var(--primary-text-color); display:block; margin-bottom:4px; }" +
      "select, input[type=text] { width:100%; padding:8px 12px; border:1px solid var(--divider-color,#e0e0e0); border-radius:4px; background:var(--card-background-color,#fff); color:var(--primary-text-color); font-size:14px; }" +
      "select:focus, input[type=text]:focus { outline:none; border-color:var(--primary-color); }" +
      "</style>" +
      "<div class='form'>" +
      "<div><label>Title</label>" +
      "<input type='text' id='cm_title' value='" + cmEsc(title) + "' placeholder='Connectivity Monitor - " + cmEsc(dt) + "'></div>" +
      "<div><label>Device Type</label>" +
      "<select id='cm_dt'>" + dtOptions + "</select></div>" +
      "<div><label>Status Filter</label>" +
      "<select id='cm_sf'>" + sfOptions + "</select></div>" +
      "</div>";

    var self = this;
    this.shadowRoot.getElementById("cm_title").addEventListener("input", function(e) {
      self._config = Object.assign({}, self._config, { title: e.target.value });
      self._fire();
    });
    this.shadowRoot.getElementById("cm_dt").addEventListener("change", function(e) {
      var v = e.target.value;
      self._config = Object.assign({}, self._config, { device_type: v, status_filter: CM_DEFAULT_STATUS[v] });
      self._fire();
      self._render();
    });
    this.shadowRoot.getElementById("cm_sf").addEventListener("change", function(e) {
      var v = e.target.value;
      self._config = Object.assign({}, self._config, { status_filter: v });
      self._fire();
    });
  }
  _fire() {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: this._config }, bubbles: true, composed: true
    }));
  }
}
customElements.define("connectivity-monitor-card-editor", ConnectivityMonitorCardEditor);
console.log("[CM] editor defined OK");

// --- Card ---
class ConnectivityMonitorCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("connectivity-monitor-card-editor");
  }
  static getStubConfig() { return { device_type: "Network", status_filter: "All" }; }
  setConfig(config) {
    this._config = config;
    // Migrate old "Both" value to "All"
    if (this._config && this._config.status_filter === "Both") {
      this._config = Object.assign({}, this._config, { status_filter: "All" });
    }
    if (this.shadowRoot) this._render();
  }
  getCardSize() { return 8; }
  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) this._render();
  }
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this._render();
  }

  // -- Data fetching --
  _getDevices() {
    if (!this._hass) return [];
    var states = this._hass.states;
    var dt = (this._config && this._config.device_type) || "Network";
    var devices = [];

    if (dt === "Network") {
      for (var entityId in states) {
        if (!entityId.startsWith("sensor.connectivity_monitor_")) continue;
        if (!entityId.endsWith("_overall")) continue;
        var st = states[entityId];
        if (st.attributes.monitor_type === "zha") continue;
        if (st.attributes.monitor_type === "matter") continue;
        if (st.attributes.monitor_type === "esphome") continue;
        var host = st.attributes.host || "";
        var sensors = [];
        for (var sid in states) {
          var ss = states[sid];
          if (!sid.startsWith("sensor.connectivity_monitor_")) continue;
          if (sid.endsWith("_overall") || sid.endsWith("_ad")) continue;
          if (ss.attributes.host !== host) continue;
          if (ss.attributes.monitor_type === "zha" || ss.attributes.monitor_type === "matter" || ss.attributes.monitor_type === "esphome") continue;
          sensors.push(ss);
        }
        sensors.sort(function(a, b) {
          var af = (a.state === "Disconnected" || a.state === "Not Connected") ? 0 : 1;
          var bf = (b.state === "Disconnected" || b.state === "Not Connected") ? 0 : 1;
          return af !== bf ? af - bf : a.entity_id.localeCompare(b.entity_id);
        });
        devices.push({
          entityId: entityId,
          name: st.attributes.device_name || host,
          subtitle: host,
          status: st.state || "Unknown",
          sensors: sensors
        });
      }
    } else {
      var monitorType = dt === "ZigBee" ? "zha" : dt === "Matter" ? "matter" : "esphome";
      for (var eid in states) {
        if (!eid.startsWith("sensor.connectivity_monitor_")) continue;
        var s = states[eid];
        if (s.attributes.monitor_type !== monitorType) continue;
        var sub = "";
        if (monitorType === "zha") sub = s.attributes.ieee || "";
        else if (monitorType === "matter") sub = s.attributes.node_id || "";
        else sub = s.attributes.device_id || "";
        devices.push({
          entityId: eid,
          name: s.attributes.device_name || sub,
          subtitle: sub,
          status: s.state || "Unknown",
          sensors: [],
          minutesAgo: s.attributes.minutes_ago,
          timeout: s.attributes.timeout_minutes
        });
      }
    }
    return devices;
  }

  _filterDevices(devices) {
    var sf = (this._config && this._config.status_filter) || "All";
    var dt = (this._config && this._config.device_type) || "Network";
    if (sf === "All") return devices;
    var result = [];
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      if (dt === "Network") {
        if (sf === "Connected" && d.status === "Connected") result.push(d);
        else if (sf === "Disconnected" && (d.status === "Disconnected" || d.status === "Not Connected")) result.push(d);
        else if (sf === "Partially Connected" && d.status === "Partially Connected") result.push(d);
        else if (sf === "Disconnected & Partially Connected" && (d.status === "Disconnected" || d.status === "Not Connected" || d.status === "Partially Connected")) result.push(d);
        else if (sf === "Connected & Partially Connected" && (d.status === "Connected" || d.status === "Partially Connected")) result.push(d);
      } else {
        if (sf === "Active" && d.status === "Active") result.push(d);
        else if (sf === "Inactive" && (d.status === "Inactive" || d.status === "Unknown")) result.push(d);
      }
    }
    return result;
  }

  _groupDevices(devices) {
    var map = {};
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      if (!map[d.status]) map[d.status] = [];
      map[d.status].push(d);
    }
    var groups = [];
    for (var status in map) {
      map[status].sort(function(a, b) { return a.name.localeCompare(b.name); });
      groups.push({ status: status, devices: map[status] });
    }
    groups.sort(function(a, b) {
      var oa = CM_STATUS_ORDER[a.status] != null ? CM_STATUS_ORDER[a.status] : 99;
      var ob = CM_STATUS_ORDER[b.status] != null ? CM_STATUS_ORDER[b.status] : 99;
      return oa - ob;
    });
    return groups;
  }

  // -- Rendering --
  _renderSensor(sensor) {
    var st = sensor.state;
    var isErr = (st === "Disconnected" || st === "Not Connected");
    var isWarn = (st === "Partially Connected");
    var dot = isErr ? "error" : isWarn ? "warning" : "ok";
    var proto = sensor.attributes.protocol || "ICMP";
    var port = sensor.attributes.port;
    var service = sensor.attributes.service;
    var label;
    if (service) label = cmEsc(proto) + " - " + cmEsc(service) + " (" + cmEsc(port) + ")";
    else if (port) label = cmEsc(proto) + ":" + cmEsc(port);
    else label = cmEsc(proto);
    var latency = sensor.attributes.latency_ms != null
      ? "<span class='sensor-latency'>" + cmEsc(sensor.attributes.latency_ms) + " ms</span>" : "";
    return "<div class='sensor-row'>" +
      "<span class='dot dot-" + dot + "'></span>" +
      "<span class='sensor-proto'>" + label + "</span>" +
      "<span class='label-" + dot + "'>" + cmEsc(st) + "</span>" +
      latency + "</div>";
  }

  _renderDevice(device) {
    var meta = CM_STATUS_META[device.status] || CM_STATUS_META.Unknown;
    var dt = (this._config && this._config.device_type) || "Network";
    var html = "<div class='device-card card-" + meta.css + "'>" +
      "<div class='device-header'>" +
      "<div class='device-info'>" +
      "<div class='device-name'>" + cmEsc(device.name) + "</div>" +
      "<div class='device-host'>" + cmEsc(device.subtitle) + "</div></div>" +
      "<span class='badge badge-" + meta.css + "'>" + cmEsc(device.status) + "</span></div>";
    if (dt === "Network" && device.sensors.length > 0) {
      html += "<div class='sensor-list'>";
      for (var i = 0; i < device.sensors.length; i++) {
        html += this._renderSensor(device.sensors[i]);
      }
      html += "</div>";
    } else if (dt === "ZigBee" && device.minutesAgo != null) {
      var ago;
      if (device.minutesAgo < 60) ago = device.minutesAgo + " min ago";
      else if (device.minutesAgo < 1440) ago = Math.round(device.minutesAgo / 60) + " hr ago";
      else ago = Math.round(device.minutesAgo / 1440) + " day(s) ago";
      html += "<div class='sensor-list'><div class='sensor-row'>" +
        "<span class='dot dot-" + meta.css + "'></span>" +
        "<span class='sensor-proto'>Last seen: " + cmEsc(ago) + "</span>" +
        "</div></div>";
    }
    html += "</div>";
    return html;
  }

  _styles() {
    return "<style>" +
      "*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }" +
      ".card-content { padding:16px; }" +
      ".group { margin-bottom:16px; }" +
      ".group-header { display:flex; align-items:center; gap:8px; padding:6px 12px; border-radius:6px 6px 0 0; font-size:0.82rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }" +
      ".group-header-error   { background:rgba(244,67,54,.15);  color:var(--error-color,#f44336); }" +
      ".group-header-warning { background:rgba(255,152,0,.15);  color:var(--warning-color,#ff9800); }" +
      ".group-header-ok      { background:rgba(76,175,80,.12);  color:var(--success-color,#4caf50); }" +
      ".group-header-unknown { background:rgba(128,128,128,.12);color:var(--secondary-text-color); }" +
      ".group-count { background:rgba(0,0,0,.12); border-radius:10px; padding:1px 8px; font-size:0.78rem; }" +
      ".device-card { background:var(--card-background-color,#fff); margin-bottom:4px; border-left:4px solid transparent; box-shadow:var(--ha-card-box-shadow,0 1px 4px rgba(0,0,0,.08)); overflow:hidden; }" +
      ".device-card:last-child { margin-bottom:0; border-radius:0 0 6px 6px; }" +
      ".card-error   { border-left-color:var(--error-color,#f44336); }" +
      ".card-warning { border-left-color:var(--warning-color,#ff9800); }" +
      ".card-ok      { border-left-color:var(--success-color,#4caf50); }" +
      ".card-unknown { border-left-color:var(--secondary-text-color); }" +
      ".device-header { display:flex; align-items:center; gap:8px; padding:8px 14px; background:var(--secondary-background-color,rgba(0,0,0,.03)); border-bottom:1px solid var(--divider-color,rgba(0,0,0,.08)); }" +
      ".device-info { flex:1; min-width:0; }" +
      ".device-name { font-size:0.92rem; font-weight:500; }" +
      ".device-host { font-size:0.75rem; color:var(--secondary-text-color); margin-top:1px; }" +
      ".badge { border-radius:20px; padding:2px 10px; font-size:0.73rem; font-weight:600; white-space:nowrap; color:#fff; }" +
      ".badge-error   { background:var(--error-color,#f44336); }" +
      ".badge-warning { background:var(--warning-color,#ff9800); }" +
      ".badge-ok      { background:var(--success-color,#4caf50); }" +
      ".badge-unknown { background:var(--secondary-text-color); }" +
      ".sensor-list { padding:2px 0; }" +
      ".sensor-row { display:flex; align-items:center; padding:5px 14px; gap:10px; border-bottom:1px solid var(--divider-color,rgba(0,0,0,.06)); font-size:0.85rem; }" +
      ".sensor-row:last-child { border-bottom:none; }" +
      ".dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }" +
      ".dot-error   { background:var(--error-color,#f44336); }" +
      ".dot-warning { background:var(--warning-color,#ff9800); }" +
      ".dot-ok      { background:var(--success-color,#4caf50); }" +
      ".dot-unknown { background:var(--secondary-text-color); }" +
      ".sensor-proto { flex:1; color:var(--secondary-text-color); }" +
      ".sensor-latency { font-size:0.78rem; color:var(--secondary-text-color); margin-left:8px; }" +
      ".label-error   { color:var(--error-color,#f44336); font-weight:500; }" +
      ".label-warning { color:var(--warning-color,#ff9800); font-weight:500; }" +
      ".label-ok      { color:var(--success-color,#4caf50); font-weight:500; }" +
      ".label-unknown { color:var(--secondary-text-color); }" +
      ".no-devices { text-align:center; padding:32px 16px; color:var(--secondary-text-color); font-size:0.9rem; }" +
      "</style>";
  }

  _render() {
    if (!this.shadowRoot) return;
    var dt = (this._config && this._config.device_type) || "Network";
    var sf = (this._config && this._config.status_filter) || CM_DEFAULT_STATUS[dt] || "All";
    var allDevices = this._getDevices();
    var filtered = this._filterDevices(allDevices);
    var groups = this._groupDevices(filtered);

    var bodyHtml = "";
    if (filtered.length === 0) {
      bodyHtml = "<div class='no-devices'>No " + cmEsc(dt) + " devices" +
        (sf !== "All" && sf !== "Both" ? " with status '" + cmEsc(sf) + "'" : "") +
        " found.</div>";
    } else {
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var meta = CM_STATUS_META[group.status] || CM_STATUS_META.Unknown;
        bodyHtml += "<div class='group'>" +
          "<div class='group-header group-header-" + meta.css + "'>" +
          "<span>" + meta.icon + "</span>" +
          "<span style='flex:1'>" + cmEsc(meta.label) + "</span>" +
          "<span class='group-count'>" + group.devices.length + "</span></div>";
        for (var d = 0; d < group.devices.length; d++) {
          bodyHtml += this._renderDevice(group.devices[d]);
        }
        bodyHtml += "</div>";
      }
    }

    this.shadowRoot.innerHTML = this._styles() +
      "<ha-card header='" + cmEsc(this._config && this._config.title ? this._config.title : "Connectivity Monitor - " + dt) + "'>" +
      "<div class='card-content'>" + bodyHtml + "</div>" +
      "</ha-card>";
  }
}

customElements.define("connectivity-monitor-card", ConnectivityMonitorCard);
console.log("[CM] element defined OK");

window.customCards = window.customCards || [];
window.customCards.push({
  type: "connectivity-monitor-card",
  name: "Connectivity Monitor",
  description: "Connectivity Monitor card",
});
