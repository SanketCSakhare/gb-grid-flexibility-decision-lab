"""Meaningful output checks; run after pipeline.py with python -m unittest discover -s tests."""
import json
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "grid_lab.sqlite"
RESULTS = ROOT / "data" / "processed" / "results.json"


class OutputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = json.loads(RESULTS.read_text(encoding="utf-8"))
        cls.con = sqlite3.connect(DB)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_grain_and_join(self):
        row = self.con.execute("""SELECT COUNT(*), COUNT(DISTINCT timestamp_utc),
                          SUM(carbon_intensity_g_kwh IS NULL)
                          FROM mart_grid_interval""").fetchone()
        self.assertEqual(row, (31390, 31390, 0))
        self.assertEqual(self.results["quality"]["matched_rows"], row[0])

    def test_forecast_mae_independent_sql(self):
        mae, baseline = self.con.execute("""SELECT AVG(ABS(national_demand_mw-model_mw)),
                            AVG(ABS(national_demand_mw-persistence_mw))
                            FROM forecast_backtest WHERE split='test'""").fetchone()
        self.assertAlmostEqual(mae, self.results["forecast"]["test"]["model"]["mae_mw"], delta=.051)
        self.assertAlmostEqual(baseline, self.results["forecast"]["test"]["persistence"]["mae_mw"], delta=.051)

    def test_scenario_arithmetic(self):
        count, mismatches = self.con.execute("""SELECT COUNT(*), SUM(ABS(exposure_delta_kg_per_mwh -
                               (evening_mean_g_kwh-best_two_daytime_mean_g_kwh)) > 0.000001)
                               FROM flexibility_scenario""").fetchone()
        self.assertEqual(count, self.results["scenario"]["days"])
        self.assertEqual(mismatches, 0)

    def test_clock_change_days(self):
        counts = self.results["quality"]["clock_change_period_counts"]
        self.assertEqual(counts["2025-03-30"], 46)
        self.assertEqual(counts["2025-10-26"], 50)


if __name__ == "__main__":
    unittest.main()

