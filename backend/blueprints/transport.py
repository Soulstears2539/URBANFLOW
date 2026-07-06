"""Endpoints de transporte público (buses de Quito)."""
from __future__ import annotations

from html import escape

from flask import Blueprint, Response, jsonify, request

from ..auth import require_admin, require_admin_or_localhost
from ..external import overpass
from ..services import transport

bp = Blueprint("transport", __name__, url_prefix="/api")


_CITY_META = {
    "Quito": ("Quito", "Pichincha", "Ecuador"),
    "Guayaquil": ("Guayaquil", "Guayas", "Ecuador"),
    "Cuenca": ("Cuenca", "Azuay", "Ecuador"),
    "Riobamba": ("Riobamba", "Chimborazo", "Ecuador"),
}


def _route_location(fuente: str) -> tuple[str, str, str]:
    for city, meta in _CITY_META.items():
        if city.lower() in (fuente or "").lower():
            return meta
    return _CITY_META["Quito"]


def _matrix_export_rows() -> tuple[list[str], list[dict]]:
    rutas = transport.rutas_matriz()
    rows = []
    max_paradas = 5
    for ruta in rutas:
        ciudad, provincia, pais = _route_location(ruta.get("fuente", ""))
        paradas_por_sentido = {}
        for parada in ruta.get("paradas") or []:
            sentido = parada.get("sentido") or "ida"
            paradas_por_sentido.setdefault(sentido, []).append(parada)

        for sentido, paradas in paradas_por_sentido.items():
            paradas = sorted(paradas, key=lambda p: p.get("orden") or 0)
            max_paradas = max(max_paradas, len(paradas))
            rows.append({
                "ciudad": ciudad,
                "provincia": provincia,
                "pais": pais,
                "cooperativa": ruta.get("operator", ""),
                "linea": ruta.get("ref", ""),
                "ruta": ruta.get("name", ""),
                "sentido": sentido,
                "paradas": [p.get("nombre", "") for p in paradas],
                "horario": ruta.get("horario") or (ruta.get("horarios") or {}).get("lunes_viernes", ""),
                "intervalo_min": ruta.get("intervalo_min") or "",
                "flota": ruta.get("flota") or "",
                "tarifa": ruta.get("tarifa") or "",
            })

    columnas = [
        "ciudad", "provincia", "pais", "cooperativa", "linea", "ruta", "sentido",
        *[f"parada_{i}" for i in range(1, max_paradas + 1)],
        "horario", "intervalo_min", "flota", "tarifa",
    ]
    return columnas, rows


@bp.post("/transport")
def transporte():
    data = request.get_json(silent=True) or {}
    try:
        olat, olon = float(data["olat"]), float(data["olon"])
        dlat, dlon = float(data["dlat"]), float(data["dlon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se requieren olat, olon, dlat, dlon"}), 400
    radio_m = int(data.get("radio_m", 600))
    return jsonify(transport.buscar_transporte(olat, olon, dlat, dlon, radio_m))


@bp.get("/buses")
def buses():
    buses = transport.buses_summary()
    return jsonify({"buses": buses, "total": len(buses)})


@bp.get("/buses/<ref>")
def bus_detalle(ref):
    detalle = transport.bus_detail(ref)
    if not detalle:
        return jsonify({"error": f"Línea '{ref}' no encontrada"}), 404
    return jsonify(detalle)


@bp.post("/route/bus")
def route_bus():
    data = request.get_json(silent=True) or {}
    try:
        olat, olon = float(data["olat"]), float(data["olon"])
        dlat, dlon = float(data["dlat"]), float(data["dlon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se requieren olat, olon, dlat, dlon"}), 400
    radio_m = int(data.get("radio_m", 600))
    return jsonify(transport.ruta_bus_pasos(olat, olon, dlat, dlon, radio_m))


@bp.get("/transport/matrix/template")
def matrix_template():
    return jsonify(transport.plantilla_matriz())


@bp.get("/transport/matrix")
def matrix_routes():
    rutas = transport.rutas_matriz()
    total = len(rutas)
    compact = request.args.get("compact", "0").lower() in {"1", "true", "yes", "on"}
    if compact:
        try:
            limit = max(1, min(int(request.args.get("limit", 25)), 100))
        except ValueError:
            limit = 25
        resumen = [
            {
                "id": ruta.get("id"),
                "ref": ruta.get("ref"),
                "name": ruta.get("name"),
                "operator": ruta.get("operator"),
                "tipo": ruta.get("tipo"),
                "fuente": ruta.get("fuente"),
                "n_paradas": len(ruta.get("paradas") or []),
            }
            for ruta in rutas[:limit]
        ]
        return jsonify({"rutas": resumen, "total": total, "mostradas": len(resumen)})
    return jsonify({"rutas": rutas, "total": total})


@bp.get("/transport/matrix/export.xls")
def matrix_export_excel():
    columnas, rows = _matrix_export_rows()
    header = "".join(
        f"<th>{escape(col)}</th>"
        for col in columnas
    )
    body_rows = []
    for row in rows:
        values = []
        for col in columnas:
            if col.startswith("parada_"):
                idx = int(col.split("_", 1)[1]) - 1
                values.append(row["paradas"][idx] if idx < len(row["paradas"]) else "")
            else:
                values.append(row.get(col, ""))
        body_rows.append(
            "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>"
        )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    table {{ border-collapse: collapse; font-family: Calibri, Arial, sans-serif; }}
    th {{
      background: #1f8a5b;
      border: 1px solid #d9ead3;
      color: #ffffff;
      font-weight: 700;
      padding: 6px 10px;
      text-align: center;
    }}
    td {{
      border: 1px solid #d9ead3;
      padding: 5px 8px;
      mso-number-format: "\\@";
    }}
  </style>
</head>
<body>
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</body>
</html>"""
    return Response(
        html,
        mimetype="application/vnd.ms-excel; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=urbanflow_rutas_cargadas.xls"},
    )


@bp.post("/transport/matrix/import")
@require_admin_or_localhost
def matrix_import():
    if "file" not in request.files:
        return jsonify({"error": "Se requiere archivo CSV/XLS/XLSX en campo 'file'"}), 400
    reemplazar = request.form.get("reemplazar", "0").lower() in {"1", "true", "yes", "on"}
    file = request.files["file"]
    raw = file.read()
    try:
        result = transport.importar_matriz_archivo(raw, filename=file.filename or "", reemplazar=reemplazar)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@bp.post("/transport/matrix/manual")
@require_admin_or_localhost
def matrix_manual_import():
    data = request.get_json(silent=True) or {}
    try:
        result = transport.importar_ruta_manual(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@bp.post("/transport/osm/import")
@require_admin
def osm_import():
    scope = (request.args.get("scope") or "quito").lower()
    if scope in {"ecuador", "all", "principales"}:
        rutas = overpass.fetch_ecuador_transport_routes()
    else:
        rutas = overpass.fetch_quito_transport_routes()
    result = transport.importar_rutas_osm(rutas, reemplazar_osm=True)
    return jsonify({"ok": True, "scope": scope, "rutas_osm_encontradas": len(rutas), **result})
