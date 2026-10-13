"""One-time builder: FARS (1975+) and EAGLE-I (2014+) per-state shards for the ZIP dashboard.
Output: zip_src/data/{fars,eaglei}/<statefips>.json  as {county3: [delta_day, value, delta_day, value, ...]}
day = days since 1975-01-01 (FARS) / 2014-01-01 (EAGLE-I)."""
import zipfile, io, csv, glob, os, json, sys, collections, datetime as dt
FR = sys.argv[1]; EG = sys.argv[2]
def enc(d, base):
    out = {}
    for c, m in d.items():
        a = []; p = 0
        for day in sorted(m):
            i = (day - base).days; a += [i - p, m[day]]; p = i
        out[c] = a
    return out
def write(kind, data, base):
    os.makedirs(f'zip_src/data/{kind}', exist_ok=True)
    for s, d in data.items():
        json.dump({'base': str(base), 'c': enc(d, base)}, open(f'zip_src/data/{kind}/{s}.json', 'w'), separators=(',', ':'))
fars = collections.defaultdict(lambda: collections.defaultdict(collections.Counter)); last = 0
for z in sorted(glob.glob(f'{FR}/*.zip')):
    Z = zipfile.ZipFile(z); n = [x for x in Z.namelist() if x.lower().endswith('accident.csv')][0]
    for r in csv.DictReader(io.TextIOWrapper(Z.open(n), encoding='utf-8-sig', errors='replace')):
        r = {k.strip('\ufeff\xef\xbb\xbf" ').upper(): v for k, v in r.items()}
        try:
            y = int(r['YEAR']); y = y + 1900 if y < 100 else y
            d = dt.date(y, int(r['MONTH']), int(r['DAY']))
        except Exception: continue
        fars[f"{int(r['STATE']):02d}"][f"{int(r['COUNTY']):03d}"][d] += 1; last = max(last, y)
write('fars', fars, dt.date(1975, 1, 1)); print('fars through', last)
eg = collections.defaultdict(lambda: collections.defaultdict(dict))
for f in sorted(glob.glob(f'{EG}/d_*.csv')):
    for l in open(f):
        fips, d, v = l.rstrip().split(','); v = int(float(v))
        if v < 10 or not fips.isdigit(): continue
        fips = fips.zfill(5); d = dt.date.fromisoformat(d)
        m = eg[fips[:2]][fips[2:]]; m[d] = max(m.get(d, 0), v)
write('eaglei', eg, dt.date(2014, 1, 1)); print('eaglei done')
json.dump({'fars_last_year': last, 'eaglei_last': max(str(max(m)) for s in eg.values() for m in s.values())}, open('zip_src/data/meta.json', 'w'))
