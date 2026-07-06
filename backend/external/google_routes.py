"""Adaptador a Google Routes API para rutas y trafico."""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached

_TRAVEL_MODES = {
    "auto": "DRIVE",
    "moto": "TWO_WHEELER",
    "bus": "DRIVE",
    "bici": "BICYCLE",
    "pie": "WALK",
}


def _api_key() -> str | None:
    return current_app.config.get("GOOGLE_MAPS_API_KEY")


def _parse_duration_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).rstrip("s"))
    except ValueError:
        return 0.0


def _decode_polyline(encoded: str) -> list[list[float]]:
    points = []
    index = 0
    lat = 0
    lon = 0

    while index < len(encoded):
        for target in ("lat", "lon"):
            result = 0
            shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if target == "lat":
                lat += delta
            else:
                lon += delta
        points.append([round(lat / 1e5, 6), round(lon / 1e5, 6)])

    return points


def _headers(field_mask: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _api_key() or "",
        "X-Goog-FieldMask": field_mask,
    }


def compute_routes(
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str = "auto",
    alternativas: int = 3,
) -> list[dict]:
    key_api = _api_key()
    if not key_api:
        return []

    cfg = current_app.config
    body = {
        "origin": {"location": {"latLng": {"latitude": olat, "longitude": olon}}},
        "destination": {"location": {"latLng": {"latitude": dlat, "longitude": dlon}}},
        "travelMode": _TRAVEL_MODES.get(modo, "DRIVE"),
        "languageCode": "es-419",
        "units": "METRIC",
        "computeAlternativeRoutes": alternativas > 1,
        "polylineQuality": "HIGH_QUALITY",
    }
    if modo in {"auto", "moto", "bus"}:
        body["routingPreference"] = "TRAFFIC_AWARE_OPTIMAL"

    field_mask = ",".join([
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.navigationInstruction.instructions",
    ])
    cache_key = f"google:route:{modo}:{round(olat,5)}:{round(olon,5)}:{round(dlat,5)}:{round(dlon,5)}:{alternativas}"

    def _producer():
        try:
            resp = requests.post(
                cfg["GOOGLE_ROUTES_BASE"],
                json=body,
                headers=_headers(field_mask),
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()
            rutas = []
            for route in data.get("routes", []):
                encoded = ((route.get("polyline") or {}).get("encodedPolyline") or "")
                path = _decode_polyline(encoded) if encoded else []
                dur_s = _parse_duration_seconds(route.get("duration"))
                static_s = _parse_duration_seconds(route.get("staticDuration"))

                steps = []
                for leg in route.get("legs", []):
                    for step in leg.get("steps", []):
                        steps.append({
                            "instruccion": ((step.get("navigationInstruction") or {}).get("instructions") or "Continua"),
                            "dist_m": round(step.get("distanceMeters", 0), 1),
                            "dur_s": round(_parse_duration_seconds(step.get("staticDuration")), 1),
                            "tipo": "google",
                            "icono": "->",
                        })

                rutas.append({
                    "dist_km": round(route.get("distanceMeters", 0) / 1000, 3),
                    "dur_min": round(dur_s / 60, 2),
                    "dur_min_original": round((static_s or dur_s) / 60, 2),
                    "path": path,
                    "steps": steps,
                    "fuente": "GOOGLE_ROUTES",
                    "trafico_directo": modo in {"auto", "moto", "bus"},
                })
            return rutas
        except (requests.RequestException, KeyError, IndexError, ValueError):
            return None

    return cached(cache_key, cfg["EXTERNAL_CACHE_TTL"], _producer) or []


def traffic_flow(lat: float, lon: float) -> dict | None:
    key_api = _api_key()
    if not key_api:
        return None

    cfg = current_app.config
    body = {
        "origin": {"location": {"latLng": {"latitude": lat, "longitude": lon}}},
        "destination": {"location": {"latLng": {"latitude": lat, "longitude": lon + 0.0027}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "languageCode": "es-419",
        "units": "METRIC",
        "polylineQuality": "OVERVIEW",
    }
    field_mask = ",".join([
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
    ])
    cache_key = f"google:flow:{round(lat,4)}:{round(lon,4)}"

    def _producer():
        try:
            resp = requests.post(
                cfg["GOOGLE_ROUTES_BASE"],
                json=body,
                headers=_headers(field_mask),
                timeout=10,
            )
            resp.raise_for_status()
            route = resp.json().get("routes", [])[0]
            dist_m = max(route.get("distanceMeters", 0), 1)
            dur_s = max(_parse_duration_seconds(route.get("duration")), 1)
            static_s = max(_parse_duration_seconds(route.get("staticDuration")), 1)
            vel_actual = (dist_m / dur_s) * 3.6
            vel_libre = (dist_m / static_s) * 3.6
            return {
                "velocidad_actual_kmh": round(vel_actual, 1),
                "velocidad_libre_kmh": round(vel_libre, 1),
                "retraso_relativo": round(max(0.0, 1 - vel_actual / max(vel_libre, 1)), 3),
            }
        except (requests.RequestException, KeyError, IndexError, ValueError, ZeroDivisionError):
            return None

    return cached(cache_key, 600, _producer)
