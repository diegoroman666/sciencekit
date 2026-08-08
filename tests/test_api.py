"""Black-box tests of the dispatch surface.

`dispatch()` is the only entry point both transports use, so everything the app
can do — and every way a user can get it wrong — is exercised from here. The
contract under test: a call either returns {ok: True, ...} or {ok: False,
error: <message a person can act on>}, and never raises or leaks a traceback.
"""

from __future__ import annotations

import base64
import json
import math
import unittest

from core.api import ACTIONS, MAX_UPLOAD_BYTES, Session, dispatch, dispatch_json

CSV = "x,y,g\n1,10,a\n2,12,b\n3,15,a\n4,19,b\n5,22,a\n6,28,b\n"


def loaded() -> Session:
    session = Session()
    assert dispatch(session, "load", {"filename": "t.csv", "text": CSV})["ok"]
    return session


class Contract(unittest.TestCase):
    def test_unknown_action_is_reported_not_raised(self):
        result = dispatch(Session(), "no_existe", {})
        self.assertFalse(result["ok"])
        self.assertIn("Acción desconocida", result["error"])

    def test_every_action_without_a_dataset_answers_instead_of_crashing(self):
        session = Session()
        for action in sorted(ACTIONS):
            result = dispatch(session, action, {})
            self.assertIn("ok", result, action)
            if not result["ok"]:
                self.assertTrue(str(result["error"]).strip(), action)

    def test_missing_payload_is_tolerated(self):
        self.assertIn("ok", dispatch(Session(), "describe", None))

    def test_results_are_json_serialisable_without_nan(self):
        session = loaded()
        for action, payload in [
            ("describe", {"column": "x"}),
            ("frequency", {"column": "g"}),
            ("chart", {"type": "scatter", "x": "x", "y": "y", "fit": True}),
            ("regression", {"x": "x", "y": "y"}),
            ("normal", {"column": "x"}),
        ]:
            text = json.dumps(dispatch(session, action, payload), allow_nan=False)
            self.assertNotIn("NaN", text, action)
            self.assertNotIn("Infinity", text, action)


class Loading(unittest.TestCase):
    def test_load_from_text(self):
        result = dispatch(Session(), "load", {"filename": "t.csv", "text": CSV})
        self.assertTrue(result["ok"])
        self.assertEqual(result["dataset"]["rows"], 6)
        self.assertEqual(len(result["dataset"]["columns"]), 3)

    def test_load_from_base64(self):
        payload = {
            "filename": "t.csv",
            "content_b64": base64.b64encode(CSV.encode("utf-8")).decode("ascii"),
        }
        self.assertTrue(dispatch(Session(), "load", payload)["ok"])

    def test_load_with_no_content(self):
        result = dispatch(Session(), "load", {"filename": "t.csv"})
        self.assertFalse(result["ok"])
        self.assertIn("archivo", result["error"])

    def test_invalid_base64(self):
        result = dispatch(Session(), "load", {"content_b64": "no-es-base64!!"})
        self.assertFalse(result["ok"])
        self.assertIn("decodificar", result["error"])

    def test_oversized_upload_is_refused_with_the_limit(self):
        payload = {
            "filename": "big.csv",
            "content_b64": base64.b64encode(b"a" * (MAX_UPLOAD_BYTES + 1)).decode("ascii"),
        }
        result = dispatch(Session(), "load", payload)
        self.assertFalse(result["ok"])
        self.assertIn("MB", result["error"])

    def test_oversized_text_is_refused(self):
        result = dispatch(Session(), "load", {"text": "a" * (MAX_UPLOAD_BYTES + 1)})
        self.assertFalse(result["ok"])

    def test_unreadable_file_gets_a_readable_message(self):
        result = dispatch(Session(), "load", {"filename": "t.csv", "text": ""})
        self.assertFalse(result["ok"])
        self.assertIn("datos", result["error"])

    def test_loading_a_new_dataset_clears_the_previous_model(self):
        session = loaded()
        self.assertTrue(dispatch(session, "regression", {"x": "x", "y": "y"})["ok"])
        dispatch(session, "load", {"filename": "t.csv", "text": CSV})
        self.assertFalse(dispatch(session, "predict", {"value": 3})["ok"])


class Samples(unittest.TestCase):
    def test_catalogue_lists_five_datasets_without_the_payloads(self):
        result = dispatch(Session(), "samples", {})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["samples"]), 5)
        for item in result["samples"]:
            self.assertNotIn("csv", item)
            for field in ("key", "name", "title", "area", "description", "rows", "columns"):
                self.assertIn(field, item)

    def test_default_key_is_in_the_catalogue(self):
        result = dispatch(Session(), "samples", {})
        self.assertIn(result["default"], [s["key"] for s in result["samples"]])

    def test_demo_without_a_key_loads_the_default(self):
        result = dispatch(Session(), "demo", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["sample"], "cultivos")

    def test_every_catalogued_key_loads(self):
        session = Session()
        for item in dispatch(session, "samples", {})["samples"]:
            result = dispatch(session, "demo", {"sample": item["key"]})
            self.assertTrue(result["ok"], item["key"])
            self.assertEqual(result["dataset"]["name"], item["name"])
            self.assertEqual(result["dataset"]["rows"], item["rows"])

    def test_unknown_key_is_refused(self):
        result = dispatch(Session(), "demo", {"sample": "inventado"})
        self.assertFalse(result["ok"])
        self.assertIn("inventado", result["error"])

    def test_sample_csv_returns_a_downloadable_table(self):
        result = dispatch(Session(), "sample_csv", {"sample": "salud"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["name"].endswith(".csv"))
        self.assertEqual(len(result["csv"].strip().splitlines()), 151)

    def test_sample_csv_rejects_an_unknown_key(self):
        self.assertFalse(dispatch(Session(), "sample_csv", {"sample": "x"})["ok"])

    def test_demo_does_not_carry_a_model_over(self):
        session = loaded()
        dispatch(session, "regression", {"x": "x", "y": "y"})
        dispatch(session, "demo", {"sample": "ventas"})
        self.assertFalse(dispatch(session, "predict", {"value": 10})["ok"])


class Describe(unittest.TestCase):
    def test_quantitative_column(self):
        result = dispatch(loaded(), "describe", {"column": "x"})
        self.assertEqual(result["kind"], "quantitative")
        self.assertIn("<svg", result["chart"])
        self.assertEqual(result["stats"]["n"], 6)

    def test_qualitative_column_falls_back_to_a_frequency_table(self):
        result = dispatch(loaded(), "describe", {"column": "g"})
        self.assertEqual(result["kind"], "qualitative")
        self.assertEqual(result["table"]["distinct"], 2)

    def test_missing_column_argument(self):
        result = dispatch(loaded(), "describe", {})
        self.assertFalse(result["ok"])
        self.assertIn("column", result["error"])

    def test_unknown_column(self):
        result = dispatch(loaded(), "describe", {"column": "zzz"})
        self.assertFalse(result["ok"])
        self.assertIn("zzz", result["error"])


class Charts(unittest.TestCase):
    def test_scatter(self):
        result = dispatch(loaded(), "chart", {"type": "scatter", "x": "x", "y": "y"})
        self.assertEqual(result["points"], 6)
        self.assertEqual(result["dropped"], 0)
        self.assertIsNone(result["fit"])

    def test_scatter_with_a_fit_line(self):
        result = dispatch(loaded(), "chart", {"type": "scatter", "x": "x", "y": "y", "fit": True})
        self.assertIsNotNone(result["fit"])
        self.assertGreater(result["fit"]["r2"], 0.9)

    def test_histogram(self):
        self.assertTrue(dispatch(loaded(), "chart", {"type": "histogram", "x": "x"})["ok"])

    def test_histogram_of_a_qualitative_column_suggests_bars(self):
        result = dispatch(loaded(), "chart", {"type": "histogram", "x": "g"})
        self.assertFalse(result["ok"])
        self.assertIn("barras", result["error"])

    def test_bars(self):
        result = dispatch(loaded(), "chart", {"type": "bars", "x": "g"})
        self.assertEqual(result["distinct"], 2)
        self.assertEqual(result["points"], 6)

    def test_unknown_chart_type(self):
        self.assertFalse(dispatch(loaded(), "chart", {"type": "pastel", "x": "x"})["ok"])

    def test_scatter_needs_overlapping_numeric_rows(self):
        session = Session()
        dispatch(session, "load", {"text": "x,y\n1,\n2,\n3,\n", "filename": "t.csv"})
        result = dispatch(session, "chart", {"type": "scatter", "x": "x", "y": "y"})
        self.assertFalse(result["ok"])

    def test_chart_markup_escapes_column_names(self):
        session = Session()
        dispatch(session, "load", {
            "filename": "t.csv",
            "text": '"<script>alert(1)</script>",y\n1,2\n2,4\n3,6\n',
        })
        name = session.dataset.names[0]
        result = dispatch(session, "chart", {"type": "scatter", "x": name, "y": "y"})
        self.assertTrue(result["ok"])
        self.assertNotIn("<script>", result["chart"])
        self.assertIn("&lt;script&gt;", result["chart"])


class RegressionAndPrediction(unittest.TestCase):
    def test_fit(self):
        result = dispatch(loaded(), "regression", {"x": "x", "y": "y"})
        self.assertTrue(result["ok"])
        self.assertGreater(result["report"]["model"]["r2"], 0.9)
        self.assertIn("<svg", result["chart"])

    def test_same_variable_on_both_axes_is_refused(self):
        result = dispatch(loaded(), "regression", {"x": "x", "y": "x"})
        self.assertFalse(result["ok"])
        self.assertIn("distintas", result["error"])

    def test_qualitative_variable_is_refused(self):
        self.assertFalse(dispatch(loaded(), "regression", {"x": "g", "y": "y"})["ok"])

    def test_predict_requires_a_trained_model(self):
        result = dispatch(loaded(), "predict", {"value": 3})
        self.assertFalse(result["ok"])
        self.assertIn("Entrene", result["error"])

    def test_predict_after_training(self):
        session = loaded()
        dispatch(session, "regression", {"x": "x", "y": "y"})
        result = dispatch(session, "predict", {"value": 3.5})
        self.assertTrue(result["ok"])
        self.assertFalse(result["prediction"]["extrapolated"])
        self.assertIn("proyecta", result["prediction"]["advice"])

    def test_predict_accepts_a_decimal_comma(self):
        session = loaded()
        dispatch(session, "regression", {"x": "x", "y": "y"})
        comma = dispatch(session, "predict", {"value": "3,5"})
        dot = dispatch(session, "predict", {"value": "3.5"})
        self.assertAlmostEqual(comma["prediction"]["y"], dot["prediction"]["y"])

    def test_predict_rejects_text(self):
        session = loaded()
        dispatch(session, "regression", {"x": "x", "y": "y"})
        result = dispatch(session, "predict", {"value": "mucho"})
        self.assertFalse(result["ok"])
        self.assertIn("número", result["error"])

    def test_predict_far_outside_the_range_warns(self):
        session = loaded()
        dispatch(session, "regression", {"x": "x", "y": "y"})
        result = dispatch(session, "predict", {"value": 500})
        self.assertTrue(result["prediction"]["extrapolated"])
        self.assertIn("extrapolación", result["prediction"]["warning"])


class Normal(unittest.TestCase):
    def test_profile(self):
        result = dispatch(loaded(), "normal", {"column": "x"})
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["profile"]["mu"], 3.5)
        self.assertIn("<svg", result["chart"])

    def test_qualitative_column_is_refused(self):
        self.assertFalse(dispatch(loaded(), "normal", {"column": "g"})["ok"])

    def test_probability_queries(self):
        session = loaded()
        for kind, payload in [
            ("less", {"a": 3}),
            ("greater", {"a": 3}),
            ("between", {"a": 2, "b": 4}),
            ("outside", {"a": 2, "b": 4}),
        ]:
            result = dispatch(session, "probability", {"mu": 3, "sigma": 1, "kind": kind, **payload})
            self.assertTrue(result["ok"], kind)
            self.assertGreaterEqual(result["result"]["value"], 0.0)
            self.assertLessEqual(result["result"]["value"], 1.0)

    def test_between_without_the_second_bound(self):
        result = dispatch(Session(), "probability", {"mu": 0, "sigma": 1, "kind": "between", "a": 1})
        self.assertFalse(result["ok"])

    def test_zero_sigma(self):
        result = dispatch(Session(), "probability", {"mu": 0, "sigma": 0, "kind": "less", "a": 1})
        self.assertFalse(result["ok"])
        self.assertIn("desviación", result["error"].lower())

    def test_probability_does_not_need_a_dataset(self):
        result = dispatch(Session(), "probability", {"mu": 10, "sigma": 2, "kind": "less", "a": 10})
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["result"]["value"], 0.5)


class JsonBridge(unittest.TestCase):
    """The browser talks to the engine through these two strings only."""

    def test_round_trip(self):
        session = Session()
        out = json.loads(dispatch_json(session, "demo", json.dumps({"sample": "aire"})))
        self.assertTrue(out["ok"])
        self.assertEqual(out["dataset"]["name"], "calidad_aire.csv")

    def test_empty_payload_string(self):
        self.assertTrue(json.loads(dispatch_json(Session(), "samples", ""))["ok"])

    def test_malformed_json_is_reported(self):
        out = json.loads(dispatch_json(Session(), "demo", "{no json"))
        self.assertFalse(out["ok"])
        self.assertIn("JSON", out["error"])

    def test_output_is_strict_json(self):
        session = Session()
        dispatch_json(session, "demo", "{}")
        for action, payload in [
            ("describe", {"column": "Rendimiento_ton_ha"}),
            ("normal", {"column": "Riego_mm"}),
            ("chart", {"type": "bars", "x": "Region"}),
        ]:
            text = dispatch_json(session, action, json.dumps(payload))
            self.assertNotIn("NaN", text, action)
            json.loads(text)  # raises if the payload is not valid JSON


class Isolation(unittest.TestCase):
    def test_sessions_do_not_share_state(self):
        first, second = loaded(), Session()
        self.assertTrue(dispatch(first, "describe", {"column": "x"})["ok"])
        self.assertFalse(dispatch(second, "describe", {"column": "x"})["ok"])


if __name__ == "__main__":
    unittest.main()
