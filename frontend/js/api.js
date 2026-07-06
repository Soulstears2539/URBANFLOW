/* Cliente de la API REST de UrbanFlow. */
(function () {
  const { API } = window.UF;

  async function request(path, { method = "GET", body = null, admin = false } = {}) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    if (admin) headers["X-API-Key"] = window.UF.getAdminKey();
    const res = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : null,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) throw new Error(data.error || "Falta clave admin");
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  async function upload(path, file, fields = {}) {
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(fields).forEach(([key, value]) => fd.append(key, value));
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "X-API-Key": window.UF.getAdminKey() },
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) throw new Error(data.error || "Falta clave admin");
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  async function download(path, filename) {
    const res = await fetch(`${API}${path}`, {
      headers: { "X-API-Key": window.UF.getAdminKey() },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (res.status === 401) throw new Error(data.error || "Falta clave admin");
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  window.UF.api = {
    health: () => request("/health"),
    search: (q, lat, lon) =>
      request(`/search?q=${encodeURIComponent(q)}&lat=${lat}&lon=${lon}`),
    suggestions: (q, lat, lon) =>
      request(`/search/suggestions?q=${encodeURIComponent(q)}&lat=${lat}&lon=${lon}`),
    geocode: (q) => request(`/geocode?q=${encodeURIComponent(q)}`),
    route: (b) => request("/route", { method: "POST", body: b }),
    routeBus: (b) => request("/route/bus", { method: "POST", body: b }),
    trafficMap: (escenario = "real") =>
      request(`/traffic/map?escenario=${encodeURIComponent(escenario)}`),
    realtime: (lat, lon, radio = 700, escenario = "real") =>
      request(`/realtime?lat=${lat}&lon=${lon}&radio=${radio}&escenario=${encodeURIComponent(escenario)}`),
    sources: () => request("/sources/status"),
    mlEstado: () => request("/ml/estado"),
    mlTrain: () => request("/ml/entrenar", { method: "POST", admin: true }),
    mlPredict: (b) => request("/ml/predecir", { method: "POST", body: b }),
    gtfsImport: (url) => request("/gtfs/import", { method: "POST", body: { url }, admin: true }),
    tts: (texto) => request("/tts/speak", { method: "POST", body: { texto } }),
    uploadCsv: (file) => upload("/ml/importar", file),
    transportMatrixTemplate: () => request("/transport/matrix/template"),
    transportMatrix: (compact = false, limit = 25) =>
      request(`/transport/matrix${compact ? `?compact=1&limit=${limit}` : ""}`),
    downloadTransportMatrixExcel: () =>
      download("/transport/matrix/export.xls", "urbanflow_rutas_cargadas.xls"),
    uploadTransportMatrix: (file, reemplazar = false) =>
      upload("/transport/matrix/import", file, { reemplazar: reemplazar ? "1" : "0" }),
    createManualTransportRoute: (body) =>
      request("/transport/matrix/manual", { method: "POST", body }),
    transport: (body) => request("/transport", { method: "POST", body }),
    busDetail: (ref) => request(`/buses/${encodeURIComponent(ref)}`),
    importOsmTransport: (scope = "ecuador") =>
      request(`/transport/osm/import?scope=${encodeURIComponent(scope)}`, { method: "POST", admin: true }),
    
    // SerpAPI - Búsqueda de POI (Puntos de Interés)
    poiSearch: (query, lat, lng, max = 10) =>
      request(`/poi/search?query=${encodeURIComponent(query)}&lat=${lat}&lng=${lng}&max=${max}`),
    poiTypes: () => request("/poi/types"),
    poiNearby: (lat, lng, queries, maxPerQuery = 5) =>
      request("/poi/nearby", {
        method: "POST",
        body: { lat, lng, queries, max_per_query: maxPerQuery },
      }),
  };
})();
