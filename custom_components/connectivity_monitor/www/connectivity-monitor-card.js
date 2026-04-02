console.log("[CM] script start");

var CM_DEVICE_TYPES = ["ESP32", "Matter", "Network", "ZigBee"];
var CM_STATUS_OPTIONS = {
  ESP32:    ["Active", "Inactive", "Both"],
  Matter:   ["Active", "Inactive", "Both"],
  ZigBee:   ["Active", "Inactive", "Both"],
  Network:  ["Connected", "Disconnected", "Partially Connected",
             "Disconnected & Partially Connected",
             "Connected & Partially Connected", "All"]
};
var CM_DEFAULT_STATUS = { ESP32: "Both", Matter: "Both", ZigBee: "Both", Network: "All" };

// --- Visual editor ---
class ConnectivityMonitorCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = Object.assign({}, config);
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
      "select { width:100%; padding:8px 12px; border:1px solid var(--divider-color,#e0e0e0); border-radius:4px; background:var(--card-background-color,#fff); color:var(--primary-text-color); font-size:14px; }" +
      "select:focus { outline:none; border-color:var(--primary-color); }" +
      "</style>" +
      "<div class='form'>" +
      "<div><label>Device Type</label>" +
      "<select id='cm_dt'>" + dtOptions + "</select></div>" +
      "<div><label>Status Filter</label>" +
      "<select id='cm_sf'>" + sfOptions + "</select></div>" +
      "</div>";

    var self = this;
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
    if (this.shadowRoot) this._render();
  }
  getCardSize() { return 3; }
  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) this._render();
  }
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this._render();
  }
  _render() {
    var dt = (this._config && this._config.device_type) || "Network";
    var sf = (this._config && this._config.status_filter) || "All";
    this.shadowRoot.innerHTML =
      "<ha-card header='Connectivity Monitor'>" +
      "<div style='padding:16px'>" +
      "<p><b>Device type:</b> " + dt + "</p>" +
      "<p><b>Status filter:</b> " + sf + "</p>" +
      "</div></ha-card>";
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
