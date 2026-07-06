"""Servicio de persistencia de registros de movilidad (reemplaza el CSV)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db
from ..models import MobilityRecord


def _now_fields() -> dict:
    now = datetime.now(timezone.utc)
    return {"timestamp": now, "hora": now.hour, "dia_semana": now.weekday()}


def registrar_busqueda(query: str, fuente: str, lat=None, lon=None, ciudad="Quito") -> MobilityRecord:
    rec = MobilityRecord(
        tipo="busqueda", ciudad=ciudad, origen_query=query,
        fuente_busqueda=fuente, olat=lat, olon=lon, **_now_fields(),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def registrar_ruta(datos: dict, ciudad="Quito") -> MobilityRecord:
    rec = MobilityRecord(
        tipo="ruta", ciudad=ciudad,
        olat=datos.get("olat"), olon=datos.get("olon"),
        dlat=datos.get("dlat"), dlon=datos.get("dlon"),
        distancia_km=datos.get("distancia_km"),
        duracion_base_min=datos.get("duracion_base_min"),
        duracion_trafico_min=datos.get("duracion_trafico_min"),
        duracion_estimacion_min=datos.get("duracion_estimacion_min"),
        retraso_trafico_min=datos.get("retraso_trafico_min"),
        nivel_trafico=datos.get("nivel_trafico"),
        fuente_ruta=datos.get("fuente_ruta", "OSRM"),
        fuente_trafico=datos.get("fuente_trafico"),
        proveedor_trafico=datos.get("proveedor_trafico"),
        es_dato_real=datos.get("es_dato_real", False),
        tiempo_real_min=datos.get("tiempo_real_min"),
        **_now_fields(),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def registrar_generico(tipo: str, **campos) -> MobilityRecord:
    base = _now_fields()
    base.update(campos)
    rec = MobilityRecord(tipo=tipo, **base)
    db.session.add(rec)
    db.session.commit()
    return rec


def total_registros() -> int:
    return db.session.query(MobilityRecord).count()
