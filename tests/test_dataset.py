"""Parsing and type inference against the messy files real users upload."""

from __future__ import annotations

import io
import unittest
import zipfile

from core.dataset import QUALITATIVE, QUANTITATIVE, build_dataset, read_bytes, read_csv


class Delimiters(unittest.TestCase):
    def test_comma(self):
        data = read_csv("a,b\n1,2\n3,4\n")
        self.assertEqual(data.names, ["a", "b"])
        self.assertEqual(data.row_count, 2)

    def test_semicolon(self):
        data = read_csv("a;b\n1;2\n3;4\n")
        self.assertEqual(data.names, ["a", "b"])

    def test_tab(self):
        data = read_csv("a\tb\n1\t2\n3\t4\n")
        self.assertEqual(data.names, ["a", "b"])

    def test_pipe(self):
        data = read_csv("a|b\n1|2\n3|4\n")
        self.assertEqual(data.names, ["a", "b"])

    def test_quoted_field_containing_the_delimiter(self):
        data = read_csv('name,v\n"Pérez, Ana",3\n"Ruiz, Bea",4\n')
        self.assertEqual(data.column("name").values[0], "Pérez, Ana")
        self.assertEqual(data.row_count, 2)

    def test_bom_is_stripped_from_the_first_header(self):
        data = read_csv("﻿a,b\n1,2\n3,4\n")
        self.assertEqual(data.names, ["a", "b"])

    def test_crlf_line_endings(self):
        data = read_csv("a,b\r\n1,2\r\n3,4\r\n")
        self.assertEqual(data.row_count, 2)
        self.assertEqual(data.column("b").kind, QUANTITATIVE)


class TypeInference(unittest.TestCase):
    def test_all_numeric_column_is_quantitative(self):
        self.assertEqual(read_csv("x\n1\n2,5\n3\n").column("x").kind, QUANTITATIVE)

    def test_one_stray_label_makes_the_whole_column_qualitative(self):
        col = read_csv("x\n1\n2\ntres\n").column("x")
        self.assertEqual(col.kind, QUALITATIVE)
        # And the numbers are re-read as text, so the column stays coherent.
        self.assertEqual(col.values, ["1", "2", "tres"])

    # Files written with a decimal comma use ';' as the delimiter — that is what
    # Excel produces under a Spanish locale, and the only way the two can coexist.
    def test_spanish_decimal_comma(self):
        self.assertEqual(read_csv("x;y\n1,5;a\n2,25;b\n").column("x").numbers(), [1.5, 2.25])

    def test_thousands_dot_with_decimal_comma(self):
        self.assertEqual(read_csv("x;y\n1.234,56;a\n2;b\n").column("x").numbers()[0], 1234.56)

    def test_thousands_comma_with_decimal_dot(self):
        self.assertEqual(read_csv("x;y\n1,234.56;a\n2;b\n").column("x").numbers()[0], 1234.56)

    def test_a_lone_group_of_three_is_read_as_thousands(self):
        self.assertEqual(read_csv("x;y\n1,234;a\n2;b\n").column("x").numbers()[0], 1234.0)

    def test_a_comma_delimited_file_splits_on_every_comma(self):
        """The ambiguity is resolved in favour of the delimiter, as it must be.

        `1,5` in a comma-separated file is two fields, not one decimal — no
        parser can tell them apart, and reading it as a delimiter is what every
        spreadsheet does.
        """
        data = read_csv("x\n1,5\n2,25\n")
        self.assertEqual(len(data.columns), 2)
        self.assertEqual(data.column("x").numbers(), [1.0, 2.0])

    def test_currency_and_percent_decoration(self):
        self.assertEqual(read_csv("x\n$10\n20%\n").column("x").numbers(), [10.0, 20.0])

    def test_scientific_notation(self):
        self.assertEqual(read_csv("x\n1e3\n2E-2\n").column("x").numbers(), [1000.0, 0.02])

    def test_missing_markers(self):
        col = read_csv("x,y\n1,a\nNA,b\nn/a,c\n-,d\nnull,e\n,f\n").column("x")
        self.assertEqual(col.missing, 5)
        self.assertEqual(col.numbers(), [1.0])
        self.assertEqual(col.kind, QUANTITATIVE)

    def test_booleans_are_labels_not_numbers(self):
        self.assertEqual(read_csv("x\nTRUE\nFALSE\n").column("x").kind, QUALITATIVE)

    def test_negative_and_signed_values(self):
        self.assertEqual(read_csv("x\n-1\n+2\n").column("x").numbers(), [-1.0, 2.0])


class Shape(unittest.TestCase):
    def test_short_rows_are_padded(self):
        data = read_csv("a,b,c\n1,2\n3,4,5\n")
        self.assertEqual(len(data.columns), 3)
        self.assertIsNone(data.column("c").values[0])

    def test_long_rows_widen_the_table(self):
        data = read_csv("a,b\n1,2,3\n4,5,6\n")
        self.assertEqual(len(data.columns), 3)
        self.assertEqual(data.columns[2].name, "Columna 3")

    def test_duplicate_headers_are_disambiguated(self):
        self.assertEqual(read_csv("x,x,x\n1,2,3\n").names, ["x", "x (2)", "x (3)"])

    def test_blank_header_cell_gets_a_positional_name(self):
        self.assertEqual(read_csv("a,,c\n1,2,3\n").names, ["a", "Columna 2", "c"])

    def test_blank_lines_between_rows_are_ignored(self):
        self.assertEqual(read_csv("a,b\n1,2\n\n\n3,4\n").row_count, 2)

    def test_header_only_file_is_rejected_with_a_readable_message(self):
        with self.assertRaises(ValueError) as ctx:
            read_csv("a,b\n")
        self.assertIn("encabezados", str(ctx.exception))

    def test_empty_file_is_rejected(self):
        with self.assertRaises(ValueError):
            read_csv("")

    def test_whitespace_is_trimmed_from_labels(self):
        self.assertEqual(read_csv("x\n  hola  \nadios\n").column("x").values[0], "hola")

    def test_unknown_column_raises_keyerror(self):
        with self.assertRaises(KeyError):
            read_csv("a\n1\n").column("nope")

    def test_preview_is_capped(self):
        text = "x\n" + "".join(f"{i}\n" for i in range(100))
        self.assertEqual(len(read_csv(text).to_dict()["preview"]), 8)


class Pairs(unittest.TestCase):
    def test_rows_stay_aligned_when_a_gap_appears(self):
        # The Dart original zipped by index and silently mispaired after a gap.
        data = read_csv("x,y\n1,10\n2,\n3,30\n")
        xs, ys = data.pairs("x", "y")
        self.assertEqual(xs, [1.0, 3.0])
        self.assertEqual(ys, [10.0, 30.0])

    def test_gap_on_either_side_drops_the_row(self):
        data = read_csv("x,y\n1,10\n,20\n3,30\n")
        self.assertEqual(data.pairs("x", "y")[0], [1.0, 3.0])

    def test_qualitative_columns_are_rejected(self):
        data = read_csv("x,y\n1,a\n2,b\n")
        with self.assertRaises(ValueError):
            data.pairs("x", "y")


class Bytes(unittest.TestCase):
    def test_utf8_with_bom_round_trips(self):
        # This is exactly what the app's CSV download produces.
        raw = ("﻿" + "Región,Año\nÑuñoa,2026\nAçaí,2027\n").encode("utf-8")
        data = read_bytes(raw, "x.csv")
        self.assertEqual(data.names, ["Región", "Año"])
        self.assertEqual(data.column("Región").values, ["Ñuñoa", "Açaí"])

    def test_latin1_fallback(self):
        data = read_bytes("a\nÑ\n".encode("latin-1"), "x.csv")
        self.assertEqual(data.row_count, 1)

    def test_xls_is_rejected_with_guidance(self):
        with self.assertRaises(ValueError) as ctx:
            read_bytes(b"\xd0\xcf\x11\xe0", "old.xls")
        self.assertIn(".xlsx", str(ctx.exception))

    def test_corrupt_xlsx_is_rejected_with_guidance(self):
        with self.assertRaises(ValueError) as ctx:
            read_bytes(b"not a zip", "broken.xlsx")
        self.assertIn("xlsx", str(ctx.exception).lower())


def make_xlsx(rows: list[list[object]]) -> bytes:
    """A minimal single-sheet .xlsx, built without openpyxl."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    def letter(index: int) -> str:
        name = ""
        index += 1
        while index:
            index, rest = divmod(index - 1, 26)
            name = chr(65 + rest) + name
        return name

    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{letter(c)}{r}"
            if value is None:
                continue
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')

    sheet = f'<worksheet xmlns="{ns}"><sheetData>{"".join(body)}</sheetData></worksheet>'
    workbook = (
        f'<workbook xmlns="{ns}" xmlns:r="{rel_ns}">'
        f'<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        f'<Relationships xmlns="{rel_ns}/package/2006/relationships">'
        f'<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
        f'Type="{rel_ns}/officeDocument/2006/relationships/worksheet"/></Relationships>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class Xlsx(unittest.TestCase):
    def test_reads_a_simple_sheet(self):
        data = read_bytes(make_xlsx([["a", "b"], [1, "uno"], [2, "dos"]]), "t.xlsx")
        self.assertEqual(data.names, ["a", "b"])
        self.assertEqual(data.row_count, 2)
        self.assertEqual(data.column("a").kind, QUANTITATIVE)
        self.assertEqual(data.column("b").values, ["uno", "dos"])

    def test_a_gap_keeps_later_cells_in_their_own_column(self):
        # Excel omits empty cells entirely; the reader honours the cell refs.
        data = read_bytes(make_xlsx([["a", "b", "c"], [1, None, 3]]), "t.xlsx")
        self.assertIsNone(data.column("b").values[0])
        self.assertEqual(data.column("c").values[0], 3.0)

    def test_xlsm_is_accepted(self):
        data = read_bytes(make_xlsx([["a"], [1], [2]]), "macro.xlsm")
        self.assertEqual(data.row_count, 2)


class BuildDataset(unittest.TestCase):
    def test_rejects_a_table_with_no_rows(self):
        with self.assertRaises(ValueError):
            build_dataset([])

    def test_column_dict_shape_is_what_the_ui_expects(self):
        info = read_csv("x,y\n1,a\n2,b\n").to_dict()
        self.assertEqual(info["rows"], 2)
        self.assertEqual(
            set(info["columns"][0]),
            {"name", "kind", "count", "missing", "is_numeric"},
        )
        self.assertTrue(info["columns"][0]["is_numeric"])
        self.assertFalse(info["columns"][1]["is_numeric"])


if __name__ == "__main__":
    unittest.main()
