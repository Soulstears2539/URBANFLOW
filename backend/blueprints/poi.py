"""Blueprint de POI cercanos via SerpApi."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from backend.external.serpapi import search_places

logger = logging.getLogger(__name__)

bp = Blueprint("poi", __name__, url_prefix="/api/poi")


@bp.get("/search")
def search_poi():
    query = request.args.get("query", "").strip()
    lat_str = request.args.get("lat", "").strip()
    lng_str = request.args.get("lng", "").strip()
    max_results = request.args.get("max", 10, type=int)

    if not query:
        return jsonify({"error": "query requerido"}), 400
    if not lat_str or not lng_str:
        return jsonify({"error": "lat y lng requeridos"}), 400

    try:
        lat = float(lat_str)
        lng = float(lng_str)
    except ValueError:
        return jsonify({"error": "lat y lng deben ser numeros"}), 400

    if max_results < 1 or max_results > 50:
        max_results = 10

    result = search_places(
        query=query,
        latitude=lat,
        longitude=lng,
        api_key=current_app.config.get("SERPAPI_API_KEY"),
        max_results=max_results,
    )
    logger.info("POI search: %s @ (%s,%s) -> %s", query, lat, lng, result.get("count"))
    return jsonify(result), 200


@bp.get("/types")
def poi_types():
    types = {
        "coffee": ["Coffee", "Cafe", "Coffee shop"],
        "food": ["Restaurant", "Pizza", "Chinese", "Japanese", "Mexican", "Italian"],
        "medical": ["Hospital", "Pharmacy", "Clinic", "Dental"],
        "transport": ["Gas Station", "Parking", "Car Rental"],
        "entertainment": ["Movie Theater", "Park", "Museum", "Zoo"],
        "shopping": ["Supermarket", "Shopping Mall", "Bookstore"],
        "accommodation": ["Hotel", "Hostel", "Bed & Breakfast"],
    }
    return jsonify({"success": True, "types": types, "total_categories": len(types)}), 200


@bp.post("/nearby")
def nearby_poi():
    data = request.get_json(silent=True) or {}
    try:
        lat = float(data.get("lat", 0))
        lng = float(data.get("lng", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "lat y lng deben ser numeros"}), 400

    queries = data.get("queries", ["Coffee"])
    max_per_query = int(data.get("max_per_query", 5))

    if not lat or not lng:
        return jsonify({"error": "lat y lng requeridos"}), 400
    if max_per_query < 1 or max_per_query > 50:
        max_per_query = 5

    results_by_type = {}
    for query in queries:
        results_by_type[query] = search_places(
            query=query,
            latitude=lat,
            longitude=lng,
            api_key=current_app.config.get("SERPAPI_API_KEY"),
            max_results=max_per_query,
        )

    logger.info("POI nearby: %s queries @ (%s,%s)", len(queries), lat, lng)
    return jsonify({
        "success": True,
        "lat": lat,
        "lng": lng,
        "results_by_type": results_by_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200
