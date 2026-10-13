"""Fetch worldwide OpenSky state vectors (OAuth2 client creds) -> <out>/aircraft.json (compact).
Cost: 4 credits per global call. Called up to 4x per 10-min workflow run => ~2300 of 4000 credits/day."""
import json, os, sys, time, urllib.request, urllib.parse
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
cid, sec = os.environ.get('OPENSKY_CLIENT_ID'), os.environ.get('OPENSKY_CLIENT_SECRET')
d = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': cid, 'client_secret': sec}).encode()
tok = json.load(urllib.request.urlopen('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', d, timeout=30))['access_token']
r = urllib.request.urlopen(urllib.request.Request('https://opensky-network.org/api/states/all?extended=1', headers={'Authorization': 'Bearer ' + tok}), timeout=60)
j = json.load(r)
ac = []
for s in j.get('states') or []:
    if s[6] is None or s[5] is None: continue
    alt = 'g' if s[8] else (None if s[7] is None else round(s[7] * 3.281))
    ac.append([s[0], (s[1] or '').strip(), round(s[6], 4), round(s[5], 4), alt, None if s[9] is None else round(s[9] * 1.944), None if s[10] is None else round(s[10]), s[17] if len(s) > 17 else None, s[2]])
json.dump({'time': j.get('time'), 'fetched': int(time.time()), 'src': 'OpenSky Network', 'fields': ['hex','flight','lat','lon','alt_ft','gs_kt','track','cat','country'], 'ac': ac}, open(os.path.join(out, 'aircraft.json'), 'w'), separators=(',', ':'))
print('aircraft', len(ac), 'credits left', r.headers.get('X-Rate-Limit-Remaining'))
