import sys,os,glob;sys.path.insert(0,os.path.dirname(__file__));import build as B
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for f in sorted(glob.glob('*/*.pdf')+glob.glob('*/*.html')):
    if f.startswith('parse'): continue
    try: sy,items,_=B.parse_doc(f)
    except Exception as e: print('ERR',f,e); continue
    if not sy or not items: print(f'{f[:95]:95s} sy={sy} items={len(items)}'); continue
    s=B.summarize(sy,items); pr=B.check(sy,s)
    print(f"{f[:95]:95s} {sy} it={len(items):3d} first={s['first']} last={s['last']} n={B.session_days(s)} nos={len(s['nos'])} er={len(s['early'])} {'OK' if not pr else pr}")
