#!/usr/bin/env python3
"""Plain-language daily outlook for Eugene/Lane County. Usage: python daily_report.py [YYYY-MM-DD]
Writes reports/outlook_YYYY-MM-DD.md and prints it. Each source is fetched independently; failures are reported, not fatal.
Optional env: TRIPCHECK_KEY (ODOT TripCheck API subscription key, free registration at apiportal.odot.state.or.us)."""
import os, sys, json, math, pickle, datetime as dt
import requests, ephem, numpy as np, pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from zoneinfo import ZoneInfo
PT=ZoneInfo('America/Los_Angeles'); HERE=os.path.dirname(os.path.abspath(__file__))
LAT,LON=44.05,-123.09; UA={'User-Agent':'eugene-env daily_report (personal research)'}
day=pd.Timestamp(sys.argv[1]) if len(sys.argv)>1 else pd.Timestamp(dt.datetime.now(PT).date())
out=[f'# Eugene daily outlook — {day:%A %b %d, %Y}', f'_Generated {dt.datetime.now(PT):%Y-%m-%d %H:%M} PT_','']
def get(url,headers=None,**kw):
    r=requests.get(url,headers={**UA,**(headers or {})},timeout=25,**kw); r.raise_for_status(); return r
def section(title,fn):
    out.append(f'## {title}')
    try: out.extend(fn())
    except Exception as e: out.append(f'- (unavailable: {type(e).__name__}: {str(e)[:120]})')
    out.append('')
WX={}
def weather():
    p=get('https://api.weather.gov/gridpoints/PQR/85,39/forecast').json()['properties']['periods'][:4]
    L=[f"- **{x['name']}**: {x['detailedForecast']}" for x in p]
    om=get('https://api.open-meteo.com/v1/forecast',params=dict(latitude=LAT,longitude=LON,daily='temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,precipitation_probability_max',temperature_unit='fahrenheit',precipitation_unit='inch',timezone='America/Los_Angeles',forecast_days=7)).json()['daily']
    WX.update({k:v for k,v in om.items()})
    L.append('- 7-day (Open-Meteo): '+'; '.join(f"{pd.Timestamp(t):%a} {hi:.0f}/{lo:.0f}°F {pr:.2f}in" for t,hi,lo,pr in zip(om['time'],om['temperature_2m_max'],om['temperature_2m_min'],om['precipitation_sum'])))
    return L
def alerts():
    f=get('https://api.weather.gov/alerts/active',params={'zone':'ORZ118,ORC039'}).json()['features']
    if not f: return ['- No active NWS watches, warnings or advisories for Eugene / Lane County.']
    return [f"- **{a['properties']['event']}** until {a['properties'].get('ends') or a['properties'].get('expires')}: {a['properties']['headline']}" for a in f]
def roads():
    k=os.environ.get('TRIPCHECK_KEY')
    if not k: return ['- ODOT TripCheck API needs a free subscription key (set TRIPCHECK_KEY). Meanwhile see https://tripcheck.com/ (I-5, OR-126, OR-58 near Eugene).']
    r=get('https://api.odot.state.or.us/tripcheck/Incidents',headers={**UA,'Ocp-Apim-Subscription-Key':k}).json()
    inc=[i for i in r.get('incidents',[]) if 'Lane' in json.dumps(i)]
    return [f"- {len(inc)} TripCheck incidents/closures mentioning Lane County."]+[f"  - {i.get('headline') or i.get('comments','')[:120]}" for i in inc[:8]]
def fire():
    q=get('https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0/query',params=dict(where="IncidentTypeCategory='WF'",geometry=f'{LON},{LAT}',geometryType='esriGeometryPoint',distance=100,units='esriSRUnit_StatuteMile',inSR=4326,outFields='IncidentName,IncidentSize,PercentContained',f='json')).json()['features']
    q=sorted([x['attributes'] for x in q],key=lambda a:-(a['IncidentSize'] or 0))
    L=[f"- Active wildfires within 100 mi (NIFC): {len(q)}"]+[f"  - {a['IncidentName']}: {a['IncidentSize'] or 0:,.0f} ac, {a['PercentContained'] or 0:.0f}% contained" for a in q[:6]]
    aq=get('https://air-quality-api.open-meteo.com/v1/air-quality',params=dict(latitude=LAT,longitude=LON,hourly='us_aqi,pm2_5',timezone='America/Los_Angeles',forecast_days=2)).json()['hourly']
    a=pd.Series(aq['us_aqi'],index=pd.to_datetime(aq['time'])); a=a[a.index.normalize()==day]
    if len(a): L.append(f"- Air quality (CAMS model): max US AQI {a.max():.0f} ({'Good' if a.max()<=50 else 'Moderate' if a.max()<=100 else 'Unhealthy for sensitive groups' if a.max()<=150 else 'Unhealthy'})")
    return L
def rivers():
    L=[]
    for g,n in [('HARO3','Willamette at Harrisburg'),('VIDO3','McKenzie near Vida')]:
        try:
            j=get(f'https://api.water.noaa.gov/nwps/v1/gauges/{g}').json(); s=j.get('status',{})
            o,fc=s.get('observed',{}),s.get('forecast',{})
            L.append(f"- {n}: {o.get('primary')} {o.get('primaryUnit','ft')} observed, flood category: {o.get('floodCategory','?')}"+(f"; forecast {fc.get('primary')} ({fc.get('floodCategory')})" if fc.get('primary') not in (None,-999) else ''))
        except Exception as e: L.append(f'- {n}: unavailable ({e.__class__.__name__})')
    return L
# Official kickoff times announced before ESPN's feed is updated (ESPN keeps a midnight-ET placeholder with timeValid=false)
KICKOFF_OVERRIDES={('2483','2026-10-31'):('12:30','UO release 2026-10-19: Northwestern at Oregon, 12:30 PM PT, Peacock')}
SPORTS_TODAY={}
def _hav(lat,lon):
    p1,p2=math.radians(LAT),math.radians(lat); dl=math.radians(lon-LON)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 2*3958.8*math.asin(math.sqrt(a))
_VEN={'Autzen Stadium':(44.0582,-123.0685),'Matthew Knight Arena':(44.0451,-123.0662),'Reser Stadium':(44.5595,-123.2811),
      'Gill Coliseum':(44.5612,-123.2793),'PK Park':(44.059,-123.065),'Hayward Field':(44.0425,-123.0703),'Volcanoes Stadium':(45.0213,-123.0148)}
def upcoming_games(days=7):
    """Home games at venues within 100 mi of Eugene, today..today+days. Returns list of dicts sorted by date."""
    G=[]; end=day+pd.Timedelta(days=days)
    teams=[('2483','Ducks',(44.0451,-123.0662)),('204','Beavers',(44.5612,-123.2793))]
    for sport,path in [('football','football/college-football'),("men's basketball",'basketball/mens-college-basketball'),("women's basketball",'basketball/womens-college-basketball')]:
        for tid,nick,campus in teams:
            try: ev=get(f'https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{tid}/schedule').json().get('events',[])
            except Exception: continue
            for e in ev:
                c=e['competitions'][0]; ts=pd.Timestamp(c.get('date') or e['date']); valid=c.get('timeValid',True)
                # timeValid=false -> date/time not set; ESPN stores midnight Eastern, so take the Eastern date and show TBA
                d=(ts.tz_convert(PT) if valid else ts.tz_convert('America/New_York')).tz_localize(None).normalize()
                if not (day<=d<=end): continue
                me=next((x for x in c['competitors'] if str(x['id'])==tid),None)
                if not me or me.get('homeAway')!='home' or c.get('neutralSite'): continue
                vn=(c.get('venue') or {}).get('fullName',''); ll=next((v for k,v in _VEN.items() if k in vn),campus)
                if _hav(*ll)>100: continue
                ko=ts.tz_convert(PT).strftime('%H:%M') if valid else None; note=''
                ov=KICKOFF_OVERRIDES.get((tid,str(d.date())))
                if ov and not ko: ko,note=ov
                opp=next((x['team'].get('displayName','') for x in c['competitors'] if x is not me),'')
                G.append(dict(date=d,ko=ko,team=nick,sport=sport,opp=opp,venue=vn,dist=_hav(*ll),note=note))
    try:
        j=get('https://statsapi.mlb.com/api/v1/schedule',params={'teamId':461,'sportId':13,'startDate':str(day.date()),'endDate':str(end.date())}).json()
        for dd in j.get('dates',[]):
            for g in dd['games']:
                if g['teams']['home']['team']['id']!=461: continue
                t=pd.Timestamp(g['gameDate']).tz_convert(PT)
                G.append(dict(date=pd.Timestamp(dd['date']),ko=None if g.get('status',{}).get('startTimeTBD') else t.strftime('%H:%M'),team='Emeralds',sport='baseball',
                              opp=g['teams']['away']['team']['name'],venue=g.get('venue',{}).get('name','PK Park'),dist=_hav(*_VEN['PK Park']),note=''))
    except Exception: pass
    return sorted(G,key=lambda g:(g['date'],g['ko'] or '99'))
def school_lines(days=7):
    """No-school / early-release days (9 local districts) and notable HS home football+basketball games, today..today+days."""
    import io
    def rd(name):
        for p in (os.path.join(HERE,'data',name), os.path.join('/workspace/eugene-sky/data',name)):
            if os.path.exists(p): return pd.read_csv(p, dtype=str)
        return pd.read_csv(io.StringIO(get(f'https://raw.githubusercontent.com/Churchy156/eugene-sky/main/data/{name}').text), dtype=str)
    NM={'4j':'4J','bethel':'Bethel','springfield':'Springfield','junction_city':'Junction City','monroe':'Monroe','harrisburg':'Harrisburg','creswell':'Creswell','pleasant_hill':'Pleasant Hill','south_lane':'South Lane (Cottage Grove)'}
    L=[]; end=day+pd.Timedelta(days=days)
    try:
        c=rd('school_calendars.csv'); c['d']=pd.to_datetime(c.date); c=c[(c.d>=day)&(c.d<=end)&(c.d.dt.dayofweek<5)]
        lab={'no_school':'no school','no_school_some_grades':'no school (some grades)','early_release':'early release','conference':'conferences'}
        c=c[c.event_type.isin(lab)]
        if len(c):
            L.append('- School days off / short days, next 7 days:')
            for (d,et),g in c.groupby(['d','event_type']):
                L.append(f"  - {d:%a %b %d}: {lab[et]} — {', '.join(sorted(NM.get(k,k) for k in g.district_key.unique()))}")
        else: L.append('- All local districts with a published calendar are in normal session the next 7 days.')
        cov=rd('school_calendar_coverage.csv'); sy=f"{day.year if day.month>=7 else day.year-1}-{str((day.year if day.month>=7 else day.year-1)+1)[2:]}"
        miss=[NM[k] for k in NM if not ((cov.district_key==k)&(cov.school_year==sy)).any()]
        if miss: L.append(f"  - (No published {sy} calendar found for: {', '.join(miss)}.)")
    except Exception as e: L.append(f'- School calendars unavailable ({e.__class__.__name__}).')
    try:
        h=rd('hs_sports_games.csv'); h['d']=pd.to_datetime(h.date)
        h=h[(h.d>=day)&(h.d<=end)&(h.sport.isin(['football','boys_basketball','girls_basketball']))].sort_values(['d','time_local'])
        nb=h[(h.sport!='football')&(h.marquee_rivalry!='1')&(h.game_type!='state playoff')]
        h=h.drop(nb.index)   # notable = all football + basketball rivalry/playoff games
        if len(h) or len(nb):
            L.append(f'- High-school home games, next 7 days: {len(h)} notable'+(f' (+{len(nb)} other basketball home games)' if len(nb) else '')+':')
            for r in h.head(12).itertuples():
                t=pd.Timestamp(f'2000-01-01 {r.time_local}').strftime('%I:%M %p').lstrip('0')+' PT' if isinstance(r.time_local,str) and r.time_local else 'time TBA'
                tag=(' [state playoff]' if r.game_type=='state playoff' else '')+(' [rivalry]' if r.marquee_rivalry=='1' else '')
                L.append(f"  - {r.d:%a %b %d} {t} — {r.sport.replace('_',' ')}: {r.away_team} @ {r.home_team}{tag}")
            if len(h)>12: L.append(f'  - …and {len(h)-12} more.')
    except Exception as e: L.append(f'- HS schedule unavailable ({e.__class__.__name__}).')
    return L
def events():
    L=[]
    hol=USFederalHolidayCalendar().holidays(day,day+pd.Timedelta(days=7))
    L+= [f"- US holiday: {h:%a %b %d}" for h in hol] or ['- No federal holidays in the next 7 days.']
    G=upcoming_games(7)
    SPORTS_TODAY['ducks_fb_home']=int(any(g['date']==day and g['team']=='Ducks' and g['sport']=='football' for g in G))
    if not G: L.append('- No UO/OSU football or basketball or Emeralds home games within 100 mi in the next 7 days.')
    else:
        L.append(f"- Sports home games within 100 mi, next 7 days ({len(G)}):")
        for g in G:
            when=f"{g['date']:%a %b %d} "+(pd.Timestamp(f"2000-01-01 {g['ko']}").strftime('%I:%M %p').lstrip('0')+' PT' if g['ko'] else 'time TBA')
            big=' — expect heavy traffic near the stadium' if g['sport']=='football' else ''
            L.append(f"  - {when} — {g['team']} {g['sport']} HOME vs {g['opp']} @ {g['venue']} ({g['dist']:.0f} mi){big}"+(f" [{g['note']}]" if g['note'] else ''))
    try: L+=school_lines(7)
    except Exception: pass
    L.append('- UO term: see the official UO calendar (dataset uses approximate rules).')
    return L
SUN={}
def daylight():
    o=ephem.Observer(); o.lat,o.lon=str(LAT),str(LON); o.pressure=0; o.horizon='-0:34'
    o.date=ephem.Date((day+pd.Timedelta(hours=19)).to_pydatetime())
    r=o.previous_rising(ephem.Sun()).datetime().replace(tzinfo=dt.timezone.utc).astimezone(PT); s=o.next_setting(ephem.Sun()).datetime().replace(tzinfo=dt.timezone.utc).astimezone(PT)
    SUN.update(sunset=s.hour+s.minute/60,dst=bool(s.dst()))
    nxt=[d for d in pd.date_range(day,day+pd.Timedelta(days=60)) if bool(dt.datetime(d.year,d.month,d.day,12,tzinfo=PT).dst())!=bool(dt.datetime(day.year,day.month,day.day,12,tzinfo=PT).dst())]
    L=[f"- Sunrise {r:%I:%M %p}, sunset {s:%I:%M %p} PT — {(s-r).total_seconds()/3600:.1f} h of daylight."]
    if nxt: L.append(f"- Clocks change on {nxt[0]:%a %b %d} ({'spring forward' if bool(dt.datetime(nxt[0].year,nxt[0].month,nxt[0].day,12,tzinfo=PT).dst()) else 'fall back'}).")
    return L
def space():
    t=get('https://services.swpc.noaa.gov/text/3-day-forecast.txt').text
    L=[' '.join(p.split()) for p in t.split('\n\n') if p.strip().startswith('The greatest')]
    L=[x.split('\n')[0] for x in L]
    rat=t.split('Rationale:')[1].split('\n\n')[0].replace('\n',' ').strip() if 'Rationale:' in t else ''
    return [f'- {x}' for x in L]+([f'- {rat}'] if rat else [])+['- (Historically no measurable effect on Eugene weather or markets.)']
def moontide():
    d=ephem.Date((day+pd.Timedelta(hours=19)).to_pydatetime()); m=ephem.Moon(d)
    L=[f"- Moon {m.phase:.0f}% illuminated; next full {ephem.localtime(ephem.next_full_moon(d)):%b %d}, next new {ephem.localtime(ephem.next_new_moon(d)):%b %d}."]
    tp=get('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter',params=dict(product='predictions',interval='hilo',station='9435380',begin_date=f'{day:%Y%m%d}',range=24,datum='MLLW',units='english',time_zone='lst_ldt',format='json',application='eugene-env')).json()['predictions']
    L.append('- Newport (South Beach) tides: '+', '.join(f"{'High' if p['type']=='H' else 'Low'} {float(p['v']):.1f} ft at {p['t'][-5:]}" for p in tp))
    return L
def markets():
    L=[]
    for s,n in [('^GSPC','S&P 500'),('^DJI','Dow'),('^IXIC','Nasdaq'),('GC=F','Gold'),('DX-Y.NYB','Dollar index'),('^TNX','10-yr Treasury yield %')]:
        try:
            r=get(f'https://query1.finance.yahoo.com/v8/finance/chart/{s}',params=dict(range='5d',interval='1d'),headers={'User-Agent':'Mozilla/5.0'}).json()['chart']['result'][0]
            c=[x for x in r['indicators']['quote'][0]['close'] if x]; L.append(f"- {n}: {c[-1]:,.2f} ({(c[-1]/c[-2]-1)*100:+.2f}% vs prior close)")
        except Exception as e: L.append(f'- {n}: unavailable')
    return L
def crash():
    m=pickle.load(open(os.path.join(HERE,'crash_model.pkl'),'rb'))
    if not WX: return ['- needs weather forecast (unavailable)']
    i=WX['time'].index(str(day.date())) if str(day.date()) in WX['time'] else 0
    pr=WX['precipitation_sum'][i] or 0; prev=WX['precipitation_sum'][:i]
    hol=int(day in USFederalHolidayCalendar().holidays(day,day))
    row=dict(dow=str(day.dayofweek),month=str(day.month),covid=0,wet=int(pr>=0.01),rain_in=min(pr,2),first_rain=0,freeze=int(WX['temperature_2m_min'][i]<=32),snow=int((WX['snowfall_sum'][i] or 0)>0),hot=int(WX['temperature_2m_max'][i]>=95),
             sunset_hour_local=SUN.get('sunset',18),dst_week_after=0,hol=hol,ev_ducks_fb_home=SPORTS_TODAY.get('ducks_fb_home',0),ev_4j_break_approx=0,ev_uo_in_session_approx=1,fire_smoke_day=0,nws_alerts_winter=0)
    level=np.log(31.5)  # approx 2024 daily mean, 6-county ODOT reported crashes (latest year available)
    X=pd.DataFrame([row]); e=float(m.predict(X,offset=[level])[0])
    norm=dict(row,wet=0,rain_in=0,freeze=0,snow=0,hot=0); n=float(m.predict(pd.DataFrame([norm]),offset=[level])[0])
    rel=e/n-1
    lvl='ELEVATED' if rel>0.15 else 'slightly above normal' if rel>0.05 else 'about normal' if rel>-0.05 else 'below normal'
    return [f"- Expected reported crashes (6-county ODOT-style count): ~{e:.0f} vs ~{n:.0f} on a dry day with the same weekday/season → **{lvl}** ({rel:+.0%}).",
            '- Drivers: rain amount (+21% per inch), freezing low (+8%), winter-storm alerts (+16%), holidays (−23%). Model is rough (held-out r≈0.52); treat as a nudge, not a prediction.']
def power():  # Steven's utilities: EWEB, Emerald PUD, Blachly-Lane, Pacific Power + nearby BPA lines (zip_tools/power_feeds.py)
    for p in (os.path.join(HERE,'zip_tools'),'/workspace/eugene-sky/zip_tools'):
        if os.path.exists(os.path.join(p,'power_feeds.py')):
            if p not in sys.path: sys.path.insert(0,p)
            break
    import power_feeds
    return power_feeds.report_lines()

def _zip_tools():
    for p in (os.path.join(HERE,'zip_tools'),'/workspace/eugene-sky/zip_tools'):
        if os.path.exists(os.path.join(p,'eq_map.py')):
            if p not in sys.path: sys.path.insert(0,p)
            return
def earthquakes():  # USGS near-Eugene + worldwide; renders reports/eq_map_DATE.png and copies it to the email attachments folder (eq_map.py)
    _zip_tools(); import eq_map
    return eq_map.report_lines(day.date(), os.path.join(HERE,'reports'))

def ring_of_fire():  # GeoNet + Pacific Ring of Fire (shared code in eugene-sky/zip_tools/ringfire_core.py)
    for p in (os.path.join(HERE,'zip_tools'),'/workspace/eugene-sky/zip_tools'):
        if os.path.exists(os.path.join(p,'ringfire_core.py')):
            if p not in sys.path: sys.path.insert(0,p)
            break
    import ringfire_core
    return ringfire_core.report_lines()

section('Weather',weather); section('NWS alerts',alerts); section('Roads (ODOT TripCheck)',roads); section('Wildfire & smoke',fire)
section('Rivers (NOAA NWPS)',rivers); section('Events & calendar',events); section('Daylight',daylight); section('Space weather (NOAA SWPC)',space)
section('Earthquakes',earthquakes); section('Ring of Fire (Pacific quakes, volcanoes, tsunami)',ring_of_fire)
section('Moon & tides',moontide); section('Power & grid',power); section('Markets snapshot',markets); section('Crash risk vs normal',crash)
os.makedirs(os.path.join(HERE,'reports'),exist_ok=True); txt='\n'.join(out)
open(os.path.join(HERE,'reports',f'outlook_{day.date()}.md'),'w').write(txt); print(txt)
try:  # HTML email version with the quake map inline (cid:eq_map_DATE.png). Re-run `python zip_tools/eq_map.py html reports/email_DATE.md` after editing the email .md.
    _zip_tools(); import eq_map
    _src=os.path.join(HERE,'reports',f'email_{day.date()}.md')
    eq_map.write_html(_src if os.path.exists(_src) else os.path.join(HERE,'reports',f'outlook_{day.date()}.md'),
                      html_path=os.path.join(HERE,'reports',f'email_{day.date()}.html'))
except Exception as e: print(f'(email html failed: {e.__class__.__name__}: {e})',file=sys.stderr)
