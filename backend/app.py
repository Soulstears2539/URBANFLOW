"""Fábrica de la aplicación Flask de UrbanFlow OSM.

Crea la app, inicializa extensiones, registra blueprints, sirve el frontend
estático y prepara la base de datos (tablas + clave admin + modelo ML).
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .auth import ensure_admin_key
from .config import Config
from .extensions import cors, db
from .services import ml

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _register_blueprints(app: Flask) -> None:
    from .blueprints import admin, geocode, gtfs, ml as ml_bp, ops, overpass, poi, routes, traffic, transport

    for modulo in (geocode, routes, transport, traffic, overpass, gtfs, ml_bp, ops, poi, admin):
        app.register_blueprint(modulo.bp)


def _register_frontend(app: Flask) -> None:
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(FRONTEND_DIR, filename)


def _register_errors(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Recurso no encontrado"}), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": "Error interno del servidor"}), 500


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config)

    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}})

    _register_blueprints(app)
    _register_frontend(app)
    _register_errors(app)

    with app.app_context():
        db.create_all()
        admin_key = ensure_admin_key()
        ml.init_modelo()
        app.config["_ADMIN_KEY_VALUE"] = admin_key.key

    return app
