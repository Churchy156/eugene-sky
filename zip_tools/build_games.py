"""ESPN home-game history/upcoming for the ZIP dashboard (ESPN API has no CORS, so prebuilt).
Usage: python zip_tools/build_games.py [start YYYYMM]  -> zip_src/data/games.json (merged with existing)."""
import json, sys, os, datetime as dt, urllib.request, gzip, concurrent.futures as cf
LG = [('CFB','football/college-football','&groups=80'),('MBB','basketball/mens-college-basketball','&groups=50'),
      ('NFL','football/nfl',''),('NBA','basketball/nba',''),('MLB','baseball/mlb',''),('NHL','hockey/nhl',''),
      ('MLS','soccer/usa.1',''),('WNBA','basketball/wnba','')]
OUT = 'zip_src/data/games.json'
P = {}
for l in open('data/us_places.tsv'):
    s, n, la, lo = l.rstrip('\n').split('\t'); P.setdefault((s, n.lower()), (float(la), float(lo)))
def get(u):
    for _ in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'}), timeout=30).read()
            return json.loads(gzip.decompress(r) if r[:2] == b'\x1f\x8b' else r)
        except Exception: pass
    return {'events': []}
def fetch(lg, path, g, ds):
    e = get(f'https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={ds}&limit=500{g}').get('events', [])
    if len(ds) == 6 and (len(e) >= 450 or lg == 'CFB'):  # CFB month view only returns week 1  # month capped: split into days
        y, m = int(ds[:4]), int(ds[4:]); d = dt.date(y, m, 1); e = []
        while d.month == m: e += fetch(lg, path, g, d.strftime('%Y%m%d')); d += dt.timedelta(1)
    return e
def rows(lg, ev):
    out = []
    for e in ev:
        try:
            c = e['competitions'][0]; a = c.get('venue', {}).get('address', {}); st = a.get('state'); city = (a.get('city') or '').lower()
            if not st or (st, city) not in P or c.get('neutralSite'): continue
            home = [x['team']['displayDisplayName' if 0 else 'displayName'] for x in c['competitors'] if x['homeAway'] == 'home'][0]
            d = (dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00')) - dt.timedelta(hours=7)).date().isoformat()
            la, lo = P[(st, city)]; out.append([d, lg, home, la, lo])
        except Exception: continue
    return out
start = sys.argv[1] if len(sys.argv) > 1 else None
old = json.load(open(OUT)) if os.path.exists(OUT) else {'g': []}
today = dt.date.today(); s = dt.date(int(start[:4]), int(start[4:]), 1) if start else dt.date(today.year, today.month, 1) - dt.timedelta(40)
months = []; d = dt.date(s.year, s.month, 1); end = today + dt.timedelta(200)
while d <= end: months.append(d.strftime('%Y%m')); d = (d + dt.timedelta(32)).replace(day=1)
new = []
with cf.ThreadPoolExecutor(8) as ex:
    fs = {ex.submit(fetch, lg, p, g, m): lg for lg, p, g in LG for m in months}
    for f in cf.as_completed(fs): new += rows(fs[f], f.result())
cut = months[0][:4] + '-' + months[0][4:] + '-01'
g = [r for r in old['g'] if r[0] < cut] + new
g = sorted({tuple(r) for r in g})
json.dump({'built': today.isoformat(), 'g': [list(r) for r in g]}, open(OUT, 'w'), separators=(',', ':'))
print('games', len(g), 'new', len(new))
