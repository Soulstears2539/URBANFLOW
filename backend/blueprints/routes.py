"""Endpoints de cálculo de rutas multimodales."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..external import osrm, overpass
from ..services import recorder, routing
from ..services.routing import haversine_km

bp = Blueprint("routes", __name__, url_prefix="/api")


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _req_coords(data: dict):
    try:
        return (float(data["olat"]), float(data["olon"]),
                float(data["dlat"]), float(data["dlon"]))
    except (KeyError, TypeError, ValueError):
        return None


@bp.post("/route")
def route():
    data = _body()
    coords = _req_coords(data)
    if not coords:
        return jsonify({"error": "Se requieren olat, olon, dlat, dlon"}), 400
    olat, olon, dlat, dlon = coords
    modo = data.get("modo", "auto")
    escenario = data.get("escenario", "real")
    rutas = routing.calcular_rutas(olat, olon, dlat, dlon, modo, escenario)
    if not rutas:
        return jsonify({"error": "No se pudo calcular la ruta"}), 502

    mejor = rutas[0]
    recorder.registrar_ruta({
        "olat": olat, "olon": olon, "dlat": dlat, "dlon": dlon,
        "distancia_km": mejor["dist_km"],
        "duracion_base_min": mejor["dur_min_original"],
        "duracion_trafico_min": mejor["dur_min"],
        "duracion_estimacion_min": mejor["dur_min"],
        "retraso_trafico_min": round(mejor["dur_min"] - mejor["dur_min_original"], 1),
        "nivel_trafico": mejor["trafico_nivel"],
        "fuente_ruta": mejor["fuente"],
        "fuente_trafico": mejor["fuente_trafico"],
        "es_dato_real": not mejor["trafico_simulado"],
        "tiempo_real_min": mejor["dur_min"],
    })
    return jsonify({"rutas": rutas, "total": len(rutas), "modo": modo})


@bp.post("/osrm/route")
def osrm_route():
    data = _body()
    coords = _req_coords(data)
    if not coords:
        return jsonify({"error": "Se requieren olat, olon, dlat, dlon"}), 400
    olat, olon, dlat, dlon = coords
    rutas = osrm.fetch_osrm_route(olat, olon, dlat, dlon,
                                  data.get("modo", "auto"),
                                  int(data.get("alternativas", 3)))
    return jsonify({"rutas": rutas, "total": len(rutas)})


@bp.post("/pois-en-ruta")
def pois_en_ruta():
    data = _body()
    path = data.get("path") or []
    radio_m = int(data.get("radio_m", 150))
    if len(path) < 2:
        return jsonify({"error": "Se requiere 'path' con al menos 2 puntos"}), 400

    # Muestrea puntos a lo largo de la ruta para no saturar Overpass.
    muestra = path[:: max(1, len(path) // 6)]
    vistos, pois = set(), []
    for lat, lon in muestra:
        for p in overpass.fetch_pois(lat, lon, radio_m):
            clave = (round(p["lat"], 5), round(p["lon"], 5))
            if clave in vistos:
                continue
            vistos.add(clave)
            p["dist_ruta_m"] = round(haversine_km(lat, lon, p["lat"], p["lon"]) * 1000)
            pois.append(p)
    return jsonify({"pois": pois, "total": len(pois)})


@bp.get("/nearby")
def nearby():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Se requieren lat y lon"}), 400
    cat = request.args.get("cat", "all")
    mapa = {
        "restaurant": ["amenity=restaurant"],
        "hotel": ["tourism=hotel"],
        "museum": ["tourism=museum"],
        "pharmacy": ["amenity=pharmacy"],
        "all": ["amenity=restaurant", "amenity=pharmacy", "shop=supermarket"],
    }
    pois = overpass.fetch_pois(lat, lon, 600, mapa.get(cat, mapa["all"]))
    return jsonify({"pois": pois, "total": len(pois)})
