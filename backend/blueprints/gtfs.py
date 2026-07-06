"""Endpoints GTFS (importación estática y realtime).

La importación es administrativa (require_admin) porque descarga recursos
remotos y escribe en la base de datos.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..auth import require_admin
from ..external import gtfs
from ..external.overpass import _center  # noqa: F401 (reservado para uso futuro)
from ..external.security import SecurityError
from ..services import recorder
from ..services.routing import haversine_km

bp = Blueprint("gtfs", __name__, url_prefix="/api/gtfs")


@bp.post("/import")
@require_admin
def importar():
    data = request.get_json(silent=True) or {}
    url = data.get("url") or current_app.config.get("GTFS_FEED_URL")
    ciudad = data.get("ciudad", "Quito")
    if not url:
        return jsonify({"error": "Se requiere 'url' del feed GTFS"}), 400
    try:
        raw = gtfs.download_gtfs(url)
        parsed = gtfs.parse_gtfs(raw)
    except SecurityError as exc:
        return jsonify({"error": f"URL rechazada: {exc}"}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"No se pudo importar el feed: {exc}"}), 502

    guardadas = 0
    for stop in parsed["stops"][:2000]:  # límite defensivo
        recorder.registrar_generico(
            "gtfs_parada", ciudad=ciudad, origen_query=stop["nombre"],
            olat=stop["lat"], olon=stop["lon"], fuente_busqueda="GTFS",
        )
        guardadas += 1

    return jsonify({
        "rutas": parsed["n_routes"], "paradas": parsed["n_stops"],
        "viajes": parsed["n_trips"], "guardadas": guardadas,
        "ciudad": ciudad, "fuente": "GTFS",
    })


@bp.get("/paradas")
def paradas():
    from ..models import MobilityRecord  # import local para evitar ciclos
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Se requieren lat y lon"}), 400
    radio_m = int(request.args.get("radio", 500))

    registros = MobilityRecord.query.filter_by(tipo="gtfs_parada").limit(5000).all()
    cercanas = []
    for r in registros:
        if r.olat is None or r.olon is None:
            continue
        d = haversine_km(lat, lon, r.olat, r.olon) * 1000
        if d <= radio_m:
            cercanas.append({"nombre": r.origen_query, "lat": r.olat, "lon": r.olon,
                             "dist_m": round(d), "fuente": "GTFS"})
    cercanas.sort(key=lambda x: x["dist_m"])
    return jsonify({"paradas": cercanas, "total": len(cercanas)})


@bp.get("/realtime/vehicles")
def rt_vehicles():
    url = current_app.config.get("GTFS_REALTIME_VEHICLES_URL")
    return jsonify(gtfs.fetch_realtime(url, "vehicles"))


@bp.get("/realtime/trip-updates")
def rt_trip_updates():
    url = current_app.config.get("GTFS_REALTIME_TRIP_UPDATES_URL")
    return jsonify(gtfs.fetch_realtime(url, "trip-updates"))


@bp.get("/realtime/alerts")
def rt_alerts():
    url = current_app.config.get("GTFS_REALTIME_ALERTS_URL")
    return jsonify(gtfs.fetch_realtime(url, "alerts"))
