"""GeoNet (NZ) + Pacific 'Ring of Fire' builder.
  --static        rebuild zip_src/data/rof_mask.json, plates_rof.json, volcano_coords.json (from PB2002 + GVP; rarely needed)
  --history       full daily rebuild 1950->today into data/ringfire_daily.json (USGS ComCat yearly M5+, GeoNet FDSN M4+, GVP, NCEI)
  (default, CI)   refresh the last ~60 days of data/ringfire_daily.json and write zip_src/data/ringfire.json (map snapshot + NCEI history)
  --live OUTDIR   write OUTDIR/live/ringfire.json for the 10-minute relay (tsunami.gov has no CORS)
Daily dates are America/Los_Angeles calendar days (to line up with the Eugene dataset)."""
import os, sys, io, csv, json, math, time, datetime as dt
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ringfire_core as rc
PT = ZoneInfo('America/Los_Angeles'); UTC = dt.timezone.utc
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DAILY = os.path.join(ROOT, 'data', 'ringfire_daily.json'); ZD = os.path.join(ROOT, 'zip_src', 'data')
RAW = os.environ.get('RINGFIRE_RAW', '/workspace/eugene-env/raw/ringfire')
NZ_BOX = (-49.0, -32.0, 164.0, 180.0)   # NZ mainland + near offshore (excludes Kermadecs north of 32S)
COLS = ['nz_eq_M4plus', 'nz_eq_M5plus', 'nz_eq_maxmag', 'rof_eq_M5plus', 'rof_eq_M6plus', 'rof_eq_M7plus', 'rof_eq_maxmag',
        'volc_erupting_global', 'volc_erupting_rof', 'volc_new_eruptions_rof', 'tsunami_events_global', 'tsunami_events_rof',
        'ncei_sig_eq_global', 'ncei_sig_eq_rof']
MAXCOLS = {'nz_eq_maxmag', 'rof_eq_maxmag'}   # NaN (not 0) on days with no qualifying quake
START = '1950-01-01'
def ptday(t):  # ISO UTC string -> PT date string
    return dt.datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(PT).date().isoformat()

# ---------------- static ----------------
def build_static():
    import numpy as np
    s = json.load(open(f'{RAW}/pb_steps.json'))['features']
    EXC = {'IN', 'BU', 'SC', 'SW', 'AF', 'AR', 'EU', 'GP', 'EA', 'JZ'}; BAD = {frozenset(('AM', 'YA')), frozenset(('YA', 'SU'))}
    def keep(p):
        if p['STEPCLASS'] not in ('SUB', 'OCB', 'CTF'): return False
        a, b = p['PLATEBOUND'][:2], p['PLATEBOUND'][3:5]
        lon = (p['STARTLONG'] + p['FINALLONG']) / 2; lat = (p['STARTLAT'] + p['FINALLAT']) / 2
        if not (lon >= 95 or lon <= -68) or not (-62 <= lat <= 66): return False
        if lat > 59 and 100 < lon < 170: return False       # NE Siberia interior (Chersky) is not 'Ring of Fire'
        if a in EXC or b in EXC or frozenset((a, b)) in BAD: return False
        if 'CA' in (a, b) and 'CO' not in (a, b): return False
        if 'AN' in (a, b) and 'SA' not in (a, b): return False
        return True
    k = [f for f in s if keep(f['properties'])]
    pts = np.array([c for f in k for c in f['geometry']['coordinates']]); la = np.radians(pts[:, 1]); lo = np.radians(pts[:, 0])
    P = np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]; cells = []
    for lat in range(-70, 75):
        for lon in range(-180, 180):
            a, o = math.radians(lat + .5), math.radians(lon + .5)
            v = np.array([math.cos(a) * math.cos(o), math.cos(a) * math.sin(o), math.sin(a)])
            if 6371 * np.arccos(np.clip(P @ v, -1, 1)).min() <= 400: cells.append([lat, lon])
    os.makedirs(ZD, exist_ok=True)
    json.dump({'note': '1-degree cells [floor(lat),floor(lon)] whose centre is within ~400 km of PB2002 (Bird 2003) subduction/convergent/continental-transform steps on the Pacific rim. Approximate Ring of Fire.', 'res': 1, 'cells': cells},
              open(f'{ZD}/rof_mask.json', 'w'), separators=(',', ':'))
    # ring outline: chain step endpoints into polylines
    segs = [[[round(f['properties']['STARTLAT'], 2), round(f['properties']['STARTLONG'], 2)], [round(f['properties']['FINALLAT'], 2), round(f['properties']['FINALLONG'], 2)], f['properties']['STEPCLASS']] for f in k]
    lines = []
    for a, b, c in segs:
        if lines and lines[-1]['p'][-1] == a and lines[-1]['c'] == c: lines[-1]['p'].append(b)
        else: lines.append({'c': c, 'p': [a, b]})
    bnd = json.load(open(f'{RAW}/pb_boundaries.json'))['features']; plates = []
    for f in bnd:
        cs = f['geometry']['coordinates']; step = max(1, len(cs) // 60)
        plates.append({'n': f['properties']['Name'], 't': f['properties'].get('Type') or '', 'p': [[round(y, 2), round(x, 2)] for x, y in cs[::step] + ([cs[-1]] if (len(cs) - 1) % step else [])]})
    json.dump({'src': 'PB2002 plate boundaries (Bird 2003, via github.com/fraxen/tectonicplates)', 'ring': lines, 'plates': plates}, open(f'{ZD}/plates_rof.json', 'w'), separators=(',', ':'))
    vs = json.load(open(f'{RAW}/gvp_volcanoes.json'))['features']; by_num, by_name = {}, {}
    for f in vs:
        p = f['properties']; d = {'name': p['Volcano_Name'], 'lat': p['Latitude'], 'lon': p['Longitude'], 'country': p['Country']}
        by_num[str(p['Volcano_Number'])] = d
        if p['Country'] in ('Indonesia',): by_name.setdefault(rc._norm(p['Volcano_Name'].split(',')[0].replace('Lewotobi', 'Lewotobi')), d)
    for alias, real in (('anakkrakatau', 'krakatau'), ('lewotobilakilaki', 'lewotobi'), ('lewotobiperempuan', 'lewotobi')):
        if real in by_name: by_name[alias] = by_name[real]
    json.dump({'src': 'Smithsonian GVP Holocene volcanoes (GeoServer WFS)', 'by_num': by_num, 'by_name': by_name}, open(f'{ZD}/volcano_coords.json', 'w'), separators=(',', ':'))
    print('static: mask cells', len(cells), 'ring lines', len(lines), 'plates', len(plates), 'volcanoes', len(by_num))

# ---------------- history pieces ----------------
def usgs_m5(t0, t1):
    txt = rc.get('https://earthquake.usgs.gov/fdsnws/event/1/query', t=180, params=dict(format='csv', starttime=t0, endtime=t1, minmagnitude=5, eventtype='earthquake', orderby='time-asc'))
    return [(r['time'], float(r['latitude']), float(r['longitude']), float(r['mag'] or 0)) for r in csv.DictReader(io.StringIO(txt))]
def geonet_m4(t0, t1):
    txt = rc.get('https://service.geonet.org.nz/fdsnws/event/1/query', t=180, params=dict(starttime=t0, endtime=t1, minmagnitude=4, format='text'))
    out = []
    for ln in txt.splitlines():
        if ln.startswith('#') or not ln.strip(): continue
        f = ln.split('|')
        if len(f) < 11 or (len(f) > 13 and f[13].strip() not in ('earthquake', '')): continue
        try: out.append((f[1] + 'Z', float(f[2]), float(f[3]), float(f[10])))
        except ValueError: pass
    return out
def in_nz(lat, lon): return NZ_BOX[0] <= lat <= NZ_BOX[1] and NZ_BOX[2] <= (lon % 360) <= NZ_BOX[3]
def ncei(kind, min_year):
    out, page = [], 1
    while True:
        j = rc.getj(f'https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/{kind}', t=120, params=dict(minYear=min_year, page=page))
        out += j.get('items', [])
        if page >= (j.get('totalPages') or 1): break
        page += 1
    return out
def ncei_day(e):
    y, m, d = e.get('year'), e.get('month'), e.get('day')
    if not (y and m and d) or y < 1949: return None
    try:
        t = dt.datetime(y, m, d, int(e.get('hour') or 12), int(e.get('minute') or 0), tzinfo=UTC)
        return t.astimezone(PT).date().isoformat() if e.get('hour') is not None else dt.date(y, m, d).isoformat()
    except ValueError: return None
_GVP = {}
def gvp_eruptions(holo=False):
    """(volcano_number, name, lat, lon, start_date, end_date) intervals covering 1950->today."""
    B = 'https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application/json&typeName=GVP-VOTW:'
    def load(name, fn):
        p = f'{RAW}/{fn}'
        try:
            j = json.loads(rc.get(B + name, t=300)); os.makedirs(RAW, exist_ok=True); json.dump(j, open(p, 'w')); return j
        except Exception as e:
            print('gvp fetch failed, using cache', name, e); return json.load(open(p))
    if holo in _GVP: return _GVP[holo]
    today = dt.datetime.now(PT).date()
    def mk(y, m, d, end=False):
        if not y: return None
        m = m or (12 if end else 1); d = d or (28 if end else 1)
        try: return dt.date(int(y), int(m), int(d))
        except ValueError: return dt.date(int(y), int(m), 28)
    E = load('E3WebApp_Eruptions1960', 'gvp_e1960.json')['features']; out, ids = [], set()
    for f in E:
        p = f['properties']; ids.add(p['Activity_ID'])
        s = mk(p['StartDateYear'], p['StartDateMonth'], p['StartDateDay'])
        e = today if p['ContinuingEruption'] == 'True' else (mk(p['EndDateYear'], p['EndDateMonth'], p['EndDateDay'], True) or s)
        if s: out.append((p['VolcanoNumber'], p['VolcanoName'], p['LatitudeDecimal'], p['LongitudeDecimal'], s, max(s, e)))
    coords = json.load(open(f'{ZD}/volcano_coords.json'))['by_num']
    H = []
    if holo:
        try: H = load('Smithsonian_VOTW_Holocene_Eruptions', 'gvp_holo_eruptions.json')['features']
        except Exception: H = []
    for f in H:   # 1950s eruptions that ended before 1960 (not in the 1960+ table)
        p = f['properties']
        if p.get('Eruption_Number') in ids or 'Confirmed' not in (p.get('Activity_Type') or 'Confirmed'): continue
        sy, ey = p.get('StartDateYear'), p.get('EndDateYear') or p.get('StartDateYear')
        if not sy or sy < 1900 or not (1950 <= (ey or 0) <= 1960): continue
        s = mk(sy, p.get('StartDateMonth'), p.get('StartDateDay')); e = mk(ey, p.get('EndDateMonth'), p.get('EndDateDay'), True) or s
        c = coords.get(str(p['Volcano_Number']), {})
        if s and c: out.append((p['Volcano_Number'], p['Volcano_Name'], c['lat'], c['lon'], s, max(s, e)))
    _GVP[holo] = out
    return out

def blank(): return [0] * len(COLS)
def fill(D, d0, d1, usgs=None, nz=None, erup=None, ts=None, sig=None):
    """Recompute days d0..d1 (inclusive ISO strings) in D for the supplied event lists."""
    days = [ (dt.date.fromisoformat(d0) + dt.timedelta(i)).isoformat() for i in range((dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days + 1)]
    ix = {c: i for i, c in enumerate(COLS)}
    for d in days: D.setdefault(d, blank())
    def reset(cols):
        for d in days:
            for c in cols: D[d][ix[c]] = None if c in MAXCOLS else 0
    def bump(d, c, v=1):
        if d in D and d0 <= d <= d1: D[d][ix[c]] += v
    def mx(d, c, m):
        if d in D and d0 <= d <= d1: D[d][ix[c]] = m if D[d][ix[c]] is None else max(D[d][ix[c]], m)
    if usgs is not None:
        reset(['rof_eq_M5plus', 'rof_eq_M6plus', 'rof_eq_M7plus', 'rof_eq_maxmag'])
        for t, la, lo, m in usgs:
            if not rc.in_rof(la, lo): continue
            d = ptday(t); bump(d, 'rof_eq_M5plus'); mx(d, 'rof_eq_maxmag', m)
            if m >= 6: bump(d, 'rof_eq_M6plus')
            if m >= 7: bump(d, 'rof_eq_M7plus')
    if nz is not None:
        reset(['nz_eq_M4plus', 'nz_eq_M5plus', 'nz_eq_maxmag'])
        for t, la, lo, m in nz:
            if not in_nz(la, lo) or m < 4: continue
            d = ptday(t); bump(d, 'nz_eq_M4plus'); mx(d, 'nz_eq_maxmag', m)
            if m >= 5: bump(d, 'nz_eq_M5plus')
    if erup is not None:
        reset(['volc_erupting_global', 'volc_erupting_rof', 'volc_new_eruptions_rof'])
        a, b = dt.date.fromisoformat(d0), dt.date.fromisoformat(d1)
        active = {}   # day -> set of volcano numbers (a volcano with overlapping eruption records counts once)
        for vn, nm, la, lo, s, e in erup:
            rof = rc.in_rof(la, lo)
            if a <= s <= b and rof: bump(s.isoformat(), 'volc_new_eruptions_rof')
            x, y = max(s, a), min(e, b)
            for i in range((y - x).days + 1):
                active.setdefault((x + dt.timedelta(i)).isoformat(), {})[vn] = rof
        for d, vs in active.items():
            D[d][ix['volc_erupting_global']] = len(vs); D[d][ix['volc_erupting_rof']] = sum(vs.values())
    if ts is not None:
        reset(['tsunami_events_global', 'tsunami_events_rof'])
        for e in ts:
            if (e.get('eventValidity') or 0) < 3: continue
            d = ncei_day(e)
            if not d: continue
            bump(d, 'tsunami_events_global')
            if rc.in_rof(e.get('latitude'), e.get('longitude')): bump(d, 'tsunami_events_rof')
    if sig is not None:
        reset(['ncei_sig_eq_global', 'ncei_sig_eq_rof'])
        for e in sig:
            d = ncei_day(e)
            if not d: continue
            bump(d, 'ncei_sig_eq_global')
            if rc.in_rof(e.get('latitude'), e.get('longitude')): bump(d, 'ncei_sig_eq_rof')

def save(D, meta):
    D = {k: [None if v is None else (round(v, 1) if isinstance(v, float) else v) for v in D[k]] for k in sorted(D)}
    json.dump({'cols': COLS, 'start': START, 'zero_fill': [c for c in COLS if c not in MAXCOLS], 'meta': meta, 'd': D}, open(DAILY, 'w'), separators=(',', ':'))
    print('saved', DAILY, len(D), 'days')

def history():
    today = dt.datetime.now(PT).date(); D = {}; meta = {'built': dt.datetime.now(UTC).isoformat(timespec='seconds')}
    U = []
    for y in range(1949, today.year + 1):   # 1949-12-31 UTC events can be 1950 PT days
        for attempt in range(3):
            try: U += usgs_m5(f'{y}-01-01', f'{y + 1}-01-01'); break
            except Exception as e: print('usgs', y, e); time.sleep(5)
        print('usgs', y, len(U), flush=True)
    N = []
    for y in range(1949, today.year + 1, 5):
        for attempt in range(3):
            try: N += geonet_m4(f'{y}-01-01', f'{y + 5}-01-01'); break
            except Exception as e: print('geonet', y, e); time.sleep(5)
        print('geonet', y, len(N), flush=True)
    E = gvp_eruptions(holo=True); T = ncei('tsunamis/events', 1949); S = ncei('earthquakes', 1949)
    print('gvp', len(E), 'ncei ts', len(T), 'ncei sig eq', len(S))
    fill(D, START, today.isoformat(), U, N, E, T, S)
    meta.update(usgs_m5=len(U), geonet_m4=len(N), gvp_eruptions=len(E), ncei_tsunamis=len(T), ncei_sig_eq=len(S))
    save(D, meta)

def refresh(days=60):
    j = json.load(open(DAILY)); D = j['d']; meta = j.get('meta', {})
    today = dt.datetime.now(PT).date(); d0 = (today - dt.timedelta(days)).isoformat(); d1 = today.isoformat()
    t0 = (today - dt.timedelta(days + 1)).isoformat(); t1 = (today + dt.timedelta(2)).isoformat()
    kw = {}
    for k, fn in (('usgs', lambda: usgs_m5(t0, t1)), ('nz', lambda: geonet_m4(t0, t1)), ('erup', gvp_eruptions),
                  ('ts', lambda: ncei('tsunamis/events', today.year - 1)), ('sig', lambda: ncei('earthquakes', today.year - 1))):
        try: kw[k] = fn()
        except Exception as e: print('refresh', k, 'failed:', e)
    # NCEI/GVP: recompute only the refresh window (the API returns everything since last year; window-limited by fill)
    fill(D, d0, d1, **kw); meta['refreshed'] = dt.datetime.now(UTC).isoformat(timespec='seconds'); save(D, meta)

def map_snapshot():
    S = rc.snapshot(intensity=False)
    try:
        T = ncei('tsunamis/events', 1950)
        S['ncei_tsunamis'] = [dict(t=f"{e['year']:04d}-{e.get('month') or 1:02d}-{e.get('day') or 1:02d}", lat=e.get('latitude'), lon=e.get('longitude'),
                                   mag=e.get('eqMagnitude'), place=e.get('locationName'), country=e.get('country'), h=e.get('maxWaterHeight'),
                                   deaths=e.get('deathsTotal'), cause=e.get('causeCode'), id=e['id']) for e in T
                              if (e.get('eventValidity') or 0) >= 3 and e.get('latitude') is not None and e.get('longitude') is not None]
        S['status']['ncei_tsunamis'] = f"ok ({len(S['ncei_tsunamis'])})"
    except Exception as e: S['ncei_tsunamis'] = []; S['status']['ncei_tsunamis'] = f'failed: {e}'
    try:
        E = gvp_eruptions(); today = dt.datetime.now(PT).date()
        S['gvp_continuing'] = sorted({(vn, nm, la, lo, s.isoformat()) for vn, nm, la, lo, s, e in E if e >= today - dt.timedelta(1)}, key=lambda x: x[4])
        S['gvp_continuing'] = [dict(num=a, name=b, lat=c, lon=d, since=e, url=f'https://volcano.si.edu/volcano.cfm?vn={a}') for a, b, c, d, e in S['gvp_continuing']]
        S['status']['gvp_continuing'] = f"ok ({len(S['gvp_continuing'])})"
    except Exception as e: S['gvp_continuing'] = []; S['status']['gvp_continuing'] = f'failed: {e}'
    json.dump(S, open(f'{ZD}/ringfire.json', 'w'), separators=(',', ':')); print('snapshot', S['status'])

if __name__ == '__main__':
    a = sys.argv[1:]
    if '--static' in a: build_static()
    elif '--history' in a: history()
    elif '--live' in a:
        out = (a[a.index('--live') + 1] if len(a) > a.index('--live') + 1 else '/tmp/out') + '/live'; os.makedirs(out, exist_ok=True)
        S = rc.snapshot(intensity=True); json.dump(S, open(f'{out}/ringfire.json', 'w'), separators=(',', ':')); print('live', S['status'])
    else:
        try: refresh()
        except Exception as e: print('daily refresh failed:', e)
        map_snapshot()
