#!/usr/bin/env python3
"""Publish 'I'm alive and able to send' to GitHub as repo Actions variable ALERT_PRIMARY_HEARTBEAT (UTC ISO).
GitHub's backup workflow skips its webhook while this is under 30 minutes old. No commits are made.
Token: GH_TOKEN_REF (op://...) or GH_TOKEN in /etc/eugene-alerts/alerts.env. Fine-grained PAT, repo
Churchy156/eugene-sky, permission 'Variables: Read and write'. Never printed."""
import os, sys, json, datetime as dt, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from send_alert import secret
REPO = os.environ.get('GH_REPO', 'Churchy156/eugene-sky'); NAME = 'ALERT_PRIMARY_HEARTBEAT'

def call(method, url, tok, body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json',
                                          'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'eugene-alerts-vm'})
    with urllib.request.urlopen(req, timeout=30) as r: return r.status

def main():
    if not (os.environ.get('GH_TOKEN_REF') or os.environ.get('GH_TOKEN')): print('heartbeat skipped: no GitHub token configured'); return 3
    tok = secret('GH_TOKEN'); now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    base = f'https://api.github.com/repos/{REPO}/actions/variables'
    try: st = call('PATCH', f'{base}/{NAME}', tok, {'name': NAME, 'value': now})
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
        st = call('POST', base, tok, {'name': NAME, 'value': now})
    print(f'heartbeat {now} ({st})'); return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as e: print(f'heartbeat failed: {type(e).__name__}: {str(e)[:200]}'); sys.exit(1)
