"""Spanish number formatting.

The interface is Spanish, so numbers use a comma decimal separator and a dot
for thousands. Python's f-strings do the opposite, which would otherwise mix
conventions in the same view (`0.01822` in prose next to `0,01822` in a metric).
Every number the engine bakes into prose or chart labels goes through here.
"""

from __future__ import annotations


def es(value: float, digits: int | None = None, *, signed: bool = False) -> str:
    """Format `value` with Spanish separators.

    `digits` fixes the decimal count; when omitted, up to 4 significant
    decimals are kept and trailing zeros are dropped. `signed` forces a
    leading + on positive values, for coefficients where direction matters.
    """
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return "—"

    if digits is None:
        text = f"{value:.4g}"
        # `%g` may produce exponent form; expand it so we can localise it.
        if "e" in text or "E" in text:
            text = f"{value:.6f}".rstrip("0").rstrip(".")
    else:
        text = f"{value:.{digits}f}"

    negative = text.startswith("-")
    text = text.lstrip("+-")

    if "." in text:
        whole, _, decimals = text.partition(".")
    else:
        whole, decimals = text, ""

    # Group the integer part in threes with a dot.
    grouped = ""
    for index, char in enumerate(reversed(whole)):
        if index and index % 3 == 0:
            grouped = "." + grouped
        grouped = char + grouped

    out = grouped + ("," + decimals if decimals else "")

    if negative:
        return "−" + out  # U+2212 minus, which aligns with digit width
    if signed:
        return "+" + out
    return out


def pct(value: float, digits: int = 1) -> str:
    """A 0–1 ratio rendered as a Spanish percentage."""
    return es(value * 100, digits) + "%"
