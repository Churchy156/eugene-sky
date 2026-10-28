"""Wayback helper: wb.py OUTFILE URL [prefer=last|first]  -> fetch best 200 snapshot (raw, id_)."""
import sys,requests,time,os
H={'User-Agent':'eugene-sky school calendar research (personal)'}
def snaps(u):
    for k in range(3):
        try:
            r=requests.get('https://web.archive.org/cdx/search/cdx',params=dict(url=u,filter='statuscode:200',fl='timestamp,original,length'),headers=H,timeout=90)
            return [l.split() for l in r.text.splitlines() if l.strip()]
        except Exception: time.sleep(5)
    return []
def fetch(out,u,prefer='last',maxts='20240601'):
    s=[x for x in snaps(u) if x[0]<maxts]
    if not s: print('NOSNAP',u); return None
    ts,orig,_=s[-1] if prefer=='last' else s[0]
    for k in range(3):
        try:
            r=requests.get(f'https://web.archive.org/web/{ts}id_/{orig}',headers=H,timeout=90)
            if r.ok: open(out,'wb').write(r.content); print(out,len(r.content),ts,orig); return ts
        except Exception: time.sleep(5)
    print('FAIL',u)
if __name__=='__main__': fetch(sys.argv[1],sys.argv[2],*(sys.argv[3:5]))
