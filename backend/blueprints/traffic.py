"""Endpoints de tráfico y realtime."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from ..external import overpass
from ..services import recorder, traffic

bp = Blueprint("traffic", __name__, url_prefix="/api")


def _coords():
    try:
        return float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return None


def _escenario():
    return request.args.get("escenario", "auto")


@bp.get("/traffic")
def trafico_punto():
    c = _coords()
    if not c:
        return jsonify({"error": "Se requieren lat y lon"}), 400
    flujo = traffic.flujo_punto(*c, escenario=_escenario())
    return jsonify({
        "nivel": flujo["nivel_trafico"],
        "texto": flujo["texto"],
        "simulado": not flujo["es_dato_real"],
        "velocidad_actual_kmh": flujo["velocidad_actual_kmh"],
        "proveedor": flujo["proveedor"],
    })


@bp.get("/traffic/map")
def trafico_mapa():
    mapa = traffic.mapa_trafico(_escenario())
    recorder.registrar_busqueda(
        f"traffic_map:nivel_prom={mapa['nivel_promedio']}", mapa["fuente"]
    )
    return jsonify(mapa)


@bp.get("/realtime")
def realtime():
    c = _coords() or (-0.2200, -78.5125)  # centro de Quito por defecto
    lat, lon = c
    radio = int(request.args.get("radio", 500))
    escenario = _escenario()
    flujo = traffic.flujo_punto(lat, lon, escenario=escenario)
    paradas = overpass.fetch_bus_stops(lat, lon, radio)
    vehiculos = traffic.vehiculos_simulados(escenario)
    return jsonify({
        "trafico": flujo,
        "paradas": paradas,
        "vehiculos": vehiculos,
        "resumen": {
            "vehiculos_activos": len(vehiculos),
            "paradas_cercanas": len(paradas),
            "modo": "simulado" if all(v.get("simulado") for v in vehiculos) else "mixto",
            "escenario": escenario,
        },
        "incidentes": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fuente_trafico": flujo["fuente_datos"],
    })
