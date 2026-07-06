"""Adaptador a las APIs de TomTom (búsqueda y tráfico vía routing).

Nota: TomTom Traffic Flow tiene poca cobertura en Quito, por eso el tráfico
real se estima con la Routing API (compara tiempos con/sin tráfico).
"""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached


def _api_key() -> str | None:
    return current_app.config.get("TOMTOM_API_KEY")


def fuzzy_search(query: str, lat: float | None, lon: float | None, limit: int = 6) -> list[dict]:
    """Autocompletado / búsqueda enriquecida. Requiere API key."""
    key_api = _api_key()
    if not key_api or not query.strip():
        return []

    cfg = current_app.config
    url = f"{cfg['TOMTOM_SEARCH_BASE']}/{requests.utils.quote(query.strip())}.json"
    params = {"key": key_api, "limit": limit, "countrySet": "EC"}
    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon})

    cache_key = f"tomtom:search:{query.strip().lower()}:{lat}:{lon}:{limit}"

    def _producer():
        try:
            resp = requests.get(url, params=params, timeout=6)
            resp.raise_for_status()
            out = []
            for r in resp.json().get("results", []):
                pos = r.get("position", {})
                addr = r.get("address", {})
                poi = r.get("poi", {})
                out.append({
                    "id": r.get("id"),
                    "nombre": poi.get("name") or addr.get("freeformAddress", ""),
                    "categoria": (poi.get("categories") or ["lugar"])[0],
                    "direccion_corta": addr.get("freeformAddress", ""),
                    "ciudad": addr.get("municipality", ""),
                    "lat": pos.get("lat"),
                    "lon": pos.get("lon"),
                    "distancia_m": round(r.get("dist", 0)),
                    "fuente_datos": "TOMTOM_SEARCH",
                })
            return out
        except requests.RequestException:
            return None

    return cached(cache_key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []


def routing_traffic_flow(lat: float, lon: float) -> dict | None:
    """Estima el flujo de tráfico comparando una ruta corta con/sin tráfico."""
    key_api = _api_key()
    if not key_api:
        return None

    cfg = current_app.config
    # Pequeño tramo de ~300 m hacia el este para medir velocidad efectiva.
    dlat, dlon = lat, lon + 0.0027
    loc = f"{lat},{lon}:{dlat},{dlon}"
    url = f"{cfg['TOMTOM_ROUTING_BASE']}/{loc}/json"
    cache_key = f"tomtom:flow:{round(lat,4)}:{round(lon,4)}"

    def _producer():
        try:
            base = requests.get(url, params={"key": key_api, "traffic": "false"}, timeout=8)
            live = requests.get(url, params={"key": key_api, "traffic": "true"}, timeout=8)
            base.raise_for_status()
            live.raise_for_status()
            b = base.json()["routes"][0]["summary"]
            l = live.json()["routes"][0]["summary"]
            dist_m = b.get("lengthInMeters", 1)
            t_base = b.get("travelTimeInSeconds", 1)
            t_live = l.get("travelTimeInSeconds", 1)
            vel_libre = (dist_m / max(t_base, 1)) * 3.6
            vel_actual = (dist_m / max(t_live, 1)) * 3.6
            return {
                "velocidad_actual_kmh": round(vel_actual, 1),
                "velocidad_libre_kmh": round(vel_libre, 1),
                "retraso_relativo": round(max(0.0, 1 - vel_actual / max(vel_libre, 1)), 3),
            }
        except (requests.RequestException, KeyError, IndexError, ZeroDivisionError):
            return None

    return cached(cache_key, 600, _producer)  # caché de 10 min para datos reales
