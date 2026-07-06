"""Configuración central de UrbanFlow OSM.

Carga variables desde el entorno (.env) y expone objetos de configuración
por ambiente. Todo lo configurable vive aquí para evitar valores mágicos
dispersos por el código.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# Carga .env desde la raíz del proyecto si existe.
load_dotenv(PROJECT_ROOT / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: str) -> list[str]:
    raw = value if value is not None else default
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


class Config:
    """Configuración base compartida por todos los ambientes."""

    # --- Servidor ---
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5050"))
    DEBUG = _bool(os.getenv("FLASK_DEBUG"), True)
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-cambia-esto")

    # --- Base de datos ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'urbanflow.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- CORS ---
    CORS_ORIGINS = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]

    # --- Auth ---
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip() or None

    # --- Proveedores externos ---
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip() or None
    TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "").strip() or None
    GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip() or None
    HERE_API_KEY = os.getenv("HERE_API_KEY", "").strip() or None
    SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "").strip() or None

    ROUTE_PROVIDERS = _csv(
        os.getenv("ROUTE_PROVIDERS"),
        "osrm,google,geoapify,serpapi",
    )
    SEARCH_PROVIDERS = _csv(
        os.getenv("SEARCH_PROVIDERS"),
        "tomtom,geoapify,nominatim",
    )
    TRAFFIC_PROVIDERS = _csv(
        os.getenv("TRAFFIC_PROVIDERS"),
        "google,here,tomtom",
    )

    GTFS_FEED_URL = os.getenv("GTFS_FEED_URL", "").strip() or None
    GTFS_REALTIME_VEHICLES_URL = os.getenv("GTFS_REALTIME_VEHICLES_URL", "").strip() or None
    GTFS_REALTIME_TRIP_UPDATES_URL = os.getenv("GTFS_REALTIME_TRIP_UPDATES_URL", "").strip() or None
    GTFS_REALTIME_ALERTS_URL = os.getenv("GTFS_REALTIME_ALERTS_URL", "").strip() or None

    # --- Endpoints públicos de terceros ---
    OSRM_BASE = "https://router.project-osrm.org/route/v1"
    NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
    GOOGLE_ROUTES_BASE = "https://routes.googleapis.com/directions/v2:computeRoutes"
    OVERPASS_URLS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    GEOAPIFY_AUTOCOMPLETE_BASE = "https://api.geoapify.com/v1/geocode/autocomplete"
    GEOAPIFY_ROUTING_BASE = "https://api.geoapify.com/v1/routing"
    TOMTOM_SEARCH_BASE = "https://api.tomtom.com/search/2/search"
    TOMTOM_ROUTING_BASE = "https://api.tomtom.com/routing/1/calculateRoute"
    HERE_FLOW_BASE = "https://data.traffic.hereapi.com/v7/flow"

    USER_AGENT = "UrbanFlowOSM/2.0 (movilidad urbana Ecuador)"

    # --- Límites de seguridad ---
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024       # 10 MB para CSV
    MAX_GTFS_BYTES = 50 * 1024 * 1024          # 50 MB para feeds GTFS
    EXTERNAL_CACHE_TTL = 60                     # segundos


def get_config() -> type[Config]:
    return Config
