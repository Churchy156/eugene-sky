#!/usr/bin/env python3
"""Near-real-time alert detector for Steven (Eugene, OR). Run every 30 min by the "Eugene urgent alerts" routine.

  python3 /workspace/eugene-sky/zip_tools/alert_check.py            # normal check
  python3 .../alert_check.py --seed     # (re)seed state with everything currently active, no alert
  python3 .../alert_check.py --test     # write a sample alert from fake events (state untouched, nothing sent)
  python3 .../alert_check.py --dry-run  # normal check but don't save state

stdout is exactly one line:  NONE   or   ALERT <md path> <html path> <attachment filename or ->
Everything else (feed failures, counts) goes to /workspace/eugene-env/data/alert_check.log.
A fetch failure never alerts and never clears state (so it can't fake a "restored" note).
First run (no state file) seeds silently.

Reuses: eq_map.py (USGS geojson, distance, map styling, md->HTML), power_feeds.py (utility feed URLs, HTTP,
distance, nearest-town lookup), ringfire_core.py (Ring of Fire mask, NOAA PTWC/NTWC tsunami feed parser),
and the NWS alert query from daily_report.py (Lane County zone ORC039 / SAME 041039 + the Eugene point)."""
import os, sys, json, math, time, hashlib, datetime as dt, shutil, traceback
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import eq_map, power_feeds as pf, ringfire_core as rf

# ======================= THRESHOLDS / SETTINGS =======================
EUG = (44.052, -123.087)                 # Eugene (lat, lon)
EQ_NEAR_KM, EQ_NEAR_MAG = 250, 3.0       # M3.0+ within 250 km of Eugene
EQ_REGION_KM, EQ_REGION_MAG = 500, 4.5   # M4.5+ within 500 km
EQ_WORLD_MAG = 7.0                       # any M7.0+ worldwide
EQ_ROF_MAG, EQ_ROF_KM = 6.0, 2000        # M6.0+ on the Ring of Fire within 2000 km of the Oregon coast
EQ_REVISE_MAG = 0.5                      # re-alert an already-alerted quake only if USGS revises it up by this much
USGS_FEED = '2.5_day'                    # USGS summary feed polled (all M2.5+ worldwide, past 24 h)
TSU_WEST_COAST_CATS = ('warning', 'advisory', 'watch')   # NTWC/PTWC messages for the US West Coast
TSU_PACIFIC_CATS = ('warning', 'threat')                 # PTWC Pacific-wide tsunami warning / threat messages
TSU_MAX_AGE_H = 24
PWR_NEW_OUTAGE = 50                      # a new outage of 50+ customers
PWR_UTIL_TOTAL = 200                     # total out at one utility jumps above 200
PWR_UTIL_CLEAR = 100                     # ...and counts as cleared once back under 100 (hysteresis, avoids flapping)
PWR_NEAR_MI = 45                         # Pacific Power outages within 45 mi of Eugene
NWS_SAME = '041039'                      # Lane County FIPS (NWS SAME code)
NWS_ZONES = 'ORZ118,ORC039'              # as used in daily_report.py alerts()
EXPIRE_DAYS = 7
# Paths default to the box; GitHub Actions (.github/workflows/alerts.yml) overrides them with env vars.
STATE = os.environ.get('ALERT_STATE', '/workspace/eugene-env/data/alert_state.json')
LOG = os.environ.get('ALERT_LOG', '/workspace/eugene-env/data/alert_check.log')
REPORTS = os.environ.get('ALERT_REPORTS', '/workspace/eugene-env/reports')
ATTACH = os.environ.get('ALERT_ATTACH', '/home/box/agent-data/agents/15f61d5b-1432-45e0-800f-fc00e7b4ab04/attachments')
DIRTY_FILE = os.environ.get('ALERT_DIRTY_FILE')   # if set, gets '1' when the state changed in a way worth committing, else '0'
STATE_REFRESH_H = 12                     # Actions: re-commit unchanged state at most this often so last_seen/expiry stays honest
OR_COAST = [(46.25, -123.98), (45.9, -123.96), (45.5, -123.95), (45.0, -124.0), (44.6, -124.07), (44.0, -124.13),
            (43.4, -124.25), (42.8, -124.5), (42.4, -124.42), (42.0, -124.21)]
NWS_RANK = {'statement': 1, 'outlook': 1, 'advisory': 2, 'watch': 3, 'warning': 4, 'emergency': 5}
# =====================================================================
PT = ZoneInfo('America/Los_Angeles'); UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)
UA = {'User-Agent': 'eugene-sky alert_check (personal research; github.com/Churchy156/eugene-sky)', 'Accept': 'application/geo+json'}

def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a') as f: f.write(f"{dt.datetime.now(PT):%Y-%m-%d %H:%M:%S} PT  {msg}\n")
    except Exception: pass

def ptime(t): return f"{t.astimezone(PT):%a %b} {t.astimezone(PT).day}, {t.astimezone(PT):%-I:%M %p} PT"
def iso(t): return t.astimezone(UTC).isoformat(timespec='seconds')
def parse(s):
    try: return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception: return None
def km_to_mi(k): return k * 0.621371
def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    x = math.sin(lo2 - lo1) * math.cos(la2); y = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][int(((math.degrees(math.atan2(x, y)) + 360) % 360 + 22.5) // 45) % 8]
def coast_km(lat, lon): return min(eq_map.km((lat, lon), p) for p in OR_COAST)

# ----------------------------- fetchers (each raises on failure) -----------------------------
def f_quakes():
    out = []
    for f in eq_map._get(USGS_FEED):
        p = f['properties']; lon, lat, dep = f['geometry']['coordinates'][:3]; mag = p.get('mag')
        if mag is None: continue
        d = eq_map.km(EUG, (lat, lon)); why = []
        if mag >= EQ_NEAR_MAG and d <= EQ_NEAR_KM: why.append(f'M{EQ_NEAR_MAG}+ within {EQ_NEAR_KM} km of Eugene')
        elif mag >= EQ_REGION_MAG and d <= EQ_REGION_KM: why.append(f'M{EQ_REGION_MAG}+ within {EQ_REGION_KM} km of Eugene')
        if mag >= EQ_WORLD_MAG: why.append(f'M{EQ_WORLD_MAG}+ anywhere in the world')
        elif mag >= EQ_ROF_MAG and rf.in_rof(lat, lon) and coast_km(lat, lon) <= EQ_ROF_KM: why.append(f'M{EQ_ROF_MAG}+ on the Ring of Fire within {EQ_ROF_KM} km of the Oregon coast')
        if not why: continue
        out.append(dict(id=f['id'], mag=round(mag, 1), lat=lat, lon=lon, depth=dep or 0, place=p.get('place') or '', km=d,
                        t=iso(dt.datetime.fromtimestamp(p['time'] / 1000, UTC)), url=p.get('url'), tsunami=p.get('tsunami'),
                        felt=p.get('felt'), why='; '.join(why), status=p.get('status')))
    return out

def f_tsunami():
    out = []
    for a in rf.tsunami_alerts():
        cat = (a.get('category') or '').lower()
        if a.get('age_h', 999) > TSU_MAX_AGE_H: continue
        txt = (a.get('title', '') + ' ' + a.get('summary', '')).lower()
        west = a['center'] == 'NTWC' or any(w in txt for w in ('west coast', 'oregon', 'california', 'washington', 'british columbia'))
        if (west and cat in TSU_WEST_COAST_CATS) or (a['center'] == 'PTWC' and cat in TSU_PACIFIC_CATS):
            a['id'] = 'tsu:' + (a.get('url') or hashlib.sha1(f"{a['center']}|{a['t']}|{a['title']}".encode()).hexdigest()[:16])
            out.append(a)
    return out

def f_nws():
    seen = {}
    for params in ({'area': 'OR'}, {'point': f'{EUG[0]},{EUG[1]}'}, {'zone': NWS_ZONES}):
        r = pf.requests.get('https://api.weather.gov/alerts/active', params=params, headers=UA, timeout=pf.T); r.raise_for_status()
        for f in r.json()['features']:
            p = f['properties']
            if 'area' in params and NWS_SAME not in (p.get('geocode') or {}).get('SAME', []): continue
            if p.get('status') != 'Actual' or p.get('messageType') == 'Cancel': continue
            seen[p['id']] = dict(id=p['id'], event=p.get('event'), headline=p.get('headline') or p.get('event'), area=p.get('areaDesc'),
                                 severity=p.get('severity'), sent=p.get('sent'), ends=p.get('ends') or p.get('expires'), mtype=p.get('messageType'),
                                 refs=[x.get('identifier') for x in p.get('references') or []], desc=(p.get('description') or '')[:700],
                                 url=f"https://api.weather.gov/alerts/{p['id']}")
    return list(seen.values())

def f_power():
    """Per-outage list for the 4 utilities + per-utility totals. One failing utility raises only for itself."""
    res = {}
    def eweb():
        j = pf._get('https://services7.arcgis.com/6AM8yPAeyXiPc9eF/arcgis/rest/services/PublicOutageMap_Public_View/FeatureServer/0/query',
                    params=dict(where='1=1', outFields='OBJECTID,incidentid,custcnt,ostart,etor,name,cause,status', returnGeometry='false', f='json')).json()
        if 'features' not in j: raise ValueError('EWEB: no features key')
        o = [x['attributes'] for x in j['features'] if x['attributes'].get('status') != 'Restored']
        return [dict(id=f"eweb:{a.get('incidentid') or a['OBJECTID']}", cust=a.get('custcnt') or 0,
                     where=(f"near {a['name']}" if a.get('name') else ''), cause=a.get('cause'), etr=a.get('etor'), start=a.get('ostart')) for a in o]
    def nisc(slug, key, pref):
        d = pf._get(f'https://outagemap-data.cloud.coop/{slug}/Hosted_Outage_Map/summary.json').json()
        if 'outages' not in d: raise ValueError(f'{slug}: no outages key')
        sets = {s['id']: s['regions'] for s in d.get('regionDataSets', [])}
        regs = next((sets[k] for k in pref if k in sets), [])
        hit = sorted([r for r in regs if (r.get('numberOut') or 0) > 0], key=lambda r: -r['numberOut'])
        area = f"in the {hit[0]['id'].title()} area" if hit else ''
        return [dict(id=f"{key}:{x.get('id')}", cust=x.get('nbrOut') or 0, where=area, cause='planned work' if x.get('planned') else None, etr=None,
                     start=iso(dt.datetime.fromtimestamp(x['timeOff'] / 1000, UTC)) if x.get('timeOff') else None) for x in d['outages']]
    def pacific():
        m = pf._get('https://www.pacificpower.net/etc/pcorp/datafiles/outagemap/mapOR.json').json()
        if 'outages' not in m: raise ValueError('Pacific: no outages key')
        out = []
        for x in m['outages']:
            mi = pf._mi(EUG, (x['latitude'], x['longitude']))
            if mi > PWR_NEAR_MI: continue
            town = pf._town(x['latitude'], x['longitude'])
            out.append(dict(id=f"pac:{x['latitude']:.3f},{x['longitude']:.3f}|{x.get('reported')}", cust=x.get('custOut') or 0,
                            where=f"near {town or 'ZIP ' + str(x.get('zip'))} (ZIP {x.get('zip')}), {mi:.0f} mi from Eugene", cause=x.get('cause'),
                            etr=x.get('etr'), start=x.get('reported')))
        return out
    jobs = {'eweb': eweb, 'epud': lambda: nisc('epud', 'epud', ['Territory', 'ZipCode']),
            'blachly': lambda: nisc('blachlylane', 'blachly', ['Cities', 'Substation']), 'pacific': pacific}
    for k, fn in jobs.items():
        try: res[k] = fn()
        except Exception as e: res[k] = None; log(f'feed failed: power/{k}: {type(e).__name__}: {str(e)[:150]}')
    return res

UTIL_NAME = {'eweb': 'EWEB', 'epud': 'Emerald PUD', 'blachly': 'Blachly-Lane', 'pacific': 'Pacific Power'}
UTIL_LINK = {'eweb': pf.LINKS['eweb'], 'epud': pf.LINKS['epud'], 'blachly': pf.LINKS['blachly'], 'pacific': pf.LINKS['pacific']}

def fetch_all():
    jobs = {'quakes': f_quakes, 'tsunami': f_tsunami, 'nws': f_nws, 'power': f_power}
    out = {}
    with ThreadPoolExecutor(4) as ex:
        fut = {k: ex.submit(fn) for k, fn in jobs.items()}
        for k, f in fut.items():
            try: out[k] = f.result(timeout=90)
            except Exception as e: out[k] = None; log(f'feed failed: {k}: {type(e).__name__}: {str(e)[:150]}')
    return out

# ----------------------------- state -----------------------------
def load_state():
    if not os.path.exists(STATE): return None
    try: return json.load(open(STATE))
    except Exception as e:
        log(f'state unreadable ({e}); backing up and re-seeding'); shutil.copy2(STATE, STATE + f'.bad.{int(time.time())}'); return None
def save_state(S):
    cut = NOW - dt.timedelta(days=EXPIRE_DAYS)
    for sec in ('quake', 'tsunami', 'nws', 'outage'):
        S[sec] = {k: v for k, v in S.get(sec, {}).items() if (parse(v.get('last_seen')) or NOW) >= cut}
    S['updated'] = iso(NOW)
    tmp = STATE + '.tmp'; os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(S, open(tmp, 'w'), indent=1, sort_keys=True); os.replace(tmp, STATE)

def signature(S):
    """State minus timestamps/counts: changes only when keys or alert flags change."""
    if S is None: return None
    drop = {'last_seen', 'cust', 'peak', 'where', 'first_seen'}
    return json.dumps({k: ({kk: {a: b for a, b in vv.items() if a not in drop} if isinstance(vv, dict) else vv for kk, vv in v.items()} if isinstance(v, dict) else v)
                       for k, v in S.items() if k not in ('updated', 'created')}, sort_keys=True, default=str)

# ----------------------------- detection -----------------------------
def nws_rank(ev): ev = (ev or '').lower(); return max([v for k, v in NWS_RANK.items() if k in ev] or [1])

def detect(D, S, seed=False):
    """Mutates state S; returns list of new items (dicts with kind, ...). In seed mode records everything, returns []."""
    new = []; now = iso(NOW); seeded = S.setdefault('seeded_feeds', []); all_seed = seed
    def sd(feed):   # a feed that has never been fetched successfully is seeded silently on its first success
        if feed not in seeded: seeded.append(feed); return True
        return all_seed
    S.setdefault('quake', {}); S.setdefault('tsunami', {}); S.setdefault('nws', {}); S.setdefault('outage', {}); S.setdefault('util', {})
    if D.get('quakes') is not None:
        seed = sd('quakes')
        for q in D['quakes']:
            old = S['quake'].get(q['id'])
            if old is None:
                S['quake'][q['id']] = dict(mag=q['mag'], first_seen=now, last_seen=now, seeded=seed)
                if not seed: new.append(dict(kind='quake', **q))
            else:
                old['last_seen'] = now
                if not seed and q['mag'] >= old['mag'] + EQ_REVISE_MAG:
                    new.append(dict(kind='quake', revised_from=old['mag'], **q))
                old['mag'] = max(old['mag'], q['mag'])
    if D.get('tsunami') is not None:
        seed = sd('tsunami')
        for a in D['tsunami']:
            old = S['tsunami'].get(a['id'])
            if old is None:
                S['tsunami'][a['id']] = dict(cat=a['category'], title=a['title'][:120], first_seen=now, last_seen=now, seeded=seed)
                if not seed: new.append(dict(kind='tsunami', **a))
            else: old['last_seen'] = now
    if D.get('nws') is not None:
        seed = sd('nws')
        for a in D['nws']:
            old = S['nws'].get(a['id'])
            if old is not None: old['last_seen'] = now; continue
            prior = [S['nws'][r] for r in a['refs'] if r in S['nws']]
            S['nws'][a['id']] = dict(event=a['event'], first_seen=now, last_seen=now, seeded=seed, refs=a['refs'][-3:])
            if seed: continue
            if not prior: new.append(dict(kind='nws', change='new', **a)); continue
            pe = max(prior, key=lambda p: nws_rank(p['event']))['event']
            if nws_rank(a['event']) > nws_rank(pe): new.append(dict(kind='nws', change='upgrade', prev_event=pe, **a))
            elif a['event'] != pe: new.append(dict(kind='nws', change='changed', prev_event=pe, **a))
            else: log(f"nws update (same event, no alert): {a['event']} {a['id'][-24:]}")
    P = D.get('power') or {}
    for u, items in P.items():
        if items is None: continue                       # feed failed: leave state alone
        seed = sd('power:' + u)
        cur = {i['id']: i for i in items}
        for i in items:
            old = S['outage'].get(i['id'])
            if old is None and i['cust'] < PWR_NEW_OUTAGE: continue   # small outages aren't tracked (keeps state stable)
            if old is None:
                S['outage'][i['id']] = old = dict(util=u, cust=i['cust'], peak=i['cust'], first_seen=now, last_seen=now,
                                                  alerted=False, seeded_big=seed and i['cust'] >= PWR_NEW_OUTAGE, where=i['where'])
            else:
                old.update(last_seen=now, cust=i['cust'], peak=max(old.get('peak', 0), i['cust']), where=i['where'] or old.get('where'))
            if not seed and i['cust'] >= PWR_NEW_OUTAGE and not old['alerted'] and not old.get('seeded_big'):
                old['alerted'] = True; new.append(dict(kind='outage', util=u, **i))
        for k, old in list(S['outage'].items()):         # cleared outages
            if old.get('util') != u or k in cur: continue
            if old.get('alerted') and not seed:
                new.append(dict(kind='restored', util=u, id=k, peak=old.get('peak'), where=old.get('where'), since=old.get('first_seen')))
            del S['outage'][k]
        tot = sum(i['cust'] for i in items); us = S['util'].setdefault(u, dict(high=False, alerted=False))
        us['cust'] = tot; us['last_seen'] = now
        if not us['high'] and tot > PWR_UTIL_TOTAL:
            us['high'] = True; us['alerted'] = not seed
            if not seed: new.append(dict(kind='util_high', util=u, cust=tot, n=len(items)))
        elif us['high'] and tot < PWR_UTIL_CLEAR:
            if us.get('alerted') and not seed: new.append(dict(kind='util_clear', util=u, cust=tot))
            us['high'] = False; us['alerted'] = False
    return new

# ----------------------------- writing -----------------------------
def quake_where(q):
    if q['km'] <= EQ_REGION_KM: return f"{km_to_mi(q['km']):.0f} mi {bearing(EUG, (q['lat'], q['lon']))} of Eugene"
    return eq_map.short_place(q['place']) or f"{q['lat']:.1f}, {q['lon']:.1f}"

def headline(i):
    k = i['kind']
    if k == 'quake': return f"M{i['mag']:.1f} quake {quake_where(i)}"
    if k == 'tsunami': return f"Tsunami {i['category'].lower()} ({i['center']})"
    if k == 'nws': return (f"{i['event']} (upgraded from {i['prev_event']})" if i['change'] == 'upgrade' else i['event']) + ' for Lane County'
    if k == 'outage': return f"{UTIL_NAME[i['util']]} outage, {i['cust']:,} customers"
    if k == 'util_high': return f"{i['cust']:,} {UTIL_NAME[i['util']]} customers out"
    if k == 'restored': return f"{UTIL_NAME[i['util']]} outage restored"
    if k == 'util_clear': return f"{UTIL_NAME[i['util']]} mostly back on"
PRIO = {'tsunami': 0, 'quake': 1, 'nws': 2, 'util_high': 3, 'outage': 4, 'util_clear': 5, 'restored': 6}

def body_lines(items):
    L = []; by = lambda *ks: [i for i in items if i['kind'] in ks]
    ts = by('tsunami')
    if ts:
        L.append('## Tsunami')
        for a in ts:
            L.append(f"- **Tsunami {a['category'].upper()}** from NOAA {'National (US West Coast/Alaska)' if a['center'] == 'NTWC' else 'Pacific'} Tsunami Warning Center: {a['title']}")
            L.append(f"  - Issued {ptime(parse(a['t']))}" + (f", quake M{a['mag']}" if a.get('mag') else '') + f". Details: {a['url'] or 'https://www.tsunami.gov'}")
        L.append('- Live status: https://www.tsunami.gov'); L.append('')
    qs = sorted(by('quake'), key=lambda q: -q['mag'])
    if qs:
        L.append('## Earthquake' + ('s' if len(qs) > 1 else ''))
        for q in qs:
            t = parse(q['t'])
            L.append(f"- **M{q['mag']:.1f}** {q['place']} — {quake_where(q) if q['km'] <= EQ_REGION_KM else f'{km_to_mi(q['km']):,.0f} mi from Eugene'}" +
                     (f" (USGS raised it from M{q['revised_from']:.1f})" if q.get('revised_from') else ''))
            L.append(f"  - {ptime(t)}, {q['depth']:.0f} km deep" + (f", felt by {q['felt']:,} people so far" if q.get('felt') else '') +
                     ('. USGS tsunami flag is set — check https://www.tsunami.gov' if q.get('tsunami') else ''))
            L.append(f"  - Why you're getting this: {q['why']}. USGS page: {q['url']}")
        L.append('- Map below: dots sized by strength, coloured by depth; Eugene is the green star.'); L.append('')
    ws = by('nws')
    if ws:
        L.append('## Weather alerts (National Weather Service)')
        for a in ws:
            tag = {'new': 'New', 'upgrade': f"Upgraded from {a.get('prev_event')}", 'changed': f"Changed from {a.get('prev_event')}"}[a['change']]
            ends = parse(a.get('ends'))
            L.append(f"- **{a['event']}** — {tag}. {a['headline']}")
            L.append(f"  - Area: {a['area']}" + (f". In effect until {ptime(ends)}" if ends else ''))
            what = ' '.join(a['desc'].replace('* ', '').replace('...', ': ').split())
            if what: L.append(f"  - {what[:400]}{'…' if len(what) > 400 else ''}")
            L.append(f"  - Full text: {a['url']}")
        L.append('- All active alerts for Eugene: https://forecast.weather.gov/MapClick.php?lat=44.05&lon=-123.09'); L.append('')
    ps = by('util_high', 'outage', 'util_clear', 'restored')
    if ps:
        L.append('## Power')
        for i in ps:
            n = UTIL_NAME[i['util']]; link = UTIL_LINK[i['util']]
            if i['kind'] == 'outage':
                L.append(f"- **{n}: new outage, {i['cust']:,} customers out**" + (f" {i['where']}" if i['where'] else '') +
                         (f". Cause: {i['cause'].lower()}" if i.get('cause') else '') + (f". Expected back {i['etr']}" if i.get('etr') else '') + f". Map: {link}")
            elif i['kind'] == 'util_high': L.append(f"- **{n}: {i['cust']:,} customers out in total** across {i['n']} outage{'s' if i['n'] != 1 else ''} (over {PWR_UTIL_TOTAL}). Map: {link}")
            elif i['kind'] == 'restored': L.append(f"- Restored: the {n} outage" + (f" {i['where']}" if i.get('where') else '') + f" (peak {i.get('peak') or 0:,} customers) is off the outage map.")
            elif i['kind'] == 'util_clear': L.append(f"- {n} is mostly back: {i['cust']:,} customers still out (under {PWR_UTIL_CLEAR}).")
        L.append('')
    L.append(f"_Checked {ptime(NOW)}. Sources: USGS, NOAA tsunami.gov (PTWC/NTWC), National Weather Service, EWEB, Emerald PUD, Blachly-Lane, Pacific Power outage maps. "
             'You get these only when something new crosses a threshold; the full picture is in the morning report._')
    return L

def render_map(qs, path):
    """Small map centred on the biggest new quake, reusing eq_map's basemap, depth colours, sizes and Ring of Fire lines."""
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    B = eq_map._data('eqmap_base.json'); P = eq_map._data('plates_rof.json')
    q0 = max(qs, key=lambda q: q['mag']); lat0, lon0 = q0['lat'], q0['lon']
    near = q0['km'] <= EQ_REGION_KM
    half = 2.6 if near and q0['mag'] < 4.5 else 4.5 if near else 22
    wrap = lambda lo: ((lo - lon0 + 180) % 360) - 180 + lon0
    land, sea, edge = '#ece6d6', '#dbe9f4', '#9a9282'
    fig, ax = plt.subplots(figsize=(6.4, 5.0), dpi=100); ax.set_facecolor(sea)
    cosl = math.cos(math.radians(max(-70, min(70, lat0))))
    x0, x1, y0, y1 = lon0 - half / cosl, lon0 + half / cosl, lat0 - half * 0.75, lat0 + half * 0.75
    rings = B['pnw_land'] if near else B['world_land']
    for r in rings:
        xs, ys = zip(*r)
        if near: ax.fill(xs, ys, color=land, ec=edge, lw=0.6, zorder=1)
        else:
            for off in (-360, 0, 360): ax.fill([x + off for x in xs], ys, color=land, ec=edge, lw=0.4, zorder=1)
    if near:
        for r in B['pnw_states']: ax.plot(*zip(*r), color='#b5ab98', lw=0.7, zorder=2)
    for seg in P['ring']:
        ys, xs = zip(*seg['p']); xs = [wrap(x) for x in xs]; cur = [[], []]
        for x, y in zip(xs, ys):
            if cur[0] and abs(x - cur[0][-1]) > 180: ax.plot(*cur, color='#c0392b', lw=1.1, alpha=0.5, zorder=3); cur = [[], []]
            cur[0].append(x); cur[1].append(y)
        ax.plot(*cur, color='#c0392b', lw=1.1, alpha=0.5, zorder=3)
    for q in sorted(qs, key=lambda q: q['mag']):
        ax.scatter(wrap(q['lon']), q['lat'], s=eq_map.dsize(q['mag'], 22 if near else 9), c=eq_map.dcol(q['depth']), edgecolors='black',
                   linewidths=1.8 if q is q0 else 0.6, alpha=0.88, zorder=6)
        ax.annotate(f"M{q['mag']:.1f}", (wrap(q['lon']), q['lat']), xytext=(8, 6), textcoords='offset points', fontsize=10, weight='bold', zorder=8,
                    annotation_clip=True, bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='#333', lw=0.6))
    ex, ey = wrap(EUG[1]), EUG[0]
    ax.plot(ex, ey, marker='*', ms=15, color='#1b7837', mec='white', mew=1, zorder=9)
    ax.annotate('Eugene', (ex, ey), xytext=(7, -12), textcoords='offset points', fontsize=9.5, weight='bold', color='#1b7837', zorder=9, annotation_clip=True)
    if near:
        for nm, la, lo in [('Portland', 45.52, -122.68), ('Salem', 44.94, -123.03), ('Corvallis', 44.56, -123.26), ('Bend', 44.06, -121.31),
                           ('Roseburg', 43.22, -123.34), ('Medford', 42.33, -122.87), ('Coos Bay', 43.37, -124.22), ('Newport', 44.64, -124.05),
                           ('Seattle', 47.61, -122.33), ('Eureka', 40.80, -124.16), ('Klamath Falls', 42.22, -121.78)]:
            if x0 < lo < x1 and y0 < la < y1:
                ax.plot(lo, la, 'o', ms=2.8, color='#444', zorder=4); ax.text(lo + 0.05, la + 0.05, nm, fontsize=7.5, color='#444', zorder=4, clip_on=True)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect(1 / cosl); ax.set_xticks([]); ax.set_yticks([])
    t = parse(q0['t'])
    ax.set_title(f"M{q0['mag']:.1f} {eq_map.short_place(q0['place'])[:48]}\n{ptime(t)} · {q0['depth']:.0f} km deep · {km_to_mi(q0['km']):,.0f} mi from Eugene",
                 fontsize=10.5, weight='bold')
    h = [Line2D([], [], ls='', marker='o', ms=8, mfc=c, mec='#333', label=lab) for _, c, lab in eq_map.DEPTH]
    h += [Line2D([], [], color='#c0392b', lw=1.5, alpha=0.6, label='Ring of Fire plate boundary'), Line2D([], [], ls='', marker='*', ms=11, color='#1b7837', label='Eugene')]
    ax.legend(handles=h, loc='lower left', fontsize=7, framealpha=0.9)
    fig.text(0.5, 0.01, 'Bigger dot = stronger quake; colour = depth. Times Pacific (PT). Source: USGS.', ha='center', fontsize=7.5, color='#333')
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(path, dpi=100, facecolor='white'); plt.close(fig)
    return path

def write_alert(items, suffix=''):
    items = sorted(items, key=lambda i: (PRIO[i['kind']], -(i.get('mag') or i.get('cust') or 0)))
    stamp = dt.datetime.now(PT).strftime('%Y%m%d_%H%M') + suffix
    subj = 'Eugene alert: ' + headline(items[0]) + (f" + {len(items) - 1} more" if len(items) > 1 else '')
    if all(i['kind'] in ('restored', 'util_clear') for i in items): subj = 'Eugene update: ' + headline(items[0]) + (f" + {len(items) - 1} more" if len(items) > 1 else '')
    md = [subj, ''] + body_lines(items)
    os.makedirs(REPORTS, exist_ok=True)
    mdp = os.path.join(REPORTS, f'alert_{stamp}.md'); open(mdp, 'w').write('\n'.join(md) + '\n')
    att = '-'; qs = [i for i in items if i['kind'] == 'quake']
    if qs:
        name = f'alert_map_{stamp}.png'
        try:
            p = render_map(qs, os.path.join(REPORTS, name)); os.makedirs(ATTACH, exist_ok=True)
            if os.path.abspath(ATTACH) != os.path.abspath(REPORTS): shutil.copy2(p, os.path.join(ATTACH, name))
            att = name
        except Exception as e: log(f'map failed: {type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}')
    htp = os.path.join(REPORTS, f'alert_{stamp}.html')
    open(htp, 'w').write(eq_map.md_to_html('\n'.join(md[2:]), None if att == '-' else att, subj)
                         .replace("Map of where today's earthquakes hit", 'Map of the new earthquake'))
    return mdp, htp, att

def fake_items():
    t = NOW - dt.timedelta(minutes=12)
    return [dict(kind='quake', id='test_q1', mag=4.1, lat=44.30, lon=-122.65, depth=12.0, place='14 km NE of Leaburg, Oregon (TEST)',
                 km=eq_map.km(EUG, (44.30, -122.65)), t=iso(t), url='https://earthquake.usgs.gov/earthquakes/map/', tsunami=0, felt=212,
                 why=f'M{EQ_NEAR_MAG}+ within {EQ_NEAR_KM} km of Eugene (TEST EVENT)'),
            dict(kind='quake', id='test_q2', mag=3.2, lat=44.12, lon=-122.85, depth=8.0, place='9 km SE of Walterville, Oregon (TEST)',
                 km=eq_map.km(EUG, (44.12, -122.85)), t=iso(t - dt.timedelta(minutes=20)), url='https://earthquake.usgs.gov/earthquakes/map/', tsunami=0,
                 felt=None, why=f'M{EQ_NEAR_MAG}+ within {EQ_NEAR_KM} km of Eugene (TEST EVENT)'),
            dict(kind='outage', util='eweb', id='eweb:test', cust=430, where='near Santa Clara (TEST)', cause='Tree on line', etr='about 2:30 PM', start=None),
            dict(kind='nws', change='upgrade', prev_event='Wind Advisory', id='test', event='High Wind Warning',
                 headline='High Wind Warning issued by NWS Portland OR (TEST)', area='Lane County Lowlands', severity='Severe',
                 sent=iso(t), ends=iso(NOW + dt.timedelta(hours=10)), mtype='Update', refs=[], desc='* WHAT...South winds 25 to 35 mph with gusts up to 60 mph. (TEST EVENT)',
                 url='https://alerts.weather.gov/'),
            dict(kind='restored', util='epud', id='epud:test', peak=75, where='in the Junction City area (TEST)', since=None)]

def main():
    a = sys.argv[1:]
    if '--test' in a:
        mdp, htp, att = write_alert(fake_items(), suffix='_test'); print(f'ALERT {mdp} {htp} {att}'); return 0
    t0 = time.time(); D = fetch_all(); S = load_state()
    sig0 = signature(S); stale = S is None or (NOW - (parse(S.get('updated')) or NOW)).total_seconds() > STATE_REFRESH_H * 3600
    seed = S is None or '--seed' in a
    if seed: S = dict(created=iso(NOW))
    new = detect(D, S, seed=seed)
    ok = {k: ('fail' if v is None else (','.join(f"{u}:{'fail' if x is None else len(x)}" for u, x in v.items()) if k == 'power' else len(v))) for k, v in D.items()}
    log(f"{'SEED' if seed else 'run'} {time.time() - t0:.1f}s feeds={ok} new={len(new)}" + (f" [{'; '.join(headline(i) for i in new)}]" if new else ''))
    if DIRTY_FILE:
        open(DIRTY_FILE, 'w').write('1' if (new or stale or signature(S) != sig0) else '0')
    if new:
        mdp, htp, att = write_alert(new)
        if '--dry-run' not in a: save_state(S)
        print(f'ALERT {mdp} {htp} {att}')
    else:
        if '--dry-run' not in a: save_state(S)
        print('NONE')
    return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as e:   # never crash loudly / never alert on our own failure
        log(f'fatal: {type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}'); print('NONE'); sys.exit(0)
