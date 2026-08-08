"""Generate the bundled sample datasets (deterministic).

Writes one CSV per dataset into `sample_data/` (files a user can download or
re-upload) and `core/sample.py`, which embeds all of them so the browser build
needs no extra fetch to load a demo.

Every builder uses a fixed seed, so re-running this script reproduces the same
tables byte for byte.

Run:  python scripts/make_sample.py
"""

from __future__ import annotations

import csv
import io
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── 01 · Agronomía ───────────────────────────────────────────────────────────

REGIONS = ["Norte", "Centro", "Sur", "Litoral"]
VARIETIES = ["Aurora", "Sembra", "Kirán"]
IRRIGATION = ["Goteo", "Aspersión", "Gravedad"]

HEADER = [
    "Parcela",
    "Region",
    "Variedad",
    "Riego",
    "Riego_mm",
    "Fertilizante_kg_ha",
    "Temp_media_C",
    "Horas_sol",
    "Rendimiento_ton_ha",
]


def build_rows(n: int = 140, seed: int = 20260808) -> list[list[object]]:
    rng = random.Random(seed)
    rows: list[list[object]] = [HEADER]

    for i in range(n):
        region = rng.choice(REGIONS)
        variety = rng.choice(VARIETIES)
        irrigation = rng.choice(IRRIGATION)

        # Regional baselines keep the categorical columns informative.
        base_water = {"Norte": 380, "Centro": 460, "Sur": 520, "Litoral": 600}[region]
        water = round(rng.gauss(base_water, 70), 1)
        water = max(180.0, water)

        fertiliser = round(max(20.0, rng.gauss(160, 42)), 1)
        temperature = round(rng.gauss({"Norte": 17.5, "Centro": 20.0,
                                       "Sur": 22.5, "Litoral": 24.0}[region], 1.9), 1)
        sunshine = round(max(3.5, rng.gauss(7.6, 1.15)), 2)

        variety_bonus = {"Aurora": 0.0, "Sembra": 0.28, "Kirán": -0.18}[variety]

        # Fertiliser is the dominant driver (strong fit, R² ~0.76) while water,
        # sunshine and temperature are only weakly predictive on their own. That
        # spread gives each variable pairing a visibly different result, with
        # mild diminishing returns so the relationship is not perfectly linear.
        yield_ton = (
            0.85
            + 0.0225 * fertiliser
            - 0.0000175 * fertiliser * fertiliser
            + 0.0034 * water
            - 0.0000011 * water * water
            + 0.132 * sunshine
            + variety_bonus
            + rng.gauss(0, 0.22)
        )
        yield_ton = round(max(0.6, yield_ton), 2)

        rows.append([
            f"P-{i + 1:03d}",
            region,
            variety,
            irrigation,
            water,
            fertiliser,
            temperature,
            sunshine,
            yield_ton,
        ])

    return rows


# ── 02 · Salud ───────────────────────────────────────────────────────────────

HEALTH_HEADER = [
    "Paciente",
    "Sexo",
    "Grupo_edad",
    "Actividad_fisica",
    "Edad",
    "IMC",
    "Colesterol_mg_dl",
    "Horas_sueno",
    "Presion_sistolica",
]


def build_health(n: int = 150, seed: int = 20260809) -> list[list[object]]:
    """Cardiovascular check-ups: age and BMI drive systolic pressure."""
    rng = random.Random(seed)
    rows: list[list[object]] = [HEALTH_HEADER]

    for i in range(n):
        sex = rng.choice(["Femenino", "Masculino"])
        activity = rng.choices(["Baja", "Media", "Alta"], weights=[38, 42, 20])[0]

        age = rng.randint(18, 79)
        group = (
            "18-34" if age < 35 else "35-49" if age < 50 else "50-64" if age < 65 else "65+"
        )

        bmi_base = {"Baja": 29.4, "Media": 26.3, "Alta": 23.8}[activity]
        bmi = round(max(16.5, rng.gauss(bmi_base + 0.035 * (age - 45), 2.9)), 1)

        cholesterol = round(
            max(110.0, 148 + 0.88 * age + 2.4 * (bmi - 25) + rng.gauss(0, 17)), 1
        )
        sleep = round(min(10.0, max(3.5, rng.gauss(7.0, 1.05))), 1)

        # Age is the dominant term and BMI the second: a clean pairing for the
        # regression module, while sleep and cholesterol stay weakly predictive
        # on their own.
        systolic = (
            78.0
            + 0.62 * age
            + 1.25 * bmi
            + 0.035 * (cholesterol - 180)
            - 2.0 * (sleep - 7.0)
            + {"Baja": 2.6, "Media": 0.0, "Alta": -2.4}[activity]
            + (2.8 if sex == "Masculino" else 0.0)
            + rng.gauss(0, 6.0)
        )
        systolic = round(min(196.0, max(92.0, systolic)), 1)

        rows.append([
            f"PAC-{i + 1:03d}",
            sex,
            group,
            activity,
            age,
            bmi,
            cholesterol,
            sleep,
            systolic,
        ])

    return rows


# ── 03 · Educación ───────────────────────────────────────────────────────────

EDU_HEADER = [
    "Estudiante",
    "Carrera",
    "Jornada",
    "Beca",
    "Horas_estudio_sem",
    "Asistencia_pct",
    "Horas_pantalla_dia",
    "Puntaje_final",
]

CAREERS = ["Ingeniería", "Biología", "Economía", "Enfermería"]


def build_education(n: int = 160, seed: int = 20260810) -> list[list[object]]:
    """Academic performance: weekly study hours drive the final score."""
    rng = random.Random(seed)
    rows: list[list[object]] = [EDU_HEADER]

    for i in range(n):
        career = rng.choice(CAREERS)
        shift = rng.choices(["Diurna", "Vespertina"], weights=[64, 36])[0]
        scholarship = rng.choices(["Sí", "No"], weights=[35, 65])[0]

        study_base = 13.5 if shift == "Diurna" else 9.5
        study = round(min(32.0, max(1.5, rng.gauss(study_base, 4.6))), 1)
        attendance = round(min(100.0, max(42.0, rng.gauss(84.0, 10.5))), 1)
        screen = round(min(9.5, max(0.5, rng.gauss(4.3, 1.35))), 1)

        # Study hours explain most of the variance in the score; attendance adds
        # a second, weaker signal.
        score = (
            17.0
            + 1.62 * study
            + 0.40 * attendance
            - 1.55 * screen
            + (3.1 if scholarship == "Sí" else 0.0)
            + {"Ingeniería": -1.2, "Biología": 0.6,
               "Economía": 0.0, "Enfermería": 1.4}[career]
            + rng.gauss(0, 5.4)
        )
        score = round(min(100.0, max(12.0, score)), 1)

        rows.append([
            f"EST-{i + 1:03d}",
            career,
            shift,
            scholarship,
            study,
            attendance,
            screen,
            score,
        ])

    return rows


# ── 04 · Economía ────────────────────────────────────────────────────────────

SALES_HEADER = [
    "Sucursal",
    "Ciudad",
    "Categoria",
    "Canal",
    "Inversion_publicidad_kUSD",
    "Precio_medio_USD",
    "Visitas_miles",
    "Ventas_kUSD",
]

CITIES = ["Quito", "Guayaquil", "Cuenca", "Manta", "Loja"]
CATEGORIES = ["Tecnología", "Hogar", "Vestuario", "Alimentos"]
CHANNELS = ["Tienda física", "Online", "Mixto"]


def build_sales(n: int = 150, seed: int = 20260811) -> list[list[object]]:
    """Retail branches: ad spend and traffic drive monthly revenue."""
    rng = random.Random(seed)
    rows: list[list[object]] = [SALES_HEADER]

    for i in range(n):
        city = rng.choice(CITIES)
        category = rng.choice(CATEGORIES)
        channel = rng.choices(CHANNELS, weights=[45, 27, 28])[0]

        spend = round(max(4.0, rng.gauss(46.0, 15.5)), 1)
        price_base = {"Tecnología": 320.0, "Hogar": 96.0,
                      "Vestuario": 54.0, "Alimentos": 21.0}[category]
        price = round(max(6.0, rng.gauss(price_base, price_base * 0.18)), 2)

        # Traffic partly follows ad spend, so the two predictors overlap the way
        # they do in real commercial data.
        visits = round(max(1.2, 9.5 + 0.30 * spend + rng.gauss(0, 4.2)), 2)

        revenue = (
            22.0
            + 1.95 * spend
            + 2.35 * visits
            - 0.012 * price
            + {"Tienda física": 0.0, "Online": 9.5, "Mixto": 14.0}[channel]
            + {"Quito": 6.0, "Guayaquil": 7.5, "Cuenca": 0.0,
               "Manta": -3.5, "Loja": -6.0}[city]
            + rng.gauss(0, 13.5)
        )
        revenue = round(max(5.0, revenue), 2)

        rows.append([
            f"SUC-{i + 1:03d}",
            city,
            category,
            channel,
            spend,
            price,
            visits,
            revenue,
        ])

    return rows


# ── 05 · Medio ambiente ──────────────────────────────────────────────────────

AIR_HEADER = [
    "Registro",
    "Ciudad",
    "Zona",
    "Estacion_del_ano",
    "Trafico_veh_hora",
    "Temp_media_C",
    "Humedad_pct",
    "Viento_km_h",
    "PM25_ug_m3",
]

ZONES = ["Industrial", "Céntrica", "Residencial", "Periurbana"]
SEASONS = ["Verano", "Otoño", "Invierno", "Primavera"]


def build_air(n: int = 150, seed: int = 20260812) -> list[list[object]]:
    """Air-quality stations: traffic raises PM2.5, wind disperses it."""
    rng = random.Random(seed)
    rows: list[list[object]] = [AIR_HEADER]

    for i in range(n):
        city = rng.choice(CITIES)
        zone = rng.choice(ZONES)
        season = rng.choice(SEASONS)

        traffic_base = {"Industrial": 1450, "Céntrica": 1750,
                        "Residencial": 780, "Periurbana": 420}[zone]
        traffic = int(max(90, rng.gauss(traffic_base, 320)))

        temp = round(rng.gauss({"Verano": 24.5, "Otoño": 19.0,
                                "Invierno": 14.5, "Primavera": 20.5}[season], 2.6), 1)
        humidity = round(min(98.0, max(28.0, rng.gauss(68.0, 11.5))), 1)
        wind = round(max(0.6, rng.gauss(11.5, 4.3)), 1)

        # Traffic is the leading term and wind the clearest negative one, so the
        # regression module shows both signs of slope on the same table.
        pm25 = (
            9.0
            + 0.0135 * traffic
            - 0.92 * wind
            - 0.055 * humidity
            + {"Industrial": 7.5, "Céntrica": 3.0,
               "Residencial": 0.0, "Periurbana": -2.5}[zone]
            + {"Verano": -1.5, "Otoño": 1.0,
               "Invierno": 5.5, "Primavera": 0.0}[season]
            + rng.gauss(0, 3.4)
        )
        pm25 = round(max(1.4, pm25), 1)

        rows.append([
            f"AIR-{i + 1:03d}",
            city,
            zone,
            season,
            traffic,
            temp,
            humidity,
            wind,
            pm25,
        ])

    return rows


# ── catalogue ────────────────────────────────────────────────────────────────

DATASETS = [
    {
        "key": "cultivos",
        "constant": "CULTIVOS_CSV",
        "name": "rendimiento_cultivos.csv",
        "title": "Rendimiento de cultivos",
        "area": "Agronomía",
        "description": (
            "Parcelas agrícolas con riego, fertilización y clima. "
            "El fertilizante explica la mayor parte del rendimiento."
        ),
        "target": "Rendimiento_ton_ha",
        "driver": "Fertilizante_kg_ha",
        "build": build_rows,
    },
    {
        "key": "salud",
        "constant": "SALUD_CSV",
        "name": "salud_cardiovascular.csv",
        "title": "Chequeo cardiovascular",
        "area": "Salud",
        "description": (
            "Pacientes con edad, IMC, colesterol y horas de sueño frente "
            "a la presión sistólica. La edad es el predictor dominante."
        ),
        "target": "Presion_sistolica",
        "driver": "Edad",
        "build": build_health,
    },
    {
        "key": "educacion",
        "constant": "EDUCACION_CSV",
        "name": "rendimiento_academico.csv",
        "title": "Rendimiento académico",
        "area": "Educación",
        "description": (
            "Estudiantes con horas de estudio, asistencia y tiempo de "
            "pantalla frente al puntaje final sobre 100."
        ),
        "target": "Puntaje_final",
        "driver": "Horas_estudio_sem",
        "build": build_education,
    },
    {
        "key": "ventas",
        "constant": "VENTAS_CSV",
        "name": "ventas_retail.csv",
        "title": "Ventas de retail",
        "area": "Economía",
        "description": (
            "Sucursales con inversión publicitaria, precio medio y tráfico "
            "de clientes frente a las ventas mensuales en miles de USD."
        ),
        "target": "Ventas_kUSD",
        "driver": "Inversion_publicidad_kUSD",
        "build": build_sales,
    },
    {
        "key": "aire",
        "constant": "AIRE_CSV",
        "name": "calidad_aire.csv",
        "title": "Calidad del aire",
        "area": "Medio ambiente",
        "description": (
            "Mediciones de estaciones urbanas: tráfico, viento y humedad "
            "frente a la concentración de PM2.5."
        ),
        "target": "PM25_ug_m3",
        "driver": "Trafico_veh_hora",
        "build": build_air,
    },
]


def to_csv(rows: list[list[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def count_numeric(rows: list[list[object]]) -> int:
    """Columns whose every data cell is a number — mirrors core/dataset.py."""
    numeric = 0
    for index in range(len(rows[0])):
        values = [row[index] for row in rows[1:]]
        if values and all(isinstance(value, (int, float)) for value in values):
            numeric += 1
    return numeric


MODULE_DOC = '''"""Bundled sample datasets — generated by scripts/make_sample.py.

Embedded as a module so the Pyodide build can load any demo dataset without a
second network request. Five tables from different fields, each with a clear
quantitative relationship to explore. Do not edit by hand.
"""

'''

MODULE_FOOTER = '''

SAMPLE_INDEX = {item["key"]: item for item in SAMPLES}
DEFAULT_SAMPLE = SAMPLES[0]["key"]

# Back-compat aliases: the first dataset is the one loaded when no key is given.
SAMPLE_NAME = SAMPLES[0]["name"]
SAMPLE_CSV = SAMPLES[0]["csv"]


def catalog() -> list[dict]:
    """Metadata for every dataset, without the CSV payloads."""
    return [
        {key: value for key, value in item.items() if key != "csv"}
        for item in SAMPLES
    ]


def get(key: str | None = None) -> dict | None:
    """Look up one dataset by key; None when the key is unknown."""
    return SAMPLE_INDEX.get(key or DEFAULT_SAMPLE)
'''


def entry_source(spec: dict, rows: list[list[object]]) -> str:
    numeric = count_numeric(rows)
    return "\n".join([
        "    {",
        f'        "key": "{spec["key"]}",',
        f'        "name": "{spec["name"]}",',
        f'        "title": "{spec["title"]}",',
        f'        "area": "{spec["area"]}",',
        f'        "description": "{spec["description"]}",',
        f'        "rows": {len(rows) - 1},',
        f'        "columns": {len(rows[0])},',
        f'        "numeric": {numeric},',
        f'        "categorical": {len(rows[0]) - numeric},',
        f'        "target": "{spec["target"]}",',
        f'        "driver": "{spec["driver"]}",',
        f'        "csv": {spec["constant"]},',
        "    },",
    ])


def main() -> None:
    parts: list[str] = [MODULE_DOC]
    entries: list[str] = []

    for spec in DATASETS:
        rows = spec["build"]()
        text = to_csv(rows)

        csv_path = ROOT / "sample_data" / spec["name"]
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(text, encoding="utf-8")
        print(f"wrote sample_data/{spec['name']}  ({len(rows) - 1} filas)")

        parts.append(f"{spec['constant']} = '''{text}'''\n\n")
        entries.append(entry_source(spec, rows))

    parts.append("SAMPLES = [\n" + "\n".join(entries) + "\n]\n")
    parts.append(MODULE_FOOTER)

    source = "".join(parts)
    module = ROOT / "core" / "sample.py"
    module.write_text(source, encoding="utf-8")
    print(f"wrote core/sample.py  ({len(source):,} bytes, {len(DATASETS)} datasets)")


if __name__ == "__main__":
    main()
