"""Adaptador a HERE Traffic Flow API (opcional, requiere HERE_API_KEY)."""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached


def flow(lat: float, lon: float) -> dict | None:
    key_api = current_app.config.get("HERE_API_KEY")
    if not key_api:
        return None

    cfg = current_app.config
    params = {
        "apiKey": key_api,
        "in": f"circle:{lat},{lon};r=250",
        "locationReferencing": "shape",
    }
    cache_key = f"here:flow:{round(lat,4)}:{round(lon,4)}"

    def _producer():
        try:
            resp = requests.get(cfg["HERE_FLOW_BASE"], params=params, timeout=8)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None
            cf = results[0].get("currentFlow", {})
            vel_actual = cf.get("speed", 0) * 3.6
            vel_libre = cf.get("freeFlow", 0) * 3.6 or vel_actual
            return {
                "velocidad_actual_kmh": round(vel_actual, 1),
                "velocidad_libre_kmh": round(vel_libre, 1),
                "retraso_relativo": round(max(0.0, 1 - vel_actual / max(vel_libre, 1)), 3),
            }
        except (requests.RequestException, KeyError, IndexError, ZeroDivisionError):
            return None

    return cached(cache_key, 600, _producer)
