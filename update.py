"""Incremental update: re-fetch the last DAYS days from live sources and upsert into data/eugene_env_daily.csv.gz.
Each source is independent; failures are logged and skipped. Historical-only columns (flares, EAGLE-I outages,
EPA AirData, ODOT crashes, FRED FX lag) are left as-is."""
import os, io, json, datetime as dt, traceback
import requests, numpy as np, pandas as pd, ephem
from zoneinfo import ZoneInfo
from pandas.tseries.holiday import USFederalHolidayCalendar
PT=ZoneInfo('America/Los_Angeles'); P='data/eugene_env_daily.csv.gz'; DAYS=int(os.environ.get('DAYS',21))
UA={'User-Agent':'eugene-sky updater (github actions)'}
df=pd.read_csv(P,index_col=0,parse_dates=True)
today=pd.Timestamp(dt.datetime.now(PT).date()); start=today-pd.Timedelta(days=DAYS)
df=df.reindex(df.index.union(pd.date_range(df.index.min(),today))); df.index.name='date'
W=pd.date_range(start,today); log=[]
def get(u,headers=None,**k): r=requests.get(u,headers={**UA,**(headers or {})},timeout=60,**k); r.raise_for_status(); return r
def put(col,s):
    s=s[(s.index>=start)&(s.index<=today)].dropna()
    if len(s): df.loc[s.index,col]=s.values
def src(name):
    def deco(fn):
        try: fn(); log.append(f'ok   {name}')
        except Exception as e: log.append(f'FAIL {name}: {e.__class__.__name__}: {str(e)[:150]}')
    return deco
@src('weather GHCN')
def _():
    g=pd.read_csv(io.StringIO(get('https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/USW00024221.csv').text),usecols=['DATE','TMAX','TMIN','PRCP','SNOW'],parse_dates=['DATE'],low_memory=False).set_index('DATE')
    put('tmax_F',g.TMAX/10*9/5+32); put('tmin_F',g.TMIN/10*9/5+32); put('prcp_in',g.PRCP/254); put('snow_in',g.SNOW/25.4)
@src('ERA5/Open-Meteo pressure, RH, wind')
def _():
    a=get('https://api.open-meteo.com/v1/forecast',params=dict(latitude=44.12,longitude=-123.22,past_days=DAYS,forecast_days=1,daily='pressure_msl_mean,surface_pressure_mean,relative_humidity_2m_mean,wind_speed_10m_max,shortwave_radiation_sum',wind_speed_unit='mph',timezone='America/Los_Angeles')).json()['daily']
    a=pd.DataFrame(a); a.index=pd.to_datetime(a.pop('time'))
    for c,s in [('pressure_msl_hPa_era5','pressure_msl_mean'),('surface_pressure_hPa_era5','surface_pressure_mean'),('rh_mean_pct_era5','relative_humidity_2m_mean'),('wind_max_mph_era5','wind_speed_10m_max'),('solar_rad_MJm2_era5','shortwave_radiation_sum')]: put(c,a[s])
@src('GFZ Kp/Ap/F10.7')
def _():
    rows=[]
    for l in get('https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_nowcast.txt').text.splitlines():
        if l.startswith('#') or not l.strip(): continue
        p=l.split(); kp=[float(x) for x in p[7:15]]
        rows.append((pd.Timestamp(f'{p[0]}-{p[1]}-{p[2]}'),max(kp) if min(kp)>=0 else np.nan,sum(kp) if min(kp)>=0 else np.nan,float(p[23]) if float(p[23])>=0 else np.nan,float(p[25]) if float(p[25])>0 else np.nan))
    k=pd.DataFrame(rows,columns=['d','kp_max','kp_sum','Ap','F107_adj']).set_index('d')
    for c in k: put(c,k[c])
@src('SILSO sunspots')
def _():
    s=pd.read_csv(io.StringIO(get('https://www.sidc.be/SILSO/INFO/sndtotcsv.php').text),sep=';',header=None)
    s.index=pd.to_datetime(dict(year=s[0],month=s[1],day=s[2])); put('sunspot_n',s[4].where(s[4]>=0))
@src('solar wind (SWPC real-time, last ~day; OMNI history)')
def _():
    w=pd.DataFrame(get('https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json').json()); w.index=pd.to_datetime(w.time_tag)
    m=pd.DataFrame(get('https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json').json()); m.index=pd.to_datetime(m.time_tag)
    w=w[['proton_speed','proton_density']].apply(pd.to_numeric,errors='coerce').resample('D').mean(); m=m[['bz_gsm','bt']].apply(pd.to_numeric,errors='coerce').resample('D').mean()
    put('sw_speed_kms',w.proton_speed); put('sw_density_cc',w.proton_density); put('sw_Bz_gsm_nT',m.bz_gsm); put('sw_B_nT',m.bt)
@src('USGS quakes')
def _():
    B='https://earthquake.usgs.gov/fdsnws/event/1/query'
    eg=pd.read_csv(io.StringIO(get(B,params=dict(format='csv',starttime=str(start.date()),minmagnitude=6)).text),parse_dates=['time'])
    er=pd.read_csv(io.StringIO(get(B,params=dict(format='csv',starttime=str(start.date()),minmagnitude=2.5,latitude=44.12,longitude=-123.22,maxradiuskm=500)).text),parse_dates=['time'])
    eg['d']=eg.time.dt.tz_localize(None).dt.normalize() if eg.time.dt.tz is None else eg.time.dt.tz_convert('UTC').dt.tz_localize(None).dt.normalize()
    er['d']=(er.time if er.time.dt.tz is not None else er.time.dt.tz_localize('UTC')).dt.tz_convert(PT).dt.tz_localize(None).dt.normalize()
    put('eq_global_M6plus',eg.groupby('d').size().reindex(W).fillna(0)); df.loc[W,'eq_global_maxmag']=eg.groupby('d').mag.max().reindex(W).values
    put('eq_500km_M2.5plus',er.groupby('d').size().reindex(W).fillna(0)); df.loc[W,'eq_500km_maxmag']=er.groupby('d').mag.max().reindex(W).values
@src('moon, daylight, DST, holidays (computed)')
def _():
    o=ephem.Observer(); o.lat,o.lon='44.05','-123.09'; o.pressure=0; o.horizon='-0:34'
    for d in W:
        t=ephem.Date((d+pd.Timedelta(hours=20)).to_pydatetime()); df.loc[d,'moon_illum']=round(ephem.Moon(t).phase/100,3); df.loc[d,'moon_age_days']=round(t-ephem.previous_new_moon(t),2)
        o.date=ephem.Date((d+pd.Timedelta(hours=19)).to_pydatetime())
        r=pd.Timestamp(o.previous_rising(ephem.Sun()).datetime(),tz='UTC').tz_convert(PT); s=pd.Timestamp(o.next_setting(ephem.Sun()).datetime(),tz='UTC').tz_convert(PT)
        df.loc[d,['sunrise_local','sunset_local']]=[r.strftime('%H:%M'),s.strftime('%H:%M')]; df.loc[d,'daylight_hours']=round((s-r).total_seconds()/3600,3); df.loc[d,'sunset_hour_local']=round(s.hour+s.minute/60,3)
        df.loc[d,'dst_in_effect']=int(bool(dt.datetime(d.year,d.month,d.day,12,tzinfo=PT).dst()))
    df['moon_phase']=pd.cut(df.moon_age_days,[-1,1.85,5.5,9.2,12.9,16.6,20.3,24,27.7,30],labels=['New','Waxing Crescent','First Quarter','Waxing Gibbous','Full','Waning Gibbous','Last Quarter','Waning Crescent','New'],ordered=False).astype(str)
    hol=USFederalHolidayCalendar().holidays(start,today); df.loc[W,'ev_us_holiday']=W.isin(hol).astype(int)
@src('NOAA tides 9435380')
def _():
    txt=get('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter',params=dict(product='high_low',station='9435380',begin_date=f'{start:%Y%m%d}',end_date=f'{today:%Y%m%d}',datum='MLLW',units='english',time_zone='lst_ldt',format='csv',application='eugene-sky')).text
    if 'No data' in txt: log.append('note tides: no new verified high/low data yet (NOAA verifies with ~1-2 month lag)'); return
    t=pd.read_csv(io.StringIO(txt))
    t.columns=[c.strip() for c in t.columns]; t['d']=pd.to_datetime(t['Date Time']).dt.normalize(); t['TY']=t.TY.str.strip()
    hi=t[t.TY.isin(['H','HH'])].groupby('d')['Water Level'].max(); lo=t[t.TY.isin(['L','LL'])].groupby('d')['Water Level'].min()
    put('tide_high_ft',hi); put('tide_low_ft',lo); put('tide_range_ft',hi-lo)
@src('markets (Yahoo)')
def _():
    for s,c in [('^GSPC','fin_sp500_close'),('^DJI','fin_dow_close'),('^IXIC','fin_nasdaq_comp'),('GC=F','fin_gold_usd_oz'),('DX-Y.NYB','fin_dxy')]:
        r=get(f'https://query1.finance.yahoo.com/v8/finance/chart/{s}',params=dict(range='1mo',interval='1d'),headers={'User-Agent':'Mozilla/5.0'}).json()['chart']['result'][0]
        d=pd.to_datetime(r['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
        put(c,pd.Series(r['indicators']['quote'][0]['close'],index=d,dtype=float).groupby(level=0).last())
@src('FRED rates & FX')
def _():
    for sid,c in [('DFF','fin_fed_funds_pct'),('DGS10','fin_ust10y_pct'),('DTWEXBGS','fin_usd_broad_idx'),('DEXUSEU','fin_usd_per_eur'),('DEXJPUS','fin_jpy_per_usd'),('DEXUSUK','fin_usd_per_gbp'),('DEXCHUS','fin_cny_per_usd'),('DEXCAUS','fin_cad_per_usd'),('DEXMXUS','fin_mxn_per_usd')]:
        x=pd.read_csv(io.StringIO(get('https://fred.stlouisfed.org/graph/fredgraph.csv',params=dict(id=sid,cosd=str((start-pd.Timedelta(days=30)).date()))).text)); x.index=pd.to_datetime(x.iloc[:,0]); put(c,pd.to_numeric(x.iloc[:,1],errors='coerce'))
@src('returns recompute')
def _():
    for c in [c for c in df.columns if c.startswith('fin_')]:
        s=df[c].dropna(); r=s.diff() if 'pct' in c else np.log(s).diff(); df['ret_'+c[4:]]=r.reindex(df.index)
@src('USGS rivers')
def _():
    names={'14166000':'willamette_harrisburg','14162500':'mckenzie_vida','14165500':'mckenzie_coburg'}
    j=get('https://waterservices.usgs.gov/nwis/dv/',params=dict(format='json',sites=','.join(names),parameterCd='00060',startDT=str(start.date()))).json()
    for ts in j['value']['timeSeries']:
        site=ts['sourceInfo']['siteCode'][0]['value']; v=ts['values'][0]['value']
        put('river_'+names[site]+'_cfs',pd.Series([float(x['value']) for x in v],index=pd.to_datetime([x['dateTime'][:10] for x in v])))
@src('NWS alerts (IEM archive)')
def _():
    ev=[]
    for u in ['ORZ118','ORC039']: ev+=get('https://mesonet.agron.iastate.edu/json/vtec_events_byugc.php',params=dict(ugc=u,sdate=str(start.date()),edate=str((today+pd.Timedelta(days=1)).date()))).json()['events']
    grp={'winter':['WS','WW','BZ','IS','ZR','WC','EC','HZ','FZ','FR'],'heat':['HT','EH','XH'],'wind':['WI','HW'],'flood':['FA','FF','FL','HY'],'fog':['FG'],'smoke_airq':['AQ','AS','SM','DU']}
    act={k:pd.Series(0,index=W) for k in ['any','warning',*grp]}
    seen=set()
    for r in ev:
        key=(r['wfo'],r['phenomena'],r['significance'],r['eventid'],r['issue'])
        if key in seen: continue
        seen.add(key)
        s=pd.Timestamp(r['issue']).tz_convert(PT).tz_localize(None).normalize(); t=pd.Timestamp(r['expire']).tz_convert(PT).tz_localize(None).normalize()
        days=pd.date_range(s,max(s,t)); days=days[days.isin(W)]
        act['any'][days]+=1
        if r['significance']=='W': act['warning'][days]+=1
        for g,ps in grp.items():
            if r['phenomena'] in ps: act[g][days]+=1
    for k,s in act.items(): df.loc[W,f'nws_alerts_{k}']=s.values
@src('air quality (CAMS)')
def _():
    q=get('https://air-quality-api.open-meteo.com/v1/air-quality',params=dict(latitude=44.05,longitude=-123.09,past_days=DAYS,forecast_days=1,hourly='pm2_5,us_aqi,uv_index',timezone='America/Los_Angeles')).json()['hourly']
    q=pd.DataFrame(q); q.index=pd.to_datetime(q.pop('time')); d=q.resample('D').agg({'pm2_5':'mean','us_aqi':'max','uv_index':'max'})
    put('pm25_ugm3_cams',d.pm2_5); put('us_aqi_max_cams',d.us_aqi); put('uv_index_max_cams',d.uv_index)
@src('BPA load/generation (5-min, last 7 days)')
def _():
    rows=[l.split('\t') for l in get('https://transmission.bpa.gov/business/operations/Wind/baltwg.txt').text.splitlines() if l[:2].isdigit()]
    b=pd.DataFrame([r[:6] for r in rows if len(r)>=6],columns=['t','load','ver','hydro','thermal','nuclear'])
    b.index=pd.to_datetime(b.pop('t'),format='%m/%d/%Y %H:%M'); b=b.apply(pd.to_numeric,errors='coerce').dropna(subset=['load'])
    d=b.resample('D').mean(); full=b.resample('D').size()>=240  # only days with ≥20h of data
    d=d[full]; put('bpa_ba_load_avg_MW',d.load.round()); put('bpa_hydro_gen_avg_MW',d.hydro.round()); put('bpa_thermal_gen_avg_MW',(d.thermal+d.nuclear).round())
    put('bpa_wind_gen_avg_MW',d.ver.round())  # BPA 'VER' = wind+solar; solar column left blank for live days
@src('EWEB + Consumers Power live outage snapshot')
def _():
    f=get('https://services7.arcgis.com/6AM8yPAeyXiPc9eF/arcgis/rest/services/PublicOutageMap_Public_View/FeatureServer/0/query',params=dict(where='1=1',outFields='custcnt,status',returnGeometry='false',f='json')).json()['features']
    e=sum((x['attributes']['custcnt'] or 0) for x in f if x['attributes'].get('status')!='Restored')
    c=sum((x.get('customersOutNow') or 0) for x in get('https://outage.cpi.coop/data/outages.json').json())
    for col,v in [('outage_live_eweb_cust_out_max',e),('outage_live_cpi_cust_out_max',c)]:
        if col not in df: df[col]=np.nan
        df.loc[today,col]=max(v,df.loc[today,col]) if pd.notna(df.loc[today,col]) else v
df.to_csv(P,float_format='%.5g',compression='gzip')
print('\n'.join(log)); print('rows',len(df),'last',df.index.max().date())
open('site_update_log.txt','w').write(f'{dt.datetime.now(PT):%Y-%m-%d %H:%M %Z}\n'+'\n'.join(log)+'\n')
