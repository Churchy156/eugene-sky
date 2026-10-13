import pandas as pd, numpy as np, json, pickle
import statsmodels.api as sm, statsmodels.formula.api as smf
from scipy import stats
df=pd.read_csv('eugene_env_daily_1950_present.csv',index_col=0,parse_dates=True)
inc=pd.read_csv('incidents/incidents_daily_counts.csv',index_col=0,parse_dates=True)
d=df.join(inc[['crashes_all_6cty','crashes_lane','crashes_injury_fatal_6cty']])
d=d[d.crashes_all_6cty.notna()].copy()
print('crash data',d.index.min().date(),d.index.max().date(),len(d))
d['y']=d.crashes_all_6cty; d['dow']=d.index.dayofweek.astype(str); d['month']=d.index.month.astype(str); d['t']=(d.index.year-2015)/10
d['wet']=(d.prcp_in>=0.01).astype(int); d['rain_in']=d.prcp_in.clip(upper=2).fillna(0)
dry=(d.prcp_in<0.01).astype(int); d['first_rain']=((d.wet==1)&(dry.shift(1).rolling(7).sum()==7)).astype(int)
d['freeze']=(d.tmin_F<=32).astype(int); d['snow']=(d.snow_in.fillna(0)>0).astype(int)
d['hot']=(d.tmax_F>=95).astype(int)
for c in ['nws_alerts_any','nws_alerts_winter','fire_smoke_day','ev_ducks_fb_home','ev_ducks_mbb_home']: d[c]=d[c].fillna(0)
d['logQ']=np.log(d.river_willamette_harrisburg_cfs)
d['covid']=((d.index>='2020-03-16')&(d.index<='2021-06-30')).astype(int)
d['hol']=d.ev_us_holiday
d['log_outage_lane']=np.log1p(d.outage_lane_cust_out_peak)
d['bpa_load_GW']=d.bpa_ba_load_avg_MW/1000
# univariate associations (rate ratio via Poisson with dow+month+trend control)
d['lvl']=np.log(d.y.shift(1).rolling(365,min_periods=180).mean()); d=d.dropna(subset=['lvl'])
base='y ~ C(dow)+C(month)+covid'
vars_=['wet','rain_in','first_rain','freeze','snow','hot','daylight_hours','sunset_hour_local','dst_week_after','dst_in_effect','hol','ev_ducks_fb_home','ev_ducks_mbb_home','ev_uo_in_session_approx','ev_4j_break_approx','logQ','fire_smoke_day','nws_alerts_any','nws_alerts_winter','kp_max','moon_illum','pressure_msl_hPa_era5','log_outage_lane','bpa_load_GW','nws_alerts_flood','nws_alerts_wind','nws_alerts_heat']
rows=[]
for v in vars_:
    m=smf.glm(base+'+'+v,d.dropna(subset=[v]),offset=d.dropna(subset=[v]).lvl,family=sm.families.NegativeBinomial(alpha=0.05)).fit()
    rows.append(dict(variable=v,rate_ratio_per_unit=round(np.exp(m.params[v]),4),ci_low=round(np.exp(m.conf_int().loc[v,0]),4),ci_high=round(np.exp(m.conf_int().loc[v,1]),4),p=m.pvalues[v]))
U=pd.DataFrame(rows).sort_values('p'); U['p_bonferroni']=(U.p*len(U)).clip(upper=1); U.round(5).to_csv('crash_correlations_v2.csv',index=False); print(U.round(4).to_string())
# model: train <=2018, test 2019-2024 (2020-21 covid flagged)
fx='+wet+rain_in+first_rain+freeze+snow+hot+sunset_hour_local+dst_week_after+hol+ev_ducks_fb_home+ev_4j_break_approx+ev_uo_in_session_approx+fire_smoke_day+nws_alerts_winter'
tr=d[d.index.year<=2018]; te=d[d.index.year>=2019]
fam=sm.families.NegativeBinomial(alpha=0.05)
m0=smf.glm(base,tr,offset=tr.lvl,family=fam).fit(); m1=smf.glm(base+fx,tr,offset=tr.lvl,family=fam).fit()
def ev(m):
    p=m.predict(te,offset=te.lvl); return dict(MAE=round(np.mean(abs(te.y-p)),3),RMSE=round(np.sqrt(np.mean((te.y-p)**2)),3),r=round(np.corrcoef(te.y,p)[0,1],3),mean_obs=round(te.y.mean(),2),mean_pred=round(p.mean(),2))
res=dict(train='2008-2018 (offset = trailing 365-day mean, so 2007 used for warm-up)',test='2019-2024',baseline_calendar_only=ev(m0),full_weather_calendar=ev(m1))
# naive: same dow mean over train
res['naive_trailing365_mean']=dict(MAE=round(np.mean(abs(te.y-np.exp(te.lvl))),3))
# high-risk-day skill: top-decile predicted vs actual top decile
p1=m1.predict(te,offset=te.lvl); hi=te.y>=te.y.quantile(.9); ph=p1>=p1.quantile(.9)
res['top10pct_day_precision']=round((hi&ph).sum()/ph.sum(),3); res['top10pct_day_recall']=round((hi&ph).sum()/hi.sum(),3)
# final fit on all years for live use
mf=smf.glm(base+fx,d,offset=d.lvl,family=fam).fit()
res['coefs_rate_ratios']={k:round(float(np.exp(v)),3) for k,v in mf.params.items() if not k.startswith(('C(','Intercept'))}
json.dump(res,open('crash_model_results.json','w'),indent=1); print(json.dumps(res,indent=1))
mf.remove_data(); pickle.dump(mf,open('crash_model.pkl','wb'))
