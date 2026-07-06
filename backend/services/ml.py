"""Servicio de Machine Learning: entrena y predice tiempos de viaje.

Mejora sobre el original: los datos de entrenamiento se leen desde la base de
datos (tabla ``mobility_records``) en vez de un CSV, y el modelo se persiste
en disco con joblib para no reentrenar en cada arranque.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..extensions import db
from ..models import MobilityRecord

FEATURES = ["distancia_km", "duracion_base_min", "nivel_trafico", "hora", "dia_semana"]
TARGET = "tiempo_real_min"
FACTOR_TRAFICO = {1: 1.00, 2: 1.25, 3: 1.60}

_MODEL_PATH = Path(__file__).resolve().parent.parent / "ml_model.joblib"
_LOCK = threading.Lock()
_STATE: dict = {"modelo": None, "metricas": None, "entrenado_en": None}


def _cargar_modelo_persistido() -> None:
    if _MODEL_PATH.exists():
        try:
            import joblib
            payload = joblib.load(_MODEL_PATH)
            _STATE["modelo"] = payload.get("modelo")
            _STATE["metricas"] = payload.get("metricas")
            _STATE["entrenado_en"] = payload.get("entrenado_en")
        except Exception:  # noqa: BLE001 - modelo corrupto: se ignora
            _STATE["modelo"] = None


def init_modelo() -> None:
    """Carga el modelo persistido al iniciar la app (si existe)."""
    with _LOCK:
        if _STATE["modelo"] is None:
            _cargar_modelo_persistido()


def _dataset() -> pd.DataFrame:
    rows = (
        db.session.query(MobilityRecord)
        .filter(MobilityRecord.tiempo_real_min.isnot(None))
        .filter(MobilityRecord.distancia_km.isnot(None))
        .all()
    )
    data = [
        {
            "distancia_km": r.distancia_km,
            "duracion_base_min": r.duracion_base_min,
            "nivel_trafico": r.nivel_trafico or 1,
            "hora": r.hora if r.hora is not None else 12,
            "dia_semana": r.dia_semana if r.dia_semana is not None else 0,
            "tiempo_real_min": r.tiempo_real_min,
        }
        for r in rows
    ]
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.dropna(subset=FEATURES + [TARGET])
    return df


def entrenar() -> dict:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import train_test_split

    df = _dataset()
    if len(df) < 5:
        return {"ok": False, "error": "Se necesitan al menos 5 registros con tiempo real", "registros": len(df)}

    X = df[FEATURES].values
    y = df[TARGET].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    modelo = RandomForestRegressor(n_estimators=150, random_state=42)
    modelo.fit(X_train, y_train)
    mae = float(mean_absolute_error(y_test, modelo.predict(X_test)))
    importancias = {f: round(float(i), 4) for f, i in zip(FEATURES, modelo.feature_importances_)}

    metricas = {"registros": len(df), "mae_min": round(mae, 2), "importancias": importancias}
    entrenado_en = datetime.now(timezone.utc).isoformat()

    with _LOCK:
        _STATE.update({"modelo": modelo, "metricas": metricas, "entrenado_en": entrenado_en})
        try:
            import joblib
            joblib.dump(
                {"modelo": modelo, "metricas": metricas, "entrenado_en": entrenado_en},
                _MODEL_PATH,
            )
        except Exception:  # noqa: BLE001 - persistencia best-effort
            pass

    return {"ok": True, **metricas, "entrenado_en": entrenado_en}


def predecir(distancia_km, duracion_base_min, nivel_trafico=1, hora=None, dia_semana=None) -> dict:
    nivel_trafico = int(nivel_trafico or 1)
    ahora = datetime.now(timezone.utc)
    hora = ahora.hour if hora is None else int(hora)
    dia_semana = ahora.weekday() if dia_semana is None else int(dia_semana)

    modelo = _STATE["modelo"]
    if modelo is None:
        factor = FACTOR_TRAFICO.get(nivel_trafico, 1.0)
        return {
            "tiempo_min": round(float(duracion_base_min) * factor, 1),
            "modelo_listo": False,
            "fuente": "heuristica",
            "features": FEATURES,
        }

    x = np.array([[distancia_km, duracion_base_min, nivel_trafico, hora, dia_semana]], dtype=float)
    tiempo = float(modelo.predict(x)[0])
    return {
        "tiempo_min": round(tiempo, 1),
        "modelo_listo": True,
        "fuente": "modelo_ml",
        "features": FEATURES,
        "inputs": x.tolist()[0],
    }


def estado() -> dict:
    return {
        "modelo_listo": _STATE["modelo"] is not None,
        "metricas": _STATE["metricas"],
        "entrenado_en": _STATE["entrenado_en"],
        "registros_entrenables": len(_dataset()),
    }


def modelo_listo() -> bool:
    return _STATE["modelo"] is not None
