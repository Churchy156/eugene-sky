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
