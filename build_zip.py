"""Prebuild global JSON for the nationwide ZIP dashboard (site/zip/)."""
import json, os, urllib.request
import pandas as pd
import shutil
OUT = 'site/zip'; os.makedirs(OUT, exist_ok=True)
for f in ('index.html', 'radar.html', 'mapx.js', 'extra.js'): shutil.copy(f'zip_src/{f}', f'{OUT}/{f}')
shutil.copytree('zip_src/data', f'{OUT}/data', dirs_exist_ok=True)
import subprocess, sys
if not os.environ.get('SKIP_TRAFFIC'): subprocess.run([sys.executable, 'zip_tools/build_traffic.py', f'{OUT}/data'], check=False)
d = pd.read_csv('data/eugene_env_daily.csv.gz')
def dump(cols, name, start=None):
    x = d[['date'] + cols].copy()
    if start: x = x[x.date >= start]
    x = x.dropna(subset=cols, how='all')
    rec = {c: [None if pd.isna(v) else round(float(v), 4) for v in x[c]] for c in cols}
    rec['date'] = list(x.date)
    json.dump(rec, open(f'{OUT}/{name}', 'w'), separators=(',', ':'))
dump(['kp_max', 'sunspot_n', 'flares_M', 'flares_X', 'sw_speed_kms', 'eq_global_M6plus'], 'space.json')
dump(['fin_sp500_close', 'fin_dow_close', 'fin_nasdaq_comp', 'fin_gold_usd_oz', 'fin_fed_funds_pct',
      'fin_ust10y_pct', 'fin_dxy', 'fin_usd_per_eur', 'fin_jpy_per_usd'], 'markets.json')
try:
    s = json.load(urllib.request.urlopen(
        'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions', timeout=60))
    st = [[x['id'], x['name'], x.get('state', ''), round(x['lat'], 4), round(x['lng'], 4)] for x in s['stations']]
    json.dump(st, open(f'{OUT}/tide_stations.json', 'w'), separators=(',', ':'))
except Exception as e:
    print('tide station refresh failed (keeping old):', e)
m = {'tmax_F': 'temperature_2m_max', 'tmin_F': 'temperature_2m_min', 'prcp_in': 'precipitation_sum', 'snow_in': 'snowfall_sum',
     'wind_max_mph_era5': 'wind_speed_10m_max', 'pressure_msl_hPa_era5': 'pressure_msl_mean', 'rh_mean_pct_era5': 'relative_humidity_2m_mean', 'solar_rad_MJm2_era5': 'shortwave_radiation_sum'}
x = d[['date'] + list(m)].dropna(subset=['tmax_F', 'prcp_in'], how='all')
e = {'date': list(x.date)}
for k, v in m.items(): e[v] = [None if pd.isna(z) else round(float(z), 2) for z in x[k]]
json.dump(e, open(f'{OUT}/data/eugene_wx.json', 'w'), separators=(',', ':'))
print('zip prebuild done')
