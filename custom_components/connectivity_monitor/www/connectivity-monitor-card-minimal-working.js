class ConnectivityMonitorCard extends HTMLElement {
  setConfig(config) {}
  getCardSize() { return 3; }
  static getStubConfig() { return {}; }
  set hass(hass) {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = "<ha-card><div style='padding:16px'>Connectivity Monitor card is working!</div></ha-card>";
  }
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = "<ha-card><div style='padding:16px'>Connectivity Monitor card loading...</div></ha-card>";
  }
}

customElements.define("connectivity-monitor-card", ConnectivityMonitorCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "connectivity-monitor-card",
  name: "Connectivity Monitor",
  description: "Connectivity Monitor card",
});
