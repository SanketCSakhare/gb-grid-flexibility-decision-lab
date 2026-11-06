"""Run: streamlit run app.py"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "processed" / "grid_lab.sqlite"
RESULTS = ROOT / "data" / "processed" / "results.json"

st.set_page_config(page_title="GB Grid Flexibility Decision Lab", layout="wide")
st.title("GB Grid Flexibility Decision Lab")
st.caption("NESO open data · 2025–16 Oct 2026 · historical analysis, offline forecast backtest")


@st.cache_data
def load():
    with sqlite3.connect(DB) as con:
        daily = pd.read_sql_query("SELECT * FROM mart_grid_day ORDER BY local_date", con)
        flex = pd.read_sql_query("SELECT * FROM flexibility_scenario ORDER BY local_date", con)
        forecast = pd.read_sql_query("SELECT * FROM forecast_backtest WHERE split='test' ORDER BY timestamp_utc", con)
        interval = pd.read_sql_query("SELECT local_date, local_hour, carbon_intensity_g_kwh, national_demand_mw, renewable_pct FROM mart_grid_interval", con)
    return daily, flex, forecast, interval, json.loads(RESULTS.read_text(encoding="utf-8"))


daily, flex, forecast, interval, results = load()
min_date, max_date = pd.to_datetime(daily.local_date.min()).date(), pd.to_datetime(daily.local_date.max()).date()
date_range = st.sidebar.date_input("Date range", (min_date, max_date), min_value=min_date, max_value=max_date)
if len(date_range) != 2:
    st.stop()
start, end = (d.isoformat() for d in date_range)
d = daily[daily.local_date.between(start, end)]
f = flex[flex.local_date.between(start, end)]
i = interval[interval.local_date.between(start, end)]
if d.empty:
    st.warning("No data in this range.")
    st.stop()

st.info("Decision question: when did lower average grid intensity coincide with demand, and how well can near-term demand be forecast from historical intervals?")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Days", f"{len(d):,}")
k2.metric("Mean carbon intensity", f"{d.mean_carbon_intensity_g_kwh.mean():.0f} gCO₂/kWh")
k3.metric("Peak national demand", f"{d.peak_demand_mw.max():,.0f} MW")
k4.metric("Lower-intensity daytime days", f"{100*f.daytime_lower.mean():.1f}%" if len(f) else "n/a")

tab1, tab2, tab3 = st.tabs(["Grid trends", "Flexibility scenario", "Forecast & quality"])
with tab1:
    st.subheader("Demand and grid intensity over time")
    st.line_chart(d.set_index("local_date")[["national_demand_mwh"]], y_label="MWh per day")
    st.line_chart(d.set_index("local_date")[["mean_carbon_intensity_g_kwh"]], y_label="gCO₂/kWh")
    st.subheader("Intraday pattern in selected dates")
    hourly = i.groupby("local_hour", as_index=False).agg(
        national_demand_mw=("national_demand_mw", "mean"),
        carbon_intensity_g_kwh=("carbon_intensity_g_kwh", "mean"))
    c1, c2 = st.columns(2)
    c1.line_chart(hourly.set_index("local_hour")[["national_demand_mw"]], y_label="MW")
    c2.line_chart(hourly.set_index("local_hour")[["carbon_intensity_g_kwh"]], y_label="gCO₂/kWh")
with tab2:
    st.subheader("Illustrative 1 MWh per day load-shifting screen")
    st.write("Compare the mean 18:00–22:00 local intensity with the two lowest 30-minute intervals from 10:00–16:00 on the same day. The destination is chosen with hindsight, so this is an opportunity screen, not an achievable operational strategy.")
    if not f.empty:
        st.line_chart(f.set_index("local_date")[["exposure_delta_kg_per_mwh"]], y_label="kg per MWh")
        st.dataframe(f.sort_values("exposure_delta_kg_per_mwh", ascending=False).head(20), hide_index=True)
    st.warning("National average intensity is not marginal emissions. These differences do not establish avoided CO₂ or financial savings; no electricity price or asset constraints are modelled.")
with tab3:
    test = results["forecast"]["test"]
    c1, c2 = st.columns(2)
    c1.metric("Model test MAE", f"{test['model']['mae_mw']:,.0f} MW")
    c2.metric("Persistence test MAE", f"{test['persistence']['mae_mw']:,.0f} MW")
    st.write("Train: 2025 · validation: Jan–Jun 2026 · untouched test: Jul–16 Oct 2026. Forecast each interval 30 minutes ahead using only previous demand and calendar features.")
    chart = forecast.tail(7 * 48).copy()
    chart["timestamp_utc"] = pd.to_datetime(chart.timestamp_utc)
    st.line_chart(chart.set_index("timestamp_utc")[["national_demand_mw", "model_mw", "persistence_mw"]], y_label="MW")
    st.json(results["quality"])
    st.caption("NESO demand has an approximately 21-day publication lag and may be revised. Generation mix is also revised and quality-corrected. The dashboard is analytical, not a live dispatch tool.")

st.markdown("Sources: [NESO historic demand](https://www.neso.energy/data-portal/historic-demand-data) · [NESO generation mix](https://www.neso.energy/data-portal/historic-generation-mix) · [Methodology](README.md)")
