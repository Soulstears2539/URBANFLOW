"""Endpoints de geocodificacion y busqueda de lugares."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from flask import Blueprint, jsonify, request

from flask import current_app

from ..external import geoapify, nominatim, tomtom
from ..external import local as local_provider
from ..services import recorder

bp = Blueprint("geocode", __name__, url_prefix="/api")


def _float(name):
    val = request.args.get(name)
    return float(val) if val not in (None, "") else None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    radio = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radio * asin(sqrt(a))


def _texto_resultado(r: dict) -> str:
    return " ".join(
        str(r.get(k, "") or "")
        for k in ("nombre", "name", "direccion_corta", "display_name", "ciudad", "categoria")
    ).lower()


def _rank_resultados(query: str, resultados: list[dict], lat: float | None, lon: float | None) -> list[dict]:
    q = query.strip().lower()
    tokens = [t for t in q.replace(",", " ").split() if t]
    aliases_quito = ("quito", "ladron de guevara", "ladrón de guevara", "la floresta", "mariscal", "pichincha")
    aliases_epn = (
        "epn",
        "escuela politecnica nacional",
        "escuela politécnica nacional",
        "politecnica nacional",
        "politécnica nacional",
    )

    def _score(r: dict):
        texto = _texto_resultado(r)
        score = 0

        if texto.startswith(q):
            score += 120
        if q and q in texto:
            score += 80
        score += sum(15 for t in tokens if t in texto)

        if any(alias in texto for alias in aliases_quito):
            score += 35

        if "epn" in q and any(alias in texto for alias in aliases_epn):
            score += 180
        if "escuela politecnica nacional" in q and "escuela politecnica nacional" in texto:
            score += 220
        if "escuela politécnica nacional" in q and "escuela politécnica nacional" in texto:
            score += 220

        if lat is not None and lon is not None and r.get("lat") is not None and r.get("lon") is not None:
            dist_km = _haversine_km(lat, lon, float(r["lat"]), float(r["lon"]))
            r["distancia_ref_km"] = round(dist_km, 2)
            if dist_km <= 3:
                score += 80
            elif dist_km <= 8:
                score += 45
            elif dist_km <= 20:
                score += 15
            else:
                score -= min(80, int(dist_km))

        return score

    return sorted(resultados, key=_score, reverse=True)


def _search_providers(query: str, lat: float | None, lon: float | None, limit: int = 8) -> list[dict]:
    # Intentar primero datos locales (paradas, rutas, búsquedas históricas)
    try:
        resultados_local = local_provider.fuzzy_search(query, lat, lon, limit=limit)
        if resultados_local:
            return resultados_local
    except Exception:
        # no bloquear el servicio por errores locales
        pass

    providers = current_app.config.get("SEARCH_PROVIDERS") or ["tomtom", "geoapify", "nominatim"]
    for provider in providers:
        if provider == "tomtom":
            resultados = tomtom.fuzzy_search(query, lat, lon, limit=limit)
        elif provider == "geoapify":
            resultados = geoapify.autocomplete(query, lat, lon, limit=limit)
        elif provider == "nominatim":
            resultados = [
                {
                    "nombre": r["name"],
                    "categoria": r["category"],
                    "direccion_corta": r["display_name"],
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "fuente_datos": "Nominatim",
                }
                for r in nominatim.search(query, lat, lon, limite=limit)
            ]
        else:
            resultados = []
        if resultados:
            return resultados
    return []


@bp.get("/geocode")
def geocode():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Parametro 'q' requerido"}), 400
    resultados = _search_providers(q, None, None, limit=1)
    res = resultados[0] if resultados else None
    recorder.registrar_busqueda(
        q,
        res.get("fuente_datos", "Search") if res else "Search",
        res["lat"] if res else None,
        res["lon"] if res else None,
    )
    if not res:
        return jsonify({"error": "Sin resultados"}), 404
    return jsonify({
        "lat": res["lat"],
        "lon": res["lon"],
        "query": q,
        "display_name": res.get("display_name") or res.get("direccion_corta") or res.get("nombre", q),
        "fuente_datos": res.get("fuente_datos", "Nominatim"),
    })


@bp.get("/search")
def search():
    q = request.args.get("q", "").strip()
    lat, lon = _float("lat"), _float("lon")
    if not q:
        return jsonify({"error": "Parametro 'q' requerido"}), 400
    resultados = _search_providers(q, lat, lon)
    resultados = _rank_resultados(q, resultados, lat, lon)
    primero = resultados[0] if resultados else None
    recorder.registrar_busqueda(
        q,
        primero.get("fuente_datos", "Search") if primero else "Search",
        primero["lat"] if primero else None,
        primero["lon"] if primero else None,
    )
    return jsonify({"resultados": resultados, "total": len(resultados)})


@bp.get("/search/suggestions")
def suggestions():
    q = request.args.get("q", "").strip()
    lat, lon = _float("lat"), _float("lon")
    if not q:
        return jsonify({"sugerencias": []})
    sug = _search_providers(q, lat, lon, limit=6)
    sug = _rank_resultados(q, sug, lat, lon)
    return jsonify({"sugerencias": sug, "total": len(sug)})


@bp.get("/nominatim/search")
def nominatim_search():
    q = request.args.get("q", "").strip()
    lat, lon = _float("lat"), _float("lon")
    if not q:
        return jsonify({"error": "Parametro 'q' requerido"}), 400
    resultados = nominatim.search(q, lat, lon)
    resultados = _rank_resultados(q, resultados, lat, lon)
    primero = resultados[0] if resultados else None
    recorder.registrar_busqueda(q, "Nominatim", primero["lat"] if primero else None, primero["lon"] if primero else None)
    return jsonify({"resultados": resultados, "total": len(resultados)})
