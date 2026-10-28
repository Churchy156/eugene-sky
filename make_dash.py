import pandas as pd, json, plotly, os, numpy as np
df=pd.read_csv('data/eugene_env_daily.csv.gz',index_col=0,parse_dates=True)
inc=pd.read_csv('data/incidents_daily_counts.csv',index_col=0,parse_dates=True)
cols={'tmax_F':1,'tmin_F':1,'prcp_in':2,'pressure_msl_hPa_era5':1,'kp_max':2,'Ap':0,'sunspot_n':0,'sw_speed_kms':0,'moon_illum':2,'tide_range_ft':2,'eq_500km_M2.5plus':0,'eq_500km_maxmag':1,'fin_sp500_close':1,'fin_gold_usd_oz':1,'fin_dxy':2,'daylight_hours':2,'sunset_hour_local':2,'river_willamette_harrisburg_cfs':0,'river_mckenzie_vida_cfs':0,'nws_alerts_any':0,'pm25_epa_lane_mean':1,'pm25_cams_dummy':0,'ev_ducks_fb_home':0,'ev_us_holiday':0,'bpa_ba_load_avg_MW':0,'bpa_hydro_gen_avg_MW':0,'bpa_wind_gen_avg_MW':0,'outage_lane_cust_out_peak':0,'outage_region_cust_out_peak':0}
cols.pop('pm25_cams_dummy'); cols['pm25_ugm3_cams']=1
for _c in ('games_within_100mi','major_home_game','est_attendance_100mi'):
    if _c in df: cols[_c]=0
d=df[list(cols)].join(inc[['crashes_all_6cty','crashes_lane','fatal_crashes_FARS_9cty']],how='left')
cols.update({'crashes_all_6cty':0,'crashes_lane':0,'fatal_crashes_FARS_9cty':0})
data={'start':str(d.index[0].date()),'n':len(d)}
for c,r in cols.items():
    v=d[c].round(r)
    data[c]=[None if pd.isna(x) else (int(x) if r==0 else float(x)) for x in v]
js=open(os.path.join(os.path.dirname(plotly.__file__),'package_data','plotly.min.js')).read()
html=open('dash_template.html').read().replace('/*PLOTLY*/',js).replace('/*DATA*/','const D='+json.dumps(data,separators=(',',':'))+';').replace('/*LABELS*/','const EXP='+json.dumps({k:v[1] for k,v in __import__('labels').L.items() if v[1]},ensure_ascii=False)+';')
import sys; os.makedirs('site',exist_ok=True); open(sys.argv[1] if len(sys.argv)>1 else 'site/index.html','w').write(html); print(os.path.getsize(sys.argv[1] if len(sys.argv)>1 else 'site/index.html')/1e6,'MB')
