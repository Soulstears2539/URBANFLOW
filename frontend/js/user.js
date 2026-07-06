/* Logica de la vista de usuario: busqueda, autocompletado, rutas y tiempo real. */
(function () {
  const { api, map } = window.UF;
  let ultimosPasos = [];
  let ttsPlaying = false;
  let ttsIndex = 0;
  let ttsUtterance = null;
  let ubicacionSolicitada = false;
  let realtimeTimer = null;

  function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("error", "warning", "success");
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2600);
  }

  async function loadTransportStops(limitRoutes = 200) {
    try {
      const data = await api.transportMatrix(false);
      const rutas = data.rutas || [];
      const stops = [];
      rutas.slice(0, limitRoutes).forEach((ruta) => {
        (ruta.paradas || []).forEach((p) => {
          if (typeof p.lat !== 'number' || typeof p.lon !== 'number') return;
          stops.push({ nombre: p.nombre, lat: p.lat, lon: p.lon, tipo: 'intermedia', orden: p.orden });
        });
      });
      if (stops.length) map.drawBusStops(stops);
      console.log(`Cargadas ${stops.length} paradas desde ${Math.min(rutas.length, limitRoutes)} rutas`);
    } catch (e) {
      console.error('Error cargando paradas de transporte:', e);
    }
  }

  function toastTipo(msg, tipo) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("error", "warning", "success");
    if (tipo) el.classList.add(tipo);
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2600);
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...a), ms);
    };
  }

  function getInput(id) {
    return document.getElementById(id);
  }

  function getInputValue(id) {
    return getInput(id)?.value.trim() || "";
  }

  function setHidden(id, hidden) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle("hidden", hidden);
  }

  function getSearchReference() {
    const ubicacionRef = window.UF.state.userLocation;
    return ubicacionRef ? [ubicacionRef.lat, ubicacionRef.lon] : window.UF.QUITO;
  }

  function getRealtimeReference() {
    if (window.UF.state.userLocation) return window.UF.state.userLocation;
    if (window.UF.state.origen) return window.UF.state.origen;
    const [lat, lon] = window.UF.QUITO;
    return { lat, lon };
  }

  function updateInputValue(id, value) {
    const input = getInput(id);
    if (input) input.value = value;
  }

  function setSelectedPoint(slot, punto, label) {
    window.UF.state[slot] = punto;
    window.UF.state[`${slot}Label`] = label;
    const inputId = slot === "origen" ? "origen" : "destino";
    updateInputValue(inputId, label);
    if (slot === "origen") {
      map.setOrigen(punto, label);
    } else {
      map.setDestino(punto, label);
    }
  }

  function clearSelectedPoint(slot) {
    window.UF.state[slot] = null;
    window.UF.state[`${slot}Label`] = "";
  }

  function syncSlotWithInput(slot) {
    const inputId = slot === "origen" ? "origen" : "destino";
    const currentValue = getInputValue(inputId);
    const savedLabel = window.UF.state[`${slot}Label`] || "";
    if (!currentValue) {
      clearSelectedPoint(slot);
      return;
    }
    if (savedLabel && currentValue === savedLabel) return;
    clearSelectedPoint(slot);
  }

  function getGeolocationErrorMessage(err) {
    if (!window.isSecureContext) {
      return "La ubicacion del navegador solo funciona en HTTPS o en localhost. Abre UrbanFlow en 127.0.0.1 o publica la app con HTTPS";
    }
    if (!err) return "No se pudo obtener la ubicacion";
    if (err.code === 1) return "Permiso de ubicacion denegado";
    if (err.code === 2) return "Ubicacion no disponible";
    if (err.code === 3) return "Tiempo de espera agotado al detectar la ubicacion";
    return "No se pudo obtener la ubicacion";
  }

  function renderRealtimeSummary(data) {
    const box = document.getElementById("traffic-info");
    const out = document.getElementById("traffic-summary");
    box.hidden = false;
    out.innerHTML = [
      `<strong>Estado:</strong> ${data.trafico.texto} (${data.trafico.proveedor})`,
      `<strong>Escenario:</strong> ${data.resumen.escenario || "real"}`,
      `<strong>Zona:</strong> ${data.trafico.zona_referencia || "Quito"}`,
      `<strong>Velocidad actual:</strong> ${data.trafico.velocidad_actual_kmh} km/h`,
      `<strong>Vehiculos activos:</strong> ${data.resumen.vehiculos_activos}`,
      `<strong>Paradas cercanas:</strong> ${data.resumen.paradas_cercanas}`,
      `<strong>Actualizado:</strong> ${new Date(data.timestamp).toLocaleTimeString()}`,
    ].join("<br>");
  }

  async function fetchRealtime() {
    if (!window.UF.state.realtimeEnabled) return;
    const ref = getRealtimeReference();
    try {
      const data = await api.realtime(ref.lat, ref.lon, 700, window.UF.state.trafficScenario);
      map.drawVehicles(data.vehiculos || []);
      renderRealtimeSummary(data);
    } catch (_e) {
      map.clearVehicles();
    }
  }

  function startRealtime() {
    if (realtimeTimer) clearInterval(realtimeTimer);
    fetchRealtime();
    realtimeTimer = setInterval(fetchRealtime, window.UF.REALTIME_INTERVAL_MS);
  }

  function stopRealtime() {
    if (realtimeTimer) clearInterval(realtimeTimer);
    realtimeTimer = null;
    map.clearVehicles();
    document.getElementById("traffic-info").hidden = true;
  }

  function toggleRealtime() {
    window.UF.state.realtimeEnabled = !window.UF.state.realtimeEnabled;
    const btn = document.getElementById("btn-traffic-toggle");
    if (window.UF.state.realtimeEnabled) {
      btn.title = "Pausar simulacion en vivo";
      startRealtime();
      toastTipo("Simulacion en tiempo real activada", "success");
    } else {
      btn.title = "Activar simulacion en vivo";
      stopRealtime();
      toastTipo("Simulacion en tiempo real pausada", "warning");
    }
  }

  function setTrafficScenario(escenario) {
    window.UF.state.trafficScenario = escenario;
    document.querySelectorAll(".traffic-chip").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.escenario === escenario);
    });
    loadTraffic();
    if (window.UF.state.realtimeEnabled) fetchRealtime();
    toastTipo(`Escenario de trafico: ${escenario}`, "success");
  }

  function solicitarUbicacion({ centrar = true, silent = false } = {}) {
    if (!window.isSecureContext) {
      if (!silent) toastTipo(getGeolocationErrorMessage(), "warning");
      return;
    }

    if (!navigator.geolocation) {
      if (!silent) toastTipo("Tu navegador no soporta geolocalizacion", "warning");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const punto = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        map.setUserLocation(punto, "Mi ubicacion actual");
        setSelectedPoint("origen", punto, "Mi ubicacion actual");
        if (centrar) map.centerOn(punto, 16);
        window.UF.state.userLocation = punto;
        if (window.UF.state.realtimeEnabled) fetchRealtime();
        if (!silent) toastTipo("Ubicacion detectada automaticamente", "success");
      },
      (err) => {
        if (!silent) toastTipo(getGeolocationErrorMessage(err), "error");
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 30000,
      }
    );
  }

  function intentarUbicacionAutomatica() {
    if (ubicacionSolicitada) return;
    ubicacionSolicitada = true;
    solicitarUbicacion({ centrar: false, silent: true });
  }

  async function resolverTextoAPunto(query) {
    const limpio = query.trim();
    if (!limpio) return null;
    const [lat, lon] = getSearchReference();
    const resp = await api.search(limpio, lat, lon);
    const primero = resp.resultados?.[0];
    if (!primero) return null;
    return {
      punto: { lat: primero.lat, lon: primero.lon },
      label: primero.nombre || primero.direccion_corta || limpio,
    };
  }

  async function asegurarPunto(slot) {
    syncSlotWithInput(slot);
    if (window.UF.state[slot]) return true;

    const inputId = slot === "origen" ? "origen" : "destino";
    const escrito = getInputValue(inputId);
    if (!escrito) return false;

    try {
      const resuelto = await resolverTextoAPunto(escrito);
      if (!resuelto) return false;
      setSelectedPoint(slot, resuelto.punto, resuelto.label);
      return true;
    } catch (_e) {
      return false;
    }
  }

  function attachAutocomplete(inputId, listId, slot) {
    const input = getInput(inputId);
    const list = getInput(listId);
    const run = debounce(async () => {
      const q = input.value.trim();
      syncSlotWithInput(slot);
      if (q.length < 3) {
        list.innerHTML = "";
        return;
      }
      const [lat, lon] = getSearchReference();
      try {
        const { sugerencias } = await api.suggestions(q, lat, lon);
        list.innerHTML = "";
        sugerencias.forEach((s) => {
          const li = document.createElement("li");
          li.textContent = `${s.nombre} · ${s.direccion_corta || ""}`;
          li.onclick = () => {
            list.innerHTML = "";
            setSelectedPoint(slot, { lat: s.lat, lon: s.lon }, s.nombre);
          };
          list.appendChild(li);
        });
      } catch (_e) {
        list.innerHTML = "";
      }
    }, 280);

    input.addEventListener("input", run);
    input.addEventListener("change", () => syncSlotWithInput(slot));
    input.addEventListener("blur", () => {
      setTimeout(() => {
        list.innerHTML = "";
      }, 120);
    });
  }

  async function calcularRuta() {
    const origenOk = await asegurarPunto("origen");
    const destinoOk = await asegurarPunto("destino");
    const { origen, destino, modo } = window.UF.state;

    if (!origenOk || !destinoOk || !origen || !destino) {
      toast("Selecciona un origen y un destino validos");
      return;
    }

    const body = {
      olat: origen.lat,
      olon: origen.lon,
      dlat: destino.lat,
      dlon: destino.lon,
      modo,
      escenario: window.UF.state.trafficScenario,
    };
    const block = document.getElementById("resultado-block");
    try {
      if (modo === "bus") {
        const r = await api.routeBus(body);
        if (!r.ok) {
          map.drawRoute([], "bus");
          drawBusSuggestionStops(r);
          toast(r.mensaje || "Sin linea directa");
          renderBusAlternativas(r);
          block.hidden = false;
          await loadNearbyTransportRoutes();
          return;
        }
        map.drawRoute([{ path: r.polyline, segmentos: r.segmentos, paradas_bus: r.paradas_bus }], "bus");
        renderPasosBus(r);
      } else {
        const r = await api.route(body);
        map.drawRoute(r.rutas, modo);
        renderRuta(r.rutas[0]);
      }
      block.hidden = false;
      await loadNearbyTransportRoutes();
    } catch (e) {
      toast(`Error: ${e.message}`);
    }
  }

  function drawBusSuggestionStops(r) {
    const sugerencias = r.sugerencias || {};
    const seen = new Set();
    const paradas = [];
    function addStop(stop, tipo) {
      if (!stop || typeof stop.lat !== "number" || typeof stop.lon !== "number") return;
      const key = `${stop.nombre}-${stop.lat.toFixed(5)}-${stop.lon.toFixed(5)}`;
      if (seen.has(key)) return;
      seen.add(key);
      paradas.push({
        nombre: stop.nombre,
        lat: stop.lat,
        lon: stop.lon,
        tipo,
        orden: paradas.length + 1,
      });
    }
    (sugerencias.directas || []).forEach((linea) => {
      addStop(linea.parada_origen, "subida");
      addStop(linea.parada_destino, "bajada");
    });
    (sugerencias.orig_solo || []).slice(0, 15).forEach((linea) => addStop(linea.parada_origen, "subida"));
    (sugerencias.dest_solo || []).slice(0, 15).forEach((linea) => addStop(linea.parada_destino, "bajada"));
    if (paradas.length) map.drawBusStops(paradas);
  }

  function renderRuta(ruta) {
    const traf = ruta.trafico_texto || { 1: "Bueno", 2: "Regular", 3: "Malo" }[ruta.trafico_nivel] || "";
    document.getElementById("resumen-ruta").innerHTML =
      `${ruta.dur_min} min · ${ruta.dist_km} km · ${traf}`;
    const cont = document.getElementById("pasos");
    cont.innerHTML = "";
    ultimosPasos = [];
    (ruta.trafico_segmentos || []).forEach((seg, idx) => {
      const div = document.createElement("div");
      div.className = "paso";
      div.innerHTML = `Tramo ${idx + 1}: trafico ${seg.trafico_texto} <small>${seg.dist_km} km · ${seg.zona_referencia || "Quito"}</small>`;
      cont.appendChild(div);
    });
    ruta.steps.slice(0, 25).forEach((s, idx) => {
      ultimosPasos.push(s.instruccion);
      const div = document.createElement("div");
      div.className = "paso";
      div.dataset.step = idx;
      div.innerHTML = `${s.icono} ${s.instruccion} <small>${s.dist_m} m</small>`;
      cont.appendChild(div);
    });
    document.getElementById("btn-tts").hidden = ultimosPasos.length === 0;
    // Auto-open fullscreen panel
    setTimeout(() => openFullScreenInstructions(), 300);
  }

  function renderPasosBus(r) {
    document.getElementById("resumen-ruta").innerHTML =
      `Linea ${r.linea} · ${r.duracion_total_min} min · ${(r.distancia_total_m / 1000).toFixed(1)} km`;
    const cont = document.getElementById("pasos");
    cont.innerHTML = "";
    ultimosPasos = [];
    if (r.mensaje_geometria) {
      const aviso = document.createElement("div");
      aviso.className = "paso";
      aviso.innerHTML = `<strong>Nota:</strong> ${r.mensaje_geometria}`;
      cont.appendChild(aviso);
    }
    r.pasos.forEach((p, idx) => {
      ultimosPasos.push(p.instruccion);
      const div = document.createElement("div");
      div.className = "paso";
      div.dataset.step = idx;
      const icono = p.tipo === "bus" ? "🚌" : "🚶";
      div.innerHTML = `${icono} ${p.instruccion} <small>${p.distancia_m} m</small>`;
      cont.appendChild(div);
    });
    document.getElementById("btn-tts").hidden = false;
    // Auto-open fullscreen panel
    setTimeout(() => openFullScreenInstructions(), 300);
  }

  function renderBusAlternativas(r) {
    document.getElementById("resumen-ruta").innerHTML = r.mensaje || "Sin linea directa";
    const cont = document.getElementById("pasos");
    cont.innerHTML = "";
    ultimosPasos = [];

    const sugerencias = r.sugerencias || {};
    (sugerencias.transbordos || []).slice(0, 3).forEach((t) => {
      const div = document.createElement("div");
      div.className = "paso";
      div.innerHTML = `Transbordo sugerido: ${t.primera_linea.ref} -> ${t.segunda_linea.ref}<small>${t.mensaje}</small>`;
      cont.appendChild(div);
    });

    [
      ["Cerca de tu origen", sugerencias.orig_solo || []],
      ["Cerca de tu destino", sugerencias.dest_solo || []],
    ].forEach(([titulo, lineas]) => {
      if (!lineas.length) return;
      const header = document.createElement("div");
      header.className = "paso";
      header.innerHTML = `<strong>${titulo}</strong>`;
      cont.appendChild(header);
      lineas.slice(0, 5).forEach((linea) => {
        const div = document.createElement("div");
        div.className = "paso";
        div.innerHTML = `${linea.ref} · ${linea.operator}<small>${linea.name} · ${linea.frecuencia || "frecuencia no registrada"} · ${linea.fuente}</small>`;
        cont.appendChild(div);
      });
    });

    if (!cont.children.length) {
      const div = document.createElement("div");
      div.className = "paso";
      div.textContent = "Aun no hay cooperativas cercanas cargadas para esta zona. Sube una matriz con paradas y coordenadas.";
      cont.appendChild(div);
    }
    document.getElementById("btn-tts").hidden = true;
  }

  // --- TTS helpers (client-side) ---
  function clearStepHighlight() {
    document.querySelectorAll('#pasos .paso.active, #fullscreen-steps .paso.active').forEach((el) => el.classList.remove('active'));
  }

  function highlightStep(i) {
    clearStepHighlight();
    const sel = `div.paso[data-step='${i}']`;
    const el1 = document.querySelector(`#pasos ${sel}`);
    const el2 = document.querySelector(`#fullscreen-steps ${sel}`);
    if (el1) el1.classList.add('active');
    if (el2) {
      el2.classList.add('active');
      // ensure visible in overlay
      el2.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function speakStepsSequentially(steps = [], opts = {}) {
    const { onStep = () => {}, onEnd = () => {} } = opts;
    if (!('speechSynthesis' in window)) {
      onEnd();
      return;
    }
    window.speechSynthesis.cancel();
    let index = 0;
    function speakNext() {
      if (index >= steps.length) {
        onEnd();
        return;
      }
      const text = steps[index];
      onStep(index);
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'es-ES';
      u.rate = 1.0;
      u.onend = () => { index += 1; speakNext(); };
      u.onerror = () => { onEnd(); };
      window.speechSynthesis.speak(u);
    }
    speakNext();
  }

  async function loadNearbyTransportRoutes() {
    const { origen, destino } = window.UF.state;
    if (!origen || !destino) {
      map.clearNearbyRoutes();
      return;
    }
    try {
      const transporte = await api.transport({
        olat: origen.lat,
        olon: origen.lon,
        dlat: destino.lat,
        dlon: destino.lon,
        radio_m: 900,
      });
      const refs = new Set();
      const candidates = [];
      ["directas", "orig_solo", "dest_solo"].forEach((key) => {
        (transporte[key] || []).slice(0, 5).forEach((linea) => {
          if (!linea?.ref || refs.has(linea.ref)) return;
          refs.add(linea.ref);
          candidates.push(linea.ref);
        });
      });
      if (!candidates.length) {
        map.clearNearbyRoutes();
        return;
      }
      const rutas = [];
      for (const ref of candidates.slice(0, 6)) {
        try {
          const detalle = await api.busDetail(ref);
          if (detalle) rutas.push(detalle);
        } catch (_e) {
          // Ignorar errores de detalle de ruta.
        }
      }
      if (rutas.length) {
        map.drawNearbyRoutes(rutas);
      } else {
        map.clearNearbyRoutes();
      }
    } catch (e) {
      console.error("Error cargando rutas cercanas:", e);
      map.clearNearbyRoutes();
    }
  }

  function renderPOIStatus(result, query) {
    const status = document.getElementById("poi-status");
    if (!status) return;
    const isReal = result.fuente === "REAL";
    status.classList.remove("real", "simulated");
    status.classList.add(isReal ? "real" : "simulated");
    status.innerHTML = isReal
      ? `Fuente real activa para <strong>${query}</strong>. Se pintaron ${result.count} lugares en el mapa.`
      : `SerpApi respondio en modo simulado para <strong>${query}</strong>. Si me pasas una clave valida, lo dejamos con datos reales de Google Maps.`;
  }

  function renderPOIResults(results, source) {
    const container = document.getElementById("poi-results");
    container.innerHTML = "";
    results.slice(0, 15).forEach((place) => {
      const item = document.createElement("div");
      item.className = "poi-result-item";
      const ratingStr = place.rating ? `Rating ${place.rating}${place.reviews ? ` (${place.reviews})` : ""}` : "sin rating";
      const distStr = place.distance_km !== null ? ` · ${place.distance_km} km` : "";
      const sourceLabel = source === "REAL" ? "Google Maps" : "Simulado";
      item.innerHTML = `
        <div class="poi-title">${place.title}</div>
        <div class="poi-meta">
          <span>${place.types?.join(", ") || "Lugar"}</span>
          <span class="poi-rating">${ratingStr}</span>
        </div>
        <div class="poi-address">${place.address}</div>
        <small style="color: var(--text-light);">${sourceLabel}</small>
        ${place.phone ? `<small style="color: var(--text-light);">Tel: ${place.phone}</small>` : ""}
        ${distStr}
      `;

      item.addEventListener("click", () => {
        if (place.lat && place.lng) {
          setSelectedPoint("destino", { lat: place.lat, lon: place.lng }, place.title);
          map.centerOn({ lat: place.lat, lon: place.lng }, 16);
          toast(`${place.title} establecido como destino`);
          setHidden("poi-results", true);
          const poiInput = document.getElementById("poi-query");
          if (poiInput) poiInput.value = "";
        }
      });

      container.appendChild(item);
    });
  }

  function bindPOISearch() {
    const btnPoi = document.getElementById("btn-poi-search");
    const inputPoi = document.getElementById("poi-query");
    const resultsPoi = document.getElementById("poi-results");
    const statusPoi = document.getElementById("poi-status");
    if (!btnPoi || !inputPoi) return;

    btnPoi.onclick = async () => {
      const query = inputPoi.value.trim();
      if (!query) {
        toast("Ingresa un tipo de lugar (ej: Coffee, Restaurant)");
        return;
      }

      const ref = getRealtimeReference();
      btnPoi.disabled = true;
      btnPoi.textContent = "Buscando...";

      try {
        const result = await api.poiSearch(query, ref.lat, ref.lon, 12);
        if (!result.success || !result.results.length) {
          toast("No se encontraron resultados");
          resultsPoi.innerHTML = "";
          if (statusPoi) statusPoi.innerHTML = "";
          setHidden("poi-results", true);
          setHidden("poi-status", true);
          map.clearPOIs();
          return;
        }

        renderPOIResults(result.results, result.fuente);
        renderPOIStatus(result, query);
        map.drawPOIs(result.results, result.fuente);
        setHidden("poi-results", false);
        setHidden("poi-status", false);
        toastTipo(
          `${result.count} lugares encontrados (${result.fuente === "REAL" ? "datos reales" : "simulados"})`,
          result.fuente === "REAL" ? "success" : "warning"
        );
      } catch (e) {
        toast(`Error: ${e.message}`);
        if (statusPoi) statusPoi.innerHTML = "";
        setHidden("poi-results", true);
        setHidden("poi-status", true);
        map.clearPOIs();
      } finally {
        btnPoi.disabled = false;
        btnPoi.textContent = "Buscar";
      }
    };

    inputPoi.addEventListener("keypress", (e) => {
      if (e.key === "Enter") btnPoi.click();
    });
  }

  function bindUI() {
    document.getElementById("modos").addEventListener("click", (e) => {
      const btn = e.target.closest(".mode");
      if (!btn) return;
      document.querySelectorAll(".mode").forEach((m) => m.classList.remove("active"));
      btn.classList.add("active");
      window.UF.state.modo = btn.dataset.modo;
    });

    document.getElementById("btn-ruta").onclick = calcularRuta;
    document.getElementById("btn-gps").onclick = () => solicitarUbicacion({ centrar: true, silent: false });
    document.getElementById("btn-locate").onclick = () => solicitarUbicacion({ centrar: true, silent: false });
    document.getElementById("btn-traffic-toggle").onclick = toggleRealtime;
    const btnTts = document.getElementById("btn-tts");
    const fsBtnTts = document.getElementById("fs-btn-tts");
    
    function toggleTTS() {
      if (!ultimosPasos.length) return;
      if ('speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined') {
        if (ttsPlaying) {
          window.speechSynthesis.cancel();
          ttsPlaying = false;
          ttsIndex = 0;
          btnTts.textContent = '🎧 Escuchar';
          if (fsBtnTts) fsBtnTts.textContent = '🎧';
          clearStepHighlight();
          return;
        }
        ttsPlaying = true;
        btnTts.textContent = '⏹️ Detener';
        if (fsBtnTts) fsBtnTts.textContent = '⏹️';
        speakStepsSequentially(ultimosPasos, {
          onStep: (i) => highlightStep(i),
          onEnd: () => { 
            ttsPlaying = false; 
            ttsIndex = 0; 
            btnTts.textContent = '🎧 Escuchar'; 
            if (fsBtnTts) fsBtnTts.textContent = '🎧';
            clearStepHighlight(); 
          }
        });
      } else {
        api.tts(ultimosPasos.join('. ')).catch(() => toast('No fue posible reproducir audio'));
      }
    }
    
    document.getElementById("btn-tts").onclick = toggleTTS;
    if (fsBtnTts) fsBtnTts.onclick = toggleTTS;

    attachAutocomplete("origen", "sug-origen", "origen");
    attachAutocomplete("destino", "sug-destino", "destino");
    document.getElementById("traffic-sim").addEventListener("click", (e) => {
      const btn = e.target.closest(".traffic-chip");
      if (!btn) return;
      setTrafficScenario(btn.dataset.escenario);
    });

    bindPOISearch();
    intentarUbicacionAutomatica();
    // Add fullscreen instructions button to result-actions if not present
    const actions = document.querySelector('.result-actions');
    if (actions && !document.getElementById('btn-fullscreen-steps')) {
      const btnFull = document.createElement('button');
      btnFull.id = 'btn-fullscreen-steps';
      btnFull.className = 'btn-secondary';
      btnFull.title = 'Ver instrucciones en ventana flotante';
      btnFull.textContent = '📺 Pantalla';
      btnFull.onclick = toggleFullScreenInstructions;
      actions.insertBefore(btnFull, actions.firstChild);
    }
  }

  // Fullscreen instructions panel
  function openFullScreenInstructions() {
    const panel = document.getElementById('fullscreen-steps');
    if (!panel) return;
    const content = panel.querySelector('.fs-content');
    const fsBtnTts = document.getElementById('fs-btn-tts');
    const pasos = document.getElementById('pasos');
    content.innerHTML = pasos ? pasos.innerHTML : '<div class="paso">Sin instrucciones</div>';
    if (fsBtnTts) fsBtnTts.hidden = ultimosPasos.length === 0;
    panel.classList.remove('hidden');
    if (ttsPlaying && fsBtnTts) fsBtnTts.textContent = '⏹️';
    else if (fsBtnTts) fsBtnTts.textContent = '🎧';
  }

  function closeFullScreenInstructions() {
    const panel = document.getElementById('fullscreen-steps');
    if (!panel) return;
    panel.classList.add('hidden');
  }

  function toggleFullScreenInstructions() {
    const panel = document.getElementById('fullscreen-steps');
    if (!panel) return;
    if (panel.classList.contains('hidden')) {
      openFullScreenInstructions();
    } else {
      closeFullScreenInstructions();
    }
  }

  async function loadTraffic() {
    try {
      const { zonas } = await api.trafficMap(window.UF.state.trafficScenario);
      map.drawTraffic(zonas);
    } catch (_e) {
      // opcional
    }
  }

  window.UF.user = {
    bindUI,
    loadTraffic,
    startRealtime,
    stopRealtime,
    toast,
    solicitarUbicacion,
  };
})();
