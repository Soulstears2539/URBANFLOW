"""Catálogo local de líneas de transporte de Quito.

Dataset semilla con líneas troncales y alimentadoras reales de Quito
(Trole, Ecovía, Metrobús/Corredores y líneas convencionales). Cada línea
incluye paradas representativas con coordenadas aproximadas.

Estructura por línea:
    {
        "ref": str, "name": str, "tipo": str, "colour": str,
        "operator": str, "frecuencia": str, "horario": str, "tarifa": str,
        "paradas": [(nombre, lat, lon), ...]
    }
"""
from __future__ import annotations

QUITO_BUSES: list[dict] = [
    {
        "ref": "Trole", "name": "Trolebús: Estación Norte - Quitumbe",
        "tipo": "trolleybus", "colour": "#c0392b", "operator": "Trolebús EPMTP",
        "frecuencia": "5-8 min", "horario": "05:00-23:30", "tarifa": "0.35",
        "paradas": [
            ("Estación Norte (La Y)", -0.1746, -78.4830),
            ("Estación La Y", -0.1801, -78.4855),
            ("Mariana de Jesús", -0.1925, -78.4900),
            ("La Colón", -0.2010, -78.4920),
            ("El Ejido", -0.2095, -78.4972),
            ("Santo Domingo", -0.2207, -78.5128),
            ("La Marín", -0.2230, -78.5090),
            ("El Recreo", -0.2520, -78.5210),
            ("Morán Valverde", -0.2960, -78.5430),
            ("Quitumbe", -0.2980, -78.5510),
        ],
    },
    {
        "ref": "Ecovia", "name": "Ecovía: La Marín - Río Coca",
        "tipo": "bus", "colour": "#2980b9", "operator": "Ecovía EPMTP",
        "frecuencia": "6-10 min", "horario": "05:00-22:00", "tarifa": "0.35",
        "paradas": [
            ("La Marín", -0.2230, -78.5090),
            ("Plaza del Teatro", -0.2185, -78.5120),
            ("Manuela Sáenz", -0.2120, -78.5040),
            ("La Floresta", -0.2030, -78.4880),
            ("Estadio Olímpico", -0.1960, -78.4830),
            ("La Carolina", -0.1820, -78.4820),
            ("Estación Río Coca", -0.1690, -78.4790),
        ],
    },
    {
        "ref": "C4", "name": "Corredor Central Norte: Ofelia - Universidades",
        "tipo": "bus", "colour": "#27ae60", "operator": "EPMTP",
        "frecuencia": "8-12 min", "horario": "05:30-22:30", "tarifa": "0.35",
        "paradas": [
            ("Terminal La Ofelia", -0.1080, -78.4880),
            ("Cotocollao", -0.1090, -78.4960),
            ("La Y", -0.1801, -78.4855),
            ("Estadio", -0.1960, -78.4830),
            ("La Pradera", -0.1990, -78.4870),
            ("Universidad Central", -0.2000, -78.5020),
        ],
    },
    {
        "ref": "Metro-L1", "name": "Metro de Quito Línea 1: Quitumbe - El Labrador",
        "tipo": "subway", "colour": "#8e44ad", "operator": "Metro de Quito",
        "frecuencia": "4-7 min", "horario": "05:30-23:00", "tarifa": "0.45",
        "paradas": [
            ("Quitumbe", -0.2980, -78.5510),
            ("Morán Valverde", -0.2960, -78.5430),
            ("El Recreo", -0.2520, -78.5210),
            ("La Magdalena", -0.2370, -78.5180),
            ("San Francisco", -0.2200, -78.5150),
            ("La Alameda", -0.2130, -78.5050),
            ("El Ejido", -0.2095, -78.4972),
            ("Universidad Central", -0.2000, -78.5020),
            ("La Pradera", -0.1990, -78.4870),
            ("La Carolina", -0.1820, -78.4820),
            ("Iñaquito", -0.1760, -78.4860),
            ("Jipijapa", -0.1700, -78.4800),
            ("El Labrador", -0.1640, -78.4860),
        ],
    },
    {
        "ref": "16", "name": "Línea 16: La Marín - Cumbayá",
        "tipo": "bus", "colour": "#e67e22", "operator": "Trans Oriental",
        "frecuencia": "10-15 min", "horario": "06:00-21:00", "tarifa": "0.35",
        "paradas": [
            ("La Marín", -0.2230, -78.5090),
            ("Av. Gonzáles Suárez", -0.2030, -78.4760),
            ("Guápulo", -0.2050, -78.4650),
            ("Túnel Guápulo", -0.2010, -78.4530),
            ("Cumbayá Centro", -0.1980, -78.4360),
        ],
    },
    {
        "ref": "201", "name": "Línea 201: Carcelén - El Tingo",
        "tipo": "bus", "colour": "#16a085", "operator": "Cooperativa Carcelén",
        "frecuencia": "12-18 min", "horario": "05:30-21:30", "tarifa": "0.35",
        "paradas": [
            ("Terminal Carcelén", -0.0980, -78.4760),
            ("Ponceano", -0.1100, -78.4880),
            ("La Y", -0.1801, -78.4855),
            ("El Ejido", -0.2095, -78.4972),
            ("La Marín", -0.2230, -78.5090),
            ("El Tingo", -0.3060, -78.4490),
        ],
    },
]


def buses_summary() -> list[dict]:
    """Catálogo resumido (sin paradas completas)."""
    return [
        {
            "ref": b["ref"], "name": b["name"], "tipo": b["tipo"],
            "operator": b["operator"], "colour": b["colour"],
            "frecuencia": b["frecuencia"], "horario": b["horario"],
            "tarifa": b["tarifa"], "n_paradas": len(b["paradas"]),
        }
        for b in QUITO_BUSES
    ]


def bus_detail(ref: str) -> dict | None:
    for b in QUITO_BUSES:
        if b["ref"].lower() == ref.lower():
            data = dict(b)
            data["paradas"] = [
                {"nombre": n, "lat": la, "lon": lo} for n, la, lo in b["paradas"]
            ]
            return data
    return None
