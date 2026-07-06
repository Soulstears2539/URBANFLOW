"""Adaptador SerpApi para busqueda de lugares en Google Maps."""
from __future__ import annotations

import logging
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

import requests
from flask import current_app

from .cache import cached

logger = logging.getLogger(__name__)

SERPAPI_BASE = "https://serpapi.com/search.json"

_MODE_MAP = {
    "auto": "Driving",
    "moto": "Driving",
    "bus": "Transit",
    "bici": "Cycling",
    "pie": "Walking",
}


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def search_places(
    query: str,
    latitude: float,
    longitude: float,
    api_key: str | None = None,
    max_results: int = 10,
) -> dict:
    if not api_key:
        logger.warning("SerpApi: sin clave configurada para '%s'", query)
        return _simulated_results(query, latitude, longitude, "Sin clave configurada")

    params = {
        "engine": "google_maps",
        "type": "search",
        "q": query,
        "ll": f"@{latitude},{longitude},14z",
        "api_key": api_key,
        "google_domain": "google.com",
        "hl": "en",
    }

    try:
        logger.info("SerpApi: buscando '%s' cerca de (%s, %s)", query, latitude, longitude)
        response = requests.get(SERPAPI_BASE, params=params, timeout=12)
        response.raise_for_status()
        data = response.json()
        local_results = data.get("local_results", [])

        results = []
        for i, place in enumerate(local_results[:max_results], 1):
            coords = place.get("gps_coordinates", {})
            place_lat = coords.get("latitude")
            place_lng = coords.get("longitude")
            distance_km = None
            if place_lat is not None and place_lng is not None:
                distance_km = round(_dist_km(latitude, longitude, place_lat, place_lng), 2)

            results.append({
                "position": i,
                "title": place.get("title", "Unknown"),
                "address": place.get("address", ""),
                "rating": place.get("rating"),
                "reviews": place.get("reviews"),
                "price": place.get("price", "N/A"),
                "lat": place_lat,
                "lng": place_lng,
                "distance_km": distance_km,
                "phone": place.get("phone", ""),
                "website": place.get("website", ""),
                "types": place.get("types", []),
                "hours": place.get("hours", ""),
                "open_state": place.get("open_state", ""),
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
            "timestamp": data.get("search_metadata", {}).get("created_at", ""),
            "fuente": "REAL",
            "request_time_ms": data.get("search_metadata", {}).get("total_time_taken", 0) * 1000,
        }
    except requests.exceptions.RequestException as exc:
        logger.error("SerpApi error para '%s': %s", query, exc)
        return _simulated_results(query, latitude, longitude, f"Error de red/API: {exc}")
    except Exception as exc:
        logger.exception("SerpApi parse error para '%s'", query)
        return _simulated_results(query, latitude, longitude, f"Error parseando respuesta: {exc}")


def directions_route(
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str = "auto",
    alternativas: int = 3,
) -> list[dict]:
    """Calcula rutas con SerpApi Google Maps Directions."""
    api_key = current_app.config.get("SERPAPI_API_KEY")
    if not api_key:
        return []

    params = {
        "engine": "google_maps_directions",
        "start_addr": f"{olat},{olon}",
        "end_addr": f"{dlat},{dlon}",
        "api_key": api_key,
        "hl": "es",
    }
    cache_key = f"serpapi:directions:{modo}:{round(olat,5)}:{round(olon,5)}:{round(dlat,5)}:{round(dlon,5)}"

    def _producer():
        try:
            response = requests.get(SERPAPI_BASE, params=params, timeout=14)
            response.raise_for_status()
            return _parse_directions_response(
                response.json(), olat, olon, dlat, dlon, modo, alternativas
            )
        except requests.exceptions.RequestException as exc:
            logger.error("SerpApi directions error: %s", exc)
            return None
        except Exception:
            logger.exception("SerpApi directions parse error")
            return None

    return cached(cache_key, current_app.config["EXTERNAL_CACHE_TTL"], _producer) or []


def _parse_directions_response(
    data: dict,
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str,
    alternativas: int,
) -> list[dict]:
    desired_mode = _MODE_MAP.get(modo, "Driving")
    directions = data.get("directions") or []
    if desired_mode != "Driving":
        directions = [d for d in directions if d.get("travel_mode") == desired_mode] or directions

    rutas = []
    for route in directions[:alternativas]:
        steps = []
        path = [[olat, olon]]
        for trip in route.get("trips", []):
            for detail in trip.get("details", []):
                coords = detail.get("gps_coordinates") or {}
                lat = coords.get("latitude")
                lon = coords.get("longitude")
                if lat is not None and lon is not None:
                    path.append([round(float(lat), 6), round(float(lon), 6)])
                steps.append({
                    "instruccion": detail.get("title") or trip.get("title") or "Continua",
                    "dist_m": round(float(detail.get("distance") or 0), 1),
                    "dur_s": round(float(detail.get("duration") or 0), 1),
                    "tipo": detail.get("action") or "serpapi",
                    "icono": _step_icon(detail.get("action")),
                    "geo_photo": detail.get("geo_photo"),
                })
        path.append([dlat, dlon])

        distance_m = float(route.get("distance") or 0)
        duration_s = float(route.get("duration") or 0)
        if not distance_m:
            distance_m = _path_distance_km(path) * 1000

        rutas.append({
            "dist_km": round(distance_m / 1000, 3),
            "dur_min": round(duration_s / 60, 2) if duration_s else 0,
            "dur_min_original": round(duration_s / 60, 2) if duration_s else 0,
            "path": path,
            "steps": steps,
            "fuente": "SERPAPI_GOOGLE_MAPS_DIRECTIONS",
            "trafico_directo": bool(route.get("typical_duration_range")) and desired_mode == "Driving",
            "trafico_rango_tipico": route.get("typical_duration_range"),
            "via": route.get("via", ""),
            "advertencias": route.get("extensions", []),
        })
    return [r for r in rutas if len(r["path"]) >= 2]


def _path_distance_km(path: list[list[float]]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        total += _dist_km(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    return total


def _step_icon(action: str | None) -> str:
    if not action:
        return "->"
    if "left" in action:
        return "<-"
    if "right" in action:
        return "->"
    if "merge" in action or "ramp" in action:
        return "=>"
    if "roundabout" in action:
        return "o"
    return "->"


def _simulated_results(query: str, lat: float, lng: float, motivo: str | None = None) -> dict:
    poi_database = {
        "coffee": [
            {
                "title": "Brew Haven Cafe",
                "address": "123 Main St, Downtown",
                "rating": 4.8,
                "reviews": 142,
                "price": "$10-15",
                "lat": lat + 0.005,
                "lng": lng - 0.005,
                "phone": "(201) 555-0001",
                "website": "https://brewhaven.com",
                "types": ["Coffee shop", "Cafe"],
            },
            {
                "title": "Espresso Express",
                "address": "456 Oak Ave, Midtown",
                "rating": 4.6,
                "reviews": 87,
                "price": "$5-10",
                "lat": lat - 0.003,
                "lng": lng + 0.004,
                "phone": "(201) 555-0002",
                "website": "https://espressoexpress.com",
                "types": ["Coffee shop"],
            },
            {
                "title": "The Daily Grind",
                "address": "789 Pine Rd, Uptown",
                "rating": 4.9,
                "reviews": 256,
                "price": "$8-12",
                "lat": lat + 0.008,
                "lng": lng + 0.006,
                "phone": "(201) 555-0003",
                "website": "https://dailygrind.co",
                "types": ["Coffee shop", "Bakery"],
            },
        ],
        "restaurant": [
            {
                "title": "Urban Kitchen",
                "address": "321 Market St, Downtown",
                "rating": 4.7,
                "reviews": 203,
                "price": "$20-35",
                "lat": lat + 0.002,
                "lng": lng + 0.003,
                "phone": "(201) 555-0010",
                "website": "https://urbankitchen.com",
                "types": ["Restaurant", "Contemporary"],
            },
            {
                "title": "Flavor Fusion",
                "address": "654 River Blvd, Riverside",
                "rating": 4.5,
                "reviews": 165,
                "price": "$15-25",
                "lat": lat - 0.006,
                "lng": lng - 0.004,
                "phone": "(201) 555-0011",
                "website": "https://flavorfusion.net",
                "types": ["Restaurant", "International"],
            },
        ],
        "hospital": [
            {
                "title": "City Medical Center",
                "address": "999 Health Ave, Medical District",
                "rating": 4.6,
                "reviews": 78,
                "price": "N/A",
                "lat": lat + 0.010,
                "lng": lng - 0.008,
                "phone": "(201) 555-0100",
                "website": "https://citymedicenter.org",
                "types": ["Hospital", "Emergency"],
            },
        ],
    }

    query_lower = query.lower()
    if "coffee" in query_lower or "cafe" in query_lower:
        base_results = poi_database["coffee"]
    elif "restaurant" in query_lower or "food" in query_lower:
        base_results = poi_database["restaurant"]
    elif "hospital" in query_lower or "medical" in query_lower:
        base_results = poi_database["hospital"]
    else:
        base_results = poi_database["coffee"][:2]

    results = []
    for i, place in enumerate(base_results[:10], 1):
        results.append({
            "position": i,
            "title": place["title"],
            "address": place["address"],
            "rating": place["rating"],
            "reviews": place["reviews"],
            "price": place["price"],
            "lat": place["lat"],
            "lng": place["lng"],
            "distance_km": round(_dist_km(lat, lng, place["lat"], place["lng"]), 2),
            "phone": place["phone"],
            "website": place["website"],
            "types": place["types"],
            "hours": "9 AM - 6 PM",
            "open_state": "Open",
        })

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat(),
        "fuente": "SIMULADO",
        "nota": "Requiere clave SerpApi valida en .env para datos reales",
        "motivo_fallback": motivo,
    }
