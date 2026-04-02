console.log("[CM] script start");

class ConnectivityMonitorCard extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }
  getCardSize() { return 3; }
  static getStubConfig() { return { device_type: "Network", status_filter: "All" }; }
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
