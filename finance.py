import pandas as pd, numpy as np, json
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
F='raw/fin/'
df=pd.read_csv('eugene_env_daily_1950_present.csv',index_col=0,parse_dates=True)
df=df[[c for c in df.columns if not c.startswith(('fin_','ret_'))]]
def fred(s):
    x=pd.read_csv(F+s+'.csv'); x.index=pd.to_datetime(x.iloc[:,0]); return pd.to_numeric(x.iloc[:,1],errors='coerce')
def yh(f):
    r=json.load(open(F+f))['chart']['result'][0]
    d=pd.to_datetime(r['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
    s=pd.Series(r['indicators']['quote'][0]['close'],index=d,dtype=float); return s[~s.index.duplicated(keep='last')]
fin={'fin_sp500_close':(yh('y_GSPC.json'),'S&P 500 index close','Yahoo ^GSPC'),
 'fin_dow_close':(yh('y_DJI.json'),'Dow Jones Industrial Avg close','Yahoo ^DJI'),
 'fin_nasdaq_comp':(fred('NASDAQCOM'),'Nasdaq Composite close','FRED NASDAQCOM'),
 'fin_gold_usd_oz':(yh('y_GCF.json'),'Gold front-month futures settle, USD/oz','Yahoo GC=F (COMEX futures, not spot)'),
 'fin_fed_funds_pct':(fred('DFF'),'Effective federal funds rate, % (published 7 days/wk)','FRED DFF'),
 'fin_ust10y_pct':(fred('DGS10'),'10-yr Treasury constant-maturity yield, %','FRED DGS10'),
 'fin_dxy':(yh('y_DXYNYB.json'),'ICE US Dollar Index (DXY)','Yahoo DX-Y.NYB'),
 'fin_usd_broad_idx':(fred('DTWEXBGS'),'Fed nominal broad dollar index (Jan2006=100)','FRED DTWEXBGS'),
 'fin_usd_major_idx_old':(fred('DTWEXM'),'Fed major-currencies dollar index (discontinued 2019)','FRED DTWEXM'),
 'fin_usd_per_eur':(fred('DEXUSEU'),'USD per 1 EUR','FRED DEXUSEU'),
 'fin_jpy_per_usd':(fred('DEXJPUS'),'JPY per 1 USD','FRED DEXJPUS'),
 'fin_usd_per_gbp':(fred('DEXUSUK'),'USD per 1 GBP','FRED DEXUSUK'),
 'fin_cny_per_usd':(fred('DEXCHUS'),'CNY per 1 USD','FRED DEXCHUS'),
 'fin_cad_per_usd':(fred('DEXCAUS'),'CAD per 1 USD','FRED DEXCAUS'),
 'fin_mxn_per_usd':(fred('DEXMXUS'),'MXN per 1 USD','FRED DEXMXUS')}
cov={}
for c,(s,desc,src) in fin.items():
    s=s[(s.index>='1950-01-01')&(s.index<='2026-10-12')].dropna()
    df[c]=s.reindex(df.index)   # no fill: closed days stay blank
    cov[c]=dict(first=str(s.index.min().date()),last=str(s.index.max().date()),n_days=len(s),source=src,desc=desc)
# returns between consecutive valid observations (no fill); rates as changes in pct points
ret={}
for c in fin:
    s=df[c].dropna()
    r=(s.diff() if 'pct' in c else np.log(s).diff())
    if 'pct' in c and c=='fin_fed_funds_pct': pass
    ret['ret_'+c[4:]]=r
for k,r in ret.items(): df[k]=r.reindex(df.index)
df.to_csv('eugene_env_daily_1950_present.csv',float_format='%.5g')
# analysis
doy=df.index.dayofyear
anom=lambda s: s-s.groupby(doy).transform('mean')
drv=pd.DataFrame({'Ap':df.Ap,'kp_max':df.kp_max,'sunspot_n':df.sunspot_n,'sw_speed':df.sw_speed_kms,'sw_Bz':df.sw_Bz_gsm_nT,'flares_M':df.flares_M,
 'moon_illum':df.moon_illum,'eq_500km':df['eq_500km_M2.5plus'],'eq_global_M6':df.eq_global_M6plus,'eugene_tmax_anom':anom(df.tmax_F),'eugene_prcp':df.prcp_in,'pressure_msl':df.pressure_msl_hPa_era5})
targets=['ret_sp500_close','ret_dow_close','ret_nasdaq_comp','ret_gold_usd_oz','ret_ust10y_pct','ret_dxy','ret_usd_per_eur','ret_jpy_per_usd','ret_usd_per_gbp','ret_cny_per_usd','ret_cad_per_usd','ret_mxn_per_usd']
rng=np.random.default_rng(1); out=[]
for t in targets:
    for d in drv:
        for lag in [0,1,5]:
            x=drv[d].shift(lag); m=x.notna()&df[t].notna()
            if m.sum()<500: continue
            xv,yv=x[m].values,df[t][m].values; r=stats.spearmanr(xv,yv)[0]
            null=np.array([stats.spearmanr(np.roll(xv,rng.integers(250,len(xv)-250)),yv)[0] for _ in range(300)])
            out.append(dict(target=t,driver=d,lag=lag,n=int(m.sum()),r=r,p=(1+np.sum(np.abs(null)>=abs(r)))/301))
R=pd.DataFrame(out); R=R.sort_values('p'); m=len(R)
R['p_BH_fdr']=np.minimum.accumulate((R.p*m/np.arange(1,m+1))[::-1])[::-1].clip(upper=1)
R.round(5).to_csv('finance_correlations.csv',index=False)
print('tests',m,'min p',R.p.min(),'n p<0.05',(R.p<0.05).sum(),'expected by chance',round(.05*m,1),'n FDR<0.1',(R.p_BH_fdr<0.1).sum())
print(R.head(15).round(4).to_string())
# storm effect on S&P: mean return over 6 trading days after Kp>=7 storms vs others
sp=df.ret_sp500_close.dropna(); storm=(df.kp_max>=7).reindex(sp.index).fillna(False)
after=storm.rolling(6,min_periods=1).max().astype(bool)
tt=stats.ttest_ind(sp[after],sp[~after],equal_var=False)
res=dict(sp_after_storm_mean_bp=round(sp[after].mean()*1e4,2),sp_other_mean_bp=round(sp[~after].mean()*1e4,2),n_after=int(after.sum()),p=round(tt.pvalue,3))
mph=pd.cut(df.moon_age_days.reindex(sp.index),8,labels=['New','WxC','1stQ','WxG','Full','WnG','LastQ','WnC'])
mm=sp.groupby(mph,observed=False).mean()*1e4; kw=stats.kruskal(*[sp[mph==k] for k in mm.index])
res['sp_by_moon_bp']=mm.round(2).to_dict(); res['moon_kruskal_p']=round(kw.pvalue,3); print(res)
json.dump(dict(coverage=cov,storm_moon=res,n_tests=m),open('finance_summary.json','w'),indent=1)
# chart
fig,a=plt.subplots(1,2,figsize=(13,4.5))
a[0].bar(mm.index,mm.values); a[0].axhline(sp.mean()*1e4,c='k',ls='--',lw=1); a[0].set_title(f'S&P 500 avg daily return by moon phase, 1950–2026\n(Kruskal p={kw.pvalue:.2f})'); a[0].set_ylabel('basis points')
a[1].hist(R.p,bins=20,range=(0,1),edgecolor='k'); a[1].axhline(m/20,c='r',ls='--',label='expected if no real effects'); a[1].legend(); a[1].set_title(f'p-values of all {m} finance-vs-nature tests'); a[1].set_xlabel('p (circular-shift test)')
plt.tight_layout(); plt.savefig('chart4_finance_vs_nature.png',dpi=110)
# Excel + dictionary
dic=json.load(open('coverage.json')); dd=[]
basic={'tmax_F':'Daily max temp °F, Eugene Airport USW00024221 (NOAA GHCN-D)','tmin_F':'Daily min temp °F, GHCN-D','prcp_in':'Precip inches, GHCN-D','snow_in':'Snowfall inches, GHCN-D','wind_avg_mph':'Avg wind mph, GHCN-D',
'kp_max':'Max 3-hr Kp (GFZ Potsdam)','kp_sum':'Sum of 8 Kp values','Ap':'Daily Ap (GFZ)','F107_adj':'F10.7 solar radio flux, adjusted (sfu)','sunspot_n':'Daily total sunspot number (SILSO)',
'flares_C':'GOES C-class flare count (NOAA NGDC), 1975-09..2016','flares_M':'GOES M-class flare count','flares_X':'GOES X-class flare count',
'eq_global_M6plus':'Count of global M6+ quakes (USGS, UTC day)','eq_global_maxmag':'Max global M6+ magnitude (blank=none)','eq_500km_M2.5plus':'Count M2.5+ within 500 km of Eugene (USGS, PT day)','eq_500km_maxmag':'Max mag of those (blank=none)',
'moon_illum':'Moon illuminated fraction at ~noon PT (ephem)','moon_age_days':'Days since new moon','moon_phase':'Named phase',
'tide_high_ft':'Highest observed high water, ft MLLW, NOAA 9435380 South Beach','tide_low_ft':'Lowest observed low water, ft MLLW','tide_range_ft':'High minus low',
'sw_Bz_gsm_nT':'Daily mean IMF Bz GSM nT (NASA OMNI)','sw_B_nT':'Daily mean |B| nT (OMNI)','sw_speed_kms':'Solar wind speed km/s (OMNI)','sw_density_cc':'Proton density /cc (OMNI)',
'pressure_msl_hPa_era5':'Mean sea-level pressure hPa (ERA5 reanalysis via Open-Meteo)','surface_pressure_hPa_era5':'Mean surface pressure hPa (ERA5)','rh_mean_pct_era5':'Mean relative humidity % (ERA5)','wind_max_mph_era5':'Max 10 m wind mph (ERA5)','solar_rad_MJm2_era5':'Shortwave radiation sum MJ/m² (ERA5)',
'pm25_ugm3_cams':'Daily mean PM2.5 µg/m³ (CAMS model via Open-Meteo)','us_aqi_max_cams':'Daily max US AQI (CAMS model)','uv_index_max_cams':'Daily max UV index (CAMS model)'}
for c in df.columns:
    s=df[c]; fv=s.first_valid_index(); lv=s.last_valid_index()
    if c in cov: desc=cov[c]['desc']+' — '+cov[c]['source']+'. Blank on market-closed days.'
    elif c.startswith('ret_'): desc=('Daily change in percentage points' if 'pct' in c else 'Log return')+' vs previous available observation of fin_'+c[4:]
    else: desc=basic.get(c,'')
    dd.append(dict(column=c,description=desc,first=str(fv)[:10],last=str(lv)[:10],pct_days_nonblank=round(100*s.notna().mean(),1)))
D=pd.DataFrame(dd); D.to_csv('column_dictionary.csv',index=False)
with pd.ExcelWriter('eugene_env_daily_1950_present.xlsx') as w:
    df.reset_index().to_excel(w,'daily_data',index=False); D.to_excel(w,'column_dictionary',index=False)
print(D[D.column.str.startswith('fin_')].to_string())
