"""Statistics, checked against values worked out by hand.

These are black-box tests: they call the public functions the way the app does
and compare against numbers computed independently (by hand or from a textbook
identity), never against whatever the code happens to return today.
"""

from __future__ import annotations

import math
import unittest

from core import analysis
from core.dataset import read_csv


def ds(text: str):
    return read_csv(text, name="t.csv")


class Descriptive(unittest.TestCase):
    def test_mean_median_std_of_known_series(self):
        # 2,4,4,4,5,5,7,9 — the classic textbook series: mean 5, population σ 2.
        data = [2, 4, 4, 4, 5, 5, 7, 9]
        self.assertAlmostEqual(analysis.mean(data), 5.0)
        self.assertAlmostEqual(analysis.std_dev(data), 2.0)
        self.assertAlmostEqual(analysis.std_dev(data, population=False), 2.13808993, places=6)

    def test_percentiles_use_linear_interpolation(self):
        data = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(analysis._percentile(data, 0.25), 1.75)
        self.assertAlmostEqual(analysis._percentile(data, 0.50), 2.5)
        self.assertAlmostEqual(analysis._percentile(data, 0.75), 3.25)

    def test_percentile_of_single_value(self):
        self.assertEqual(analysis._percentile([7.0], 0.9), 7.0)

    def test_empty_series_raise(self):
        for fn in (analysis.mean, analysis.std_dev):
            with self.assertRaises(ValueError):
                fn([])

    def test_std_dev_of_one_value_is_zero(self):
        self.assertEqual(analysis.std_dev([3.0]), 0.0)

    def test_modes(self):
        self.assertEqual(analysis.modes([1, 2, 3]), [])          # all unique
        self.assertEqual(analysis.modes([1, 2, 2, 3]), [2])      # unimodal
        self.assertEqual(sorted(analysis.modes([1, 1, 2, 2])), [1, 2])  # bimodal
        self.assertEqual(analysis.modes([]), [])

    def test_amodal_series_reports_no_mode(self):
        stats = analysis.descriptive_stats(ds("x\n1\n2\n3\n4\n"), "x")
        moda = next(m for m in stats["measures"] if m["label"] == "Moda")
        self.assertIsNone(moda["value"])
        self.assertEqual(moda["note"], "sin moda")

    def test_multimodal_series_reports_the_count(self):
        stats = analysis.descriptive_stats(ds("x\n1\n1\n2\n2\n3\n"), "x")
        moda = next(m for m in stats["measures"] if m["label"] == "Moda")
        self.assertIsNone(moda["value"])
        self.assertEqual(moda["note"], "2 modas")

    def test_measures_match_hand_computed_values(self):
        stats = analysis.descriptive_stats(ds("x\n2\n4\n4\n4\n5\n5\n7\n9\n"), "x")
        by_label = {m["label"]: m["value"] for m in stats["measures"]}
        self.assertEqual(stats["n"], 8)
        self.assertAlmostEqual(by_label["Media"], 5.0)
        self.assertAlmostEqual(by_label["Mediana"], 4.5)
        self.assertAlmostEqual(by_label["Moda"], 4.0)
        self.assertAlmostEqual(by_label["Desv. estándar"], 2.0)
        self.assertAlmostEqual(by_label["Varianza"], 4.0)
        self.assertAlmostEqual(by_label["Coef. variación"], 40.0)
        self.assertAlmostEqual(by_label["Rango"], 7.0)
        self.assertAlmostEqual(by_label["Mínimo"], 2.0)
        self.assertAlmostEqual(by_label["Máximo"], 9.0)
        self.assertAlmostEqual(by_label["Q1"], 4.0)
        self.assertAlmostEqual(by_label["Q3"], 5.5)
        self.assertAlmostEqual(by_label["Rango interc."], 1.5)

    def test_coefficient_of_variation_is_none_when_mean_is_zero(self):
        stats = analysis.descriptive_stats(ds("x\n-1\n1\n"), "x")
        cv = next(m for m in stats["measures"] if m["label"] == "Coef. variación")
        self.assertIsNone(cv["value"])

    def test_descriptive_stats_rejects_a_qualitative_column(self):
        with self.assertRaises(ValueError):
            analysis.descriptive_stats(ds("x\na\nb\n"), "x")

    def test_missing_values_are_counted_not_dropped_silently(self):
        # `y` keeps the rows alive; a row that is blank in every column is
        # dropped as an empty line instead, which the next test covers.
        stats = analysis.descriptive_stats(ds("x,y\n1,1\n,2\n3,3\nNA,4\n"), "x")
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["missing"], 2)

    def test_a_row_blank_in_every_column_is_not_a_row(self):
        stats = analysis.descriptive_stats(ds("x\n1\n\n3\nNA\n"), "x")
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["missing"], 0)


class Histogram(unittest.TestCase):
    def test_counts_add_up_to_the_sample_size(self):
        data = [float(i % 17) for i in range(200)]
        hist = analysis.histogram(data)
        self.assertEqual(sum(b["count"] for b in hist["bins"]), len(data))
        self.assertEqual(hist["max_count"], max(b["count"] for b in hist["bins"]))

    def test_bins_are_contiguous_and_cover_the_range(self):
        data = [1.0, 2.0, 3.0, 9.0]
        hist = analysis.histogram(data, bins=4)
        self.assertAlmostEqual(hist["bins"][0]["start"], 1.0)
        self.assertAlmostEqual(hist["bins"][-1]["end"], 9.0)
        for left, right in zip(hist["bins"], hist["bins"][1:]):
            self.assertAlmostEqual(left["end"], right["start"])

    def test_maximum_lands_in_the_last_bin_not_out_of_range(self):
        hist = analysis.histogram([0.0, 5.0, 10.0], bins=5)
        self.assertEqual(hist["bins"][-1]["count"], 1)

    def test_constant_series_collapses_to_one_bin(self):
        hist = analysis.histogram([4.0] * 9)
        self.assertEqual(len(hist["bins"]), 1)
        self.assertEqual(hist["bins"][0]["count"], 9)

    def test_empty_series(self):
        self.assertEqual(analysis.histogram([]), {"bins": [], "max_count": 0})


class Frequencies(unittest.TestCase):
    def setUp(self):
        self.table = analysis.frequency_table(ds("c\na\na\na\nb\nb\nc\n"), "c")

    def test_sorted_by_count_descending(self):
        self.assertEqual([r["value"] for r in self.table["rows"]], ["a", "b", "c"])
        self.assertEqual([r["count"] for r in self.table["rows"]], [3, 2, 1])

    def test_relative_frequencies_sum_to_one(self):
        self.assertAlmostEqual(sum(r["relative"] for r in self.table["rows"]), 1.0)

    def test_cumulative_reaches_one(self):
        self.assertAlmostEqual(self.table["rows"][-1]["cumulative"], 1.0)
        cumulative = [r["cumulative"] for r in self.table["rows"]]
        self.assertEqual(cumulative, sorted(cumulative))

    def test_totals(self):
        self.assertEqual(self.table["total"], 6)
        self.assertEqual(self.table["distinct"], 3)
        self.assertEqual(self.table["truncated"], 0)

    def test_long_tables_are_truncated_but_report_how_many_are_hidden(self):
        text = "c\n" + "".join(f"v{i}\n" for i in range(50))
        table = analysis.frequency_table(ds(text), "c", limit=10)
        self.assertEqual(len(table["rows"]), 10)
        self.assertEqual(table["distinct"], 50)
        self.assertEqual(table["truncated"], 40)

    def test_column_with_no_values_raises(self):
        with self.assertRaises(ValueError):
            analysis.frequency_table(ds("a,c\n1,\n2,\n"), "c")


class Regression(unittest.TestCase):
    def test_perfect_line_recovers_its_own_coefficients(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2 * x + 1 for x in xs]
        model = analysis.linear_regression(xs, ys)
        self.assertAlmostEqual(model["m"], 2.0)
        self.assertAlmostEqual(model["b"], 1.0)
        self.assertAlmostEqual(model["r"], 1.0)
        self.assertAlmostEqual(model["r2"], 1.0)
        self.assertAlmostEqual(model["std_error"], 0.0)

    def test_perfect_negative_line(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        model = analysis.linear_regression(xs, [10 - 3 * x for x in xs])
        self.assertAlmostEqual(model["m"], -3.0)
        self.assertAlmostEqual(model["r"], -1.0)
        self.assertAlmostEqual(model["r2"], 1.0)

    def test_known_noisy_fit(self):
        # By hand: x̄ = 3, ȳ = 3,4; Sxx = 10, Sxy = 7, Syy = 5,2.
        # m = 7/10 = 0,7 · b = 3,4 − 0,7·3 = 1,3 · R² = 7²/(10·5,2) = 0,942307…
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 3.0, 3.0, 4.0, 5.0]
        model = analysis.linear_regression(xs, ys)
        self.assertAlmostEqual(model["m"], 0.7)
        self.assertAlmostEqual(model["b"], 1.3)
        self.assertAlmostEqual(model["r2"], 49 / 52)
        # σ_est = √(SSE/(n−2)); SSE = Syy − m·Sxy = 5,2 − 4,9 = 0,3.
        self.assertAlmostEqual(model["std_error"], math.sqrt(0.3 / 3))

    def test_r_stays_inside_minus_one_and_one(self):
        model = analysis.linear_regression([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        self.assertLessEqual(abs(model["r"]), 1.0)

    def test_too_few_points(self):
        with self.assertRaises(ValueError):
            analysis.linear_regression([1.0, 2.0], [1.0, 2.0])

    def test_mismatched_series(self):
        with self.assertRaises(ValueError):
            analysis.linear_regression([1.0, 2.0, 3.0], [1.0, 2.0])

    def test_constant_x_is_rejected_instead_of_returning_nan(self):
        with self.assertRaises(ValueError):
            analysis.linear_regression([2.0, 2.0, 2.0], [1.0, 2.0, 3.0])

    def test_constant_y_is_rejected_instead_of_returning_nan(self):
        with self.assertRaises(ValueError):
            analysis.linear_regression([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])

    def test_fit_quality_thresholds(self):
        self.assertEqual(analysis.fit_quality(0.85)["label"], "Fuerte")
        self.assertEqual(analysis.fit_quality(0.55)["label"], "Moderado")
        self.assertEqual(analysis.fit_quality(0.10)["label"], "Débil")

    def test_report_drops_incomplete_rows_and_says_how_many(self):
        report = analysis.regression_report(ds("x,y\n1,2\n2,4\n3,\n4,8\n"), "x", "y")
        self.assertEqual(len(report["points"]), 3)
        self.assertEqual(report["dropped"], 1)
        self.assertIn("explica", report["interpretation"])


class Prediction(unittest.TestCase):
    def setUp(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.model = analysis.linear_regression(xs, [2 * x + 1 for x in xs])

    def test_inside_the_observed_range(self):
        out = analysis.predict(self.model, 3.0)
        self.assertAlmostEqual(out["y"], 7.0)
        self.assertFalse(out["extrapolated"])
        self.assertIsNone(out["warning"])

    def test_beyond_the_range_is_flagged(self):
        out = analysis.predict(self.model, 50.0)
        self.assertTrue(out["extrapolated"])
        self.assertIn("extrapolación", out["warning"])

    def test_below_the_range_is_flagged_too(self):
        self.assertTrue(analysis.predict(self.model, -10.0)["extrapolated"])

    def test_the_range_endpoints_are_not_extrapolation(self):
        self.assertFalse(analysis.predict(self.model, 1.0)["extrapolated"])
        self.assertFalse(analysis.predict(self.model, 5.0)["extrapolated"])


class Probability(unittest.TestCase):
    def test_standard_normal_cdf_reference_values(self):
        self.assertAlmostEqual(analysis.normal_cdf(0.0), 0.5)
        self.assertAlmostEqual(analysis.normal_cdf(1.0), 0.8413447, places=6)
        self.assertAlmostEqual(analysis.normal_cdf(1.96), 0.9750021, places=6)
        self.assertAlmostEqual(analysis.normal_cdf(-1.96), 0.0249979, places=6)

    def test_cdf_is_symmetric(self):
        for z in (0.3, 1.1, 2.7):
            self.assertAlmostEqual(analysis.normal_cdf(z) + analysis.normal_cdf(-z), 1.0)

    def test_pdf_peak(self):
        self.assertAlmostEqual(analysis.normal_pdf(0.0), 1 / math.sqrt(2 * math.pi))

    def test_less_and_greater_are_complementary(self):
        less = analysis.probability(10, 2, analysis.P_LESS, a=12)
        greater = analysis.probability(10, 2, analysis.P_GREATER, a=12)
        self.assertAlmostEqual(less["value"] + greater["value"], 1.0)
        self.assertAlmostEqual(less["value"], 0.8413447, places=6)

    def test_between_matches_the_empirical_rule(self):
        out = analysis.probability(0, 1, analysis.P_BETWEEN, a=-1, b=1)
        self.assertAlmostEqual(out["value"], 0.6826895, places=6)

    def test_outside_is_the_complement_of_between(self):
        inside = analysis.probability(5, 2, analysis.P_BETWEEN, a=3, b=7)
        outside = analysis.probability(5, 2, analysis.P_OUTSIDE, a=3, b=7)
        self.assertAlmostEqual(inside["value"] + outside["value"], 1.0)

    def test_reversed_bounds_are_swapped_not_rejected(self):
        forward = analysis.probability(0, 1, analysis.P_BETWEEN, a=-1, b=1)
        reversed_ = analysis.probability(0, 1, analysis.P_BETWEEN, a=1, b=-1)
        self.assertAlmostEqual(forward["value"], reversed_["value"])

    def test_equal_bounds_are_rejected(self):
        with self.assertRaises(ValueError):
            analysis.probability(0, 1, analysis.P_BETWEEN, a=2, b=2)

    def test_missing_bound(self):
        with self.assertRaises(ValueError):
            analysis.probability(0, 1, analysis.P_BETWEEN, a=1, b=None)
        with self.assertRaises(ValueError):
            analysis.probability(0, 1, analysis.P_LESS, a=None)

    def test_zero_sigma_is_rejected(self):
        with self.assertRaises(ValueError):
            analysis.probability(10, 0, analysis.P_LESS, a=5)

    def test_result_is_always_a_probability(self):
        for a in (-1e6, 0, 1e6):
            out = analysis.probability(0, 1, analysis.P_LESS, a=a)
            self.assertGreaterEqual(out["value"], 0.0)
            self.assertLessEqual(out["value"], 1.0)
            self.assertAlmostEqual(out["percent"], out["value"] * 100)

    def test_z_values_are_reported_for_the_shown_bounds(self):
        out = analysis.probability(10, 2, analysis.P_LESS, a=14)
        self.assertAlmostEqual(out["z_values"][0], 2.0)


class NormalProfile(unittest.TestCase):
    def test_symmetric_data(self):
        text = "x\n" + "".join(f"{v}\n" for v in [1, 2, 2, 3, 3, 3, 4, 4, 5])
        profile = analysis.normal_profile(ds(text), "x")
        self.assertAlmostEqual(profile["mu"], 3.0)
        self.assertAlmostEqual(profile["median"], 3.0)
        self.assertEqual(profile["shape"], "aproximadamente simétrica")
        self.assertAlmostEqual(profile["skew"], 0.0)

    def test_right_skewed_data_is_labelled(self):
        text = "x\n" + "".join(f"{v}\n" for v in [1, 1, 1, 2, 2, 3, 9, 20])
        self.assertEqual(analysis.normal_profile(ds(text), "x")["shape"], "sesgada a la derecha")

    def test_empirical_rule_proportions_are_ratios(self):
        text = "x\n" + "".join(f"{i}\n" for i in range(50))
        profile = analysis.normal_profile(ds(text), "x")
        for band in profile["empirical"]:
            self.assertGreaterEqual(band["observed"], 0.0)
            self.assertLessEqual(band["observed"], 1.0)
        observed = [b["observed"] for b in profile["empirical"]]
        self.assertEqual(observed, sorted(observed))

    def test_qualitative_column_is_rejected(self):
        with self.assertRaises(ValueError):
            analysis.normal_profile(ds("x\na\nb\n"), "x")

    def test_needs_at_least_two_values(self):
        with self.assertRaises(ValueError):
            analysis.normal_profile(ds("x\n5\n\n"), "x")


if __name__ == "__main__":
    unittest.main()
