"""Servicio de trafico y simulacion en tiempo real para Quito."""
from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from flask import current_app

from ..data.quito_buses import QUITO_BUSES
from ..external import google_routes, here, tomtom

QUITO_TRAFFIC_ZONES = [
    {"id": "z01", "nombre": "La Marin", "lat": -0.2230, "lon": -78.5090, "nivel_base": 3, "vel_libre": 40},
    {"id": "z02", "nombre": "El Labrador", "lat": -0.1640, "lon": -78.4860, "nivel_base": 2, "vel_libre": 50},
    {"id": "z03", "nombre": "Naciones Unidas", "lat": -0.1760, "lon": -78.4830, "nivel_base": 3, "vel_libre": 45},
    {"id": "z04", "nombre": "El Inca", "lat": -0.1500, "lon": -78.4790, "nivel_base": 2, "vel_libre": 50},
    {"id": "z05", "nombre": "La Magdalena", "lat": -0.2370, "lon": -78.5180, "nivel_base": 2, "vel_libre": 45},
    {"id": "z06", "nombre": "Quitumbe", "lat": -0.2980, "lon": -78.5510, "nivel_base": 2, "vel_libre": 50},
    {"id": "z07", "nombre": "Carcelen", "lat": -0.0980, "lon": -78.4760, "nivel_base": 2, "vel_libre": 50},
    {"id": "z08", "nombre": "La Alameda", "lat": -0.2130, "lon": -78.5050, "nivel_base": 3, "vel_libre": 40},
    {"id": "z09", "nombre": "La Colmena", "lat": -0.2250, "lon": -78.5180, "nivel_base": 3, "vel_libre": 35},
    {"id": "z10", "nombre": "El Ejido", "lat": -0.2095, "lon": -78.4972, "nivel_base": 3, "vel_libre": 40},
    {"id": "z11", "nombre": "Av. Patria", "lat": -0.2060, "lon": -78.4950, "nivel_base": 3, "vel_libre": 45},
    {"id": "z12", "nombre": "Av. America", "lat": -0.1980, "lon": -78.4980, "nivel_base": 2, "vel_libre": 50},
    {"id": "z13", "nombre": "Plaza Grande", "lat": -0.2200, "lon": -78.5125, "nivel_base": 3, "vel_libre": 30},
    {"id": "z14", "nombre": "Real Audiencia", "lat": -0.1300, "lon": -78.4920, "nivel_base": 2, "vel_libre": 50},
    {"id": "z15", "nombre": "Cotocollao", "lat": -0.1090, "lon": -78.4960, "nivel_base": 2, "vel_libre": 50},
    {"id": "z16", "nombre": "Carapungo", "lat": -0.0850, "lon": -78.4500, "nivel_base": 2, "vel_libre": 55},
    {"id": "z17", "nombre": "Los Chillos", "lat": -0.3060, "lon": -78.4490, "nivel_base": 2, "vel_libre": 55},
    {"id": "z18", "nombre": "Tumbaco", "lat": -0.2100, "lon": -78.4000, "nivel_base": 2, "vel_libre": 60},
    {"id": "z19", "nombre": "San Bartolo", "lat": -0.2650, "lon": -78.5300, "nivel_base": 2, "vel_libre": 45},
    {"id": "z20", "nombre": "Av. 10 de Agosto", "lat": -0.1900, "lon": -78.4920, "nivel_base": 3, "vel_libre": 45},
    {"id": "z21", "nombre": "El Recreo", "lat": -0.2520, "lon": -78.5210, "nivel_base": 3, "vel_libre": 40},
    {"id": "z22", "nombre": "Av. Occidental", "lat": -0.1850, "lon": -78.5050, "nivel_base": 2, "vel_libre": 55},
    {"id": "z23", "nombre": "La Carolina", "lat": -0.1820, "lon": -78.4820, "nivel_base": 3, "vel_libre": 45},
    {"id": "z24", "nombre": "Ponceano", "lat": -0.1100, "lon": -78.4880, "nivel_base": 2, "vel_libre": 50},
    {"id": "z25", "nombre": "Av. De los Shyris", "lat": -0.1700, "lon": -78.4850, "nivel_base": 3, "vel_libre": 50},
]

_NIVEL_TEXTO = {1: "Bueno", 2: "Regular", 3: "Malo"}


def normalizar_escenario(escenario: str | None) -> str:
    valor = (escenario or "real").strip().lower()
    if valor == "auto":
        valor = "real"
    return valor if valor in {"real", "bueno", "regular", "malo"} else "real"


def _nivel_desde_relativo(actual: float, libre: float) -> int:
    if libre <= 0:
        return 2
    ratio = actual / libre
    if ratio >= 0.75:
        return 1
    if ratio >= 0.45:
        return 2
    return 3


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radio = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radio * asin(sqrt(a))


def _zona_mas_cercana(lat: float, lon: float) -> dict:
    return min(QUITO_TRAFFIC_ZONES, key=lambda z: _dist_km(lat, lon, z["lat"], z["lon"]))


def _nivel_simulado(lat: float, lon: float, nivel_base: int) -> int:
    ahora = datetime.now(timezone.utc)
    hora = (ahora.hour - 5) % 24

    if hora in range(6, 10) or hora in range(17, 21):
        ajuste_hora = 1
    elif hora in range(10, 16):
        ajuste_hora = 0
    elif hora in range(21, 24):
        ajuste_hora = -1
    else:
        ajuste_hora = -1

    semilla_espacial = int(abs(lat * 1000) + abs(lon * 1000))
    ajuste_espacial = (-1, 0, 1)[semilla_espacial % 3]

    bloque_minuto = ahora.minute // 10
    ajuste_temporal = (-1, 0, 1)[(bloque_minuto + semilla_espacial) % 3]

    nivel = nivel_base + ajuste_hora
    if ajuste_hora >= 0:
      nivel += max(0, ajuste_espacial)
    else:
      nivel += min(0, ajuste_espacial)
    nivel += 1 if (nivel_base == 3 and ajuste_temporal > 0) else 0
    nivel += -1 if (nivel_base == 2 and ajuste_temporal < 0) else 0
    return max(1, min(3, nivel))


def _interpolar_punto(paradas: list[tuple[str, float, float]], progreso: float) -> tuple[float, float]:
    if not paradas:
        return -0.2200, -78.5125
    if len(paradas) == 1:
        return paradas[0][1], paradas[0][2]

    distancias = []
    total = 0.0
    for i in range(len(paradas) - 1):
        _, lat1, lon1 = paradas[i]
        _, lat2, lon2 = paradas[i + 1]
        tramo = _dist_km(lat1, lon1, lat2, lon2)
        distancias.append(tramo)
        total += tramo

    if total <= 0:
        return paradas[0][1], paradas[0][2]

    objetivo = max(0.0, min(0.9999, progreso)) * total
    acumulado = 0.0
    for i, tramo in enumerate(distancias):
        if acumulado + tramo >= objetivo:
            fraccion = 0.0 if tramo == 0 else (objetivo - acumulado) / tramo
            _, lat1, lon1 = paradas[i]
            _, lat2, lon2 = paradas[i + 1]
            return lat1 + (lat2 - lat1) * fraccion, lon1 + (lon2 - lon1) * fraccion
        acumulado += tramo

    return paradas[-1][1], paradas[-1][2]


def flujo_punto(
    lat: float,
    lon: float,
    nivel_base: int | None = None,
    vel_libre: float | None = None,
    escenario: str | None = None,
) -> dict:
    """Devuelve el flujo de trafico de un punto con fallback ordenado."""
    escenario = normalizar_escenario(escenario)
    data, proveedor, fuente, real = None, "Simulado", "SIMULADO", False
    if escenario == "real":
        cfg = {
            "google": ("Google", "GOOGLE_TRAFFIC", google_routes.traffic_flow),
            "here": ("HERE", "HERE_LIVE", here.flow),
            "tomtom": ("TomTom", "TOMTOM_LIVE", tomtom.routing_traffic_flow),
        }
        for provider in current_providers():
            meta = cfg.get(provider)
            if not meta:
                continue
            proveedor, fuente, getter = meta
            data = getter(lat, lon)
            if data:
                real = True
                break

    zona = _zona_mas_cercana(lat, lon)
    nivel_base = zona["nivel_base"] if nivel_base is None else nivel_base
    vel_libre = zona["vel_libre"] if vel_libre is None else vel_libre

    if data is None:
        if escenario == "bueno":
            nivel = 1
        elif escenario == "regular":
            nivel = 2
        elif escenario == "malo":
            nivel = 3
        else:
            nivel = _nivel_simulado(lat, lon, nivel_base)
        factor_velocidad = {1: 0.92, 2: 0.58, 3: 0.32}[nivel]
        return {
            "nivel_trafico": nivel,
            "velocidad_actual_kmh": round(vel_libre * factor_velocidad, 1),
            "velocidad_libre_kmh": vel_libre,
            "retraso_relativo": {1: 0.1, 2: 0.45, 3: 0.7}[nivel],
            "fuente_datos": "SIMULADO_CONTROLADO" if escenario != "real" else "SIMULADO",
            "proveedor": "Manual" if escenario != "real" else "Simulado",
            "es_dato_real": False,
            "texto": _NIVEL_TEXTO[nivel],
            "zona_referencia": zona["nombre"],
            "escenario": escenario,
        }

    nivel = _nivel_desde_relativo(data["velocidad_actual_kmh"], data["velocidad_libre_kmh"])
    return {
        "nivel_trafico": nivel,
        "velocidad_actual_kmh": data["velocidad_actual_kmh"],
        "velocidad_libre_kmh": data["velocidad_libre_kmh"],
        "retraso_relativo": data["retraso_relativo"],
        "fuente_datos": fuente,
        "proveedor": proveedor,
        "es_dato_real": real,
        "texto": _NIVEL_TEXTO[nivel],
        "zona_referencia": zona["nombre"],
        "escenario": "real",
    }


def current_providers() -> list[str]:
    return list(current_app.config.get("TRAFFIC_PROVIDERS") or ["google", "here", "tomtom"])


def nivel_punto(lat: float, lon: float) -> tuple[int, bool]:
    flujo = flujo_punto(lat, lon)
    return flujo["nivel_trafico"], not flujo["es_dato_real"]


def mapa_trafico(escenario: str | None = None) -> dict:
    escenario = normalizar_escenario(escenario)
    zonas = []
    for z in QUITO_TRAFFIC_ZONES:
        flujo = flujo_punto(z["lat"], z["lon"], z["nivel_base"], z["vel_libre"], escenario)
        retraso_min = round(flujo["retraso_relativo"] * 10, 1)
        zonas.append({
            "zona_id": z["id"],
            "nombre": z["nombre"],
            "lat": z["lat"],
            "lon": z["lon"],
            "nivel_trafico": flujo["nivel_trafico"],
            "velocidad_actual_kmh": flujo["velocidad_actual_kmh"],
            "velocidad_libre_kmh": flujo["velocidad_libre_kmh"],
            "retraso_min": retraso_min,
            "fuente_datos": flujo["fuente_datos"],
            "es_dato_real": flujo["es_dato_real"],
            "proveedor": flujo["proveedor"],
            "texto": flujo["texto"],
        })
    fuente_global = "REAL" if any(z["es_dato_real"] for z in zonas) else "SIMULADO"
    promedio = round(sum(z["nivel_trafico"] for z in zonas) / len(zonas), 2)
    return {
        "zonas": zonas,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fuente": fuente_global,
        "nivel_promedio": promedio,
        "total": len(zonas),
        "escenario": escenario,
    }


def vehiculos_simulados(escenario: str | None = None) -> list[dict]:
    """Genera buses y metro simulados moviendose por la ciudad."""
    escenario = normalizar_escenario(escenario)
    ahora = datetime.now(timezone.utc)
    segundos_dia = ahora.hour * 3600 + ahora.minute * 60 + ahora.second
    vehiculos = []

    for i, linea in enumerate(QUITO_BUSES):
        paradas = linea["paradas"]
        lat_ref, lon_ref = paradas[0][1], paradas[0][2]
        nivel = flujo_punto(lat_ref, lon_ref, escenario=escenario)["nivel_trafico"]
        velocidad = round(max(8, 36 - (nivel * 7) + (i % 4)), 1)
        cantidad = 2 if linea["tipo"] in {"subway", "trolleybus"} else 3
        ciclo = 1400 + (i * 110) + (nivel * 90)
        ida = paradas
        vuelta = list(reversed(ida))

        for j in range(cantidad):
            progreso = ((segundos_dia + (j * (ciclo // cantidad))) % ciclo) / ciclo
            sentido_ida = ((segundos_dia // ciclo) + j) % 2 == 0
            lat, lon = _interpolar_punto(ida if sentido_ida else vuelta, progreso)
            vehiculos.append({
                "vehicle_id": f"sim-{linea['ref'].lower()}-{j + 1}",
                "cooperativa": linea["operator"],
                "route_id": linea["ref"],
                "route_name": linea["name"],
                "tipo": linea["tipo"],
                "color": linea["colour"],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "speed_kmh": velocidad,
                "ocupacion": ["Baja", "Media", "Alta"][(i + j + ahora.minute) % 3],
                "sentido": "ida" if sentido_ida else "vuelta",
                "simulado": True,
                "trafico_texto": _NIVEL_TEXTO[nivel],
                "escenario": escenario,
                "timestamp": ahora.isoformat(),
            })

    return vehiculos
