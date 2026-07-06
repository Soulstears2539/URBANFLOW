"""Caché en memoria con expiración por TTL, segura para hilos.

Se usa para no repetir llamadas a APIs externas (OSRM, Overpass, Nominatim,
TomTom, HERE) dentro de una ventana de tiempo.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_LOCK = threading.Lock()
_STORE: dict[str, tuple[float, Any]] = {}


def cache_get(key: str) -> Any | None:
    with _LOCK:
        item = _STORE.get(key)
        if not item:
            return None
        expires_at, value = item
        if time.time() > expires_at:
            _STORE.pop(key, None)
            return None
        return value


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    with _LOCK:
        _STORE[key] = (time.time() + ttl, value)


def cached(key: str, ttl: int, producer: Callable[[], Any]) -> Any:
    """Devuelve el valor cacheado o lo produce y cachea."""
    hit = cache_get(key)
    if hit is not None:
        return hit
    value = producer()
    if value is not None:
        cache_set(key, value, ttl)
    return value


def cache_clear() -> None:
    with _LOCK:
        _STORE.clear()
