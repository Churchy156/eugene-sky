"""Add NWS warnings, rivers, smoke/fire, events, daylight/DST, respiratory to master CSV."""
import pandas as pd, numpy as np, json, glob, zipfile, ephem, datetime as dt
from zoneinfo import ZoneInfo
from pandas.tseries.holiday import USFederalHolidayCalendar
X='raw/x/'; PT=ZoneInfo('America/Los_Angeles')
df=pd.read_csv('eugene_env_daily_1950_present.csv',index_col=0,parse_dates=True)
NEW=[c for c in df.columns if c.startswith(('nws_','river_','pm25_epa','fire_','ev_','sunrise','sunset','daylight','dst_','resp_'))]
df=df.drop(columns=NEW); idx=df.index; dd={}
# 1 NWS warnings (IEM VTEC archive), Eugene zone ORZ008(<=2024-03)/ORZ118 + Lane County ORC039
ev=[]
for f in ['iem_z.json','iem_z2.json','iem_c.json']: ev+=json.load(open(X+f))['events']
e=pd.DataFrame(ev); e=e.drop_duplicates(['wfo','phenomena','significance','eventid','issue'])
e['s']=pd.to_datetime(e.issue,utc=True).dt.tz_convert(PT).dt.tz_localize(None).dt.normalize()
e['t']=pd.to_datetime(e.expire,utc=True).dt.tz_convert(PT).dt.tz_localize(None).dt.normalize()
act={k:pd.Series(0,index=idx) for k in ['any','warning','winter','heat','wind','flood','fog','smoke_airq']}
grp={'winter':['WS','WW','BZ','IS','ZR','WC','EC','HZ','FZ','FR'],'heat':['HT','EH','XH'],'wind':['WI','HW'],'flood':['FA','FF','FL','HY'],'fog':['FG'],'smoke_airq':['AQ','AS','SM','DU']}
for _,r in e.iterrows():
    days=pd.date_range(r.s,max(r.s,r.t)); days=days[days.isin(idx)]
    act['any'][days]+=1
    if r.significance=='W': act['warning'][days]+=1
    for g,ps in grp.items():
        if r.phenomena in ps: act[g][days]+=1
start=pd.Timestamp('2005-10-01')
for k,s in act.items():
    c=f'nws_alerts_{k}'; df[c]=s.where(idx>=start)
    dd[c]=f'Count of NWS watch/warning/advisory events active that day for Eugene zone (ORZ008→ORZ118) or Lane County ORC039, group={k} (IEM VTEC archive; zone archive starts 2005-10, county-only events earlier excluded)'
# 4 rivers NWIS daily
rows=[l.rstrip('\n').split('\t') for l in open(X+'nwis.rdb') if not l.startswith('#')]
names={'14166000':'willamette_harrisburg','14162500':'mckenzie_vida','14165500':'mckenzie_coburg'}
cur=None
for l in open(X+'nwis.rdb'):
    if l.startswith('#'): continue
    p=l.rstrip('\n').split('\t')
    if p[0]=='agency_cd': hdr=p; continue
    if p[0]!='USGS': continue
    d=dict(zip(hdr,p)); col=[h for h in hdr if h.endswith('_00060_00003')]
    for h in col:
        v=d.get(h,'')
        try: df.loc[pd.Timestamp(d['datetime']),'river_'+names[p[1]]+'_cfs']=float(v)
        except: pass
for n in names.values():
    c='river_'+n+'_cfs'; dd[c]=f'USGS NWIS daily mean discharge, cfs ({n.replace("_"," ")})'
# 3 smoke: EPA AirData daily PM2.5 (FRM/FEM 88101), Lane County monitors, daily mean across monitors
pm=[]
for z in sorted(glob.glob(X+'epa/pm_*.zip')):
    try:
        with zipfile.ZipFile(z) as zz:
            t=pd.read_csv(zz.open(zz.namelist()[0]),usecols=['State Code','County Code','Date Local','Arithmetic Mean'],dtype={'State Code':str})
        pm.append(t[(t['State Code']=='41')&(t['County Code']==39)])
    except Exception as ex: print('epa',z,ex)
pm=pd.concat(pm); pm['d']=pd.to_datetime(pm['Date Local'])
g=pm.groupby('d')['Arithmetic Mean']
df['pm25_epa_lane_mean']=g.mean(); df['pm25_epa_lane_max']=g.max()
df['fire_smoke_day']=(df.pm25_epa_lane_max>=35.5).astype(float).where(df.pm25_epa_lane_max.notna())
dd.update(pm25_epa_lane_mean='EPA AirData daily PM2.5 µg/m³ (param 88101), mean of Lane County monitors',pm25_epa_lane_max='Max of Lane County monitors',fire_smoke_day='1 if any Lane monitor ≥35.5 µg/m³ (AQI Unhealthy-for-Sensitive+); mostly wildfire smoke in summer/fall, wood smoke in winter')
fh=pd.DataFrame([f['attributes'] for f in json.load(open(X+'firehist.json'))['features']])
fh['yr']=pd.to_numeric(fh.FIRE_YEAR,errors='coerce'); acres=fh.groupby('yr').GIS_ACRES.sum()
df['fire_acres_100mi_year']=pd.Series(idx.year,index=idx).map(acres).fillna(0).where(idx.year<=2025)
dd['fire_acres_100mi_year']='ANNUAL total acres of fires >1000 ac within 100 mi of Eugene (NIFC perimeter history; no reliable daily dates — same value all year)'
# 5 events
hol=USFederalHolidayCalendar().holidays('1950-01-01','2026-12-31')
df['ev_us_holiday']=idx.isin(hol).astype(int); dd['ev_us_holiday']='US federal holiday (pandas calendar, applied retroactively)'
def espn(kind):
    out=[]
    for f in glob.glob(X+f'espn/{kind}_*.json'):
        for e in json.load(open(f)).get('events',[]):
            c=e['competitions'][0]
            if c.get('neutralSite'): continue
            if any(x['homeAway']=='home' and x['team']['id']=='2483' for x in c['competitors']):
                out.append(pd.Timestamp(e['date']).tz_convert(PT).tz_localize(None).normalize())
    return pd.Series(1,index=pd.DatetimeIndex(out).unique())
for k,lab in [('fb','football'),('bb','men\'s basketball')]:
    s=espn(k)
    c='ev_ducks_fb_home' if k=='fb' else 'ev_ducks_mbb_home'
    df[c]=s.reindex(idx).fillna(0).where(idx>='2001-07-01'); dd[c]=f'Oregon Ducks {lab} home game in Eugene (ESPN schedule API; 2001+)'
# UO terms / 4J breaks: APPROXIMATE rules
y=idx.year; m=idx.month; dday=idx.day
thx=pd.Series([d for d in hol if d.month==11],dtype='datetime64[ns]')
uo=np.zeros(len(idx),int); k4=np.zeros(len(idx),int)
for yr in range(1950,2027):
    lab=pd.Timestamp(f'{yr}-09-01'); lab+= pd.Timedelta(days=(0-lab.weekday())%7) # Labor Day
    fall=lab+pd.Timedelta(days=21); fall_end=pd.Timestamp(f'{yr}-12-13')
    win=pd.Timestamp(f'{yr}-01-06'); win+=pd.Timedelta(days=(0-win.weekday())%7); win_end=win+pd.Timedelta(days=74)
    spr=win_end+pd.Timedelta(days=10); spr_end=spr+pd.Timedelta(days=74)
    for a,b in [(fall,fall_end),(win,win_end),(spr,spr_end)]: uo[(idx>=a)&(idx<=b)]=1
    tg=thx[thx.dt.year==yr]
    # 4J: winter break Dec 21-Jan 3, spring break week of last full week of March, Thanksgiving Wed-Fri, summer mid-Jun to day after Labor Day
    sb=pd.Timestamp(f'{yr}-03-31'); sb-=pd.Timedelta(days=(sb.weekday()-0)%7)
    if sb.day>25: sb-=pd.Timedelta(days=7)
    for a,b in [(f'{yr}-12-21',f'{yr}-12-31'),(f'{yr}-01-01',f'{yr}-01-03'),(sb,sb+pd.Timedelta(days=4)),(f'{yr}-06-14',lab+pd.Timedelta(days=1))]+([(tg.iloc[0]-pd.Timedelta(days=1),tg.iloc[0]+pd.Timedelta(days=1))] if len(tg) else []):
        k4[(idx>=pd.Timestamp(a))&(idx<=pd.Timestamp(b))]=1
df['ev_uo_in_session_approx']=uo; df['ev_4j_break_approx']=k4
dd['ev_uo_in_session_approx']='APPROXIMATE UO quarter in session (rule-based: fall ~3 wks after Labor Day–Dec 13; winter 1st Mon Jan +10.5 wks; spring after ~10-day break). Not official calendar.'
dd['ev_4j_break_approx']='APPROXIMATE Eugene 4J school break/summer (rule-based: Dec 21–Jan 3, late-March week, Thanksgiving Wed–Fri, Jun 14–day after Labor Day). Not official calendar.'
# 6 daylight / DST
o=ephem.Observer(); o.lat,o.lon,o.elevation='44.05','-123.09',130; o.pressure=0; o.horizon='-0:34'
sr=[];ss=[]
for d in idx:
    o.date=ephem.Date((d+pd.Timedelta(hours=19)).to_pydatetime())  # ~noon PDT/11am PST in UTC
    r=o.previous_rising(ephem.Sun()).datetime(); s=o.next_setting(ephem.Sun()).datetime()
    sr.append(r);ss.append(s)
sr=pd.to_datetime(sr).tz_localize('UTC').tz_convert(PT); ss=pd.to_datetime(ss).tz_localize('UTC').tz_convert(PT)
df['sunrise_local']=sr.strftime('%H:%M'); df['sunset_local']=ss.strftime('%H:%M')
df['daylight_hours']=np.round((ss-sr).total_seconds()/3600,3)
df['sunset_hour_local']=np.round(ss.hour+ss.minute/60,3)
dst=np.array([bool(dt.datetime(d.year,d.month,d.day,12,tzinfo=PT).dst()) for d in idx])
df['dst_in_effect']=dst.astype(int)
ch=np.r_[False,dst[1:]!=dst[:-1]]
df['dst_transition_day']=0; df.loc[ch,'dst_transition_day']=np.where(dst[ch],1,-1)
wk=pd.Series(ch.astype(int),index=idx).rolling(7,min_periods=1).max()
df['dst_week_after']=wk.astype(int)
dd.update(sunrise_local='Sunrise local time Eugene (computed, ephem)',sunset_local='Sunset local time',daylight_hours='Hours between sunrise and sunset',sunset_hour_local='Sunset as decimal hour local time (darkness during PM commute)',dst_in_effect='1 if Pacific Daylight Time in effect (tz database, historical rules)',dst_transition_day='+1 spring-forward day, -1 fall-back day, 0 otherwise',dst_week_after='1 for the transition day and 6 days after')
# 7 respiratory: CDC ILINet Oregon weekly via Delphi epidata (assigned to all 7 days of epiweek)
f=pd.DataFrame(json.load(open(X+'flu.json'))['epidata'])
def ew2d(w): y,k=divmod(int(w),100); j=pd.Timestamp(f'{y}-01-04'); return j-pd.Timedelta(days=(j.weekday()+1)%7)+pd.Timedelta(weeks=k-1)
f['d']=f.epiweek.map(ew2d); s=f.set_index('d').wili
df['resp_ili_pct_oregon_weekly']=s.reindex(idx).ffill(limit=6).where(idx>=s.index.min())
dd['resp_ili_pct_oregon_weekly']='CDC ILINet weighted % of outpatient visits for influenza-like illness, Oregon, weekly (Delphi epidata); value repeated for the 7 days of its epiweek (Sun–Sat), not a daily measure'
df.to_csv('eugene_env_daily_1950_present.csv',float_format='%.5g')
D=pd.read_csv('column_dictionary.csv'); D=D[~D.column.isin(dd)]
for c,desc in dd.items():
    s=df[c]; D.loc[len(D)]=dict(column=c,description=desc,first=str(s.first_valid_index())[:10],last=str(s.last_valid_index())[:10],pct_days_nonblank=round(100*s.notna().mean(),1))
D.to_csv('column_dictionary.csv',index=False)
print(D[D.column.isin(dd)].drop(columns='description').to_string())
