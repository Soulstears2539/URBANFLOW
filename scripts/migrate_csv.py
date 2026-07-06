"""Migra el histórico CSV legado a la base de datos, limpiando duplicados.

Uso:
    python scripts/migrate_csv.py [ruta_al_csv]

Por defecto busca el CSV del proyecto original en
``mapadefinitivo/backend/historico_movilidad.csv``. Limpia:
- IDs duplicados (se reasignan IDs nuevos por autoincremento).
- Filas exactamente repetidas.
- Valores numéricos vacíos -> NULL.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Permite importar el paquete backend al ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app  # noqa: E402
from backend.config import Config  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import MobilityRecord  # noqa: E402

_DEFAULT_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "mapaaaa" / "mapadefinitivo" / "backend" / "historico_movilidad.csv"
)

_NUMERIC = {
    "olat", "olon", "dlat", "dlon", "distancia_km", "duracion_base_min",
    "duracion_trafico_min", "duracion_estimacion_min", "retraso_trafico_min",
    "tiempo_real_min",
}
_INT = {"nivel_trafico", "hora", "dia_semana"}


def _clean_value(col: str, value):
    if pd.isna(value) or value == "":
        return None
    if col == "timestamp":
        try:
            return datetime.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            return None
    if col in _NUMERIC:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if col in _INT:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if col == "es_dato_real":
        return str(value).strip().lower() in {"true", "1", "yes"}
    return value


def migrate(csv_path: Path) -> int:
    if not csv_path.exists():
        print(f"[!] No se encontró el CSV: {csv_path}")
        return 0

    df = pd.read_csv(csv_path, dtype=str)
    # Elimina filas exactamente duplicadas (ignorando la columna id).
    cols_sin_id = [c for c in df.columns if c != "id"]
    df = df.drop_duplicates(subset=cols_sin_id)

    columnas_validas = {c.name for c in MobilityRecord.__table__.columns}
    insertados = 0
    for _, fila in df.iterrows():
        campos = {}
        for col in df.columns:
            if col == "id" or col not in columnas_validas:
                continue
            campos[col] = _clean_value(col, fila[col])
        if not campos.get("tipo"):
            continue
        db.session.add(MobilityRecord(**campos))
        insertados += 1
        if insertados % 500 == 0:
            db.session.commit()
    db.session.commit()
    return insertados


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_CSV
    app = create_app(Config)
    with app.app_context():
        antes = MobilityRecord.query.count()
        n = migrate(csv_path)
        despues = MobilityRecord.query.count()
    print(f"[ok] Migrados {n} registros limpios desde {csv_path.name}")
    print(f"[ok] Registros en DB: {antes} -> {despues}")


if __name__ == "__main__":
    main()
