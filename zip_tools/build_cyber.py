"""Cyber daily history (keyless): CISA KEV, NVD critical/high CVE counts, IODA US-state internet outages, SANS ISC,
abuse.ch URLhaus/ThreatFox/Feodo. Incremental cache zip_src/data/cyber.json; daily table data/cyber_daily.json.
Env NVD_DAYS (default 12; first local run used 400)."""
import json, os, io, csv, time, urllib.request, datetime as dt, collections, statistics
OUT = 'zip_src/data/cyber.json'
def get(u, raw=False, h=None, t=60):
    err = None
    for i in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'eugene-sky (github.com/Churchy156/eugene-sky)', **(h or {})}), timeout=t).read()
            return r.decode('utf-8', 'replace') if raw else json.loads(r)
        except Exception as e: err = e; time.sleep(6 * (i + 1))
    print('fail', u[:90], err); return None
C = json.load(open(OUT)) if os.path.exists(OUT) else {}
D = collections.defaultdict(dict, {k: v for k, v in C.get('daily', {}).items()})
today = dt.date.today(); now = int(time.time())
# CISA KEV
k = get('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json')
if k:
    cnt = collections.Counter(v['dateAdded'] for v in k['vulnerabilities'])
    for d in list(D): D[d].pop('kev', None)
    for d, n in cnt.items(): D[d]['kev'] = n
    C['kev_recent'] = [[v['dateAdded'], v['cveID'], v['vendorProject'], v['product'], v['vulnerabilityName'][:120], v.get('knownRansomwareCampaignUse', '')] for v in sorted(k['vulnerabilities'], key=lambda v: v['dateAdded'])[-25:]][::-1]
    C['kev_total'] = len(k['vulnerabilities'])
# NVD (keyless: 5 requests / 30 s)
nd = int(os.environ.get('NVD_DAYS', '12'))
for i in range(nd, 0, -1):
    d = today - dt.timedelta(i)
    if 'nvd_crit' in D.get(str(d), {}) and i > 3: continue
    for sev, key in (('CRITICAL', 'nvd_crit'), ('HIGH', 'nvd_high')):
        r = get(f'https://services.nvd.nist.gov/rest/json/cves/2.0?pubStartDate={d}T00:00:00.000&pubEndDate={d}T23:59:59.999&cvssV3Severity={sev}&resultsPerPage=1')
        if r is not None: D[str(d)][key] = r['totalResults']
        time.sleep(6.5)
# IODA: US state-level outage events (30-day windows)
st = C.get('ioda_through', now - 3 * 365 * 86400); ev = C.get('ioda_recent', [])
s = max(st - 2 * 86400, now - 3 * 365 * 86400)
while s < now:
    e = min(s + 30 * 86400, now)
    r = get(f'https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events?from={s}&until={e}&entityType=region&relatedTo=country/US&limit=10000', t=120)
    for x in (r or {}).get('data', []):
        d = str(dt.datetime.fromtimestamp(x["start"], dt.timezone.utc).date()); key = (x['location'], x['start'], x['datasource'])
        D[d].setdefault('_ioda', [])
        if list(key) not in D[d]['_ioda']: D[d]['_ioda'].append(list(key))
        if x['start'] > now - 14 * 86400: ev.append([x['start'], x['location_name'], x['duration'], x['datasource'], round(x['score'])])
    s = e
C['ioda_through'] = now
C['ioda_recent'] = sorted({tuple(x) for x in ev if x[0] > now - 14 * 86400}, reverse=True)
for d, v in D.items():
    if '_ioda' in v:
        v['ioda_us'] = len(v['_ioda']); v['ioda_or'] = sum(1 for x in v['_ioda'] if x[0] == 'region/4420')  # IODA region code for Oregon
# SANS ISC daily summary (records, sources)
s0 = min([d for d in D if 'isc_rec' in D[d]] or ['2020-01-01'])
fr = '2020-01-01' if s0 == '2020-01-01' and not any('isc_rec' in v for v in D.values()) else str(today - dt.timedelta(15))
a = dt.date.fromisoformat(fr)
while a < today:
    b = min(a + dt.timedelta(180), today)
    for x in get(f'https://isc.sans.edu/api/dailysummary/{a}/{b}?json', t=40) or []:
        if isinstance(x, dict) and x.get('date'): D[x['date']]['isc_rec'] = int(x.get('records') or 0); D[x['date']]['isc_src'] = int(x.get('sources') or 0)
    a = b + dt.timedelta(1)
ic = get('https://isc.sans.edu/api/infocon?json'); C['infocon'] = (ic or {}).get('status', '?')
tp = get('https://isc.sans.edu/api/topports/records/10?json') or {}
C['topports'] = [[v['targetport'], v['records'], v['sources']] for k2, v in sorted(tp.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99) if isinstance(v, dict)]
# abuse.ch
u = get('https://urlhaus.abuse.ch/downloads/csv_recent/', raw=True)
if u:
    cnt = collections.Counter(l.split('","')[1][:10] for l in u.splitlines() if l.startswith('"') and '","' in l)
    for d, n in cnt.items():
        if d < str(today): D[d]['urlhaus'] = n
t = get('https://threatfox.abuse.ch/export/json/recent/')
if t:
    cnt = collections.Counter(x['first_seen_utc'][:10] for L in t.values() for x in L)
    for d, n in cnt.items():
        if d < str(today): D[d]['threatfox'] = n
f = get('https://feodotracker.abuse.ch/downloads/ipblocklist.json')
if f:
    C['feodo'] = [[x['ip_address'], x['port'], x['status'], x.get('country') or '', x.get('as_name') or '', x.get('malware') or '', (x.get('last_online') or '')[:10]] for x in f]
    D[str(today)]['feodo_online'] = sum(1 for x in f if x['status'] == 'online')
for v in D.values(): v.pop('_ioda_tmp', None)
C['daily'] = D; C['built'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
cols = ['kev', 'nvd_crit', 'nvd_high', 'ioda_us', 'ioda_or', 'isc_rec', 'isc_src', 'urlhaus', 'threatfox', 'feodo_online']
# honest correlations vs space weather / Lane County outages
try:
    import pandas as pd
    e = pd.read_csv('data/eugene_env_daily.csv.gz', usecols=['date', 'kp_max', 'outage_lane_cust_out_peak', 'flares_M', 'flares_X']).set_index('date')
    cy = pd.DataFrame({d: {c: v.get(c) for c in cols} for d, v in D.items()}).T
    j = cy.join(e, how='inner').apply(pd.to_numeric, errors='coerce')
    corr = []
    for c in cols:
        for z in ('kp_max', 'outage_lane_cust_out_peak'):
            x = j[[c, z]].dropna()
            if len(x) >= 60: corr.append([c, z, round(x[c].corr(x[z], method='spearman'), 3), len(x)])
    C['corr'] = corr
except Exception as ex: print('corr skipped', ex)
json.dump(C, open(OUT, 'w'), separators=(',', ':'), default=list)
json.dump({'cols': ['cyber_' + c for c in cols], 'start': '9999-01-01', 'd': {d: [v.get(c) for c in cols] for d, v in D.items() if d >= '2010-01-01'}}, open('data/cyber_daily.json', 'w'))
pub = {k: v for k, v in C.items() if k != 'daily'}; pub['daily'] = {d: {c: v[c] for c in cols if c in v} for d, v in D.items()}
json.dump(pub, open('zip_src/data/cyber_pub.json', 'w'), separators=(',', ':'), default=list)
print('cyber days', len(D), 'corr', C.get('corr'))
