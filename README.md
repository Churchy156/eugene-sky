# eugene-sky
Daily environmental dataset (1950→today) for Eugene, Oregon — weather, space weather, solar wind, quakes, moon/tides, rivers,
NWS alerts, air quality, BPA grid, power outages, markets — with an interactive dashboard and a plain-language daily outlook.

- **Site:** dashboard (`index.html`) + outlook (`outlook.html`), rebuilt every 3 h by GitHub Actions (`.github/workflows/update.yml`).
- **Data:** `data/eugene_env_daily.csv.gz` (one row per day); column descriptions in `column_dictionary.csv`.
- **Scripts:** `build*.py` / `finance.py` (one-time historical build from raw downloads, not in repo), `analyze.py`, `crash_model.py`,
  `update.py` (incremental), `make_dash.py`, `daily_report.py`, `render_outlook.py`.
- Historical-only columns (GOES flares to 2016, EPA PM2.5 to 2025, EAGLE-I outages to 2025, ODOT crashes to 2024) are not updated live.
- Statistical findings: solar/geomagnetic/lunar/quake variables show no useful relationship with Eugene weather or markets.
- Secrets: `TRIPCHECK_KEY` (repo secret, optional). Never committed.

## Sports games within 100 mi
`zip_tools/build_sports.py` keeps `data/sports_games_100mi.csv` (one row per game within 100 mi of Eugene, measured by haversine from 44.05N, -123.09W) and merges 13 daily columns into `data/eugene_env_daily.csv.gz`: `games_within_100mi`, `ducks_home_football`, `osu_home_football`, `major_home_game`, `ducks_home_mbb`, `osu_home_mbb`, `ducks_home_wbb`, `osu_home_wbb`, `milb_home_games`, `hayward_major_meet`, `football_attendance_100mi`, `est_attendance_100mi`, `football_kickoff_hour`. CI refreshes it from ESPN and MLB StatsAPI on every run; a failed refresh doesn't stop the run. To rebuild the full history from the raw caches, run `--history RAWDIR`. Correlations: `reports/incidents/sports_*`.

## GeoNet (NZ) + Pacific Ring of Fire
`zip_tools/build_ringfire.py` (stdlib only; live fetchers in `zip_tools/ringfire_core.py`) adds 14 daily columns back to 1950 via `data/ringfire_daily.json`: `nz_eq_M4plus`, `nz_eq_M5plus`, `nz_eq_maxmag` (GeoNet FDSN), `rof_eq_M5plus/M6plus/M7plus`, `rof_eq_maxmag` (USGS ComCat inside the Ring of Fire mask), `volc_erupting_global`, `volc_erupting_rof`, `volc_new_eruptions_rof` (Smithsonian GVP), `tsunami_events_global/rof`, `ncei_sig_eq_global/rof` (NOAA NCEI). Dates are Pacific-time calendar days. "Ring of Fire" = 1° cells within ~400 km of Pacific-rim subduction/convergent/transform boundaries in Bird (2003) PB2002 (`zip_src/data/rof_mask.json`). Caveats: USGS M5–6 counts are incomplete before ~1973; GVP adds new eruptions weeks late.
- CI: the 3-hourly run refreshes the last 60 days and writes the map snapshot `zip_src/data/ringfire.json`; the 10-minute relay writes `live/ringfire.json` (volcano alert levels from GeoNet, USGS HANS, JMA, PHIVOLCS, MAGMA Indonesia; BMKG quakes; PTWC/NTWC tsunami messages; GeoNet shaking intensity). Full history rebuild: `--history`; static layers: `--static`.
- World view (`/world/`): 10 toggles under Hazards (GeoNet quakes, volcano alert levels, Ring of Fire outline, plate boundaries, Pacific quakes, tsunami alerts, erupting volcanoes, NCEI tsunami history, BMKG quakes, GeoNet shaking) plus a "Ring of Fire now" panel. The daily outlook has a Ring of Fire section.
- Not used: SERNAGEOMIN Chile (times out for scripted clients) and the GVP weekly report (bot-check 403). MAGMA's JSON API needs a key, so the public HTML is parsed instead.
- Correlations (`reports/incidents/ringfire_*`, `analyze_ringfire.py`): 200 tests (8 predictors × 5 outcomes × lags 0/1/2/3/7 d), Poisson/OLS with weekday, month, year and holiday effects, weather controls, HAC errors and BH-FDR. **Nothing survives correction (smallest q = 0.15)**; 17 tests have p<0.05 where ~10 are expected by chance. A positive control (M7+ → aftershocks over the next 1–3 days, p<0.001) shows the method can find real lagged effects.

## Urgent alerts (every 30 min)
`zip_tools/alert_check.py` prints `NONE` or `ALERT <md> <html> <map png|->`. Thresholds are constants at the top: quakes M3.0+ ≤250 km / M4.5+ ≤500 km of Eugene, M7.0+ worldwide, M6.0+ Ring of Fire ≤2000 km of the Oregon coast; NOAA tsunami warning/advisory/watch for the West Coast or a Pacific tsunami warning; new outages of 50+ customers or a utility total over 200 (EWEB, Emerald PUD, Blachly-Lane, Pacific Power ≤45 mi) with short "restored" follow-ups; any new or upgraded NWS alert for Lane County / the Eugene point. Dedupe state: `/workspace/eugene-env/data/alert_state.json` (keys expire after 7 days); log: `data/alert_check.log`. A failed feed is logged and skipped, never alerted. `--seed` re-seeds silently, `--test` writes a sample alert.
