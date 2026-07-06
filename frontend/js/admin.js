/* Logica de la vista de administrador. */
(function () {
  const { api } = window.UF;

  function log(msg, cls = "") {
    const el = document.getElementById("log");
    const line = document.createElement("span");
    line.className = cls;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}\n`;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }

  function showImportOut(msg, cls = "") {
    const out = document.getElementById("import-out");
    out.textContent = msg;
    out.classList.remove("hidden", "success", "error", "warning");
    if (cls) out.classList.add(cls);
  }

  function requireAdminKeyFor(label) {
    if (window.UF.getAdminKey()) return true;
    showImportOut(`${label}: falta guardar la clave admin en la tarjeta de autenticacion.`, "error");
    log(`${label}: falta clave admin`, "err");
    return false;
  }

  async function refreshHealth() {
    try {
      const h = await api.health();
      document.getElementById("health").textContent =
        `Estado: ${h.status}\nRegistros ML: ${h.registros_ml}\nModelo listo: ${h.modelo_listo}\nBuses/Rutas: ${h.buses_quito}`;
      document.getElementById("ml-badge").textContent = h.modelo_listo
        ? "ML: entrenado"
        : "ML: heuristica";
    } catch (e) {
      log(`Health error: ${e.message}`, "err");
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderMatrixSummary(data) {
    const out = document.getElementById("matrix-summary");
    const rutas = data.rutas || [];
    if (!data.total) {
      out.innerHTML = "<strong>No hay rutas cargadas todavia.</strong><span>Sube un Excel de rutas o importa OSM Ecuador.</span>";
      out.classList.remove("hidden");
      return;
    }

    const rows = rutas.map((ruta) => {
      const titulo = [ruta.ref, ruta.name].filter(Boolean).join(" - ") || `Ruta ${ruta.id}`;
      const meta = [
        ruta.operator || "Operador sin nombre",
        `${ruta.n_paradas || 0} paradas`,
        ruta.fuente || "LOCAL",
      ].join(" - ");
      return `<div class="matrix-route-item"><strong>${escapeHtml(titulo)}</strong><span>${escapeHtml(meta)}</span></div>`;
    }).join("");

    out.innerHTML = [
      `<div class="matrix-total"><strong>${data.total}</strong><span>rutas cargadas en UrbanFlow</span></div>`,
      `<div class="matrix-list">${rows}</div>`,
      data.total > rutas.length ? `<small>Mostrando ${rutas.length} primeras rutas. El resto tambien esta guardado.</small>` : "",
    ].join("");
    out.classList.remove("hidden");
  }

  async function refreshMatrixSummary() {
    try {
      const data = await api.transportMatrix(true, 25);
      renderMatrixSummary(data);
      log(`Rutas cargadas visibles: ${data.total}`, "ok");
    } catch (e) {
      log(`Error matriz: ${e.message}`, "err");
    }
  }

  async function downloadMatrixExcel() {
    try {
      await refreshMatrixSummary();
      await api.downloadTransportMatrixExcel();
      log("Excel de rutas descargado", "ok");
    } catch (e) {
      showImportOut(`Error descargando Excel: ${e.message}`, "error");
      log(`Error descargando Excel: ${e.message}`, "err");
    }
  }

  function manualRoutePayload() {
    const stops = document.getElementById("manual-stops").value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    return {
      ciudad: document.getElementById("manual-city").value.trim() || "Quito",
      cooperativa: document.getElementById("manual-operator").value.trim(),
      linea: document.getElementById("manual-line").value.trim(),
      ruta: document.getElementById("manual-route-name").value.trim(),
      sentido: document.getElementById("manual-direction").value,
      intervalo_min: document.getElementById("manual-interval").value,
      flota: document.getElementById("manual-fleet").value,
      horario: document.getElementById("manual-schedule").value.trim(),
      tarifa: document.getElementById("manual-fare").value.trim() || "0.35",
      color: document.getElementById("manual-color").value.trim(),
      paradas: stops,
    };
  }

  function clearManualRouteForm() {
    ["manual-operator", "manual-line", "manual-route-name", "manual-interval", "manual-fleet", "manual-schedule", "manual-color", "manual-stops"]
      .forEach((id) => { document.getElementById(id).value = ""; });
    document.getElementById("manual-city").value = "Quito";
    document.getElementById("manual-direction").value = "ida";
    document.getElementById("manual-fare").value = "0.35";
  }

  function bindUI() {
    document.getElementById("admin-key").value = window.UF.getAdminKey();

    document.getElementById("btn-save-key").onclick = () => {
      window.UF.setAdminKey(document.getElementById("admin-key").value.trim());
      document.getElementById("auth-status").textContent = "Clave admin guardada en este navegador.";
      document.getElementById("auth-status").className = "auth-status success";
      log("Clave admin guardada", "ok");
    };

    document.getElementById("btn-health").onclick = refreshHealth;
    document.getElementById("btn-matrix-refresh").onclick = downloadMatrixExcel;

    document.getElementById("btn-train").onclick = async () => {
      if (!requireAdminKeyFor("Entrenar modelo")) return;
      log("Entrenando modelo...");
      try {
        const r = await api.mlTrain();
        if (r.ok) {
          document.getElementById("ml-metrics").textContent =
            `MAE: ${r.mae_min} min - ${r.registros} registros\nImportancias: ${JSON.stringify(r.importancias)}`;
          document.getElementById("ml-metrics").classList.remove("hidden");
          log("Modelo entrenado", "ok");
          refreshHealth();
        } else {
          log(`No entrenado: ${r.error}`, "err");
        }
      } catch (e) {
        log(`Error: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-predict").onclick = async () => {
      const body = {
        distancia_km: parseFloat(document.getElementById("p-dist").value),
        duracion_base_min: parseFloat(document.getElementById("p-base").value),
        nivel_trafico: parseInt(document.getElementById("p-traf").value, 10) || 1,
      };
      try {
        const r = await api.mlPredict(body);
        const out = document.getElementById("ml-pred");
        out.textContent = `Tiempo estimado: ${r.tiempo_min} min (fuente: ${r.fuente})`;
        out.classList.add("show");
      } catch (e) {
        log(`Error: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-upload").onclick = async () => {
      if (!requireAdminKeyFor("CSV de trafico/ML")) return;
      const file = document.getElementById("csv-file").files[0];
      if (!file) {
        showImportOut("Selecciona un CSV de trafico/ML.", "error");
        return;
      }
      try {
        showImportOut("Subiendo CSV de trafico/ML...", "warning");
        const r = await api.uploadCsv(file);
        showImportOut(`Importadas ${r.importadas} filas`, "success");
        log(`CSV importado: ${r.importadas} filas`, "ok");
        refreshHealth();
      } catch (e) {
        showImportOut(`Error CSV: ${e.message}`, "error");
        log(`Error CSV: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-gtfs").onclick = async () => {
      if (!requireAdminKeyFor("GTFS")) return;
      const url = document.getElementById("gtfs-url").value.trim();
      if (!url) {
        showImportOut("Indica la URL del feed GTFS.", "error");
        return;
      }
      try {
        showImportOut("Importando GTFS...", "warning");
        const r = await api.gtfsImport(url);
        showImportOut(`GTFS: ${r.rutas} rutas, ${r.paradas} paradas (${r.guardadas} guardadas)`, "success");
        log("GTFS importado", "ok");
      } catch (e) {
        showImportOut(`Error GTFS: ${e.message}`, "error");
        log(`Error GTFS: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-matrix-template").onclick = async () => {
      try {
        const tpl = await api.transportMatrixTemplate();
        const out = document.getElementById("matrix-template");
        out.textContent = [
          tpl.columnas.join(","),
          tpl.columnas.map((c) => tpl.ejemplo[c] ?? "").join(","),
        ].join("\n");
        out.classList.remove("hidden");
        log("Plantilla de matriz cargada", "ok");
      } catch (e) {
        showImportOut(`Error plantilla: ${e.message}`, "error");
        log(`Error plantilla: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-matrix-upload").onclick = async () => {
      const file = document.getElementById("matrix-file").files[0];
      const reemplazar = document.getElementById("matrix-replace").checked;
      if (!file) {
        showImportOut("Selecciona primero un Excel de rutas (.xlsx, .xls o CSV).", "error");
        log("Selecciona una matriz Excel/CSV", "err");
        return;
      }
      try {
        showImportOut(`Subiendo ${file.name}. Esto puede tardar si hay paradas nuevas...`, "warning");
        const r = await api.uploadTransportMatrix(file, reemplazar);
        const pendientes = r.sin_coordenadas?.length
          ? ` - ${r.sin_coordenadas.length} paradas sin coordenadas`
          : "";
        showImportOut(`Matriz: ${r.rutas_creadas} rutas y ${r.paradas_creadas} paradas cargadas${pendientes}`, "success");
        log(`Matriz importada: ${r.rutas_creadas} rutas, ${r.paradas_creadas} paradas, ${r.geocodificadas || 0} geocodificadas`, "ok");
        refreshHealth();
        refreshMatrixSummary();
      } catch (e) {
        showImportOut(`Error matriz: ${e.message}`, "error");
        log(`Error matriz: ${e.message}`, "err");
      }
    };

    document.getElementById("matrix-file").onchange = (e) => {
      const file = e.target.files[0];
      document.getElementById("matrix-file-name").textContent = file
        ? `Archivo listo: ${file.name}`
        : "Puedes subir el Excel descargado y editado: .xlsx, .xls o CSV.";
    };

    document.getElementById("btn-manual-route").onclick = async () => {
      const body = manualRoutePayload();
      if (!body.cooperativa || !body.linea) {
        showImportOut("Completa cooperativa y linea para guardar la ruta manual.", "error");
        return;
      }
      if (body.paradas.length < 2) {
        showImportOut("Agrega al menos dos paradas, una por linea.", "error");
        return;
      }
      try {
        showImportOut("Guardando ruta manual...", "warning");
        const r = await api.createManualTransportRoute(body);
        const pendientes = r.sin_coordenadas?.length
          ? ` - ${r.sin_coordenadas.length} paradas sin coordenadas`
          : "";
        showImportOut(`Ruta manual guardada: ${r.rutas_creadas} ruta y ${r.paradas_creadas} paradas${pendientes}`, "success");
        log(`Ruta manual guardada: ${body.linea}`, "ok");
        clearManualRouteForm();
        refreshHealth();
        refreshMatrixSummary();
      } catch (e) {
        showImportOut(`Error ruta manual: ${e.message}`, "error");
        log(`Error ruta manual: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-osm-import").onclick = async () => {
      if (!requireAdminKeyFor("Importar OSM")) return;
      try {
        showImportOut("Buscando rutas OSM Ecuador...", "warning");
        log("Buscando rutas de Quito, Guayaquil, Cuenca y Riobamba en OpenStreetMap...");
        const r = await api.importOsmTransport("ecuador");
        showImportOut(`OSM: ${r.rutas_creadas} rutas y ${r.paradas_creadas} paradas cargadas`, "success");
        log(`OSM importado: ${r.rutas_creadas}/${r.rutas_osm_encontradas} rutas, ${r.paradas_creadas} paradas`, "ok");
        refreshHealth();
        refreshMatrixSummary();
      } catch (e) {
        showImportOut(`Error OSM: ${e.message}`, "error");
        log(`Error OSM: ${e.message}`, "err");
      }
    };

    document.getElementById("btn-sources").onclick = async () => {
      try {
        const s = await api.sources();
        document.getElementById("sources-out").textContent =
          Object.entries(s)
            .filter(([k]) => k !== "timestamp")
            .map(([k, v]) => `${k}: ${v.estado}${v.latencia_ms ? " (" + v.latencia_ms + "ms)" : ""}`)
            .join("\n");
        log("Estado de fuentes actualizado", "ok");
      } catch (e) {
        log(`Error: ${e.message}`, "err");
      }
    };

    refreshMatrixSummary();
  }

  window.UF.admin = { bindUI, refreshHealth, refreshMatrixSummary, log };
})();
