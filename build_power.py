"""Add BPA balancing-authority load/generation and regional power-outage history to master CSV. Re-runnable."""
import pandas as pd, numpy as np, glob, os
df=pd.read_csv('eugene_env_daily_1950_present.csv',index_col=0,parse_dates=True)
df=df[[c for c in df.columns if not c.startswith(('bpa_','outage_'))]]; dd={}
# BPA BA load 2000-2013 (BPA file, hourly)
x=pd.read_excel('raw/bpa/BPA_BALoad_2000_2013.xls',sheet_name=None,header=None,skiprows=9)
parts=[]
for k,v in x.items():
    for c0 in ([0,5] if v.shape[1]>5 else [0]):
        t=v[[c0,c0+2]].dropna(); t.columns=['d','mw']; parts.append(t)
h=pd.concat(parts); h['d']=pd.to_datetime(h.d,errors='coerce'); h['mw']=pd.to_numeric(h.mw,errors='coerce')
load_old=h.dropna().groupby('d').mw.mean()
# EIA-930 BPAT hourly (2015-07+)
e=pd.concat([pd.read_csv(f,thousands=',',low_memory=False) for f in sorted(glob.glob('raw/bpa/eia/EIA930_BALANCE_*.csv'))])
e=e[e['Balancing Authority']=='BPAT']; e['d']=pd.to_datetime(e['Data Date'])
def col(name):
    import re
    bases=sorted({re.sub(r' \((Adjusted|Imputed)\)$','',c) for c in e.columns if c.startswith(f'Net Generation (MW) from {name}')})
    parts=[]
    for bse in bases:
        out=pd.Series(np.nan,index=e.index)
        for c in [bse+' (Adjusted)',bse,bse+' (Imputed)']:
            if c in e: out=out.fillna(pd.to_numeric(e[c],errors='coerce'))
        parts.append(out)
    return pd.concat(parts,axis=1).sum(axis=1,min_count=1)
dcol='Demand (MW) (Adjusted)' if 'Demand (MW) (Adjusted)' in e else 'Demand (MW)'
e['load']=pd.to_numeric(e[dcol],errors='coerce'); e['hydro']=col('Hydropower'); e['wind']=col('Wind'); e['solar']=col('Solar')
th=pd.concat([col(n) for n in ['Coal','Natural Gas','Nuclear','Other Fuel Sources','All Petroleum Products']],axis=1); e['thermal']=th.sum(axis=1,min_count=1)
g=e.groupby('d')[['load','hydro','wind','solar','thermal']].mean()
load=pd.concat([load_old,g.load[g.index>load_old.index.max()]])
df['bpa_ba_load_avg_MW']=load.reindex(df.index).round(0)
for k in ['hydro','wind','solar','thermal']: df[f'bpa_{k}_gen_avg_MW']=g[k].reindex(df.index).round(0)
dd['bpa_ba_load_avg_MW']='BPA balancing-authority load, daily mean MW (BPA BALoad file 2000-2013; EIA-930 BPAT demand 2015-07+; gap 2014-mid-2015)'
for k in ['hydro','wind','solar','thermal']: dd[f'bpa_{k}_gen_avg_MW']=f'BPAT net generation from {k} (thermal = coal+gas+nuclear+other), daily mean MW, EIA-930 (2018-07+ fuel detail; earlier mostly blank)'
# EAGLE-I county outages, Oregon counties within ~100 mi of Eugene
C=['Lane','Linn','Benton','Douglas','Lincoln','Marion','Polk','Coos','Deschutes','Yamhill','Jefferson','Klamath']
fs=sorted(glob.glob('raw/pwr/eaglei/or_*.csv'))
if fs:
    o=pd.concat([pd.read_csv(f,header=None,names=['fips','county','state','out','t']) for f in fs])
    o=o[o.county.isin(C)]; o['t']=pd.to_datetime(o.t).dt.tz_localize('UTC').dt.tz_convert('America/Los_Angeles').dt.tz_localize(None); o['d']=o.t.dt.normalize()
    yrs=sorted(int(os.path.basename(f)[3:7]) for f in fs); cover=df.index.year.isin(yrs)&(df.index>='2014-11-01')
    lane=o[o.county=='Lane'].groupby('d').out
    reg=o.groupby(['d','t']).out.sum().groupby('d')
    df['outage_lane_cust_out_peak']=lane.max().reindex(df.index).where(cover).fillna(0).where(cover)
    df['outage_lane_cust_hours']=(lane.sum()*0.25).reindex(df.index).fillna(0).where(cover).round(0)
    df['outage_region_cust_out_peak']=reg.max().reindex(df.index).fillna(0).where(cover)
    dd['outage_lane_cust_out_peak']='Peak customers without power in Lane County that day (ORNL EAGLE-I; utility coverage grew 2014-2018 so early years undercount, all reporting utilities incl. EWEB/Pacific Power/coops; 15-min snapshots)'
    dd['outage_lane_cust_hours']='Approx customer-hours out in Lane County (sum of 15-min snapshots × 0.25 h)'
    dd['outage_region_cust_out_peak']='Peak simultaneous customers out across '+', '.join(C)+' counties (EAGLE-I)'
    print('EAGLE-I years',yrs)
df.to_csv('eugene_env_daily_1950_present.csv',float_format='%.5g')
D=pd.read_csv('column_dictionary.csv'); D=D[~D.column.str.startswith(('bpa_','outage_'))]
for c,desc in dd.items():
    s=df[c]; D.loc[len(D)]=dict(column=c,description=desc,first=str(s.first_valid_index())[:10],last=str(s.last_valid_index())[:10],pct_days_nonblank=round(100*s.notna().mean(),1))
D.to_csv('column_dictionary.csv',index=False)
with pd.ExcelWriter('eugene_env_daily_1950_present.xlsx') as w:
    df.reset_index().to_excel(w,sheet_name='daily_data',index=False); D.to_excel(w,sheet_name='column_dictionary',index=False)
print(D[D.column.isin(dd)].drop(columns='description').to_string()); print(df.shape)
