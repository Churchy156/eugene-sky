"""Do Pacific Ring of Fire / New Zealand events line up with anything in Eugene?
Outcomes: Lane-area crashes (ODOT 2007-2024, FARS 1975-2024), Oregon quakes within 500 km (M2.5+, 1980+), Lane PM2.5 (EPA, 1999+).
Predictors (Ring of Fire columns from eugene-sky build_ringfire.py) at lags 0,1,2,3,7 days (event day t-L vs outcome day t).
Model: Poisson GLM (counts) or OLS on log(PM2.5); weekday, month, year, holiday fixed effects; weather controls for crashes/PM2.5;
HAC (Newey-West, 7-day) standard errors; Benjamini-Hochberg FDR q-values across all tests. A positive control
(big quake -> more Ring of Fire M5+ aftershocks) checks that the method can find a real lagged link."""
import pandas as pd,numpy as np,statsmodels.api as sm,holidays,warnings,os
from statsmodels.stats.multitest import multipletests
warnings.filterwarnings('ignore'); os.chdir(os.path.dirname(os.path.abspath(__file__)))
e=pd.read_csv('../eugene_env_daily_1950_present.csv',parse_dates=['date']).set_index('date')
I=pd.read_csv('incidents_daily_counts.csv',parse_dates=['date']).set_index('date')
PRED={'RoF quake M6+ day':(e.rof_eq_M6plus>0).astype(float),'RoF quake M7+ day':(e.rof_eq_M7plus>0).astype(float),
      'RoF M5+ count (log)':np.log1p(e.rof_eq_M5plus),'NZ quake M5+ day':(e.nz_eq_M5plus>0).astype(float),
      'NZ M4+ count (log)':np.log1p(e.nz_eq_M4plus),'RoF volcanoes erupting':e.volc_erupting_rof.astype(float),
      'RoF new eruption day':(e.volc_new_eruptions_rof>0).astype(float),'RoF tsunami event day':(e.tsunami_events_rof>0).astype(float)}
OUT={'crashes_all_6cty':(I.crashes_all_6cty,'pois',True),'crashes_injury_fatal_6cty':(I.crashes_injury_fatal_6cty,'pois',True),
     'fatal_crashes_FARS_9cty':(I.fatal_crashes_FARS_9cty,'pois',True),
     'oregon_quakes_500km_M2.5+':(e['eq_500km_M2.5plus'].loc['1980':],'pois',False),
     'lane_pm25_log':(np.log1p(e.pm25_epa_lane_mean),'ols',True)}
W=pd.DataFrame({'w_rain':e.prcp_in,'w_tmin':e.tmin_F,'w_tmax':e.tmax_F,'w_press':e.pressure_msl_hPa_era5})
hol=holidays.US(years=range(1950,2028)); LAGS=[0,1,2,3,7]
def fit(y,x,kind,wx):
    df=pd.DataFrame({'y':y}).join(x.rename('x'))
    if wx: df=df.join(W)
    df=df.dropna()
    binary=set(df.x.unique())<={0,1}
    if len(df)<300 or df.x.std()==0 or (binary and df.x.sum()<10): return None
    X=pd.DataFrame(index=df.index); X['x']=df.x if binary else (df.x-df.x.mean())/df.x.std()
    for nm,v in [('dow',df.index.dayofweek),('m',df.index.month),('y',df.index.year)]:
        X=X.join(pd.get_dummies(v,prefix=nm,drop_first=True,dtype=float).set_index(df.index))
    if wx: X=X.join((df[W.columns]-df[W.columns].mean())/df[W.columns].std())
    X['holiday']=[float(d in hol) for d in df.index]; X=sm.add_constant(X.astype(float))
    if kind=='pois': r=sm.GLM(df.y.astype(float).values,X.values,family=sm.families.Poisson()).fit(cov_type='HAC',cov_kwds={'maxlags':7})
    else: r=sm.OLS(df.y.values,X.values).fit(cov_type='HAC',cov_kwds={'maxlags':7})
    b,se,p=r.params[1],r.bse[1],r.pvalues[1]
    return dict(kind='yes/no' if binary else 'per 1 SD',pct_change=100*(np.exp(b)-1),ci_lo=100*(np.exp(b-1.96*se)-1),ci_hi=100*(np.exp(b+1.96*se)-1),
                p=p,n_days=len(df),n_event_days=int(df.x.sum()) if binary else None,start=str(df.index.min().date()),end=str(df.index.max().date()))
rows=[]
for on,(y,kind,wx) in OUT.items():
    for pn,x in PRED.items():
        for L in LAGS:
            r=fit(y,x.shift(L),kind,wx)
            if r: rows.append(dict(outcome=on,predictor=pn,lag_days=L,**r))
    print(on,len(rows),flush=True)
R=pd.DataFrame(rows); R['q_fdr']=multipletests(R.p,method='fdr_bh')[1]; R['bonferroni_sig']=R.p<0.05/len(R)
# positive control: RoF M7+ day -> RoF M5+ count L days later (aftershocks); not part of the FDR family
pc=[]
for L in [1,2,3,7]:
    r=fit(e.rof_eq_M5plus.loc['1973':],PRED['RoF quake M7+ day'].shift(L),'pois',False); pc.append(dict(outcome='RoF M5+ count (positive control)',predictor='RoF quake M7+ day',lag_days=L,**r))
PC=pd.DataFrame(pc)
R=R.round(4).sort_values('p'); R.to_csv('ringfire_correlations.csv',index=False); PC.round(4).to_csv('ringfire_positive_control.csv',index=False)
pd.set_option('display.width',250)
print(len(R),'tests; q<0.05:',(R.q_fdr<0.05).sum(),'; p<0.05:',(R.p<0.05).sum(),'(expected by chance ~',round(0.05*len(R)),')')
print(R.head(15)[['outcome','predictor','lag_days','kind','pct_change','ci_lo','ci_hi','p','q_fdr','n_days','n_event_days']].to_string())
print('\nPositive control:\n',PC[['lag_days','pct_change','ci_lo','ci_hi','p']].round(4).to_string())
