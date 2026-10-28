"""PNG charts (reports/schumann/*.png) + interactive page (site/schumann.html) for the Schumann resonance study.
All SR values are DIGITIZED ESTIMATES read off published spectrogram/line charts.
Display names come from labels.py (plain English); data columns are unchanged."""
import os, sys, json, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, B)
from labels import label, wrap, explain, caption, MODELS, EVENTS, SEASONS
D, R, S = os.path.join(B, 'data'), os.path.join(B, 'reports', 'schumann'), os.path.join(B, 'site')
EST = 'digitized estimate'
Dd = pd.read_csv(os.path.join(D, 'schumann_daily.csv.gz'), index_col=0, parse_dates=True)
C = pd.read_csv(os.path.join(R, 'schumann_correlations.csv'))
DI = pd.read_csv(os.path.join(R, 'schumann_diurnal.csv'))
EP = pd.read_csv(os.path.join(R, 'schumann_epoch.csv'))
SK = pd.read_csv(os.path.join(R, 'schumann_forecast_skill.csv'))
SG = pd.read_csv(os.path.join(R, 'schumann_forecast_significance.csv'))
P = pd.read_csv(os.path.join(R, 'schumann_forecast_test_predictions.csv.gz'), parse_dates=['date']).set_index('date').asfreq('D')
LBL = label
ML = lambda m: MODELS.get(m, m)
EV = lambda e: EVENTS.get(e, e)
# Diurnal data is binned by UTC hour; show Pacific time. Winter (DJF) is PST = UTC-8, the other seasons are mostly PDT = UTC-7.
PT_OFF = {'DJF': -8, 'MAM': -7, 'JJA': -7, 'SON': -7}
def pt_hours(x, se):
    x = x.copy(); x['hour_pt'] = (x.hour_utc + PT_OFF[se]) % 24; return x.sort_values('hour_pt')
CAP = {}
figs = []

# 1 time series + solar overlay (monthly means)
M = Dd.resample('MS').mean()
fig, ax = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
for c, col in [('ver_f1_ns', 'C0'), ('ver_f1_ew', 'C1'), ('sou_f1_ns', 'C2'), ('tomsk_F1', 'C3')]:
    ax[0].plot(M.index, M[c], color=col, label=LBL(c))
ax[0].set_ylabel('Pitch of the main hum (Hz)\nmonthly average'); ax[0].legend(fontsize=8, ncol=2)
ax[0].set_title(f"Earth's natural 'hum' (Schumann resonance) 2002–2026 vs. the Sun's 11-year cycle  [values are {EST}s]")
for c, col in [('ver_a1_ns', 'C0'), ('ver_a1_ew', 'C1')]: ax[1].plot(M.index, M[c], color=col, label=LBL(c))
ax[1].set_ylabel('Signal strength\n(relative dB)'); ax[1].legend(fontsize=8)
ax[2].plot(M.index, M.sunspot_n, 'k', label=label('sunspot_n')); a2 = ax[2].twinx(); a2.plot(M.index, M.kp_max, 'C3', alpha=.6, label=label('kp_max') + ', monthly avg')
ax[2].set_ylabel(label('sunspot_n')); a2.set_ylabel('Geomagnetic storm level (0–9)'); ax[2].legend(loc='upper left', fontsize=8); a2.legend(loc='upper right', fontsize=8)
CAP['ts'] = "Top: the pitch of the hum at each station; middle: how loud it is; bottom: sunspots (black) and magnetic storms (red). When the Sun is busier, the hum's pitch and loudness go up."
caption(fig, CAP['ts']); plt.savefig(os.path.join(R, 'sr_timeseries_solar.png'), dpi=110); plt.close()

# 2 daily cycle by season (Pacific time)
ser = [s for s in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'sou_f1_ns', 'tomsk_F1', 'tomsk_A1'] if s in DI.series.unique()]
fig, ax = plt.subplots(2, 3, figsize=(14, 8)); ax = ax.ravel()
for i, s in enumerate(ser):
    for se in ['DJF', 'MAM', 'JJA', 'SON']:
        x = pt_hours(DI[(DI.series == s) & (DI.season == se)], se); ax[i].plot(x.hour_pt, x['mean'], label=SEASONS[se])
    ax[i].set_title(wrap(s, 45), fontsize=9); ax[i].set_xlabel('Hour of day (Pacific time)'); ax[i].set_xticks(range(0, 24, 3)); ax[i].legend(fontsize=7)
fig.suptitle(f'How the hum changes over a day, by season  [{EST}s]')
CAP['diurnal'] = "Each line is the average day in one season. The hum rises and falls each day as thunderstorms build over Africa, Asia and the Americas in turn (hours shown in Pacific time)."
caption(fig, CAP['diurnal']); plt.savefig(os.path.join(R, 'sr_diurnal.png'), dpi=110); plt.close()

# 3 heatmap of link strength (daily family, best lag)
d = C[C.family == 'daily']
best = d.loc[d.groupby(['target', 'predictor']).p.idxmin()]
H = best.pivot(index='predictor', columns='target', values='partial_r'); Q = best.pivot(index='predictor', columns='target', values='q_fdr')
L = best.pivot(index='predictor', columns='target', values='lag')
fig, ax = plt.subplots(figsize=(13, 11)); im = ax.imshow(H.values, cmap='RdBu_r', vmin=-.3, vmax=.3, aspect='auto')
def short(c):
    st = {'ver': 'Antarctica', 'sou': 'Arctic', 'tomsk': 'Siberia'}[c.split('_')[0]]
    kind = 'pitch of hum' if c.lower().split('_')[1].startswith('f') else ('hum strength' if c.lower().split('_')[1].startswith('a') else 'hum sharpness')
    sen = {'ns': '\nnorth-south sensor', 'ew': '\neast-west sensor'}.get(c.split('_')[-1], '')
    return f'{st}\n{kind}{sen}'
order = [c for c in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew', 'sou_f1_ns', 'sou_f1_ew', 'tomsk_F1', 'tomsk_A1', 'tomsk_F2', 'tomsk_Q1'] if c in H.columns]
H, Q, L = H[order], Q[order], L[order]
im.set_data(H.values)
ax.set_xticks(range(H.shape[1])); ax.set_xticklabels([short(c) for c in H.columns], rotation=0, fontsize=8)
ax.set_yticks(range(H.shape[0])); ax.set_yticklabels([label(r) for r in H.index], fontsize=9)
ax.xaxis.tick_top()
for i in range(H.shape[0]):
    for j in range(H.shape[1]):
        if pd.notna(H.values[i, j]):
            lg = int(L.values[i, j]); ls = 'same day' if lg == 0 else f'{lg} day{"s" if lg > 1 else ""} later'
            ax.text(j, i, f"{H.values[i,j]:+.2f}{' ★' if Q.values[i,j] < .05 else ''}\n{ls}", ha='center', va='center', fontsize=6.5)
plt.colorbar(im, label='Link strength (−1 to +1), after removing season & calendar effects', shrink=.8)
ax.set_title("What moves the Earth's hum? Each square: link between a possible cause (left) and a hum measurement (top)", pad=12, fontsize=11)
CAP['heat'] = "Red = they rise together, blue = one rises as the other falls, white = no link. ★ = chance it's a fluke under 5% (after correction). 'Days later' = when the link is strongest."
caption(fig, CAP['heat']); plt.savefig(os.path.join(R, 'sr_heatmap.png'), dpi=110); plt.close()

# 4 lag plot + scatter
fig, ax = plt.subplots(1, 3, figsize=(16, 5.5))
for pr in ['kp_max', 'AE_mean', 'omni_sw_V', 'Dst_min', 'sunspot_n', 'moon_illum', 'pressure_msl_hPa_era5']:
    x = d[(d.target == 'ver_f1_ns') & (d.predictor == pr)].sort_values('lag'); ax[0].errorbar(x.lag, x.beta_per_sd, yerr=[x.beta_per_sd - x.ci_lo, x.ci_hi - x.beta_per_sd], label=label(pr), capsize=3, marker='o')
ax[0].axhline(0, color='k', lw=.5); ax[0].set_xlabel('Days later'); ax[0].set_xticks([0, 1, 2, 3]); ax[0].set_ylabel('Change in pitch (Hz) per typical swing of the cause')
ax[0].set_title('Antarctica main tone: effect of each cause,\nsame day to 3 days later', fontsize=10); ax[0].legend(fontsize=7)
for k, (pr, tg) in enumerate([('kp_max', 'ver_f1_ns'), ('moon_illum', 'ver_f1_ns')]):
    an = Dd[tg] - Dd[tg].groupby([Dd.index.year, Dd.index.month]).transform('mean')
    xx = Dd[pr].shift(1) if pr == 'kp_max' else Dd[pr]
    ok = an.notna() & xx.notna(); ax[k + 1].scatter(xx[ok], an[ok], s=2, alpha=.25)
    bins = pd.cut(xx[ok], 10); g = an[ok].groupby(bins, observed=True).mean(); ax[k + 1].plot([b.mid for b in g.index], g.values, 'r-o')
    ax[k + 1].set_xlabel(label(pr) + (' (the day before)' if pr == 'kp_max' else '')); ax[k + 1].set_ylabel('Pitch vs. that month\'s average (Hz)')
    ax[k + 1].set_title(wrap(tg, 50), fontsize=10)
CAP['lag'] = "Left: dots above the zero line mean the cause raises the hum's pitch (bars = 95% range). Middle/right: each dot is one day; the red line is the average, so a sloped red line means a real effect."
caption(fig, CAP['lag']); plt.savefig(os.path.join(R, 'sr_lag_scatter.png'), dpi=110); plt.close()

# 5 superposed epoch
fig, ax = plt.subplots(1, 3, figsize=(16, 5))
for i, ev in enumerate(EP.event.unique()):
    for tg in ['ver_f1_ns', 'ver_f1_ew', 'sou_f1_ns']:
        x = EP[(EP.event == ev) & (EP.target == tg)]
        if len(x): ax[i].errorbar(x.lag, x.mean_anom, yerr=1.96 * x.se, label=wrap(tg, 40) + f'\n({int(x.n_events.max())} events)', capsize=2, marker='.')
    ax[i].axvline(0, color='k', lw=.5); ax[i].axhline(0, color='k', lw=.5); ax[i].set_title(EV(ev)); ax[i].set_xlabel('Days before (−) / after (+) the event'); ax[i].legend(fontsize=6.5)
ax[0].set_ylabel('Pitch vs. normal (Hz)')
CAP['epoch'] = "Averages of the hum around every past event of each kind (day 0 = the event). A bump after day 0 that clears the zero line means the event changes the hum."
caption(fig, CAP['epoch']); plt.savefig(os.path.join(R, 'sr_epoch.png'), dpi=110); plt.close()

# 6 forecast skill vs horizon
fig, ax = plt.subplots(2, 2, figsize=(14, 9)); ax = ax.ravel()
for i, tg in enumerate(['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']):
    x = SK[SK.target == tg]
    for m, st in [('ridge:hist+solar', '-o'), ('ridge:hist', '--o'), ('gbm:hist+solar', '-s'), ('persistence', ':x'), ('climatology', ':x'), ('persist_7d_mean', ':x')]:
        y = x[x.model == m].sort_values('h'); ax[i].plot(y.h, y.skill_vs_best_baseline, st, label=ML(m))
    ax[i].axhline(0, color='k', lw=.6); ax[i].set_title(wrap(tg, 60), fontsize=10); ax[i].set_xlabel('Days ahead'); ax[i].set_ylabel('Improvement over best simple guess'); ax[i].set_ylim(-.4, .25)
ax[0].legend(fontsize=7)
fig.suptitle('Can we forecast the hum? Tested on 2016–2020 data the forecasts never saw')
CAP['skill'] = "Above the zero line = the forecast beats every simple guess (e.g. 0.1 = 10% smaller errors); below = worse than just guessing."
caption(fig, CAP['skill']); plt.savefig(os.path.join(R, 'sr_forecast_skill.png'), dpi=110); plt.close()

# 7 forecast vs actual (2019, h=7)
fig, ax = plt.subplots(2, 1, figsize=(13, 8))
for i, tg in enumerate(['ver_f1_ns', 'ver_a1_ns']):
    h = 7; sl = slice('2019-01-01', '2019-12-31')
    for m, st in [('ridge:all(+wx)', 'C3'), ('clim+damped_anom', 'C2'), ('persistence', 'C7')]:
        pr = P[f'{tg}|{h}|{m}']; pr.index = pr.index + pd.Timedelta(days=h); ax[i].plot(pr[sl].index, pr[sl], color=st, label=ML(m))
    a = P['actual_' + tg][sl]; ax[i].plot(a.index, a, 'k', lw=.8, label=f'What actually happened ({EST})'); ax[i].set_title(f'{LBL(tg)}: forecasts made 7 days ahead, 2019'); ax[i].legend(fontsize=7)
CAP['fva'] = "Black = what was measured; colored lines = what each method predicted a week earlier. The closer a colored line hugs the black one, the better the forecast."
caption(fig, CAP['fva']); plt.savefig(os.path.join(R, 'sr_forecast_vs_actual.png'), dpi=110); plt.close()

# ---------- interactive page ----------
def div(f, cap, h=450):
    f.update_layout(height=h, margin=dict(l=60, r=20, t=60, b=50), template='plotly_white'); figs.append((f, cap))
f = make_subplots(rows=3, cols=1, shared_xaxes=True, specs=[[{}], [{}], [{'secondary_y': True}]], vertical_spacing=.05)
W = Dd.resample('W').mean()
for c in ['ver_f1_ns', 'ver_f1_ew', 'sou_f1_ns', 'tomsk_F1']: f.add_trace(go.Scatter(x=W.index, y=W[c].round(4), name=LBL(c) + ' [est]', mode='lines'), 1, 1)
for c in ['ver_a1_ns', 'ver_a1_ew']: f.add_trace(go.Scatter(x=W.index, y=W[c].round(2), name=LBL(c) + ' [est]', mode='lines'), 2, 1)
f.add_trace(go.Scatter(x=W.index, y=W.sunspot_n.round(1), name=label('sunspot_n'), line=dict(color='black')), 3, 1)
f.add_trace(go.Scatter(x=W.index, y=W.kp_max.round(2), name=label('kp_max') + ', weekly avg', line=dict(color='firebrick')), 3, 1, secondary_y=True)
f.update_yaxes(title_text='Pitch (Hz)', row=1, col=1); f.update_yaxes(title_text='Strength (rel dB)', row=2, col=1); f.update_yaxes(title_text='Sunspots', row=3, col=1)
f.update_yaxes(title_text='Storm level', row=3, col=1, secondary_y=True)
f.update_layout(title="Earth's natural 'hum' vs. the Sun (weekly averages)", legend=dict(font=dict(size=10))); div(f, CAP['ts'], 750)
f = go.Figure()
for s in ser:
    for se in ['DJF', 'JJA']:
        x = pt_hours(DI[(DI.series == s) & (DI.season == se)], se)
        f.add_trace(go.Scatter(x=x.hour_pt, y=(x['mean'] - x['mean'].mean()).round(4), name=f'{LBL(s)} – {SEASONS[se]}', mode='lines'))
f.update_layout(title='The hum over an average day: winter vs. summer', xaxis_title='Hour of day (Pacific time)', yaxis_title='Difference from the daily average'); div(f, CAP['diurnal'], 550)
f = go.Figure(go.Heatmap(z=H.values.round(3), x=[LBL(c) for c in H.columns], y=[label(r) for r in H.index], zmin=-.3, zmax=.3, colorscale='RdBu', reversescale=True,
                         colorbar=dict(title='Link<br>strength'),
                         text=[[f"Chance it's a fluke (after correction): {Q.values[i,j]:.3g}<br>Strongest {('same day' if L.values[i,j] == 0 else f'{L.values[i,j]:.0f} day(s) later')}" if pd.notna(Q.values[i, j]) else '' for j in range(H.shape[1])] for i in range(H.shape[0])],
                         hovertemplate='%{y} → %{x}<br>Link strength = %{z}<br>%{text}<extra></extra>'))
f.update_layout(title='What moves the hum? (hover a square for details)', xaxis=dict(tickangle=-30, tickfont=dict(size=9))); div(f, CAP['heat'], 750)
f = go.Figure()
for pr in ['kp_max', 'AE_mean', 'omni_sw_V', 'Dst_min', 'sunspot_n', 'moon_illum', 'moon_dist_km', 'pressure_msl_hPa_era5', 'tmax_F']:
    x = d[(d.target == 'ver_f1_ns') & (d.predictor == pr)].sort_values('lag')
    f.add_trace(go.Scatter(x=x.lag, y=x.beta_per_sd, error_y=dict(type='data', symmetric=False, array=x.ci_hi - x.beta_per_sd, arrayminus=x.beta_per_sd - x.ci_lo), name=label(pr), mode='lines+markers'))
f.update_layout(title=f'{LBL("ver_f1_ns")}: effect of each cause, same day to 3 days later', xaxis_title='Days later', yaxis_title='Change in pitch (Hz) per typical swing'); div(f, CAP['lag'].split('Middle/right')[0])
f = make_subplots(rows=1, cols=3, subplot_titles=[EV(e) for e in EP.event.unique()])
for i, ev in enumerate(EP.event.unique()):
    for tg in ['ver_f1_ns', 'sou_f1_ns']:
        x = EP[(EP.event == ev) & (EP.target == tg)]
        f.add_trace(go.Scatter(x=x.lag, y=x.mean_anom, error_y=dict(array=1.96 * x.se), name=f'{EV(ev)}: {LBL(tg)}', mode='lines+markers'), 1, i + 1)
f.update_xaxes(title_text='Days from event'); f.update_layout(title='What happens to the hum around solar storms and flares', yaxis_title='Pitch vs. normal (Hz)'); div(f, CAP['epoch'], 520)
f = make_subplots(rows=2, cols=2, subplot_titles=[LBL(t) for t in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']])
for i, tg in enumerate(['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']):
    x = SK[SK.target == tg]
    for m in ['ridge:hist+solar', 'ridge:hist', 'ridge:all(+wx)', 'gbm:hist+solar', 'persistence', 'climatology', 'persist_7d_mean', 'clim+damped_anom']:
        y = x[x.model == m].sort_values('h')
        f.add_trace(go.Scatter(x=y.h, y=y.skill_vs_best_baseline.round(3), name=ML(m), legendgroup=m, showlegend=i == 0, mode='lines+markers'), i // 2 + 1, i % 2 + 1)
f.update_xaxes(title_text='Days ahead'); f.update_layout(title='Can we forecast the hum? (tested on unseen 2016–2020 data)'); f.update_yaxes(range=[-.4, .25], title_text='Improvement'); div(f, CAP['skill'], 750)
f = make_subplots(rows=2, cols=1, subplot_titles=[LBL('ver_f1_ns') + ', forecast 7 days ahead', LBL('ver_a1_ns') + ', forecast 7 days ahead'])
for i, tg in enumerate(['ver_f1_ns', 'ver_a1_ns']):
    for m in ['ridge:all(+wx)', 'clim+damped_anom', 'persistence']:
        pr = P[f'{tg}|7|{m}'].copy(); pr.index = pr.index + pd.Timedelta(days=7)
        f.add_trace(go.Scatter(x=pr.index, y=pr.round(4), name=ML(m), legendgroup=m, showlegend=i == 0, mode='lines'), i + 1, 1)
    f.add_trace(go.Scatter(x=P.index, y=P['actual_' + tg].round(4), name='What actually happened [est]', legendgroup='a', showlegend=i == 0, line=dict(color='black', width=1)), i + 1, 1)
f.update_layout(title='Forecast vs. what happened, 2016–2020'); div(f, CAP['fva'], 700)

def tbl(df, cols):
    df = df[list(cols)].copy()
    for c in ('target', 'predictor'):
        if c in df: df[c] = df[c].map(LBL)
    for c in ('model', 'best_baseline'):
        if c in df: df[c] = df[c].map(ML)
    return df.round(4).rename(columns=cols).to_html(index=False, border=0, classes='t')
sig = SG[SG.h.isin([1, 7])].copy()
sig_html = tbl(sig, {'target': 'What is forecast', 'h': 'Days ahead', 'model': 'Forecast method', 'best_baseline': 'Best simple guess',
                     'mae_model': 'Typical error (forecast)', 'mae_baseline': 'Typical error (simple guess)', 'skill': 'Improvement',
                     'p_one_sided': "Chance it's a fluke"})
top = C[(C.family == 'daily') & (C.q_fdr < .05)].sort_values('p').drop_duplicates(['target', 'predictor']).head(40)
top_html = tbl(top, {'target': 'Hum measurement', 'predictor': 'Possible cause', 'lag': 'Days later', 'beta_per_sd': 'Change per typical swing',
                     'partial_r': 'Link strength (−1 to +1)', 'q_fdr': "Chance it's a fluke (after correction)", 'n_days': 'Days of data'})
covc = ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'sou_f1_ns', 'tomsk_F1', 'tomsk_A1', 'tomsk_Q1']
cov = pd.DataFrame({LBL(c): [Dd[c].first_valid_index().date() if Dd[c].notna().any() else None, Dd[c].last_valid_index().date() if Dd[c].notna().any() else None, int(Dd[c].notna().sum())]
                    for c in covc}, index=['First day', 'Last day', 'Days with data']).T
gloss = ''.join(f'<li><b>{label(k)}</b> – {explain(k)}</li>' for k in ['ver_f1_ns', 'ver_a1_ns', 'kp_max', 'Dst_min', 'AE_mean', 'F107_adj', 'omni_Bz', 'log_p10MeV_max', 'partial_r', 'q_fdr'])
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Schumann resonance (Earth's hum): history & forecast</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:10px;color:#222}} .warn{{background:#fff4d6;border:1px solid #e0b84c;padding:8px;border-radius:6px}}
.cap{{background:#f4f6f8;border-left:4px solid #6b8cae;padding:6px 10px;margin:2px 0 22px;font-size:14px}}
table.t{{border-collapse:collapse;font-size:12px}} table.t td,table.t th{{padding:2px 6px;border-bottom:1px solid #ddd}} nav a{{margin-right:12px}}</style></head><body>
<nav><a href="index.html">← Dashboard</a><a href="outlook.html">Outlook</a><a href="world/">World</a></nav>
<h1>Schumann resonance – the Earth's natural "hum": history, links and forecast</h1>
<p>Lightning around the world makes the space between the ground and the upper atmosphere ring like a bell at about 7.8 Hz. Three stations record it: <b>Antarctica (Vernadsky)</b>, <b>Arctic (Svalbard)</b> and <b>Siberia (Tomsk)</b>. "North-south" and "east-west" are the two directions each station's sensor listens in.</p>
<p class="warn"><b>All hum values here are digitized estimates</b>, read pixel-by-pixel off published charts: Antarctica (Vernadsky) and Arctic (Svalbard, SOUSY) daily line charts and spectrograms (Zenodo), plus Siberia (Tomsk) charts (Internet Archive snapshots, values read by OCR). Pitch error is about ±0.003–0.01 Hz. Strength is relative (dB at Vernadsky, chart units at Tomsk), not calibrated. Each station measures its own local field, so stations do not track each other day to day.</p>
<details><summary><b>What the words mean</b></summary><ul>{gloss}</ul></details>
<h3>How much data each station has</h3>{cov.to_html(border=0, classes='t')}
<div id="figs"></div>
<h3>Daily links that are probably real (chance of a fluke under 5% after correction), strongest per pair</h3><p>Each link is measured after removing weekday, month, year and holiday effects, so the slow 11-year sun cycle is taken out here (it is tested separately on monthly data). "Change per typical swing" = how much the hum moves when the cause moves by a normal amount.</p>{top_html}
<h3>Is the forecast really better than guessing? (tested on 2016–2020)</h3><p>Improvement = how much smaller the forecast's errors are than the best simple guess (0.10 = 10% smaller). "Chance it's a fluke" comes from re-testing on thousands of shuffled 30-day blocks.</p>{sig_html}
<p>Generated {pd.Timestamp.now(tz='America/Los_Angeles').strftime('%Y-%m-%d %H:%M %Z')} by schumann/make_schumann_charts.py. Plain-English names come from labels.py. Data: data/schumann_*.csv.gz; results: reports/schumann/.</p>
<script>const F={json.dumps([dict(json.loads(x.to_json()), cap=c) for x, c in figs])};
const c=document.getElementById('figs');F.forEach((f,i)=>{{const d=document.createElement('div');c.appendChild(d);Plotly.newPlot(d,f.data,f.layout,{{responsive:true}});
const p=document.createElement('p');p.className='cap';p.textContent='How to read it: '+f.cap;c.appendChild(p);}});</script></body></html>"""
open(os.path.join(R, 'schumann.html'), 'w').write(html)   # tracked copy; CI copies it into site/
os.makedirs(S, exist_ok=True); open(os.path.join(S, 'schumann.html'), 'w').write(html)
print('ok', os.path.getsize(os.path.join(S, 'schumann.html')))
