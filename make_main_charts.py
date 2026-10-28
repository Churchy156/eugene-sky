"""Chart-only redraw of chart1-3 (main 1950-present study) with plain-English labels. Reads the saved outputs
(eugene_env_daily_1950_present.csv, correlations.csv, summary_stats.json) READ-ONLY; does not re-run analyze.py.
Usage: python make_main_charts.py [dir]  (default /workspace/eugene-env)"""
import os, sys, json, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), '/workspace/eugene-sky']
from labels import label, caption
W = sys.argv[1] if len(sys.argv) > 1 else '/workspace/eugene-env'
j = lambda f: os.path.join(W, f)
_h = pd.read_csv(j('eugene_env_daily_1950_present.csv'), nrows=0).columns
df = pd.read_csv(j('eugene_env_daily_1950_present.csv'), index_col=0, parse_dates=True, usecols=[_h[0], 'tmax_F', 'tmin_F', 'sunspot_n', 'Ap'])
R = pd.read_csv(j('correlations.csv')); S = json.load(open(j('summary_stats.json')))
y = df.resample('YE').mean(numeric_only=True)
fig, ax = plt.subplots(3, 1, figsize=(12, 10.5), sharex=True)
ax[0].plot(y.index[:-1], y.tmax_F[:-1], label='Average daily high'); ax[0].plot(y.index[:-1], y.tmin_F[:-1], label='Average daily low'); ax[0].legend(); ax[0].set_ylabel('Temperature (°F)')
ax[0].set_title('Eugene yearly temperatures vs. the Sun and magnetic storms, 1950–2025')
ax[1].plot(y.index[:-1], y.sunspot_n[:-1], c='orange'); ax[1].set_ylabel(label('sunspot_n') + '\n(yearly average)')
ax[2].plot(y.index[:-1], y.Ap[:-1], c='purple'); ax[2].set_ylabel('Magnetic disturbance\n(yearly average)')
caption(fig, "Each point is one year. Eugene has warmed steadily, while sunspots and magnetic storms go up and down every ~11 years, so the Sun's cycle does not explain the warming.")
fig.savefig(j('chart1_annual_temp_vs_solar.png'), dpi=110); plt.close(fig)
drivers = ['Ap', 'kp_max', 'sunspot_n', 'F107_adj', 'sw_speed_kms', 'sw_Bz_gsm_nT', 'flares_M', 'moon_illum', 'tide_range_ft', 'eq_500km_M2.5plus', 'eq_global_M6plus', 'pressure_msl_hPa_era5']
TG = {'tmax_F': 'Daily high\nvs. normal', 'tmin_F': 'Daily low\nvs. normal', 'prcp_in': 'Rain\nvs. normal'}
p = R[R.lag_days == 0].pivot(index='driver', columns='target', values='spearman_r').loc[drivers][list(TG)]
fig, a = plt.subplots(figsize=(9, 8.5)); im = a.imshow(p, cmap='RdBu_r', vmin=-.4, vmax=.4, aspect='auto')
a.set_xticks(range(3), [TG[c] for c in p.columns]); a.set_yticks(range(len(p)), [label(d) + (' (method check)' if d.startswith('pressure') else '') for d in p.index])
for i in range(len(p)):
    for k in range(3): a.text(k, i, f'{p.iloc[i,k]:+.2f}', ha='center', va='center', fontsize=8)
plt.colorbar(im, label='Link strength (−1 to +1)', shrink=.8); a.set_title('Does anything in the sky move Eugene\'s weather the same day? (1950–present)')
caption(fig, "Red = they rise together, blue = one rises as the other falls, white = no link. Only air pressure (the method check) shows a strong link; the Sun, Moon and quakes are all close to zero.")
fig.savefig(j('chart2_correlation_heatmap.png'), dpi=110); plt.close(fig)
mc = pd.Series(S['moon_comp']['wet_frac']).sort_index(key=lambda s: s.astype(int)); pv = S['moon_chi2_p']
fig, a = plt.subplots(figsize=(10, 5))
a.bar(range(8), mc.values * 100, tick_label=['New\nmoon', 'Growing\ncrescent', 'First\nquarter', 'Growing\ngibbous', 'Full\nmoon', 'Shrinking\ngibbous', 'Last\nquarter', 'Shrinking\ncrescent'])
a.set_ylim(30, 45); a.set_ylabel('% of days with rain')
a.set_title(f"Does the Moon's phase change how often it rains in Eugene?  (chance it's a fluke: {pv:.0%})")
caption(fig, "Each bar is the share of days with rain in that moon phase. Bars that are nearly the same height mean the Moon makes little or no difference.")
fig.savefig(j('chart3_rain_by_moon_phase.png'), dpi=110); plt.close(fig)
print('ok')
