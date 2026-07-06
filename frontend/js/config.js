/* Configuracion global del frontend. */
window.UF = {
  API: `${window.location.origin}/api`,
  QUITO: [-0.2200, -78.5125],
  REALTIME_INTERVAL_MS: 5000,
  COLORS: { auto: "#ff4dff", bus: "#00fff0", moto: "#ff8c42", bici: "#7c4dff", pie: "#00ff9d" },
  getAdminKey: () => localStorage.getItem("uf_admin_key") || "",
  setAdminKey: (k) => localStorage.setItem("uf_admin_key", k),
  state: {
    origen: null,
    destino: null,
    modo: "auto",
    realtimeEnabled: true,
    trafficScenario: "real",
  },
};
