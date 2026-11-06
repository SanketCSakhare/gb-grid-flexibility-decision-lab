## CV project entry — use after you have reviewed the code and dashboard

**GB Grid Flexibility Decision Lab | Independent portfolio project | Python, SQL, Streamlit, scikit-learn**

- Built a reproducible data pipeline and SQLite analytical mart joining 31,390 half-hourly GB demand observations to NESO generation carbon-intensity data, with UTC/DST handling and checks for duplicate keys, gaps and missing joins.
- Developed a 30-minute-ahead demand forecasting backtest using temporal train/validation/test splits; achieved **294 MW MAE on the held-out Jul–Oct 2026 period**, compared with **620 MW** for a persistence baseline.
- Delivered an interactive dashboard and a historical flexible-load scenario screen, explicitly distinguishing average-intensity exposure from causal emissions savings.

**Interview explanation:** I chose a live UK energy transition problem, sourced open NESO data, documented its publication lag and revisions, built the data model and baseline-led forecast, then translated findings into a bounded decision screen. This was a self-directed project; I did not deploy it into grid operations.

**Skills evidenced by the project:** Python/pandas, SQL/SQLite, data modelling, ETL, source assessment, quality assurance, time-series backtesting, statistical metrics, dashboard design, stakeholder communication, reproducibility, and limitations/governance. Power BI, dbt and cloud platforms are common in UK vacancies but are **not** claimed here because this project does not use them.
