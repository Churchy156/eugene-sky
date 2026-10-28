import re,os,sys,glob,subprocess,json,datetime as dt,collections
sys.path.insert(0,os.path.dirname(__file__)); import extract as X
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def doctext(f):
    if f.endswith('.pdf'): return subprocess.run(['pdftotext','-layout',f,'-'],capture_output=True,text=True).stdout
    sys.path.insert(0,ROOT); import totext; return totext.text(f)
def school_year(f,text):
    b=os.path.basename(f)
    m=re.search(r'SY(\d\d)',b)
    if m: return 2000+int(m[1])-1
    m=re.search(r'(20\d\d)\s*[-–_]\s*(20)?(\d\d)(?!\d)',b) or re.search(r'(?<!\d)(\d\d)-(\d\d)-CALENDAR',b)
    if m and len(m[1])==2: return 2000+int(m[1])
    if m and (int(m[3])-int(m[1][2:]))%100==1: return int(m[1])
    m=re.search(r'(20\d\d)\s*[-–]\s*(20)?(\d\d)(?!\d)',text[:3000])
    if m and (int(m[3])-int(m[1][2:]))%100==1: return int(m[1])
    m=re.search(r'4j/e(20\d\d)',f)
    if m: return int(m[1])
    return None
def kinds(lab):
    l=lab.lower(); k=set()
    partial=bool(re.search(r'elementary|middle|secondary|high school|k-?8|k-?5|6-?12|9-?12|\bwhs\b|\bces\b|\bcms\b|\bchs\b|kinder|\bhs\b|\bms\b|grades? \d|9th|freshm|seniors?\b|trimester sch|\belem\b|ms/hs|\bsec only',l))
    if re.search(r'possible|tentative|make-?up|if needed|if no ',l) and not re.search(r'last day',l): k.add('makeup')
    if re.search(r'first day|classes begin|school begins|start of school|begin(s)? school|start of [1l]st quarter|school starts|students? start|first student day|classes start',l) and 'teacher' not in l: k.add('first')
    if re.search(r'last (student |class )?day|end of 4th quarter|end of (3rd|third) trimester|end of (2nd|second) semester|last day of school|end of school year|students? last day',l) and 'teacher' not in l and 'staff' not in l: k.add('last')
    if re.search(r'early (release|dismissal)|half[- ]day|1/2 day|½ day|late start',l): k.add('early')
    if 'conference' in l: k.add('conf')
    nos=re.search(r'no school|no classes|break|vacation|holiday|non[- ]?student|non[- ]?contract|in-?service|grading|record ?keeping|\brk\b|\bpa day|teacher work|staff work|work ?day|planning|professional|prof dev|collaboration|labor day|memorial day|veterans|president|martin luther|mlk|thanksgiving|new year|christmas|independence|juneteenth|staff development|curriculum development|furlough|closed',l)
    if nos and 'early' not in k and not re.search(r'student school day|classes resume|school resumes|return|report|1/2 day of school|staggered',l): k.add('noschool_partial' if partial else 'noschool')
    if 'conf' in k and 'early' not in k and 'noschool' not in k and 'noschool_partial' not in k and not re.search(r'evening|night|pm',l): k.add('noschool_partial' if partial else 'noschool')
    return k
def ydate(sy,m,d):
    y=sy if m>=7 else sy+1
    try: return dt.date(y,m,d)
    except ValueError: return None
def expand(sy,it):
    a=ydate(sy,it['m1'],it['d1'])
    if a is None: return []
    out=[a]
    if it.get('d_and'):
        b=ydate(sy,it['m1'],it['d_and']); out+= [b] if b else []
    if it.get('d2'):
        m2=it['m2'] or it['m1']; b=ydate(sy,m2,it['d2'])
        if b and b<a and not it['m2']: b=ydate(sy,(it['m1']%12)+1,it['d2'])
        if b and 0<(b-a).days<40: out=[a+dt.timedelta(i) for i in range((b-a).days+1)]
    return out
def fourj_items(text):
    toks=[t.strip() for t in re.split(r'\||\n',text)]
    toks=[t for t in toks if t]
    found=[]
    for i in range(len(toks)-2):
        m=re.match(r'^'+X.MONRE+r'$',toks[i],re.I)
        if not m: continue
        # day may be "21–" with next "1" on separate token in 2009 layout ("Dec.\nJan." / "21–\n1")
        j=i+1; mon2=None
        if re.match(r'^'+X.MONRE+r'$',toks[j],re.I): mon2=toks[j]; j+=1
        dm=re.match(r'^(\d{1,2})(?:\s*(?:,|&)\s*(\d{1,2}))?(?:\s*[–-]\s*(?:'+X.MONRE+r'\s*)?(\d{1,2})?)?(?:\s*&.*)?$',toks[j])
        if not dm: continue
        d1,dand,m2b,d2=dm.groups(); k=j+1
        if d2 is None and toks[j].rstrip().endswith(('–','-')) and re.match(r'^\d{1,2}$',toks[k]): d2=toks[k]; k+=1
        if k<len(toks) and re.match(r'^\(.{1,8}\)\*?$',toks[k]): k+=1
        mm=mon2 or m2b
        found.append(dict(m1=X.mnum(m[1]),d1=int(d1),d_and=int(dand) if dand else None,m2=X.mnum(mm) if mm else None,d2=int(d2) if d2 else None,after=toks[k] if k<len(toks) else '',before=toks[i-1]))
    def score(key):
        s=0
        for f in found:
            l=f[key].lower()
            if 'classes begin' in l and f['m1'] in (8,9): s+=3
            if 'memorial' in l and f['m1']==5: s+=2
            if 'thanksgiving' in l and f['m1']==11: s+=2
            if 'spring' in l and f['m1'] in (3,4): s+=2
            if 'labor day' in l and f['m1']==9: s+=2
        return s
    key='after' if score('after')>=score('before') else 'before'
    out=[]
    for f in found:
        f['label']=f.pop(key); f.pop('after' if key=='before' else 'before'); f['how']='4jhtml'; out.append(f)
    return out
def parse_doc(f):
    text=doctext(f); sy=school_year(f,text)
    if '/4j/' in os.path.abspath(f) and f.endswith('.html'): items=fourj_items(text)
    else:
        items=X.bbox_items(f,'band' if '/south_lane/' in os.path.abspath(f) else 'col') if f.endswith('.pdf') else []
        inl=X.inline_items(text)
        if len(inl)>=10 or not items: items=inl
    return sy,items,text
if __name__=='__main__':
    for f in sys.argv[1:]:
        sy,items,_=parse_doc(f); print('###',f,sy,len(items))
        for it in items: print('  ',it['m1'],it['d1'],it.get('d2'),'|',it['label'][:70],'|',sorted(kinds(it['label'])))

def summarize(sy,items):
    first=last=None; nos=set(); part=set(); early=set(); conf=set(); mk=set()
    for it in items:
        if re.match(r'^'+X.MONRE+r'$',it['label'],re.I): continue
        k=kinds(it['label']); ds=expand(sy,it)
        if not ds: continue
        if 'makeup' in k and 'last' not in k: mk.update(ds); continue
        if 'first' in k: first=min(first or ds[0],ds[0])
        if 'last' in k: last=max(last or ds[0],ds[0]) if 'makeup' not in k or not last else last
        if 'noschool' in k: nos.update(ds)
        if 'noschool_partial' in k: part.update(ds)
        if 'early' in k: early.update(ds)
        if 'conf' in k: conf.update(ds)
    return dict(first=first,last=last,nos=nos,part=part,early=early,conf=conf)
def session_days(s):
    if not s['first'] or not s['last']: return None
    d=s['first'];n=0
    while d<=s['last']:
        if d.weekday()<5 and d not in s['nos']: n+=1
        d+=dt.timedelta(1)
    return n
def check(sy,s):
    p=[]
    if not s['first'] or not (dt.date(sy,8,15)<=s['first']<=dt.date(sy,9,25)): p.append(f"first={s['first']}")
    if not s['last'] or not (dt.date(sy+1,5,25)<=s['last']<=dt.date(sy+1,6,25)): p.append(f"last={s['last']}")
    n=session_days(s)
    if n is None or not 150<=n<=185: p.append(f'ndays={n}')
    for nm,(m,lo,hi) in dict(thanks=(11,20,30),winter=(12,20,31),spring=(3,14,31)).items():
        y=sy if m>=7 else sy+1
        if not any(x.year==y and x.month==m and lo<=x.day<=hi for x in s['nos']): p.append('no_'+nm)
    return p
