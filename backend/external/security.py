"""Validaciones de seguridad para entradas que tocan la red o el disco.

- ``validate_remote_url``: previene SSRF (bloquea localhost, IP privadas,
  esquemas peligrosos) antes de descargar feeds GTFS u otros recursos.
- ``validate_upload_filename``: previene path traversal y exige extensión CSV.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


class SecurityError(ValueError):
    """Error de validación de seguridad."""


def validate_remote_url(url: str) -> str:
    if not url or not isinstance(url, str):
        raise SecurityError("URL vacía")

    parsed = urlparse(url.strip())
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SecurityError(f"Esquema no permitido: {parsed.scheme or 'desconocido'}")
    if not parsed.hostname:
        raise SecurityError("URL sin host")

    host = parsed.hostname
    if host.lower() in {"localhost", "0.0.0.0"}:
        raise SecurityError("Acceso a host local bloqueado")

    # Resuelve y verifica todas las IPs asociadas al host.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SecurityError(f"No se pudo resolver el host: {host}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise SecurityError("La URL resuelve a una IP privada/reservada")

    return url.strip()


def validate_upload_filename(filename: str) -> str:
    if not filename:
        raise SecurityError("Nombre de archivo vacío")
    base = filename.replace("\\", "/").split("/")[-1]
    if not base.lower().endswith(".csv"):
        raise SecurityError("Solo se permiten archivos .csv")
    if ".." in base:
        raise SecurityError("Nombre de archivo inválido")
    return base
