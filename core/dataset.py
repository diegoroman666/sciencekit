"""Dataset parsing and automatic type inference.

Port of the original Dart `DataProvider._parseData` / `DataColumnModel`.
Pure standard library so the exact same module runs under CPython (Flask)
and under Pyodide (browser).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

QUANTITATIVE = "quantitative"
QUALITATIVE = "qualitative"

# Values that count as "missing" and are skipped rather than coerced.
_BLANKS = {"", "na", "n/a", "nan", "null", "none", "-", "--"}

# 1.234,56 (es-ES) vs 1,234.56 (en-US) both appear in real spreadsheets.
_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _to_number(value: Any) -> float | None:
    """Best-effort numeric coercion. Returns None when the value is not numeric."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if text.lower() in _BLANKS:
        return None

    # Strip thousands separators / currency / percent decoration.
    cleaned = text.replace(" ", "").replace(" ", "")
    cleaned = cleaned.lstrip("$€£").rstrip("%")

    if "," in cleaned and "." in cleaned:
        # Whichever separator comes last is the decimal point.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # A single comma with 3 trailing digits is ambiguous; treat "1,234" as
        # a thousands group and "1,23" as a decimal comma.
        head, _, tail = cleaned.rpartition(",")
        cleaned = head + ("" if len(tail) == 3 and head else ".") + tail

    if not _NUM_RE.match(cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip().lower() in _BLANKS


class Column:
    """A single typed column of a dataset."""

    def __init__(self, name: str, values: list[Any], kind: str, missing: int = 0):
        self.name = name
        self.values = values
        self.kind = kind
        self.missing = missing

    @property
    def is_numeric(self) -> bool:
        return self.kind == QUANTITATIVE

    def numbers(self) -> list[float]:
        """Numeric values only — safe to call on a qualitative column."""
        return [v for v in self.values if isinstance(v, float)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "count": len(self.values),
            "missing": self.missing,
            "is_numeric": self.is_numeric,
        }


class Dataset:
    """A parsed table: named columns plus row-aligned access."""

    def __init__(self, columns: list[Column], name: str = "dataset", row_count: int = 0):
        self.columns = columns
        self.name = name
        self.row_count = row_count

    # -- lookup ---------------------------------------------------------------

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(f"La columna '{name}' no existe en el dataset.")

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def numeric_names(self) -> list[str]:
        return [c.name for c in self.columns if c.is_numeric]

    def pairs(self, x_name: str, y_name: str) -> tuple[list[float], list[float]]:
        """Row-aligned numeric pairs with incomplete rows dropped.

        Both columns must be quantitative. Rows where either side is missing or
        non-numeric are excluded so x and y stay index-aligned — the original
        Dart version zipped by index and silently mispaired after a gap.
        """
        col_x = self.column(x_name)
        col_y = self.column(y_name)
        if not col_x.is_numeric or not col_y.is_numeric:
            raise ValueError(
                "Ambas variables deben ser cuantitativas (numéricas) "
                "para este análisis."
            )

        xs: list[float] = []
        ys: list[float] = []
        for a, b in zip(col_x.values, col_y.values):
            if isinstance(a, float) and isinstance(b, float):
                xs.append(a)
                ys.append(b)
        return xs, ys

    def head(self, limit: int = 8) -> list[list[Any]]:
        """First `limit` rows as a list of row lists, for the preview table."""
        rows: list[list[Any]] = []
        for i in range(min(limit, self.row_count)):
            rows.append([
                col.values[i] if i < len(col.values) else None
                for col in self.columns
            ])
        return rows

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rows": self.row_count,
            "columns": [c.to_dict() for c in self.columns],
            "preview": self.head(),
        }


def build_dataset(rows: list[list[Any]], name: str = "dataset") -> Dataset:
    """Turn raw rows (first row = header) into a typed Dataset.

    A column is quantitative only when every non-blank cell parses as a number.
    Blanks are recorded as None so all columns stay the same length and rows
    remain aligned across columns.
    """
    rows = [r for r in rows if r and not all(_is_blank(c) for c in r)]
    if not rows:
        raise ValueError("El archivo no contiene datos legibles.")

    header = rows[0]
    body = rows[1:]
    if not body:
        raise ValueError(
            "El archivo sólo contiene la fila de encabezados, sin datos."
        )

    width = max(len(header), max((len(r) for r in body), default=0))
    names = _unique_headers(header, width)

    columns: list[Column] = []
    for i in range(width):
        raw = [row[i] if i < len(row) else None for row in body]
        values: list[Any] = []
        numeric = True
        missing = 0

        for cell in raw:
            if _is_blank(cell):
                values.append(None)
                missing += 1
                continue
            number = _to_number(cell)
            if number is None:
                numeric = False
                values.append(str(cell).strip())
            else:
                values.append(number)

        if not numeric:
            # Re-read as text so a column with one stray label stays coherent.
            values = [
                None if _is_blank(c) else str(c).strip()
                for c in raw
            ]

        kind = QUANTITATIVE if numeric else QUALITATIVE
        columns.append(Column(names[i], values, kind, missing))

    return Dataset(columns, name=name, row_count=len(body))


def _unique_headers(header: list[Any], width: int) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for i in range(width):
        raw = header[i] if i < len(header) else None
        label = "" if raw is None else str(raw).strip()
        if not label:
            label = f"Columna {i + 1}"
        if label in seen:
            seen[label] += 1
            label = f"{label} ({seen[label]})"
        else:
            seen[label] = 1
        names.append(label)
    return names


# -- file readers -------------------------------------------------------------


def read_csv(text: str, name: str = "dataset.csv") -> Dataset:
    """Parse CSV/TSV text, sniffing the delimiter."""
    if text.startswith("﻿"):
        text = text[1:]
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return build_dataset(rows, name=name)


def read_xlsx(data: bytes, name: str = "dataset.xlsx") -> Dataset:
    """Parse the first worksheet of an .xlsx file.

    An .xlsx is a zip of XML parts, so this reads it with `zipfile` +
    `xml.etree` instead of pulling in openpyxl. That keeps the engine
    dependency-free and importable in Pyodide without a wheel download.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError(
            "El archivo no es un .xlsx válido (parece estar dañado o tener "
            "otro formato). Vuelva a guardarlo desde Excel como .xlsx o .csv."
        )

    with archive:
        members = set(archive.namelist())

        shared: list[str] = []
        if "xl/sharedStrings.xml" in members:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{ns}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{ns}t")))

        sheet_path = _first_sheet_path(archive, members, ns, rel_ns)
        rows = _parse_sheet(archive.read(sheet_path), shared, ns)

    return build_dataset(rows, name=name)


def _first_sheet_path(archive, members, ns, rel_ns) -> str:
    """Resolve the first worksheet in workbook order, not zip order."""
    import xml.etree.ElementTree as ET

    if "xl/workbook.xml" in members:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = book.find(f"{ns}sheets/{ns}sheet")
        if sheet is not None:
            rel_id = sheet.get(f"{rel_ns}id")
            rels_name = "xl/_rels/workbook.xml.rels"
            if rel_id and rels_name in members:
                rels = ET.fromstring(archive.read(rels_name))
                for rel in rels:
                    if rel.get("Id") == rel_id:
                        target = rel.get("Target", "")
                        target = target.lstrip("/")
                        if not target.startswith("xl/"):
                            target = "xl/" + target
                        if target in members:
                            return target

    sheets = sorted(m for m in members if m.startswith("xl/worksheets/sheet"))
    if not sheets:
        raise ValueError("El archivo .xlsx no contiene hojas de cálculo.")
    return sheets[0]


def _parse_sheet(xml_bytes: bytes, shared: list[str], ns: str) -> list[list[Any]]:
    """Read a worksheet into dense rows, honouring cell references for gaps."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    rows: list[list[Any]] = []

    for row_el in root.iter(f"{ns}row"):
        cells: list[Any] = []
        for cell in row_el.findall(f"{ns}c"):
            index = _column_index(cell.get("r"))
            if index is None:
                index = len(cells)
            while len(cells) < index:
                cells.append(None)
            cells.append(_cell_value(cell, shared, ns))
        rows.append(cells)

    return rows


def _cell_value(cell, shared: list[str], ns: str) -> Any:
    cell_type = cell.get("t")

    if cell_type == "inlineStr":
        node = cell.find(f"{ns}is")
        return "".join(t.text or "" for t in node.iter(f"{ns}t")) if node is not None else None

    value_el = cell.find(f"{ns}v")
    if value_el is None or value_el.text is None:
        return None
    raw = value_el.text

    if cell_type == "s":  # shared string table index
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    if cell_type in ("str", "e"):
        return raw

    try:
        return float(raw)
    except ValueError:
        return raw


def _column_index(ref: str | None) -> int | None:
    """'C7' -> 2. Returns None when the reference is absent or malformed."""
    if not ref:
        return None
    letters = ""
    for ch in ref:
        if ch.isalpha():
            letters += ch.upper()
        else:
            break
    if not letters:
        return None
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def read_bytes(data: bytes, filename: str) -> Dataset:
    """Dispatch on file extension."""
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return read_xlsx(data, name=filename)
    if lower.endswith(".xls"):
        raise ValueError(
            "El formato .xls (Excel 97-2003) no es compatible. "
            "Guarde el archivo como .xlsx o .csv."
        )
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return read_csv(data.decode(encoding), name=filename)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar el archivo como texto.")
