#!/usr/bin/env python3
"""Small email-friendly earthquake map for the Eugene daily report (+ markdown -> HTML email helper).

  python eq_map.py map  OUT.png             # render today's map (USGS feeds, offline Natural Earth basemap)
  python eq_map.py html reports/email_X.md  # write reports/email_X.html with <img src="cid:eq_map_X.png"> under Earthquakes

Panel A: Pacific Northwest, USGS M2.5+ within 500 km of Eugene, past 24 h (falls back to 7 days if none).
Panel B: Pacific-centred world with the Ring of Fire (PB2002 convergent/transform boundaries), USGS M5+ past 24 h, M6+ flagged.
Dots: size = magnitude, colour = depth. The biggest quakes get numbers on the map and a plain-English key. Times in PT.
Basemap is bundled (zip_src/data/eqmap_base.json, Natural Earth public domain) so no tile server is needed."""
import os, re, sys, json, math, html, shutil, datetime as dt, urllib.request
from zoneinfo import ZoneInfo
PT = ZoneInfo('America/Los_Angeles')
HERE = os.path.dirname(os.path.abspath(__file__))
EUG = (44.05, -123.09)
USGS = 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{}.geojson'
ATTACH_DIR = os.environ.get('EQMAP_ATTACH_DIR', '/home/box/agent-data/agents/15f61d5b-1432-45e0-800f-fc00e7b4ab04/attachments')
PNW_KM = 500

def _data(name):
    for p in (os.path.join(HERE, '..', 'zip_src', 'data', name), os.path.join(HERE, name), '/workspace/eugene-sky/zip_src/data/' + name):
        if os.path.exists(p): return json.load(open(p))
    raise FileNotFoundError(name)

def _get(feed):
    req = urllib.request.Request(USGS.format(feed), headers={'User-Agent': 'eugene-sky eq_map (personal research)'})
    with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read())['features']

def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

def _q(f):
    p = f['properties']; lon, lat, z = f['geometry']['coordinates'][:3]
    t = dt.datetime.fromtimestamp(p['time'] / 1000, dt.timezone.utc).astimezone(PT)
    return dict(mag=round(p.get('mag') or 0, 1), place=p.get('place') or '', lat=lat, lon=lon, depth=z or 0, t=t, url=p.get('url'))

def short_place(s):
    s = re.sub(r'^\d+\s*km\s+[NSEW]{1,3}\s+of\s+', 'near ', s or '')
    return s.replace(' region', '')

def ptime(t): return f"{t:%a %b} {t.day} {t:%-I:%M %p} PT"

def fetch():
    """-> dict(pnw=[...], pnw_window='24 hours'|'7 days', world=[...]). Raises if USGS is down."""
    def near(fs): return sorted([q for q in map(_q, fs) if q['mag'] >= 2.5 and km(EUG, (q['lat'], q['lon'])) <= PNW_KM], key=lambda q: -q['mag'])
    pnw, win = near(_get('2.5_day')), '24 hours'
    if not pnw: pnw, win = near(_get('2.5_week')), '7 days'
    world = sorted([q for q in map(_q, _get('4.5_day')) if q['mag'] >= 5.0], key=lambda q: -q['mag'])
    return dict(pnw=pnw, pnw_window=win, world=world)

# ---------- drawing ----------
DEPTH = [(70, '#d7301f', 'Shallow (under 70 km deep)'), (300, '#fdae38', 'Medium (70-300 km deep)'), (1e9, '#3a6fb0', 'Deep (over 300 km)')]
def dcol(z): return next(c for lim, c, _ in DEPTH if z < lim)
def dsize(m, base): return base * (1.9 ** (m - 2.5))

def render(path, d=None, day=None):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    d = d or fetch(); B = _data('eqmap_base.json'); P = _data('plates_rof.json')
    day = day or dt.datetime.now(PT)
    land, sea, edge = '#ece6d6', '#dbe9f4', '#9a9282'
    fig = plt.figure(figsize=(7.0, 9.6), dpi=100)
    fig.patch.set_facecolor('white')
    fig.text(0.5, 0.985, f"Earthquakes — {day:%A %b} {day.day}, {day.year}", ha='center', va='top', fontsize=14, weight='bold')

    def key_text(ax, items, x0, y0, title, empty, dy=0.075, fs=8.6):
        ax.axis('off'); ax.text(x0, y0, title, fontsize=9.5, weight='bold', va='top', transform=ax.transAxes)
        if not items: ax.text(x0, y0 - dy, empty, fontsize=fs, va='top', transform=ax.transAxes, color='#555'); return
        for i, q in enumerate(items, 1):
            flag = '  (M6+ strong)' if q['mag'] >= 6 else ''
            ax.text(x0, y0 - 0.1 - dy * (i - 1), f"{i}. M{q['mag']:.1f}{flag}\n    {short_place(q['place'])[:44]}\n    {ptime(q['t'])}, {q['depth']:.0f} km deep",
                    fontsize=fs, va='top', transform=ax.transAxes, linespacing=1.15)
        return

    def dots(ax, qs, base, xf=lambda x: x, top=5, merge_km=60):
        for q in sorted(qs, key=lambda q: q['mag']):
            ax.scatter(xf(q['lon']), q['lat'], s=dsize(q['mag'], base), c=dcol(q['depth']), edgecolors='black' if q['mag'] >= 6 else '#333',
                       linewidths=1.8 if q['mag'] >= 6 else 0.5, alpha=0.85, zorder=5)
        groups = []  # merge numbers for quakes close together so labels don't sit on top of each other
        for i, q in enumerate(qs[:top], 1):
            g = next((g for g in groups if km((g[0]['lat'], g[0]['lon']), (q['lat'], q['lon'])) < merge_km), None)
            if g: g[1].append(i)
            else: groups.append((q, [i]))
        for q, nums in groups:
            ax.annotate(','.join(map(str, nums)), (xf(q['lon']), q['lat']), xytext=(6, 5), textcoords='offset points', fontsize=9, weight='bold', zorder=7,
                        annotation_clip=True, bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='#333', lw=0.6))

    # ---- panel A: Pacific Northwest ----
    axA = fig.add_axes([0.02, 0.585, 0.56, 0.355])
    axA.set_facecolor(sea)
    for r in B['pnw_land']: axA.fill(*zip(*r), color=land, ec=edge, lw=0.5, zorder=1)
    for r in B['pnw_states']: axA.plot(*zip(*r), color='#b5ab98', lw=0.6, zorder=2)
    # 500 km circle
    cir = [(EUG[1] + (PNW_KM / 111.2) * math.sin(a) / math.cos(math.radians(EUG[0])), EUG[0] + (PNW_KM / 111.2) * math.cos(a)) for a in [i * math.pi / 90 for i in range(181)]]
    axA.plot(*zip(*cir), color='#777', lw=0.8, ls='--', zorder=3)
    dots(axA, d['pnw'], 9, top=4, merge_km=25)
    axA.plot(EUG[1], EUG[0], marker='*', ms=15, color='#1b7837', mec='white', mew=1, zorder=8)
    axA.annotate('Eugene', (EUG[1], EUG[0]), xytext=(7, -11), textcoords='offset points', fontsize=9.5, weight='bold', color='#1b7837', zorder=8)
    for nm, la, lo in [('Portland', 45.52, -122.68), ('Seattle', 47.61, -122.33), ('Sacramento', 38.58, -121.49), ('Boise', 43.62, -116.2), ('Medford', 42.33, -122.87)]:
        axA.plot(lo, la, 'o', ms=2.5, color='#444', zorder=4); axA.text(lo + 0.15, la + 0.1, nm, fontsize=7, color='#444', zorder=4, clip_on=True)
    axA.text(-131.2, 41.2, 'Pacific\nOcean', fontsize=8, color='#6a8caf', style='italic')
    axA.set_xlim(-131.8, -114.6); axA.set_ylim(39.2, 49.0); axA.set_aspect(1 / math.cos(math.radians(44)))
    axA.set_xticks([]); axA.set_yticks([])
    n = len(d['pnw'])
    fig.text(0.02, 0.938, (f"Near Eugene: {n} quake{'s' if n != 1 else ''} M2.5+ in the last {d['pnw_window']}" + (' (none in the last 24 hours)' if d['pnw_window'] != '24 hours' else ''))
             if n else 'Near Eugene: no M2.5+ quakes in the last 7 days', fontsize=10, weight='bold', va='bottom')
    if not n: axA.text(0.5, 0.06, 'No quakes in the last 7 days within 500 km', ha='center', transform=axA.transAxes, fontsize=9, bbox=dict(fc='white', ec='#999'))
    axA.text(0.99, 0.01, 'dashed ring = 500 km from Eugene', ha='right', va='bottom', transform=axA.transAxes, fontsize=6.5, color='#555')
    kA = fig.add_axes([0.60, 0.60, 0.39, 0.33])
    key_text(kA, d['pnw'][:4], 0.0, 1.0, 'Biggest near Eugene', 'Nothing M2.5+ within 500 km.', dy=0.22)

    # ---- panel B: Ring of Fire (Pacific-centred, lon 0..360) ----
    X0, X1 = 92, 298
    xf = lambda lo: lo + 360 if lo < 0 else lo
    axB = fig.add_axes([0.02, 0.185, 0.96, 0.36])
    axB.set_facecolor(sea)
    for r in B['world_land']:
        xs, ys = zip(*r)
        for off in (0, 360): axB.fill([x + off for x in xs], ys, color=land, ec=edge, lw=0.4, zorder=1)
    for seg in P['ring']:
        ys, xs = zip(*seg['p']); xs = [xf(x) for x in xs]
        # break the line where it wraps
        cur = [[], []]
        for x, y in zip(xs, ys):
            if cur[0] and abs(x - cur[0][-1]) > 180: axB.plot(*cur, color='#c0392b', lw=1.1, alpha=0.55, zorder=3); cur = [[], []]
            cur[0].append(x); cur[1].append(y)
        axB.plot(*cur, color='#c0392b', lw=1.1, alpha=0.55, zorder=3)
    dots(axB, d['world'], 6, xf, merge_km=400)
    axB.plot(xf(EUG[1]), EUG[0], marker='*', ms=11, color='#1b7837', mec='white', mew=0.8, zorder=8)
    axB.set_xlim(X0, X1); axB.set_ylim(-56, 64); axB.set_aspect(1.0); axB.set_xticks([]); axB.set_yticks([])
    m = len(d['world']); m6 = sum(q['mag'] >= 6 for q in d['world'])
    fig.text(0.02, 0.552, (f"Ring of Fire & world: {m} quake{'s' if m != 1 else ''} M5+ in the last 24 hours" + (f" ({m6} {'was' if m6 == 1 else 'were'} M6+)" if m6 else '')) if m
                  else 'Ring of Fire & world: no M5+ quakes in the last 24 hours', fontsize=10, weight='bold', va='bottom')
    if not m: axB.text(0.5, 0.5, 'No M5+ quakes in the last 24 hours', ha='center', transform=axB.transAxes, fontsize=10, bbox=dict(fc='white', ec='#999'))
    off_map = [q for q in d['world'][:5] if not (X0 <= xf(q['lon']) <= X1)]
    if off_map: axB.text(0.01, 0.02, f"{len(off_map)} of the numbered quakes are outside this Pacific view", transform=axB.transAxes, fontsize=6.5, color='#555')

    # ---- bottom: world key + legend + caption ----
    kB = fig.add_axes([0.03, 0.035, 0.56, 0.14]); kB.axis('off')
    kB.text(0, 1.0, 'Biggest worldwide', fontsize=9.5, weight='bold', va='top', transform=kB.transAxes)
    if not m: kB.text(0, 0.8, 'Nothing M5+ anywhere in the last 24 hours.', fontsize=8.6, va='top', transform=kB.transAxes, color='#555')
    for i, q in enumerate(d['world'][:5], 1):
        kB.text(0, 1.0 - 0.17 * i, f"{i}. M{q['mag']:.1f}{' (M6+)' if q['mag'] >= 6 else ''}  {short_place(q['place'])[:38]}  ·  {q['t']:%a} {q['t']:%-I:%M %p}",
                fontsize=8.2, va='top', transform=kB.transAxes)
    lg = fig.add_axes([0.60, 0.035, 0.39, 0.14]); lg.axis('off')
    h = [Line2D([], [], ls='', marker='o', ms=8, mfc=c, mec='#333', label=lab) for _, c, lab in DEPTH]
    h += [Line2D([], [], ls='', marker='o', ms=9, mfc='white', mec='black', mew=1.8, label='Thick black ring = M6+ (strong)'),
          Line2D([], [], color='#c0392b', lw=1.5, alpha=0.6, label='Ring of Fire plate boundaries'),
          Line2D([], [], ls='', marker='*', ms=11, color='#1b7837', label='Eugene')]
    lg.legend(handles=h, loc='upper left', fontsize=7.6, frameon=False, handletextpad=0.4, borderaxespad=0, labelspacing=0.45)
    fig.text(0.5, 0.012, 'Bigger dots = stronger quakes. Colour shows how deep the quake was. Numbers match the lists. Times are Pacific (PT). Source: USGS.',
             ha='center', fontsize=7.4, color='#333')
    fig.savefig(path, dpi=100, facecolor='white')
    plt.close(fig)
    try:  # shrink to an indexed-colour PNG for email
        from PIL import Image
        if os.path.getsize(path) > 250_000: Image.open(path).convert('RGB').quantize(colors=256).save(path, optimize=True)
    except Exception: pass
    return path

# ---------- report section ----------
def report_lines(day=None, reports_dir=None, attach_dir=ATTACH_DIR):
    """Lines for the '## Earthquakes' section; also renders reports/eq_map_DATE.png and copies it to attach_dir."""
    day = day or dt.datetime.now(PT).date()
    d = fetch(); L = []
    if d['pnw']:
        L.append(f"- Near Eugene (M2.5+ within 500 km, past {d['pnw_window']}, USGS): {len(d['pnw'])}" + (" — none in the past 24 hours" if d['pnw_window'] != '24 hours' else ''))
        L += [f"  - M{q['mag']:.1f} {short_place(q['place'])}, {ptime(q['t'])}" for q in d['pnw'][:4]]
    else: L.append('- Near Eugene (M2.5+ within 500 km, USGS): none in the past 7 days.')
    if d['world']:
        m6 = [q for q in d['world'] if q['mag'] >= 6]
        L.append(f"- Worldwide M5+ in the past 24 h: {len(d['world'])}" + (f", including {len(m6)} M6+" if m6 else ''))
        L += [f"  - M{q['mag']:.1f} {short_place(q['place'])}, {ptime(q['t'])}" for q in d['world'][:4]]
    else: L.append('- Worldwide M5+ in the past 24 h: none.')
    name = f'eq_map_{day}.png'
    if reports_dir:
        os.makedirs(reports_dir, exist_ok=True)
        p = render(os.path.join(reports_dir, name), d, dt.datetime.combine(day, dt.time(), PT))
        try: os.makedirs(attach_dir, exist_ok=True); shutil.copy2(p, os.path.join(attach_dir, name))
        except Exception as e: L.append(f'- (map copy to email attachments failed: {e.__class__.__name__})')
        L.append(f'- Map attached: {name} (where today\'s quakes hit, near Eugene and around the Ring of Fire)')
    return L

# ---------- markdown -> simple HTML email ----------
def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<![\w*])_(.+?)_(?![\w*])', r'<i>\1</i>', s)
    s = re.sub(r'(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)', r'<i>\1</i>', s)
    return re.sub(r'(?<![">])(https?://[^\s<)]+)', r'<a href="\1">\1</a>', s)

def md_to_html(md, cid=None, title=None):
    """Tiny converter for our report markdown (#/## headings, '-' bullets with 2-space nesting, paragraphs).
    If cid is given, inserts <img src="cid:..."> right under the Earthquakes heading (or appends an Earthquakes heading)."""
    out, depth, in_eq, placed = [], 0, False, False
    img = (f'<p><img src="cid:{cid}" alt="Map of where today\'s earthquakes hit" width="700" '
           f'style="max-width:100%;height:auto;border:1px solid #ddd"></p>') if cid else ''
    def close(to=0):
        nonlocal depth
        while depth > to: out.append('</li></ul>'); depth -= 1
    for line in md.splitlines():
        m = re.match(r'^(\s*)[-*] (.*)$', line)
        if m:
            lvl = len(m.group(1)) // 2 + 1
            if lvl > depth:
                while depth < lvl: out.append('<ul>'); depth += 1; out.append('<li>')
                out[-1] = '<li>' + _inline(m.group(2))
            else:
                close(lvl); out.append('</li><li>' + _inline(m.group(2)))
            continue
        close()
        h = re.match(r'^(#{1,4})\s+(.*)$', line)
        if h:
            n = len(h.group(1)); out.append(f'<h{n}>{_inline(h.group(2))}</h{n}>')
            if img and not placed and re.search(r'earthquake', h.group(2), re.I): out.append(img); placed = True
        elif line.strip(): out.append(f'<p>{_inline(line)}</p>')
    close()
    body = '\n'.join(out).replace('<ul>\n<li>', '<ul><li>')
    if img and not placed: body += '\n<h2>Earthquakes</h2>\n' + img
    css = ('body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.45;color:#222;max-width:740px;margin:0 auto;padding:12px}'
           'h1{font-size:21px;margin:0 0 4px}h2{font-size:17px;margin:20px 0 6px;border-bottom:1px solid #e3e3e3;padding-bottom:3px}'
           'ul{margin:4px 0 4px 0;padding-left:22px}li{margin:2px 0}a{color:#1a5fb4}')
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title or "Eugene daily report")}</title>'
            f'<style>{css}</style></head><body>\n{body}\n</body></html>\n')

def write_html(md_path, cid=None, html_path=None):
    """email_2026-10-28.md -> email_2026-10-28.html. If line 1 isn't a heading it's treated as the subject (body from line 3)."""
    txt = open(md_path).read(); lines = txt.splitlines()
    subj = None
    if lines and not lines[0].startswith('#'): subj, txt = lines[0].strip(), '\n'.join(lines[2:] if len(lines) > 1 and not lines[1].strip() else lines[1:])
    dm = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(md_path))
    if cid is None and dm and os.path.exists(os.path.join(os.path.dirname(md_path), f'eq_map_{dm.group(1)}.png')): cid = f'eq_map_{dm.group(1)}.png'
    html_path = html_path or re.sub(r'\.md$', '', md_path) + '.html'
    open(html_path, 'w').write(md_to_html(txt, cid, subj)); return html_path

if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'map': print(render(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == 'html': print(write_html(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    else: print(__doc__)
