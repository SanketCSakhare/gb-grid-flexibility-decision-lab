# GB Grid Flexibility Decision Lab

**Decision question:** Can a near-term GB electricity-demand forecast and a historical carbon-intensity screen help analysts identify periods worth investigating for flexible-load scheduling?

This is a senior analyst portfolio project using **open NESO data**. It demonstrates source assessment, a reproducible Python pipeline, dimensional/SQL modelling, temporal backtesting against a baseline, data-quality controls, an interactive Streamlit dashboard, and decision communication. It does **not** claim dispatch-ready forecasts, avoided emissions or cost savings.

The design reflects the [UK Government senior data analyst capability framework](https://understand-digital-data-roles-skills.service.gov.uk/role/data-analyst/) and current [UK senior analyst vacancy requirements](https://www.awtg.co.uk/jobs/senior-data-analyst): analysis leadership, SQL, BI, Python, data quality, modelling and communication. This project demonstrates the technical parts and documents the decision narrative; it cannot itself prove workplace leadership or stakeholder management.

## Evidence at snapshot date (6 November 2026)

| Measure | Result | Interpretation |
|---|---:|---|
| Demand intervals, 2025–16 Oct 2026 | 31,390 | All actual rows in the supplied snapshot |
| Demand ↔ generation UTC matches | 31,390 / 31,390 | No missing carbon-intensity joins |
| 30-minute forecast test MAE | 294 MW | Jul–16 Oct 2026 held-out period |
| Persistence baseline test MAE | 620 MW | Previous interval as forecast |
| Test WAPE | 1.29% vs 2.72% | Model vs persistence baseline |
| Illustrative days with lower daytime intensity | 90.7% of 653 | Retrospective, hindsight-selected daytime slots |
| Median intensity-weighted difference | 55.2 kg/MWh | Scenario screen; **not** avoided emissions |

These figures are reproducible with `python pipeline.py` from the included dated source snapshot. Results will change if NESO revises or extends the source files.

## Run

```bash
python -m venv .venv
# activate the environment using your shell's command
pip install -r requirements.txt
python pipeline.py
streamlit run app.py
python -m unittest discover -s tests
```

The pipeline writes `data/processed/grid_lab.sqlite` and `data/processed/results.json`. The included processed files let you open the dashboard directly. Python 3.12 was used for this build.

## Sources and grain

| Input | Grain | Supplied snapshot | Provenance |
|---|---|---|---|
| `demand_2025.csv` | GB settlement date × period | 17,520 intervals | [NESO 2025 historic demand](https://www.neso.energy/data-portal/historic-demand-data/historic_demand_data_2025) |
| `demand_2026.csv` | GB settlement date × period | 13,870 actual intervals to 16 Oct | [NESO 2026 historic demand](https://www.neso.energy/data-portal/historic-demand-data/historic_demand_data_2026) |
| `generation_mix_2025_2026.csv` | UTC half-hour | 31,392 intervals | Date-filtered from [NESO historic generation mix](https://www.neso.energy/data-portal/historic-generation-mix) downloaded 6 Nov 2026 |

`ND` is NESO national demand in MW; it is **not** total household consumption. A half-hour interval's energy is `ND × 0.5` MWh. Generation carbon intensity is in gCO₂/kWh. The two datasets are joined at a UTC half-hour timestamp. Settlement periods are mapped from Europe/London midnight using elapsed 30-minute periods, preserving 46- and 50-period clock-change days. The 2026 `FORECAST_ACTUAL_INDICATOR` is restricted to `A`; 2025 has no such column.

The bundled source snapshot is attributed to National Energy System Operator under its [open data licence](https://www.neso.energy/data-portal/ngeso-open-licence). `data/raw/SHA256.json` records checksums for the exact files used. The generation CSV is a dated subset of the downloaded NESO file, filtered to the 2025–16 Oct 2026 UTC range.

## Analytical design

**Data model:** `mart_grid_interval` is one row per UTC half-hour, `mart_grid_day` is one row per local day, `forecast_backtest` is one row per forecasted interval, and `flexibility_scenario` is one row per complete scenario day. See [`sql/daily_mart.sql`](sql/daily_mart.sql).

**Forecast:** HistGradientBoostingRegressor predicts demand for interval *t* using demand at *t−1*, *t−2*, *t−48* and *t−336* plus calendar cycles. No future generation or carbon-intensity values enter the model. Train on 2025, validate on Jan–Jun 2026, and report the final Jul–16 Oct 2026 holdout. The persistence benchmark predicts *t* from *t−1*. Inputs are historical NESO actuals; the test emulates rolling 30-minute updates after data is observed, but it does not test real-time data availability. DST means 48 previous **UTC** intervals need not correspond to the same local clock time.

**Flexibility screen:** For each complete local day, compare average intensity across 18:00–22:00 with the mean of the two lowest daytime half-hours between 10:00–16:00. For an illustrative 1 MWh load shifted between these slots, the numeric g/kWh difference equals kg/MWh of *average-intensity-weighted exposure*. Daytime slots are selected with hindsight and therefore show retrospective potential, not a forecast or operating policy. Negative daily differences are retained. No price, marginal emissions, load profile, storage efficiency, congestion, or customer constraints are included.

## Quality controls and limitations

- Fail on duplicate settlement keys, duplicate UTC keys, missing demand, non-positive demand, missing UTC joins, and gaps in the half-hour demand timeline.
- Report source row counts, matched rows, missing intensity, date range, and unusual 46/50-period days in `results.json`.
- 2026 demand is partial; year-on-year annual totals would be misleading. Source files are a dated snapshot.
- [NESO historic demand](https://www.neso.energy/data-portal/historic-demand-data) is published with a lag and can be corrected retrospectively. [NESO generation mix](https://www.neso.energy/data-portal/historic-generation-mix) uses seasonal decomposition to correct irregular data and is subject to revision. Batteries and transmission solar currently sit in `OTHER`.
- **Average** grid carbon intensity is not the **marginal** response to an added or shifted MWh. The scenario cannot substantiate avoided emissions. Historical best slots are also not known ahead of time.
- No causal inference, electricity price forecast, uncertainty interval, or deployment monitoring is claimed.

## Further work before operational use

Add a carbon-intensity forecast available at decision time, marginal-emissions estimates, tariff and network constraints, a realistic asset schedule, prediction intervals, and live data freshness monitoring. Rebacktest with rolling retraining and a recent seasonal benchmark.

## Skills coverage for UK applications

| Competency | Evidence in this repository |
|---|---|
| SQL and data modelling | SQLite interval/day marts and SQL transformation |
| Python and ETL | Versioned pipeline, source harmonisation, typed calculations |
| Data quality and governance | Key, null, continuity and date-coverage checks; source limitations |
| Statistics/forecasting | Time-ordered split, baseline, MAE/RMSE/WAPE |
| BI and communication | Interactive Streamlit dashboard and decision framing |
| Domain judgement | Retrospective scenario labelled separately from real emissions impact |

Power BI, dbt, Azure/AWS and production orchestration appear in many UK roles but are **not evidenced** by this implementation. Add these through a subsequent, real extension before claiming them in a CV.

## CV wording

See [`CV_ENTRY.md`](CV_ENTRY.md) for a concise, verifiable project entry. Present this as an **independent portfolio project**, not employer experience.
