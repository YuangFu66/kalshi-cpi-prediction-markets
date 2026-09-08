"""Unit tests for the parsing and distribution logic, plus integration checks
that the committed raw data reproduces the numbers reported in the README.

Run:  python3 -m unittest discover -s tests -v      (or: make test)

The integration tests pin the results for the data snapshot pulled on
2026-07-21. Re-running the pull scripts adds newer months and will change
those numbers; update the expectations together with the README.
"""
import math
import pathlib
import sys
import unittest

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_series import implied_distribution, parse_threshold   # noqa: E402
from cpi_values import parse_actual, settled_value               # noqa: E402
from evaluate import dm_test                                     # noqa: E402


def day_frame(thresholds, mids, actual=None, spread=0.02):
    """One (event, day) slice of market_day, as implied_distribution expects it."""
    n = len(mids)
    return pd.DataFrame({"threshold": thresholds, "mid": mids, "spread": [spread] * n,
                         "volume": [10.0] * n, "actual_cpi_mom": [actual] * n})


class ParseThreshold(unittest.TestCase):
    def test_every_ticker_convention(self):
        self.assertEqual(parse_threshold("KXCPI-26MAY-T-0.3", "KXCPI-26MAY"), -0.3)
        self.assertEqual(parse_threshold("CPI-22AUG-TN0.1", "CPI-22AUG"), -0.1)
        self.assertEqual(parse_threshold("CPI-22JUL-T0.1", "CPI-22JUL"), 0.1)
        self.assertEqual(parse_threshold("KXCPI-26MAR-T1.3", "KXCPI-26MAR"), 1.3)

    def test_non_threshold_ticker(self):
        self.assertIsNone(parse_threshold("CPI-22JUL-B0.1", "CPI-22JUL"))


class ParseActual(unittest.TestCase):
    def test_every_settlement_format(self):
        cases = [("0.5", 0.5), ("0.60", 0.6), ("0.5%", 0.5), (".9%", 0.9),
                 (" 0.3 ", 0.3), ("", None), (None, None), ("n/a", None)]
        for raw, want in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_actual(raw), want)


class SettledValue(unittest.TestCase):
    def test_uses_expiration_value_when_markets_agree(self):
        ms = [{"ticker": "E-T0.1", "expiration_value": "0.30", "result": "yes"},
              {"ticker": "E-T0.3", "expiration_value": ".3%", "result": "no"}]
        self.assertEqual(settled_value(ms, {"E-T0.1": 0.1, "E-T0.3": 0.3}), 0.3)

    def test_infers_print_from_contract_results(self):
        # CPI-23OCT style: no usable value; YES up to -0.1, NO from 0.0 => print = 0.0
        ms, thr = [], {}
        for x in [-0.2, -0.1, 0.0, 0.1, 0.2]:
            t = f"E-T{x}"
            ms.append({"ticker": t, "expiration_value": "",
                       "result": "yes" if x < 0 else "no"})
            thr[t] = x
        self.assertEqual(settled_value(ms, thr), 0.0)

    def test_gap_in_threshold_grid_is_ambiguous(self):
        ms = [{"ticker": "E-T-0.2", "expiration_value": "", "result": "yes"},
              {"ticker": "E-T0.2", "expiration_value": "", "result": "no"}]
        self.assertIsNone(settled_value(ms, {"E-T-0.2": -0.2, "E-T0.2": 0.2}))


class ImpliedDistribution(unittest.TestCase):
    def test_worked_example_from_the_presentation(self):
        # prices 95c/78c/35c/8c for "above 0.0/0.1/0.2/0.3" -> mean 0.216, P(0.2) = 43%
        r = implied_distribution(day_frame([0.0, 0.1, 0.2, 0.3],
                                           [0.95, 0.78, 0.35, 0.08], actual=0.2))
        self.assertAlmostEqual(r["implied_mean"], 0.216, places=9)
        self.assertAlmostEqual(r["prob_sum_raw"], 1.0, places=12)
        self.assertAlmostEqual(r["prob_true_bin"], 0.43, places=9)
        self.assertEqual(r["mono_violation"], 0.0)
        self.assertEqual(r["n_thresholds"], 4)
        self.assertAlmostEqual(r["abs_error_mean"], 0.016, places=9)

    def test_monotonicity_violation_is_fixed_and_recorded(self):
        # CPI-24JAN on 2024-02-01: two prices sit above the one below them
        r = implied_distribution(day_frame([-0.2, -0.1, 0.0, 0.1, 0.2],
                                           [0.900, 0.970, 0.905, 0.520, 0.065]))
        self.assertAlmostEqual(r["mono_violation"], 0.07, places=9)
        self.assertAlmostEqual(r["prob_sum_raw"], 1.0, places=12)
        self.assertGreaterEqual(r["implied_sd"], 0.0)

    def test_uninformative_quotes_are_dropped(self):
        f = day_frame([0.0, 0.1, 0.2], [0.9, 0.5, 0.1])
        f.loc[1, "spread"] = 0.98                      # quoted 0/100
        self.assertEqual(implied_distribution(f)["n_thresholds"], 2)
        self.assertIsNone(implied_distribution(day_frame([0.0, 0.1], [0.5, 0.5], spread=1.0)))

    def test_tail_bins(self):
        # all mass above the top threshold -> valued one grid step beyond it
        r = implied_distribution(day_frame([0.1, 0.2], [1.0, 1.0]))
        self.assertAlmostEqual(r["implied_mean"], 0.3, places=9)
        # all mass below the bottom threshold -> valued at that threshold
        r = implied_distribution(day_frame([0.1, 0.2], [0.0, 0.0]))
        self.assertAlmostEqual(r["implied_mean"], 0.1, places=9)


class DieboldMariano(unittest.TestCase):
    def test_matches_paired_t_test_at_lag_zero(self):
        n, mean_d, t, p = dm_test([1, 2, 3, 4], [2, 2, 2, 2])
        self.assertEqual(n, 4)
        self.assertAlmostEqual(mean_d, 0.5)
        self.assertAlmostEqual(t, 0.5 / math.sqrt((5 / 3) / 4), places=9)
        self.assertTrue(0 < p < 1)

    def test_sign_convention(self):
        _, _, t, _ = dm_test([0.1, 0.1, 0.1, 0.1], [0.3, 0.2, 0.4, 0.3])
        self.assertLess(t, 0)                          # first forecaster is better

    def test_degenerate_input(self):
        n, _, t, p = dm_test([0.1, 0.2], [0.1, 0.2])
        self.assertTrue(math.isnan(t) and math.isnan(p))


class CommittedDataReproducesReportedResults(unittest.TestCase):
    """Integration checks on the committed snapshot (pulled 2026-07-21)."""

    @classmethod
    def setUpClass(cls):
        if not (ROOT / "results" / "diebold_mariano.csv").exists():
            raise unittest.SkipTest("results not built yet (run: make build evaluate)")

    def test_clean_tables(self):
        ev = pd.read_csv(ROOT / "data/clean/events_table.csv")
        self.assertEqual(len(ev), 66)
        self.assertEqual(int(ev.settled.sum()), 61)
        dd = pd.read_csv(ROOT / "data/clean/distribution_day.csv")
        self.assertTrue(((dd.prob_sum_raw - 1).abs() < 1e-9).all())
        self.assertTrue((dd.implied_sd >= 0).all())
        sn = pd.read_csv(ROOT / "data/clean/forecast_snapshots.csv")
        self.assertEqual(sn.event_ticker.nunique(), 57)
        self.assertEqual(set(sn.horizon), {30, 14, 7, 1})

    def test_headline_accuracy_one_day_before_release(self):
        acc = pd.read_csv(ROOT / "results/accuracy_by_horizon.csv")
        h = acc[(acc["sample"] == "headline") & (acc.horizon_days == 1)].set_index("forecaster")
        self.assertEqual(int(h.loc["kalshi", "n"]), 56)
        self.assertAlmostEqual(h.loc["kalshi", "mae"], 0.091, delta=0.0006)
        self.assertAlmostEqual(h.loc["cleveland", "mae"], 0.128, delta=0.0006)
        self.assertLess(h.loc["kalshi", "mae"], h.loc["naive_last", "mae"])

    def test_site_data_matches_results(self):
        import json
        s = json.loads((ROOT / "site/data/summary.json").read_text())
        acc = pd.read_csv(ROOT / "results/accuracy_by_horizon.csv")
        h = acc[(acc["sample"] == "headline") & (acc.horizon_days == 1)].set_index("forecaster")
        self.assertAlmostEqual(s["headline"]["kalshi_mae_1d"], h.loc["kalshi", "mae"], places=4)
        events = json.loads((ROOT / "site/data/events.json").read_text())["events"]
        self.assertEqual(len(events), 57)
        for e in events:
            for d in e["days"]:
                self.assertAlmostEqual(sum(d["p"]), 1.0, delta=0.01)   # probabilities rounded to 3 dp
                self.assertEqual(len(d["p"]), len(d["thr"]) + 1)

    def test_headline_diebold_mariano(self):
        dm = pd.read_csv(ROOT / "results/diebold_mariano.csv")
        r = dm[(dm["sample"] == "headline") & (dm.horizon_days == 1)
               & (dm.benchmark == "cleveland") & (dm.loss == "abs")].iloc[0]
        self.assertEqual(int(r.n), 56)
        self.assertAlmostEqual(r.dm_t, -3.26, places=2)
        self.assertLess(r.dm_p, 0.01)
        self.assertEqual(int(r.kalshi_closer), 32)


if __name__ == "__main__":
    unittest.main()
