"""Merge prebuilt daily side-tables (DONKI, cyber, Ring of Fire/GeoNet) into data/eugene_env_daily.csv.gz (idempotent).
Side-table format: {'cols': [...], 'start': 'YYYY-MM-DD', 'd': {date: [values]}, optional 'zero_fill': [cols]}.
Columns in zero_fill (default: all) are filled with 0 on days >= start that have no record; others (e.g. daily max magnitude) stay blank."""
import json, os, pandas as pd
p = 'data/eugene_env_daily.csv.gz'; df = pd.read_csv(p)
for f in ('data/donki_daily.json', 'data/cyber_daily.json', 'data/ringfire_daily.json'):
    if not os.path.exists(f): continue
    j = json.load(open(f)); cols = j['cols']
    df = df.drop(columns=[c for c in cols if c in df])
    t = pd.DataFrame([[k, *v] for k, v in j['d'].items()], columns=['date', *cols])
    df = df.merge(t, on='date', how='left')
    m = df.date >= j['start']
    for c in j.get('zero_fill', cols): df.loc[m, c] = df.loc[m, c].fillna(0)
    print('merged', f, len(t))
df.to_csv(p, index=False, compression='gzip')
