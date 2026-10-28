#!/usr/bin/env python3
"""School calendars (9 districts near Eugene) + varsity high-school home games -> daily columns.

  python zip_tools/build_schools.py --maxpreps RAWDIR   # rebuild data/hs_sports_games.csv from cached MaxPreps pages, then merge
  python zip_tools/build_schools.py                     # merge only (reads data/school_calendars.csv, data/hs_sports_games.csv)

Calendar source rows (data/school_calendars.csv, data/school_calendar_coverage.csv) come from
zip_tools/school_cal_parse/assemble.py (district PDFs / web pages, live sites + Wayback Machine).
School years with no real calendar fall back to an ESTIMATED 4J-style rule (Wed after Labor Day to ~Jun 13,
Thanksgiving Wed-Fri, Dec 21-Jan 3, last full week of March, federal Monday holidays, Veterans Day).
All dates are Pacific Time calendar days.  Never fatal in CI.
"""
import os, sys, re, glob, json, argparse, datetime as dt
import pandas as pd, numpy as np
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL = os.path.join(HERE, 'data', 'school_calendars.csv')
COV = os.path.join(HERE, 'data', 'school_calendar_coverage.csv')
HS = os.path.join(HERE, 'data', 'hs_sports_games.csv')
DAILY = os.path.join(HERE, 'data', 'eugene_env_daily.csv.gz')
DICT = os.path.join(HERE, 'column_dictionary.csv')
DISTRICTS = ['4j', 'bethel', 'springfield', 'junction_city', 'monroe', 'harrisburg', 'creswell', 'pleasant_hill', 'south_lane']
# MaxPreps slug -> (school name, district key)
SCHOOLS = {'eugene/sheldon-irish': ('Sheldon', '4j'), 'eugene/south-eugene-axe': ('South Eugene', '4j'),
    'eugene/churchill-lancers': ('Churchill', '4j'), 'eugene/north-eugene-highlanders': ('North Eugene', '4j'),
    'eugene/willamette-wolverines': ('Willamette', 'bethel'), 'springfield/thurston-colts': ('Thurston', 'springfield'),
    'springfield/springfield-millers': ('Springfield', 'springfield'), 'junction-city/junction-city-tigers': ('Junction City', 'junction_city'),
    'monroe/monroe-dragons': ('Monroe', 'monroe'), 'harrisburg/harrisburg-eagles': ('Harrisburg', 'harrisburg'),
    'creswell/creswell-bulldogs': ('Creswell', 'creswell'), 'pleasant-hill/pleasant-hill-billies': ('Pleasant Hill', 'pleasant_hill'),
    'cottage-grove/cottage-grove-lions': ('Cottage Grove', 'south_lane')}
SPORT = {'football': 'football', 'basketball': 'boys_basketball', 'basketball_girls': 'girls_basketball', 'soccer': 'boys_soccer',
         'soccer_girls': 'girls_soccer', 'volleyball': 'volleyball', 'baseball': 'baseball', 'softball': 'softball'}
MARQUEE = [{'Thurston', 'Springfield'}, {'Sheldon', 'South Eugene'}, {'Churchill', 'South Eugene'}, {'Sheldon', 'Churchill'},
           {'North Eugene', 'Willamette'}, {'Creswell', 'Pleasant Hill'}, {'Junction City', 'Harrisburg'}, {'Monroe', 'Harrisburg'}]
LOCAL_VENUE = re.compile(r'eugene|springfield|sheldon|churchill|thurston|willamette|autzen|hayward|matthew knight|mcarthur|silke|lane c|lcc|'
                         r'junction|j\. ?city|monroe|harrisburg|creswell|pleasant hill|cottage grove|pk park|civic', re.I)

def hs_games(raw):
    rows = {}
    for f in sorted(glob.glob(os.path.join(raw, '*__*__*__*.json'))):
        city, slug, sp, season = os.path.basename(f)[:-5].split('__')
        key = f'{city}/{slug}'
        if key not in SCHOOLS or sp not in SPORT: continue
        try: d = json.load(open(f))
        except Exception: continue
        tour = {t.get('contestId'): t for t in d.get('tournaments') or []}
        for x in d.get('contests') or []:
            try:
                state = str(x[28] or '')
                if 'Deleted' in state or 'TBA' in state or len(x[0]) != 2: continue
                when = x[11] or ''
                if not when[:4].isdigit(): continue
                teams = x[0]; home = [t for t in teams if t[11] == 0]; neutral = all(t[11] == 2 for t in teams)
                desc = x[29] or ''; venue = (x[5] or '').strip()
                ours = [t for t in teams if t[13] and any(f'/{k}/' in t[13] for k in SCHOOLS)]
                host = None
                if home and home[0][13] and any(f'/{k}/' in home[0][13] for k in SCHOOLS):
                    host = next(SCHOOLS[k][0] for k in SCHOOLS if f'/{k}/' in home[0][13])
                elif neutral and venue and LOCAL_VENUE.search(venue) and ours:
                    host = 'neutral (local)'
                if not host: continue
                cid = x[1] or x[18]
                t = tour.get(x[1]) or {}
                playoff = bool(t.get('isTournamentPlayOff')) or bool(re.search(r'\bplayoff', desc, re.I))
                tname = t.get('tournamentName') or ''
                gtype = 'state playoff' if playoff else ('tournament' if (tname or 'tournament' in desc.lower()) else 'regular')
                names = [tm[14] for tm in teams]
                local = [n for n in names if n in {v[0] for v in SCHOOLS.values()}]
                hm = home[0][14] if home else names[0]; aw = [n for n in names if n != hm][0] if len(set(names)) > 1 else names[-1]
                tm_ = when[11:16]; tba = tm_ in ('', '00:00', '00:01')
                rows[cid] = dict(date=when[:10], time_local='' if tba else tm_, sport=SPORT[sp], home_team=hm, away_team=aw,
                    host_school=host, host_district=next((SCHOOLS[k][1] for k in SCHOOLS if SCHOOLS[k][0] == host), ''),
                    venue=venue if venue and venue != 'TBA' else ('' if host.startswith('neutral') else f'{host} High School'),
                    game_type=gtype, tournament=tname[:80], local_derby=int(len(set(local)) == 2),
                    marquee_rivalry=int(set(names) in MARQUEE), season=season, url=x[18] or '')
            except (IndexError, TypeError): continue
    g = pd.DataFrame(rows.values()).sort_values(['date', 'time_local', 'sport']).reset_index(drop=True)
    return g

def labor(y):
    d = dt.date(y, 9, 1); return d + dt.timedelta((0 - d.weekday()) % 7)
def nth(y, m, wd, n):
    d = dt.date(y, m, 1); d += dt.timedelta((wd - d.weekday()) % 7); return d + dt.timedelta(7 * (n - 1))
def last_mon(y, m):
    d = dt.date(y, m + 1, 1) - dt.timedelta(1); return d - dt.timedelta(d.weekday())
def estimated_year(sy):
    """4J-style rule calendar for school year sy (fall year): (first, last, set(no-school weekdays))."""
    first = labor(sy) + dt.timedelta(2); last = dt.date(sy + 1, 6, 13)
    while last.weekday() >= 5: last -= dt.timedelta(1)
    nos = {dt.date(sy, 11, 11)}
    th = nth(sy, 11, 3, 4); nos |= {th - dt.timedelta(1), th, th + dt.timedelta(1)}
    d = dt.date(sy, 12, 21)
    while d <= dt.date(sy + 1, 1, 3): nos.add(d); d += dt.timedelta(1)
    sb = dt.date(sy + 1, 3, 31); sb -= dt.timedelta(sb.weekday())
    if sb.day > 25: sb -= dt.timedelta(7)
    nos |= {sb + dt.timedelta(i) for i in range(5)}
    nos |= {nth(sy + 1, 1, 0, 3), nth(sy + 1, 2, 0, 3), last_mon(sy + 1, 5)}
    return first, last, nos

def calendar_daily(idx):
    cal = pd.read_csv(CAL, parse_dates=['date']); cov = pd.read_csv(COV, parse_dates=['first_day', 'last_day'])
    real = {(r.district_key, int(r.school_year[:4])): r for r in cov.itertuples()}
    days = pd.Series(idx.date, index=idx)
    out = {}
    for dk in DISTRICTS:
        ins = np.zeros(len(idx), dtype=np.int8); out_ = np.zeros(len(idx), dtype=np.int8)
        er = np.zeros(len(idx), dtype=np.int8); isreal = np.zeros(len(idx), dtype=np.int8)
        c = cal[cal.district_key == dk]
        for sy in range(idx[0].year - 1, idx[-1].year + 1):
            if (dk, sy) in real:
                r = real[(dk, sy)]; first, last = r.first_day.date(), r.last_day.date()
                cc = c[c.school_year == f'{sy}-{str(sy + 1)[2:]}']
                nos = set(cc[cc.event_type == 'no_school'].date.dt.date); erl = set(cc[cc.event_type == 'early_release'].date.dt.date)
                rl = 1
            else:
                first, last, nos = estimated_year(sy); erl = set(); rl = 0
            m = ((days >= first) & (days <= last)).values
            wk = idx.dayofweek < 5
            nos_m = days.isin(nos).values
            ins[m & wk & ~nos_m] = 1; out_[m & wk & nos_m] = 1; er[m & wk & days.isin(erl).values] = 1; isreal[m] = rl
        out[dk] = (ins, out_, er, isreal)
    D = pd.DataFrame(index=idx)
    D['schools_in_session_count'] = sum(v[0] for v in out.values())
    D['school_4j_in_session'] = out['4j'][0]
    D['districts_out_count'] = sum(v[1] for v in out.values())
    D['early_release_count'] = sum(v[2] for v in out.values())
    D['early_release_any'] = (D.early_release_count > 0).astype(int)
    D['school_calendar_real_count'] = sum(v[3] for v in out.values())
    return D

def hs_daily(g, idx):
    g = g.copy(); g['date'] = pd.to_datetime(g['date'])
    D = pd.DataFrame(index=idx)
    cnt = lambda s: s.groupby('date').size().reindex(idx).fillna(0).astype(int)
    D['hs_home_games'] = cnt(g)
    D['hs_home_football'] = cnt(g[g.sport == 'football'])
    D['hs_football_friday'] = ((D.hs_home_football > 0) & (idx.dayofweek == 4)).astype(int)
    D['hs_home_basketball'] = cnt(g[g.sport.str.contains('basketball')])
    D['hs_playoff_home_games'] = cnt(g[g.game_type == 'state playoff'])
    D['hs_rivalry_game'] = cnt(g[g.marquee_rivalry == 1])
    D['hs_local_derby_games'] = cnt(g[g.local_derby == 1])
    first = g.date.min()
    for c in D.columns: D.loc[D.index < first, c] = np.nan
    return D

DESC = {
 'schools_in_session_count': 'Number of the 9 local school districts (4J, Bethel, Springfield, Junction City, Monroe, Harrisburg, Creswell, Pleasant Hill, South Lane/Cottage Grove) with students in class that day (0-9). Real district calendars where available, otherwise an estimated 4J-style rule; see school_calendar_real_count.',
 'school_4j_in_session': 'Eugene 4J students in class that day (1/0). Real 4J calendars 2007-08 to 2026-27; estimated rule before that.',
 'districts_out_count': 'Number of the 9 districts with a scheduled no-school weekday inside their school year (breaks, holidays, in-service, grading/conference days). Summer and weekends count as 0.',
 'early_release_count': 'Number of the 9 districts with an early-release / half day that day (real calendars only).',
 'early_release_any': 'Any of the 9 districts has an early-release / half day (1/0; real calendars only).',
 'school_calendar_real_count': 'How many of the 9 districts use a real published calendar for this day (the rest use the estimated rule).',
 'hs_home_games': 'Varsity high-school home games at the 13 local high schools (football, basketball, soccer, volleyball, baseball, softball; MaxPreps), plus neutral-site games held locally.',
 'hs_home_football': 'Varsity high-school home football games at the 13 local high schools that day.',
 'hs_football_friday': 'A Friday with at least one local varsity high-school home football game (1/0).',
 'hs_home_basketball': 'Varsity high-school home basketball games (boys + girls) at the 13 local high schools.',
 'hs_playoff_home_games': 'Locally hosted varsity high-school state-playoff games (OSAA brackets).',
 'hs_rivalry_game': 'Big local rivalry games that day (Thurston-Springfield, Sheldon-South Eugene, Churchill-South Eugene, Sheldon-Churchill, North Eugene-Willamette, Creswell-Pleasant Hill, Junction City-Harrisburg, Monroe-Harrisburg).',
 'hs_local_derby_games': 'Home games where both teams are among the 13 local high schools (any sport).'}

def merge(D, path):
    comp = 'gzip' if path.endswith('.gz') else None
    df = pd.read_csv(path, compression=comp, low_memory=False)
    dates = pd.to_datetime(df['date'])
    df = df.drop(columns=[c for c in D.columns if c in df.columns])
    add = D.reindex(dates.values); add.index = df.index
    out = pd.concat([df, add], axis=1); out.to_csv(path, index=False, compression=comp); return out

def update_dict(df, cols):
    cd = pd.read_csv(DICT); cd = cd[~cd['column'].isin(cols)]; rows = []
    for c in cols:
        nn = df[c].notna(); dts = pd.to_datetime(df.loc[nn, 'date'])
        rows.append(dict(column=c, description=DESC.get(c, ''), first=dts.min().date().isoformat() if nn.any() else '',
                         last=dts.max().date().isoformat() if nn.any() else '', pct_days_nonblank=round(100 * nn.mean(), 1)))
    pd.concat([cd, pd.DataFrame(rows)], ignore_index=True).to_csv(DICT, index=False)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--maxpreps'); ap.add_argument('--no-merge', action='store_true')
    a = ap.parse_args()
    if a.maxpreps:
        g = hs_games(a.maxpreps); g.to_csv(HS, index=False)
        print('hs games', len(g), g.date.min(), g.date.max(), g.groupby('sport').size().to_dict())
    g = pd.read_csv(HS, dtype={'time_local': str})
    if a.no_merge: return
    df = pd.read_csv(DAILY, compression='gzip', usecols=['date'])
    idx = pd.DatetimeIndex(pd.to_datetime(df['date']).sort_values().unique())
    D = calendar_daily(idx).join(hs_daily(g, idx))
    out = merge(D, DAILY); update_dict(out, list(D.columns))
    print('merged', out.shape, list(D.columns))

if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('build_schools failed:', repr(e)); sys.exit(0 if os.environ.get('CI') else 1)
