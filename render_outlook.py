"""Run daily_report.py and render the newest outlook markdown as site/outlook.html (no extra deps)."""
import glob, html, os, re, subprocess, sys
subprocess.run([sys.executable,'daily_report.py'],check=True,stdout=subprocess.DEVNULL)
md=open(sorted(glob.glob('reports/outlook_*.md'))[-1]).read(); out=[]
for l in md.splitlines():
    e=html.escape(l); e=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',e); e=re.sub(r'(https?://\S+)',r'<a href="\1">\1</a>',e)
    if l.startswith('# '): out.append(f'<h1>{e[2:]}</h1>')
    elif l.startswith('## '): out.append(f'<h2>{e[3:]}</h2>')
    elif l.startswith('  - '): out.append(f'<li class="sub">{e[4:]}</li>')
    elif l.startswith('- '): out.append(f'<li>{e[2:]}</li>')
    elif l.startswith('_'): out.append(f'<p class="ts">{e.strip("_")}</p>')
    elif l.strip(): out.append(f'<p>{e}</p>')
log=open('site_update_log.txt').read() if os.path.exists('site_update_log.txt') else ''
page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Eugene daily outlook</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:auto;padding:14px;font-size:18px;line-height:1.45;color:#222}}h1{{font-size:26px;color:#1f3b57}}h2{{font-size:21px;border-bottom:2px solid #dde;margin-top:26px}}li{{margin:5px 0}}li.sub{{margin-left:26px;list-style:circle}}.ts{{color:#666}}pre{{font-size:13px;background:#f4f4f6;padding:8px;white-space:pre-wrap}}</style></head><body>
<p><a href="index.html">← Dashboard</a></p>{"".join(out)}<h2>Data update log</h2><pre>{html.escape(log)}</pre></body></html>'''
os.makedirs('site',exist_ok=True); open('site/outlook.html','w').write(page); print('wrote site/outlook.html')
