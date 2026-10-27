#!/usr/bin/env python3
"""Digitize Tomsk (SOSRFF / sos70.ru) 3-day Schumann resonance charts.

Charts: srf.jpg (F1..F4 frequency, Hz), sra.jpg (A1..A4 amplitude, station units),
srq.jpg (Q1..Q4 quality factor).  1006x340 px, black background, 3 days x 24 h,
local Tomsk time (Asia/Tomsk; verified 2026-10-27: chart ends at UTC+7 'now').

Per image: OCR (tesseract) the axis labels -> per-trace linear calibration
(robust arithmetic fit), OCR the 3 dates, extract each coloured trace
column-by-column, median per local hour, convert to UTC.

VALUES ARE ESTIMATES digitized from published images.
Usage: digitize_tomsk.py OUT.csv IMG [IMG ...]   (kind inferred from file/dir name)
"""
import sys, os, re, subprocess, tempfile, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
from PIL import Image

X0, PXH = 71, 12            # day-1 0h column, px per hour (288 px/day)
Y0, Y1 = 30, 310            # plot top/bottom gridlines
GRID_ROWS = list(range(30, 311, 20))
TZ = ZoneInfo('Asia/Tomsk')
# label groups: (side, rows) -> trace index
GROUPS = {1: ('L', range(30, 131, 20)), 3: ('L', range(150, 251, 20)),
          2: ('R', range(90, 191, 20)), 4: ('R', range(210, 311, 20))}

def kind_of(path):
    s = path.lower()
    for k in ('srf', 'sra', 'srq'):
        if k in s: return k[2]
    return None

def ocr_words(img_bool, scale=4, psm='6', wl='0123456789.'):
    im = Image.fromarray(np.where(img_bool, 0, 255).astype(np.uint8))
    im = im.resize((im.width*scale, im.height*scale), Image.LANCZOS)
    with tempfile.NamedTemporaryFile(suffix='.png') as t:
        im.save(t.name)
        out = subprocess.run(['tesseract', t.name, '-', '--psm', psm, '-c',
                              f'tessedit_char_whitelist={wl}', 'tsv'],
                             capture_output=True, text=True).stdout
    words = []
    for ln in out.splitlines()[1:]:
        p = ln.split('\t')
        if len(p) < 12 or not p[11].strip(): continue
        l, t, w, h = map(int, p[6:10])
        words.append((p[11].strip(), (l + w/2)/scale, (t + h/2)/scale))
    return words

def num(tok):
    d = re.sub(r'\D', '', tok)
    if not (2 <= len(d) <= 5): return None
    return int(d) / 100.0

def fit_labels(pts):
    """pts: [(row, value)]; robust fit value = a + b*row on arithmetic labels."""
    best = None
    for i in range(len(pts)):
        for j in range(i+1, len(pts)):
            (r1, v1), (r2, v2) = pts[i], pts[j]
            if r1 == r2: continue
            b = (v2 - v1)/(r2 - r1)
            if b >= 0: continue
            a = v1 - b*r1
            inl = [(r, v) for r, v in pts if abs(a + b*r - v) <= max(0.011, 0.01*abs(v)*0.05)]
            if best is None or len(inl) > len(best):
                best = inl
    if not best or len(best) < 3: return None
    r = np.array([p[0] for p in best], float); v = np.array([p[1] for p in best])
    b, a = np.polyfit(r, v, 1)
    return a, b, len(best)

def calibrate(a):
    cal = {}
    crops = {'L': (22, 18, 67, 322), 'R': (937, 18, 990, 322)}
    words = {}
    for side, (x0, y0, x1, y1) in crops.items():
        c = a[y0:y1, x0:x1]
        m = c.max(2) > 100
        if side == 'R':   # mask sos70 logo (blue/white) area
            m[:max(0, 100 - y0), :] &= ~logo_mask(a)[y0:100, x0:x1]
        words[side] = [(w, y + y0) for w, x, y in ocr_words(m)]
    for tr, (side, rows) in GROUPS.items():
        pts = []
        for w, y in words[side]:
            v = num(w)
            if v is None: continue
            rr = min(rows, key=lambda r: abs(r - y))
            if abs(rr - y) <= 6: pts.append((rr, v))
        cal[tr] = fit_labels(pts)
    return cal

def logo_mask(a):
    m = np.zeros(a.shape[:2], bool)
    reg = a[:110, 880:]
    blue = (reg[..., 2] > 170) & (reg[..., 0] < 90)
    if blue.sum() > 200:
        m[:100, 895:] = True
    return m

def read_dates(a):
    c = a[0:22, 60:940]
    ws = ocr_words(c.max(2) > 100, psm='6')
    ds = []
    for w, x, y in ws:
        mm = re.fullmatch(r'(\d{1,2})\.?(\d{2})\.?(\d{4})', w)
        if not mm: continue
        try: d = dt.date(int(mm[3]), int(mm[2]), int(mm[1]))
        except ValueError: continue
        k = int((x + 60 - X0)//288)
        if 0 <= k <= 2: ds.append(d - dt.timedelta(days=k))
    if not ds: return None
    vals, cnt = np.unique(ds, return_counts=True)
    return vals[np.argmax(cnt)], int(cnt.max())

def masks(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    white = (np.minimum(np.minimum(r, g), b) > 165)
    yellow = (r > 150) & (g > 150) & (b < 150) & (np.abs(r - g) < 70)
    red = (r > 100) & (r - g > 60) & (r - b > 50)
    green = (g > 120) & (g - r > 75) & (g - b > 75)
    grid = np.zeros(a.shape[:2], bool)
    for y in GRID_ROWS: grid[max(0, y-1):y+2, :] = True
    for x in range(X0, 940, 24): grid[:, max(0, x-1):x+2] = True
    green &= ~grid
    lm = logo_mask(a)
    out = {1: white, 2: yellow, 3: red, 4: green}
    for k in out:
        out[k] = out[k] & ~lm
        out[k][:Y0+1, :] = False; out[k][Y1:, :] = False
        out[k][:, :X0+1] = False; out[k][:, X0+3*288:] = False
    return out

def digitize(path):
    try:
        return _digitize(path)
    except Exception as e:
        return [], f'error {type(e).__name__}: {str(e)[:80]}'

def _digitize(path):
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    if a.shape[:2] != (340, 1006): return [], f'size {a.shape}'
    kd = kind_of(path)
    dd = read_dates(a)
    if dd is None: return [], 'no date'
    day0, ndate = dd
    cal = calibrate(a)
    ms = masks(a)
    rows = []
    for tr, m in ms.items():
        if cal.get(tr) is None: continue
        ca, cb, ninl = cal[tr]
        colrow = np.full(a.shape[1], np.nan)
        for x in range(X0+1, X0+3*288):
            ys = np.nonzero(m[:, x])[0]
            if len(ys): colrow[x] = np.median(ys)
        for d in range(3):
            for h in range(24):
                x0 = X0 + d*288 + h*PXH
                seg = colrow[x0:x0+PXH]
                ok = np.isfinite(seg)
                if ok.sum() < 4: continue
                yr = np.median(seg[ok])
                clip = (yr <= Y0 + 2) or (yr >= Y1 - 2)
                loc = dt.datetime.combine(day0 + dt.timedelta(days=d), dt.time(h), TZ)
                utc = loc.astimezone(dt.timezone.utc).replace(tzinfo=None)
                rows.append(dict(time_utc=utc.isoformat(), local_date=str(loc.date()), local_hour=h,
                                 var=f'{kd.upper()}{tr}', value=round(ca + cb*yr, 4),
                                 cov=round(ok.mean(), 2), clip=int(clip), ncal=ninl,
                                 ndate=ndate, src=os.path.basename(os.path.dirname(path)) + '/' + os.path.basename(path)))
    return rows, 'ok'

if __name__ == '__main__':
    import csv
    from multiprocessing import Pool
    out, imgs = sys.argv[1], sys.argv[2:]
    with Pool(max(1, os.cpu_count() - 1)) as p:
        res = p.map(digitize, imgs, chunksize=4)
    fields = ['time_utc', 'local_date', 'local_hour', 'var', 'value', 'cov', 'clip', 'ncal', 'ndate', 'src']
    n = 0
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fields); w.writeheader()
        for (rs, st), im in zip(res, imgs):
            if st != 'ok': print('skip', im, st, file=sys.stderr)
            for r in rs: w.writerow(r); n += 1
    print('rows', n)
