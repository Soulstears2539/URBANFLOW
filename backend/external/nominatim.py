"""Adaptador a Nominatim (geocodificación de OpenStreetMap)."""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached


def _headers() -> dict:
    return {"User-Agent": current_app.config["USER_AGENT"]}


def geocode(query: str, pais: str = "ec") -> dict | None:
    """Convierte una dirección en coordenadas (primer resultado)."""
    resultados = search(query, limite=1, pais=pais)
    return resultados[0] if resultados else None


def search(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    limite: int = 8,
    pais: str = "ec",
) -> list[dict]:
    if not query or not query.strip():
        return []

    cfg = current_app.config
    params = {
        "q": query.strip(),
        "format": "jsonv2",
        "limit": limite,
        "addressdetails": 1,
        "countrycodes": pais,
    }
    if lat is not None and lon is not None:
        # Sesga resultados alrededor del punto (bounding box ~0.3°).
        params["viewbox"] = f"{lon-0.3},{lat+0.3},{lon+0.3},{lat-0.3}"
        params["bounded"] = 0

    key = f"nominatim:{query.strip().lower()}:{lat}:{lon}:{limite}"

    def _producer():
        try:
            resp = requests.get(
                cfg["NOMINATIM_BASE"], params=params, timeout=10, headers=_headers()
            )
            resp.raise_for_status()
            out = []
            for item in resp.json():
                out.append({
                    "name": item.get("name") or item.get("display_name", "").split(",")[0],
                    "display_name": item.get("display_name"),
                    "category": item.get("category") or item.get("type"),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "fuente": "Nominatim",
                })
            return out
        except (requests.RequestException, ValueError, KeyError):
            return None

    return cached(key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []
