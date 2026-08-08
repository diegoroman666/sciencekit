"""SVG chart rendering.

Charts are generated as SVG markup by Python — no JS charting library — so the
visual language is fully controlled here and identical on the server and in the
browser. Colours reference CSS custom properties (`var(--…)`) instead of literal
hex values, so a chart re-themes with the page without being re-rendered.
"""

from __future__ import annotations

import math
from typing import Any

from .fmt import es

# Viewbox geometry. Charts scale responsively via `width=100%` + preserveAspectRatio.
W = 720
H = 420
PAD = {"top": 24, "right": 24, "bottom": 48, "left": 64}

PLOT_W = W - PAD["left"] - PAD["right"]
PLOT_H = H - PAD["top"] - PAD["bottom"]


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt(value: float) -> str:
    """Compact axis label in Spanish notation: 1,2k · 3,4M · 0,05 · −12."""
    if value == 0:
        return "0"
    magnitude = abs(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if magnitude >= limit:
            return es(value / limit, 1).rstrip("0").rstrip(",") + suffix
    if magnitude < 0.01:
        return f"{value:.1e}".replace(".", ",")
    if magnitude < 1:
        return es(value, 3).rstrip("0").rstrip(",")
    if magnitude < 100:
        return es(value)
    return es(value, 0)


def _nice_ticks(lo: float, hi: float, target: int = 6) -> list[float]:
    """Human-friendly tick values (1/2/5 x 10^n) spanning [lo, hi]."""
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        return [lo]
    raw = (hi - lo) / max(1, target)
    exponent = math.floor(math.log10(raw))
    base = 10 ** exponent
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * base
        if step >= raw:
            break
    start = math.ceil(lo / step) * step
    ticks: list[float] = []
    value = start
    while value <= hi + step * 1e-9 and len(ticks) < 40:
        # Snap values that are float-noise away from a round number.
        ticks.append(0.0 if abs(value) < step * 1e-9 else value)
        value += step
    return ticks


class _Scale:
    """Maps a data range onto a pixel range, with padding and a safe zero-span."""

    def __init__(self, lo: float, hi: float, px_lo: float, px_hi: float, pad: float = 0.06):
        if hi == lo:
            delta = abs(hi) * 0.1 or 1.0
            lo, hi = lo - delta, hi + delta
        else:
            span = (hi - lo) * pad
            lo, hi = lo - span, hi + span
        self.lo, self.hi = lo, hi
        self.px_lo, self.px_hi = px_lo, px_hi

    def __call__(self, value: float) -> float:
        ratio = (value - self.lo) / (self.hi - self.lo)
        return self.px_lo + ratio * (self.px_hi - self.px_lo)


def _open(label: str) -> list[str]:
    return [
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'class="sk-chart" role="img" aria-label="{_esc(label)}" '
        'xmlns="http://www.w3.org/2000/svg">'
    ]


def _grid_and_axes(
    parts: list[str],
    x: _Scale,
    y: _Scale,
    x_label: str,
    y_label: str,
    x_ticks: list[float] | None = None,
    y_ticks: list[float] | None = None,
) -> None:
    """Horizontal grid lines, tick labels and axis titles."""
    x_ticks = _nice_ticks(x.lo, x.hi) if x_ticks is None else x_ticks
    y_ticks = _nice_ticks(y.lo, y.hi) if y_ticks is None else y_ticks

    parts.append('<g class="sk-grid">')
    for tick in y_ticks:
        py = y(tick)
        parts.append(
            f'<line x1="{PAD["left"]:.1f}" y1="{py:.1f}" '
            f'x2="{PAD["left"] + PLOT_W:.1f}" y2="{py:.1f}" />'
        )
    parts.append("</g>")

    parts.append('<g class="sk-tick sk-tick-y">')
    for tick in y_ticks:
        py = y(tick)
        parts.append(
            f'<text x="{PAD["left"] - 12:.1f}" y="{py + 4:.1f}" '
            f'text-anchor="end">{_esc(_fmt(tick))}</text>'
        )
    parts.append("</g>")

    parts.append('<g class="sk-tick sk-tick-x">')
    for tick in x_ticks:
        px = x(tick)
        parts.append(
            f'<text x="{px:.1f}" y="{PAD["top"] + PLOT_H + 22:.1f}" '
            f'text-anchor="middle">{_esc(_fmt(tick))}</text>'
        )
    parts.append("</g>")

    # Baseline + left rule frame the plot without a full box.
    parts.append(
        f'<line class="sk-axis" x1="{PAD["left"]:.1f}" y1="{PAD["top"] + PLOT_H:.1f}" '
        f'x2="{PAD["left"] + PLOT_W:.1f}" y2="{PAD["top"] + PLOT_H:.1f}" />'
    )

    parts.append(
        f'<text class="sk-axis-label" x="{PAD["left"] + PLOT_W / 2:.1f}" '
        f'y="{H - 8}" text-anchor="middle">{_esc(x_label)}</text>'
    )
    parts.append(
        f'<text class="sk-axis-label" x="14" y="{PAD["top"] + PLOT_H / 2:.1f}" '
        f'text-anchor="middle" transform="rotate(-90 14 '
        f'{PAD["top"] + PLOT_H / 2:.1f})">{_esc(y_label)}</text>'
    )


def _empty(message: str) -> str:
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'class="sk-chart" role="img" aria-label="{_esc(message)}" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<text class="sk-empty" x="{W / 2}" y="{H / 2}" text-anchor="middle">'
        f"{_esc(message)}</text></svg>"
    )


# -- scatter ------------------------------------------------------------------


def scatter(
    points: list[dict[str, float]],
    x_label: str,
    y_label: str,
    line: dict[str, float] | None = None,
    highlight: dict[str, float] | None = None,
) -> str:
    """Scatter plot, optionally with a fitted regression line and a marked point."""
    if not points:
        return _empty("Sin datos para graficar")

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]

    lo_x, hi_x = min(xs), max(xs)
    lo_y, hi_y = min(ys), max(ys)
    if highlight:
        lo_x, hi_x = min(lo_x, highlight["x"]), max(hi_x, highlight["x"])
        lo_y, hi_y = min(lo_y, highlight["y"]), max(hi_y, highlight["y"])

    x = _Scale(lo_x, hi_x, PAD["left"], PAD["left"] + PLOT_W)
    y = _Scale(lo_y, hi_y, PAD["top"] + PLOT_H, PAD["top"])

    parts = _open(f"Dispersión de {y_label} frente a {x_label}")
    _grid_and_axes(parts, x, y, x_label, y_label)

    # Radius shrinks as the cloud gets denser so overplotting stays readable.
    radius = 4.5 if len(points) <= 60 else 3.5 if len(points) <= 250 else 2.5
    opacity = 0.9 if len(points) <= 60 else 0.7 if len(points) <= 250 else 0.5

    parts.append(f'<g class="sk-dots" opacity="{opacity}">')
    for p in points:
        parts.append(f'<circle cx="{x(p["x"]):.1f}" cy="{y(p["y"]):.1f}" r="{radius}" />')
    parts.append("</g>")

    if line:
        m, b = line["m"], line["b"]
        # Clip the fitted line to the visible x-window.
        x0, x1 = x.lo, x.hi
        parts.append(
            f'<line class="sk-fit" x1="{x(x0):.1f}" y1="{y(m * x0 + b):.1f}" '
            f'x2="{x(x1):.1f}" y2="{y(m * x1 + b):.1f}" />'
        )

    if highlight:
        hx, hy = x(highlight["x"]), y(highlight["y"])
        parts.append(
            f'<g class="sk-marker">'
            f'<line x1="{hx:.1f}" y1="{PAD["top"] + PLOT_H:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" />'
            f'<line x1="{PAD["left"]:.1f}" y1="{hy:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" />'
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="7" />'
            f"</g>"
        )

    parts.append("</svg>")
    return "".join(parts)


# -- bars ---------------------------------------------------------------------


def bars(
    labels: list[Any],
    values: list[float],
    x_label: str = "",
    y_label: str = "Frecuencia",
) -> str:
    """Vertical bar chart for categorical frequencies."""
    if not values:
        return _empty("Sin datos para graficar")

    shown = min(len(values), 24)
    labels, values = labels[:shown], values[:shown]

    y = _Scale(0, max(values), PAD["top"] + PLOT_H, PAD["top"], pad=0.0)
    y.lo = 0  # bars must sit on a true zero baseline
    y.hi = max(values) * 1.08 or 1

    parts = _open(f"Frecuencia por {x_label}" if x_label else "Distribución de frecuencias")

    y_ticks = _nice_ticks(0, y.hi, 5)
    parts.append('<g class="sk-grid">')
    for tick in y_ticks:
        py = y(tick)
        parts.append(
            f'<line x1="{PAD["left"]:.1f}" y1="{py:.1f}" '
            f'x2="{PAD["left"] + PLOT_W:.1f}" y2="{py:.1f}" />'
        )
    parts.append("</g>")
    parts.append('<g class="sk-tick sk-tick-y">')
    for tick in y_ticks:
        parts.append(
            f'<text x="{PAD["left"] - 12:.1f}" y="{y(tick) + 4:.1f}" '
            f'text-anchor="end">{_esc(_fmt(tick))}</text>'
        )
    parts.append("</g>")

    slot = PLOT_W / shown
    bar_w = min(slot * 0.62, 46)
    baseline = PAD["top"] + PLOT_H

    parts.append('<g class="sk-bars">')
    for i, value in enumerate(values):
        cx = PAD["left"] + slot * (i + 0.5)
        top = y(value)
        height = max(1.0, baseline - top)
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{top:.1f}" '
            f'width="{bar_w:.1f}" height="{height:.1f}" rx="2" />'
        )
    parts.append("</g>")

    # Value on top of each bar, only when bars are wide enough to fit it.
    if shown <= 14:
        parts.append('<g class="sk-bar-value">')
        for i, value in enumerate(values):
            cx = PAD["left"] + slot * (i + 0.5)
            parts.append(
                f'<text x="{cx:.1f}" y="{y(value) - 8:.1f}" '
                f'text-anchor="middle">{_esc(_fmt(value))}</text>'
            )
        parts.append("</g>")

    parts.append(
        f'<line class="sk-axis" x1="{PAD["left"]:.1f}" y1="{baseline:.1f}" '
        f'x2="{PAD["left"] + PLOT_W:.1f}" y2="{baseline:.1f}" />'
    )

    # Rotate labels when horizontal text would collide.
    rotate = shown > 8 or any(len(str(l)) > 6 for l in labels)
    parts.append('<g class="sk-tick sk-tick-x">')
    for i, label in enumerate(labels):
        cx = PAD["left"] + slot * (i + 0.5)
        text = str(label)
        if len(text) > 14:
            text = text[:13] + "…"
        if rotate:
            parts.append(
                f'<text x="{cx:.1f}" y="{baseline + 16:.1f}" text-anchor="end" '
                f'transform="rotate(-38 {cx:.1f} {baseline + 16:.1f})">{_esc(text)}</text>'
            )
        else:
            parts.append(
                f'<text x="{cx:.1f}" y="{baseline + 22:.1f}" '
                f'text-anchor="middle">{_esc(text)}</text>'
            )
    parts.append("</g>")

    if x_label:
        parts.append(
            f'<text class="sk-axis-label" x="{PAD["left"] + PLOT_W / 2:.1f}" '
            f'y="{H - 4}" text-anchor="middle">{_esc(x_label)}</text>'
        )
    parts.append(
        f'<text class="sk-axis-label" x="14" y="{PAD["top"] + PLOT_H / 2:.1f}" '
        f'text-anchor="middle" transform="rotate(-90 14 '
        f'{PAD["top"] + PLOT_H / 2:.1f})">{_esc(y_label)}</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def histogram_chart(hist: dict[str, Any], x_label: str) -> str:
    """Contiguous-bin histogram — bars touch, unlike the categorical chart."""
    bins = hist.get("bins") or []
    if not bins:
        return _empty("Sin datos para graficar")

    lo = bins[0]["start"]
    hi = bins[-1]["end"]
    x = _Scale(lo, hi, PAD["left"], PAD["left"] + PLOT_W, pad=0.02)
    top_count = hist.get("max_count") or 1
    y = _Scale(0, top_count, PAD["top"] + PLOT_H, PAD["top"], pad=0.0)
    y.lo, y.hi = 0, top_count * 1.08

    parts = _open(f"Histograma de {x_label}")
    _grid_and_axes(
        parts, x, y, x_label, "Frecuencia",
        y_ticks=_nice_ticks(0, y.hi, 5),
    )

    baseline = PAD["top"] + PLOT_H
    parts.append('<g class="sk-bars">')
    for b in bins:
        x0, x1 = x(b["start"]), x(b["end"])
        top = y(b["count"])
        parts.append(
            f'<rect x="{x0 + 0.75:.1f}" y="{top:.1f}" '
            f'width="{max(1.0, x1 - x0 - 1.5):.1f}" '
            f'height="{max(0.0, baseline - top):.1f}" rx="1.5" />'
        )
    parts.append("</g></svg>")
    return "".join(parts)


# -- normal distribution ------------------------------------------------------


def normal_curve(
    mu: float,
    sigma: float,
    shade: list[tuple[float | None, float | None]] | None = None,
    label: str = "",
) -> str:
    """Bell curve with the queried region filled, for the probability module."""
    if sigma <= 0:
        return _empty("σ = 0: la variable no tiene dispersión")

    lo, hi = mu - 4 * sigma, mu + 4 * sigma
    x = _Scale(lo, hi, PAD["left"], PAD["left"] + PLOT_W, pad=0.0)
    peak = 1.0 / (sigma * math.sqrt(2 * math.pi))
    y = _Scale(0, peak, PAD["top"] + PLOT_H, PAD["top"], pad=0.0)
    y.lo, y.hi = 0, peak * 1.14

    def density(value: float) -> float:
        z = (value - mu) / sigma
        return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2 * math.pi))

    steps = 240
    curve = [lo + (hi - lo) * i / steps for i in range(steps + 1)]
    baseline = PAD["top"] + PLOT_H

    parts = _open(label or "Distribución normal")

    # σ gridlines at ±1σ, ±2σ, ±3σ instead of arbitrary numeric ticks.
    parts.append('<g class="sk-grid">')
    for k in (-3, -2, -1, 0, 1, 2, 3):
        px = x(mu + k * sigma)
        parts.append(f'<line x1="{px:.1f}" y1="{PAD["top"]:.1f}" x2="{px:.1f}" y2="{baseline:.1f}" />')
    parts.append("</g>")

    # Shaded probability region(s).
    for start, end in (shade or []):
        s = lo if start is None else max(lo, start)
        e = hi if end is None else min(hi, end)
        if e <= s:
            continue
        region = [s + (e - s) * i / 120 for i in range(121)]
        path = [f"M {x(s):.1f} {baseline:.1f}"]
        path += [f"L {x(v):.1f} {y(density(v)):.1f}" for v in region]
        path.append(f"L {x(e):.1f} {baseline:.1f} Z")
        parts.append(f'<path class="sk-area" d="{" ".join(path)}" />')

    # The curve itself.
    curve_path = " ".join(
        ("M" if i == 0 else "L") + f" {x(v):.1f} {y(density(v)):.1f}"
        for i, v in enumerate(curve)
    )
    parts.append(f'<path class="sk-curve" d="{curve_path}" />')

    # Boundary markers at each queried limit.
    for start, end in (shade or []):
        for bound in (start, end):
            if bound is None or not (lo <= bound <= hi):
                continue
            px = x(bound)
            parts.append(
                f'<line class="sk-bound" x1="{px:.1f}" y1="{PAD["top"] + 4:.1f}" '
                f'x2="{px:.1f}" y2="{baseline:.1f}" />'
                f'<text class="sk-bound-label" x="{px:.1f}" y="{PAD["top"] - 6:.1f}" '
                f'text-anchor="middle">{_esc(_fmt(bound))}</text>'
            )

    parts.append(
        f'<line class="sk-axis" x1="{PAD["left"]:.1f}" y1="{baseline:.1f}" '
        f'x2="{PAD["left"] + PLOT_W:.1f}" y2="{baseline:.1f}" />'
    )

    parts.append('<g class="sk-tick sk-tick-x">')
    for k in (-3, -2, -1, 0, 1, 2, 3):
        px = x(mu + k * sigma)
        sigma_label = "μ" if k == 0 else f"μ{k:+d}σ".replace("1σ", "σ")
        parts.append(
            f'<text x="{px:.1f}" y="{baseline + 20:.1f}" text-anchor="middle">'
            f"{_esc(sigma_label)}</text>"
        )
        parts.append(
            f'<text class="sk-tick-sub" x="{px:.1f}" y="{baseline + 36:.1f}" '
            f'text-anchor="middle">{_esc(_fmt(mu + k * sigma))}</text>'
        )
    parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)
