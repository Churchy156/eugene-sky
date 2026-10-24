#!/usr/bin/env python3
"""Sports games within 100 miles of Eugene (44.05N, -123.09W, haversine).

  python zip_tools/build_sports.py --history RAWDIR   # one-off full rebuild from raw caches
  python zip_tools/build_sports.py                    # CI: refresh current ESPN + MiLB seasons

Writes data/sports_games_100mi.csv (one row per game) and merges daily columns into
data/eugene_env_daily.csv.gz (+ column_dictionary.csv).  Never fatal in CI.
"""
import sys, os, io, re, glob, json, math, argparse, datetime as dt
import pandas as pd, numpy as np
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(HERE, 'data', 'sports_games_100mi.csv')
DAILY = os.path.join(HERE, 'data', 'eugene_env_daily.csv.gz')
DICT = os.path.join(HERE, 'column_dictionary.csv')
LAT0, LON0, RADIUS = 44.05, -123.09, 100.0
PT = 'America/Los_Angeles'
STATES = {'Oregon':'OR','Washington':'WA','California':'CA','Idaho':'ID','Arizona':'AZ','Utah':'UT','Colorado':'CO','Nevada':'NV','Texas':'TX','Hawaii':'HI','Montana':'MT','Wyoming':'WY','New Mexico':'NM','Nebraska':'NE','Michigan':'MI','Ohio':'OH','Illinois':'IL','Indiana':'IN','Wisconsin':'WI','Minnesota':'MN','Iowa':'IA','Missouri':'MO','Kansas':'KS','Oklahoma':'OK','Louisiana':'LA','Tennessee':'TN','Georgia':'GA','Florida':'FL','Alabama':'AL','New York':'NY','Pennsylvania':'PA','New Jersey':'NJ','Massachusetts':'MA','Maryland':'MD','Virginia':'VA','North Carolina':'NC','South Carolina':'SC','Kentucky':'KY','Arkansas':'AR','Mississippi':'MS','Connecticut':'CT','Rhode Island':'RI','Indiana':'IN','District of Columbia':'DC','Alaska':'AK'}
# hard-coded venues (lat, lon) -- campus stadia/arenas and ballparks inside the radius
VENUES = {
 'Autzen Stadium':(44.0582,-123.0685), 'Hayward Field':(44.0425,-123.0703),
 'Matthew Knight Arena':(44.0451,-123.0662), 'McArthur Court':(44.0447,-123.0711),
 'Reser Stadium':(44.5595,-123.2811), 'Parker Stadium':(44.5595,-123.2811), 'Bell Field':(44.5626,-123.2787), 'Gill Coliseum':(44.5612,-123.2793),
 'PK Park':(44.0590,-123.0650), 'Civic Stadium':(44.0326,-123.0857),
 'Volcanoes Stadium':(45.0213,-123.0148),
}
CAMPUS = {'UO':(44.0451,-123.0662), 'OSU':(44.5612,-123.2793)}
# major Hayward Field meets (inclusive date ranges)
HAYWARD = [('1972-06-29','1972-07-09','US Olympic Trials'),('1976-06-19','1976-06-27','US Olympic Trials'),
 ('1980-06-21','1980-06-29','US Olympic Trials'),('2008-06-27','2008-07-06','US Olympic Trials'),
 ('2012-06-21','2012-07-01','US Olympic Trials'),('2016-07-01','2016-07-10','US Olympic Trials'),
 ('2021-06-18','2021-06-27','US Olympic Trials'),('2024-06-21','2024-06-30','US Olympic Trials'),
 ('2014-07-22','2014-07-27','World U20 Championships'),('2022-07-15','2022-07-24','World Athletics Championships')]

def hav(lat, lon, lat0=LAT0, lon0=LON0):
    r = 3958.8; p1, p2 = math.radians(lat0), math.radians(lat)
    dp, dl = p2-p1, math.radians(lon-lon0)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

_PL = None
def places():
    global _PL
    if _PL is None:
        d = {}
        for ln in open(os.path.join(HERE, 'data', 'us_places.tsv')):
            st, nm, la, lo = ln.rstrip('\n').split('\t')
            d.setdefault((st, nm.lower()), (float(la), float(lo)))
        _PL = d
    return _PL

def geocode(city, st):
    if not city or not st: return None
    st = STATES.get(st, st)
    return places().get((st, city.strip().lower()))

def num(x):
    """Attendance cell -> float. Handles '58,391', '8,000–9,000' (midpoint), footnotes; rejects implausible values."""
    s = re.sub(r'\[.*?\]', '', str(x))
    v = [float(n.replace(',', '')) for n in re.findall(r'\d[\d,]*', s) if n.replace(',', '').isdigit()]
    if not v: return np.nan
    a = v[0] if len(v) == 1 else (v[0] + v[1]) / 2
    return a if 100 <= a <= 120000 else np.nan

def parse_time(s):
    s = re.sub(r'\[.*?\]', '', str(s)).strip().lower().replace('.', '')
    m = re.match(r'(\d{1,2})(?::(\d\d))?\s*(am|pm|noon)?', s)
    if not m or 'tba' in s or 'tbd' in s: return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == 'pm' and h < 12: h += 12
    if m.group(3) == 'am' and h == 12: h = 0
    if 'noon' in s: h = 12
    if h > 23: return None
    return f'{h:02d}:{mi:02d}'

# ---------------------------------------------------------------- Wikipedia football
def site_city(site):
    s = re.sub(r'\[.*?\]', '', str(site)); s = re.sub(r'\(.*?\)', '', s).strip()
    s = re.sub(r'([a-z\.])([A-Z])', r'\1 \2', s)           # "StadiumEugene" -> "Stadium Eugene"
    m = re.search(r'^(.*?),\s*([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*$', s)
    if not m: return None, None, None, s
    head, st = m.group(1).split(), m.group(2)
    for k in (4, 3, 2, 1):
        if len(head) >= k:
            c = ' '.join(head[-k:]); ll = geocode(c, st)
            if ll: return c, STATES.get(st, st), ll, ' '.join(head[:-k])
    return None, STATES.get(st, st), None, s

def wiki_football(raw):
    out = []
    for f in sorted(glob.glob(os.path.join(raw, 'wiki', '*.html'))):
        team, yr = os.path.basename(f)[:-5].split('_'); yr = int(yr); TEAM = team.upper()
        try: tabs = pd.read_html(io.StringIO(open(f, encoding='utf-8').read()))
        except Exception: continue
        t = next((t for t in tabs if 'Date' in map(str, t.columns) and 'Opponent' in map(str, t.columns)), None)
        if t is None: continue
        t.columns = [str(c) for c in t.columns]
        for _, r in t.iterrows():
            ds = re.sub(r'\[.*?\]', '', str(r['Date'])).strip()
            ds = re.sub(r'^[A-Za-z]+,\s*', '', ds) if re.match(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)', ds) else ds
            try: d = pd.Timestamp(f'{ds} {yr}')
            except Exception: continue
            if d.month <= 2: d = d.replace(year=yr+1)
            opp = re.sub(r'\[.*?\]', '', str(r['Opponent'])).strip()
            if opp.lower().startswith('nan') or 'Opponent' in opp: continue
            away = opp.lower().startswith('at ')
            neutral = opp.lower().startswith('vs')
            opp_clean = re.sub(r'^(at|vs\.?)\s+', '', opp, flags=re.I); opp_clean = re.sub(r'^No\.\s*\d+\s+', '', opp_clean)
            city, st, ll, venue = site_city(r.get('Site', ''))
            if ll is None:
                if not away and not neutral: ll = CAMPUS[TEAM]; city = 'Eugene' if TEAM=='UO' else 'Corvallis'; st='OR'
                else: continue
            ll = next((VENUES[k] for k in VENUES if k.lower() in venue.lower()), ll)
            dist = hav(*ll)
            if dist > RADIUS: continue
            host = TEAM if (not away and not neutral) else ('OSU' if city=='Corvallis' else 'UO' if city=='Eugene' else 'neutral')
            out.append(dict(date=d.date().isoformat(), sport='football', level='NCAA FBS', host=host,
                team=TEAM, opponent=opp_clean, venue=venue.strip(), city=city, state=st, lat=round(ll[0],4), lon=round(ll[1],4),
                dist_mi=round(dist,1), kickoff_local=parse_time(r.get('Time','')) or '', time_tba=int(parse_time(r.get('Time','')) is None),
                attendance=num(r.get('Attendance', np.nan)), source='Wikipedia season page'))
    return out

# ---------------------------------------------------------------- ESPN team schedules
def espn_event_rows(e, TEAM, sport):
    rows = []
    c = e['competitions'][0]
    ts = pd.Timestamp(c.get('date') or e['date'])
    valid = c.get('timeValid', True)
    if valid: lt = ts.tz_convert(PT); d = lt.date(); ko = lt.strftime('%H:%M')
    else: d = ts.tz_convert('America/New_York').date(); ko = ''   # TBA placeholder = midnight ET
    v = c.get('venue') or {}; addr = v.get('address') or {}
    me = next((x for x in c['competitors'] if str(x['id']) in ('2483','204')), None)
    opp = next((x for x in c['competitors'] if x is not me), {})
    home = me is not None and me.get('homeAway') == 'home' and not c.get('neutralSite')
    vn = v.get('fullName', '')
    ll = next((VENUES[k] for k in VENUES if k.lower() in vn.lower()), None) or geocode(addr.get('city'), addr.get('state'))
    if ll is None and home: ll = CAMPUS[TEAM]
    if ll is None: return rows
    dist = hav(*ll)
    if dist > RADIUS: return rows
    host = TEAM if home else ('OSU' if (addr.get('city')=='Corvallis') else 'UO' if addr.get('city')=='Eugene' else 'neutral')
    att = c.get('attendance') or np.nan
    rows.append(dict(date=d.isoformat(), sport=sport, level='NCAA D1', host=host, team=TEAM,
        opponent=(opp.get('team') or {}).get('displayName', ''), venue=vn, city=addr.get('city', ''), state=addr.get('state', ''),
        lat=round(ll[0],4), lon=round(ll[1],4), dist_mi=round(dist,1), kickoff_local=ko, time_tba=int(not valid),
        attendance=float(att) if att and 100 <= float(att) <= 120000 else np.nan, source='ESPN team schedule'))
    return rows

ESPN_SPORT = {'cfb':('football','college-football'), 'mbb':('mens_basketball','mens-college-basketball'),
              'wbb':('womens_basketball','womens-college-basketball')}
def espn_files(raw, which=('mbb','wbb'), min_season=2002):
    out = []
    for f in sorted(glob.glob(os.path.join(raw, 'espn', '*.json'))):
        sp, tid, season, st = os.path.basename(f)[:-5].split('_')
        if sp not in which or int(season) < min_season: continue
        TEAM = 'UO' if tid == '2483' else 'OSU'
        try: j = json.load(open(f))
        except Exception: continue
        for e in j.get('events', []):
            try: out += espn_event_rows(e, TEAM, ESPN_SPORT[sp][0])
            except Exception: pass
    return out

def espn_live(seasons):
    import requests
    out = []
    for sp, (name, path) in ESPN_SPORT.items():
        for tid, TEAM in (('2483','UO'), ('204','OSU')):
            for season in seasons:
                for stype in (2, 3):
                    try:
                        j = requests.get(f'https://site.api.espn.com/apis/site/v2/sports/football/{path}/teams/{tid}/schedule' if sp=='cfb' else
                                         f'https://site.api.espn.com/apis/site/v2/sports/basketball/{path}/teams/{tid}/schedule',
                                         params={'season':season,'seasontype':stype}, timeout=30).json()
                        for e in j.get('events', []): out += espn_event_rows(e, TEAM, name)
                    except Exception as ex: print('espn', sp, tid, season, stype, ex)
    return out

# ---------------------------------------------------------------- Sports-Reference men's basketball (pre-2002)
HOME_ARENAS = {'McArthur Court':'UO', 'Gill Coliseum':'OSU', 'Matthew Knight Arena':'UO'}
def sr_mbb(raw, max_season=2001):
    out = []
    for f in sorted(glob.glob(os.path.join(raw, 'sr', '*.html'))):
        sch, season = os.path.basename(f)[:-5].rsplit('_', 1); season = int(season)
        if season > max_season: continue
        TEAM = 'UO' if sch == 'oregon' else 'OSU'
        try: tabs = pd.read_html(io.StringIO(open(f, encoding='utf-8', errors='ignore').read()))
        except Exception: continue
        t = next((t for t in tabs if 'Date' in t.columns and 'Opponent' in t.columns), None)
        if t is None: continue
        loc = 'Unnamed: 3' if 'Unnamed: 3' in t.columns else None
        for _, r in t.iterrows():
            try: d = pd.Timestamp(str(r['Date']))
            except Exception: continue
            where = str(r[loc]) if loc else 'nan'; arena = str(r.get('Arena', 'nan'))
            if arena in HOME_ARENAS: ll = VENUES[arena]; host = HOME_ARENAS[arena]
            elif where == 'nan' and arena == 'nan': ll = CAMPUS[TEAM]; host = TEAM; arena = ''
            else: continue
            dist = hav(*ll)
            out.append(dict(date=d.date().isoformat(), sport='mens_basketball', level='NCAA D1', host=host, team=TEAM,
                opponent=str(r['Opponent']), venue=arena, city='Eugene' if host=='UO' else 'Corvallis', state='OR',
                lat=ll[0], lon=ll[1], dist_mi=round(dist,1), kickoff_local='', time_tba=1, attendance=np.nan,
                source='Sports-Reference CBB'))
    return out

# ---------------------------------------------------------------- MiLB (MLB StatsAPI)
MILB_VENUES = {'PK Park':'PK Park', 'Civic Stadium':'Civic Stadium', 'Volcanoes Stadium':'Volcanoes Stadium'}
MILB_TEAMS = {461:'Eugene Emeralds', 578:'Salem-Keizer Volcanoes'}
def milb_rows(j, tid):
    out = []
    for dd in j.get('dates', []):
        for g in dd.get('games', []):
            if g.get('gameType') not in ('R', 'F', 'D', 'L', 'W'): continue
            if (g.get('status') or {}).get('detailedState', '') in ('Postponed', 'Cancelled'): continue
            if g['teams']['home']['team']['id'] != tid: continue
            vn = (g.get('venue') or {}).get('name', '')
            key = next((MILB_VENUES[k] for k in MILB_VENUES if k.lower() in vn.lower()), None)
            if key is None and vn.lower() in ('volcano stadium', 'keizer stadium'): key = 'Volcanoes Stadium'
            if key is None: continue
            ll = VENUES[key]; dist = hav(*ll)
            ts = pd.Timestamp(g['gameDate']); lt = ts.tz_convert(PT)
            tba = (g.get('status') or {}).get('startTimeTBD', False)
            d = dd.get('date') or lt.date().isoformat()
            out.append(dict(date=d, sport='minor_league_baseball', level='MiLB', host=MILB_TEAMS[tid], team=MILB_TEAMS[tid],
                opponent=g['teams']['away']['team'].get('name', ''), venue=vn, city='Eugene' if tid==461 else 'Keizer', state='OR',
                lat=ll[0], lon=ll[1], dist_mi=round(dist,1), kickoff_local='' if tba else lt.strftime('%H:%M'), time_tba=int(bool(tba)),
                attendance=np.nan, source='MLB StatsAPI', game_pk=g.get('gamePk')))
    return out

def milb_files(raw):
    out = []
    for f in sorted(glob.glob(os.path.join(raw, 'milb', '*.json'))):
        tid = int(os.path.basename(f).split('_')[0])
        try: out += milb_rows(json.load(open(f)), tid)
        except Exception: pass
    return out

def milb_live(years):
    import requests
    out = []
    for tid in MILB_TEAMS:
        for y in years:
            try:
                j = requests.get('https://statsapi.mlb.com/api/v1/schedule', params={'teamId':tid,'season':y,'sportIds':'11,12,13,14,15,16',
                    'gameType':'R,F,D,L,W'}, timeout=30).json()
                out += milb_rows(j, tid)
            except Exception as ex: print('milb', tid, y, ex)
    return out

def hayward_rows():
    out = []
    for a, b, name in HAYWARD:
        for d in pd.date_range(a, b):
            out.append(dict(date=d.date().isoformat(), sport='track_meet', level='major', host='Hayward Field', team='',
                opponent=name, venue='Hayward Field', city='Eugene', state='OR', lat=VENUES['Hayward Field'][0],
                lon=VENUES['Hayward Field'][1], dist_mi=round(hav(*VENUES['Hayward Field']),1), kickoff_local='', time_tba=1,
                attendance=np.nan, source='hard-coded meet dates'))
    return out

KICKOFF_OVERRIDES = {('2026-10-31', 'UO', 'football'): '12:30'}  # UO release 2026-10-19, Peacock
# ---------------------------------------------------------------- assemble
COLS = ['date','sport','level','host','team','opponent','venue','city','state','lat','lon','dist_mi','kickoff_local','time_tba','attendance','source','game_pk']
def dedupe(df):
    df = df.copy(); df['_k'] = df['date'] + '|' + df['sport'] + '|' + df['city'].fillna('') + '|' + df['host']
    # prefer row with attendance / known kickoff; MiLB doubleheaders keep both (distinct game_pk)
    df['_q'] = df['attendance'].notna().astype(int)*2 + (df['kickoff_local'].fillna('') != '').astype(int)
    if 'game_pk' in df:
        df['game_pk'] = pd.to_numeric(df['game_pk'], errors='coerce').astype('Int64')
        df['_k'] = np.where(df['game_pk'].notna(), df['_k'] + '|' + df['game_pk'].astype(str), df['_k'])
    df = df.sort_values(['_q','_k'], ascending=[False,True], kind='mergesort').drop_duplicates('_k').drop(columns=['_k','_q'])
    df['_o'] = df['opponent'].fillna('').astype(str); df['_h'] = df['host'].fillna('').astype(str)
    return df.sort_values(['date','sport','_h','_o','kickoff_local'], kind='mergesort', na_position='first').drop(columns=['_o','_h']).reset_index(drop=True)

# coverage start per series (column is blank before this)
COVER = {'ducks_home_football':'1950-01-01','osu_home_football':'1950-01-01','major_home_game':'1950-01-01',
         'ducks_home_mbb':'1950-11-01','osu_home_mbb':'1950-11-01','ducks_home_wbb':'2001-11-01','osu_home_wbb':'2001-11-01',
         'milb_home_games':'2005-01-01','hayward_major_meet':'1950-01-01','games_within_100mi':'1950-01-01',
         'football_attendance_100mi':'1950-01-01','est_attendance_100mi':'1950-01-01','football_kickoff_hour':'1950-01-01'}
DESC = {
 'games_within_100mi':'Count of covered sports events at venues within 100 mi (haversine) of Eugene that day: UO/OSU football (1950+), UO/OSU men\'s basketball (1950-51+), UO/OSU women\'s basketball (2001-02+), Emeralds/Volcanoes MiLB home games (2005+), major Hayward Field meets. Source mix grows over time.',
 'ducks_home_football':'1 if Oregon Ducks football home game at Autzen (or Hayward/Multnomah-in-radius) that day (Wikipedia 1950+, ESPN refresh)',
 'osu_home_football':'1 if Oregon State football home game in Corvallis that day (Wikipedia 1950+, ESPN refresh)',
 'major_home_game':'1 if Ducks or Beavers home football game within 100 mi that day',
 'ducks_home_mbb':'1 if Oregon men\'s basketball home game (Sports-Reference <=2001, ESPN 2002+)',
 'osu_home_mbb':'1 if Oregon State men\'s basketball home game (Sports-Reference <=2001, ESPN 2002+)',
 'ducks_home_wbb':'1 if Oregon women\'s basketball home game (ESPN, 2001-02 season+)',
 'osu_home_wbb':'1 if Oregon State women\'s basketball home game (ESPN, 2001-02 season+)',
 'milb_home_games':'Eugene Emeralds + Salem-Keizer Volcanoes home games in-radius (MLB StatsAPI, 2005+; Volcanoes through 2019; no 2020 season)',
 'hayward_major_meet':'1 on days of US Olympic Trials (1972/76/80/2008/12/16/21/24), 2014 World U20s, 2022 World Championships at Hayward Field',
 'football_attendance_100mi':'Reported attendance summed over UO/OSU football games within 100 mi that day (Wikipedia/ESPN); blank if no game or not reported',
 'est_attendance_100mi':'Sum of reported attendance over all covered games within 100 mi (football 1950+, ESPN men\'s/women\'s basketball 2002+; MiLB and meets not included); partial, blank if none reported',
 'football_kickoff_hour':'Local (PT) kickoff hour, decimal, of the earliest in-radius UO/OSU football game that day; blank if no game or time unknown/TBA',
}
def daily_from_games(g):
    g = g.copy(); g['date'] = pd.to_datetime(g['date'])
    idx = pd.date_range('1950-01-01', g['date'].max())
    D = pd.DataFrame(index=idx)
    fb = g[g.sport=='football']
    D['ducks_home_football'] = fb[fb.host=='UO'].groupby('date').size().reindex(idx).fillna(0).clip(upper=1)
    D['osu_home_football'] = fb[fb.host=='OSU'].groupby('date').size().reindex(idx).fillna(0).clip(upper=1)
    D['major_home_game'] = ((D.ducks_home_football + D.osu_home_football) > 0).astype(int)
    for sp, a in (('mens_basketball','mbb'), ('womens_basketball','wbb')):
        s = g[g.sport==sp]
        D[f'ducks_home_{a}'] = s[s.host=='UO'].groupby('date').size().reindex(idx).fillna(0).clip(upper=1)
        D[f'osu_home_{a}'] = s[s.host=='OSU'].groupby('date').size().reindex(idx).fillna(0).clip(upper=1)
    D['milb_home_games'] = g[g.sport=='minor_league_baseball'].groupby('date').size().reindex(idx).fillna(0)
    D['hayward_major_meet'] = g[g.sport=='track_meet'].groupby('date').size().reindex(idx).fillna(0).clip(upper=1)
    D['games_within_100mi'] = g.groupby('date').size().reindex(idx).fillna(0)
    D['football_attendance_100mi'] = fb.groupby('date')['attendance'].sum(min_count=1).reindex(idx)
    D['est_attendance_100mi'] = g.groupby('date')['attendance'].sum(min_count=1).reindex(idx)
    k = fb[fb.kickoff_local.fillna('') != ''].copy()
    k['h'] = k.kickoff_local.str.slice(0,2).astype(float) + k.kickoff_local.str.slice(3,5).astype(float)/60
    D['football_kickoff_hour'] = k.groupby('date')['h'].min().reindex(idx).round(2)
    for c, s in COVER.items(): D.loc[D.index < s, c] = np.nan
    D.index.name = 'date'
    return D

def merge_daily(D, path, datecol='date'):
    comp = 'gzip' if path.endswith('.gz') else None
    df = pd.read_csv(path, compression=comp, low_memory=False)
    dates = pd.to_datetime(df[datecol])
    df = df.drop(columns=[c for c in D.columns if c in df.columns])
    add = D.reindex(dates.values); add.index = df.index
    # days after the last game row but inside the dataset: zero (not blank) for count columns
    last = D.index.max()
    cnt = [c for c in D.columns if c not in ('football_attendance_100mi','est_attendance_100mi','football_kickoff_hour')]
    after = (dates > last).values
    for c in cnt: add.loc[after, c] = 0
    out = pd.concat([df, add], axis=1)
    out.to_csv(path, index=False, compression=comp)
    return out

def update_dict(path, D, df):
    cd = pd.read_csv(path)
    cd = cd[~cd['column'].isin(D.columns)]
    rows = []
    for c in D.columns:
        s = df[c]; nn = s.notna(); dts = pd.to_datetime(df.loc[nn, 'date'])
        rows.append(dict(column=c, description=DESC.get(c, ''), first=dts.min().date().isoformat() if nn.any() else '',
                         last=dts.max().date().isoformat() if nn.any() else '', pct_days_nonblank=round(100*nn.mean(), 1)))
    cd = pd.concat([cd, pd.DataFrame(rows)], ignore_index=True)
    cd.to_csv(path, index=False)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--history'); ap.add_argument('--no-merge', action='store_true')
    ap.add_argument('--also-merge', nargs='*', default=[])
    a = ap.parse_args()
    if a.history:
        rows = wiki_football(a.history) + espn_files(a.history) + sr_mbb(a.history) + milb_files(a.history) + hayward_rows()
        g = pd.DataFrame(rows)
        print('raw rows', len(g), g.groupby(['sport','source']).size().to_dict())
    else:
        g = pd.read_csv(GAMES, dtype={'kickoff_local':str})
        if 'game_pk' in g: g['game_pk'] = g['game_pk'].astype('Int64')
        now = pd.Timestamp.now(tz=PT); y = now.year
        fresh = pd.DataFrame(espn_live([y, y+1]) + milb_live([y]))
        if len(fresh):
            for (sp, tm), grp in fresh.groupby(['sport', 'team']):
                lo, hi = grp['date'].min(), grp['date'].max()
                drop = (g.sport == sp) & (g.team == tm) & (g.date >= lo) & (g.date <= hi)
                if sp == 'football': drop |= (g.sport == sp) & (g.team == tm) & (g.date >= lo)  # season rewritten by ESPN
                g = g[~drop]
            g = pd.concat([g, fresh], ignore_index=True)
        print('fresh rows', len(fresh))
    g = dedupe(g)
    g['kickoff_local'] = g['kickoff_local'].fillna('')
    # verified kickoffs where ESPN still shows TBA (keep in sync with daily_report.KICKOFF_OVERRIDES)
    for (d, host, sp), t in KICKOFF_OVERRIDES.items():
        m = (g.date == d) & (g.host == host) & (g.sport == sp) & (g.kickoff_local == '')
        g.loc[m, 'kickoff_local'] = t; g.loc[m, 'time_tba'] = 0
    g[[c for c in COLS if c in g.columns]].to_csv(GAMES, index=False)
    print('games', len(g), g.date.min(), g.date.max(), g.groupby('sport').size().to_dict())
    if a.no_merge: return
    today = pd.Timestamp.now(tz=PT).normalize().tz_localize(None)
    D = daily_from_games(g)
    for p in [DAILY] + a.also_merge:
        out = merge_daily(D, p)
        print('merged into', p, out.shape)
    update_dict(DICT, D, pd.read_csv(DAILY, compression='gzip', low_memory=False))

if __name__ == '__main__':
    try: main()
    except Exception as ex:
        import traceback; traceback.print_exc()
        if '--history' in sys.argv: raise
        print('build_sports: non-fatal failure')
