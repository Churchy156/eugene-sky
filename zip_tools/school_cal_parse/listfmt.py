"""Springfield 2014-17 community calendars: a middle column of 'Month' headers followed by 'DD[ & DD][-DD]: label'."""
import re,sys,os,datetime as dt
sys.path.insert(0,os.path.dirname(__file__)); import build
M='January February March April May June July August September October November December'.split()
IT=re.compile(r'(?<![\w/])(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.? )?(\d{1,2}(?:\s*(?:&|,)\s*\d{1,2})*(?:\s*-\s*\d{1,2})?)\s*:\s+(.+?)(?=\s{2,}\d|\s{3,}|$)')
def items(txt,sy):
    out=[];cur=None
    for line in txt.replace('\u2013','-').replace('\u2014','-').splitlines():
        for m in re.finditer(r'(?<![A-Za-z])('+'|'.join(M)+r')(?! ?\d{4})(?=\s{2,}|$)',line):
            cur=M.index(m.group(1))+1
        for m in IT.finditer(line):
            ds,lab=m.group(2),m.group(3).strip()
            if m.group(1): cur=[x[:3] for x in M].index(m.group(1))+1
            if not re.match(r'[A-Za-z½]',lab) or (cur is None and not m.group(1)): continue
            parts=re.split(r'\s*(?:&|,)\s*',ds); days=[]
            for p in parts:
                if '-' in p:
                    a,b=map(int,p.split('-'))
                    if b>=a: days+=list(range(a,b+1))
                    else: days+=list(range(a,32))+[('next',x) for x in range(1,b+1)]
                else: days.append(int(p))
            for d in days:
                mm=cur
                if isinstance(d,tuple): mm=cur%12+1; d=d[1]
                y=sy if mm>=7 else sy+1
                try: out.append((dt.date(y,mm,d),lab))
                except ValueError: pass
    return out
def summary(f,sy):
    its=items(build.doctext(f),sy); first=last=None; nos=set();part=set();early=set();conf=set()
    for d,lab in its:
        k=build.kinds(lab)
        if 'first' in k: first=min(first or d,d)
        if 'last' in k: last=max(last or d,d)
        if 'noschool' in k and d.weekday()<5: nos.add(d)
        if 'noschool_partial' in k and d.weekday()<5: part.add(d)
        if 'early' in k: early.add(d)
        if 'conf' in k: conf.add(d)
    return dict(first=first,last=last,nos=nos,part=part,early=early,conf=conf),its
if __name__=='__main__':
    s,its=summary(sys.argv[1],int(sys.argv[2]))
    for d,l in its: print(d,l, build.kinds(l))
    print(s['first'],s['last'],len(s['nos']),len(s['early']))
