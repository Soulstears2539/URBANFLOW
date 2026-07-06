"""Adaptador a feeds GTFS (estático) y GTFS Realtime.

- Descarga y parsea un ZIP GTFS estático (rutas, paradas, viajes).
- Lee GTFS Realtime si está disponible la librería de bindings.
La descarga valida la URL contra SSRF y limita el tamaño.
"""
from __future__ import annotations

import csv
import io
import zipfile

import requests
from flask import current_app

from .security import validate_remote_url


def download_gtfs(url: str) -> bytes:
    safe_url = validate_remote_url(url)
    cfg = current_app.config
    max_bytes = cfg["MAX_GTFS_BYTES"]
    resp = requests.get(
        safe_url, timeout=30, stream=True,
        headers={"User-Agent": cfg["USER_AGENT"]},
    )
    resp.raise_for_status()
    buffer = io.BytesIO()
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("El feed GTFS supera el tamaño máximo permitido (50 MB)")
        buffer.write(chunk)
    return buffer.getvalue()


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    if name not in zf.namelist():
        return []
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig")
        return list(csv.DictReader(text))


def parse_gtfs(gtfs_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(gtfs_bytes)) as zf:
        routes = _read_csv(zf, "routes.txt")
        stops = _read_csv(zf, "stops.txt")
        trips = _read_csv(zf, "trips.txt")

    parsed_stops = []
    for s in stops:
        try:
            parsed_stops.append({
                "nombre": s.get("stop_name", "Parada"),
                "lat": float(s["stop_lat"]),
                "lon": float(s["stop_lon"]),
                "fuente": "GTFS",
            })
        except (KeyError, ValueError):
            continue

    return {
        "routes": routes,
        "stops": parsed_stops,
        "n_routes": len(routes),
        "n_stops": len(parsed_stops),
        "n_trips": len(trips),
    }


def fetch_realtime(url: str | None, kind: str) -> dict:
    """Lee un feed GTFS Realtime. Devuelve mensaje si no está configurado."""
    if not url:
        return {"mensaje": f"Feed GTFS Realtime ({kind}) no configurado", "items": []}
    try:
        from google.transit import gtfs_realtime_pb2  # type: ignore
    except ImportError:
        return {
            "mensaje": "Instala 'gtfs-realtime-bindings' para leer feeds en tiempo real",
            "items": [],
        }
    try:
        safe_url = validate_remote_url(url)
        resp = requests.get(safe_url, timeout=10)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        items = []
        for entity in feed.entity:
            items.append({"id": entity.id})
        return {"items": items, "total": len(items)}
    except (requests.RequestException, ValueError) as exc:
        return {"error": str(exc), "items": []}
