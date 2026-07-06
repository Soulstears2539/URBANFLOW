"""Adaptador a Overpass API (consultas a OpenStreetMap).

Provee paradas de transporte, POIs y rutas de transporte público con
fallback automático entre varios mirrors de Overpass.
"""
from __future__ import annotations

import requests
from flask import current_app

from .cache import cached


ECUADOR_CITY_BBOXES = {
    # south, west, north, east
    "Quito": "-0.36,-78.62,-0.04,-78.34",
    "Guayaquil": "-2.32,-80.08,-2.03,-79.78",
    "Cuenca": "-3.02,-79.10,-2.80,-78.88",
    "Riobamba": "-1.76,-78.72,-1.60,-78.58",
}


def _run_query(ql: str, timeout: int = 25) -> dict | None:
    cfg = current_app.config
    for url in cfg["OVERPASS_URLS"]:
        try:
            resp = requests.post(
                url, data={"data": ql}, timeout=timeout,
                headers={"User-Agent": cfg["USER_AGENT"]},
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            continue
    return None


def _center(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    return None


def fetch_bus_stops(lat: float, lon: float, radio_m: int = 500) -> list[dict]:
    ql = f"""
    [out:json][timeout:25];
    (
      node["highway"="bus_stop"](around:{radio_m},{lat},{lon});
      node["public_transport"="platform"](around:{radio_m},{lat},{lon});
      node["railway"="tram_stop"](around:{radio_m},{lat},{lon});
    );
    out body;"""
    key = f"overpass:stops:{round(lat,4)}:{round(lon,4)}:{radio_m}"

    def _producer():
        data = _run_query(ql)
        if data is None:
            return None
        paradas = []
        for el in data.get("elements", []):
            c = _center(el)
            if not c:
                continue
            tags = el.get("tags", {})
            paradas.append({
                "nombre": tags.get("name", "Parada"),
                "lat": c[0], "lon": c[1],
                "tipo": tags.get("public_transport") or tags.get("highway", "bus_stop"),
                "lineas": tags.get("route_ref", ""),
                "fuente": "OSM",
            })
        return paradas

    return cached(key, current_app.config["EXTERNAL_CACHE_TTL"], _producer) or []


def fetch_pois(lat: float, lon: float, radio_m: int = 500, tipos: list[str] | None = None) -> list[dict]:
    tipos = tipos or ["amenity=restaurant", "amenity=pharmacy", "shop=supermarket"]
    bloques = ""
    for t in tipos:
        if "=" in t:
            k, v = t.split("=", 1)
            bloques += f'node["{k}"="{v}"](around:{radio_m},{lat},{lon});\n'
    ql = f"[out:json][timeout:25];\n({bloques});\nout body;"
    key = f"overpass:pois:{round(lat,4)}:{round(lon,4)}:{radio_m}:{','.join(tipos)}"

    def _producer():
        data = _run_query(ql)
        if data is None:
            return None
        pois = []
        for el in data.get("elements", []):
            c = _center(el)
            if not c:
                continue
            tags = el.get("tags", {})
            pois.append({
                "nombre": tags.get("name", "POI"),
                "lat": c[0], "lon": c[1],
                "tipo": tags.get("amenity") or tags.get("shop", ""),
                "telefono": tags.get("phone", ""),
                "web": tags.get("website", ""),
                "fuente": "OSM",
            })
        return pois

    return cached(key, current_app.config["EXTERNAL_CACHE_TTL"], _producer) or []


def fetch_bus_routes(lat: float, lon: float, radio_m: int = 1500) -> list[dict]:
    ql = f"""
    [out:json][timeout:25];
    (
      relation["type"="route"]["route"~"bus|trolleybus|tram"](around:{radio_m},{lat},{lon});
    );
    out tags;"""
    key = f"overpass:routes:{round(lat,4)}:{round(lon,4)}:{radio_m}"

    def _producer():
        data = _run_query(ql)
        if data is None:
            return None
        rutas = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            rutas.append({
                "osm_id": el.get("id"),
                "ref": tags.get("ref", ""),
                "name": tags.get("name", ""),
                "tipo": tags.get("route", "bus"),
                "from": tags.get("from", ""),
                "to": tags.get("to", ""),
                "network": tags.get("network", ""),
                "colour": tags.get("colour", ""),
                "operator": tags.get("operator", ""),
                "interval": tags.get("interval", ""),
                "fuente": "OSM",
            })
        return rutas

    return cached(key, current_app.config["EXTERNAL_CACHE_TTL"], _producer) or []


def fetch_city_transport_routes(city: str, bbox: str) -> list[dict]:
    """Extrae rutas de transporte publico mapeadas en OSM para una ciudad."""
    ql = f"""
    [out:json][timeout:90];
    (
      relation["type"="route"]["route"~"bus|trolleybus|subway|tram"]({bbox});
    );
    out body;
    >;
    out body qt;"""
    key = f"overpass:{city.lower()}:transport_routes:v2"

    def _producer():
        data = _run_query(ql, timeout=100)
        if data is None:
            return None

        nodes = {
            el["id"]: el
            for el in data.get("elements", [])
            if el.get("type") == "node" and "lat" in el and "lon" in el
        }
        ways = {
            el["id"]: el
            for el in data.get("elements", [])
            if el.get("type") == "way"
        }

        rutas = []
        for rel in [el for el in data.get("elements", []) if el.get("type") == "relation"]:
            tags = rel.get("tags", {})
            stops = []
            seen = set()
            for member in rel.get("members", []):
                role = (member.get("role") or "").lower()
                ref = member.get("ref")
                node = nodes.get(ref)
                if node and ("stop" in role or "platform" in role or not role):
                    if ref in seen:
                        continue
                    seen.add(ref)
                    ntags = node.get("tags", {})
                    stops.append({
                        "nombre": ntags.get("name") or tags.get("name") or tags.get("ref") or "Parada",
                        "lat": node["lat"],
                        "lon": node["lon"],
                        "role": role,
                    })

            if len(stops) < 2:
                # Muchas relaciones solo traen ways; usamos nodos de la geometria como respaldo.
                for member in rel.get("members", []):
                    way = ways.get(member.get("ref"))
                    if not way:
                        continue
                    for node_id in way.get("nodes", [])[:: max(1, len(way.get("nodes", [])) // 8 or 1)]:
                        node = nodes.get(node_id)
                        if not node or node_id in seen:
                            continue
                        seen.add(node_id)
                        stops.append({
                            "nombre": tags.get("name") or tags.get("ref") or "Punto de ruta",
                            "lat": node["lat"],
                            "lon": node["lon"],
                            "role": "shape",
                        })
                    if len(stops) >= 12:
                        break

            if len(stops) < 2:
                continue

            rutas.append({
                "osm_id": rel.get("id"),
                "ref": tags.get("ref") or tags.get("name") or f"osm-{rel.get('id')}",
                "name": tags.get("name") or tags.get("ref") or f"Ruta OSM {rel.get('id')}",
                "tipo": tags.get("route", "bus"),
                "operator": tags.get("operator") or tags.get("network") or f"OSM {city}",
                "network": tags.get("network", ""),
                "from": tags.get("from", ""),
                "to": tags.get("to", ""),
                "colour": tags.get("colour", ""),
                "interval": tags.get("interval", ""),
                "stops": stops,
                "fuente": f"OSM {city}",
            })
        return rutas

    return cached(key, 3600, _producer) or []


def fetch_quito_transport_routes() -> list[dict]:
    """Extrae rutas de transporte publico mapeadas en OSM para Quito."""
    return fetch_city_transport_routes("Quito", ECUADOR_CITY_BBOXES["Quito"])


def fetch_ecuador_transport_routes(cities: list[str] | None = None) -> list[dict]:
    """Extrae rutas OSM de las ciudades principales configuradas."""
    selected = cities or list(ECUADOR_CITY_BBOXES)
    rutas = []
    for city in selected:
        bbox = ECUADOR_CITY_BBOXES.get(city)
        if not bbox:
            continue
        rutas.extend(fetch_city_transport_routes(city, bbox))
    return rutas
