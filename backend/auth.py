"""Autenticación y autorización por API key.

Mejora sobre el proyecto original: aquí la autenticación SÍ se aplica.
- ``require_api_key``  -> exige cualquier clave activa.
- ``require_admin``    -> exige una clave con privilegios de administrador.
- ``optional_api_key`` -> registra la clave si viene, pero no obliga.

La clave se envía en la cabecera ``X-API-Key`` o como ``?api_key=``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

from flask import current_app, g, jsonify, request

from .extensions import db
from .models import ApiKey


def _extract_key() -> str | None:
    key = request.headers.get("X-API-Key")
    if not key:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    if not key:
        key = request.args.get("api_key")
    return key.strip() if key else None


def _resolve_key(raw: str | None) -> ApiKey | None:
    if not raw:
        return None
    api_key = ApiKey.query.filter_by(key=raw, active=True).first()
    if api_key:
        api_key.last_used = datetime.now(timezone.utc)
        api_key.requests = (api_key.requests or 0) + 1
        db.session.commit()
    return api_key


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = _resolve_key(_extract_key())
        if api_key is None:
            return jsonify({"error": "API key requerida o inválida"}), 401
        g.api_key = api_key
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        api_key = _resolve_key(_extract_key())
        if api_key is None:
            return jsonify({"error": "API key requerida o inválida"}), 401
        if not api_key.is_admin:
            return jsonify({"error": "Se requieren privilegios de administrador"}), 403
        g.api_key = api_key
        return fn(*args, **kwargs)

    return wrapper


def _is_local_request() -> bool:
    remote = request.remote_addr or ""
    host = (request.host or "").split(":", 1)[0]
    return remote in {"127.0.0.1", "::1"} or host in {"127.0.0.1", "localhost"}


def require_admin_or_localhost(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _is_local_request():
            g.api_key = None
            return fn(*args, **kwargs)

        api_key = _resolve_key(_extract_key())
        if api_key is None:
            return jsonify({"error": "API key requerida o invalida"}), 401
        if not api_key.is_admin:
            return jsonify({"error": "Se requieren privilegios de administrador"}), 403
        g.api_key = api_key
        return fn(*args, **kwargs)

    return wrapper


def optional_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.api_key = _resolve_key(_extract_key())
        return fn(*args, **kwargs)

    return wrapper


def ensure_admin_key() -> ApiKey:
    """Garantiza que exista al menos una clave admin; la crea si falta.

    Si ``ADMIN_API_KEY`` está en el entorno, la usa como clave fija.
    Devuelve la clave admin (para mostrarla en logs al iniciar).
    """
    existing = ApiKey.query.filter_by(is_admin=True, active=True).first()
    if existing:
        return existing

    fixed = current_app.config.get("ADMIN_API_KEY")
    api_key = ApiKey.generate(name="Administrador", is_admin=True)
    if fixed:
        api_key.key = fixed
    db.session.add(api_key)
    db.session.commit()
    return api_key
