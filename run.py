"""Punto de arranque de UrbanFlow OSM.

Uso:
    python run.py
La app sirve la API y el frontend en http://HOST:PORT/ (por defecto 127.0.0.1:5050).
"""
from __future__ import annotations

from backend.app import create_app
from backend.config import Config

app = create_app(Config)


if __name__ == "__main__":
    admin_key = app.config.get("_ADMIN_KEY_VALUE", "(ver base de datos)")
    print("=" * 64)
    print("  UrbanFlow OSM — plataforma de movilidad urbana")
    print(f"  Frontend : http://{Config.HOST}:{Config.PORT}/")
    print(f"  API base : http://{Config.HOST}:{Config.PORT}/api")
    print(f"  Admin key: {admin_key}")
    print("  (Envía la clave en la cabecera X-API-Key para endpoints admin)")
    print("=" * 64)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, use_reloader=False)
