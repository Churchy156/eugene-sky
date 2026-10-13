"""DONKI (CCMC, no key) space-weather events 2010+ (incremental) + NASA NeoWs (NASA_API_KEY) -> zip_src/data/donki.json,
and merges daily DONKI columns into data/eugene_env_daily.csv.gz."""
import json, os, urllib.request, datetime as dt, collections
OUT = 'zip_src/data/donki.json'; B = 'https://ccmc.gsfc.nasa.gov/DONKI-API/get/'
def get(u):
    err = None
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'eugene-sky'}), timeout=90).read() or b'[]')
        except Exception as e: err = e
    print('fail', u.split('api_key')[0], err); return None
old = json.load(open(OUT)) if os.path.exists(OUT) else {'ev': []}
today = dt.date.today(); start = dt.date(2010, 1, 1) if not old['ev'] else today - dt.timedelta(120)
ev = [e for e in old['ev'] if e[0] < str(start)]; d = start
while d <= today:
    e2 = min(d + dt.timedelta(59), today); q = f'startDate={d}&endDate={e2}'
    for e in get(B + 'FLR?' + q) or []:
        ev.append([(e.get('peakTime') or e['beginTime'])[:16], 'FLR', e.get('classType') or '', e.get('sourceLocation') or '', e.get('link', '')])
    for e in get(B + 'CME?' + q) or []:
        an = e.get('cmeAnalyses') or []; a = [x for x in an if x.get('isMostAccurate')] or an or [{}]
        sp = a[0].get('speed'); earth = any(en.get('estimatedShockArrivalTime') for x in an for en in (x.get('enlilList') or []))
        ev.append([e['startTime'][:16], 'CME', f"{int(sp)} km/s" if sp else '', 'Earth-directed' if earth else '', e.get('link', '')])
    for e in get(B + 'GST?' + q) or []:
        kp = max([k['kpIndex'] for k in e.get('allKpIndex') or []] or [0])
        ev.append([e['startTime'][:16], 'GST', f'Kp {kp:g}', '', e.get('link', '')])
    for e in get(B + 'SEP?' + q) or []: ev.append([e['eventTime'][:16], 'SEP', '', '', e.get('link', '')])
    for e in get(B + 'IPS?' + q) or []: ev.append([e['eventTime'][:16], 'IPS', e.get('location', ''), '', e.get('link', '')])
    d = e2 + dt.timedelta(1)
ev = sorted({tuple(x) for x in ev})
neo = []
k = os.environ.get('NASA_API_KEY') or (open('/workspace/eugene-env/.nasa_key').read().strip() if os.path.exists('/workspace/eugene-env/.nasa_key') else 'DEMO_KEY')
n = get(f'https://api.nasa.gov/neo/rest/v1/feed?start_date={today}&end_date={today + dt.timedelta(6)}&api_key={k}')
for day, L in (n or {}).get('near_earth_objects', {}).items():
    for o in L:
        ca = o['close_approach_data'][0]
        neo.append([day, o['name'], round(o['estimated_diameter']['meters']['estimated_diameter_max']), o['is_potentially_hazardous_asteroid'],
                    round(float(ca['miss_distance']['lunar']), 1), round(float(ca['relative_velocity']['kilometers_per_hour'])), o['nasa_jpl_url']])
neo.sort(key=lambda r: r[4])
json.dump({'built': dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'), 'ev': [list(x) for x in ev], 'neo': neo}, open(OUT, 'w'), separators=(',', ':'))
print('donki events', len(ev), 'neo', len(neo))
c = collections.defaultdict(collections.Counter)
for t, typ, a, b, _ in ev:
    day = t[:10]
    if typ == 'FLR' and a[:1] in ('M', 'X'): c[day]['donki_flr_MX'] += 1
    if typ == 'CME':
        c[day]['donki_cme'] += 1; c[day]['donki_cme_earth'] += bool(b)
        try: c[day]['donki_cme_max_kms'] = max(c[day]['donki_cme_max_kms'], int(a.split()[0]))
        except Exception: pass
    if typ in ('GST', 'SEP', 'IPS'): c[day]['donki_' + typ.lower()] += 1
cols = ['donki_flr_MX', 'donki_cme', 'donki_cme_earth', 'donki_cme_max_kms', 'donki_gst', 'donki_sep', 'donki_ips']
json.dump({'cols': cols, 'start': '2010-01-01', 'd': {k: [v[x] for x in cols] for k, v in c.items()}}, open('data/donki_daily.json', 'w'))
