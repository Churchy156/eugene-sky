"""Cell-based parser for grid calendars (Springfield 2019+ community calendars): month titles in caps,
day number at the top-right... text for the day sits left of / around its number within the cell."""
import re,sys,os,datetime as dt
sys.path.insert(0,os.path.dirname(__file__)); import extract as X
MONS='JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER'.split()
def grid_days(pdf,sy):
    out={}
    for words in X.words_bbox(pdf):
        titles=[(w[0],w[1],w[2],MONS.index(w[4])+1) for w in words if w[4] in MONS]
        if len(titles)<6: continue
        nums=[w for w in words if re.fullmatch(r'\d{1,2}',w[4]) and 1<=int(w[4])<=31]
        def block(x,y):
            c=[t for t in titles if t[1]<y-3 and t[0]-90<x]
            if not c: return None
            ty=max(t[1] for t in c); row=[t for t in c if abs(t[1]-ty)<5]
            return max(row,key=lambda t:t[0])
        cells={}
        for w in nums:
            b=block(w[0],w[1])
            if not b: continue
            m=b[3]; y=sy if m>=7 else sy+1
            try: d=dt.date(y,m,int(w[4]))
            except ValueError: continue
            if d.weekday()>4: continue
            cells.setdefault(d,[]).append(w)
        # drop dates with more than one number word (legend collisions): keep the one nearest its block
        anchors={d:v[0] for d,v in cells.items()}
        texts={d:[] for d in anchors}
        numset=set(id(v) for v in anchors.values())
        for w in words:
            if re.fullmatch(r'\d{1,2}',w[4]) or w[4] in MONS: continue
            xc=(w[0]+w[2])/2; yc=(w[1]+w[3])/2
            best=None
            for d,a in anchors.items():
                dx=a[2]-xc; dy=yc-a[1]
                if -3<=dx<=40 and -18<=dy<=14:
                    sc=dx+abs(dy)*0.5
                    if best is None or sc<best[0]: best=(sc,d)
            if best: texts[best[1]].append(w[4])
        for d,t in texts.items(): out[d]=' '.join(t)
    return out
def grid_summary(pdf,sy):
    g=grid_days(pdf,sy); first=last=None; nos=set(); part=set(); early=set()
    for d,t in sorted(g.items()):
        T=t.upper().replace('NOSCHOOL','NO SCHOOL')
        toks=set(T.split())
        if 'NO SCHOOL' in T or 'X' in toks:
            (part if re.search(r'ELEMENTARY|SECONDARY|KINDER|MIDDLE|HIGH|ELEM ONLY|SEC ONLY',T) else nos).add(d)
        frag=len(re.findall(r'\b(Ea|rly|Re|le|as|ase|lease|Early|Release|ly|E|arl|a)\b',t))
        if frag>=3 or 'Early' in t: early.add(d)
        if d.month in(8,9) and re.search(r'FIRST|\bK,|\d-\d',T): first=min(first or d,d)
        if 'LAST' in T: last=max(last or d,d)
    for d,t in g.items():
        toks=set(t.upper().split())
        if 'NO SCHOOL' in t.upper().replace('NOSCHOOL','NO SCHOOL') or not (toks&{'NO','SCHOOL'}): continue
        nb=[d+dt.timedelta(k) for k in(-1,1,-3,3)]
        if any(n in nos for n in nb): nos.add(d)
        elif any(n in part for n in nb): part.add(d)
    return dict(first=first,last=last,nos=nos,part=part,early=early,conf=set()),g
if __name__=='__main__':
    s,g=grid_summary(sys.argv[1],int(sys.argv[2]))
    for d,t in sorted(g.items()):
        if t: print(d,d.strftime('%a'),t[:80])
    print({k:(sorted(v) if isinstance(v,set) else v) for k,v in s.items() if k in('first','last')},len(s['nos']),len(s['early']))
