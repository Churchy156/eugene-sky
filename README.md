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
