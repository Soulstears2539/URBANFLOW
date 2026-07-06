"""Endpoints de OpenStreetMap vía Overpass."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..external import overpass

bp = Blueprint("overpass", __name__, url_prefix="/api/overpass")


def _coords_radio(default_radio=500):
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return None
    return lat, lon, int(request.args.get("radio", default_radio))


@bp.get("/stops")
def stops():
    c = _coords_radio()
    if not c:
        return jsonify({"error": "Se requieren lat y lon"}), 400
    paradas = overpass.fetch_bus_stops(*c)
    return jsonify({"paradas": paradas, "total": len(paradas)})


@bp.get("/pois")
def pois():
    c = _coords_radio()
    if not c:
        return jsonify({"error": "Se requieren lat y lon"}), 400
    lat, lon, radio = c
    tipos = request.args.get("tipos")
    tipos_list = [t.strip() for t in tipos.split(",")] if tipos else None
    res = overpass.fetch_pois(lat, lon, radio, tipos_list)
    return jsonify({"pois": res, "total": len(res)})


@bp.get("/routes")
def routes():
    c = _coords_radio(1500)
    if not c:
        return jsonify({"error": "Se requieren lat y lon"}), 400
    rutas = overpass.fetch_bus_routes(*c)
    return jsonify({"rutas": rutas, "total": len(rutas)})
