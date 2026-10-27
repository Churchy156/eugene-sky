"""PNG charts (reports/schumann/*.png) + interactive page (site/schumann.html) for the Schumann resonance study.
All SR values are DIGITIZED ESTIMATES read off published spectrogram/line charts."""
import os, json, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
D, R, S = os.path.join(B, 'data'), os.path.join(B, 'reports', 'schumann'), os.path.join(B, 'site')
EST = 'digitized estimate'
Dd = pd.read_csv(os.path.join(D, 'schumann_daily.csv.gz'), index_col=0, parse_dates=True)
C = pd.read_csv(os.path.join(R, 'schumann_correlations.csv'))
DI = pd.read_csv(os.path.join(R, 'schumann_diurnal.csv'))
EP = pd.read_csv(os.path.join(R, 'schumann_epoch.csv'))
SK = pd.read_csv(os.path.join(R, 'schumann_forecast_skill.csv'))
SG = pd.read_csv(os.path.join(R, 'schumann_forecast_significance.csv'))
P = pd.read_csv(os.path.join(R, 'schumann_forecast_test_predictions.csv.gz'), parse_dates=['date']).set_index('date').asfreq('D')
LBL = {'ver_f1_ns': 'Vernadsky f1 NS (Hz)', 'ver_f1_ew': 'Vernadsky f1 EW (Hz)', 'ver_a1_ns': 'Vernadsky A1 NS (rel dB)',
       'ver_a1_ew': 'Vernadsky A1 EW (rel dB)', 'sou_f1_ns': 'SOUSY Svalbard f1 NS (Hz)', 'tomsk_F1': 'Tomsk F1 (Hz)', 'tomsk_A1': 'Tomsk A1 (chart units)'}
figs = []

# 1 time series + solar overlay (monthly means)
M = Dd.resample('MS').mean()
fig, ax = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
for c, col in [('ver_f1_ns', 'C0'), ('ver_f1_ew', 'C1'), ('sou_f1_ns', 'C2'), ('tomsk_F1', 'C3')]:
    ax[0].plot(M.index, M[c], color=col, label=LBL[c])
ax[0].set_ylabel('f1 Hz (monthly mean)'); ax[0].legend(fontsize=8, ncol=2); ax[0].set_title(f'Schumann f1 2002-2026 ({EST}s) with solar activity')
for c, col in [('ver_a1_ns', 'C0'), ('ver_a1_ew', 'C1')]: ax[1].plot(M.index, M[c], color=col, label=LBL[c])
ax[1].set_ylabel('A1 rel dB'); ax[1].legend(fontsize=8)
ax[2].plot(M.index, M.sunspot_n, 'k', label='sunspot number'); a2 = ax[2].twinx(); a2.plot(M.index, M.kp_max, 'C3', alpha=.6, label='mean daily max Kp')
ax[2].set_ylabel('sunspots'); a2.set_ylabel('Kp'); ax[2].legend(loc='upper left', fontsize=8); a2.legend(loc='upper right', fontsize=8)
plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_timeseries_solar.png'), dpi=110); plt.close()

# 2 diurnal by season
ser = [s for s in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'sou_f1_ns', 'tomsk_F1', 'tomsk_A1'] if s in DI.series.unique()]
fig, ax = plt.subplots(2, 3, figsize=(14, 7)); ax = ax.ravel()
for i, s in enumerate(ser):
    for se in ['DJF', 'MAM', 'JJA', 'SON']:
        x = DI[(DI.series == s) & (DI.season == se)]; ax[i].plot(x.hour_utc, x['mean'], label=se)
    ax[i].set_title(LBL.get(s, s), fontsize=9); ax[i].set_xlabel('hour UTC'); ax[i].legend(fontsize=7)
fig.suptitle(f'Diurnal cycle by season ({EST}s)'); plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_diurnal.png'), dpi=110); plt.close()

# 3 heatmap of partial r (daily family, best lag) with BH markers
d = C[C.family == 'daily']
best = d.loc[d.groupby(['target', 'predictor']).p.idxmin()]
H = best.pivot(index='predictor', columns='target', values='partial_r'); Q = best.pivot(index='predictor', columns='target', values='q_fdr')
L = best.pivot(index='predictor', columns='target', values='lag')
fig, ax = plt.subplots(figsize=(10, 8)); im = ax.imshow(H.values, cmap='RdBu_r', vmin=-.3, vmax=.3, aspect='auto')
ax.set_xticks(range(H.shape[1])); ax.set_xticklabels(H.columns, rotation=40, ha='right'); ax.set_yticks(range(H.shape[0])); ax.set_yticklabels(H.index)
for i in range(H.shape[0]):
    for j in range(H.shape[1]):
        if pd.notna(H.values[i, j]):
            ax.text(j, i, f"{H.values[i,j]:.2f}{'*' if Q.values[i,j] < .05 else ''}\nL{int(L.values[i,j])}", ha='center', va='center', fontsize=6)
plt.colorbar(im, label='partial r (FE + controls)'); ax.set_title('Daily SR vs drivers: best lag 0-3 d, * = BH q<0.05 (per target family)')
plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_heatmap.png'), dpi=110); plt.close()

# 4 lag plot + scatter
fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
for pr in ['kp_max', 'AE_mean', 'omni_sw_V', 'Dst_min', 'sunspot_n', 'moon_illum', 'pressure_msl_hPa_era5']:
    x = d[(d.target == 'ver_f1_ns') & (d.predictor == pr)].sort_values('lag'); ax[0].errorbar(x.lag, x.beta_per_sd, yerr=[x.beta_per_sd - x.ci_lo, x.ci_hi - x.beta_per_sd], label=pr, capsize=3, marker='o')
ax[0].axhline(0, color='k', lw=.5); ax[0].set_xlabel('lag (days)'); ax[0].set_ylabel('Hz per SD'); ax[0].set_title('Vernadsky f1 NS: effect vs lag (95% HAC CI)'); ax[0].legend(fontsize=7)
for k, (pr, tg) in enumerate([('kp_max', 'ver_f1_ns'), ('moon_illum', 'ver_f1_ns')]):
    an = Dd[tg] - Dd[tg].groupby([Dd.index.year, Dd.index.month]).transform('mean')
    xx = Dd[pr].shift(1) if pr == 'kp_max' else Dd[pr]
    ok = an.notna() & xx.notna(); ax[k + 1].scatter(xx[ok], an[ok], s=2, alpha=.25)
    bins = pd.cut(xx[ok], 10); g = an[ok].groupby(bins, observed=True).mean(); ax[k + 1].plot([b.mid for b in g.index], g.values, 'r-o')
    ax[k + 1].set_xlabel(pr + (' (lag 1 d)' if pr == 'kp_max' else '')); ax[k + 1].set_ylabel('f1 anomaly vs year-month mean (Hz)'); ax[k + 1].set_title(f'{tg} ({EST})')
plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_lag_scatter.png'), dpi=110); plt.close()

# 5 superposed epoch
fig, ax = plt.subplots(1, 3, figsize=(15, 4))
for i, ev in enumerate(EP.event.unique()):
    for tg in ['ver_f1_ns', 'ver_f1_ew', 'sou_f1_ns']:
        x = EP[(EP.event == ev) & (EP.target == tg)]
        if len(x): ax[i].errorbar(x.lag, x.mean_anom, yerr=1.96 * x.se, label=f'{tg} (n={int(x.n_events.max())})', capsize=2, marker='.')
    ax[i].axvline(0, color='k', lw=.5); ax[i].axhline(0, color='k', lw=.5); ax[i].set_title(ev); ax[i].set_xlabel('days from event'); ax[i].legend(fontsize=7)
ax[0].set_ylabel('f1 anomaly (Hz)'); plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_epoch.png'), dpi=110); plt.close()

# 6 forecast skill vs horizon
fig, ax = plt.subplots(2, 2, figsize=(13, 8)); ax = ax.ravel()
for i, tg in enumerate(['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']):
    x = SK[SK.target == tg]
    for m, st in [('ridge:hist+solar', '-o'), ('ridge:hist', '--o'), ('gbm:hist+solar', '-s'), ('persistence', ':x'), ('climatology', ':x'), ('persist_7d_mean', ':x')]:
        y = x[x.model == m].sort_values('h'); ax[i].plot(y.h, y.skill_vs_best_baseline, st, label=m)
    ax[i].axhline(0, color='k', lw=.6); ax[i].set_title(LBL[tg]); ax[i].set_xlabel('horizon (days)'); ax[i].set_ylabel('MAE skill vs best baseline'); ax[i].set_ylim(-.4, .25)
ax[0].legend(fontsize=7); fig.suptitle('Held-out test 2016-2020: forecast skill (1 - MAE/MAE_best_baseline); >0 beats every baseline')
plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_forecast_skill.png'), dpi=110); plt.close()

# 7 forecast vs actual (2019, h=7)
fig, ax = plt.subplots(2, 1, figsize=(13, 7))
for i, tg in enumerate(['ver_f1_ns', 'ver_a1_ns']):
    h = 7; sl = slice('2019-01-01', '2019-12-31'); act = P['actual_' + tg].shift(-h)
    for m, st in [('ridge:all(+wx)', 'C3'), ('clim+damped_anom', 'C2'), ('persistence', 'C7')]:
        pr = P[f'{tg}|{h}|{m}']; pr.index = pr.index + pd.Timedelta(days=h); ax[i].plot(pr[sl].index, pr[sl], color=st, label=f'{m} forecast')
    a = P['actual_' + tg][sl]; ax[i].plot(a.index, a, 'k', lw=.8, label=f'actual ({EST})'); ax[i].set_title(f'{LBL[tg]}: 7-day-ahead forecasts, 2019 (test year)'); ax[i].legend(fontsize=7)
plt.tight_layout(); plt.savefig(os.path.join(R, 'sr_forecast_vs_actual.png'), dpi=110); plt.close()

# ---------- interactive page ----------
def div(f, h=450):
    f.update_layout(height=h, margin=dict(l=50, r=20, t=50, b=40), template='plotly_white'); figs.append(f)
f = make_subplots(rows=3, cols=1, shared_xaxes=True, specs=[[{}], [{}], [{'secondary_y': True}]], vertical_spacing=.05)
W = Dd.resample('W').mean()
for c in ['ver_f1_ns', 'ver_f1_ew', 'sou_f1_ns', 'tomsk_F1']: f.add_trace(go.Scatter(x=W.index, y=W[c].round(4), name=LBL[c] + ' [est]', mode='lines'), 1, 1)
for c in ['ver_a1_ns', 'ver_a1_ew']: f.add_trace(go.Scatter(x=W.index, y=W[c].round(2), name=LBL[c] + ' [est]', mode='lines'), 2, 1)
f.add_trace(go.Scatter(x=W.index, y=W.sunspot_n.round(1), name='sunspots', line=dict(color='black')), 3, 1)
f.add_trace(go.Scatter(x=W.index, y=W.kp_max.round(2), name='weekly mean daily max Kp', line=dict(color='firebrick')), 3, 1, secondary_y=True)
f.update_layout(title='Schumann f1 / A1 (weekly means of digitized estimates) with solar overlay'); div(f, 750)
f = go.Figure()
for s in ser:
    for se in ['DJF', 'JJA']:
        x = DI[(DI.series == s) & (DI.season == se)]
        f.add_trace(go.Scatter(x=x.hour_utc, y=(x['mean'] - x['mean'].mean()).round(4), name=f'{s} {se}', mode='lines'))
f.update_layout(title='Diurnal cycle (deviation from daily mean), Dec-Feb vs Jun-Aug, hour UTC [estimates]'); div(f)
f = go.Figure(go.Heatmap(z=H.values.round(3), x=list(H.columns), y=list(H.index), zmin=-.3, zmax=.3, colorscale='RdBu', reversescale=True,
                         text=[[f"q={Q.values[i,j]:.3g} lag {L.values[i,j]:.0f}" if pd.notna(Q.values[i, j]) else '' for j in range(H.shape[1])] for i in range(H.shape[0])],
                         hovertemplate='%{y} → %{x}<br>partial r=%{z}<br>%{text}<extra></extra>'))
f.update_layout(title='Partial correlation heatmap (daily, best lag 0-3 d; hover for BH q)'); div(f, 600)
f = go.Figure()
for pr in ['kp_max', 'AE_mean', 'omni_sw_V', 'Dst_min', 'sunspot_n', 'moon_illum', 'moon_dist_km', 'pressure_msl_hPa_era5', 'tmax_F']:
    x = d[(d.target == 'ver_f1_ns') & (d.predictor == pr)].sort_values('lag')
    f.add_trace(go.Scatter(x=x.lag, y=x.beta_per_sd, error_y=dict(type='data', symmetric=False, array=x.ci_hi - x.beta_per_sd, arrayminus=x.beta_per_sd - x.ci_lo), name=pr, mode='lines+markers'))
f.update_layout(title='Vernadsky f1 NS: effect per SD of driver vs lag (95% HAC CI)', xaxis_title='lag (days)', yaxis_title='Hz per SD'); div(f)
f = make_subplots(rows=1, cols=3, subplot_titles=list(EP.event.unique()))
for i, ev in enumerate(EP.event.unique()):
    for tg in ['ver_f1_ns', 'sou_f1_ns']:
        x = EP[(EP.event == ev) & (EP.target == tg)]
        f.add_trace(go.Scatter(x=x.lag, y=x.mean_anom, error_y=dict(array=1.96 * x.se), name=f'{ev} {tg}', mode='lines+markers'), 1, i + 1)
f.update_layout(title='Superposed epoch: f1 anomaly around events'); div(f)
f = make_subplots(rows=2, cols=2, subplot_titles=[LBL[t] for t in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']])
for i, tg in enumerate(['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']):
    x = SK[SK.target == tg]
    for m in ['ridge:hist+solar', 'ridge:hist', 'ridge:all(+wx)', 'gbm:hist+solar', 'persistence', 'climatology', 'persist_7d_mean', 'clim+damped_anom']:
        y = x[x.model == m].sort_values('h')
        f.add_trace(go.Scatter(x=y.h, y=y.skill_vs_best_baseline.round(3), name=m, legendgroup=m, showlegend=i == 0, mode='lines+markers'), i // 2 + 1, i % 2 + 1)
f.update_layout(title='Forecast skill on held-out 2016-2020 (1 − MAE/best-baseline MAE)'); f.update_yaxes(range=[-.4, .25]); div(f, 700)
f = make_subplots(rows=2, cols=1, subplot_titles=['Vernadsky f1 NS, 7 days ahead', 'Vernadsky A1 NS, 7 days ahead'])
for i, tg in enumerate(['ver_f1_ns', 'ver_a1_ns']):
    for m in ['ridge:all(+wx)', 'clim+damped_anom', 'persistence']:
        pr = P[f'{tg}|7|{m}'].copy(); pr.index = pr.index + pd.Timedelta(days=7)
        f.add_trace(go.Scatter(x=pr.index, y=pr.round(4), name=f'{m} (7d)', legendgroup=m, showlegend=i == 0, mode='lines'), i + 1, 1)
    f.add_trace(go.Scatter(x=P.index, y=P['actual_' + tg].round(4), name='actual [est]', legendgroup='a', showlegend=i == 0, line=dict(color='black', width=1)), i + 1, 1)
f.update_layout(title='Forecast vs actual, test period 2016-2020'); div(f, 700)

sig = SG[SG.h.isin([1, 7])].copy()
sig_html = sig[['target', 'h', 'model', 'best_baseline', 'mae_model', 'mae_baseline', 'skill', 'p_one_sided']].round(4).to_html(index=False, border=0, classes='t')
top = C[(C.family == 'daily') & (C.q_fdr < .05)].sort_values('p').drop_duplicates(['target', 'predictor'])
top_html = top[['target', 'predictor', 'lag', 'beta_per_sd', 'partial_r', 'q_fdr', 'n_days']].round(4).head(40).to_html(index=False, border=0, classes='t')
cov = pd.DataFrame({c: [Dd[c].first_valid_index().date() if Dd[c].notna().any() else None, Dd[c].last_valid_index().date() if Dd[c].notna().any() else None, int(Dd[c].notna().sum())]
                    for c in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'sou_f1_ns', 'tomsk_F1', 'tomsk_A1', 'tomsk_Q1']}, index=['first', 'last', 'valid days']).T
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Schumann resonance history & forecast</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:10px;color:#222}} .warn{{background:#fff4d6;border:1px solid #e0b84c;padding:8px;border-radius:6px}}
table.t{{border-collapse:collapse;font-size:12px}} table.t td,table.t th{{padding:2px 6px;border-bottom:1px solid #ddd}} nav a{{margin-right:12px}}</style></head><body>
<nav><a href="index.html">← Dashboard</a><a href="outlook.html">Outlook</a><a href="world/">World</a></nav>
<h1>Schumann resonance: historical record, correlations and forecast</h1>
<p class="warn"><b>All SR values here are digitized estimates</b>, read pixel-by-pixel off published charts: Vernadsky (Antarctica) and SOUSY (Svalbard) daily f1 line charts and spectrograms (Zenodo), plus Tomsk/sos70 F/A/Q charts (Internet Archive snapshots, values read by OCR). Frequency error is about ±0.003–0.01 Hz. Amplitudes are relative dB (Vernadsky) or chart units (Tomsk), not calibrated pT. Each station measures its own local field, so different stations do not track each other day to day.</p>
<h3>Coverage</h3>{cov.to_html(border=0, classes='t')}
<div id="figs"></div>
<h3>Daily associations surviving BH correction (q&lt;0.05), strongest per target×driver</h3><p>OLS on daily means with weekday, month, year and holiday fixed effects; Newey-West HAC SE (7 lags); BH within each target. Year fixed effects absorb the solar cycle (the cycle is tested separately on monthly data).</p>{top_html}
<h3>Forecast significance (30-day block bootstrap, test 2016-2020)</h3><p>skill = 1 − MAE_model/MAE_best_baseline. p_one_sided = bootstrap share of samples where the model did not beat that baseline.</p>{sig_html}
<p>Generated {pd.Timestamp.now(tz='America/Los_Angeles').strftime('%Y-%m-%d %H:%M %Z')} by schumann/make_schumann_charts.py. Data: data/schumann_*.csv.gz; results: reports/schumann/.</p>
<script>const F={json.dumps([json.loads(x.to_json()) for x in figs])};
const c=document.getElementById('figs');F.forEach((f,i)=>{{const d=document.createElement('div');c.appendChild(d);Plotly.newPlot(d,f.data,f.layout,{{responsive:true}});}});</script></body></html>"""
open(os.path.join(R, 'schumann.html'), 'w').write(html)   # tracked copy; CI copies it into site/
os.makedirs(S, exist_ok=True); open(os.path.join(S, 'schumann.html'), 'w').write(html)
print('ok', os.path.getsize(os.path.join(S, 'schumann.html')))
