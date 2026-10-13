"""World view data (rebuilt from original sources, cited):
 - Bitcoin reachable nodes per country: bitnodes.io snapshot (IPs) geolocated with DB-IP Lite country DB (CC BY 4.0)
 - Life expectancy SP.DYN.LE00.IN; GDP per person employed SL.GDP.PCAP.EM.KD (World Bank WDI, CC BY 4.0)
 - Rule of Law estimate RL.EST (World Bank WGI, CC BY 4.0) as property-rights/fiscal proxy
 - Firm/dispatchable electricity share = fossil + nuclear + hydro share (Our World in Data energy dataset, CC BY 4.0; Ember/EI)
 - IODA country-level internet outage events (14 d); Feodo C2 by country (abuse.ch)
 - Physical bitcoin attacks: jlopp/physical-bitcoin-attacks attacks.json (Unlicense)
Output zip_src/data/world.json"""
import json, csv, io, gzip, urllib.request, datetime as dt, ipaddress, bisect, time, collections, os
UA = {'User-Agent': 'Mozilla/5.0 eugene-sky (github.com/Churchy156/eugene-sky)'}
def get(u, t=120, raw=False):
    for i in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read()
            return r if raw else json.loads(r)
        except Exception as e: err = e; time.sleep(5)
    print('fail', u[:90], err); return None
W = {'built': dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'), 'c': collections.defaultdict(dict), 'src': {}}
# World Bank
iso2to3 = {}
for ind, key, src in (('SP.DYN.LE00.IN', 'life', ''), ('SL.GDP.PCAP.EM.KD', 'gdp_emp', ''), ('RL.EST', 'rule', '&source=3'), ('NY.GDP.PCAP.PP.CD', 'gdp_pc', '')):
    j = get(f'https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&per_page=20000&mrnev=1{src}')
    for r in (j[1] if j and len(j) > 1 else []) or []:
        c3 = r.get('countryiso3code') or ''
        if len(c3) == 3 and r.get('value') is not None:
            W['c'][c3][key] = round(r['value'], 2); W['c'][c3][key + '_yr'] = r['date']; W['c'][c3]['name'] = r['country']['value']
            iso2to3[r['country']['id']] = c3
for c, v in W['c'].items():
    if v.get('gdp_emp'): v['hours_10k'] = round(10000 / (v['gdp_emp'] / 2000), 1)  # hours of average work (2,000 h/yr) to produce $10k
# country list for iso2 mapping
cl = get('https://api.worldbank.org/v2/country?format=json&per_page=400')
for r in (cl[1] if cl else []): iso2to3[r['iso2Code']] = r['id']
# OWID energy
e = get('https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv', raw=True)
if e:
    best = {}
    for r in csv.DictReader(io.StringIO(e.decode())):
        c = r['iso_code']
        if len(c) != 3: continue
        try: f = sum(float(r[k] or 0) for k in ('fossil_share_elec', 'nuclear_share_elec', 'hydro_share_elec')); ok = r['fossil_share_elec'] != ''
        except Exception: continue
        if ok and (c not in best or int(r['year']) > best[c][0]): best[c] = (int(r['year']), round(min(100, f), 1))
    for c, (y, f) in best.items(): W['c'][c]['firm'] = f; W['c'][c]['firm_yr'] = y
# Bitcoin nodes
bn = get('https://bitnodes.io/api/v1/snapshots/latest/', t=180)
if bn:
    m = dt.date.today()
    db = None
    for k in range(3):
        mm = (m.replace(day=1) - dt.timedelta(days=28 * k)).strftime('%Y-%m')
        db = get(f'https://download.db-ip.com/free/dbip-country-lite-{mm}.csv.gz', t=300, raw=True)
        if db: break
    if db:
        st4, cc4, st6, cc6 = [], [], [], []
        for a, b, c in csv.reader(io.StringIO(gzip.decompress(db).decode())):
            ip = ipaddress.ip_address(a)
            (st4 if ip.version == 4 else st6).append(int(ip)); (cc4 if ip.version == 4 else cc6).append(c)
        cnt = collections.Counter(); tor = 0
        for n in bn['nodes']:
            h = n.rsplit(':', 1)[0].strip('[]')
            if h.endswith('.onion'): tor += 1; continue
            try: ip = ipaddress.ip_address(h)
            except Exception: continue
            S, C = (st4, cc4) if ip.version == 4 else (st6, cc6)
            i = bisect.bisect_right(S, int(ip)) - 1
            if i >= 0: cnt[C[i]] += 1
        for c2, n in cnt.items():
            c3 = iso2to3.get(c2)
            if c3: W['c'][c3]['btc_nodes'] = n
        W['btc'] = {'total': bn['total_nodes'], 'tor': tor, 'ts': bn['timestamp']}
# IODA country outages, 14 d
now = int(time.time())
io_ = get(f'https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events?from={now - 14 * 86400}&until={now}&entityType=country&limit=10000')
for x in (io_ or {}).get('data', []):
    c3 = iso2to3.get(x['location'].split('/')[-1])
    if c3: W['c'][c3]['ioda14'] = W['c'][c3].get('ioda14', 0) + 1
# Feodo C2 by country
f = get('https://feodotracker.abuse.ch/downloads/ipblocklist.json')
for x in f or []:
    c3 = iso2to3.get(x.get('country') or '')
    if c3: W['c'][c3]['feodo'] = W['c'][c3].get('feodo', 0) + 1
# Lopp physical attacks
a = get('https://raw.githubusercontent.com/jlopp/physical-bitcoin-attacks/master/attacks.json')
W['attacks'] = [[x['date']['raw'], x['date'].get('year'), x.get('victim', ''), x.get('location', ''), (x['links'][0]['label'] if x.get('links') else x.get('description', ''))[:160],
                 (x['links'][0]['url'] if x.get('links') else ''), x.get('lat'), x.get('lng'), iso2to3.get(x.get('country_code') or '', '')] for x in (a or [])]
for r in W['attacks']:
    if r[8]: W['c'][r[8]]['attacks'] = W['c'][r[8]].get('attacks', 0) + 1
json.dump(W, open('zip_src/data/world.json', 'w'), separators=(',', ':'))
print('world countries', len(W['c']), 'btc', W.get('btc'), 'attacks', len(W['attacks']))
