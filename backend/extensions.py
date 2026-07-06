"""Extensiones compartidas (instancias únicas) de la aplicación.

Se inicializan aquí sin enlazar a la app para evitar imports circulares;
``init_app`` se llama en la fábrica de la aplicación.
"""
from __future__ import annotations

from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
cors = CORS()
