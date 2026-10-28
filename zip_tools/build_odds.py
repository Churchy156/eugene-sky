"""Historical betting lines + results for Ducks/Beavers home games (football, men's and women's basketball) within 100 mi of Eugene.

Sources (free, no key):
  * SportsbookReviewsOnline archives - closing spread, total and moneyline: college football 2007-08..2022-23 (HTML),
    men's college basketball 2007-08..2020-21 (xlsx).  Primary source for those seasons.
  * ESPN core API  /events/{id}/competitions/{id}/odds - median across real sportsbooks (projection sites such as
    teamrankings/accuscore/numberfire/consensus and live in-game lines are dropped).  Used for every game SBR doesn't cover
    (football 2023+, men's basketball 2021-22+, women's basketball ~2019+ where ESPN has lines).
  * ESPN team schedules - final scores, AP/coaches rank (curatedRank), neutral site flag.
Not available: MiLB and Hayward meets (no betting markets); CollegeFootballData.com needs an API key (not used).

Writes data/sports_odds_games.csv (one row per game) and merges daily columns into data/eugene_env_daily.csv.gz.
Usage: python zip_tools/build_odds.py [--raw /tmp/odds] [--fetch] [--no-merge]
  --fetch re-downloads the ESPN schedules/odds for the current + previous season (CI-safe, non-fatal)."""
import os, re, sys, json, glob, argparse, datetime as dt
import numpy as np, pandas as pd, requests
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(HERE, 'data', 'sports_games_100mi.csv'); OUT = os.path.join(HERE, 'data', 'sports_odds_games.csv')
DAILY = os.path.join(HERE, 'data', 'eugene_env_daily.csv.gz'); DICT = os.path.join(HERE, 'column_dictionary.csv')
PT = ZoneInfo('America/Los_Angeles'); UTC = ZoneInfo('UTC')
TEAMS = {'UO': '2483', 'OSU': '204'}
SP = {'football': ('football', 'college-football'), 'mens_basketball': ('basketball', 'mens-college-basketball'),
      'womens_basketball': ('basketball', 'womens-college-basketball')}
NOT_BOOKS = re.compile(r'teamrankings|accuscore|numberfire|consensus|opening|live odds|unknown|betegy|sportsinsights|betradar', re.I)

def num(v):
    s = str(v).strip().lower()
    if s in ('pk', 'p', 'pick', 'ev'): return 0.0
    s = re.sub(r'[^0-9.\-]', '', s.replace('½', '.5'))
    try: return float(s)
    except ValueError: return np.nan

# ---------------- SportsbookReviewsOnline ----------------
def parse_sbr(raw):
    rows = []
    for f in sorted(glob.glob(os.path.join(raw, 'sbr', 'ncaa-*'))):
        sport = 'football' if 'football' in f else 'mens_basketball'; y0 = int(re.search(r'(\d{4})-\d\d', f).group(1))
        if f.endswith('.html'): t = pd.read_html(f)[0]; t.columns = t.iloc[0]; t = t.iloc[1:]
        else: t = pd.read_excel(f)
        t = t.reset_index(drop=True); i = 0
        while i + 1 < len(t):
            a, b = t.iloc[i], t.iloc[i + 1]
            try: int(float(a['Rot']))
            except (ValueError, TypeError): i += 1; continue
            if not (str(a['VH']).strip() in ('V', 'N') and str(b['VH']).strip() in ('H', 'N')): i += 1; continue
            i += 2
            if str(b['Team']).strip() not in ('Oregon', 'OregonState') or str(b['VH']).strip() != 'H': continue
            d = int(float(a['Date'])); m, dd = d // 100, d % 100; yr = y0 if m >= 7 else y0 + 1
            ca, cb = num(a['Close']), num(b['Close'])
            if np.isnan(ca) and np.isnan(cb): ca, cb = num(a['Open']), num(b['Open'])
            spread = total = np.nan; cut = 40 if sport == 'football' else 60
            if not np.isnan(ca) and not np.isnan(cb):
                if ca < cb: spread, total = ca, cb          # smaller number sits on the favourite's row
                else: spread, total = -cb, ca
            elif not np.isnan(ca) or not np.isnan(cb):
                v = ca if not np.isnan(ca) else cb
                if v < cut: spread = v if not np.isnan(ca) else -v
                else: total = v
            rows.append(dict(date=f'{yr}-{m:02d}-{dd:02d}', sport=sport, host={'Oregon': 'UO', 'OregonState': 'OSU'}[str(b['Team']).strip()],
                             sbr_opp=str(a['Team']), sbr_home_score=num(b['Final']), sbr_away_score=num(a['Final']),
                             sbr_spread=spread + 0.0 if spread == spread else spread, sbr_total=total, sbr_ml_home=num(b['ML']), sbr_ml_away=num(a['ML'])))
    return pd.DataFrame(rows, columns=['date', 'sport', 'host'] if not rows else None)

# ---------------- ESPN ----------------
S = requests.Session(); S.headers['User-Agent'] = 'eugene-sky odds builder'
def _get(u):
    for _ in range(3):
        try:
            r = S.get(u, timeout=30)
            if r.status_code == 200: return r.json()
            if r.status_code == 404: return None
        except Exception: pass
    return None

def fetch_espn(raw, seasons):
    os.makedirs(os.path.join(raw, 'espn'), exist_ok=True)
    for sp, (s, l) in SP.items():
        for t, tid in TEAMS.items():
            for y in seasons:
                for st in (2, 3):
                    d = _get(f'https://site.api.espn.com/apis/site/v2/sports/{s}/{l}/teams/{tid}/schedule?season={y}&seasontype={st}')
                    if d is not None: json.dump(d, open(os.path.join(raw, 'espn', f'sched_{sp}_{t}_{y}_{st}.json'), 'w'))
    E = parse_espn(raw)
    for _, r in E[(E.season.isin(seasons))].iterrows():
        s, l = SP[r.sport]; d = _get(f'https://sports.core.api.espn.com/v2/sports/{s}/{l}/events/{r.eid}/competitions/{r.eid}/odds?limit=50')
        if d is not None: json.dump(d, open(os.path.join(raw, 'espn', f'odds_{r.eid}.json'), 'w'))

def parse_espn(raw):
    rows = {}
    for f in glob.glob(os.path.join(raw, 'espn', 'sched_*.json')):
        sp, t, y = re.match(r'sched_(\w+?)_(UO|OSU)_(\d{4})_\d', os.path.basename(f)).groups()
        for e in (json.load(open(f)) or {}).get('events', []):
            c = e['competitions'][0]; hh = [x for x in c['competitors'] if x['homeAway'] == 'home']; aa = [x for x in c['competitors'] if x['homeAway'] == 'away']
            if not hh or not aa or hh[0]['team']['id'] != TEAMS[t]: continue
            h, a = hh[0], aa[0]; st = c.get('status', {}).get('type', {})
            sc = lambda x: (x.get('score') or {}).get('value') if isinstance(x.get('score'), dict) else num(x.get('score'))
            rk = lambda x: (x.get('curatedRank') or {}).get('current')
            when = dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00')).astimezone(PT)
            rows[e['id']] = dict(eid=e['id'], sport=sp, host=t, season=int(y), date=when.date().isoformat(), start_pt=when.strftime('%H:%M'),
                                 opponent_espn=a['team'].get('displayName'), opp_id=a['team'].get('id'), neutral=bool(c.get('neutralSite')),
                                 completed=bool(st.get('completed')), espn_home_score=sc(h) if st.get('completed') else np.nan,
                                 espn_away_score=sc(a) if st.get('completed') else np.nan, home_rank=rk(h), opp_rank=rk(a))
    return pd.DataFrame(rows.values())

def espn_lines(raw, eid):
    f = os.path.join(raw, 'espn', f'odds_{eid}.json')
    if not os.path.exists(f): return {}
    it = [i for i in (json.load(open(f)) or {}).get('items', []) if not NOT_BOOKS.search(i.get('provider', {}).get('name', ''))]
    if not it: return {}
    med = lambda v: float(np.median(v)) if v else np.nan
    sp = [i['spread'] for i in it if isinstance(i.get('spread'), (int, float))]
    tot = [i['overUnder'] for i in it if isinstance(i.get('overUnder'), (int, float))]
    mlh = [i['homeTeamOdds']['moneyLine'] for i in it if isinstance((i.get('homeTeamOdds') or {}).get('moneyLine'), (int, float))]
    mla = [i['awayTeamOdds']['moneyLine'] for i in it if isinstance((i.get('awayTeamOdds') or {}).get('moneyLine'), (int, float))]
    # ESPN's spread field is from the home team's view; double-check against the favourite flag
    fav = [(i.get('homeTeamOdds') or {}).get('favorite') for i in it]
    s = med(sp)
    if s == s and s != 0 and any(x is not None for x in fav):
        hf = sum(1 for x in fav if x) > sum(1 for x in fav if x is False)
        if hf and s > 0 or (not hf and s < 0): s = -s
    return dict(espn_spread=s, espn_total=med(tot), espn_ml_home=med(mlh), espn_ml_away=med(mla), espn_books=len(it))

# ---------------- combine ----------------
RIVAL = {'UO': re.compile(r'oregon st|beavers|^osu', re.I), 'OSU': re.compile(r'^oregon(?! st)|ducks|^\(?.*\boregon\*?$', re.I)}
def build(raw):
    g = pd.read_csv(GAMES, dtype={'kickoff_local': str}); g = g[g.sport.isin(SP) & g.host.isin(TEAMS)].copy()
    g['date'] = pd.to_datetime(g.date)
    E = parse_espn(raw); E['date'] = pd.to_datetime(E.date)
    B = parse_sbr(raw); B['date'] = pd.to_datetime(B.date)
    out = []
    for _, r in g.iterrows():
        row = dict(date=r.date, sport=r.sport, host=r.host, opponent=r.opponent, venue=r.venue, attendance=r.attendance)
        for key, T in (('e', E), ('b', B)):
            m = T[(T.sport == r.sport) & (T.host == r.host) & ((T.date - r.date).abs() <= pd.Timedelta(days=1))]
            if len(m) > 1: m = m.iloc[[(m.date - r.date).abs().argmin()]]
            if len(m): row.update(m.iloc[0].drop(['date', 'sport', 'host']).to_dict())
        out.append(row)
    G = pd.DataFrame(out)
    for c in ['eid', 'espn_home_score', 'espn_away_score', 'sbr_spread', 'sbr_total', 'sbr_ml_home', 'sbr_ml_away', 'sbr_home_score', 'sbr_away_score', 'home_rank', 'opp_rank', 'opponent_espn', 'sbr_opp']:
        if c not in G: G[c] = np.nan
    L = pd.DataFrame([espn_lines(raw, e) if isinstance(e, str) else {} for e in G.eid])
    for c in ['espn_spread', 'espn_total', 'espn_ml_home', 'espn_ml_away', 'espn_books']: G[c] = L[c] if c in L else np.nan
    has_b = G.sbr_spread.notna() | G.sbr_total.notna()
    G['spread_home'] = np.where(has_b, G.sbr_spread, G.espn_spread)
    G['total_line'] = np.where(has_b, G.sbr_total, G.espn_total)
    G['ml_home'] = np.where(has_b, G.sbr_ml_home, G.espn_ml_home); G['ml_away'] = np.where(has_b, G.sbr_ml_away, G.espn_ml_away)
    G['odds_source'] = np.where(has_b, 'SportsbookReviewsOnline closing line', np.where(G.espn_spread.notna() | G.espn_total.notna(), 'ESPN (median of sportsbooks)', ''))
    # if SBR spread is missing but moneyline says who is favoured and ESPN has the number, fill from ESPN
    miss = G.spread_home.isna() & G.espn_spread.notna(); G.loc[miss, 'spread_home'] = G.loc[miss, 'espn_spread']
    # sanity: spread sign must agree with moneyline sign (home favourite -> negative spread)
    bad = (G.ml_home.notna() & G.spread_home.notna() & (G.spread_home != 0) & (np.sign(G.spread_home) != np.sign(G.ml_home)) & (G.ml_home.abs() > 150) & (G.spread_home.abs() >= 3))
    # (checked by hand: in these cases the spread is right and the archive's moneyline columns are swapped, so drop the moneyline)
    G.loc[bad, ['ml_home', 'ml_away']] = np.nan; G['moneyline_dropped'] = bad.astype(int)
    G['home_score'] = G.espn_home_score.where(G.espn_home_score.notna(), G.sbr_home_score)
    G['away_score'] = G.espn_away_score.where(G.espn_away_score.notna(), G.sbr_away_score)
    # derived
    G['margin'] = G.home_score - G.away_score
    G['home_won'] = np.where(G.margin.notna(), (G.margin > 0).astype(float), np.nan)
    G['home_favored'] = np.where(G.spread_home.notna() & (G.spread_home != 0), (G.spread_home < 0).astype(float), np.nan)
    G['ats_margin'] = G.margin + G.spread_home            # >0 = home team beat the spread
    G['home_covered'] = np.where(G.ats_margin.notna(), np.where(G.ats_margin > 0, 1.0, np.where(G.ats_margin < 0, 0.0, 0.5)), np.nan)
    G['upset'] = np.where(G.home_favored.notna() & G.home_won.notna() & (G.margin != 0), (G.home_favored != G.home_won).astype(float), np.nan)
    G['home_upset_loss'] = np.where(G.upset.notna(), ((G.upset == 1) & (G.home_favored == 1)).astype(float), np.nan)
    G['home_upset_win'] = np.where(G.upset.notna(), ((G.upset == 1) & (G.home_favored == 0)).astype(float), np.nan)
    G['surprise_pts'] = G.ats_margin.abs()
    big = {'football': (7, 21), 'mens_basketball': (5, 20), 'womens_basketball': (5, 20)}
    G['close_game'] = [np.nan if m != m else float(abs(m) <= big[s][0]) for m, s in zip(G.margin, G.sport)]
    G['blowout'] = [np.nan if m != m else float(abs(m) >= big[s][1]) for m, s in zip(G.margin, G.sport)]
    G['total_points'] = G.home_score + G.away_score
    G['over_hit'] = np.where(G.total_points.notna() & G.total_line.notna(), (G.total_points > G.total_line).astype(float), np.nan)
    opp = G.opponent.fillna('') + ' ' + G.opponent_espn.fillna('') + ' ' + G.sbr_opp.fillna('')
    G['rivalry'] = [float(bool(re.search(r'oregon ?st|beavers', o, re.I))) if h == 'UO' else float(bool(re.search(r'(^|\W)oregon(?! ?st)(\W|$)|ducks', o, re.I)) or bool(re.search(r'\bOregon\b(?! St)', o0)))
                    for o, h, o0 in zip(opp, G.host, G.opponent.fillna(''))]
    G.loc[(G.team if 'team' in G else G.host).astype(str).ne(G.host) & False, 'rivalry'] = 1
    G['opp_ranked'] = np.where(G.opp_rank.notna(), ((G.opp_rank > 0) & (G.opp_rank <= 25)).astype(float), np.nan)
    G['home_ranked'] = np.where(G.home_rank.notna(), ((G.home_rank > 0) & (G.home_rank <= 25)).astype(float), np.nan)
    # "high total": top third of totals within the same sport
    G['high_total'] = np.nan
    for s in SP:
        m = (G.sport == s) & G.total_line.notna()
        if m.sum() > 10: G.loc[m, 'high_total'] = (G.loc[m, 'total_line'] >= G.loc[m, 'total_line'].quantile(2 / 3)).astype(float)
    keep = ['date', 'sport', 'host', 'opponent', 'opponent_espn', 'venue', 'attendance', 'eid', 'home_rank', 'opp_rank', 'home_score', 'away_score',
            'spread_home', 'total_line', 'ml_home', 'ml_away', 'odds_source', 'espn_books', 'moneyline_dropped', 'margin', 'home_won', 'home_favored',
            'ats_margin', 'home_covered', 'upset', 'home_upset_loss', 'home_upset_win', 'surprise_pts', 'close_game', 'blowout', 'total_points',
            'over_hit', 'high_total', 'rivalry', 'opp_ranked', 'home_ranked']
    G = G[keep].sort_values(['date', 'sport', 'host']); G['date'] = G.date.dt.date
    return G

DESC = {
 'fb_home_spread': 'Point spread for the home team in that day\'s Ducks/Beavers home football game (negative = home team favoured; mean if both play at home). SBR closing line 2007–2022, ESPN sportsbook median 2023+',
 'fb_upset': 'Ducks/Beavers home football game that day ended in an upset (the betting underdog won outright); blank = no game or no line',
 'fb_home_lost_as_favorite': 'Ducks/Beavers home football team lost a game it was favoured to win',
 'fb_surprise_pts': 'How far the home football result missed the spread, in points (|final margin + spread|)',
 'fb_beat_spread_pts': 'Home football result vs the spread in points (positive = home team did better than expected)',
 'fb_close_game': 'Home football game decided by 7 points or fewer',
 'fb_blowout': 'Home football game decided by 21 points or more',
 'fb_total_line': 'Over/under total for the home football game (expected combined points)',
 'fb_high_total': 'Home football over/under in the top third of all lines (expected shootout)',
 'fb_rivalry': 'Home football game was the Civil War / rivalry (Oregon vs Oregon State)',
 'fb_ranked_opponent': 'Home football opponent was ranked in the AP/coaches top 25 (ESPN)',
 'fb_home_won': 'Home football team won (1) or lost (0)',
 'mbb_home_spread': 'Point spread for the Ducks/Beavers home men\'s basketball game (negative = home favoured)',
 'mbb_upset': 'Home men\'s basketball game ended in an upset (underdog won)',
 'mbb_home_lost_as_favorite': 'Home men\'s basketball team lost a game it was favoured to win',
 'mbb_surprise_pts': 'How far the home men\'s basketball result missed the spread, in points',
 'mbb_close_game': 'Home men\'s basketball game decided by 5 points or fewer',
 'mbb_blowout': 'Home men\'s basketball game decided by 20 points or more',
 'mbb_high_total': 'Home men\'s basketball over/under in the top third of all lines',
 'wbb_home_spread': 'Point spread for the Ducks/Beavers home women\'s basketball game (ESPN, mostly 2019+)',
 'wbb_upset': 'Home women\'s basketball game ended in an upset (underdog won)',
 'games_with_odds': 'Number of Ducks/Beavers home games (football + basketball) that day with a betting line',
 'any_upset_home_loss': 'Any Ducks/Beavers home team (football or basketball) lost as the betting favourite that day',
}
def daily(G):
    G = G.copy(); G['date'] = pd.to_datetime(G.date)
    idx = pd.date_range('1950-01-01', pd.Timestamp(dt.datetime.now(PT).date())); D = pd.DataFrame(index=idx)
    for pre, sp in (('fb', 'football'), ('mbb', 'mens_basketball'), ('wbb', 'womens_basketball')):
        x = G[(G.sport == sp) & G.spread_home.notna()]; gb = x.groupby('date')
        D[f'{pre}_home_spread'] = gb.spread_home.mean()
        D[f'{pre}_upset'] = gb.upset.max()
        D[f'{pre}_home_lost_as_favorite'] = gb.home_upset_loss.max()
        D[f'{pre}_surprise_pts'] = gb.surprise_pts.max()
        if pre == 'fb':
            D['fb_beat_spread_pts'] = gb.ats_margin.mean(); D['fb_total_line'] = gb.total_line.mean(); D['fb_home_won'] = gb.home_won.min()
        if pre != 'wbb':
            D[f'{pre}_close_game'] = G[G.sport == sp].groupby('date').close_game.max(); D[f'{pre}_blowout'] = G[G.sport == sp].groupby('date').blowout.max()
            D[f'{pre}_high_total'] = gb.high_total.max()
        if pre == 'fb':
            D['fb_rivalry'] = G[G.sport == sp].groupby('date').rivalry.max(); D['fb_ranked_opponent'] = G[G.sport == sp].groupby('date').opp_ranked.max()
    D['games_with_odds'] = G[G.spread_home.notna()].groupby('date').size(); D['any_upset_home_loss'] = G.groupby('date').home_upset_loss.max()
    D = D.reindex(idx); first = G[G.spread_home.notna()].date.min()
    D.loc[D.index >= first, 'games_with_odds'] = D.loc[D.index >= first, 'games_with_odds'].fillna(0)
    D.index.name = 'date'; return D[list(DESC)]

def merge(D):
    df = pd.read_csv(DAILY, compression='gzip', low_memory=False); dates = pd.to_datetime(df['date'])
    df = df.drop(columns=[c for c in D.columns if c in df.columns]); add = D.reindex(dates.values); add.index = df.index
    out = pd.concat([df, add], axis=1); out.to_csv(DAILY, index=False, compression='gzip')
    cd = pd.read_csv(DICT); cd = cd[~cd['column'].isin(D.columns)]; rows = []
    for c in D.columns:
        nn = out[c].notna(); d = dates[nn]
        rows.append(dict(column=c, description=DESC[c], first=d.min().date().isoformat() if nn.any() else '', last=d.max().date().isoformat() if nn.any() else '', pct_days_nonblank=round(100 * nn.mean(), 1)))
    pd.concat([cd, pd.DataFrame(rows)], ignore_index=True).to_csv(DICT, index=False)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--raw', default='/tmp/odds'); ap.add_argument('--fetch', action='store_true'); ap.add_argument('--no-merge', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        y = dt.date.today().year; fetch_espn(a.raw, [y, y + 1])
    G = build(a.raw)
    if os.path.exists(OUT):   # keep games we no longer have raw files for (CI has only recent ESPN caches)
        old = pd.read_csv(OUT, dtype={'eid': str}); old['date'] = pd.to_datetime(old.date).dt.date
        k = lambda d: d.date.astype(str) + d.sport + d.host
        if not glob.glob(os.path.join(a.raw, 'sbr', '*')):   # CI: only refresh the last ~13 months from fresh ESPN files
            cut = dt.date.today() - dt.timedelta(days=400); G = G[pd.to_datetime(G.date).dt.date >= cut]
        # a fresh row replaces an old one only if it has a line, or the old one had none (keeps archived lines safe)
        keep_old = k(old).isin(k(G[G.spread_home.notna()])) == False
        oldk = set(k(old[old.spread_home.notna()]))
        G = G[G.spread_home.notna() | ~k(G).isin(oldk)]
        G = pd.concat([old[keep_old & ~k(old).isin(k(G))], G]).sort_values(['date', 'sport', 'host'])
    G.to_csv(OUT, index=False)
    print(f'{len(G)} games, {G.spread_home.notna().sum()} with a spread, {G.total_line.notna().sum()} with a total, {G.ml_home.notna().sum()} with a moneyline')
    if not a.no_merge: merge(daily(G)); print('merged', len(DESC), 'daily columns')
if __name__ == '__main__': main()
