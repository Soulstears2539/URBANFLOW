"""Adaptador a OSRM (Open Source Routing Machine) para cálculo de rutas."""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached

# Perfiles OSRM por modo de transporte de la app.
_PROFILE = {
    "auto": "driving",
    "moto": "driving",
    "bus": "driving",
    "bici": "bike",
    "pie": "foot",
}

_STEP_ICON = {
    "turn": "↪️",
    "depart": "🚩",
    "arrive": "🏁",
    "merge": "🔀",
    "roundabout": "🔄",
    "continue": "⬆️",
    "new name": "⬆️",
}


def _bearing_to_direction(bearing: float) -> str:
    """Convierte un ángulo de brújula (0-360) a dirección cardinal."""
    if bearing is None:
        return "adelante"
    bearing = bearing % 360
    dirs = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]
    idx = round(bearing / 45) % 8
    return dirs[idx]


def _build_turn_instruction(step: dict, next_step: dict = None) -> str:
    """Construye una instrucción natural para un paso."""
    man = step.get("maneuver", {})
    man_type = man.get("type", "")
    modifier = man.get("modifier", "")
    bearing_after = man.get("bearing_after")
    name = step.get("name", "")
    
    direction_text = _bearing_to_direction(bearing_after)
    
    # Instrucción de inicio
    if man_type == "depart":
        if name:
            return f"Dirígete al {direction_text} por {name}"
        return f"Comienza dirigiéndote al {direction_text}"
    
    # Llegada
    if man_type == "arrive":
        return "Llegaste a tu destino"
    
    # Rotonda
    if man_type == "roundabout":
        exit_num = man.get("exit")
        if exit_num:
            return f"Entra a la rotonda y toma la {_exit_ordinal(exit_num)} salida"
        return "Entra a la rotonda"
    
    # Giros
    if man_type == "turn":
        if modifier == "left":
            if name:
                return f"Gira a la izquierda al {direction_text} por {name}"
            return f"Gira a la izquierda hacia el {direction_text}"
        elif modifier == "right":
            if name:
                return f"Gira a la derecha al {direction_text} por {name}"
            return f"Gira a la derecha hacia el {direction_text}"
        elif modifier == "straight":
            if name:
                return f"Continúa al {direction_text} por {name}"
            return f"Continúa al {direction_text}"
        else:
            if name:
                return f"Gira al {direction_text} por {name}"
            return f"Gira hacia el {direction_text}"
    
    # Merge
    if man_type == "merge":
        side = "izquierda" if modifier == "left" else "derecha"
        if name:
            return f"Incorpórate a la {side} hacia {name}"
        return f"Incorpórate a la {side}"
    
    # Cambio de nombre
    if man_type == "new name":
        if name:
            return f"Continúa por {name}"
        return "Continúa"
    
    # Continue
    if man_type == "continue":
        if name:
            return f"Continúa al {direction_text} por {name}"
        return f"Continúa al {direction_text}"
    
    # Fallback
    if name:
        return name
    return "Continúa"


def _exit_ordinal(n: int) -> str:
    """Convierte número a ordinal en español."""
    if n == 1:
        return "1ª"
    elif n == 2:
        return "2ª"
    elif n == 3:
        return "3ª"
    elif n == 4:
        return "4ª"
    else:
        return f"{n}ª"


def _maneuver_icon(step: dict) -> str:
    man = step.get("maneuver", {})
    return _STEP_ICON.get(man.get("type", ""), "➡️")


def _parse_routes(data: dict) -> list[dict]:
    rutas = []
    for ruta in data.get("routes", []):
        coords = ruta.get("geometry", {}).get("coordinates", [])
        path = [[lat, lon] for lon, lat in coords]  # GeoJSON es [lon,lat]
        steps = []
        for leg in ruta.get("legs", []):
            leg_steps = leg.get("steps", [])
            for step_idx, step in enumerate(leg_steps):
                next_step = leg_steps[step_idx + 1] if step_idx + 1 < len(leg_steps) else None
                man = step.get("maneuver", {})
                instruccion = _build_turn_instruction(step, next_step)
                steps.append({
                    "instruccion": instruccion,
                    "dist_m": round(step.get("distance", 0), 1),
                    "dur_s": round(step.get("duration", 0), 1),
                    "tipo": man.get("type", ""),
                    "icono": _maneuver_icon(step),
                })
        rutas.append({
            "dist_km": round(ruta.get("distance", 0) / 1000, 3),
            "dur_min": round(ruta.get("duration", 0) / 60, 2),
            "path": path,
            "steps": steps,
        })
    return rutas


def fetch_osrm_route(
    olat: float, olon: float, dlat: float, dlon: float,
    modo: str = "auto", alternativas: int = 3,
) -> list[dict]:
    cfg = current_app.config
    profile = _PROFILE.get(modo, "driving")
    coords = f"{olon},{olat};{dlon},{dlat}"
    url = f"{cfg['OSRM_BASE']}/{profile}/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "true" if alternativas > 1 else "false",
    }
    key = f"osrm:{profile}:{coords}:{alternativas}"

    def _producer():
        try:
            resp = requests.get(
                url, params=params, timeout=12,
                headers={"User-Agent": cfg["USER_AGENT"]},
            )
            resp.raise_for_status()
            return _parse_routes(resp.json())
        except requests.RequestException:
            return None

    return cached(key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []


def fetch_osrm_route_waypoints(
    puntos: list[tuple[float, float]],
    modo: str = "auto",
    alternativas: int = 1,
) -> list[dict]:
    """Calcula una ruta por calles pasando por todos los puntos en orden."""
    if len(puntos) < 2:
        return []

    cfg = current_app.config
    profile = _PROFILE.get(modo, "driving")
    coords = ";".join(f"{lon},{lat}" for lat, lon in puntos)
    url = f"{cfg['OSRM_BASE']}/{profile}/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "true" if alternativas > 1 else "false",
    }
    key = f"osrm:{profile}:waypoints:{coords}:{alternativas}"

    def _producer():
        try:
            resp = requests.get(
                url, params=params, timeout=18,
                headers={"User-Agent": cfg["USER_AGENT"]},
            )
            resp.raise_for_status()
            return _parse_routes(resp.json())
        except requests.RequestException:
            return None

    return cached(key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []
