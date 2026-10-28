"""Power & grid for Steven's four utilities (EWEB, Emerald PUD, Blachly-Lane, Pacific Power) + nearby BPA lines.
All sources are the public JSON files each utility's own outage map loads (no login, no keys):
  EWEB          ArcGIS FeatureServer PublicOutageMap_Public_View (eweb.org outage map)
  Emerald PUD   https://outagemap-data.cloud.coop/epud/Hosted_Outage_Map/summary.json        (NISC map epud.outagemap.coop)
  Blachly-Lane  https://outagemap-data.cloud.coop/blachlylane/Hosted_Outage_Map/summary.json (NISC map blachlylane.outagemap.coop)
  Pacific Power https://www.pacificpower.net/etc/pcorp/datafiles/outagemap/mapOR.json + listOR.json (pacificpower.net/outages-safety.html)
  BPA           https://transmission.bpa.gov/Business/Operations/Outages/DIR/TODAY.HTM
Used by daily_report.py (report_lines) and update.py (snapshot -> daily outage_live_* columns)."""
import os, re, html, math, datetime as dt
import requests
UA={'User-Agent':'Mozilla/5.0 (eugene-sky daily report; public outage map data)'}
T=int(os.environ.get('FEED_TIMEOUT','25'))
EUG=(44.052,-123.087); NEAR_MI=45
LINKS=dict(eweb='https://www.eweb.org/outages-and-safety/power-outages/power-outage-map',
           epud='https://epud.outagemap.coop/', blachly='https://blachlylane.outagemap.coop/',
           pacific='https://www.pacificpower.net/outages-safety.html')
def _get(u,**k):
    r=requests.get(u,headers=UA,timeout=T,**k); r.raise_for_status(); return r
def _mi(a,b):
    la1,lo1,la2,lo2=map(math.radians,(*a,*b))
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 3958.8*2*math.asin(math.sqrt(h))
_PL=[]
def _town(lat,lon):
    if not _PL:
        for p in (os.path.join(os.path.dirname(__file__),'..','data','us_places.tsv'),'/workspace/eugene-sky/data/us_places.tsv'):
            if os.path.exists(p):
                for l in open(p):
                    s=l.rstrip('\n').split('\t')
                    if len(s)>=4 and s[0]=='OR': _PL.append((s[1],float(s[2]),float(s[3])))
                break
    if not _PL: return None
    return min(_PL,key=lambda x:(x[1]-lat)**2+((x[2]-lon)*0.72)**2)[0]
def _plural(n,w): return f"{n:,} {w}{'' if n==1 else 's'}"

def eweb():
    f=_get('https://services7.arcgis.com/6AM8yPAeyXiPc9eF/arcgis/rest/services/PublicOutageMap_Public_View/FeatureServer/0/query',
           params=dict(where='1=1',outFields='custcnt,cause,etor,status,name',returnGeometry='false',f='json')).json()['features']
    a=[x['attributes'] for x in f if x['attributes'].get('status')!='Restored']
    big=max(a,key=lambda x:x.get('custcnt') or 0) if a else None
    return dict(outages=len(a),cust=sum(x.get('custcnt') or 0 for x in a),
                largest=(f"{big.get('custcnt') or 0} customers{(' near '+big['name']) if big.get('name') else ''}{(', cause: '+big['cause'].lower()) if big.get('cause') else ''}{(', expected back '+big['etor']) if big.get('etor') else ''}") if big else None)

def nisc(slug,prefer):
    d=_get(f'https://outagemap-data.cloud.coop/{slug}/Hosted_Outage_Map/summary.json').json()
    o=d.get('outages') or []
    cust=sum(x.get('nbrOut') or 0 for x in o); planned=sum(1 for x in o if x.get('planned'))
    sets={s['id']:s['regions'] for s in d.get('regionDataSets',[])}
    regs=next((sets[k] for k in prefer if k in sets),[])
    hit=sorted([r for r in regs if (r.get('numberOut') or 0)>0],key=lambda r:-r['numberOut'])
    largest=f"{hit[0]['id'].title()} ({hit[0]['numberOut']} of {hit[0]['numberServed']:,} out)" if hit else None
    return dict(outages=len(o),cust=cust,planned=planned,served=d.get('totalServed'),largest=largest)

def pacific():
    m=_get('https://www.pacificpower.net/etc/pcorp/datafiles/outagemap/mapOR.json').json()
    try: lst=_get('https://www.pacificpower.net/etc/pcorp/datafiles/outagemap/listOR.json').json()
    except Exception: lst={}
    o=m.get('outages') or []
    for x in o:
        x['mi']=_mi(EUG,(x['latitude'],x['longitude'])); x['town']=_town(x['latitude'],x['longitude'])
    near=[x for x in o if x['mi']<=NEAR_MI]
    lane=next((c for c in lst.get('counties',[]) if c.get('countyName','').lower()=='lane'),None)
    def desc(x): return (f"{x.get('custOut',0)} customers near {x.get('town') or 'ZIP '+str(x.get('zip'))}, ZIP {x.get('zip')}, {x['mi']:.0f} mi from Eugene"
                         f"{', cause: '+x['cause'].lower() if x.get('cause') else ''}{', expected back '+x['etr'].replace('Before ','before ') if x.get('etr') else ''}")
    bigN=max(near,key=lambda x:x.get('custOut',0)) if near else None
    bigS=max(o,key=lambda x:x.get('custOut',0)) if o else None
    return dict(outages=sum(x.get('outCount',1) for x in near),cust=sum(x.get('custOut',0) for x in near),
                lane_cust=(lane['custOutPlan']+lane['custOutUnplan']) if lane else 0,
                state_outages=m.get('count',len(o)),state_cust=m.get('totalState',sum(x.get('custOut',0) for x in o)),
                largest=desc(bigN) if bigN else None,state_largest=desc(bigS) if bigS else None,updated=m.get('last_upd'))

CORE=r'Willakenzie|Cal Young|Mt\.? ?Vernon|Walton|Currin|Santa Clara|Blachly|Emerald|Sprngfld|Springfield'
LOCAL=r'Willakenzie|Cal Young|Mt\.? ?Vernon|Walton|Currin|Santa Clara|McKenzie|Alvey|Hawkins|Willow Creek|Bertelsen|Thurston|Hayden|Eugene|Sprngfld|Springfield|Blachly|Emerald|Lane|Jasper|Lookout|Fern Ridge|Junction|Cheshire|Noti|Veneta|Marcola|Goshen|Dexter'
NAMES={'Sprngfld Util Brd':'Springfield Utility Board','Blachly-Lane Co':'Blachly-Lane','Lane Elec Coop':'Lane Electric','Emerald Peoples Utl Dst':'Emerald PUD','Eugene Wtr & Elec Brd':'EWEB'}
def _bpa_time(s):
    try: return dt.datetime.strptime(s.replace('\xa0',' ').strip(),'%m/%d/%Y %H:%M')
    except Exception: return None
def _fmt(t): return t.strftime('%a %b %-d, %-I:%M %p').replace(':00 ',' ') if t else '?'
def _plain_bpa(r):
    name=r[2]; kv=r[3].replace('.0','')
    m=re.match(r'^([^:]+):\s*(.+?)\s+[\d.]+kV\s+(Feeder.*)$',name)
    if m:
        who=m.group(2)
        for k,v in NAMES.items(): who=who.replace(k,v)
        what=f"the {who} {m.group(3).lower()} at BPA's {m.group(1)} substation"
    else:
        what=re.sub(r'\s*[\d.]+kV line$',' power line',name)
        what=re.sub(r'(?<=[\w)])-(?=\w)','–',what).replace(' of ',' of the ')
        what=what if what.lower().startswith(('the ',)) else 'the '+what
    plan=r[5].lower().startswith('plan'); why=r[6].lower()
    kind=('planned ' + {'maintenance':'maintenance','urgent':'urgent repair work','construction':'construction work'}.get(why,why+' work')) if plan else f"an unplanned outage ({why})"
    start,end=_bpa_time(r[0]),_bpa_time(r[1])
    status=f"out of service since {_fmt(start)}" if not end else f"back in service {_fmt(end)}"
    return f"BPA {kind} on {what} ({kv} kV) — {status}"
def bpa_local(maxn=4):
    h=_get('https://transmission.bpa.gov/Business/Operations/Outages/DIR/TODAY.HTM').text
    rows=[[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'(?s)<t[dh].*?</t[dh]>',r)] for r in re.findall(r'(?s)<tr.*?</tr>',h)]
    now=dt.datetime.now(); seen=set(); out=[]
    for r in rows:
        if len(r)<10 or r[9]!='EUG' or not re.search(LOCAL,r[2]) or r[2] in seen: continue
        seen.add(r[2]); end=_bpa_time(r[1])
        if end and (now-end).total_seconds()>36*3600: continue
        out.append(((0 if re.search(r'Blachly|Emerald|Walton',r[2]) else 1 if re.search(CORE,r[2]) else 2),(0 if not r[5].lower().startswith('plan') else 1),(0 if not end else 1),-(_bpa_time(r[0]) or now).timestamp(),r))
    out.sort(key=lambda x:x[:4])
    return [_plain_bpa(x[4]) for x in out[:maxn]],max(0,len(out)-maxn)

def bpa_grid():
    t=_get('https://transmission.bpa.gov/business/operations/Wind/baltwg.txt').text.splitlines()
    rows=[r.split('\t') for r in t if r[:2].isdigit() and len(r.split('\t'))>=6 and r.split('\t')[1].strip()]
    r=rows[-1]; return f"Northwest grid (BPA, {r[0].split()[-1]} PT): demand {int(float(r[1])):,} MW; hydro {int(float(r[3])):,} MW; wind/solar {int(float(r[2])):,} MW"

def _safe(fn,*a):
    try: return fn(*a),None
    except Exception as e: return None,e.__class__.__name__

def snapshot():
    """Customers out right now per utility (for daily max columns)."""
    s={}
    v,_=_safe(eweb);  s['outage_live_eweb_cust_out_max']=v['cust'] if v else None
    v,_=_safe(nisc,'epud',['Territory','ZipCode']); s['outage_live_epud_cust_out_max']=v['cust'] if v else None
    v,_=_safe(nisc,'blachlylane',['Cities','Substation']); s['outage_live_blachly_cust_out_max']=v['cust'] if v else None
    v,_=_safe(pacific)
    s['outage_live_pacific_near_cust_out_max']=v['cust'] if v else None
    s['outage_live_pacific_or_cust_out_max']=v['state_cust'] if v else None
    return s

def report_lines():
    L=[]
    def line(label,link,fn,*a):
        v,err=_safe(fn,*a)
        if v is None: L.append(f"- **{label}:** live data unavailable right now ({err}) — check the outage map: {link}"); return None
        return v
    v=line('EWEB',LINKS['eweb'],eweb)
    if v: L.append(f"- **EWEB:** {'no outages right now' if not v['outages'] else _plural(v['outages'],'outage')+', '+_plural(v['cust'],'customer')+' out'}"+(f". Largest: {v['largest']}" if v['largest'] else '')+'.')
    for key,label,slug,pref in [('epud','Emerald PUD','epud',['Territory','ZipCode']),('blachly','Blachly-Lane','blachlylane',['Cities','Substation'])]:
        v=line(label,LINKS[key],nisc,slug,pref)
        if v:
            now_txt = 'no outages right now' if not v['outages'] else _plural(v['outages'],'outage')+(' ({} planned)'.format(v['planned']) if v['planned'] else '')+', '+_plural(v['cust'],'customer')+' out'
            L.append(f"- **{label}:** {now_txt} (of {v['served']:,} served)"+(f". Hardest-hit area: {v['largest']}" if v['largest'] else '')+'.')
    v=line('Pacific Power',LINKS['pacific'],pacific)
    if v:
        s=f"- **Pacific Power:** {'no outages' if not v['outages'] else _plural(v['outages'],'outage')+', '+_plural(v['cust'],'customer')+' out'} within {NEAR_MI} mi of Eugene"
        if v['largest']: s+=f". Largest nearby: {v['largest']}"
        s+=f". Oregon-wide: {_plural(v['state_outages'],'outage')}, {_plural(v['state_cust'],'customer')} out"
        if not v['largest'] and v['state_largest']: s+=f" (largest: {v['state_largest']})"
        L.append(s+'.')
    v,err=_safe(bpa_local)
    if v is None: L.append(f"- **BPA power lines near Eugene:** report unavailable ({err}).")
    else:
        items,more=v
        if not items: L.append('- **BPA power lines near Eugene:** nothing out of service near Eugene in BPA\'s report.')
        else:
            L.append('- **BPA power lines near Eugene:**'+''.join(f"\n  - {x}" for x in items)+(f"\n  - …plus {more} more BPA item(s) in the Eugene district" if more else ''))
    g,_=_safe(bpa_grid)
    if g: L.append(f"- {g}.")
    L.append("- _Other area utilities (SUB, Lane Electric, Consumers Power) aren't tracked here; links in POWER_SOURCES.md._")
    return L

if __name__=='__main__':
    print('\n'.join(report_lines())); print(snapshot())
