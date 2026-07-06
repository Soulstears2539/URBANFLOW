/* Gestion del mapa Leaflet. */
(function () {
  if (!window.UF) {
    window.UF = {};
  }
  let map, capaRuta, capaParadasBus, marcadorO, marcadorD, capaTrafico, marcadorUsuario, capaVehiculos, capaPoi, capaNearbyRoutes;

  function init() {
    console.log("UF.map.init: initializing map");
    try {
    map = L.map("map", { zoomControl: true }).setView(window.UF.QUITO, 13);
    } catch (err) {
      console.error('UF.map.init error creating Leaflet map:', err);
      throw err;
    }
    map.createPane("bus-stop-pane");
    map.getPane("bus-stop-pane").style.zIndex = 670;
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
    capaRuta = L.layerGroup().addTo(map);
    capaParadasBus = L.layerGroup().addTo(map);
    capaNearbyRoutes = L.layerGroup().addTo(map);
    capaTrafico = L.layerGroup().addTo(map);
    capaVehiculos = L.layerGroup().addTo(map);
    capaPoi = L.layerGroup().addTo(map);
    map.on("click", onMapClick);
    console.log("UF.map.init: map created, layers added");
  }

  let modoClick = "origen";
  function onMapClick(e) {
    const punto = { lat: e.latlng.lat, lon: e.latlng.lng };
    if (modoClick === "origen") {
      setOrigen(punto);
      modoClick = "destino";
    } else {
      setDestino(punto);
      modoClick = "origen";
    }
  }

  function _marker(lat, lon, color, label) {
    return L.circleMarker([lat, lon], {
      radius: 9,
      color: "#fff",
      weight: 2,
      fillColor: color,
      fillOpacity: 1,
    }).bindPopup(label);
  }

  function setOrigen(p, label = "Origen") {
    window.UF.state.origen = p;
    if (marcadorO) map.removeLayer(marcadorO);
    marcadorO = _marker(p.lat, p.lon, "#2ecc71", label).addTo(map);
    map.panTo([p.lat, p.lon]);
  }

  function setDestino(p, label = "Destino") {
    window.UF.state.destino = p;
    if (marcadorD) map.removeLayer(marcadorD);
    marcadorD = _marker(p.lat, p.lon, "#e74c3c", label).addTo(map);
  }

  function setUserLocation(p, label = "Mi ubicacion") {
    if (marcadorUsuario) map.removeLayer(marcadorUsuario);
    marcadorUsuario = L.circleMarker([p.lat, p.lon], {
      radius: 10,
      color: "#fff",
      weight: 3,
      fillColor: "#00d4ff",
      fillOpacity: 0.95,
    }).bindPopup(label).addTo(map);
  }

  function centerOn(p, zoom = 16) {
    map.setView([p.lat, p.lon], zoom);
  }

  function drawBusStops(paradas = []) {
    capaParadasBus.clearLayers();
    const colores = { subida: "#00fff0", bajada: "#ff4dff", intermedia: "#ffd500" };

    function _busIcon(color) {
      return L.divIcon({
        className: "",
        html: `<div class="bus-icon" style="background:${color}">🚌</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 28],
      });
    }

    paradas.forEach((p) => {
      if (typeof p.lat !== "number" || typeof p.lon !== "number") return;
      const tipo = p.tipo || "intermedia";
      const label = tipo === "subida" ? "Subida" : tipo === "bajada" ? "Bajada" : "Parada";
      const color = colores[tipo] || colores.intermedia;
      L.marker([p.lat, p.lon], { icon: _busIcon(color), pane: "bus-stop-pane" })
        .bindPopup(`<b>${label} de bus</b><br>${p.nombre || "Parada"}<br>Orden: ${p.orden || "-"}`)
        .addTo(capaParadasBus);
    });
  }

  function drawNearbyRoutes(rutas = []) {
    capaNearbyRoutes.clearLayers();
    rutas.forEach((ruta) => {
      const stops = (ruta.paradas || []).filter((p) => typeof p.lat === "number" && typeof p.lon === "number");
      const sorted = [...stops].sort((a, b) => (a.sentido || "").localeCompare(b.sentido || "") || (a.orden || 0) - (b.orden || 0));
      const puntos = sorted.map((p) => [p.lat, p.lon]);
      const color = ruta.colour || "#ff4dff";
      if (puntos.length >= 2) {
        L.polyline(puntos, {
          color,
          weight: 4,
          opacity: 0.35,
          dashArray: "8 8",
        })
          .bindPopup(`<strong>${ruta.ref}</strong> · ${ruta.name}<br>${ruta.operator || ""}`)
          .addTo(capaNearbyRoutes);
      }
      const first = sorted[0];
      const last = sorted[sorted.length - 1];
      [first, last].forEach((p) => {
        if (!p) return;
        L.circleMarker([p.lat, p.lon], {
          radius: 5,
          color: "#ffffff",
          weight: 2,
          fillColor: color,
          fillOpacity: 0.9,
        })
          .bindPopup(`<strong>${ruta.ref}</strong> · ${ruta.name}<br>${p.nombre}`)
          .addTo(capaNearbyRoutes);
      });
    });
  }

  function clearNearbyRoutes() {
    capaNearbyRoutes.clearLayers();
  }

  function drawRoute(rutas, modo) {
    capaRuta.clearLayers();
    capaParadasBus.clearLayers();
    const color = window.UF.COLORS[modo] || "#3a86ff";
    rutas.forEach((r, i) => {
      if (i === 0 && r.paradas_bus?.length) {
        drawBusStops(r.paradas_bus);
      }
      if (i === 0 && r.segmentos?.length) {
        r.segmentos.forEach((seg) => {
          const aviso = seg.aproximado ? "<br>Faltan paradas intermedias cargadas para esta linea." : "";
          L.polyline(seg.path, {
            color: seg.tipo === "bus" ? color : "#4ade80",
            weight: seg.tipo === "bus" ? 7 : 4,
            opacity: seg.tipo === "bus" ? 0.95 : 0.75,
            dashArray: seg.tipo === "bus" ? null : "8 8",
          }).bindPopup(
            `<b>${seg.tipo === "bus" ? "Tramo en bus" : "Caminata"}</b><br>Geometria: ${seg.fuente || "ruta"}${aviso}`
          ).addTo(capaRuta);
        });
      } else if (i === 0 && r.trafico_segmentos?.length) {
        const coloresTrafico = { 1: "#2ecc71", 2: "#f39c12", 3: "#e74c3c" };
        r.trafico_segmentos.forEach((seg) => {
          L.polyline(seg.path, {
            color: coloresTrafico[seg.trafico_nivel] || color,
            weight: 7,
            opacity: 0.95,
          }).bindPopup(
            `<b>Tramo</b><br>${seg.trafico_texto}<br>${seg.dist_km} km${seg.zona_referencia ? `<br>${seg.zona_referencia}` : ""}`
          ).addTo(capaRuta);
        });
      } else {
        L.polyline(r.path, {
          color,
          weight: i === 0 ? 6 : 3,
          opacity: i === 0 ? 0.9 : 0.4,
        }).addTo(capaRuta);
      }
    });
    if (rutas[0]) map.fitBounds(L.polyline(rutas[0].path).getBounds(), { padding: [40, 40] });
  }

  function drawTraffic(zonas) {
    capaTrafico.clearLayers();
    const colores = { 1: "#2ecc71", 2: "#f39c12", 3: "#e74c3c" };
    zonas.forEach((z) => {
      L.circle([z.lat, z.lon], {
        radius: 700,
        color: colores[z.nivel_trafico],
        fillColor: colores[z.nivel_trafico],
        fillOpacity: 0.25,
        weight: 1,
      }).bindPopup(
        `<b>${z.nombre}</b><br>Estado ${z.texto || z.nivel_trafico} · ${z.proveedor}`
      ).addTo(capaTrafico);
    });
  }

  function drawVehicles(vehiculos) {
    capaVehiculos.clearLayers();
    vehiculos.forEach((v) => {
      L.circleMarker([v.lat, v.lon], {
        radius: 7,
        color: "#08121c",
        weight: 2,
        fillColor: v.color || "#00d4ff",
        fillOpacity: 1,
      }).bindPopup(
        `<b>${v.route_id}</b><br>${v.route_name}<br>${v.speed_kmh} km/h · ${v.sentido}<br>Ocupacion: ${v.ocupacion}<br>Trafico: ${v.trafico_texto || "Regular"}`
      ).addTo(capaVehiculos);
    });
  }

  function clearVehicles() {
    capaVehiculos.clearLayers();
  }

  function drawPOIs(places = [], source = "SIMULADO") {
    capaPoi.clearLayers();
    const color = source === "REAL" ? "#8bd450" : "#a78bfa";
    const bounds = [];
    places.forEach((place) => {
      if (typeof place.lat !== "number" || typeof place.lng !== "number") return;
      bounds.push([place.lat, place.lng]);
      L.circleMarker([place.lat, place.lng], {
        radius: 8,
        color: "#08121c",
        weight: 2,
        fillColor: color,
        fillOpacity: 0.95,
      }).bindPopup(
        `<b>${place.title || "Lugar"}</b><br>${place.address || ""}<br>${place.types?.join(", ") || ""}<br>${place.rating ? `Rating: ${place.rating}` : "Sin rating"}`
      ).addTo(capaPoi);
    });

    if (bounds.length) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
    }
  }

  function clearPOIs() {
    capaPoi.clearLayers();
  }
  window.UF.map = {
    init,
    setOrigen,
    setDestino,
    setUserLocation,
    centerOn,
    drawRoute,
    drawBusStops,
    drawNearbyRoutes,
    clearNearbyRoutes,
    drawTraffic,
    drawVehicles,
    clearVehicles,
    drawPOIs,
    clearPOIs,
    // expose the internal Leaflet map instance via a getter
    get instance() {
      return map;
    },
  };

})();
