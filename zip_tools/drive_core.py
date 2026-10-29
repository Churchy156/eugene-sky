"""Driving-trip planner shared by the alert checker (zip_tools/alert_check.py).
The travel page (travel_src/app.js) uses the same rules in JavaScript, so the email and the page agree.

Free, keyless sources:
  route ........ OSRM public demo router (router.project-osrm.org) - distance + normal no-traffic drive time
  geocoding .... Photon (photon.komoot.io), only if a trip has no saved lat/lon
  weather ...... Open-Meteo hourly forecast at points along the route, at the time you'd pass each one
  alerts ....... National Weather Service active alerts at points along the route
  road reports . our own relay (Cloudflare Worker -> ODOT TripCheck incidents/work zones/cameras, CHP incidents,
                 state WZDx work-zone feeds); falls back to the 'live' branch the 10-min Action publishes
There are NO live traffic speeds in any of these. Rush hour is a typical-weekday allowance, not a measurement."""
import math, re, hashlib, datetime as dt, requests
from zoneinfo import ZoneInfo
PT = ZoneInfo('America/Los_Angeles'); UTC = dt.timezone.utc
UA = {'User-Agent': 'eugene-sky drive_check (personal; github.com/Churchy156/eugene-sky)'}
T = 25
RELAY = 'https://eugene-sky-traffic.eugene-sky.workers.dev/traffic/{}.json'
LIVE = 'https://raw.githubusercontent.com/Churchy156/eugene-sky/live/traffic/{}.json'
PASSES = [  # name, lat, lon, feet
    ('Santiam Pass (US 20)', 44.4248, -121.8536, 4817), ('Willamette Pass (OR 58)', 43.5955, -122.0357, 5128),
    ('McKenzie Pass (OR 242)', 44.2600, -121.8100, 5325), ('Mt Hood / Government Camp (US 26)', 45.3018, -121.7465, 4000),
    ('Siskiyou Summit (I-5)', 42.0750, -122.6050, 4310), ('Sexton Summit (I-5)', 42.6020, -123.3640, 1960),
    ('Black Butte Summit (I-5)', 41.3600, -122.3300, 3912), ('Deadman Pass / Cabbage Hill (I-84)', 45.6045, -118.5350, 3615),
    ('Snoqualmie Pass (I-90)', 47.4245, -121.4130, 3022), ('Stevens Pass (US 2)', 47.7466, -121.0859, 4061),
    ('White Pass (US 12)', 46.6376, -121.3912, 4500), ('Donner Summit (I-80)', 39.3233, -120.3283, 7227),
    ('Echo Summit (US 50)', 38.8126, -120.0303, 7382), ('Chemult / US 97 high desert', 43.2200, -121.7800, 4760),
    ('Bozeman Pass (I-90)', 45.6617, -110.8069, 5702), ('Homestake Pass (I-90)', 45.9203, -112.4136, 6329), ('Lookout Pass (I-90)', 47.4566, -115.6966, 4710),
    ('Fourth of July Pass (I-90)', 47.6247, -116.5197, 3081), ('MacDonald Pass (US 12)', 46.5603, -112.3103, 6320), ('Lolo Pass (US 12)', 46.6347, -114.5797, 5233),
    ('Blue Mountains / Emigrant Hill (I-84)', 45.47, -118.43, 4193), ('Ladd Canyon (I-84)', 45.17, -117.98, 3800), ('Sherman Summit (I-80 WY)', 41.14, -105.38, 8640),
    ('Vail Pass (I-70)', 39.53, -106.22, 10662), ('Eisenhower Tunnel (I-70)', 39.68, -105.92, 11158)]
METROS = [  # name, lat, lon, radius mi, typical weekday rush-hour extra minutes
    ('Portland', 45.52, -122.68, 15, 25), ('Seattle', 47.61, -122.33, 15, 30), ('Tacoma', 47.25, -122.44, 8, 15),
    ('Salem', 44.94, -123.03, 6, 5), ('Eugene-Springfield', 44.05, -123.05, 6, 5), ('Sacramento', 38.58, -121.49, 12, 20),
    ('San Francisco Bay Area', 37.77, -122.27, 25, 35), ('Boise', 43.61, -116.20, 8, 10), ('Bend', 44.06, -121.31, 4, 5),
    ('Spokane', 47.66, -117.42, 8, 10), ('Billings', 45.78, -108.5, 6, 5), ('Fargo-Moorhead', 46.88, -96.79, 6, 5), ('Minneapolis-St Paul', 44.97, -93.2, 18, 30),
    ('Madison', 43.07, -89.4, 8, 10), ('Milwaukee', 43.04, -87.93, 10, 15), ('Chicago', 41.88, -87.66, 22, 40), ('Denver', 39.74, -104.99, 15, 25)]
DAY_MAX, DAY_AIM = 600, 540   # over ~10 h of map driving -> overnight stops, ~9 h a day (same as the page)
RUSH = [(6.5, 9.5), (15.0, 18.5)]
STATE_BOX = {'OR': (41.9, 46.3, -124.7, -116.4), 'WA': (45.5, 49.1, -124.9, -116.9), 'CA': (32.5, 42.1, -124.5, -114.1),
             'ID': (41.9, 49.1, -117.3, -111.0), 'NV': (35.0, 42.1, -120.1, -114.0),
             # the relay has planned-roadwork feeds for these (no crash reports); MT, IL, SD, WY have no free feed
             'ND': (45.9, 49.0, -104.1, -96.5), 'MN': (43.5, 49.4, -97.3, -89.5), 'WI': (42.5, 47.1, -92.9, -86.8), 'IA': (40.4, 43.5, -96.7, -90.1),
             'IN': (37.8, 41.8, -88.1, -84.8), 'UT': (37.0, 42.0, -114.1, -109.0)}

def mi(a, b):
    R = 3958.8; t = math.pi / 180; dl = (b[0] - a[0]) * t; dn = (b[1] - a[1]) * t
    h = math.sin(dl / 2) ** 2 + math.cos(a[0] * t) * math.cos(b[0] * t) * math.sin(dn / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1, h)))
def get(u, **kw): r = requests.get(u, headers=UA, timeout=T, **kw); r.raise_for_status(); return r.json()

def geocode(q):
    j = get('https://photon.komoot.io/api/', params={'q': q, 'limit': 1, 'lang': 'en'})
    f = j['features'][0]; lon, lat = f['geometry']['coordinates']; return lat, lon

def route(a, b):
    j = get(f'https://router.project-osrm.org/route/v1/driving/{a[1]:.5f},{a[0]:.5f};{b[1]:.5f},{b[0]:.5f}',
            params={'overview': 'full', 'geometries': 'geojson', 'annotations': 'duration'})
    r = j['routes'][0]; c = [(y, x) for x, y in r['geometry']['coordinates']]; ann = r['legs'][0]['annotation']['duration']
    tot = sum(ann) or 1; k = r['duration'] / tot; cum = [0.0]
    for d in ann: cum.append(cum[-1] + d * k)
    cm = [0.0]
    for i in range(1, len(c)): cm.append(cm[-1] + mi(c[i - 1], c[i]))
    return dict(miles=r['distance'] / 1609.344, secs=r['duration'], coords=c, cum_t=cum[:len(c)], cum_mi=cm)

def near_route(R, p, maxmi):
    """(distance mi, index) of the closest route vertex, with a cheap bbox prefilter."""
    best = (1e9, 0); dlat = maxmi / 69.0 + 0.02
    for i, q in enumerate(R['coords']):
        if abs(q[0] - p[0]) > dlat or abs(q[1] - p[1]) > dlat * 1.5: continue
        d = mi(p, q)
        if d < best[0]: best = (d, i)
    return best

_PL = []
def town(lat, lon):
    if not _PL:
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'us_places.tsv')
        if os.path.exists(p):
            for l in open(p):
                x = l.rstrip('\n').split('\t')
                if len(x) >= 4: _PL.append((x[1], x[0], float(x[2]), float(x[3])))
    if not _PL: return None
    n, st, la, lo = min(_PL, key=lambda x: (x[2] - lat) ** 2 + ((x[3] - lon) * 0.72) ** 2)
    return f"{n}, {st}"
def samples(R):
    """Points about every 25 mi plus any known mountain pass within 3 mi of the route."""
    out = []; step = max(15, R['miles'] / 18); nxt = 0
    for i, m in enumerate(R['cum_mi']):
        if m >= nxt or i == len(R['coords']) - 1:
            la, lo = R['coords'][i]; tn = town(la, lo)
            out.append(dict(i=i, name=tn or f'{m:.0f} mi along', lat=la, lon=lo)); nxt = m + step
    for n, la, lo, ft in PASSES:
        d, i = near_route(R, (la, lo), 3)
        if d <= 3: out.append(dict(i=i, name=n, lat=la, lon=lo, pass_=True, ft=ft))
    out.sort(key=lambda s: s['i'])
    for s in out: s['t_off'] = R['cum_t'][s['i']]; s['mi'] = R['cum_mi'][s['i']]
    return out

def weather(S):
    j = get('https://api.open-meteo.com/v1/forecast', params=dict(latitude=','.join(f"{s['lat']:.3f}" for s in S), longitude=','.join(f"{s['lon']:.3f}" for s in S),
            hourly='temperature_2m,precipitation,snowfall,weather_code,visibility,wind_gusts_10m', timeformat='unixtime', timezone='auto', forecast_days=16,
            temperature_unit='fahrenheit', precipitation_unit='inch', wind_speed_unit='mph'))
    return j if isinstance(j, list) else [j]

def wx_at(W, ts):
    h = W['hourly']; t = h['time']
    if not t or ts < t[0] - 3600 or ts > t[-1] + 3600: return None
    i = min(range(len(t)), key=lambda k: abs(t[k] - ts)); g = lambda k: (h.get(k) or [None] * len(t))[i]
    return dict(temp=g('temperature_2m'), pr=g('precipitation') or 0, snow=g('snowfall') or 0, code=g('weather_code'), vis=g('visibility'), gust=g('wind_gusts_10m'), elev_ft=(W.get('elevation') or 0) * 3.281)

def wx_kind(w):
    if not w: return None
    c = w['code'] or 0
    if w['snow'] >= 0.01 or c in (71, 73, 75, 77, 85, 86): return 'snow'
    if c in (56, 57, 66, 67) or (w['temp'] is not None and w['temp'] <= 34 and w['pr'] >= 0.01): return 'ice'
    if c in (65, 82) or w['pr'] >= 0.2: return 'heavy rain'
    if c in (61, 63, 80, 81, 51, 53, 55) or w['pr'] >= 0.02: return 'rain'
    return None

def nws(points):
    seen = {}
    for p in points:
        try:
            for f in get('https://api.weather.gov/alerts/active', params={'point': f"{p['lat']:.3f},{p['lon']:.3f}"})['features']:
                a = f['properties']
                if a.get('status') != 'Actual' or a.get('messageType') == 'Cancel': continue
                k = a.get('event', '') + '|' + (a.get('areaDesc') or '')[:40]
                seen.setdefault(k, dict(key='nws:' + k, id=a['id'], event=a.get('event'), headline=a.get('headline') or a.get('event'), near=p['name'],
                                        ends=a.get('ends') or a.get('expires'), url=f"https://api.weather.gov/alerts/{a['id']}"))
        except Exception: pass
    return list(seen.values())

def states_on(R):
    st = set()
    for la, lo in R['coords'][::25] + [R['coords'][-1]]:
        for s, (a, b, c, d) in STATE_BOX.items():
            if a <= la <= b and c <= lo <= d: st.add(s)
    return sorted(st)

def road_reports(R):
    out = {'inc': [], 'wz': [], 'cam': [], 'src': []}
    for s in states_on(R):
        d = None
        for u in (RELAY, LIVE):
            try: d = get(u.format(s)); out['src'].append(f"{s} ({'relay' if u is RELAY else 'live branch'}, {d.get('built', '')[:16]})"); break
            except Exception: continue
        if d:
            for k in out:
                if k != 'src': out[k] += d.get(k) or []
    return out

def rush_extra(R, at, tz_near=lambda i: PT):
    """at(route seconds) -> epoch seconds; rush hour is judged in each city's own local time."""
    out = []
    for n, la, lo, rad, extra in METROS:
        d, i = near_route(R, (la, lo), rad)
        if d > rad: continue
        t = dt.datetime.fromtimestamp(at(R['cum_t'][i]), tz_near(i))
        h = t.hour + t.minute / 60
        if t.weekday() < 5 and any(a <= h <= b for a, b in RUSH): out.append((n, extra, t))
    return out

def classify(txt):
    """(kind, extra minutes) for a road report. Same rules as classify() in travel_src/app.js."""
    if re.search(r'\bclos(ed|ure|ing)\b|blocked|impassable', txt, re.I) and not re.search(r'shoulder clos|lane clos', txt, re.I): return 'closure', 30
    if re.search(r'no (traffic )?impacts?|no delay', txt, re.I): return 'notice', 0
    if re.search(r'construction|work(ers| zone| is being done)|paving|striping|signage|maintenance|lane clos|shoulder', txt, re.I): return 'roadwork', 3
    if re.search(r'minimal delay|use caution|fire in the area', txt, re.I): return 'notice', 0
    return 'incident', 10
def hhmm(t): return f"{t:%-I:%M %p}"
def tzab(t): n = t.tzname() or ''; return re.sub(r'^(AK|H|[ECMPA])[SD]T$', r'\1T', n)
def plan(trip, now=None, R=None):
    """Return a dict with leave/arrive times, buffer reasons and on-route issues. Raises if routing fails."""
    now = now or dt.datetime.now(UTC)
    a = (trip['from_lat'], trip['from_lon']) if trip.get('from_lat') is not None else geocode(trip.get('from') or 'Eugene, OR')
    b = (trip['to_lat'], trip['to_lon']) if trip.get('to_lat') is not None else geocode(trip['to'])
    R = R or route(a, b); S = samples(R)
    W = []
    for k in range(0, len(S), 40): W += weather(S[k:k + 40])
    for s, w in zip(S, W):
        try: s['tz'] = ZoneInfo(w.get('timezone')) if w.get('timezone') not in (None, 'GMT') else PT
        except Exception: s['tz'] = PT
    rr = road_reports(R)
    alerts = nws([s for k, s in enumerate(S) if s.get('pass_') or k % 2 == 0 or k == len(S) - 1][:18])
    tz_near = lambda i: min(S, key=lambda s: abs(s['i'] - i)).get('tz', PT)
    drive_min = R['secs'] / 60; base = max(10, round(drive_min * 0.05))
    mode = 'arrive' if trip.get('arrive_by') else 'depart'
    tz_in = ZoneInfo(trip['tz']) if trip.get('tz') else PT   # wall-clock time in the trip's own zone (default Pacific)
    tgt = dt.datetime.fromisoformat(trip.get('arrive_by') or trip['depart']).replace(tzinfo=tz_in)
    # long drives: even days of <= ~9 h, overnight where each day ends, next morning same local clock time
    n_days = 1 if drive_min <= DAY_MAX else math.ceil(drive_min / DAY_AIM)
    days = [dict(t0=R['secs'] * k / n_days, t1=R['secs'] * (k + 1) / n_days) for k in range(n_days)]
    for d in days[:-1]:
        i = next((j for j, t in enumerate(R['cum_t']) if t >= d['t1']), len(R['cum_t']) - 1)
        d['stop_i'] = i; d['stop'] = town(*R['coords'][i]) or f"mile {R['cum_mi'][i]:.0f}"; d['tz'] = tz_near(i)
    def sched(frac):
        f = 1 + frac; st = [0.0] * n_days; tzs = [tz_in if k == 0 else days[k - 1]['tz'] for k in range(n_days)]
        if mode == 'depart':
            st[0] = tgt.timestamp(); hm = tgt.astimezone(tz_in).time()
            for k in range(1, n_days):
                end = dt.datetime.fromtimestamp(st[k - 1] + (days[k - 1]['t1'] - days[k - 1]['t0']) * f, tzs[k])
                st[k] = dt.datetime.combine(end.date() + dt.timedelta(days=1), hm, tzs[k]).timestamp()
        else:
            st[-1] = tgt.timestamp() - (days[-1]['t1'] - days[-1]['t0']) * f; hm = dt.datetime.fromtimestamp(st[-1], tzs[-1]).time()
            for k in range(n_days - 2, -1, -1):
                need = (days[k]['t1'] - days[k]['t0']) * f; nx = dt.datetime.fromtimestamp(st[k + 1], tzs[k])
                s0 = dt.datetime.combine(nx.date() - dt.timedelta(days=1), hm, tzs[k]).timestamp()
                st[k] = min(s0, st[k + 1] - 8 * 3600 - need)
            st[0] -= st[0] % 300
        def at(t):
            k = next((j for j, d in enumerate(days) if t <= d['t1']), n_days - 1); return st[k] + (t - days[k]['t0']) * f
        return st, at, st[-1] + (days[-1]['t1'] - days[-1]['t0']) * f
    # incidents / work zones near the route (time-independent)
    trip_day = tgt.date().isoformat(); last_day = (tgt + dt.timedelta(days=n_days if n_days > 1 else 0)).date().isoformat(); issues = []; inc_min = 0; wz_min = 0
    for x in rr['inc']:
        d, i = near_route(R, (x[0], x[1]), 0.5)
        if d > 0.5: continue
        txt = f"{x[2]} {x[3]}"; kd, add = classify(txt)
        k = 'inc:' + hashlib.sha1(f"{x[2]}|{x[3][:80]}".encode()).hexdigest()[:12]
        if any(z['key'] == k for z in issues): continue
        inc_min += add
        issues.append(dict(key=k, kind=kd,
                           road=x[2], text=x[3], mi=R['cum_mi'][i], when=x[4] if len(x) > 4 else '', add=add))
    for x in rr['wz']:
        if len(x) > 5 and ((x[4] and x[4] > last_day) or (x[5] and x[5] < trip_day)): continue
        d, i = near_route(R, (x[0], x[1]), 0.3)
        if d > 0.3: continue
        k = 'wz:' + hashlib.sha1(f"{x[2]}|{x[3][:60]}".encode()).hexdigest()[:12]
        if any(z['key'] == k for z in issues): continue
        add = 0 if re.search(r'no (traffic )?impact|no delay', x[3], re.I) else 3
        wz_min += add; issues.append(dict(key=k, kind='work zone', road=x[2], text=x[3], mi=R['cum_mi'][i], add=add))
    inc_min = min(inc_min, 60); wz_min = min(wz_min, 30 if n_days > 1 else 15)
    cams = []
    for x in rr['cam']:
        d, i = near_route(R, (x[0], x[1]), 0.4)
        if d <= 0.4: cams.append(dict(name=x[2], url=x[3], mi=R['cum_mi'][i]))
    cams.sort(key=lambda c: c['mi'])
    nws_pct = 0; nws_min = 0
    for al in alerts:
        e = (al['event'] or '').lower()
        if re.search(r'winter storm warning|ice storm|blizzard', e): nws_pct = max(nws_pct, 30)
        elif re.search(r'winter weather advisory|winter storm watch|freezing (rain|drizzle|fog)', e): nws_pct = max(nws_pct, 15)
        elif re.search(r'high wind|dense fog|flood|dust|smoke', e): nws_min = 10
    def evaluate(at):
        if not callable(at): at = (lambda lv: lambda t: lv + t)(at)
        rs = []; wx = []; worst = 0; fog = gust = icy = False; pts = []
        for s, w in zip(S, W):
            ts = at(s['t_off']); x = wx_at(w, ts); kd = wx_kind(x)
            pts.append(dict(name=s['name'], mi=s['mi'], t=dt.datetime.fromtimestamp(ts, PT), w=x, kind=kd, pass_=s.get('pass_'), ft=s.get('ft')))
            if not x: continue
            pct = {'snow': 25, 'ice': 25, 'heavy rain': 10, 'rain': 5}.get(kd, 0)
            if pct > worst: worst = pct
            if kd: wx.append((kd, s['name'], ts))
            if x['vis'] is not None and x['vis'] < 800: fog = s['name']
            if (x['gust'] or 0) >= 45: gust = s['name']
            if s.get('pass_') and x['temp'] is not None and x['temp'] <= 32 and not kd: icy = s['name']
        wmin = round(drive_min * worst / 100) + (10 if fog else 0) + (10 if gust else 0) + (5 if icy else 0)
        if worst >= 25: wmin = max(wmin, 15)
        if worst:
            k0 = max(wx, key=lambda z: {'snow': 4, 'ice': 4, 'heavy rain': 2, 'rain': 1}[z[0]])
            places = sorted({z[1] for z in wx if z[0] == k0[0]})
            rs.append((round(drive_min * worst / 100) if worst < 25 else max(15, round(drive_min * worst / 100)),
                       f"{k0[0].capitalize()} in the forecast near {', '.join(places[:3])} around {hhmm(dt.datetime.fromtimestamp(k0[2], PT))} PT"
                       + (' - carry chains and check TripCheck before the pass' if k0[0] in ('snow', 'ice') else '')))
        if fog: rs.append((10, f'Fog (under half a mile visibility) near {fog}'))
        if gust: rs.append((10, f'Strong wind gusts (45+ mph) near {gust}'))
        if icy: rs.append((5, f'Below freezing at {icy} - watch for icy patches'))
        rm = rush_extra(R, at, tz_near)
        for n, e, t in rm: rs.append((e, f'Usual weekday rush hour in {n} (you\'d be there about {hhmm(t)} {tzab(t)})'))
        if nws_pct: rs.append((round(drive_min * nws_pct / 100), 'Weather Service alert on the route: ' + ', '.join(sorted({a['event'] for a in alerts if re.search(r'winter|ice storm|blizzard|freezing (rain|drizzle|fog)', a['event'] or '', re.I)}))))
        if nws_min: rs.append((10, 'Weather Service alert on the route: ' + ', '.join(sorted({a['event'] for a in alerts if re.search(r'wind|fog|flood|dust|smoke', a['event'] or '', re.I)}))))
        if inc_min: rs.append((inc_min, f"{sum(1 for z in issues if z['kind'] in ('closure', 'incident', 'roadwork') and z['add'])} road report(s) on the route that may slow you" + (' - one sounds like a CLOSURE' if any(z['kind'] == 'closure' for z in issues) else '')))
        if wz_min: rs.append((wz_min, f"{sum(1 for z in issues if z['kind'] == 'work zone' and z['add'])} work zone(s) on the route"))
        extra = sum(r[0] for r in rs); total = base + extra; total = int(math.ceil(total / 5) * 5)
        return dict(reasons=[(base, 'Normal cushion for a stop and everyday slowdowns')] + rs, buffer=total, points=pts)
    fl5 = lambda ts: ts - ts % 300
    if mode == 'arrive':
        leave_ts = tgt.timestamp() - R['secs'] - base * 60
        for _ in range(2):
            E = evaluate(leave_ts); leave_ts = tgt.timestamp() - R['secs'] - E['buffer'] * 60
        E = evaluate(leave_ts); leave_ts = fl5(tgt.timestamp() - R['secs'] - E['buffer'] * 60)
        arrive = tgt; est = dt.datetime.fromtimestamp(leave_ts + R['secs'] + (E['buffer'] - base) * 60, PT)
    else:
        leave_ts = tgt.timestamp(); E = evaluate(leave_ts)
        est = dt.datetime.fromtimestamp(leave_ts + R['secs'] + (E['buffer'] - base) * 60, PT); arrive = None
    if n_days > 1:  # replace the one-day math with the overnight schedule
        frac = base / drive_min
        for _ in range(3): st, at, end = sched(frac); E = evaluate(at); frac = E['buffer'] / drive_min
        st, at, end = sched(frac); leave_ts = st[0]; est = dt.datetime.fromtimestamp(end, PT); arrive = tgt if mode == 'arrive' else None
        for k, d in enumerate(days): d['start'] = dt.datetime.fromtimestamp(st[k], PT); d['end'] = dt.datetime.fromtimestamp(st[k] + (d['t1'] - d['t0']) * (1 + frac), PT)
    return dict(mode=mode, leave=dt.datetime.fromtimestamp(leave_ts, PT), target=tgt, est_arrive=est, arrive_by=arrive, miles=R['miles'], drive_min=drive_min,
                base=base, **E, days=days if n_days > 1 else [], issues=issues, alerts=alerts, cams=cams[:40], sources=rr['src'], frm=trip.get('from') or 'Eugene, OR', to=trip['to'])

def fmt_min(m):
    m = int(round(m)); return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"
