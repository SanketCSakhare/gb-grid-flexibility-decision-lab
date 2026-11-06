"""Rebuild the GB grid decision mart and honest backtest from NESO snapshots."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
LONDON = ZoneInfo("Europe/London")


def demand_frame() -> pd.DataFrame:
    parts = []
    for year in (2025, 2026):
        d = pd.read_csv(RAW / f"demand_{year}.csv")
        if "FORECAST_ACTUAL_INDICATOR" in d:
            d = d[d.FORECAST_ACTUAL_INDICATOR == "A"].copy()
        d = d[["SETTLEMENT_DATE", "SETTLEMENT_PERIOD", "ND", "TSD"]].copy()
        d.columns = ["settlement_date", "period", "national_demand_mw", "transmission_demand_mw"]
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    assert not d.duplicated(["settlement_date", "period"]).any(), "Duplicate settlement key"
    assert d.national_demand_mw.notna().all() and d.national_demand_mw.gt(0).all()

    # A settlement period is 30 minutes of elapsed time after local midnight.
    # This preserves the 46/50-period UK clock-change days.
    def to_utc(row):
        local_midnight = datetime.fromisoformat(row.settlement_date).replace(tzinfo=LONDON)
        return (local_midnight.astimezone(timezone.utc)
                + timedelta(minutes=30 * (int(row.period) - 1)))

    d["timestamp_utc"] = d.apply(to_utc, axis=1)
    assert not d.timestamp_utc.duplicated().any(), "Duplicate UTC interval"
    return d.sort_values("timestamp_utc").reset_index(drop=True)


def generation_frame() -> pd.DataFrame:
    g = pd.read_csv(RAW / "generation_mix_2025_2026.csv")
    g = g[["DATETIME", "CARBON_INTENSITY", "WIND_perc", "SOLAR_perc",
           "GAS_perc", "FOSSIL_perc", "RENEWABLE_perc"]].copy()
    g.columns = ["timestamp_utc", "carbon_intensity_g_kwh", "wind_pct", "solar_pct",
                 "gas_pct", "fossil_pct", "renewable_pct"]
    g.timestamp_utc = pd.to_datetime(g.timestamp_utc, utc=True)
    assert not g.timestamp_utc.duplicated().any(), "Duplicate mix UTC interval"
    return g


def make_mart() -> tuple[pd.DataFrame, dict]:
    d, g = demand_frame(), generation_frame()
    m = d.merge(g, on="timestamp_utc", how="left", validate="one_to_one", indicator=True)
    counts = m._merge.value_counts().to_dict()
    m = m.drop(columns="_merge")
    local = m.timestamp_utc.dt.tz_convert(LONDON)
    m["local_date"] = local.dt.strftime("%Y-%m-%d")
    m["local_hour"] = local.dt.hour + local.dt.minute / 60
    m["weekday"] = local.dt.dayofweek
    m["month"] = local.dt.month
    m["demand_mwh"] = m.national_demand_mw * 0.5
    quality = {
        "demand_rows": len(d), "generation_rows_in_snapshot": len(g),
        "matched_rows": int(counts.get("both", 0)),
        "unmatched_demand_rows": int(counts.get("left_only", 0)),
        "missing_intensity_rows": int(m.carbon_intensity_g_kwh.isna().sum()),
        "first_utc": str(m.timestamp_utc.min()), "last_utc": str(m.timestamp_utc.max()),
        "clock_change_period_counts": d.groupby("settlement_date").size().loc[
            lambda s: s.ne(48)].to_dict(),
    }
    assert quality["unmatched_demand_rows"] == 0, quality
    return m, quality


def forecast_backtest(m: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    f = m[["timestamp_utc", "national_demand_mw", "local_hour", "weekday", "month"]].copy()
    # Forecast each interval using only earlier demand and known calendar features.
    for lag in (1, 2, 48, 336):
        f[f"lag_{lag}"] = f.national_demand_mw.shift(lag)
    f["hour_sin"] = np.sin(2 * np.pi * f.local_hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * f.local_hour / 24)
    f["dow_sin"] = np.sin(2 * np.pi * f.weekday / 7)
    f["dow_cos"] = np.cos(2 * np.pi * f.weekday / 7)
    # Missing intervals would make row shifts invalid; fail rather than silently backfill.
    assert f.timestamp_utc.diff().iloc[1:].eq(pd.Timedelta(minutes=30)).all(), \
        "Demand timeline has gaps; lag features need time-aware joining"
    f = f.dropna().copy()
    features = ["lag_1", "lag_2", "lag_48", "lag_336", "hour_sin",
                "hour_cos", "dow_sin", "dow_cos", "month"]
    train = f.timestamp_utc.lt("2026-01-01")
    validation = f.timestamp_utc.ge("2026-01-01") & f.timestamp_utc.lt("2026-07-01")
    test = f.timestamp_utc.ge("2026-07-01")
    assert train.sum() > 10000 and validation.sum() > 5000 and test.sum() > 1000
    model = HistGradientBoostingRegressor(max_iter=180, max_leaf_nodes=24,
                                           learning_rate=0.07, l2_regularization=10,
                                           random_state=42)
    model.fit(f.loc[train, features], f.loc[train, "national_demand_mw"])
    f["model_mw"] = model.predict(f[features])
    f["persistence_mw"] = f.lag_1
    f["split"] = np.select([train, validation, test], ["train", "validation", "test"], default="unassigned")
    metrics = {}
    for name, mask in (("validation", validation), ("test", test)):
        actual = f.loc[mask, "national_demand_mw"]
        metrics[name] = {"rows": int(mask.sum())}
        for method, column in (("model", "model_mw"), ("persistence", "persistence_mw")):
            pred = f.loc[mask, column]
            metrics[name][method] = {
                "mae_mw": round(mean_absolute_error(actual, pred), 1),
                "rmse_mw": round(float(np.sqrt(mean_squared_error(actual, pred))), 1),
                "wape_pct": round(100 * np.abs(actual - pred).sum() / actual.sum(), 2),
            }
    return f[["timestamp_utc", "national_demand_mw", "model_mw", "persistence_mw", "split"]], metrics


def flexibility_scenario(m: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Illustrative 1 MWh/day shift; average intensity exposure, not avoided emissions."""
    valid = m.dropna(subset=["carbon_intensity_g_kwh"]).copy()
    valid = valid[valid.local_date.between("2025-01-01", "2026-10-15")]
    rows = []
    for day, group in valid.groupby("local_date"):
        baseline = group[(group.local_hour >= 18) & (group.local_hour < 22)]
        destination = group[(group.local_hour >= 10) & (group.local_hour < 16)]
        if len(baseline) != 8 or len(destination) != 12:
            continue
        base = float(baseline.carbon_intensity_g_kwh.mean())
        dest = float(destination.carbon_intensity_g_kwh.nsmallest(2).mean())
        # 1 MWh = 1,000 kWh; g/kWh converts numerically to kg/MWh.
        rows.append((day, base, dest, base - dest, dest < base))
    s = pd.DataFrame(rows, columns=["local_date", "evening_mean_g_kwh",
                                     "best_two_daytime_mean_g_kwh", "exposure_delta_kg_per_mwh",
                                     "daytime_lower"])
    stats = {"days": len(s), "daytime_lower_days_pct": round(100 * s.daytime_lower.mean(), 1),
             "median_exposure_delta_kg_per_mwh": round(float(s.exposure_delta_kg_per_mwh.median()), 1),
             "mean_exposure_delta_kg_per_mwh": round(float(s.exposure_delta_kg_per_mwh.mean()), 1)}
    return s, stats


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m, quality = make_mart()
    forecast, metrics = forecast_backtest(m)
    scenario, scenario_stats = flexibility_scenario(m)
    m.timestamp_utc = m.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    forecast.timestamp_utc = forecast.timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    db = OUT / "grid_lab.sqlite"
    if db.exists():
        db.unlink()
    with sqlite3.connect(db) as con:
        m.to_sql("mart_grid_interval", con, index=False)
        forecast.to_sql("forecast_backtest", con, index=False)
        scenario.to_sql("flexibility_scenario", con, index=False)
        con.execute("CREATE UNIQUE INDEX idx_grid_time ON mart_grid_interval(timestamp_utc)")
        con.execute("CREATE INDEX idx_grid_date ON mart_grid_interval(local_date)")
        con.execute("CREATE UNIQUE INDEX idx_forecast_time ON forecast_backtest(timestamp_utc)")
        con.execute("CREATE UNIQUE INDEX idx_flex_date ON flexibility_scenario(local_date)")
        daily_sql = (ROOT / "sql" / "daily_mart.sql").read_text(encoding="utf-8")
        con.executescript(daily_sql)
    summary = {"quality": quality, "forecast": metrics, "scenario": scenario_stats,
               "source_as_of": "2026-11-06", "definitions": {
                   "forecast": "30-minute-ahead rolling forecast; 2025 train, Jan-Jun 2026 validation, Jul-Oct 2026 test",
                   "scenario": "Illustrative historical average-intensity exposure for 1 MWh/day; not causal avoided emissions"}}
    (OUT / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
