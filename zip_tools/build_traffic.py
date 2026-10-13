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
    r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 eugene-sky', 'Accept-Encoding': 'gzip', **(h or {})}), timeout=45).read()
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
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
for st, v in D.items(): json.dump({'built': now, **v}, open(f'{OUT}/{st}.json', 'w'), separators=(',', ':'))
json.dump({'built': now, 'states': {s: {k: sorted(v) for k, v in c.items()} for s, c in COV.items()},
           'counts': {s: {k: len(v[k]) for k in v} for s, v in D.items()}}, open(f'{OUT}/coverage.json', 'w'), indent=0)
print('traffic states', sorted(D))
