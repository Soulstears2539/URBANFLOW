"""Endpoints de administración: gestión de claves de API.

Todos requieren una clave de administrador.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..auth import require_admin
from ..extensions import db
from ..models import ApiKey

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/keys")
@require_admin
def listar_keys():
    keys = ApiKey.query.order_by(ApiKey.id.asc()).all()
    return jsonify({"keys": [k.to_dict() for k in keys], "total": len(keys)})


@bp.post("/keys")
@require_admin
def crear_key():
    d = request.get_json(silent=True) or {}
    nombre = d.get("name", "API Key")
    es_admin = bool(d.get("is_admin", False))
    nueva = ApiKey.generate(nombre, es_admin)
    db.session.add(nueva)
    db.session.commit()
    # Se muestra el secreto solo en la creación.
    return jsonify({"ok": True, "key": nueva.to_dict(include_secret=True)}), 201


@bp.delete("/keys/<int:key_id>")
@require_admin
def revocar_key(key_id):
    key = ApiKey.query.get_or_404(key_id)
    if key.id == g.api_key.id:
        return jsonify({"error": "No puedes revocar tu propia clave en uso"}), 400
    key.active = False
    db.session.commit()
    return jsonify({"ok": True, "mensaje": f"Clave {key_id} revocada"})
