"""Servicio de rutas: ajusta tiempos por modo y trafico sobre OSRM."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from flask import current_app

from ..external import geoapify, google_routes, osrm, serpapi
from . import traffic

VELOCIDADES = {"auto": 52, "moto": 48, "bus": 20, "bici": 15, "pie": 5}
FACTORES_TRAFICO = {1: 1.0, 2: 1.3, 3: 1.7}
MODOS_MOTORIZADOS = {"auto", "moto", "bus"}
_TRAFICO_TEXTO = {1: "Bueno", 2: "Regular", 3: "Malo"}
_MAX_SALTO_GEOMETRIA_M = {"auto": 900, "moto": 900, "bus": 900, "bici": 450, "pie": 300}
_MIN_PUNTOS_POR_KM = {"auto": 4, "moto": 4, "bus": 4, "bici": 6, "pie": 8}
_MIN_DETALLE_RUTA_M = 300


def _prioridad_proveedores(proveedores: list[str]) -> list[str]:
    """SerpApi Directions trae puntos de maniobra, no polilinea completa."""
    orden_base = ["google", "osrm", "geoapify", "serpapi"]
    salida = [p for p in orden_base if p in proveedores]
    salida.extend(p for p in proveedores if p not in salida)
    return salida


def _path_distance_km(path: list[list[float]]) -> float:
    total = 0.0
    for idx in range(len(path) - 1):
        total += haversine_km(path[idx][0], path[idx][1], path[idx + 1][0], path[idx + 1][1])
    return total


def _max_salto_m(path: list[list[float]]) -> float:
    if len(path) < 2:
        return 0
    return max(
        haversine_km(path[idx][0], path[idx][1], path[idx + 1][0], path[idx + 1][1]) * 1000
        for idx in range(len(path) - 1)
    )


def _geometria_detallada(
    ruta: dict,
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str,
) -> bool:
    path = ruta.get("path") or []
    if len(path) < 2:
        return False

    distancia_directa_m = haversine_km(olat, olon, dlat, dlon) * 1000
    if len(path) < 3 and distancia_directa_m > _MIN_DETALLE_RUTA_M:
        return False

    dist_km = float(ruta.get("dist_km") or 0) or _path_distance_km(path)
    if dist_km <= 0:
        return False

    max_salto_m = _max_salto_m(path)
    puntos_por_km = len(path) / max(dist_km, 0.1)
    ruta["geometria_max_salto_m"] = round(max_salto_m, 1)
    ruta["geometria_puntos_por_km"] = round(puntos_por_km, 1)

    if dist_km > 1 and max_salto_m > _MAX_SALTO_GEOMETRIA_M.get(modo, 900):
        return False
    if dist_km > 2 and puntos_por_km < _MIN_PUNTOS_POR_KM.get(modo, 4):
        return False
    return True


def _fetch_provider_routes(
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str,
    alternativas: int = 3,
) -> list[dict]:
    proveedores = current_app.config.get("ROUTE_PROVIDERS") or ["google", "osrm", "geoapify", "serpapi"]
    for proveedor in _prioridad_proveedores(proveedores):
        if proveedor == "google":
            rutas = google_routes.compute_routes(olat, olon, dlat, dlon, modo, alternativas)
        elif proveedor == "serpapi":
            rutas = serpapi.directions_route(olat, olon, dlat, dlon, modo, alternativas)
        elif proveedor == "osrm":
            rutas = osrm.fetch_osrm_route(olat, olon, dlat, dlon, modo, alternativas)
            for ruta in rutas:
                ruta.setdefault("fuente", "OSRM")
                ruta.setdefault("trafico_directo", False)
        elif proveedor == "geoapify":
            rutas = geoapify.route(olat, olon, dlat, dlon, modo)
        else:
            rutas = []
        if rutas:
            rutas_validas = [
                ruta for ruta in rutas
                if _geometria_detallada(ruta, olat, olon, dlat, dlon, modo)
            ]
            if rutas_validas:
                return rutas_validas
    return []


def _segmentar_trafico(path: list[list[float]], escenario: str = "real") -> list[dict]:
    if len(path) < 2:
        return []

    segmentos = []
    # Limit number of traffic samples to avoid many external calls for long geometries
    max_segments = 4
    chunk_size = max(2, len(path) // max_segments)
    for i in range(0, len(path) - 1, chunk_size):
        chunk = path[i:min(len(path), i + chunk_size + 1)]
        if len(chunk) < 2:
            continue
        inicio = chunk[0]
        fin = chunk[-1]
        medio = chunk[len(chunk) // 2]
        flujo = traffic.flujo_punto(medio[0], medio[1], escenario=escenario)
        segmentos.append({
            "path": chunk,
            "trafico_nivel": flujo["nivel_trafico"],
            "trafico_texto": flujo["texto"],
            "velocidad_actual_kmh": flujo["velocidad_actual_kmh"],
            "zona_referencia": flujo.get("zona_referencia"),
            "dist_km": haversine_km(inicio[0], inicio[1], fin[0], fin[1]),
        })
    return segmentos


def calcular_rutas(
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    modo: str = "auto",
    escenario: str = "real",
) -> list[dict]:
    rutas = _fetch_provider_routes(olat, olon, dlat, dlon, modo, alternativas=3)
    if not rutas:
        return []

    flujo_global = traffic.flujo_punto((olat + dlat) / 2, (olon + dlon) / 2, escenario=escenario)
    nivel = flujo_global["nivel_trafico"]
    simulado = not flujo_global["es_dato_real"]
    vel = VELOCIDADES.get(modo, 52)
    factor = FACTORES_TRAFICO.get(nivel, 1.0) if modo in MODOS_MOTORIZADOS else 1.0

    salida = []
    for r in rutas:
        provider_has_traffic = bool(r.get("trafico_directo")) and escenario == "real"
        dur_realista = r.get("dur_min_original")
        if dur_realista is None:
            dur_realista = (r["dist_km"] / vel) * 60
        dur_final = r.get("dur_min") if provider_has_traffic else round(dur_realista * factor, 1)
        segmentos = _segmentar_trafico(r["path"], escenario)
        salida.append({
            **r,
            "dur_min": dur_final,
            "dur_min_original": round(dur_realista, 1),
            "modo": modo,
            "trafico_nivel": nivel,
            "trafico_texto": flujo_global["texto"] if provider_has_traffic else _TRAFICO_TEXTO.get(nivel, "Regular"),
            "trafico_simulado": simulado if not provider_has_traffic else False,
            "trafico_segmentos": segmentos,
            "fuente": r.get("fuente", "OSRM"),
            "fuente_trafico": r.get("fuente", "OSRM") if provider_has_traffic else ("Simulado" if simulado else "Real"),
            "escenario": escenario,
        })
    return salida


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    radio = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(2 * radio * asin(sqrt(a)), 3)
