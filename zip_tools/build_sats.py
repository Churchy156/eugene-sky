"""Cache CelesTrak GP (OMM JSON) groups to the live branch, respecting CelesTrak's ~1 fetch / 2 h / group.
Reuses the previous copy from the live branch when it is < 2 h old."""
import json, os, sys, time, urllib.request
out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/out'; os.makedirs(f'{out}/sats', exist_ok=True)
GROUPS = ['starlink', 'stations', 'gps-ops', 'glo-ops', 'galileo', 'beidou', 'weather', 'goes', 'visual']
RAW = 'https://raw.githubusercontent.com/Churchy156/eugene-sky/live/sats/'
def get(u, t=60):
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'eugene-sky (github.com/Churchy156/eugene-sky)'}), timeout=t).read()
try: meta = json.loads(get(RAW + 'meta.json', 20))
except Exception: meta = {}
now = time.time()
for g in GROUPS:
    m = meta.get(g, {}); data = None
    if now - m.get('t', 0) < 7200:
        try: data = get(RAW + g + '.json'); json.loads(data)
        except Exception: data = None
    if data is None:
        try:
            data = get(f'https://celestrak.org/NORAD/elements/gp.php?GROUP={g}&FORMAT=json', 120)
            j = json.loads(data); assert isinstance(j, list) and j
            keep = ['OBJECT_NAME','NORAD_CAT_ID','EPOCH','MEAN_MOTION','ECCENTRICITY','INCLINATION','RA_OF_ASC_NODE','ARG_OF_PERICENTER','MEAN_ANOMALY','BSTAR','MEAN_MOTION_DOT','MEAN_MOTION_DDOT','EPHEMERIS_TYPE','CLASSIFICATION_TYPE','ELEMENT_SET_NO','REV_AT_EPOCH','OBJECT_ID']
            data = json.dumps([{k: o.get(k) for k in keep} for o in j], separators=(',', ':')).encode()
            m = {'t': now, 'n': len(j)}; print(g, 'fetched', len(j))
        except Exception as e:
            print(g, 'fetch failed', e)
            try: data = get(RAW + g + '.json')
            except Exception: continue
    else: print(g, 'reused', m.get('n'))
    open(f'{out}/sats/{g}.json', 'wb').write(data); meta[g] = m
json.dump(meta, open(f'{out}/sats/meta.json', 'w'))
