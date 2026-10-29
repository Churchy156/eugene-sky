"""Prebuild traffic cameras / incidents / work zones for the ZIP map (runs every 3 h in the workflow).
Keys stay server-side (TRIPCHECK_KEY env). Output: <out>/traffic/<ST>.json + coverage.json"""
import json, os, sys, re, gzip, urllib.request, datetime as dt, concurrent.futures as cf
OUT = (sys.argv[1] if len(sys.argv) > 1 else 'site/zip/data') + '/traffic'; os.makedirs(OUT, exist_ok=True)
K = os.environ.get('TRIPCHECK_KEY') or (open('/workspace/eugene-env/.tripcheck_key').read().strip() if os.path.exists('/workspace/eugene-env/.tripcheck_key') else '')
ST = dict(alabama='AL',alaska='AK',arizona='AZ',arkansas='AR',california='CA',colorado='CO',connecticut='CT',delaware='DE',florida='FL',georgia='GA',hawaii='HI',idaho='ID',illinois='IL',indiana='IN',iowa='IA',kansas='KS',kentucky='KY',louisiana='LA',maine='ME',maryland='MD',massachusetts='MA',michigan='MI',minnesota='MN',mississippi='MS',missouri='MO',montana='MT',nebraska='NE',nevada='NV',ohio='OH',oklahoma='OK',oregon='OR',pennsylvania='PA',tennessee='TN',texas='TX',utah='UT',vermont='VT',virginia='VA',washington='WA',wisconsin='WI',wyoming='WY',**{'new hampshire':'NH','new jersey':'NJ','new mexico':'NM','new york':'NY','north carolina':'NC','north dakota':'ND','rhode island':'RI','south carolina':'SC','south dakota':'SD','west virginia':'WV'})
D = {}; COV = {}
def add(st, kind, row, src):
    D.setdefault(st, {'cam': [], 'inc': [], 'wz': []})[kind].append(row)
    COV.setdefault(st, {}).setdefault(kind, set()).add(src)
def get(u, h=None, raw=False, n=3):
    for i in range(n):
        try: return _get(u, h, raw)
        except Exception:
            if i == n - 1: raise
def _get(u, h=None, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 eugene-sky', 'Accept-Encoding': 'gzip', **(h or {})}), timeout=int(os.environ.get("FEED_TIMEOUT","45"))).read()
    if r[:2] == b'\x1f\x8b': r = gzip.decompress(r)
    return r.decode('utf-8', 'replace') if raw else json.loads(r)
def first_pt(g):
    c = g.get('coordinates') if g else None
    while isinstance(c, list) and c and isinstance(c[0], list): c = c[0]
    return (round(c[1], 5), round(c[0], 5)) if c and len(c) >= 2 else None
def wzdx(st, url, src):
    j = get(url); n = 0
    for f in j.get('features', []):
        p = f.get('properties', {}); cd = p.get('core_details', p)
        pt = first_pt(f.get('geometry'))
        if not pt: continue
        rn = cd.get('road_names') or [cd.get('road_name', '')]
        add(st, 'wz', [*pt, ', '.join(map(str, rn))[:60], (cd.get('description') or '')[:200], (p.get('start_date') or '')[:10], (p.get('end_date') or '')[:10]], src); n += 1
    return n
jobs = []
try:
    reg = get('https://data.transportation.gov/resource/69qe-yiui.json?$limit=500')
    for r in reg:
        u = r.get('url'); u = u.get('url') if isinstance(u, dict) else u
        st = ST.get((r.get('state') or '').lower().strip())
        if not u or not st or r.get('needapikey') in (True, 'true') or re.search(r'INSERT|<key>|%3ckey|Your-API|apiKey=$|key=$', u, re.I): continue
        if r.get('active') in (False, 'false'): continue
        jobs.append((st, u, 'WZDx: ' + (r.get('issuingorganization') or r.get('feedname') or '')))
except Exception as e: print('registry failed', e)
if K: jobs.append(('OR', 'https://api.odot.state.or.us/WZDx/v4.0/Workzones', 'WZDx: ODOT', {'Ocp-Apim-Subscription-Key': K}))
def run(j):
    try:
        if len(j) == 4:

            jj = get(j[1], j[3]); n = 0
            for f in jj.get('features', []):
                p = f.get('properties', {}); cd = p.get('core_details', p); pt = first_pt(f.get('geometry'))
                if pt: add(j[0], 'wz', [*pt, ', '.join(map(str, cd.get('road_names') or ['']))[:60], (cd.get('description') or '')[:200], (p.get('start_date') or '')[:10], (p.get('end_date') or '')[:10]], j[2]); n += 1
            return j[2], n
        return j[2], wzdx(*j)
    except Exception as e: return j[2], 'ERR ' + str(e)[:60]
with cf.ThreadPoolExecutor(10) as ex:
    for s, n in ex.map(run, jobs): print(s, n)
if K:
    h = {'Ocp-Apim-Subscription-Key': K}
    try:
        for c in get('https://api.odot.state.or.us/tripcheck/Cctv/Inventory', h)['CCTVInventoryRequest']:
            add('OR', 'cam', [round(c['latitude'], 5), round(c['longitude'], 5), c['device-name'], c['cctv-url'].replace('http://', 'https://')], 'ODOT TripCheck')
        for i in get('https://api.odot.state.or.us/tripcheck/Incidents', h)['incidents']:
            s = i['location'].get('start-location', {})
            if s.get('start-lat'): add('OR', 'inc', [round(s['start-lat'], 5), round(s['start-long'], 5), i['location'].get('route-id', ''), (i.get('headline') or '')[:200], i.get('update-time', '')[:16]], 'ODOT TripCheck')
    except Exception as e: print('tripcheck', e)
def ca(dn):
    try:
        for x in get(f'https://cwwp2.dot.ca.gov/data/d{dn}/cctv/cctvStatusD{dn:02d}.json')['data']:
            c = x['cctv']; l = c['location']; u = c['imageData']['static'].get('currentImageURL')
            if c.get('inService') == 'false' or not u: continue
            add('CA', 'cam', [round(float(l['latitude']), 5), round(float(l['longitude']), 5), l['locationName'][:80], u], 'Caltrans CWWP2')
    except Exception as e: print('caltrans', dn, e)
with cf.ThreadPoolExecutor(6) as ex: list(ex.map(ca, range(1, 13)))
try:
    x = get('https://media.chp.ca.gov/sa_xml/sa.xml', raw=True)
    for m in re.finditer(r'<Log ID.*?</Log>', x, re.S):
        b = m.group(0); g = lambda t: (re.search(f'<{t}>"?(.*?)"?</{t}>', b, re.S) or [None, ''])[1]
        ll = g('LATLON')
        if ':' in ll and ll != '0:0':
            a, o = ll.split(':'); add('CA', 'inc', [int(a) / 1e6, -int(o) / 1e6, g('Location')[:60], g('LogType') + ' — ' + g('LocationDesc'), g('LogTime')], 'CHP CAD')
except Exception as e: print('chp', e)
# ---- Keyless state camera lists (public map/open-data endpoints, fetched once per run = every 10 min) ----
def arcgis(url, page):
    """Page through a public ArcGIS FeatureServer layer as GeoJSON (WGS84)."""
    out, off = [], 0
    while off < 20000:
        j = get(f'{url}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson&resultRecordCount={page}&resultOffset={off}')
        fs = j.get('features', []); out += fs
        if not fs or (len(fs) < page and not j.get('exceededTransferLimit') and not (j.get('properties') or {}).get('exceededTransferLimit')): break
        off += len(fs)
    return out
def pt(f):
    c = (f.get('geometry') or {}).get('coordinates')
    return (round(c[1], 5), round(c[0], 5)) if c and len(c) >= 2 and c[0] and c[1] else None
def cams_wa():  # WSDOT TravelInfo cameras (public ArcGIS layer used by the WSDOT travel map)
    n = 0
    for f in arcgis('https://data.wsdot.wa.gov/arcgis/rest/services/TravelInformation/TravelInfoCamerasWeather/FeatureServer/0', 2000):
        p, q = f.get('properties') or {}, pt(f); u = (p.get('ImageURL') or '').strip()
        if q and u.startswith('http'): add('WA', 'cam', [*q, (p.get('CameraTitle') or '')[:80], u.replace('http://', 'https://')], 'WSDOT cameras (ArcGIS)'); n += 1
    return n
def cams_il():  # IDOT open data: Illinois Gateway / Travel Midwest snapshots (CC BY-SA 2.0)
    n = 0
    for f in arcgis('https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/TrafficCamerasTM_Public/FeatureServer/0', 1000):
        p, q = f.get('properties') or {}, pt(f); u = (p.get('SnapShot') or '').strip()
        if not q and p.get('y'): q = (round(float(p['y']), 5), round(float(p['x']), 5))
        if q and u.startswith('http') and str(p.get('TooOld')).lower() != 'true':
            d = (p.get('CameraDirection') or '').strip()
            add('IL', 'cam', [*q, ((p.get('CameraLocation') or '') + (f' ({d})' if d and d != 'NONE' else ''))[:80], u], 'IDOT Gateway / Travel Midwest (CC BY-SA)'); n += 1
    return n
def cams_nd():  # NDDOT cameras.json: ETL use only per its terms, so only this 10-min copy reads it, never the browser
    n = 0
    for f in get('https://travelfiles.dot.nd.gov/geojson_nc/cameras.json').get('features', []):
        p, q = f.get('properties') or {}, pt(f)
        if not q: continue
        cs = [c for c in (p.get('Cameras') or []) if (c.get('FullPath') or '').strip().startswith('http')]
        road = [c for c in cs if not re.search(r'pavement|surface|sensor', c.get('Description') or '', re.I)] or cs
        if road:
            c = road[0]; d = (c.get('Direction') or '').strip()
            nm = str(p.get('Name') or p.get('Description') or p.get('LocationName') or c.get('Description') or 'ND camera').strip()
            add('ND', 'cam', [*q, (nm + (f' ({d})' if d and d not in nm else ''))[:80], c['FullPath'].strip().replace(' ', '%20')], 'NDDOT travel info (provided as-is)'); n += 1
    return n
def cams_keyed(st, env, url):  # 511 sites needing a free developer key; skipped until the secret exists
    k = os.environ.get(env)
    if not k: return 'no key (' + env + ')'
    n = 0
    for c in get(url + k):
        try:
            v = (c.get('Views') or [{}])[0]; u = (v.get('Url') or c.get('Url') or '').strip()
            if u and c.get('Latitude') and str(v.get('Status', 'Enabled')).lower() != 'disabled':
                add(st, 'cam', [round(float(c['Latitude']), 5), round(float(c['Longitude']), 5), (c.get('Location') or c.get('Name') or '')[:80], u], st + ' 511 API'); n += 1
        except Exception: pass
    return n
CAMJOBS = [('WA', cams_wa), ('IL', cams_il), ('ND', cams_nd),
           ('WI', lambda: cams_keyed('WI', 'WI511_KEY', 'https://511wi.gov/api/v2/get/cameras?format=json&key=')),
           ('ID', lambda: cams_keyed('ID', 'ID511_KEY', 'https://511.idaho.gov/api/v2/get/cameras?format=json&key='))]
def camrun(j):
    try: return j[0], j[1]()
    except Exception as e: return j[0], 'ERR ' + str(e)[:80]
with cf.ThreadPoolExecutor(5) as ex:
    for s, n in ex.map(camrun, CAMJOBS): print('cams', s, n)
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
for st, v in D.items(): json.dump({'built': now, **v}, open(f'{OUT}/{st}.json', 'w'), separators=(',', ':'))
json.dump({'built': now, 'states': {s: {k: sorted(v) for k, v in c.items()} for s, c in COV.items()},
           'counts': {s: {k: len(v[k]) for k in v} for s, v in D.items()}}, open(f'{OUT}/coverage.json', 'w'), indent=0)
print('traffic states', sorted(D))
