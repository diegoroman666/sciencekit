"""Single dispatch surface for every analysis operation.

Both transports call straight into `dispatch()`:

  * Flask (`app.py`)  — HTTP POST /api/<action>, server-side CPython
  * Pyodide (`app.js`) — direct in-browser call, no server at all

Keeping the whole operation set here means the deployed static build and the
local dev server execute byte-identical logic; neither transport holds any
analysis code of its own.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from typing import Any

from . import analysis, charts
from .dataset import Dataset, read_bytes, read_csv
from .fmt import es

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


class ApiError(Exception):
    """A message that is safe and useful to show the user directly."""


class Session:
    """Holds the dataset currently under analysis, plus the last fitted model."""

    def __init__(self) -> None:
        self.dataset: Dataset | None = None
        self.model: dict[str, float] | None = None
        self.model_pair: tuple[str, str] | None = None

    def require_dataset(self) -> Dataset:
        if self.dataset is None:
            raise ApiError("Cargue un dataset para comenzar el análisis.")
        return self.dataset


def _clean(value: Any) -> Any:
    """Make a value JSON-safe: NaN/Infinity are not valid JSON."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _number(payload: dict[str, Any], key: str, required: bool = True) -> float | None:
    raw = payload.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if required:
            raise ApiError(f"Falta el valor «{key}».")
        return None
    try:
        # Accept a decimal comma, which Spanish keyboards produce.
        return float(str(raw).strip().replace(",", "."))
    except ValueError:
        raise ApiError(f"«{raw}» no es un número válido.")


def _text(payload: dict[str, Any], key: str) -> str:
    raw = payload.get(key)
    if not raw or not str(raw).strip():
        raise ApiError(f"Seleccione un valor para «{key}».")
    return str(raw).strip()


# -- actions ------------------------------------------------------------------


def _load(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Ingest an uploaded file. Content arrives base64-encoded or as raw text."""
    filename = str(payload.get("filename") or "dataset.csv")

    if "content_b64" in payload and payload["content_b64"]:
        try:
            data = base64.b64decode(payload["content_b64"], validate=True)
        except (binascii.Error, ValueError):
            raise ApiError("El contenido del archivo no se pudo decodificar.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiError(
                f"El archivo supera el límite de "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        dataset = read_bytes(data, filename)
    elif "text" in payload:
        text = str(payload["text"])
        if len(text.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise ApiError("El archivo es demasiado grande.")
        dataset = read_csv(text, name=filename)
    else:
        raise ApiError("No se recibió ningún archivo.")

    session.dataset = dataset
    session.model = None
    session.model_pair = None
    return {"dataset": dataset.to_dict()}


def _sample(key: Any) -> dict[str, Any]:
    """Resolve one bundled dataset by key, or raise a user-facing error."""
    from . import sample as samples

    requested = str(key).strip() if key else None
    item = samples.get(requested)
    if item is None:
        raise ApiError(f"No existe un dataset de ejemplo llamado «{requested}».")
    return item


def _samples(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Catalogue of the bundled datasets — metadata only, no CSV payloads."""
    from . import sample as samples

    return {"samples": samples.catalog(), "default": samples.DEFAULT_SAMPLE}


def _demo(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Load a bundled sample dataset so the app is usable with zero setup."""
    item = _sample(payload.get("sample"))

    dataset = read_csv(item["csv"], name=item["name"])
    session.dataset = dataset
    session.model = None
    session.model_pair = None
    return {"dataset": dataset.to_dict(), "demo": True, "sample": item["key"]}


def _sample_csv(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Hand back the raw CSV of a bundled dataset, for the download button."""
    item = _sample(payload.get("sample"))
    return {"name": item["name"], "title": item["title"], "csv": item["csv"]}


def _describe(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Descriptive statistics for a quantitative column, or a frequency table."""
    dataset = session.require_dataset()
    column = _text(payload, "column")
    col = dataset.column(column)

    if col.is_numeric:
        stats = analysis.descriptive_stats(dataset, column)
        return {
            "kind": "quantitative",
            "stats": stats,
            "chart": charts.histogram_chart(stats["histogram"], column),
        }

    table = analysis.frequency_table(dataset, column)
    return {
        "kind": "qualitative",
        "table": table,
        "chart": charts.bars(
            [r["value"] for r in table["rows"]],
            [r["count"] for r in table["rows"]],
            x_label=column,
        ),
    }


def _frequency(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    dataset = session.require_dataset()
    column = _text(payload, "column")
    table = analysis.frequency_table(dataset, column)
    return {
        "table": table,
        "chart": charts.bars(
            [r["value"] for r in table["rows"]],
            [r["count"] for r in table["rows"]],
            x_label=column,
        ),
    }


def _chart(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Render the chart module's selected visualisation."""
    dataset = session.require_dataset()
    kind = str(payload.get("type") or "scatter")

    if kind == "scatter":
        x_name = _text(payload, "x")
        y_name = _text(payload, "y")
        xs, ys = dataset.pairs(x_name, y_name)
        if not xs:
            raise ApiError(
                "No hay filas con valores numéricos en ambas variables."
            )

        line = None
        stats = None
        if payload.get("fit") and len(xs) >= 3:
            try:
                model = analysis.linear_regression(xs, ys)
                line = {"m": model["m"], "b": model["b"]}
                stats = {"r": model["r"], "r2": model["r2"], "m": model["m"], "b": model["b"]}
            except ValueError:
                line = None  # a constant series just means "no fit to draw"

        return {
            "chart": charts.scatter(
                [{"x": a, "y": b} for a, b in zip(xs, ys)],
                x_name, y_name, line=line,
            ),
            "points": len(xs),
            "dropped": dataset.row_count - len(xs),
            "fit": stats,
        }

    if kind == "histogram":
        column = _text(payload, "x")
        col = dataset.column(column)
        if not col.is_numeric:
            raise ApiError(
                f"«{column}» es cualitativa: use el gráfico de barras."
            )
        hist = analysis.histogram(col.numbers())
        return {"chart": charts.histogram_chart(hist, column), "points": len(col.numbers())}

    if kind == "bars":
        column = _text(payload, "x")
        table = analysis.frequency_table(dataset, column)
        return {
            "chart": charts.bars(
                [r["value"] for r in table["rows"]],
                [r["count"] for r in table["rows"]],
                x_label=column,
            ),
            "points": table["total"],
            "distinct": table["distinct"],
        }

    raise ApiError(f"Tipo de gráfico no reconocido: {kind}")


def _regression(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Fit y = mx + b and remember the model for subsequent predictions."""
    dataset = session.require_dataset()
    x_name = _text(payload, "x")
    y_name = _text(payload, "y")

    if x_name == y_name:
        raise ApiError(
            "Las variables X e Y deben ser distintas: predecir una variable "
            "a partir de sí misma no aporta información."
        )

    report = analysis.regression_report(dataset, x_name, y_name)
    session.model = report["model"]
    session.model_pair = (x_name, y_name)

    return {
        "report": report,
        "chart": charts.scatter(
            report["points"], x_name, y_name,
            line={"m": report["model"]["m"], "b": report["model"]["b"]},
        ),
    }


def _predict(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the stored model at a given x."""
    if session.model is None or session.model_pair is None:
        raise ApiError("Entrene un modelo antes de predecir.")

    dataset = session.require_dataset()
    x_name, y_name = session.model_pair
    x_value = _number(payload, "value")
    result = analysis.predict(session.model, x_value)

    xs, ys = dataset.pairs(x_name, y_name)
    chart = charts.scatter(
        [{"x": a, "y": b} for a, b in zip(xs, ys)],
        x_name, y_name,
        line={"m": session.model["m"], "b": session.model["b"]},
        highlight={"x": result["x"], "y": result["y"]},
    )

    trend = "aumentar" if session.model["m"] > 0 else "disminuir"
    result["advice"] = (
        f"Con «{x_name}» = {es(x_value)}, el modelo proyecta «{y_name}» ≈ "
        f"{es(result['y'], 2)}. La relación ajustada indica que «{y_name}» "
        f"tiende a {trend} conforme «{x_name}» crece."
    )

    return {"prediction": result, "chart": chart, "x": x_name, "y": y_name}


def _normal(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """μ / σ profile plus the bell curve for a quantitative column."""
    dataset = session.require_dataset()
    column = _text(payload, "column")
    profile = analysis.normal_profile(dataset, column)
    return {
        "profile": profile,
        "chart": charts.normal_curve(
            profile["mu"], profile["sigma"], label=f"Distribución normal de {column}"
        ),
    }


def _probability(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Normal probability for the selected query, with the region shaded."""
    mu = _number(payload, "mu")
    sigma = _number(payload, "sigma")
    kind = str(payload.get("kind") or analysis.P_LESS)
    needs_b = kind in (analysis.P_BETWEEN, analysis.P_OUTSIDE)

    result = analysis.probability(
        mu, sigma, kind,
        a=_number(payload, "a"),
        b=_number(payload, "b", required=needs_b),
    )

    return {
        "result": result,
        "chart": charts.normal_curve(
            mu, sigma, shade=result["shade"], label=result["expression"]
        ),
    }


ACTIONS = {
    "load": _load,
    "demo": _demo,
    "samples": _samples,
    "sample_csv": _sample_csv,
    "describe": _describe,
    "frequency": _frequency,
    "chart": _chart,
    "regression": _regression,
    "predict": _predict,
    "normal": _normal,
    "probability": _probability,
}


def dispatch(session: Session, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run `action` against `session`. Returns {ok: True, ...} or {ok: False, error}."""
    handler = ACTIONS.get(action)
    if handler is None:
        return {"ok": False, "error": f"Acción desconocida: {action}"}

    try:
        result = handler(session, payload or {})
    except (ApiError, ValueError, KeyError) as exc:
        return {"ok": False, "error": str(exc).strip("'\"")}
    except Exception as exc:  # unexpected — surface the type, keep the app alive
        return {"ok": False, "error": f"Error inesperado ({type(exc).__name__}): {exc}"}

    return _clean({"ok": True, **result})


def dispatch_json(session: Session, action: str, payload_json: str) -> str:
    """JSON-in / JSON-out wrapper, used by the Pyodide bridge."""
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"JSON inválido: {exc}"})
    return json.dumps(dispatch(session, action, payload), allow_nan=False)
