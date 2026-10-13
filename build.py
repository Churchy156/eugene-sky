import pandas as pd, numpy as np, glob, re, ephem, math, json
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
R='raw/'
idx=pd.date_range('1950-01-01','2026-10-12')
df=pd.DataFrame(index=idx); df.index.name='date'
# weather
g=pd.read_csv(R+'ghcn.csv',usecols=['DATE','TMAX','TMIN','PRCP','SNOW','AWND'],parse_dates=['DATE'],low_memory=False).set_index('DATE')
df['tmax_F']=g.TMAX/10*9/5+32; df['tmin_F']=g.TMIN/10*9/5+32; df['prcp_in']=g.PRCP/254; df['snow_in']=g.SNOW/25.4; df['wind_avg_mph']=g.AWND/10*2.23694
# kp
rows=[]
for l in open(R+'kp.txt'):
    if l.startswith('#'):continue
    p=l.split()
    rows.append((f'{p[0]}-{p[1]}-{p[2]}',max(map(float,p[7:15])),sum(map(float,p[7:15])),int(p[23]),float(p[25])))
k=pd.DataFrame(rows,columns=['d','kp_max','kp_sum','Ap','F107_adj']); k.index=pd.to_datetime(k.d)
k.loc[k.Ap<0,'Ap']=np.nan; k.loc[k.F107_adj<=0,'F107_adj']=np.nan; k.loc[k.kp_max<0,['kp_max','kp_sum']]=np.nan
for c in ['kp_max','kp_sum','Ap','F107_adj']: df[c]=k[c]
# sunspots
s=pd.read_csv(R+'sn.csv',sep=';',header=None); s.index=pd.to_datetime(dict(year=s[0],month=s[1],day=s[2]))
df['sunspot_n']=s[4].where(s[4]>=0)
# flares
fl=[]
for f in glob.glob(R+'fl_*.txt'):
    for l in open(f,errors='ignore'):
        m=re.search(r'\s([BCMX])\s?(\d)',l[50:]) if len(l)>60 else None
        if not m: continue
        try: d=pd.to_datetime(l[5:11],format='%y%m%d')
        except: continue
        fl.append((d,m.group(1)))
fl=pd.DataFrame(fl,columns=['d','c']); fl.loc[fl.d.dt.year<1975,'d']+=pd.DateOffset(years=100)
fl=fl[fl.d.dt.year<=2017].drop_duplicates()
for c in 'CMX': df[f'flares_{c}']=fl[fl.c==c].groupby('d').size().reindex(idx)
fmask=(idx>='1975-09-01')&(idx<='2016-12-31')
for c in 'CMX': df.loc[fmask,f'flares_{c}']=df.loc[fmask,f'flares_{c}'].fillna(0)
# quakes
eg=pd.read_csv(R+'eq_global.csv',parse_dates=['time']); eg['d']=eg.time.dt.tz_localize(None).dt.normalize()
df['eq_global_M6plus']=eg.groupby('d').size().reindex(idx).fillna(0); df['eq_global_maxmag']=eg.groupby('d').mag.max()
er=pd.concat([pd.read_csv(f,parse_dates=['time']) for f in glob.glob(R+'eq_reg_*.csv')]).drop_duplicates('id')
er['d']=er.time.dt.tz_convert('America/Los_Angeles').dt.tz_localize(None).dt.normalize()
df['eq_500km_M2.5plus']=er.groupby('d').size().reindex(idx).fillna(0); df['eq_500km_maxmag']=er.groupby('d').mag.max()
# moon
obs_ill=[];age=[]
for d in idx:
    t=ephem.Date(d.to_pydatetime()+pd.Timedelta(hours=20).to_pytimedelta()) # noon PT ~ 20 UTC
    m=ephem.Moon(t); obs_ill.append(m.phase/100)
    age.append(t-ephem.previous_new_moon(t))
df['moon_illum']=np.round(obs_ill,3); df['moon_age_days']=np.round(age,2)
df['moon_phase']=pd.cut(df.moon_age_days,[-1,1.85,5.5,9.2,12.9,16.6,20.3,24,27.7,30],labels=['New','Waxing Crescent','First Quarter','Waxing Gibbous','Full','Waning Gibbous','Last Quarter','Waning Crescent','New'],ordered=False)
# tides
t=pd.concat([pd.read_csv(f) for f in glob.glob(R+'tide/h_*.csv')]); t.columns=[c.strip() for c in t.columns]
t['d']=pd.to_datetime(t['Date Time']).dt.normalize(); t['TY']=t.TY.str.strip()
df['tide_high_ft']=t[t.TY.isin(['H','HH'])].groupby('d')['Water Level'].max()
df['tide_low_ft']=t[t.TY.isin(['L','LL'])].groupby('d')['Water Level'].min()
df['tide_range_ft']=df.tide_high_ft-df.tide_low_ft

# OMNI solar wind daily
o=pd.read_csv(R+'omni_daily.dat',sep=r'\s+',header=None)
o.index=pd.to_datetime(o[0].astype(str)+'-'+o[1].astype(str),format='%Y-%j')
df['sw_Bz_gsm_nT']=o[16].where(o[16]<999); df['sw_B_nT']=o[8].where(o[8]<999); df['sw_speed_kms']=o[24].where(o[24]<9999); df['sw_density_cc']=o[23].where(o[23]<999)
# Open-Meteo ERA5 reanalysis (not station obs)
a=json.load(open(R+'om_arch.json'))['daily']; a=pd.DataFrame(a); a.index=pd.to_datetime(a.pop('time'))
df['pressure_msl_hPa_era5']=a.pressure_msl_mean; df['surface_pressure_hPa_era5']=a.surface_pressure_mean
df['rh_mean_pct_era5']=a.relative_humidity_2m_mean; df['wind_max_mph_era5']=a.wind_speed_10m_max; df['solar_rad_MJm2_era5']=a.shortwave_radiation_sum
# air quality / UV / pollen (CAMS model)
q=json.load(open(R+'aq.json'))['hourly']; q=pd.DataFrame(q); q.index=pd.to_datetime(q.pop('time'))
dq=q.resample('D').agg({'pm2_5':'mean','us_aqi':'max','uv_index':'max','alder_pollen':'max','grass_pollen':'max'})
df['pm25_ugm3_cams']=dq.pm2_5; df['us_aqi_max_cams']=dq.us_aqi; df['uv_index_max_cams']=dq.uv_index; df['pollen_alder']=dq.alder_pollen; df['pollen_grass']=dq.grass_pollen
df.to_csv('eugene_env_daily_1950_present.csv',float_format='%.3f')
cov={c:dict(first=str(df[c].first_valid_index())[:10],last=str(df[c].last_valid_index())[:10],pct=round(100*df[c].notna().mean(),1)) for c in df.columns}
print(json.dumps(cov,indent=0))
json.dump(cov,open('coverage.json','w'),indent=1)
