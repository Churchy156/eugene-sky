"""Pick the best parsed calendar per district-year and write school_calendars.csv + coverage csv."""
import os,sys,glob,re,csv,datetime as dt
sys.path.insert(0,os.path.dirname(__file__))
import build as B, webfmt as W, listfmt as L, grid as G
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
NAMES=dict(**{'4j':'4J Eugene'},bethel='Bethel',springfield='Springfield',junction_city='Junction City',monroe='Monroe',
           harrisburg='Harrisburg',creswell='Creswell',pleasant_hill='Pleasant Hill',south_lane='South Lane (Cottage Grove)')
def labor(y):
    d=dt.date(y,9,1); return d+dt.timedelta((0-d.weekday())%7)
def cands(f):
    out=[]
    try: text=B.doctext(f)
    except Exception: return out
    sy0=B.school_year(f,text)
    try:
        sy,items,_=B.parse_doc(f)
        if sy and items:
            s=B.summarize(sy,items); s['labels']=[(B.expand(sy,it),it['label']) for it in items]; out.append((sy,'list',s))
    except Exception: pass
    try:
        for sy,s in W.parse(f,sy0).items(): s['labels']=[(ds,l) for ds,l,k in s['ev']]; out.append((sy,'keydates',s))
    except Exception as e: pass
    if sy0:
        try:
            s,its=L.summary(f,sy0); s['labels']=[([d],l) for d,l in its]
            if its: out.append((sy0,'monthlist',s))
        except Exception: pass
        if f.endswith('.pdf'):
            try:
                s,g=G.grid_summary(f,sy0); s['labels']=[([d],t) for d,t in g.items() if t]
                if g: out.append((sy0,'grid',s))
            except Exception: pass
    return out
def repair(dist,sy,s,pr):
    notes=[]; pr=list(pr)
    if dist=='springfield' and sy==2026 and not s['first']:
        s['first']=dt.date(2026,9,9); notes.append('first day Sep 9 from 2026-27 PDF text'); 
    if any(p.startswith('first=None') for p in pr) and s['last'] and not any(p.startswith('last') for p in pr):
        if not s['first']: s['first']=labor(sy)+dt.timedelta(2); notes.append('first day estimated (Wed after Labor Day)')
    if 'no_spring' in pr and dist=='harrisburg':
        a=dt.date(sy+1,3,31); a-=dt.timedelta(a.weekday());  a-= dt.timedelta(7) if a.day>25 else dt.timedelta(0)
        s['nos'].update(a+dt.timedelta(i) for i in range(5)); notes.append('spring break week estimated (only shown by colour)')
    pr=B.check(sy,s)
    if dist=='harrisburg': pr=[p for p in pr if not p.startswith('ndays')]; notes.append('student-day count not checked (calendar lists 149 student days; extra Friday closures shown only by colour are missing)')
    return pr,notes
PREF=re.compile(r'revis|updat|amend|approved|adopted|final|rev\d',re.I)
def main(out_dir):
    best={}; seen=[]
    for dist in NAMES:
        for f in sorted(glob.glob(f'{dist}/*.pdf')+glob.glob(f'{dist}/*.html')):
            for sy,meth,s in cands(f):
                if sy is None or sy<2005 or sy>2026: continue
                pr=B.check(sy,s); notes=[]
                if pr: pr,notes=repair(dist,sy,s,pr)
                seen.append((dist,sy,f,meth,pr))
                if pr: continue
                key=(dist,sy); score=(len(notes)==0, bool(PREF.search(f)), os.path.basename(f).startswith(('x_','web_')), len(s.get('labels',[])), f)
                if key not in best or score>best[key][0]: best[key]=(score,f,meth,s,notes)
    rows=[];cov=[]
    for (dist,sy),(sc,f,meth,s,notes) in sorted(best.items()):
        lab={}
        for ds,l in s.get('labels',[]):
            for d in ds or []:
                if d: lab.setdefault(d,[]).append(re.sub(r'\s+',' ',l).strip()[:90])
        def L_(d): return '; '.join(dict.fromkeys(lab.get(d,[])))[:160]
        src=f; q='real' if not notes else 'real (patched)'
        ev=[(s['first'],'first_day'),(s['last'],'last_day')]
        ev+=[(d,'no_school') for d in s['nos'] if s['first']<=d<=s['last'] and d.weekday()<5]
        ev+=[(d,'no_school_some_grades') for d in s['part'] if d not in s['nos'] and s['first']<=d<=s['last'] and d.weekday()<5]
        ev+=[(d,'early_release') for d in s['early'] if d not in s['nos'] and s['first']<=d<=s['last'] and d.weekday()<5]
        ev+=[(d,'conference') for d in s.get('conf',set()) if s['first']<=d<=s['last'] and d.weekday()<5]
        for d,t in sorted(ev,key=lambda x:(x[0],x[1])):
            rows.append(dict(district=NAMES[dist],district_key=dist,school_year=f'{sy}-{str(sy+1)[2:]}',date=d.isoformat(),event_type=t,label=L_(d),quality=q,source_file=src,parse_method=meth))
        cov.append(dict(district=NAMES[dist],district_key=dist,school_year=f'{sy}-{str(sy+1)[2:]}',status=q,first_day=s['first'],last_day=s['last'],
            student_days=B.session_days(s),no_school_days=len([d for d in s['nos'] if s['first']<=d<=s['last'] and d.weekday()<5]),early_release_days=len(s['early']),source_file=src,parse_method=meth,notes='; '.join(notes)))
    os.makedirs(out_dir,exist_ok=True)
    for name,data in [('school_calendars.csv',rows),('school_calendar_coverage.csv',cov)]:
        with open(os.path.join(out_dir,name),'w',newline='') as fh:
            w=csv.DictWriter(fh,fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    with open(os.path.join(out_dir,'_parse_log.tsv'),'w') as fh:
        for r in seen: fh.write('\t'.join(map(str,r))+'\n')
    for c in cov: print(c['district_key'],c['school_year'],c['status'],c['first_day'],c['last_day'],c['student_days'],c['parse_method'],os.path.basename(c['source_file'])[:50],c['notes'][:60])
    print(len(rows),'rows')
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '/tmp/sch/out')
