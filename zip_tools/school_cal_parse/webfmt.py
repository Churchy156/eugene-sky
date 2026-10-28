"""Key-date lists written as 'Mon, Sept. 2: label' / 'Nov. 24-26, 2025: label' / 'Dec 19-Jan 5 Winter Break'.
Used for 4J/Springfield web pages and Harrisburg/Pleasant Hill list columns. Splits multi-year pages into blocks."""
import re,sys,os,datetime as dt
sys.path.insert(0,os.path.dirname(__file__)); import build
MON=r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
WD=r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?'
D=r'\d{1,2}(?:\s*\([A-Z]\))?'
H=re.compile(r'^\W{0,2}(?:(?P<wd>'+WD+r')(?:\s*-\s*'+WD+r')?,?\s+)?(?P<m1>'+MON+r')\.?\s*(?P<days>'+D+r'(?:\s*(?:,|&|and)\s*'+D+r')*)(?:\s*-\s*(?:(?P<m2>'+MON+r')\.?\s*)?(?P<d2>\d{1,2}))?(?:,?\s*(?P<y1>20\d\d))?(?:\s*-\s*(?P<m3>'+MON+r')\.?\s*(?P<d3>\d{1,2}),?\s*(?P<y3>20\d\d))?[\^*]?\s*(?:[:\-]\s*|\s+)(?P<label>[A-Za-z(*½].*)$')
WDN=dict(mon=0,tue=1,wed=2,thu=3,fri=4,sat=5,sun=6)
def mnum(s): return ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(s[:3].lower())+1
def raw_items(text):
    out=[]
    for line in text.replace('\u2010','-').replace('\u2011','-').replace('\u2013','-').replace('\u2014','-').replace('\u00a0',' ').replace('\u200b','').splitlines():
        for seg in re.split(r'\s{4,}',line.strip()):
            m=H.match(seg.strip())
            if not m: continue
            g=m.groupdict(); m1=mnum(g['m1'])
            days=[int(x) for x in re.findall(r'\d{1,2}(?!\d)',re.sub(r'\([A-Z]\)','',g['days']))]
            out.append(dict(m1=m1,days=days,m2=mnum(g['m2']) if g['m2'] else None,d2=int(g['d2']) if g['d2'] else None,
                y1=int(g['y1']) if g['y1'] else None,m3=mnum(g['m3']) if g['m3'] else None,d3=int(g['d3']) if g['d3'] else None,
                y3=int(g['y3']) if g['y3'] else None,wd=WDN.get(g['wd'][:3].lower()) if g['wd'] else None,label=g['label'].strip()))
    return out
def blocks(its):
    bl=[[]]; prev=None
    for it in its:
        if prev in (5,6,7) and it['m1'] in (8,9) and len(bl[-1])>5: bl.append([])
        bl[-1].append(it); prev=it['m1']
    return [b for b in bl if b]
def deduce_sy(b,default):
    for it in b:
        y=it['y1'] or it['y3']
        if y: return y if it['m1']>=7 else y-1
    best=None
    for sy in range(2000,2027):
        sc=sum(1 for it in b if it['wd'] is not None and build.ydate(sy,it['m1'],it['days'][0]) and build.ydate(sy,it['m1'],it['days'][0]).weekday()==it['wd'])
        if sc and (best is None or sc>=best[0]): best=(sc,sy)
    return best[1] if best and best[0]>=3 else default
def dates(sy,it):
    yd=lambda m,d,y=None:(dt.date(y,m,d) if y else build.ydate(sy,m,d))
    try:
        a=yd(it['m1'],it['days'][0],it['y1'] if it['y1'] and not it['m3'] else None)
        if it['m3']:
            b=yd(it['m3'],it['d3'],it['y3']); return [a+dt.timedelta(i) for i in range((b-a).days+1)] if 0<=(b-a).days<40 else [a]
        if it['d2']:
            b=yd(it['m2'] or it['m1'],it['d2'],it['y1'])
            if b and b<a and not it['m2']: b=yd(it['m1']%12+1,it['d2'])
            if b and 0<=(b-a).days<40: return [a+dt.timedelta(i) for i in range((b-a).days+1)]
        return [yd(it['m1'],d,it['y1']) for d in it['days']]
    except (ValueError,TypeError): return []
def summarize(sy,b):
    first=last=None; nos=set();part=set();early=set();conf=set();ev=[]
    for it in b:
        k=build.kinds(it['label']); ds=[d for d in dates(sy,it) if d]
        if not ds or ('makeup' in k and 'last' not in k): continue
        ev.append((ds,it['label'],k))
        if 'first' in k: first=min(first or ds[0],ds[0])
        if 'last' in k: last=max(last or ds[0],ds[0])
        for d in ds:
            if d.weekday()>=5: continue
            if 'noschool' in k: nos.add(d)
            if 'noschool_partial' in k: part.add(d)
            if 'early' in k: early.add(d)
            if 'conf' in k: conf.add(d)
    return dict(first=first,last=last,nos=nos,part=part,early=early,conf=conf,ev=ev)
def parse(f,default_sy=None):
    its=raw_items(build.doctext(f)); res={}
    for b in blocks(its):
        sy=deduce_sy(b,default_sy)
        if sy is None: continue
        if sy not in res or len(b)>len(res[sy]): res[sy]=b
    return {sy:summarize(sy,b) for sy,b in res.items()}
if __name__=='__main__':
    for f in sys.argv[1:]:
        for sy,s in sorted(parse(f,build.school_year(f,build.doctext(f))).items()):
            print(f,sy,'first',s['first'],'last',s['last'],'n',build.session_days(s),'nos',len(s['nos']),'part',len(s['part']),'er',len(s['early']),build.check(sy,s) or 'OK')
