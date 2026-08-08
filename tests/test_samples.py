"""Integrity of the five bundled datasets.

The samples are the first thing a visitor touches, so they are held to the same
standard as the code: the catalogue must describe the real data, the shipped
CSV files must match what is embedded, the generator must be reproducible, and
every module must run on every column of every table without an error.
"""

from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path

from core import analysis, sample
from core.api import Session, dispatch
from core.dataset import read_bytes, read_csv

ROOT = Path(__file__).resolve().parent.parent


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "make_sample", ROOT / "scripts" / "make_sample.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Catalogue(unittest.TestCase):
    def test_five_datasets(self):
        self.assertEqual(len(sample.SAMPLES), 5)

    def test_keys_names_and_titles_are_unique(self):
        for field in ("key", "name", "title"):
            values = [item[field] for item in sample.SAMPLES]
            self.assertEqual(len(set(values)), len(values), field)

    def test_areas_are_distinct(self):
        areas = [item["area"] for item in sample.SAMPLES]
        self.assertEqual(len(set(areas)), len(areas))

    def test_default_and_aliases_point_at_the_first_dataset(self):
        first = sample.SAMPLES[0]
        self.assertEqual(sample.DEFAULT_SAMPLE, first["key"])
        self.assertEqual(sample.SAMPLE_NAME, first["name"])
        self.assertEqual(sample.SAMPLE_CSV, first["csv"])

    def test_get_falls_back_to_the_default(self):
        self.assertEqual(sample.get(None)["key"], sample.DEFAULT_SAMPLE)
        self.assertEqual(sample.get("")["key"], sample.DEFAULT_SAMPLE)

    def test_get_returns_none_for_an_unknown_key(self):
        self.assertIsNone(sample.get("no-existe"))

    def test_catalog_hides_the_payloads(self):
        self.assertTrue(all("csv" not in item for item in sample.catalog()))

    def test_descriptions_are_written_for_a_person(self):
        for item in sample.SAMPLES:
            self.assertGreater(len(item["description"]), 40, item["key"])
            self.assertTrue(item["description"].endswith("."), item["key"])


class MetadataMatchesTheData(unittest.TestCase):
    """Every number on a gallery card is checked against the parsed table."""

    def test_counts_are_accurate(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            numeric = [c for c in data.columns if c.is_numeric]
            with self.subTest(item["key"]):
                self.assertEqual(data.row_count, item["rows"])
                self.assertEqual(len(data.columns), item["columns"])
                self.assertEqual(len(numeric), item["numeric"])
                self.assertEqual(len(data.columns) - len(numeric), item["categorical"])

    def test_suggested_pair_exists_and_is_quantitative(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            with self.subTest(item["key"]):
                self.assertTrue(data.column(item["driver"]).is_numeric)
                self.assertTrue(data.column(item["target"]).is_numeric)
                self.assertNotEqual(item["driver"], item["target"])

    def test_suggested_pair_actually_fits(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            report = analysis.regression_report(data, item["driver"], item["target"])
            with self.subTest(item["key"]):
                self.assertGreater(report["model"]["r2"], 0.4, item["key"])

    def test_no_missing_cells(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            with self.subTest(item["key"]):
                self.assertEqual(sum(c.missing for c in data.columns), 0)

    def test_each_table_has_enough_of_both_kinds_to_exercise_the_app(self):
        for item in sample.SAMPLES:
            with self.subTest(item["key"]):
                self.assertGreaterEqual(item["numeric"], 4)
                self.assertGreaterEqual(item["categorical"], 2)

    def test_categorical_columns_have_a_workable_number_of_levels(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            for col in data.columns:
                if col.is_numeric:
                    continue
                levels = len(set(col.values))
                # An identifier column is one level per row; anything else must
                # stay readable as a bar chart.
                with self.subTest(f"{item['key']}.{col.name}"):
                    self.assertTrue(levels <= 12 or levels == data.row_count)


class NoGeneratorArtefacts(unittest.TestCase):
    """Guards against the clamping bug: a stack of rows on one boundary value."""

    def test_no_column_piles_up_on_its_minimum_or_maximum(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            for col in data.columns:
                if not col.is_numeric:
                    continue
                values = col.numbers()
                value, count = Counter(values).most_common(1)[0]
                with self.subTest(f"{item['key']}.{col.name}"):
                    if value in (min(values), max(values)):
                        self.assertLessEqual(
                            count, 2,
                            f"{count} filas comparten el extremo {value}: "
                            "parece un recorte en el generador",
                        )

    def test_target_columns_are_physically_plausible(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            values = data.column(item["target"]).numbers()
            with self.subTest(item["key"]):
                self.assertGreater(min(values), 0)

    def test_spread_is_wide_enough_for_a_histogram(self):
        for item in sample.SAMPLES:
            data = read_csv(item["csv"], name=item["name"])
            for col in data.columns:
                if not col.is_numeric:
                    continue
                values = col.numbers()
                with self.subTest(f"{item['key']}.{col.name}"):
                    self.assertGreater(len(set(values)), 10)
                    self.assertGreater(analysis.std_dev(values), 0)


class ShippedFilesMatch(unittest.TestCase):
    def test_sample_data_files_are_identical_to_the_embedded_copies(self):
        for item in sample.SAMPLES:
            path = ROOT / "sample_data" / item["name"]
            with self.subTest(item["key"]):
                self.assertTrue(path.exists(), path)
                self.assertEqual(path.read_text(encoding="utf-8"), item["csv"])

    def test_no_orphan_files_in_sample_data(self):
        shipped = {p.name for p in (ROOT / "sample_data").glob("*.csv")}
        self.assertEqual(shipped, {item["name"] for item in sample.SAMPLES})

    def test_generator_is_deterministic(self):
        module = load_generator()
        for spec in module.DATASETS:
            first = module.to_csv(spec["build"]())
            second = module.to_csv(spec["build"]())
            with self.subTest(spec["key"]):
                self.assertEqual(first, second)

    def test_generator_reproduces_the_committed_data(self):
        module = load_generator()
        for spec in module.DATASETS:
            embedded = sample.SAMPLE_INDEX[spec["key"]]["csv"]
            with self.subTest(spec["key"]):
                self.assertEqual(module.to_csv(spec["build"]()), embedded)

    def test_generator_audit_rejects_a_clamped_column(self):
        module = load_generator()
        spec = {"name": "falso.csv", "driver": "x", "target": "y"}
        rows = [["x", "y"], *[[1.0, 5.0] for _ in range(4)], [2.0, 6.0]]
        with self.assertRaises(SystemExit):
            module.audit(spec, rows)

    def test_bounded_never_returns_a_value_outside_its_range(self):
        import random

        module = load_generator()
        rng = random.Random(7)
        for _ in range(2000):
            value = module.bounded(rng, 5.0, 3.0, lo=1.0, hi=9.0)
            self.assertGreaterEqual(value, 1.0)
            self.assertLessEqual(value, 9.0)


class DownloadRoundTrip(unittest.TestCase):
    """What the browser writes to disk must come back in unchanged."""

    def test_downloaded_bytes_reparse_identically(self):
        for item in sample.SAMPLES:
            original = read_csv(item["csv"], name=item["name"])
            # The download prepends a BOM so Excel reads UTF-8 correctly.
            downloaded = ("﻿" + item["csv"]).encode("utf-8")
            reloaded = read_bytes(downloaded, item["name"])
            with self.subTest(item["key"]):
                self.assertEqual(reloaded.names, original.names)
                self.assertEqual(reloaded.row_count, original.row_count)
                self.assertEqual(
                    [c.kind for c in reloaded.columns],
                    [c.kind for c in original.columns],
                )

    def test_a_downloaded_file_can_be_re_uploaded_through_the_api(self):
        import base64

        session = Session()
        csv_text = dispatch(session, "sample_csv", {"sample": "educacion"})["csv"]
        payload = base64.b64encode(("﻿" + csv_text).encode("utf-8")).decode("ascii")
        result = dispatch(session, "load", {
            "filename": "rendimiento_academico.csv",
            "content_b64": payload,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["dataset"]["rows"], 160)


class EveryModuleOnEveryColumn(unittest.TestCase):
    """The smoke matrix: no column of any sample may break any module."""

    def test_describe_and_frequency(self):
        session = Session()
        for item in sample.SAMPLES:
            dispatch(session, "demo", {"sample": item["key"]})
            for name in session.dataset.names:
                with self.subTest(f"{item['key']}.{name}"):
                    self.assertTrue(dispatch(session, "describe", {"column": name})["ok"])
                    self.assertTrue(dispatch(session, "frequency", {"column": name})["ok"])

    def test_charts(self):
        session = Session()
        for item in sample.SAMPLES:
            dispatch(session, "demo", {"sample": item["key"]})
            names = session.dataset.names
            numeric = session.dataset.numeric_names
            for name in names:
                with self.subTest(f"bars {item['key']}.{name}"):
                    self.assertTrue(dispatch(session, "chart", {"type": "bars", "x": name})["ok"])
            for name in numeric:
                with self.subTest(f"hist {item['key']}.{name}"):
                    self.assertTrue(
                        dispatch(session, "chart", {"type": "histogram", "x": name})["ok"]
                    )
            for x in numeric:
                for y in numeric:
                    result = dispatch(
                        session, "chart", {"type": "scatter", "x": x, "y": y, "fit": True}
                    )
                    with self.subTest(f"scatter {item['key']}.{x}~{y}"):
                        self.assertTrue(result["ok"])

    def test_regression_over_every_numeric_pair(self):
        session = Session()
        for item in sample.SAMPLES:
            dispatch(session, "demo", {"sample": item["key"]})
            numeric = session.dataset.numeric_names
            for x in numeric:
                for y in numeric:
                    if x == y:
                        continue
                    result = dispatch(session, "regression", {"x": x, "y": y})
                    with self.subTest(f"{item['key']} {x}->{y}"):
                        self.assertTrue(result["ok"])
                        prediction = dispatch(session, "predict", {"value": 1})
                        self.assertTrue(prediction["ok"])

    def test_normal_profile_and_probability(self):
        session = Session()
        for item in sample.SAMPLES:
            dispatch(session, "demo", {"sample": item["key"]})
            for name in session.dataset.numeric_names:
                result = dispatch(session, "normal", {"column": name})
                with self.subTest(f"{item['key']}.{name}"):
                    self.assertTrue(result["ok"])
                    profile = result["profile"]
                    probability = dispatch(session, "probability", {
                        "mu": profile["mu"],
                        "sigma": profile["sigma"],
                        "kind": "less",
                        "a": profile["median"],
                    })
                    self.assertTrue(probability["ok"])
                    # A symmetric-ish variable puts about half the mass below
                    # its own median; anything outside this band is a red flag.
                    self.assertGreater(probability["result"]["value"], 0.25)
                    self.assertLess(probability["result"]["value"], 0.75)


if __name__ == "__main__":
    unittest.main()
