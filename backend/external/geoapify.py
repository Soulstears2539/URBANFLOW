"""Adaptador a Geoapify para busqueda y rutas de respaldo."""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached

_MODES = {
    "auto": "drive",
    "moto": "drive",
    "bus": "drive",
    "bici": "bicycle",
    "pie": "walk",
}


def _api_key() -> str | None:
    return current_app.config.get("GEOAPIFY_API_KEY")


def autocomplete(query: str, lat: float | None, lon: float | None, limit: int = 6) -> list[dict]:
    key_api = _api_key()
    if not key_api or not query.strip():
        return []

    cfg = current_app.config
    params = {
        "text": query.strip(),
        "format": "json",
        "limit": limit,
        "filter": "countrycode:ec",
        "apiKey": key_api,
    }
    if lat is not None and lon is not None:
        params["bias"] = f"proximity:{lon},{lat}"

    cache_key = f"geoapify:search:{query.strip().lower()}:{lat}:{lon}:{limit}"

    def _producer():
        try:
            resp = requests.get(cfg["GEOAPIFY_AUTOCOMPLETE_BASE"], params=params, timeout=8)
            resp.raise_for_status()
            out = []
            for item in resp.json().get("results", []):
                out.append({
                    "id": item.get("place_id"),
                    "nombre": item.get("name") or item.get("formatted", "").split(",")[0],
                    "categoria": item.get("result_type") or "lugar",
                    "direccion_corta": item.get("formatted", ""),
                    "ciudad": item.get("city") or item.get("county") or "",
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "fuente_datos": "GEOAPIFY_SEARCH",
                })
            return out
        except requests.RequestException:
            return None

    return cached(cache_key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []


def route(
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str = "auto",
) -> list[dict]:
    key_api = _api_key()
    if not key_api:
        return []

    cfg = current_app.config
    params = {
        "waypoints": f"{olat},{olon}|{dlat},{dlon}",
        "mode": _MODES.get(modo, "drive"),
        "details": "instruction_details",
        "apiKey": key_api,
    }
    cache_key = f"geoapify:route:{modo}:{round(olat,5)}:{round(olon,5)}:{round(dlat,5)}:{round(dlon,5)}"

    def _producer():
        try:
            resp = requests.get(cfg["GEOAPIFY_ROUTING_BASE"], params=params, timeout=12)
            resp.raise_for_status()
            rutas = []
            for feat in resp.json().get("features", []):
                coords = ((feat.get("geometry") or {}).get("coordinates") or [])
                path = [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
                props = feat.get("properties", {})

                steps = []
                for leg in props.get("legs", []):
                    for step in leg.get("steps", []):
                        steps.append({
                            "instruccion": step.get("instruction", "Continua"),
                            "dist_m": round(step.get("distance", 0), 1),
                            "dur_s": round(step.get("time", 0), 1),
                            "tipo": step.get("type", "geoapify"),
                            "icono": "->",
                        })

                rutas.append({
                    "dist_km": round(props.get("distance", 0) / 1000, 3),
                    "dur_min": round(props.get("time", 0) / 60, 2),
                    "path": path,
                    "steps": steps,
                    "fuente": "GEOAPIFY_ROUTING",
                    "trafico_directo": False,
                })
            return rutas
        except (requests.RequestException, KeyError, ValueError):
            return None

    return cached(cache_key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []
