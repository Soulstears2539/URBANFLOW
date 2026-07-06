"""Proveedor de búsqueda local: indexa registros guardados en la BD.

Busca en MobilityRecord (paradas GTFS, búsquedas históricas, rutas) y devuelve
resultados con la forma esperada por el frontend.
"""
from __future__ import annotations

from math import radians, sin, cos, sqrt, asin
from typing import List

from flask import current_app

from ..extensions import db
from ..models import MobilityRecord


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _match_score(query: str, texto: str) -> int:
    q = query.lower().strip()
    t = (texto or "").lower()
    if not q or not t:
        return 0
    score = 0
    if t.startswith(q):
        score += 120
    if q in t:
        score += 60
    for token in q.replace(",", " ").split():
        if token and token in t:
            score += 10
    return score


def fuzzy_search(query: str, lat: float | None, lon: float | None, limit: int = 8) -> List[dict]:
    """Busca coincidencias en MobilityRecord y devuelve lista de dicts.

    Prioriza paradas GTFS y registros con coordenadas.
    """
    q = (query or "").strip()
    if not q:
        return []

    # Buscar registros útiles (gtfs_parada, externo, busqueda, ruta)
    tipos = ("gtfs_parada", "externo", "busqueda", "ruta")
    registros = (
        db.session.query(MobilityRecord)
        .filter(MobilityRecord.tipo.in_(tipos))
        .filter(MobilityRecord.origen_query.isnot(None))
        .limit(5000)
        .all()
    )

    candidatos = []
    for r in registros:
        texto = r.origen_query or r.destino_query or ""
        score = _match_score(q, texto)
        if score <= 0:
            continue
        item = {
            "nombre": texto,
            "direccion_corta": texto,
            "lat": r.olat,
            "lon": r.olon,
            "fuente_datos": r.fuente_busqueda or r.fuente_ruta or "Local",
            "tipo": r.tipo,
            "score": score,
        }
        if lat is not None and lon is not None and r.olat is not None and r.olon is not None:
            item["distancia_km"] = round(_haversine_km(lat, lon, r.olat, r.olon), 3)
            # penalizar por distancia
            item["score"] = item["score"] - int(item["distancia_km"] * 2)
        candidatos.append(item)

    # Ordenar por score y distancia
    candidatos.sort(key=lambda x: (x.get("score", 0), -bool(x.get("lat"))), reverse=True)
    # Mapear al formato esperado por geocode ranking
    res = []
    for c in candidatos[:limit]:
        res.append({
            "nombre": c["nombre"],
            "display_name": c.get("direccion_corta") or c["nombre"],
            "direccion_corta": c.get("direccion_corta"),
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "fuente_datos": c.get("fuente_datos", "Local"),
            "categoria": c.get("tipo"),
        })

    return res


def autocomplete(query: str, lat: float | None, lon: float | None, limit: int = 6) -> List[dict]:
    return fuzzy_search(query, lat, lon, limit=limit)
