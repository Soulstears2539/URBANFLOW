"""Servicio de transporte publico: catalogo local + matriz de cooperativas."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import defaultdict
from html import unescape
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from ..data.quito_buses import QUITO_BUSES, bus_detail as local_bus_detail, buses_summary as local_buses_summary
from ..extensions import db
from ..external import geoapify, google_routes, nominatim, osrm, tomtom
from ..models import TransitRoute, TransitStop
from .routing import haversine_km

__all__ = [
    "QUITO_BUSES",
    "bus_detail",
    "buses_summary",
    "buscar_transporte",
    "ruta_bus_pasos",
    "importar_ruta_manual",
    "importar_matriz_archivo",
    "importar_matriz_csv",
    "rutas_matriz",
    "plantilla_matriz",
]

_RADIO_DEFECTO_M = 600
_MIN_DETALLE_RUTA_M = 300
_PENALIZA_TRAMO_LARGO_SIN_PARADAS_M = 2500
MATRIX_COLUMNS = [
    "cooperativa", "linea", "nombre_ruta", "sentido", "orden", "parada", "lat", "lon",
    "horario_lun_vie", "horario_sabado", "horario_domingo", "intervalo_min", "flota",
    "tarifa", "color", "tipo", "origen", "retorno",
]

CITY_CENTERS = {
    "quito": (-0.2202, -78.5127),
    "guayaquil": (-2.1894, -79.8891),
    "cuenca": (-2.9006, -79.0045),
    "riobamba": (-1.6636, -78.6546),
}


def _norm(value) -> str:
    return str(value or "").strip()


def _int_or_none(value):
    value = _norm(value)
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", _norm(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")


def _city_source(ciudad: str) -> str:
    ciudad = _norm(ciudad) or "Quito"
    return f"MATRIZ {ciudad}"


def _city_center(ciudad: str) -> tuple[float, float]:
    return CITY_CENTERS.get(_slug(ciudad), CITY_CENTERS["quito"])


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(unescape("".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(_norm(c) for c in self._row):
                self.rows.append(self._row)
            self._row = None


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _dict_rows_from_grid(grid: list[list[str]]) -> list[dict]:
    if not grid:
        return []
    headers = [_slug(c) for c in grid[0]]
    rows = []
    for raw_row in grid[1:]:
        row = {headers[i]: raw_row[i] if i < len(raw_row) else "" for i in range(len(headers))}
        if any(_norm(v) for v in row.values()):
            rows.append(row)
    return rows


def _read_html_rows(raw: bytes) -> list[dict]:
    parser = _TableParser()
    parser.feed(_decode_text(raw))
    return _dict_rows_from_grid(parser.rows)


def _read_xlsx_rows(raw: bytes) -> list[dict]:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    def _col_index(ref: str) -> int:
        letters = re.sub(r"[^A-Z]", "", ref.upper())
        idx = 0
        for char in letters:
            idx = idx * 26 + (ord(char) - ord("A") + 1)
        return max(0, idx - 1)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("x:si", ns):
                shared.append("".join(t.text or "" for t in si.findall(".//x:t", ns)))

        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in zf.namelist():
            sheet_name = next((n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")), "")
        if not sheet_name:
            return []

        root = ET.fromstring(zf.read(sheet_name))
        grid = []
        for row in root.findall(".//x:row", ns):
            values_by_col = {}
            for cell in row.findall("x:c", ns):
                value = cell.find("x:v", ns)
                raw_value = value.text if value is not None else ""
                if cell.get("t") == "s" and raw_value:
                    text = shared[int(raw_value)] if int(raw_value) < len(shared) else ""
                else:
                    text = raw_value
                values_by_col[_col_index(cell.get("r", ""))] = text
            if values_by_col:
                max_col = max(values_by_col)
                values = [values_by_col.get(i, "") for i in range(max_col + 1)]
            else:
                values = []
            grid.append(values)
        return _dict_rows_from_grid(grid)


def _read_csv_rows(raw: bytes) -> list[dict]:
    text = _decode_text(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    return [{_slug(k): v for k, v in row.items()} for row in reader]


def _matrix_file_rows(raw: bytes, filename: str = "") -> list[dict]:
    name = filename.lower()
    if name.endswith(".xlsx") or raw[:2] == b"PK":
        return _read_xlsx_rows(raw)
    text_start = _decode_text(raw[:512]).lower()
    if name.endswith((".xls", ".html", ".htm")) or "<table" in text_start or "<html" in text_start:
        return _read_html_rows(raw)
    return _read_csv_rows(raw)


def plantilla_matriz() -> dict:
    return {
        "columnas": MATRIX_COLUMNS,
        "ejemplo": {
            "cooperativa": "Cooperativa Turis Monserrat",
            "linea": "Carcelen Bajo - Marin",
            "nombre_ruta": "Carcelen Bajo - Marin",
            "sentido": "ida",
            "orden": "1",
            "parada": "Carcelen Bajo",
            "lat": "-0.0950",
            "lon": "-78.4750",
            "horario_lun_vie": "05:20 a 18:00",
            "horario_sabado": "05:45 a 17:00",
            "horario_domingo": "05:45 a 17:00",
            "intervalo_min": "9",
            "flota": "19",
            "tarifa": "0.35",
            "color": "#16a085",
            "tipo": "bus",
            "origen": "Carcelen Bajo",
            "retorno": "La Marin",
        },
    }


def _catalogo_matriz() -> list[dict]:
    return [
        r.to_catalog_dict()
        for r in TransitRoute.query.order_by(TransitRoute.operator, TransitRoute.ref).all()
        if len(r.stops) >= 2
    ]


def _catalogo_total() -> list[dict]:
    return [*QUITO_BUSES, *_catalogo_matriz()]


def rutas_matriz() -> list[dict]:
    return [r.to_dict() for r in TransitRoute.query.order_by(TransitRoute.operator, TransitRoute.ref).all()]


def buses_summary() -> list[dict]:
    matriz = [
        {
            "ref": r["ref"],
            "name": r["name"],
            "tipo": r["tipo"],
            "operator": r["operator"],
            "colour": r["colour"],
            "frecuencia": r["frecuencia"],
            "horario": r["horario"],
            "tarifa": r["tarifa"],
            "n_paradas": len(r["paradas"]),
            "fuente": r.get("fuente", "matriz"),
        }
        for r in _catalogo_matriz()
    ]
    return [*local_buses_summary(), *matriz]


def bus_detail(ref: str) -> dict | None:
    local = local_bus_detail(ref)
    if local:
        local["fuente"] = "local"
        return local
    for route in TransitRoute.query.filter(TransitRoute.ref.ilike(ref)).all():
        return route.to_dict()
    return None


def importar_matriz_csv(raw: bytes, reemplazar: bool = False) -> dict:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("El CSV no tiene encabezados")

    rows = list(reader)
    if not rows:
        raise ValueError("El CSV no tiene filas")

    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    errores = []
    for idx, row in enumerate(rows, start=2):
        cooperativa = _norm(row.get("cooperativa"))
        linea = _norm(row.get("linea"))
        parada = _norm(row.get("parada"))
        if not cooperativa or not linea or not parada:
            errores.append(f"Fila {idx}: cooperativa, linea y parada son obligatorias")
            continue
        try:
            float(row.get("lat", ""))
            float(row.get("lon", ""))
        except ValueError:
            errores.append(f"Fila {idx}: lat/lon deben ser numeros")
            continue
        grupos[(cooperativa, linea)].append(row)

    if errores:
        raise ValueError("; ".join(errores[:8]))

    if reemplazar:
        TransitStop.query.delete()
        TransitRoute.query.delete()

    creadas = 0
    paradas = 0
    for (cooperativa, linea), items in grupos.items():
        first = items[0]
        intervalo = _int_or_none(first.get("intervalo_min"))
        route = TransitRoute(
            ref=linea,
            name=_norm(first.get("nombre_ruta")) or linea,
            operator=cooperativa,
            tipo=_norm(first.get("tipo")) or "bus",
            colour=_norm(first.get("color")) or "#2980b9",
            frecuencia=f"{intervalo} min" if intervalo else "",
            horario=_norm(first.get("horario_lun_vie")),
            horario_lun_vie=_norm(first.get("horario_lun_vie")),
            horario_sabado=_norm(first.get("horario_sabado")),
            horario_domingo=_norm(first.get("horario_domingo")),
            intervalo_min=intervalo,
            flota=_int_or_none(first.get("flota")),
            tarifa=_norm(first.get("tarifa")) or "0.35",
            origen_nombre=_norm(first.get("origen")),
            retorno_nombre=_norm(first.get("retorno")),
        )
        db.session.add(route)
        db.session.flush()
        creadas += 1

        ordered = sorted(
            items,
            key=lambda r: (_norm(r.get("sentido")) or "ida", _int_or_none(r.get("orden")) or 0),
        )
        for row in ordered:
            db.session.add(TransitStop(
                route_id=route.id,
                sentido=_norm(row.get("sentido")) or "ida",
                orden=_int_or_none(row.get("orden")) or 0,
                nombre=_norm(row.get("parada")),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
            ))
            paradas += 1

    db.session.commit()
    return {"rutas_creadas": creadas, "paradas_creadas": paradas, "reemplazar": reemplazar}


def _coord_cache_actual() -> dict[tuple[str, str], tuple[float, float]]:
    cache = {}
    for stop in TransitStop.query.join(TransitRoute).all():
        fuente = stop.route.fuente or ""
        ciudad = "quito"
        for key in CITY_CENTERS:
            if key in _slug(fuente):
                ciudad = key
                break
        cache[(_slug(ciudad), _slug(stop.nombre))] = (stop.lat, stop.lon)
    return cache


def _geocode_parada(nombre: str, ciudad: str) -> tuple[float, float] | None:
    query = f"{nombre}, {ciudad}, Ecuador"
    lat, lon = _city_center(ciudad)
    for provider in (
        lambda: tomtom.fuzzy_search(query, lat, lon, limit=1),
        lambda: geoapify.autocomplete(query, lat, lon, limit=1),
        lambda: [
            {"lat": r["lat"], "lon": r["lon"]}
            for r in nominatim.search(query, lat, lon, limite=1)
        ],
    ):
        resultados = provider()
        if resultados:
            first = resultados[0]
            if first.get("lat") is not None and first.get("lon") is not None:
                return float(first["lat"]), float(first["lon"])
    return None


def _coords_parada(nombre: str, ciudad: str, cache: dict[tuple[str, str], tuple[float, float]]):
    key = (_slug(ciudad), _slug(nombre))
    if key in cache:
        return cache[key], "cache"
    coords = _geocode_parada(nombre, ciudad)
    if coords:
        cache[key] = coords
        return coords, "geocode"
    return None, "sin_coordenadas"


def _importar_matriz_ancha(rows: list[dict], reemplazar: bool = False) -> dict:
    grupos: dict[tuple[str, str, str], dict] = {}
    errores = []
    coord_cache = _coord_cache_actual()

    for idx, row in enumerate(rows, start=2):
        cooperativa = _norm(row.get("cooperativa"))
        linea = _norm(row.get("linea"))
        ruta = _norm(row.get("ruta")) or linea
        sentido = _norm(row.get("sentido")) or "ida"
        ciudad = _norm(row.get("ciudad")) or "Quito"
        if not cooperativa or not linea:
            errores.append(f"Fila {idx}: cooperativa y linea son obligatorias")
            continue
        paradas_cols = sorted(
            [key for key in row if key.startswith("parada_")],
            key=lambda key: _int_or_none(key.replace("parada_", "")) or 0,
        )
        paradas = [_norm(row.get(col)) for col in paradas_cols if _norm(row.get(col))]
        if len(paradas) < 2:
            errores.append(f"Fila {idx}: se necesitan al menos parada_1 y parada_2")
            continue

        grupos[(cooperativa, linea, sentido)] = {
            "ciudad": ciudad,
            "provincia": _norm(row.get("provincia")),
            "pais": _norm(row.get("pais")) or "Ecuador",
            "cooperativa": cooperativa,
            "linea": linea,
            "ruta": ruta,
            "sentido": sentido,
            "paradas": paradas,
            "horario": _norm(row.get("horario")),
            "intervalo_min": _int_or_none(row.get("intervalo_min")),
            "flota": _int_or_none(row.get("flota")),
            "tarifa": _norm(row.get("tarifa")) or "0.35",
        }

    if errores:
        raise ValueError("; ".join(errores[:8]))

    if reemplazar:
        TransitStop.query.delete()
        TransitRoute.query.delete()
    else:
        for cooperativa, linea, _sentido in grupos:
            for route in TransitRoute.query.filter_by(operator=cooperativa, ref=linea).all():
                db.session.delete(route)
        db.session.flush()

    creadas = 0
    paradas_creadas = 0
    geocodificadas = 0
    sin_coordenadas = []
    for item in grupos.values():
        intervalo = item["intervalo_min"]
        route = TransitRoute(
            ref=item["linea"],
            name=item["ruta"],
            operator=item["cooperativa"],
            tipo="bus",
            colour="#16a085",
            frecuencia=f"{intervalo} min" if intervalo else "",
            horario=item["horario"],
            horario_lun_vie=item["horario"],
            intervalo_min=intervalo,
            flota=item["flota"],
            tarifa=item["tarifa"],
            origen_nombre=item["paradas"][0],
            retorno_nombre=item["paradas"][-1],
            fuente=_city_source(item["ciudad"]),
        )
        db.session.add(route)
        db.session.flush()
        creadas += 1

        paradas_ruta = 0
        for orden, nombre in enumerate(item["paradas"], start=1):
            coords, fuente_coords = _coords_parada(nombre, item["ciudad"], coord_cache)
            if not coords:
                sin_coordenadas.append(f"{nombre} ({item['ciudad']})")
                continue
            if fuente_coords == "geocode":
                geocodificadas += 1
            db.session.add(TransitStop(
                route_id=route.id,
                sentido=item["sentido"],
                orden=orden,
                nombre=nombre,
                lat=coords[0],
                lon=coords[1],
            ))
            paradas_creadas += 1
            paradas_ruta += 1

        if paradas_ruta < 2:
            db.session.delete(route)
            creadas -= 1
            paradas_creadas -= paradas_ruta

    db.session.commit()
    return {
        "rutas_creadas": creadas,
        "paradas_creadas": paradas_creadas,
        "geocodificadas": geocodificadas,
        "sin_coordenadas": sin_coordenadas[:20],
        "reemplazar": reemplazar,
        "formato": "excel_ancho",
        "catalogo_actualizado": True,
    }


def importar_matriz_archivo(raw: bytes, filename: str = "", reemplazar: bool = False) -> dict:
    rows = _matrix_file_rows(raw, filename)
    if not rows:
        raise ValueError("El archivo no tiene filas legibles")

    headers = set(rows[0].keys())
    if any(h.startswith("parada_") for h in headers):
        return _importar_matriz_ancha(rows, reemplazar=reemplazar)
    if {"cooperativa", "linea", "parada", "lat", "lon"}.issubset(headers):
        normalized = io.StringIO()
        writer = csv.DictWriter(normalized, fieldnames=MATRIX_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in MATRIX_COLUMNS})
        return importar_matriz_csv(normalized.getvalue().encode("utf-8"), reemplazar=reemplazar)
    raise ValueError("Formato no reconocido. Usa el Excel descargado o la plantilla CSV de matriz.")


def _parse_manual_stop(item) -> dict:
    if isinstance(item, dict):
        return {
            "nombre": _norm(item.get("nombre") or item.get("parada") or item.get("name")),
            "lat": item.get("lat"),
            "lon": item.get("lon") if item.get("lon") is not None else item.get("lng"),
        }

    parts = [p.strip() for p in _norm(item).split("|")]
    stop = {"nombre": parts[0] if parts else "", "lat": None, "lon": None}
    if len(parts) >= 3:
        stop["lat"] = parts[1]
        stop["lon"] = parts[2]
    return stop


def importar_ruta_manual(data: dict) -> dict:
    ciudad = _norm(data.get("ciudad")) or "Quito"
    cooperativa = _norm(data.get("cooperativa"))
    linea = _norm(data.get("linea"))
    ruta = _norm(data.get("ruta")) or linea
    sentido = _norm(data.get("sentido")) or "ida"
    horario = _norm(data.get("horario"))
    intervalo = _int_or_none(data.get("intervalo_min"))
    flota = _int_or_none(data.get("flota"))
    tarifa = _norm(data.get("tarifa")) or "0.35"

    if not cooperativa or not linea:
        raise ValueError("cooperativa y linea son obligatorias")

    raw_paradas = data.get("paradas") or []
    if isinstance(raw_paradas, str):
        raw_paradas = [line for line in raw_paradas.splitlines() if _norm(line)]

    paradas = [_parse_manual_stop(item) for item in raw_paradas]
    paradas = [p for p in paradas if p["nombre"]]
    if len(paradas) < 2:
        raise ValueError("Agrega al menos dos paradas. Puedes escribir una por linea.")

    for route in TransitRoute.query.filter_by(operator=cooperativa, ref=linea).all():
        db.session.delete(route)
    db.session.flush()

    route = TransitRoute(
        ref=linea,
        name=ruta,
        operator=cooperativa,
        tipo=_norm(data.get("tipo")) or "bus",
        colour=_norm(data.get("color")) or "#16a085",
        frecuencia=f"{intervalo} min" if intervalo else "",
        horario=horario,
        horario_lun_vie=horario,
        intervalo_min=intervalo,
        flota=flota,
        tarifa=tarifa,
        origen_nombre=paradas[0]["nombre"],
        retorno_nombre=paradas[-1]["nombre"],
        fuente=_city_source(ciudad),
    )
    db.session.add(route)
    db.session.flush()

    coord_cache = _coord_cache_actual()
    sin_coordenadas = []
    geocodificadas = 0
    paradas_creadas = 0
    for orden, parada in enumerate(paradas, start=1):
        coords = None
        try:
            if parada.get("lat") not in (None, "") and parada.get("lon") not in (None, ""):
                coords = (float(parada["lat"]), float(parada["lon"]))
        except ValueError:
            coords = None

        fuente_coords = "manual"
        if coords is None:
            coords, fuente_coords = _coords_parada(parada["nombre"], ciudad, coord_cache)
        if coords is None:
            sin_coordenadas.append(f"{parada['nombre']} ({ciudad})")
            continue
        if fuente_coords == "geocode":
            geocodificadas += 1

        db.session.add(TransitStop(
            route_id=route.id,
            sentido=sentido,
            orden=orden,
            nombre=parada["nombre"],
            lat=coords[0],
            lon=coords[1],
        ))
        paradas_creadas += 1

    if paradas_creadas < 2:
        db.session.delete(route)
        db.session.commit()
        raise ValueError(
            "No se pudo guardar la ruta porque menos de dos paradas tienen coordenadas. "
            "Usa el formato: Nombre de parada | lat | lon"
        )

    db.session.commit()
    return {
        "rutas_creadas": 1,
        "paradas_creadas": paradas_creadas,
        "geocodificadas": geocodificadas,
        "sin_coordenadas": sin_coordenadas[:20],
        "formato": "manual",
        "catalogo_actualizado": True,
        "ruta_id": route.id,
    }


def importar_rutas_osm(rutas: list[dict], reemplazar_osm: bool = True) -> dict:
    if reemplazar_osm:
        osm_routes = TransitRoute.query.filter(TransitRoute.fuente.like("OSM%")).all()
        for route in osm_routes:
            db.session.delete(route)
        db.session.flush()

    creadas = 0
    paradas = 0
    vistas = set()
    for item in rutas:
        ref = _norm(item.get("ref"))
        operator = _norm(item.get("operator")) or "OSM Quito"
        key = (operator.lower(), ref.lower())
        if not ref or key in vistas:
            continue
        vistas.add(key)

        stops = item.get("stops") or []
        if len(stops) < 2:
            continue

        interval = _int_or_none(item.get("interval"))
        route = TransitRoute(
            ref=ref,
            name=_norm(item.get("name")) or ref,
            operator=operator,
            tipo=_norm(item.get("tipo")) or "bus",
            colour=_norm(item.get("colour")) or "#2f80ed",
            frecuencia=f"{interval} min" if interval else _norm(item.get("interval")),
            intervalo_min=interval,
            tarifa="0.35",
            origen_nombre=_norm(item.get("from")),
            retorno_nombre=_norm(item.get("to")),
            fuente=_norm(item.get("fuente")) or "OSM",
        )
        db.session.add(route)
        db.session.flush()
        creadas += 1

        for idx, stop in enumerate(stops, start=1):
            db.session.add(TransitStop(
                route_id=route.id,
                sentido="ida",
                orden=idx,
                nombre=_norm(stop.get("nombre")) or f"Parada {idx}",
                lat=float(stop["lat"]),
                lon=float(stop["lon"]),
            ))
            paradas += 1

    db.session.commit()
    return {"rutas_creadas": creadas, "paradas_creadas": paradas, "fuente": "OSM"}


def _parada_mas_cercana(linea: dict, lat: float, lon: float, radio_m: int):
    mejor, mejor_d = None, None
    for idx, (nombre, plat, plon) in enumerate(linea["paradas"]):
        d = haversine_km(lat, lon, plat, plon) * 1000
        if d <= radio_m and (mejor_d is None or d < mejor_d):
            mejor, mejor_d = (nombre, plat, plon, idx), d
    return mejor, mejor_d


def buscar_transporte(olat, olon, dlat, dlon, radio_m=_RADIO_DEFECTO_M) -> dict:
    """Clasifica lineas en directas / solo-origen / solo-destino."""
    directas, orig_solo, dest_solo = [], [], []
    for linea in _catalogo_total():
        po, do = _parada_mas_cercana(linea, olat, olon, radio_m)
        pd, dd = _parada_mas_cercana(linea, dlat, dlon, radio_m)
        resumen = {
            "ref": linea["ref"],
            "name": linea["name"],
            "tipo": linea["tipo"],
            "colour": linea["colour"],
            "operator": linea["operator"],
            "frecuencia": linea["frecuencia"],
            "horario": linea["horario"],
            "tarifa": linea["tarifa"],
            "fuente": linea.get("fuente", "local"),
            "horarios": linea.get("horarios"),
            "flota": linea.get("flota"),
            "intervalo_min": linea.get("intervalo_min"),
        }
        if po and pd:
            resumen["parada_origen"] = {"nombre": po[0], "lat": po[1], "lon": po[2], "idx": po[3], "dist_m": round(do)}
            resumen["parada_destino"] = {"nombre": pd[0], "lat": pd[1], "lon": pd[2], "idx": pd[3], "dist_m": round(dd)}
            directas.append(resumen)
        elif po:
            resumen["parada_origen"] = {"nombre": po[0], "lat": po[1], "lon": po[2], "idx": po[3], "dist_m": round(do)}
            orig_solo.append(resumen)
        elif pd:
            resumen["parada_destino"] = {"nombre": pd[0], "lat": pd[1], "lon": pd[2], "idx": pd[3], "dist_m": round(dd)}
            dest_solo.append(resumen)

    return {
        "directas": directas,
        "orig_solo": orig_solo,
        "dest_solo": dest_solo,
        "transbordos": _transbordos_simples(orig_solo, dest_solo),
    }


def _transbordos_simples(orig_solo: list[dict], dest_solo: list[dict]) -> list[dict]:
    candidatos = []
    for a in orig_solo[:8]:
        for b in dest_solo[:8]:
            if a["ref"] == b["ref"]:
                continue
            candidatos.append({
                "primera_linea": a,
                "segunda_linea": b,
                "mensaje": f"Toma {a['ref']} y transborda a {b['ref']} cerca de una parada comun o corredor cercano",
            })
    return candidatos[:5]


def _distancia_recta_m(olat: float, olon: float, dlat: float, dlon: float) -> float:
    return haversine_km(olat, olon, dlat, dlon) * 1000


def _ruta_tiene_detalle(path: list[list[float]], distancia_recta_m: float) -> bool:
    """Evita pintar tramos largos como una cuerda de dos puntos."""
    return len(path) >= 3 or distancia_recta_m <= _MIN_DETALLE_RUTA_M


def _fuente_unica(fuentes: list[str]) -> str:
    vistas = []
    for fuente in fuentes:
        if fuente and fuente not in vistas:
            vistas.append(fuente)
    return "+".join(vistas) if vistas else "sin_fuente"


def _ruta_por_calle(olat: float, olon: float, dlat: float, dlon: float, modo: str) -> dict:
    """Devuelve un tramo siguiendo calles. Nunca inventa una linea recta."""
    distancia_directa_m = _distancia_recta_m(olat, olon, dlat, dlon)
    intentos = [
        ("OSRM", lambda: osrm.fetch_osrm_route(olat, olon, dlat, dlon, modo=modo, alternativas=1)),
        ("GOOGLE_ROUTES", lambda: google_routes.compute_routes(olat, olon, dlat, dlon, modo=modo, alternativas=1)),
        ("GEOAPIFY", lambda: geoapify.route(olat, olon, dlat, dlon, modo=modo)),
    ]
    if modo == "pie":
        # El OSRM publico a veces no tiene perfil peatonal; driving evita rectas y sigue calles.
        intentos.insert(2, ("OSRM_DRIVING_PARA_CALLES", lambda: osrm.fetch_osrm_route(olat, olon, dlat, dlon, modo="auto", alternativas=1)))
        intentos.append(("GEOAPIFY_DRIVE_PARA_CALLES", lambda: geoapify.route(olat, olon, dlat, dlon, modo="auto")))

    for fuente, producer in intentos:
        rutas = producer()
        if not rutas:
            continue
        ruta = rutas[0]
        path = ruta.get("path") or []
        if len(path) < 2:
            continue
        if not _ruta_tiene_detalle(path, distancia_directa_m):
            continue
        dist_m = round((ruta.get("dist_km") or 0) * 1000)
        if dist_m <= 0:
            dist_m = round(distancia_directa_m)
        return {
            "path": path,
            "dist_m": dist_m,
            "dur_min": ruta.get("dur_min") or 0,
            "fuente": fuente,
        }

    return {
        "path": [],
        "dist_m": 0,
        "dur_min": 0,
        "fuente": "sin_ruta_por_calles",
        "error": "No se pudo calcular este tramo por calles reales",
    }


def _unir_paths(paths: list[list[list[float]]]) -> list[list[float]]:
    completo: list[list[float]] = []
    for path in paths:
        if not path:
            continue
        if completo and path[0] == completo[-1]:
            completo.extend(path[1:])
        else:
            completo.extend(path)
    return completo


def _linea_catalogo(ref: str, operator: str) -> dict | None:
    ref_norm = _norm(ref).lower()
    op_norm = _norm(operator).lower()
    for linea in _catalogo_total():
        if _norm(linea.get("ref")).lower() == ref_norm and _norm(linea.get("operator")).lower() == op_norm:
            return linea
    return None


def _paradas_tramo(linea: dict, idx_o: int | None, idx_d: int | None) -> list[dict]:
    paradas = linea.get("paradas") or []
    if idx_o is None or idx_d is None or not paradas:
        return []
    start, end = int(idx_o), int(idx_d)
    if start <= end:
        seleccion = list(enumerate(paradas[start:end + 1], start=start))
    else:
        seleccion = list(enumerate(paradas[end:start + 1], start=end))
        seleccion.reverse()
    return [
        {
            "nombre": nombre,
            "lat": lat,
            "lon": lon,
            "orden": idx + 1,
            "tipo": "intermedia",
        }
        for idx, (nombre, lat, lon) in seleccion
    ]


def _paradas_basicas(po: dict, pd: dict) -> list[dict]:
    return [
        {"nombre": po["nombre"], "lat": po["lat"], "lon": po["lon"], "orden": 1, "tipo": "subida"},
        {"nombre": pd["nombre"], "lat": pd["lat"], "lon": pd["lon"], "orden": 2, "tipo": "bajada"},
    ]


def _contar_paradas_directa(linea: dict) -> int:
    idx_o = linea.get("parada_origen", {}).get("idx")
    idx_d = linea.get("parada_destino", {}).get("idx")
    if idx_o is None or idx_d is None:
        return 2
    return abs(int(idx_d) - int(idx_o)) + 1


def _score_linea_directa(linea: dict) -> float:
    """Prioriza caminatas cortas, pero evita lineas con solo dos puntos lejanos."""
    po = linea["parada_origen"]
    pd = linea["parada_destino"]
    caminata_m = (po.get("dist_m") or 0) + (pd.get("dist_m") or 0)
    paradas = _contar_paradas_directa(linea)
    distancia_bus_m = _distancia_recta_m(po["lat"], po["lon"], pd["lat"], pd["lon"])
    penalizacion = 0
    if paradas <= 2 and distancia_bus_m > _PENALIZA_TRAMO_LARGO_SIN_PARADAS_M:
        penalizacion += distancia_bus_m * 0.9
    elif paradas <= 3 and distancia_bus_m > _PENALIZA_TRAMO_LARGO_SIN_PARADAS_M * 1.8:
        penalizacion += distancia_bus_m * 0.35
    bonus_paradas = min(paradas, 18) * 80
    return caminata_m + penalizacion - bonus_paradas


def _elegir_linea_directa(directas: list[dict]) -> dict:
    return min(directas, key=_score_linea_directa)


def _ruta_por_paradas(paradas: list[dict], modo: str = "bus") -> dict:
    """Une la geometria real entre paradas consecutivas, sin segmentos rectos."""
    if len(paradas) < 2:
        return {
            "path": [],
            "dist_m": 0,
            "dur_min": 0,
            "fuente": "sin_paradas",
            "error": "La linea no tiene suficientes paradas para construir el tramo",
        }

    puntos = [(float(p["lat"]), float(p["lon"])) for p in paradas]
    if len(puntos) > 2:
        rutas = osrm.fetch_osrm_route_waypoints(puntos, modo=modo, alternativas=1)
        if rutas:
            ruta = rutas[0]
            path = ruta.get("path") or []
            distancia_directa_m = _distancia_recta_m(puntos[0][0], puntos[0][1], puntos[-1][0], puntos[-1][1])
            if len(path) >= 2 and _ruta_tiene_detalle(path, distancia_directa_m):
                return {
                    "path": path,
                    "dist_m": round((ruta.get("dist_km") or 0) * 1000),
                    "dur_min": ruta.get("dur_min") or 0,
                    "fuente": "OSRM_WAYPOINTS",
                }

    paths = []
    fuentes = []
    total_m = 0
    total_min = 0
    for idx in range(len(paradas) - 1):
        actual = paradas[idx]
        siguiente = paradas[idx + 1]
        tramo = _ruta_por_calle(
            float(actual["lat"]),
            float(actual["lon"]),
            float(siguiente["lat"]),
            float(siguiente["lon"]),
            modo,
        )
        if tramo.get("error"):
            return {
                "path": [],
                "dist_m": total_m,
                "dur_min": total_min,
                "fuente": tramo.get("fuente", "sin_ruta_por_calles"),
                "error": f"No se pudo calcular por calles entre {actual.get('nombre')} y {siguiente.get('nombre')}",
            }
        paths.append(tramo["path"])
        fuentes.append(tramo.get("fuente", "ruta"))
        total_m += tramo.get("dist_m") or 0
        total_min += tramo.get("dur_min") or 0

    return {
        "path": _unir_paths(paths),
        "dist_m": round(total_m),
        "dur_min": round(total_min, 2),
        "fuente": _fuente_unica(fuentes),
    }


def ruta_bus_pasos(olat, olon, dlat, dlon, radio_m=_RADIO_DEFECTO_M) -> dict:
    """Construye instrucciones paso a paso usando la mejor linea directa."""
    resultado = buscar_transporte(olat, olon, dlat, dlon, radio_m)
    if not resultado["directas"]:
        return {
            "ok": False,
            "mensaje": "No se encontro una linea directa cercana",
            "sugerencias": resultado,
            "pasos": [],
        }

    linea = _elegir_linea_directa(resultado["directas"])
    po = linea["parada_origen"]
    pd = linea["parada_destino"]
    linea_catalogo = _linea_catalogo(linea["ref"], linea["operator"]) or {}
    paradas_bus = _paradas_tramo(linea_catalogo, po.get("idx"), pd.get("idx"))
    if not paradas_bus:
        paradas_bus = _paradas_basicas(po, pd)
    if paradas_bus:
        paradas_bus[0]["tipo"] = "subida"
        paradas_bus[-1]["tipo"] = "bajada"

    tramo_inicio = _ruta_por_calle(olat, olon, po["lat"], po["lon"], "pie")
    tramo_bus = _ruta_por_paradas(paradas_bus, "bus")
    tramo_final = _ruta_por_calle(pd["lat"], pd["lon"], dlat, dlon, "pie")
    tramos = [tramo_inicio, tramo_bus, tramo_final]
    if any(t.get("error") for t in tramos):
        return {
            "ok": False,
            "mensaje": "No se pudo calcular una ruta segura por calles reales para esta linea. No voy a dibujar lineas rectas falsas.",
            "sugerencias": resultado,
            "pasos": [],
            "errores_geometria": [
                {"tramo": idx + 1, "fuente": t.get("fuente"), "error": t.get("error")}
                for idx, t in enumerate(tramos)
                if t.get("error")
            ],
        }

    pasos = [
        {"tipo": "caminar", "instruccion": f"Camina hasta {po['nombre']}",
         "distancia_m": tramo_inicio["dist_m"], "lat": po["lat"], "lon": po["lon"]},
        {"tipo": "bus", "instruccion": f"Toma {linea['ref']} ({linea['name']})",
         "detalle": f"{linea['operator']} · tarifa {linea['tarifa']} · cada {linea['frecuencia']}",
         "distancia_m": tramo_bus["dist_m"], "lat": pd["lat"], "lon": pd["lon"]},
        {"tipo": "caminar", "instruccion": f"Baja en {pd['nombre']} y camina a tu destino",
         "distancia_m": tramo_final["dist_m"], "lat": dlat, "lon": dlon},
    ]
    total_m = tramo_inicio["dist_m"] + tramo_bus["dist_m"] + tramo_final["dist_m"]
    total_min = tramo_inicio["dur_min"] + tramo_bus["dur_min"] + tramo_final["dur_min"] + 3
    geometria_aproximada = (
        len(paradas_bus) <= 2
        and _distancia_recta_m(po["lat"], po["lon"], pd["lat"], pd["lon"]) > _PENALIZA_TRAMO_LARGO_SIN_PARADAS_M
    )
    segmentos = [
        {"tipo": "caminar", "path": tramo_inicio["path"], "fuente": tramo_inicio["fuente"]},
        {
            "tipo": "bus",
            "path": tramo_bus["path"],
            "fuente": tramo_bus["fuente"],
            "aproximado": geometria_aproximada,
        },
        {"tipo": "caminar", "path": tramo_final["path"], "fuente": tramo_final["fuente"]},
    ]
    fuentes = [s["fuente"] for s in segmentos]
    return {
        "ok": True,
        "linea": linea["ref"],
        "cooperativa": linea["operator"],
        "fuente": linea.get("fuente", "local"),
        "fuente_geometria": "OSRM" if all(str(f).startswith("OSRM") for f in fuentes) else "mixta",
        "geometria_aproximada": geometria_aproximada,
        "mensaje_geometria": (
            "Esta linea solo tiene subida y bajada mapeadas; se trazo por calles reales, pero faltan paradas intermedias."
            if geometria_aproximada else ""
        ),
        "horarios": linea.get("horarios"),
        "pasos": pasos,
        "polyline": _unir_paths([s["path"] for s in segmentos]),
        "segmentos": segmentos,
        "paradas_bus": paradas_bus,
        "distancia_total_m": total_m,
        "duracion_total_min": round(total_min, 1),
    }
