"""Adds free sources: EPA AQS daily AQI (Lane), CDC NWSS wastewater (Lane), CDC RESP-NET hospitalization rates (OR),
FBI CDE monthly crime (EPD/SPD/LCSO), Treasury avg interest rate, CISA KEV daily additions. Merges into master CSV/XLSX."""
import pandas as pd, numpy as np, requests, io, zipfile, os, json, time
H=os.path.dirname(os.path.abspath(__file__)); R=os.environ.get('RAWDIR',f'{H}/raw/new'); os.makedirs(R,exist_ok=True)
K=os.environ.get('NASA_API_KEY') or open(f'{H}/.nasa_key').read().strip()
M=os.environ.get('MASTER',f'{H}/eugene_env_daily_1950_present.csv'); CI='MASTER' in os.environ
df=pd.read_csv(M,parse_dates=['date']).set_index('date'); idx=df.index
DP=os.environ.get('DICT',f'{H}/column_dictionary.csv'); D=pd.read_csv(DP); dd={}
def get(u,**kw):
    for a in range(4):
        try:
            r=requests.get(u,timeout=120,**kw)
            if r.ok: return r
        except Exception as e: pass
        time.sleep(3*(a+1))
    raise RuntimeError(u)
new={}
# 1 EPA AQS daily AQI by county (Lane = 41/039), 1980+
try:
    parts=[]
    for y in range(int(os.environ.get('AQS_FROM',1980)),pd.Timestamp.now().year+1):
        f=f'{R}/aqi_{y}.csv'
        if not os.path.exists(f) or y>=pd.Timestamp.now().year-1:
            try:
                z=zipfile.ZipFile(io.BytesIO(get(f'https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_{y}.zip').content))
                a=pd.read_csv(z.open(z.namelist()[0])); a=a[(a['State Code']==41)&(a['County Code']==39)]; a.to_csv(f,index=False)
            except Exception as e: print('aqs',y,e); continue
        parts.append(pd.read_csv(f))
    a=pd.concat(parts); a['Date']=pd.to_datetime(a['Date']); a=a.set_index('Date')
    new['aqi_epa_aqs_lane']=a['AQI']; new['aqi_epa_aqs_lane_pm25_driver']=(a['Defining Parameter']=='PM2.5').astype(float)
    dd['aqi_epa_aqs_lane']='EPA AQS official daily AQI, Lane County (max over monitors/pollutants; EPA AirData daily_aqi_by_county). Pre-generated files lag ~6 months; recent days blank until EPA certifies'
    dd['aqi_epa_aqs_lane_pm25_driver']='1 if PM2.5 was the AQI-defining pollutant that day (else ozone/other), EPA AQS'
except Exception as e: print('AQS fail',e)
# 2 CDC NWSS wastewater SARS-CoV-2, Lane County sites
try:
    w=pd.DataFrame(get('https://data.cdc.gov/resource/j9g8-acpt.json',params={'county_fips':'41039','pcr_target':'sars-cov-2','$limit':50000,'$select':'sample_collect_date,pcr_target_avg_conc_lin,site'}).json())
    w['d']=pd.to_datetime(w.sample_collect_date); w['c']=pd.to_numeric(w.pcr_target_avg_conc_lin,errors='coerce')
    s=w.groupby('d').c.mean(); s=np.log10(s.clip(lower=1))
    new['ww_sarscov2_log10_lane']=s.reindex(idx).ffill(limit=6).where(idx>=s.index.min())
    dd['ww_sarscov2_log10_lane']='log10 SARS-CoV-2 RNA concentration (copies/L, mean of Lane County NWSS sites), CDC NWSS; carried forward up to 6 days between samples'
except Exception as e: print('NWSS fail',e)
# 3 CDC RESP-NET weekly hospitalization rates, Oregon
try:
    r=pd.DataFrame(get('https://data.cdc.gov/resource/kvib-3txy.json',params={'state':'Oregon','data_type':'Weekly Rate','age_category':'Overall','race':'All','sex':'All','$limit':50000}).json())
    r['d']=pd.to_datetime(r.date); r['v']=pd.to_numeric(r.estimate,errors='coerce')
    for net,c in [('COVID-NET','resp_hosp_covid_rate_or'),('RSV-NET','resp_hosp_rsv_rate_or'),('FluSurv-NET','resp_hosp_flu_rate_or')]:
        s=r[r.surveillance_network==net].groupby('d').v.mean()
        s.index=s.index-pd.Timedelta(days=6)  # week ending Sat -> fill Sun..Sat
        new[c]=s.reindex(idx).ffill(limit=6).where((idx>=s.index.min())&(idx<=s.index.max()+pd.Timedelta(days=6)))
        dd[c]=f'CDC RESP-NET {net} weekly hospitalization rate per 100k, Oregon (Portland-area catchment); weekly value repeated for each day of week; seasonal (off-season weeks may be blank)'
except Exception as e: print('RESPNET fail',e)
# 4 FBI Crime Data Explorer monthly actuals
try:
    for ori,tag,name in [('OR0200200','epd','Eugene Police Department'),('OR0200600','spd','Springfield Police Department'),('OR0200000','lcso',"Lane County Sheriff's Office")]:
        for code,lab in [('V','violent'),('P','property')]:
            f=f'{R}/fbi_{ori}_{code}.json'
            if not os.path.exists(f) or time.time()-os.path.getmtime(f)>30*86400:
                j=get(f'https://api.usa.gov/crime/fbi/cde/summarized/agency/{ori}/{code}',params={'from':'01-1985','to':pd.Timestamp.now().strftime('12-%Y'),'API_KEY':K}).json(); json.dump(j,open(f,'w'))
            j=json.load(open(f)); act=j['offenses']['actuals']; key=[k for k in act if 'Offenses' in k and 'Clear' not in k and name.split()[0] in k]
            if not key: print('fbi no key',ori,code,list(act)); continue
            s=pd.Series(act[key[0]]); s.index=pd.to_datetime(s.index,format='%m-%Y'); s=s.sort_index().astype(float)
            m=idx.to_period('M').to_timestamp(); c=f'crime_{tag}_{lab}_month'
            new[c]=pd.Series(s.reindex(m).values,index=idx)
            dd[c]=f'FBI Crime Data Explorer: {lab} offenses reported by {name} in that calendar month (same value on every day of the month; agencies may under-report some years)'
except Exception as e: print('FBI fail',e)
# 5 Treasury average interest rate on total marketable debt (monthly)
try:
    t=pd.DataFrame(get('https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates',params={'filter':'security_desc:eq:Total Marketable','page[size]':1000,'sort':'record_date'}).json()['data'])
    s=pd.Series(pd.to_numeric(t.avg_interest_rate_amt).values,index=pd.to_datetime(t.record_date))
    new['fin_ust_avg_rate_marketable_pct']=s.reindex(idx).ffill(limit=40).where(idx>=s.index.min()); 
    dd['fin_ust_avg_rate_marketable_pct']='US Treasury average interest rate on total marketable debt %, month-end, carried forward (Treasury FiscalData)'
except Exception as e: print('Treasury fail',e)
# 6 CISA KEV additions per day
try:
    k=pd.DataFrame(get('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json',headers={'User-Agent':'Mozilla/5.0'}).json()['vulnerabilities'])
    s=pd.to_datetime(k.dateAdded).value_counts()
    new['cyber_kev_added']=s.reindex(idx).fillna(0).where(idx>=pd.Timestamp('2021-11-03'))
    dd['cyber_kev_added']='Number of CVEs added to CISA Known Exploited Vulnerabilities catalog that day (catalog began 2021-11-03)'
except Exception as e: print('KEV fail',e)
N=pd.DataFrame(new).reindex(idx)
if CI:  # upsert: keep existing history, overwrite with fresh non-null values
    for c in N:
        if c not in df: df[c]=np.nan
        v=N[c].dropna(); df.loc[v.index,c]=v.values
else: df=df.drop(columns=[c for c in N if c in df]).join(N)
for c in N:
    s=df[c].dropna(); D=D[D.column!=c]
    D=pd.concat([D,pd.DataFrame([{'column':c,'description':dd.get(c,''),'first':s.index.min().date() if len(s) else '','last':s.index.max().date() if len(s) else '','pct_days_nonblank':round(100*len(s)/len(df),1)}])])
    print(c,len(s),D.iloc[-1]['first'],D.iloc[-1]['last'])
df.reset_index().to_csv(M,index=False); D.to_csv(DP,index=False)
if not CI:
 with pd.ExcelWriter(M.replace('.csv','.xlsx')) as w:
  df.reset_index().to_excel(w,sheet_name='daily_data',index=False); D.to_excel(w,sheet_name='column_dictionary',index=False)
