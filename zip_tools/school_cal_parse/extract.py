"""Extract (month, day-range, label) items from district calendar PDFs/HTML text.
Strategy 1: inline 'Month DD[-DD|-Month DD][:] label' anywhere in a line segment.
Strategy 2 (pdf bbox): month header segments define columns; 'DD[-DD] label' segments below inherit month."""
import re,subprocess,sys,html,json
MON={m:i+1 for i,m in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split())}
MONRE=r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
def mnum(s): return MON[s[:3].lower()]
DAYSPEC=r'(\d{1,2})(?:\s*(?:,|&|and)\s*(\d{1,2}))?(?:\s*[-–—]\s*(?:'+MONRE+r'\s*)?(\d{1,2}))?\*{0,2}'
INLINE=re.compile(r'\b'+MONRE+r'\s+'+DAYSPEC+r'(?:\s*\([A-Za-z–\-, ]{1,9}\))?\s*[:\-–—|]?\s*([A-Za-z][^|]{2,90})',re.I)
def words_bbox(pdf):
    out=subprocess.run(['pdftotext','-bbox',pdf,'-'],capture_output=True,text=True).stdout
    pages=[];cur=None
    for m in re.finditer(r'<page |<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>',out):
        if m.group(0).startswith('<page'): cur=[];pages.append(cur);continue
        cur.append((float(m[1]),float(m[2]),float(m[3]),float(m[4]),html.unescape(m[5])))
    return pages
def segments(words,gap=9):
    lines={}
    for w in sorted(words,key=lambda w:(round(w[1]),w[0])):
        k=None
        for y in lines:
            if abs(y-w[1])<2.5: k=y;break
        lines.setdefault(k if k is not None else w[1],[]).append(w)
    segs=[]
    for y,ws in sorted(lines.items()):
        ws.sort(key=lambda w:w[0]); cur=[ws[0]]
        for w in ws[1:]:
            h=max(4,cur[-1][3]-cur[-1][1])
            if w[0]-cur[-1][2]>gap*h/8: segs.append(cur);cur=[w]
            else: cur.append(w)
        segs.append(cur)
    # merge 'DD' / 'DD-DD' segment with following text segment on same line
    out=[]
    for sg in segs:
        if out and abs(out[-1][-1][1]-sg[0][1])<3 and re.match(r'^\d{1,2}(\s*[-–]\s*\d{1,2})?\*{0,2}$',' '.join(w[4] for w in out[-1])) and re.match(LABSTART,' '.join(w[4] for w in sg),re.I) and sg[0][0]-out[-1][-1][2]<70:
            out[-1]=out[-1]+sg
        else: out.append(sg)
    segs=out
    return [(s[0][0],s[0][1],' '.join(w[4] for w in s)) for s in segs]
GRIDTOK=re.compile(r'^(\d{1,2}|S|M|T|W|Th|F|Sa|Su|Tu|Mo|We|Fr|TH|SU|SA|TU)$')
HDR=re.compile(r'^'+MONRE+r'(\s+\d{4})?\s*$',re.I)
LABSTART=r'^([A-Za-z(“"\'*]|\d[\d /:.]*\s*(?:hour|hr|min|p\.?m|a\.?m|o.clock)\b)'
ITEM=re.compile(r'^'+DAYSPEC+r'\s*[:\-–—]?\s*((?:[A-Za-z(“"\'*]|\d[\d /:.]*\s*(?:hour|hr|min|p\.?m|a\.?m)\b).*)$',re.I)
def bbox_items(pdf,mode='col'):
    items=[]
    for words in words_bbox(pdf):
        segs=segments(words)
        hdrs=[];its=[];hw={}
        for x,y,t in segs:
            toks=t.split()
            if all(GRIDTOK.match(k) for k in toks): continue
            if HDR.match(t): hw[(x,y)]=len(t)*7; hdrs.append((x,y,mnum(HDR.match(t).group(1)),bool(HDR.match(t).group(2)))); continue
            m=ITEM.match(t)
            if m: its.append([x,y,m,t])
            elif its and re.match(r'^[A-Za-z(]',t):
                # continuation: closest item above in same column
                c=[i for i in its if abs(i[0]-x)<60 and 0<y-i[1]<14]
                if c: c[-1][3]+=' '+t
        for x,y,m,t in its:
            if mode=='band':
                above=[h for h in hdrs if h[1]<=y+3]
                if not above: continue
                hy=max(h[1] for h in above); row=sorted([h for h in above if abs(h[1]-hy)<6])
                ws={(h[0],h[1]):h for h in row}
                cen=[h[0]+hw.get((h[0],h[1]),40)/2 for h in row]
                h=row[0]
                for i in range(1,len(row)):
                    if x>=(cen[i-1]+cen[i])/2-30: h=row[i]
                d1,d2,mon2,d3,lab=m.groups(); lab=ITEM.match(t).group(5)
                items.append(dict(m1=h[2],d1=int(d1),d_and=int(d2) if d2 else None,m2=mnum(mon2) if mon2 else None,d2=int(d3) if d3 else None,label=lab.strip(),how='band'))
                continue
            # header in same column above (prefer headers without year = sidebar), else nearest header above anywhere to left
            cand=[h for h in hdrs if h[1]<=y+3 and abs(h[0]-x)<45]
            if not cand: cand=[h for h in hdrs if h[1]<=y+3 and h[0]<x and x-h[0]<260]
            if not cand: continue
            h=max(cand,key=lambda h:(h[1],-abs(h[0]-x)))
            d1,d2,mon2,d3,lab=m.groups()
            lab=ITEM.match(t).group(5)
            items.append(dict(m1=h[2],d1=int(d1),d_and=int(d2) if d2 else None,m2=mnum(mon2) if mon2 else None,d2=int(d3) if d3 else None,label=lab.strip(),how='bbox'))
    return items
def inline_items(text):
    items=[]
    segs=[]
    for ln in text.split('\n'):
        if re.match(r'^\s*'+MONRE+r'\s+\d',ln,re.I) and len(re.findall(MONRE+r'\s+\d',ln,re.I))<=2: segs.append(re.sub(r'\s{2,}',' ',ln))
        else: segs+=re.split(r'\s{4,}',ln)
    for line in segs:
        for m in INLINE.finditer(line):
            mo,d1,dand,mon2,d2,lab=m.groups()
            items.append(dict(m1=mnum(mo),d1=int(d1),d_and=int(dand) if dand else None,m2=mnum(mon2) if mon2 else None,d2=int(d2) if d2 else None,label=lab.strip(),how='inline'))
    return items
if __name__=='__main__':
    f=sys.argv[1]
    for i in (bbox_items(f) if f.endswith('.pdf') else []): print('B',i)
    t=subprocess.run(['pdftotext','-layout',f,'-'],capture_output=True,text=True).stdout if f.endswith('.pdf') else open(f).read()
    for i in inline_items(t): print('I',i)
