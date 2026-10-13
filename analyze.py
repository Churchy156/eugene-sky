import pandas as pd, numpy as np, json
from scipy import stats
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
df=pd.read_csv('eugene_env_daily_1950_present.csv',index_col=0,parse_dates=True).drop(columns=['pollen_alder','pollen_grass'],errors='ignore')
df.to_csv('eugene_env_daily_1950_present.csv',float_format='%.3f')
doy=df.index.dayofyear
def anom(s):
    clim=s.groupby(doy).mean().rolling(31,center=True,min_periods=1).mean()
    return s-clim.reindex(doy).values
A=pd.DataFrame(index=df.index)
for c in ['tmax_F','tmin_F']: A[c]=anom(df[c])
A['prcp_in']=anom(df.prcp_in); A['wet']=(df.prcp_in>=0.01).astype(float).where(df.prcp_in.notna())
drivers=['Ap','kp_max','sunspot_n','F107_adj','sw_speed_kms','sw_Bz_gsm_nT','flares_M','moon_illum','tide_range_ft','eq_500km_M2.5plus','eq_global_M6plus','pressure_msl_hPa_era5']
rng=np.random.default_rng(0); out=[]
for d in drivers:
    x=df[d]
    for t in ['tmax_F','tmin_F','prcp_in']:
        for lag in [0,1,3,7,14,27]:
            xs=x.shift(lag); m=xs.notna()&A[t].notna()
            xv,yv=xs[m].values,A[t][m].values
            r=stats.spearmanr(xv,yv)[0]
            # circular-shift null (keeps autocorrelation): 200 random shifts >= 1yr
            null=[stats.spearmanr(np.roll(xv,rng.integers(365,len(xv)-365)),yv)[0] for _ in range(200)] if lag in (0,7) else None
            p=(np.mean(np.abs(null)>=abs(r)) if null else np.nan)
            out.append(dict(driver=d,target=t,lag_days=lag,n=int(m.sum()),spearman_r=round(r,4),r2_pct=round(100*r*r,3),p_circshift=p))
R=pd.DataFrame(out); R.to_csv('correlations.csv',index=False)
# annual solar vs temp
y=df.resample('YE').mean(numeric_only=True); ya=y[['tmax_F','tmin_F','prcp_in','sunspot_n','Ap']].dropna(); ya=ya[ya.index.year<2026]
ann={c:stats.pearsonr(ya[c],ya[t]) for c in ['sunspot_n','Ap'] for t in ['tmax_F','prcp_in']} 
ann={f'{c}':(round(v[0],3),round(v[1],3)) for c,v in zip([f'{a}~{b}' for a in ['sunspot_n','Ap'] for b in ['tmax_F','prcp_in']],ann.values())}
# detrended annual
yd=ya.apply(lambda s: s-np.polyval(np.polyfit(range(len(s)),s,1),range(len(s))))
ann['detrended sunspot~tmax']=tuple(round(v,3) for v in stats.pearsonr(yd.sunspot_n,yd.tmax_F))
# moon phase composite
ph=pd.cut(df.moon_age_days,8,labels=False)
mc=pd.DataFrame({'wet_frac':A.wet.groupby(ph).mean(),'mean_prcp':df.prcp_in.groupby(ph).mean(),'tmax_anom':A.tmax_F.groupby(ph).mean()})
ct=pd.crosstab(ph,A.wet); chi=stats.chi2_contingency(ct)
# geomagnetic storm days composite
st=df.kp_max>=7; comp={L:round(A.tmax_F.shift(-L)[st].mean(),2) for L in range(0,8)}
trend=np.polyfit(np.arange(len(ya)),ya.tmax_F,1)[0]*10
res=dict(annual=ann,moon_chi2_p=chi[1],moon_comp=mc.round(4).to_dict(),storm_days=int(st.sum()),storm_tmax_anom_by_lag=comp,tmax_trend_F_per_decade=round(trend,3),tmin_trend=round(np.polyfit(np.arange(len(ya)),ya.tmin_F,1)[0]*10,3))
json.dump(res,open('summary_stats.json','w'),indent=1,default=str); print(json.dumps(res,indent=1,default=str))
print(R[R.lag_days.isin([0,7])].sort_values('r2_pct',ascending=False).head(25).to_string())
# charts
fig,ax=plt.subplots(3,1,figsize=(12,10),sharex=True)
ax[0].plot(y.index[:-1],y.tmax_F[:-1],label='mean Tmax'); ax[0].plot(y.index[:-1],y.tmin_F[:-1],label='mean Tmin'); ax[0].legend(); ax[0].set_ylabel('°F'); ax[0].set_title('Eugene annual temps vs solar & geomagnetic activity, 1950–2025')
ax[1].plot(y.index[:-1],y.sunspot_n[:-1],c='orange'); ax[1].set_ylabel('Sunspot #')
ax[2].plot(y.index[:-1],y.Ap[:-1],c='purple'); ax[2].set_ylabel('Ap index'); plt.tight_layout(); plt.savefig('chart1_annual_temp_vs_solar.png',dpi=110)
p=R[R.lag_days==0].pivot(index='driver',columns='target',values='spearman_r').loc[drivers]
fig,a=plt.subplots(figsize=(7,7)); im=a.imshow(p,cmap='RdBu_r',vmin=-.4,vmax=.4); a.set_xticks(range(3),p.columns); a.set_yticks(range(len(p)),p.index)
for i in range(len(p)):
    for j in range(3): a.text(j,i,f'{p.iloc[i,j]:.3f}',ha='center',fontsize=8)
plt.colorbar(im); a.set_title('Same-day Spearman r vs Eugene weather anomalies\n(pressure = positive control)'); plt.tight_layout(); plt.savefig('chart2_correlation_heatmap.png',dpi=110)
fig,a=plt.subplots(figsize=(9,4)); a.bar(range(8),mc.wet_frac,tick_label=['New','WxC','1stQ','WxG','Full','WnG','LastQ','WnC']); a.set_ylim(.3,.45); a.set_ylabel('Fraction of days with rain'); a.set_title(f'Eugene rain frequency by moon phase (chi² p={chi[1]:.3f})'); plt.tight_layout(); plt.savefig('chart3_rain_by_moon_phase.png',dpi=110)
