"""Shared fetchers for GeoNet (NZ) + Pacific 'Ring of Fire' sources. Stdlib only, so the box daily report,
the 3-hourly CI build and the 10-minute live relay can all import it. Every fetcher raises on failure; callers
wrap them so one dead source never breaks the rest.

Ring of Fire mask: 1-degree cells whose centre is within ~400 km of a PB2002 (Bird 2003) subduction /
convergent / continental-transform plate-boundary step around the Pacific rim (see build_ringfire.py --static).
It is an approximation for classifying quake epicentres, not an official boundary."""
import os, re, json, html, urllib.request, urllib.parse, datetime as dt
UTC = dt.timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
UA = {'User-Agent': 'eugene-sky ringfire (personal research; github.com/Churchy156/eugene-sky)'}

def get(url, accept=None, t=40, params=None):
    if params: url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    h = dict(UA)
    if accept: h['Accept'] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=t) as r:
        return r.read().decode('utf-8', 'replace')
def getj(url, accept=None, t=40, params=None): return json.loads(get(url, accept, t, params))

# ---------- mask ----------
_MASK = None
def mask_path():
    for p in (os.path.join(HERE, '..', 'zip_src', 'data', 'rof_mask.json'), os.path.join(HERE, 'data', 'geo', 'rof_mask.json'),
              os.path.join(HERE, 'rof_mask.json'), '/workspace/eugene-env/data/geo/rof_mask.json'):
        if os.path.exists(p): return p
    raise FileNotFoundError('rof_mask.json')
def in_rof(lat, lon):
    global _MASK
    if _MASK is None: _MASK = {tuple(c) for c in json.load(open(mask_path()))['cells']}
    if lat is None or lon is None: return False
    lon = ((float(lon) + 180) % 360) - 180
    return (int(float(lat) // 1), int(lon // 1)) in _MASK

# ---------- normalised volcano level: 0 green/normal, 1 yellow/advisory, 2 orange/watch, 3 red/warning ----------
LEVEL_NAMES = ['normal', 'advisory', 'watch', 'warning']
def nz_level(v): v = int(v); return 0 if v == 0 else 1 if v <= 2 else 2 if v == 3 else 3

def _iso(ms_or_str):
    if isinstance(ms_or_str, (int, float)): return dt.datetime.fromtimestamp(ms_or_str / 1000, UTC).isoformat(timespec='seconds')
    return ms_or_str

# ---------- GeoNet (CORS *) ----------
GN = 'https://api.geonet.org.nz'
GN_ACC = 'application/vnd.geo+json;version=2'
def geonet_quakes(mmi=3):
    j = getj(f'{GN}/quake?MMI={mmi}', GN_ACC); out = []
    for f in j['features']:
        p = f['properties']
        if p.get('quality') == 'deleted': continue
        lon, lat = f['geometry']['coordinates'][:2]
        out.append(dict(id=p['publicID'], t=p['time'][:19] + 'Z', lat=round(lat, 3), lon=round(lon, 3), depth=round(p.get('depth') or 0, 1),
                        mag=round(p.get('magnitude') or 0, 1), mmi=p.get('mmi'), place=p.get('locality'), quality=p.get('quality'),
                        url=f"https://www.geonet.org.nz/earthquake/{p['publicID']}"))
    return out
def geonet_val():
    j = getj(f'{GN}/volcano/val', GN_ACC); out = []
    for f in j['features']:
        p = f['properties']; lon, lat = f['geometry']['coordinates'][:2]
        out.append(dict(src='GeoNet', name=p['volcanoTitle'], lat=lat, lon=lon, level=nz_level(p['level']), native=f"VAL {p['level']}",
                        activity=p.get('activity'), hazards=p.get('hazards'), acc=p.get('acc'),
                        url=f"https://www.geonet.org.nz/volcano/{p['volcanoID']}"))
    return out
def geonet_news(n=8):
    j = getj(f'{GN}/news/geonet', 'application/json;version=2')
    return [dict(title=' '.join((x.get('title') or '').split()), t=x.get('published'), type=x.get('type'), val=x.get('val'), url=x.get('link')) for x in j.get('feed', [])[:n]]
def geonet_intensity():
    j = getj(f'{GN}/intensity?type=measured', GN_ACC)
    return [[round(f['geometry']['coordinates'][1], 3), round(f['geometry']['coordinates'][0], 3), f['properties'].get('mmi')] for f in j['features']]

# ---------- USGS (CORS *) ----------
def usgs_feed(feed='4.5_week', rof_only=True):
    j = getj(f'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson'); out = []
    for f in j['features']:
        p = f['properties']; lon, lat, dep = f['geometry']['coordinates'][:3]
        if rof_only and not in_rof(lat, lon): continue
        out.append(dict(id=f['id'], t=_iso(p['time']), lat=round(lat, 3), lon=round(lon, 3), depth=round(dep or 0, 1), mag=p.get('mag'),
                        place=p.get('place'), tsunami=p.get('tsunami'), alert=p.get('alert'), url=p.get('url')))
    return out
def hans_elevated(coords):
    j = getj('https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes'); out = []
    m = {'NORMAL': 0, 'ADVISORY': 1, 'WATCH': 2, 'WARNING': 3}
    for v in j:
        c = coords.get(str(v.get('vnum')), {})
        out.append(dict(src='USGS HANS', name=v['volcano_name'], lat=c.get('lat'), lon=c.get('lon'), level=m.get(v.get('alert_level'), 1),
                        native=f"{v.get('color_code')}/{v.get('alert_level')}", obs=(v.get('obs_abbr') or '').upper(),
                        sent=(v.get('sent_utc') or '').replace(' ', 'T') + 'Z', url=v.get('notice_url')))
    return out

# ---------- JMA (CORS *) ----------
JMA_CODE = {'11': (0, 'Level 1'), '12': (1, 'Level 2'), '13': (2, 'Level 3'), '14': (3, 'Level 4'), '15': (3, 'Level 5'),
            '22': (1, 'Crater-area warning'), '36': (2, 'Sea-area warning'), '35': (1, 'Submarine eruption notice'), '31': (2, 'Sea-area warning')}
def jma_volcano():
    lst = getj('https://www.jma.go.jp/bosai/volcano/const/volcano_list.json')
    info = {str(v.get('code')): v for v in lst} if isinstance(lst, list) else {}
    w = getj('https://www.jma.go.jp/bosai/volcano/data/warning.json'); out = {}
    for rep in w:
        for vi in rep.get('volcanoInfos', []) or []:
            for it in vi.get('items', []) or []:
                code = str(it.get('code'))
                if code not in JMA_CODE: continue
                for a in it.get('areas', []) or []:
                    vc = str(a.get('code')); meta = info.get(vc, {})
                    ll = meta.get('latlon') or [None, None]
                    lvl, nat = JMA_CODE[code]
                    if lvl == 0: continue
                    prev = out.get(vc)
                    if prev and prev['level'] >= lvl: continue
                    out[vc] = dict(src='JMA', name=meta.get('name_en') or a.get('name'), lat=ll[0], lon=ll[1], level=lvl, native=nat,
                                   sent=rep.get('reportDatetime'), url='https://www.data.jma.go.jp/vois/data/tokyo/STOCK/activity_info/map_0.html')
    return list(out.values())

# ---------- PHIVOLCS (HTML) ----------
PH_GVP = {'Taal': 273070, 'Kanlaon': 272020, 'Bulusan': 273010, 'Pinatubo': 273083, 'Mayon': 273030, 'Hibok-Hibok': 271080, 'Hibok-hibok': 271080}
def phivolcs(coords):
    t = html.unescape(re.sub(r'<[^>]+>', ' ', get('https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin')))
    t = re.sub(r'\s+', ' ', t)
    m = re.search(r'Alert Level Status:?(.*?)(?:Legend|Copyright|$)', t)
    seg = m.group(1) if m else t; out = []
    for name, lv in re.findall(r'([A-Z][A-Za-z\-]+)\s*-\s*(\d)', seg):
        lv = int(lv); g = coords.get(str(PH_GVP.get(name, '')), {})
        if name not in PH_GVP: continue
        out.append(dict(src='PHIVOLCS', name=name, lat=g.get('lat'), lon=g.get('lon'), level=0 if lv == 0 else 1 if lv <= 2 else 2 if lv == 3 else 3,
                        native=f'Alert Level {lv}', url='https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin'))
    if not out: raise ValueError('no PHIVOLCS levels parsed')
    return out

# ---------- MAGMA Indonesia (HTML; JSON API needs a key) ----------
def _norm(s): return re.sub(r'[^a-z]', '', (s or '').lower().replace('gunung', '').replace('gn.', ''))
MAGMA_ALIAS = {'anakkrakatau': 'krakatau', 'lewotobilakilaki': 'lewotobi', 'lewotobiperempuan': 'lewotobi', 'ililewotolok': 'lewotolok',
               'anakranakah': 'ranakah', 'bromo': 'tenggercaldera', 'burnitelong': 'telong', 'sangeangapi': 'sangeangapi'}
def magma(coords_by_name):
    t = get('https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas')
    t = t[t.find('Daftar Tingkat'):] or t
    lv_map = {'IV': 3, 'III': 2, 'II': 1, 'I': 0}; out = {}
    parts = re.split(r'>\s*Level (IV|III|II|I) \(', t)
    for i in range(1, len(parts) - 1, 2):
        lvl = lv_map[parts[i]]
        if lvl == 0: continue
        for nm, prov, link in re.findall(r'<td>\s*([^<\n]+?)\s+-\s+([^<\n]+?)\s*<a href="([^"]+laporan[^"]*)"', parts[i + 1]):
            nm = html.unescape(nm.strip()); k = _norm(nm); k = MAGMA_ALIAS.get(k, k)
            g = coords_by_name.get(k) or next((v for kk, v in coords_by_name.items() if kk.startswith(k) or k.startswith(kk)), None)
            out.setdefault(nm, dict(src='MAGMA Indonesia', name=nm, region=html.unescape(prov.strip()), lat=g and g['lat'], lon=g and g['lon'], level=lvl,
                                    native={1: 'Level II Waspada', 2: 'Level III Siaga', 3: 'Level IV Awas'}[lvl], url=html.unescape(link)))
    if not out: raise ValueError('no MAGMA levels parsed')
    return list(out.values())

# ---------- BMKG Indonesia quakes (CORS *) ----------
def bmkg():
    j = getj('https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json')['Infogempa']['gempa']; out = []
    for g in j:
        lat, lon = [float(x) for x in g['Coordinates'].split(',')]
        out.append(dict(t=g.get('DateTime'), lat=lat, lon=lon, mag=float(g.get('Magnitude') or 0), depth=g.get('Kedalaman'), place=g.get('Wilayah'),
                        tsunami=g.get('Potensi'), url='https://www.bmkg.go.id/gempabumi/gempabumi-dirasakan.bmkg'))
    return out

# ---------- NOAA tsunami warning centres (no CORS -> relayed) ----------
TS_FEEDS = {'PTWC': 'https://www.tsunami.gov/events/xml/PHEBAtom.xml', 'NTWC': 'https://www.tsunami.gov/events/xml/PAAQAtom.xml'}
ACTIVE_CATS = ('warning', 'advisory', 'watch', 'threat')
def tsunami_alerts():
    out = []
    for ctr, u in TS_FEEDS.items():
        x = get(u)
        for e in re.findall(r'<entry>(.*?)</entry>', x, re.S):
            g = lambda tag: html.unescape((re.search(f'<{tag}[^>]*>(.*?)</{tag}>', e, re.S) or [None, ''])[1]).strip()
            summ = re.sub(r'<[^>]+>', ' ', html.unescape(g('summary'))); summ = re.sub(r'\s+', ' ', summ)
            cat = (re.search(r'Category:\s*([A-Za-z]+)', summ) or [None, ''])[1]
            mag = (re.search(r'Magnitude:\s*([\d.]+)', summ) or [None, None])[1]
            link = (re.search(r'<link[^>]*href="([^"]+)"', e) or [None, ''])[1]
            lat, lon = g('geo:lat'), g('geo:long')
            out.append(dict(center=ctr, title=' '.join(g('title').split()), t=g('updated'), category=cat, mag=float(mag) if mag else None,
                            lat=float(lat) if lat else None, lon=float(lon) if lon else None, summary=summ[:400], url=html.unescape(link)))
    now = dt.datetime.now(UTC)
    for a in out:
        try: age = (now - dt.datetime.fromisoformat(a['t'].replace('Z', '+00:00'))).total_seconds() / 3600
        except Exception: age = 999
        a['age_h'] = round(age, 1)
        a['active'] = bool(a['category'] and a['category'].lower() in ACTIVE_CATS and age <= 24)
    return out

# ---------- GVP volcano coordinates (static, built by build_ringfire.py --static) ----------
def volcano_coords():
    for p in (os.path.join(HERE, '..', 'zip_src', 'data', 'volcano_coords.json'), os.path.join(HERE, 'data', 'geo', 'volcano_coords.json'),
              '/workspace/eugene-env/data/geo/volcano_coords.json'):
        if os.path.exists(p):
            j = json.load(open(p)); return j['by_num'], j['by_name']
    return {}, {}

def snapshot(intensity=False):
    """Everything current, each source isolated. Returns dict with 'status' per source."""
    by_num, by_name = volcano_coords()
    S = {'built': dt.datetime.now(UTC).isoformat(timespec='seconds'), 'status': {}}
    def run(k, fn):
        try: S[k] = fn(); S['status'][k] = f'ok ({len(S[k])})'
        except Exception as e: S[k] = []; S['status'][k] = f'failed: {type(e).__name__}: {str(e)[:100]}'
    run('geonet_quakes', geonet_quakes); run('geonet_news', geonet_news)
    if intensity: run('geonet_intensity', geonet_intensity)
    run('usgs_rof', lambda: usgs_feed('4.5_week'))
    run('bmkg', bmkg); run('tsunami', tsunami_alerts)
    V = []
    for k, fn in (('geonet_val', geonet_val), ('hans', lambda: hans_elevated(by_num)), ('jma', jma_volcano),
                  ('phivolcs', lambda: phivolcs(by_num)), ('magma', lambda: magma(by_name))):
        run(k, fn); V += S.pop(k)
    S['volcanoes'] = V
    S['status']['sernageomin'] = 'skipped: rnvv.sernageomin.cl / sernageomin.cl time out from scripted clients'
    S['status']['gvp_weekly'] = 'skipped: volcano.si.edu weekly report sits behind a bot-check (403); GVP GeoServer used for history instead'
    return S

# ---------- plain-language section for daily_report.py ----------
def report_lines():
    """'Ring of Fire' section for the daily outlook: Pacific M6+ (24 h), NZ felt quakes, elevated volcanoes, tsunami alerts. Times in PT."""
    from zoneinfo import ZoneInfo
    PT = ZoneInfo('America/Los_Angeles')
    def pt(t):
        try: return dt.datetime.fromisoformat(str(t).replace('Z', '+00:00')).astimezone(PT).strftime('%a %b %d %-I:%M %p %Z')
        except Exception: return str(t)
    L = []; now = dt.datetime.now(UTC)
    try:
        q = [e for e in usgs_feed('4.5_day') if (e['mag'] or 0) >= 6]
        L.append(f"- Pacific Ring of Fire M6+ quakes, past 24 h (USGS): {len(q)}" + ('' if q else ' — none.'))
        for e in sorted(q, key=lambda e: -e['mag'])[:8]:
            L.append(f"  - M{e['mag']:.1f} {e['place']} — {pt(e['t'])}, depth {e['depth']:.0f} km" + (' — USGS tsunami flag set (check tsunami.gov)' if e.get('tsunami') else '') + f" ({e['url']})")
    except Exception as e: L.append(f'- USGS Pacific quakes: unavailable ({type(e).__name__})')
    try:
        nz = [e for e in geonet_quakes(3) if (now - dt.datetime.fromisoformat(e['t'].replace('Z', '+00:00'))).total_seconds() < 86400 and e['mag'] >= 4]
        L.append(f"- New Zealand felt quakes M4+, past 24 h (GeoNet): {len(nz)}" + ('; ' + '; '.join(f"M{e['mag']:.1f} {e['place']} ({pt(e['t'])}, MMI {e['mmi']})" for e in nz[:4]) if nz else ' — none.'))
    except Exception as e: L.append(f'- GeoNet quakes: unavailable ({type(e).__name__})')
    by_num, by_name = volcano_coords(); V = []; bad = []
    for nm, fn in (('GeoNet', geonet_val), ('USGS HANS', lambda: hans_elevated(by_num)), ('JMA', jma_volcano), ('PHIVOLCS', lambda: phivolcs(by_num)), ('MAGMA', lambda: magma(by_name))):
        try: V += fn()
        except Exception as e: bad.append(nm)
    hi = sorted([v for v in V if v['level'] >= 2], key=lambda v: -v['level']); mid = [v for v in V if v['level'] == 1]
    L.append(f"- Volcanoes at watch/orange or higher ({len(hi)}): " + (', '.join(f"{v['name']} ({v['src']}: {v['native']})" for v in hi) or 'none') + '.')
    L.append(f"- Volcanoes at advisory/yellow ({len(mid)}): " + ', '.join(f"{v['name']}" for v in mid) + '.' + (f" (Unavailable today: {', '.join(bad)}.)" if bad else ''))
    try:
        news = [n for n in geonet_news(5) if n.get('type') == 'vab' or 'Volcanic Alert' in (n.get('title') or '')][:2]
        for n in news: L.append(f"  - GeoNet bulletin: {n['title']} ({pt(n['t'])}) {n['url']}")
    except Exception: pass
    try:
        ts = tsunami_alerts(); act = [t for t in ts if t['active']]
        if act:
            for t in act: L.append(f"- **TSUNAMI {t['category'].upper()}** ({t['center']}): {t['title']} — issued {pt(t['t'])}. {t['url']}")
        else:
            last = max(ts, key=lambda t: t['t']) if ts else None
            L.append('- Tsunami alerts (NOAA PTWC/NTWC): none active.' + (f" Latest message: {last['category']} — {last['title']}, {pt(last['t'])}." if last else ''))
    except Exception as e: L.append(f'- Tsunami alerts: unavailable ({type(e).__name__}) — check https://www.tsunami.gov')
    L.append('- (Historically, Pacific quakes/eruptions show no reliable link to Eugene weather or local incidents — see the dataset correlations.)')
    return L
