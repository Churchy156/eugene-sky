#!/usr/bin/env python3
"""Email one alert (plain + HTML, quake map inline via cid: and attached) straight over SMTP.
Usage: send_alert.py <alert.md> <alert.html> <map.png or -> [--test] [--check]
Settings come from /etc/eugene-alerts/alerts.env (root-only), loaded by run_alerts.sh:
  SMTP_HOST, SMTP_PORT (587 STARTTLS / 465 SSL), SMTP_USER, SMTP_FROM, ALERT_TO
  SMTP_PASSWORD_REF  = op://vault/item/field  (read at run time with the 1Password CLI; needs OP_SERVICE_ACCOUNT_TOKEN)
  or SMTP_PASSWORD   = the app password itself (only inside the root-only env file)
The password is never printed or logged."""
import os, sys, ssl, smtplib, subprocess, mimetypes
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

def secret(name):
    ref = os.environ.get(name + '_REF')
    if ref:
        r = subprocess.run(['op', 'read', '--no-newline', ref], capture_output=True, text=True, timeout=60)
        if r.returncode != 0: raise RuntimeError(f'1Password read failed for {name} (exit {r.returncode})')
        return r.stdout
    v = os.environ.get(name)
    if not v: raise RuntimeError(f'{name} not configured')
    return v

def configured():
    need = ['SMTP_HOST', 'SMTP_USER', 'ALERT_TO']
    miss = [k for k in need if not os.environ.get(k)]
    if not (os.environ.get('SMTP_PASSWORD_REF') or os.environ.get('SMTP_PASSWORD')): miss.append('SMTP_PASSWORD(_REF)')
    return miss

def main():
    a = [x for x in sys.argv[1:] if not x.startswith('--')]; test = '--test' in sys.argv
    miss = configured()
    if '--check' in sys.argv:
        print('ok' if not miss else 'missing: ' + ','.join(miss)); return 0 if not miss else 3
    if miss: print('send skipped, missing: ' + ','.join(miss), file=sys.stderr); return 3
    md, html, att = a[0], a[1], a[2]
    text = open(md, encoding='utf-8').read(); body_html = open(html, encoding='utf-8').read()
    subject = text.splitlines()[0].lstrip('# ').strip()
    if test:
        note = 'This is a TEST email from the GROKBOTS alert computer (eugene-alerts VM). Nothing in it is real.'
        subject = '[TEST] ' + subject; text = note + '\n\n' + text
        body_html = (f'<p style="background:#fff3cd;padding:8px;border:1px solid #e0c36a"><b>{note}</b></p>' + body_html)
    m = EmailMessage()
    m['Subject'] = subject; m['From'] = os.environ.get('SMTP_FROM') or os.environ['SMTP_USER']
    m['To'] = os.environ['ALERT_TO']; m['Date'] = formatdate(localtime=True); m['Message-ID'] = make_msgid('eugene-alerts')
    m.set_content(text)
    adir = os.environ.get('ALERT_ATTACH', '.')
    png = None if att in ('-', '') else (att if os.path.isabs(att) else os.path.join(adir, att))
    if png and os.path.exists(png):
        name = os.path.basename(png)
        m.add_alternative(body_html, subtype='html')
        data = open(png, 'rb').read()
        # inline copy for <img src="cid:NAME">
        m.get_payload()[1].add_related(data, 'image', 'png', cid=f'<{name}>', filename=name, disposition='inline')
        m.add_attachment(data, maintype='image', subtype='png', filename=name)
    else:
        m.add_alternative(body_html, subtype='html')
    host = os.environ['SMTP_HOST']; port = int(os.environ.get('SMTP_PORT', '587')); pw = secret('SMTP_PASSWORD')
    ctx = ssl.create_default_context()
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, context=ctx, timeout=60)
    else:
        s = smtplib.SMTP(host, port, timeout=60); s.starttls(context=ctx)
    with s:
        s.login(os.environ['SMTP_USER'], pw); s.send_message(m)
    print(f'sent: {subject}'); return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as e:
        print(f'send failed: {type(e).__name__}: {str(e)[:200]}', file=sys.stderr); sys.exit(1)
