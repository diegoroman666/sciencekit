"""Descriptive statistics, frequency tables, regression and probability.

Port of the original Dart `MathUtils` and `DataProvider` statistics methods.
Standard library only — runs unchanged under CPython and Pyodide.
"""

from __future__ import annotations

import math
from typing import Any

from .dataset import Dataset
from .fmt import es, pct

# -- descriptive statistics ---------------------------------------------------


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile (the method Excel's PERCENTILE uses)."""
    if not sorted_values:
        raise ValueError("Serie vacía.")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return sorted_values[int(pos)]
    return sorted_values[low] * (high - pos) + sorted_values[high] * (pos - low)


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("Serie vacía.")
    return math.fsum(values) / len(values)


def std_dev(values: list[float], population: bool = True) -> float:
    """Standard deviation. Population (N) by default, matching the Dart original."""
    if not values:
        raise ValueError("Serie vacía.")
    n = len(values)
    if n == 1:
        return 0.0
    mu = mean(values)
    total = math.fsum((v - mu) ** 2 for v in values)
    return math.sqrt(total / (n if population else n - 1))


def modes(values: list[Any]) -> list[Any]:
    """All values tied for the highest frequency, or [] when every value is unique."""
    counts: dict[Any, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return []
    top = max(counts.values())
    if top == 1:
        return []
    return [v for v, c in counts.items() if c == top]


def descriptive_stats(dataset: Dataset, column_name: str) -> dict[str, Any]:
    """Central-tendency and dispersion measures for a quantitative column."""
    col = dataset.column(column_name)
    if not col.is_numeric:
        raise ValueError(
            f"'{column_name}' es una variable cualitativa. "
            "Use la tabla de frecuencias para analizarla."
        )

    data = sorted(col.numbers())
    if not data:
        raise ValueError(f"'{column_name}' no contiene valores numéricos válidos.")

    n = len(data)
    mu = mean(data)
    sigma = std_dev(data)
    q1 = _percentile(data, 0.25)
    q2 = _percentile(data, 0.50)
    q3 = _percentile(data, 0.75)
    found_modes = modes(data)

    return {
        "column": column_name,
        "n": n,
        "missing": col.missing,
        # Ordered for display: label -> value. `None` renders as "—".
        "measures": [
            {"label": "Media", "symbol": "x̄", "value": mu, "group": "center"},
            {"label": "Mediana", "symbol": "Q2", "value": q2, "group": "center"},
            {
                "label": "Moda",
                "symbol": "Mo",
                "value": found_modes[0] if len(found_modes) == 1 else None,
                "note": (
                    "sin moda" if not found_modes
                    else f"{len(found_modes)} modas" if len(found_modes) > 1
                    else None
                ),
                "group": "center",
            },
            {"label": "Desv. estándar", "symbol": "σ", "value": sigma, "group": "spread"},
            {"label": "Varianza", "symbol": "σ²", "value": sigma ** 2, "group": "spread"},
            {
                "label": "Coef. variación",
                "symbol": "CV",
                "value": (sigma / mu * 100) if mu != 0 else None,
                "suffix": "%",
                "group": "spread",
            },
            {"label": "Rango", "symbol": "R", "value": data[-1] - data[0], "group": "spread"},
            {"label": "Mínimo", "symbol": "min", "value": data[0], "group": "position"},
            {"label": "Q1", "symbol": "Q1", "value": q1, "group": "position"},
            {"label": "Q3", "symbol": "Q3", "value": q3, "group": "position"},
            {"label": "Máximo", "symbol": "max", "value": data[-1], "group": "position"},
            {"label": "Rango interc.", "symbol": "IQR", "value": q3 - q1, "group": "position"},
        ],
        "summary": {"mean": mu, "median": q2, "std_dev": sigma, "min": data[0], "max": data[-1]},
        "histogram": histogram(data),
    }


def histogram(data: list[float], bins: int = 0) -> dict[str, Any]:
    """Bin a numeric series using the Sturges rule when `bins` is not given."""
    if not data:
        return {"bins": [], "max_count": 0}
    lo, hi = min(data), max(data)

    if bins <= 0:
        bins = max(4, min(16, int(math.ceil(math.log2(len(data)) + 1)) if len(data) > 1 else 4))

    if hi == lo:
        return {
            "bins": [{"start": lo, "end": lo, "count": len(data)}],
            "max_count": len(data),
        }

    width = (hi - lo) / bins
    counts = [0] * bins
    for v in data:
        idx = int((v - lo) / width)
        if idx >= bins:  # the maximum lands exactly on the upper edge
            idx = bins - 1
        counts[idx] += 1

    return {
        "bins": [
            {"start": lo + i * width, "end": lo + (i + 1) * width, "count": c}
            for i, c in enumerate(counts)
        ],
        "max_count": max(counts),
    }


def frequency_table(dataset: Dataset, column_name: str, limit: int = 40) -> dict[str, Any]:
    """Absolute, relative and cumulative frequencies, sorted by count desc."""
    col = dataset.column(column_name)
    present = [v for v in col.values if v is not None]
    if not present:
        raise ValueError(f"'{column_name}' no contiene valores.")

    counts: dict[Any, int] = {}
    for v in present:
        counts[v] = counts.get(v, 0) + 1

    total = len(present)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    truncated = max(0, len(ordered) - limit)

    rows = []
    cumulative = 0
    for value, count in ordered[:limit]:
        cumulative += count
        rows.append({
            "value": value,
            "count": count,
            "relative": count / total,
            "cumulative": cumulative / total,
        })

    return {
        "column": column_name,
        "kind": col.kind,
        "total": total,
        "distinct": len(counts),
        "missing": col.missing,
        "truncated": truncated,
        "rows": rows,
        "max_count": ordered[0][1] if ordered else 0,
    }


# -- linear regression --------------------------------------------------------


def linear_regression(x: list[float], y: list[float]) -> dict[str, float]:
    """Least-squares fit y = mx + b, with Pearson r, R² and standard error.

    Fixes a divide-by-zero in the Dart original: when y is constant the
    correlation denominator is 0, which produced NaN instead of a clear error.
    """
    if len(x) != len(y):
        raise ValueError("Las series X e Y deben tener el mismo tamaño.")
    n = len(x)
    if n < 3:
        raise ValueError(
            "Se necesitan al menos 3 pares de datos completos para ajustar "
            f"un modelo (se encontraron {n})."
        )

    sum_x = math.fsum(x)
    sum_y = math.fsum(y)
    sum_xy = math.fsum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = math.fsum(xi * xi for xi in x)
    sum_y2 = math.fsum(yi * yi for yi in y)

    var_x = n * sum_x2 - sum_x * sum_x
    var_y = n * sum_y2 - sum_y * sum_y

    if var_x == 0:
        raise ValueError(
            "La variable independiente (X) es constante: no define una "
            "pendiente. Elija otra variable."
        )
    if var_y == 0:
        raise ValueError(
            "La variable dependiente (Y) es constante: no hay variabilidad "
            "que explicar. Elija otra variable."
        )

    covariance = n * sum_xy - sum_x * sum_y
    m = covariance / var_x
    b = (sum_y - m * sum_x) / n
    r = covariance / math.sqrt(var_x * var_y)
    r = max(-1.0, min(1.0, r))  # clamp against floating-point drift

    residual_ss = math.fsum((yi - (m * xi + b)) ** 2 for xi, yi in zip(x, y))
    std_error = math.sqrt(residual_ss / (n - 2)) if n > 2 else 0.0

    return {
        "m": m,
        "b": b,
        "r": r,
        "r2": r * r,
        "n": float(n),
        "std_error": std_error,
        "x_min": min(x),
        "x_max": max(x),
        "y_mean": sum_y / n,
    }


def fit_quality(r2: float) -> dict[str, str]:
    """Human reading of R², thresholds carried over from the Dart original."""
    if r2 > 0.7:
        return {"label": "Fuerte", "tone": "strong"}
    if r2 > 0.4:
        return {"label": "Moderado", "tone": "moderate"}
    return {"label": "Débil", "tone": "weak"}


def regression_report(dataset: Dataset, x_name: str, y_name: str) -> dict[str, Any]:
    """Fit a model and package everything the prediction view needs."""
    xs, ys = dataset.pairs(x_name, y_name)
    model = linear_regression(xs, ys)
    quality = fit_quality(model["r2"])

    direction = "creciente" if model["m"] > 0 else "decreciente" if model["m"] < 0 else "plana"
    strength = quality["label"].lower()

    return {
        "x": x_name,
        "y": y_name,
        "model": model,
        "quality": quality,
        "points": [{"x": a, "y": b} for a, b in zip(xs, ys)],
        "dropped": len(dataset.column(x_name).values) - len(xs),
        "interpretation": (
            f"Cada unidad adicional de «{x_name}» se asocia con un cambio de "
            f"{es(model['m'], signed=True)} en «{y_name}». El modelo explica el "
            f"{pct(model['r2'])} de la variabilidad observada, "
            f"un ajuste {strength} con tendencia {direction}."
        ),
    }


def predict(model: dict[str, float], x_value: float) -> dict[str, Any]:
    """Evaluate y = mx + b and flag extrapolation beyond the observed range."""
    y = model["m"] * x_value + model["b"]
    x_min, x_max = model["x_min"], model["x_max"]
    span = x_max - x_min

    if x_value < x_min or x_value > x_max:
        distance = (x_min - x_value) if x_value < x_min else (x_value - x_max)
        ratio = (distance / span) if span else float("inf")
        warning = (
            f"El valor {_short(x_value)} queda fuera del rango observado "
            f"[{_short(x_min)}, {_short(x_max)}]"
            + (f", un {es(ratio * 100, 0)}% más allá del extremo. " if span else ". ")
            + "La predicción es una extrapolación y pierde fiabilidad."
        )
    else:
        warning = None

    return {
        "x": x_value,
        "y": y,
        "interval": model["std_error"] * 1.96,  # ~95% band from residual spread
        "extrapolated": warning is not None,
        "warning": warning,
    }


def _short(value: float) -> str:
    """Compact Spanish-formatted number for inline prose and expressions."""
    return es(value)


# -- probability --------------------------------------------------------------


def normal_cdf(z: float) -> float:
    """Standard-normal CDF.

    The Dart original used the Abramowitz & Stegun 7-term approximation
    (~7.5e-8 absolute error). `math.erf` is in the standard library, is
    accurate to machine precision, and is available in Pyodide — so this
    is both simpler and strictly better.
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


P_LESS = "less"
P_GREATER = "greater"
P_BETWEEN = "between"
P_OUTSIDE = "outside"


def probability(
    mu: float,
    sigma: float,
    kind: str,
    a: float | None = None,
    b: float | None = None,
) -> dict[str, Any]:
    """Normal-distribution probability for the four supported queries."""
    if sigma <= 0:
        raise ValueError(
            "La desviación estándar es 0: la variable no tiene dispersión, "
            "por lo que no se puede modelar como una normal."
        )

    def z_of(value: float) -> float:
        return (value - mu) / sigma

    if kind in (P_BETWEEN, P_OUTSIDE):
        if a is None or b is None:
            raise ValueError("Indique ambos límites, 'a' y 'b'.")
        if a > b:
            a, b = b, a
        if a == b:
            raise ValueError("Los límites 'a' y 'b' deben ser distintos.")
        z_a, z_b = z_of(a), z_of(b)
        inner = normal_cdf(z_b) - normal_cdf(z_a)
        value = inner if kind == P_BETWEEN else 1.0 - inner
        z_values = [z_a, z_b]
        bounds = [a, b]
        if kind == P_BETWEEN:
            expression = f"P({_short(a)} < X < {_short(b)})"
            shade = [(a, b)]
        else:
            expression = f"P(X < {_short(a)} ó X > {_short(b)})"
            shade = [(None, a), (b, None)]
    else:
        if a is None:
            raise ValueError("Indique el valor 'a'.")
        z_a = z_of(a)
        below = normal_cdf(z_a)
        value = below if kind == P_LESS else 1.0 - below
        z_values = [z_a]
        bounds = [a]
        if kind == P_LESS:
            expression = f"P(X < {_short(a)})"
            shade = [(None, a)]
        else:
            expression = f"P(X > {_short(a)})"
            shade = [(a, None)]

    value = max(0.0, min(1.0, value))

    return {
        "value": value,
        "percent": value * 100,
        "expression": expression,
        "z_values": z_values,
        "bounds": bounds,
        "shade": shade,
        "mu": mu,
        "sigma": sigma,
        "odds": _odds(value),
    }


def _odds(p: float) -> str | None:
    """'≈ 1 de cada 8 casos' — a plainer reading of the percentage."""
    if p <= 0 or p >= 1:
        return None
    one_in = 1 / p
    if one_in >= 2:
        return f"≈ 1 de cada {es(one_in, 0)} casos"
    return f"≈ {es(p * 100, 0)} de cada 100 casos"


def normal_profile(dataset: Dataset, column_name: str) -> dict[str, Any]:
    """μ, σ and shape diagnostics for the probability view."""
    col = dataset.column(column_name)
    if not col.is_numeric:
        raise ValueError(
            f"'{column_name}' es cualitativa. La distribución normal sólo "
            "aplica a variables cuantitativas."
        )
    data = col.numbers()
    if len(data) < 2:
        raise ValueError(
            f"'{column_name}' necesita al menos 2 valores numéricos."
        )

    mu = mean(data)
    sigma = std_dev(data)
    ordered = sorted(data)
    median = _percentile(ordered, 0.5)

    # Pearson's second skewness coefficient — cheap and readable.
    skew = (3 * (mu - median) / sigma) if sigma else 0.0
    if abs(skew) < 0.3:
        shape = "aproximadamente simétrica"
    elif skew > 0:
        shape = "sesgada a la derecha"
    else:
        shape = "sesgada a la izquierda"

    # Empirical rule check: how well does the data match a real normal?
    within = []
    for k in (1, 2, 3):
        hits = sum(1 for v in data if abs(v - mu) <= k * sigma) if sigma else 0
        within.append({
            "k": k,
            "observed": hits / len(data) if data else 0.0,
            "expected": (0.6827, 0.9545, 0.9973)[k - 1],
        })

    return {
        "column": column_name,
        "mu": mu,
        "sigma": sigma,
        "n": len(data),
        "min": ordered[0],
        "max": ordered[-1],
        "median": median,
        "skew": skew,
        "shape": shape,
        "empirical": within,
        "histogram": histogram(data),
    }
