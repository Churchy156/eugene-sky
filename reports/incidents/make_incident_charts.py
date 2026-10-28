"""Chart-only rebuild of the incident / sports / Ring of Fire PNGs from the saved result CSVs, with plain-English labels.
No regressions are re-run. Usage: python make_incident_charts.py [results_dir]  (default /workspace/eugene-env/incidents)
Writes PNGs to the results dir and to this folder (reports/incidents/)."""
import os, sys, shutil, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [os.path.join(HERE, '..', '..'), '/workspace/eugene-sky']
from labels import label, wrap, caption
SRC = sys.argv[1] if len(sys.argv) > 1 else '/workspace/eugene-env/incidents'
rd = lambda f: pd.read_csv(os.path.join(SRC, f))
out = []
def save(fig, name, dpi):
    p = os.path.join(SRC, name); fig.savefig(p, dpi=dpi); plt.close(fig); out.append(p)
    if os.path.abspath(SRC) != os.path.abspath(HERE): shutil.copy(p, os.path.join(HERE, name))

ORDER = ['pressure_msl', 'pressure_change_24h', 'tmax', 'tmin_freezing', 'rain_in', 'rain_day(>0.1in)', 'snow_day', 'first_rain_after_7dry',
         'kp_max', 'storm_Kp>=5', 'solar_wind_speed', 'full_moon(±1d)', 'moon_illum', 'tide_range', 'quakes_500km_M2.5+',
         'ring_of_fire_M6+_day', 'nz_quake_M5+_day', 'ring_of_fire_volcanoes_erupting', 'ring_of_fire_tsunami_day',
         'us_aqi_max', 'pm25', 'epa_aqi_official', 'covid_wastewater_log10', 'covid_hosp_rate_or', 'flu_hosp_rate_or', 'rsv_hosp_rate_or',
         'games_within_100mi', 'ducks_home_football', 'osu_home_football', 'major_home_game(UO/OSU FB)', 'ducks_home_mbb', 'osu_home_mbb',
         'ducks_home_wbb', 'milb_home_game', 'hayward_major_meet']

def heat(R, order, title, fname, figsize, vcap, cap):
    H = R.pivot(index='predictor', columns='outcome', values='pct_change'); Q = R.pivot(index='predictor', columns='outcome', values='q_fdr')
    H = H.reindex([p for p in order if p in H.index] + [p for p in H.index if p not in order]).dropna(how='all'); Q = Q.reindex(index=H.index, columns=H.columns)
    kind = R.drop_duplicates('predictor').set_index('predictor').kind
    fig, ax = plt.subplots(figsize=figsize); v = min(np.nanmax(np.abs(H.values)), vcap)
    im = ax.imshow(H.values, cmap='RdBu_r', vmin=-v, vmax=v, aspect='auto')
    ax.set_xticks(range(H.shape[1])); ax.set_xticklabels([wrap(c, 18) for c in H.columns], fontsize=9); ax.xaxis.tick_top()
    ax.set_yticks(range(H.shape[0]))
    ax.set_yticklabels([label(p) + (' (per typical swing)' if str(kind.get(p, '')) == 'per 1 SD' else '') for p in H.index], fontsize=9)
    for i in range(H.shape[0]):
        for j in range(H.shape[1]):
            if pd.notna(H.iat[i, j]): ax.text(j, i, f"{H.iat[i,j]:+.0f}%" + (' ★' if Q.iat[i, j] < 0.05 else ''), ha='center', va='center', fontsize=8)
    plt.colorbar(im, label='% more (red) or fewer (blue) than a normal day', shrink=.8)
    ax.set_title(title, fontsize=11, pad=10); caption(fig, cap); save(fig, fname, 130)

# 1 incidents vs environment
R = rd('incident_correlations.csv')
heat(R, ORDER, 'Do weather, space weather, the Moon, quakes, air or illness change local incident counts?\n(already adjusted for weekday, month, year and holidays)',
     'chart_incidents_correlation_heatmap.png', (13, 15), 40,
     "Red = more incidents than a normal day, blue = fewer. Yes/no rows compare those days to other days; other rows show the change for a typical swing. ★ = chance it's a fluke under 5% (after correction).")

# 2 sports
S = rd('sports_correlations.csv'); A = S[S.spec.str.startswith('all')]
sp = ['ducks_home_football', 'osu_home_football', 'major_home_game(UO/OSU FB)', 'major_home_game_next_day', 'ducks_home_mbb', 'osu_home_mbb', 'ducks_home_wbb', 'osu_home_wbb', 'milb_home_game', 'hayward_major_meet', 'games_within_100mi (per game)']
heat(A, sp, 'Crashes and police calls on sports days within 100 miles of Eugene\n(adjusted for weekday, month, year, holidays and weather)', 'chart_sports_games_incidents.png', (13, 7.5), 30,
     "Red = more than a normal day, blue = fewer. ★ = chance it's a fluke under 5% (after correction); squares without a ★ could easily be luck.")

# 3 crashes by rain / full moon / storm level
M = pd.read_csv(os.path.join(SRC, 'incidents_env_merged_daily.csv'), index_col=0, parse_dates=True)
df = M[['crashes_all_6cty', 'prcp_in', 'moon_illum', 'kp_max']].rename(columns={'crashes_all_6cty': 'y'}).dropna(subset=['y'])
df['dowm'] = df.y.groupby([df.index.dayofweek, df.index.month, df.index.year]).transform('mean'); df['ratio'] = df.y / df.dowm
fig, axs = plt.subplots(1, 3, figsize=(14, 5.5))
b = pd.cut(df.prcp_in, [-.01, 0, 0.1, 0.5, 1, 10], labels=['Dry', 'Under 0.1"', '0.1–0.5"', '0.5–1"', 'Over 1"']); g = df.groupby(b, observed=False).ratio.agg(['mean', 'sem'])
axs[0].bar(g.index.astype(str), 100 * (g['mean'] - 1), yerr=196 * g['sem']); axs[0].set_title('Rain in Eugene that day'); axs[0].set_xlabel('Rain (inches)')
df['fm'] = np.where(df.moon_illum >= 0.97, 'Full moon', 'Other nights'); g = df.groupby('fm').ratio.agg(['mean', 'sem'])
axs[1].bar(g.index, 100 * (g['mean'] - 1), yerr=196 * g['sem']); axs[1].set_title('Moon')
b = pd.cut(df.kp_max, [-1, 3, 4.99, 6.99, 10], labels=['Calm (0–3)', 'Unsettled (4)', 'Storm (5–6)', 'Strong storm (7+)']); g = df.groupby(b, observed=False).ratio.agg(['mean', 'sem'])
axs[2].bar(g.index.astype(str), 100 * (g['mean'] - 1), yerr=196 * g['sem']); axs[2].set_title(label('kp_max')); axs[2].tick_params(axis='x', labelsize=8)
for a in axs: a.axhline(0, color='k', lw=.8); a.set_ylabel('% more/fewer crashes than usual\nfor that weekday, month and year')
fig.suptitle('Reported crashes in Lane, Linn, Benton, Douglas, Marion and Lincoln counties, 2007–2024')
caption(fig, "Bars above zero = more crashes than usual, below = fewer; the black lines show the 95% range, so a bar whose line crosses zero may be no real effect. Heavier rain means clearly more crashes; full-moon days have slightly fewer; magnetic storms show no clear effect.")
save(fig, 'chart_crashes_rain_moon_kp.png', 130)

# 4 Ring of Fire lags
R = rd('ringfire_correlations.csv'); PC = rd('ringfire_positive_control.csv')
preds = ['RoF quake M6+ day', 'RoF quake M7+ day', 'NZ quake M5+ day', 'RoF tsunami event day', 'RoF new eruption day']
outs = ['crashes_all_6cty', 'fatal_crashes_FARS_9cty', 'oregon_quakes_500km_M2.5+']
def eb(ax, d, x, **k): v = d['pct_change']; ax.errorbar(x, v, yerr=[v - d.ci_lo, d.ci_hi - v], fmt='o', capsize=2, **k)
fig, axs = plt.subplots(1, 4, figsize=(18, 6))
for ax, o in zip(axs, outs):
    for i, p in enumerate(preds):
        d = R[(R.outcome == o) & (R.predictor == p)].sort_values('lag_days'); eb(ax, d, d.lag_days + (i - 2) * 0.12, ms=4, label=label(p))
    ax.axhline(0, color='k', lw=.8); ax.set_title(wrap(o, 32), fontsize=10); ax.set_xlabel('Days after the event'); ax.set_ylabel('% change vs. a normal day')
axs[0].legend(fontsize=7); ax = axs[3]; eb(ax, PC, PC.lag_days, color='crimson')
ax.axhline(0, color='k', lw=.8); ax.set_title('Method check: big (M7+) Ring of Fire quake\n→ Ring of Fire aftershocks M5+', fontsize=10); ax.set_xlabel('Days after the quake')
q = R.q_fdr.min() if 'q_fdr' in R else None
fig.suptitle('Do big Pacific "Ring of Fire" quakes, tsunamis or eruptions affect the Eugene area?' + (f'  (no link holds up; lowest chance of a fluke after correction = {q:.2f})' if q is not None else ''), fontsize=11)
caption(fig, "Dots are the % change on the days after each kind of event; lines show the 95% range, and lines that cross zero mean no clear effect. The red panel proves the method can spot a real effect (aftershocks).")
save(fig, 'chart_ringfire_lags.png', 120)
print('\n'.join(out))
