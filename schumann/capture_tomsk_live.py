"""Live capture: fetch the current Tomsk (sos70.ru) SR charts, digitize them, and merge into data/schumann_tomsk_live.csv.
Each chart covers ~3 days, so running every 6-12 h gives overlap. Raw images are NOT kept in the repo."""
import os, sys, subprocess, tempfile, urllib.request, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(H, '..', 'data', 'schumann_tomsk_live.csv')
URL = 'https://sos70.ru/provider.php?file={}.jpg'
tmp = tempfile.mkdtemp(); imgs = []
for k in ('srf', 'sra', 'srq'):
    p = os.path.join(tmp, f'live_{k}.jpg')
    try:
        req = urllib.request.Request(URL.format(k), headers={'User-Agent': 'eugene-sky SR archiver (github.com/Churchy156/eugene-sky)'})
        open(p, 'wb').write(urllib.request.urlopen(req, timeout=60).read()); imgs.append(p)
    except Exception as e: print('fetch failed', k, e)
if not imgs: sys.exit(0)
raw = os.path.join(tmp, 'raw.csv')
subprocess.run([sys.executable, os.path.join(H, 'digitize_tomsk.py'), raw] + imgs, check=True, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
n = pd.read_csv(raw)
n = n[(n['clip'] == 0) & (n['ncal'] >= 3) & (n['cov'] >= 0.34)].copy()
n['captured_utc'] = pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M'); n['src'] = n['src'].str.replace(r'.*/', '', regex=True)
old = pd.read_csv(OUT) if os.path.exists(OUT) else n.iloc[:0]
a = pd.concat([old, n]).drop_duplicates(['time_utc', 'var'], keep='last').sort_values(['time_utc', 'var'])   # newest snapshot wins
a.to_csv(OUT, index=False); print('rows', len(a), 'new', len(n))
