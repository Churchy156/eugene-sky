"""Live extras for the 10-min relay: FIRMS hotspots (FIRMS_MAP_KEY), FAA NAS airport status. Output <out>/live/*.json"""
import os, sys, json, csv, io, re, urllib.request, datetime as dt
OUT = (sys.argv[1] if len(sys.argv) > 1 else '/tmp/out') + '/live'; os.makedirs(OUT, exist_ok=True)
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')
def get(u, t=60): return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'eugene-sky'}), timeout=t).read().decode('utf-8', 'replace')
K = os.environ.get('FIRMS_MAP_KEY') or (open('/workspace/eugene-env/.firms_key').read().strip() if os.path.exists('/workspace/eugene-env/.firms_key') else '')
if K:
    pts = []
    for src in ('VIIRS_NOAA20_NRT', 'VIIRS_SNPP_NRT', 'MODIS_NRT'):
        try:
            for r in csv.DictReader(io.StringIO(get(f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{K}/{src}/-180,15,-60,72/1', 120))):
                pts.append([round(float(r['latitude']), 4), round(float(r['longitude']), 4), round(float(r.get('frp') or 0), 1), r.get('confidence', ''), r['acq_date'] + ' ' + r['acq_time'].zfill(4), src.split('_')[0] + ('-20' if 'NOAA20' in src else '')])
        except Exception as e: print('firms', src, e)
    json.dump({'built': now, 'p': pts}, open(f'{OUT}/firms.json', 'w'), separators=(',', ':')); print('firms', len(pts))
try:
    x = get('https://nasstatus.faa.gov/api/airport-status-information'); out = []
    for typ, blk in re.findall(r'<Delay_type>\s*<Name>(.*?)</Name>(.*?)</Delay_type>', x, re.S):
        for a in re.findall(r'<(?:Program|Ground_Stop|Delay|Airport)>(.*?)</(?:Program|Ground_Stop|Delay|Airport)>', blk, re.S):
            g = lambda t: (re.search(f'<{t}>(.*?)</{t}>', a, re.S) or [None, ''])[1].strip()
            code = g('ARPT') or g('ARPT_ID') or g('Code')
            if code: out.append([code, typ, g('Reason'), ' '.join(filter(None, [g('Avg'), g('Max'), g('End_Time'), g('Min'), g('Trend'), g('Start'), g('Reopen')]))[:120]])
    json.dump({'built': now, 'a': out}, open(f'{OUT}/faa.json', 'w'), separators=(',', ':')); print('faa', len(out))
except Exception as e: print('faa', e)
