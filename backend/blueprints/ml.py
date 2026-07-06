"""Endpoints de Machine Learning.

Lectura pública; entrenamiento, importación y escritura de histórico requieren
privilegios de administrador (require_admin).
"""
from __future__ import annotations

import io

import pandas as pd
from flask import Blueprint, jsonify, request

from ..auth import require_admin
from ..extensions import db
from ..external.security import SecurityError, validate_upload_filename
from ..models import MobilityRecord
from ..services import ml, recorder

bp = Blueprint("ml", __name__, url_prefix="/api/ml")

_DEPRECATED = {"error": "Endpoint obsoleto. Usa /api/ml/entrenar, /predecir, /historico."}


@bp.get("/historico")
def historico():
    limite = min(int(request.args.get("limite", 1000)), 10000)
    rows = MobilityRecord.query.order_by(MobilityRecord.id.desc()).limit(limite).all()
    return jsonify({"total": MobilityRecord.query.count(), "rows": [r.to_dict() for r in rows]})


@bp.post("/historico/busqueda")
@require_admin
def historico_busqueda():
    d = request.get_json(silent=True) or {}
    rec = recorder.registrar_busqueda(
        d.get("origen_query", ""), d.get("fuente_busqueda", "manual"),
        d.get("olat"), d.get("olon"), d.get("ciudad", "Quito"),
    )
    return jsonify({"ok": True, "id": rec.id}), 201


@bp.post("/historico/ruta")
@require_admin
def historico_ruta():
    d = request.get_json(silent=True) or {}
    rec = recorder.registrar_ruta(d, d.get("ciudad", "Quito"))
    return jsonify({"ok": True, "id": rec.id}), 201


@bp.post("/importar")
@require_admin
def importar():
    archivo = request.files.get("file")
    if not archivo:
        return jsonify({"error": "Adjunta un archivo 'file' (CSV)"}), 400
    try:
        validate_upload_filename(archivo.filename)
    except SecurityError as exc:
        return jsonify({"error": str(exc)}), 400

    raw = archivo.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        return jsonify({"error": "El archivo supera 10 MB"}), 413

    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"CSV inválido: {exc}"}), 400

    importadas = 0
    columnas = {c.name for c in MobilityRecord.__table__.columns}
    for _, fila in df.iterrows():
        campos = {k: (None if pd.isna(v) else v) for k, v in fila.items() if k in columnas}
        campos.pop("id", None)
        campos.setdefault("tipo", "externo")
        db.session.add(MobilityRecord(**campos))
        importadas += 1
    db.session.commit()
    return jsonify({"importadas": importadas})


@bp.post("/entrenar")
@require_admin
def entrenar():
    resultado = ml.entrenar()
    code = 200 if resultado.get("ok") else 422
    return jsonify(resultado), code


@bp.post("/predecir")
def predecir():
    d = request.get_json(silent=True) or {}
    try:
        distancia = float(d["distancia_km"])
        base = float(d["duracion_base_min"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se requieren distancia_km y duracion_base_min"}), 400
    return jsonify(ml.predecir(distancia, base, d.get("nivel_trafico", 1),
                               d.get("hora"), d.get("dia_semana")))


@bp.get("/estado")
def estado():
    return jsonify(ml.estado())


# --- Endpoints obsoletos (compatibilidad): responden 410 GONE ---
@bp.route("/data", methods=["GET", "POST"])
def data_gone():
    return jsonify(_DEPRECATED), 410


@bp.post("/train")
def train_gone():
    return jsonify(_DEPRECATED), 410


@bp.post("/predict")
def predict_gone():
    return jsonify(_DEPRECATED), 410
