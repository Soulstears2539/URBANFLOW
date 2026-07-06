"""Modelos de base de datos (SQLAlchemy).

Reemplaza la antigua persistencia en CSV (historico_movilidad.csv) por tablas
relacionales. Esto mejora integridad, consultas y escalabilidad.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MobilityRecord(db.Model):
    """Registro operativo e histórico (búsquedas, rutas, tráfico, GPS, GTFS).

    Equivale a una fila del antiguo ``historico_movilidad.csv`` pero tipada.
    """

    __tablename__ = "mobility_records"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=_utcnow, index=True)
    tipo = db.Column(db.String(32), index=True)  # busqueda|ruta|externo|gtfs_parada|gps_vehiculo
    ciudad = db.Column(db.String(64), default="Quito")

    origen_query = db.Column(db.String(255))
    destino_query = db.Column(db.String(255))
    fuente_busqueda = db.Column(db.String(64))

    olat = db.Column(db.Float)
    olon = db.Column(db.Float)
    dlat = db.Column(db.Float)
    dlon = db.Column(db.Float)

    distancia_km = db.Column(db.Float)
    duracion_base_min = db.Column(db.Float)
    duracion_trafico_min = db.Column(db.Float)
    duracion_estimacion_min = db.Column(db.Float)
    retraso_trafico_min = db.Column(db.Float)
    nivel_trafico = db.Column(db.Integer)

    fuente_ruta = db.Column(db.String(64))
    fuente_trafico = db.Column(db.String(64))
    proveedor_trafico = db.Column(db.String(64))
    es_dato_real = db.Column(db.Boolean, default=False)

    hora = db.Column(db.Integer, index=True)
    dia_semana = db.Column(db.Integer, index=True)
    tiempo_real_min = db.Column(db.Float)  # target de ML

    # Columnas en el mismo orden que el CSV legado (para import/export).
    CSV_COLS = [
        "id", "timestamp", "tipo", "ciudad", "origen_query", "destino_query",
        "fuente_busqueda", "olat", "olon", "dlat", "dlon", "distancia_km",
        "duracion_base_min", "duracion_trafico_min", "duracion_estimacion_min",
        "retraso_trafico_min", "nivel_trafico", "fuente_ruta", "fuente_trafico",
        "proveedor_trafico", "es_dato_real", "hora", "dia_semana", "tiempo_real_min",
    ]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "tipo": self.tipo,
            "ciudad": self.ciudad,
            "origen_query": self.origen_query,
            "destino_query": self.destino_query,
            "fuente_busqueda": self.fuente_busqueda,
            "olat": self.olat,
            "olon": self.olon,
            "dlat": self.dlat,
            "dlon": self.dlon,
            "distancia_km": self.distancia_km,
            "duracion_base_min": self.duracion_base_min,
            "duracion_trafico_min": self.duracion_trafico_min,
            "duracion_estimacion_min": self.duracion_estimacion_min,
            "retraso_trafico_min": self.retraso_trafico_min,
            "nivel_trafico": self.nivel_trafico,
            "fuente_ruta": self.fuente_ruta,
            "fuente_trafico": self.fuente_trafico,
            "proveedor_trafico": self.proveedor_trafico,
            "es_dato_real": self.es_dato_real,
            "hora": self.hora,
            "dia_semana": self.dia_semana,
            "tiempo_real_min": self.tiempo_real_min,
        }


class ApiKey(db.Model):
    """Clave de API para autenticar y autorizar peticiones.

    ``is_admin`` habilita los endpoints administrativos.
    """

    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), default="API Key")
    is_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    last_used = db.Column(db.DateTime)
    requests = db.Column(db.Integer, default=0)

    @staticmethod
    def generate(name: str = "API Key", is_admin: bool = False) -> "ApiKey":
        prefix = "adm" if is_admin else "urb"
        return ApiKey(
            key=f"{prefix}_{secrets.token_hex(16)}",
            name=name,
            is_admin=is_admin,
            active=True,
        )

    def to_dict(self, include_secret: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "is_admin": self.is_admin,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "requests": self.requests,
        }
        if include_secret:
            data["key"] = self.key
        else:
            data["key_preview"] = f"{self.key[:8]}...{self.key[-4:]}"
        return data


class VehiclePosition(db.Model):
    """Posición GPS de vehículos de cooperativas (ahora persistida en DB)."""

    __tablename__ = "vehicle_positions"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.String(64), index=True)
    cooperativa = db.Column(db.String(120))
    route_id = db.Column(db.String(64), index=True)
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    speed_kmh = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=_utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "cooperativa": self.cooperativa,
            "route_id": self.route_id,
            "lat": self.lat,
            "lon": self.lon,
            "speed_kmh": self.speed_kmh,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class TransitRoute(db.Model):
    """Ruta de bus cargada desde la matriz de cooperativas."""

    __tablename__ = "transit_routes"

    id = db.Column(db.Integer, primary_key=True)
    ref = db.Column(db.String(64), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False)
    operator = db.Column(db.String(140), nullable=False, index=True)
    tipo = db.Column(db.String(32), default="bus")
    colour = db.Column(db.String(16), default="#2980b9")
    frecuencia = db.Column(db.String(64), default="")
    horario = db.Column(db.String(180), default="")
    horario_lun_vie = db.Column(db.String(80), default="")
    horario_sabado = db.Column(db.String(80), default="")
    horario_domingo = db.Column(db.String(80), default="")
    intervalo_min = db.Column(db.Integer)
    flota = db.Column(db.Integer)
    tarifa = db.Column(db.String(32), default="0.35")
    origen_nombre = db.Column(db.String(140), default="")
    retorno_nombre = db.Column(db.String(140), default="")
    fuente = db.Column(db.String(32), default="matriz")
    created_at = db.Column(db.DateTime, default=_utcnow)

    stops = db.relationship(
        "TransitStop",
        backref="route",
        cascade="all, delete-orphan",
        order_by="TransitStop.sentido, TransitStop.orden",
    )

    def to_catalog_dict(self) -> dict:
        paradas = [
            (s.nombre, s.lat, s.lon)
            for s in sorted(self.stops, key=lambda x: (x.sentido or "", x.orden or 0))
        ]
        return {
            "ref": self.ref,
            "name": self.name,
            "tipo": self.tipo or "bus",
            "colour": self.colour or "#2980b9",
            "operator": self.operator,
            "frecuencia": self.frecuencia or (
                f"{self.intervalo_min} min" if self.intervalo_min else ""
            ),
            "horario": self.horario or self.horario_lun_vie or "",
            "tarifa": self.tarifa or "0.35",
            "paradas": paradas,
            "fuente": self.fuente,
            "horarios": {
                "lunes_viernes": self.horario_lun_vie,
                "sabado": self.horario_sabado,
                "domingo_feriados": self.horario_domingo,
            },
            "flota": self.flota,
            "intervalo_min": self.intervalo_min,
            "origen_nombre": self.origen_nombre,
            "retorno_nombre": self.retorno_nombre,
        }

    def to_dict(self) -> dict:
        data = self.to_catalog_dict()
        data["id"] = self.id
        data["paradas"] = [s.to_dict() for s in self.stops]
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        return data


class TransitStop(db.Model):
    """Parada de una ruta de transporte por sentido."""

    __tablename__ = "transit_stops"

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey("transit_routes.id"), nullable=False, index=True)
    sentido = db.Column(db.String(32), default="ida", index=True)
    orden = db.Column(db.Integer, nullable=False)
    nombre = db.Column(db.String(180), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sentido": self.sentido,
            "orden": self.orden,
            "nombre": self.nombre,
            "lat": self.lat,
            "lon": self.lon,
        }
