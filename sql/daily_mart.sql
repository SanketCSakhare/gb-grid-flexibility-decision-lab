CREATE TABLE mart_grid_day AS
SELECT local_date,
       COUNT(*) AS intervals,
       ROUND(SUM(demand_mwh), 1) AS national_demand_mwh,
       ROUND(AVG(carbon_intensity_g_kwh), 1) AS mean_carbon_intensity_g_kwh,
       ROUND(MAX(national_demand_mw), 0) AS peak_demand_mw,
       ROUND(AVG(renewable_pct), 1) AS mean_renewable_pct,
       SUM(CASE WHEN carbon_intensity_g_kwh IS NULL THEN 1 ELSE 0 END) AS missing_intensity_intervals
FROM mart_grid_interval
GROUP BY local_date;
CREATE UNIQUE INDEX idx_day_date ON mart_grid_day(local_date);

