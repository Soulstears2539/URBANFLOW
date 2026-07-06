"""Endpoints operativos: salud, estado de fuentes, configuración, vehículos, TTS."""
from __future__ import annotations

import platform
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, current_app, jsonify, request

from ..auth import require_admin
from ..extensions import db
from ..models import VehiclePosition
from ..services import ml
from ..services.recorder import total_registros
from ..services import transport

bp = Blueprint("ops", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "registros_ml": total_registros(),
        "modelo_listo": ml.modelo_listo(),
        "buses_quito": len(transport.buses_summary()),
        "hora": datetime.now(timezone.utc).isoformat(),
    })


def _check(nombre, url, **kw):
    inicio = time.time()
    try:
        resp = requests.get(url, timeout=6, **kw)
        latencia = round((time.time() - inicio) * 1000)
        estado = "ONLINE" if resp.status_code < 500 else "OFFLINE"
        return {"estado": estado, "latencia_ms": latencia}
    except requests.RequestException as exc:
        return {"estado": "OFFLINE", "latencia_ms": None, "mensaje_error": str(exc)}


@bp.get("/sources/status")
def sources_status():
    cfg = current_app.config
    fuentes = {
        "nominatim": _check("nominatim", cfg["NOMINATIM_BASE"], params={"q": "Quito", "format": "json"}),
        "overpass": _check("overpass", cfg["OVERPASS_URLS"][0], params={"data": "[out:json];out;"}),
        "osrm": _check("osrm", f"{cfg['OSRM_BASE']}/driving/-78.5,-0.2;-78.49,-0.19"),
    }
    fuentes["google_routes"] = (
        {"estado": "NO_CONFIGURADO"} if not cfg.get("GOOGLE_MAPS_API_KEY")
        else {"estado": "CONFIGURADO"}
    )
    fuentes["tomtom_search"] = (
        {"estado": "NO_CONFIGURADO"} if not cfg.get("TOMTOM_API_KEY")
        else {"estado": "CONFIGURADO"}
    )
    fuentes["geoapify"] = (
        {"estado": "NO_CONFIGURADO"} if not cfg.get("GEOAPIFY_API_KEY")
        else {"estado": "CONFIGURADO"}
    )
    fuentes["serpapi"] = (
        {"estado": "NO_CONFIGURADO"} if not cfg.get("SERPAPI_API_KEY")
        else {"estado": "CONFIGURADO"}
    )
    fuentes["here_traffic"] = (
        {"estado": "NO_CONFIGURADO"} if not cfg.get("HERE_API_KEY")
        else {"estado": "CONFIGURADO"}
    )
    fuentes["timestamp"] = datetime.now(timezone.utc).isoformat()
    return jsonify(fuentes)


@bp.post("/config/tomtom")
@require_admin
def config_tomtom():
    data = request.get_json(silent=True) or {}
    key = (data.get("api_key") or "").strip()
    if not key:
        return jsonify({"error": "Se requiere 'api_key'"}), 400
    current_app.config["TOMTOM_API_KEY"] = key
    return jsonify({"ok": True, "mensaje": "Clave TomTom actualizada en caliente"})


@bp.post("/vehicles/location")
@require_admin
def vehicle_location():
    d = request.get_json(silent=True) or {}
    try:
        pos = VehiclePosition(
            vehicle_id=str(d["vehicle_id"]),
            cooperativa=d.get("cooperativa", ""),
            route_id=str(d.get("route_id", "")),
            lat=float(d["lat"]), lon=float(d["lon"]),
            speed_kmh=float(d.get("speed_kmh", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se requieren vehicle_id, lat, lon"}), 400
    db.session.add(pos)
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.get("/vehicles/live")
def vehicles_live():
    route_id = request.args.get("route_id")
    max_age = int(request.args.get("max_age_sec", 120))
    limite = datetime.now(timezone.utc) - timedelta(seconds=max_age)
    q = VehiclePosition.query.filter(VehiclePosition.timestamp >= limite)
    if route_id:
        q = q.filter_by(route_id=route_id)
    # Última posición por vehículo.
    ultimos: dict[str, VehiclePosition] = {}
    for v in q.order_by(VehiclePosition.timestamp.asc()).all():
        ultimos[v.vehicle_id] = v
    vehiculos = [v.to_dict() for v in ultimos.values()]
    return jsonify({"vehicles": vehiculos, "total": len(vehiculos),
                    "timestamp": datetime.now(timezone.utc).isoformat()})


# --- TTS (solo Windows, best-effort) ---
def _speak_windows(texto: str) -> None:
    safe = texto.replace('"', "'")
    ps = f'Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{safe}")'
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])


@bp.post("/tts/speak")
def tts_speak():
    texto = (request.get_json(silent=True) or {}).get("texto", "").strip()
    if not texto:
        return jsonify({"error": "Se requiere 'texto'"}), 400
    if platform.system() != "Windows":
        return jsonify({"error": "TTS solo disponible en Windows"}), 501
    threading.Thread(target=_speak_windows, args=(texto[:500],), daemon=True).start()
    return jsonify({"ok": True})


@bp.post("/tts/stop")
def tts_stop():
    if platform.system() == "Windows":
        subprocess.Popen(["taskkill", "/F", "/IM", "powershell.exe"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({"ok": True})
