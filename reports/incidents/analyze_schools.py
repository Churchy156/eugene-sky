"""School calendars (9 local districts) and high-school home games vs Lane County crashes and police calls.
Same-day tests, quasi-Poisson GLM (scale=X2).
 S  = school-year weekdays (Mon-Fri, Sep-Jun): controls day-of-week x month, year, US holiday, weather (rain, tmin, tmax, pressure).
 F  = fall Fridays only (Sep-Nov): controls month, year, holiday, weather.
 A  = all days: controls day-of-week x month, year, holiday, weather.
Benjamini-Hochberg q-values across every test.  Dates are Pacific Time calendar days."""
import os, sys, warnings, pandas as pd, numpy as np, statsmodels.api as sm, holidays
from statsmodels.stats.multitest import multipletests
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
REPO = '/workspace/eugene-sky'; sys.path.insert(0, REPO)
from labels import label, caption
e = pd.read_csv(os.path.join(REPO, 'data/eugene_env_daily.csv.gz'), parse_dates=['date'], low_memory=False).set_index('date')
Y = pd.read_csv('incidents_daily_counts.csv', parse_dates=['date']).set_index('date')
OUT = {'crashes_lane': 'Crashes, Lane County', 'crashes_injury_fatal_6cty': 'Injury & deadly crashes, 6 counties',
       'eugene_police_calls': 'Eugene police calls', 'springfield_police_calls': 'Springfield police calls'}
hol = holidays.US(years=range(1975, 2028))
W = pd.DataFrame({'w_rain': e.prcp_in, 'w_tmin': e.tmin_F, 'w_tmax': e.tmax_F, 'w_press': e.pressure_msl_hPa_era5})
idx = e.index; wk = idx.dayofweek < 5; sy_months = idx.month.isin([9, 10, 11, 12, 1, 2, 3, 4, 5, 6])
s4 = e.school_4j_in_session
out4 = ((s4 == 0) & wk & (e.districts_out_count > 0)).astype(float)          # 4J weekday off inside the school year (approx: some district out)
# one-off days off: 4J off today but in class both the previous and next school weekday (teacher / in-service / single holidays)
prev_in = s4.shift(1).where(idx.dayofweek != 0, s4.shift(3)); next_in = s4.shift(-1).where(idx.dayofweek != 4, s4.shift(-3))
oneoff = ((s4 == 0) & (prev_in == 1) & (next_in == 1)).astype(float)
xmas = (idx.month == 12) & (idx.day >= 18) | (idx.month == 1) & (idx.day <= 5)
real4 = e.school_calendar_real_count
P = [  # (name, x, spec, day filter)
 ('school_in_session',      s4,                         'S', wk & sy_months),
 ('school_in_session (no Christmas-New Year)', s4,      'S', wk & sy_months & ~xmas),
 ('schools_in_session_count (per district)', e.schools_in_session_count, 'S', wk & sy_months),
 ('one-off weekday off (4J)', oneoff,                   'S', wk & sy_months & ((s4 == 1) | (oneoff == 1))),
 ('early_release_any',      e.early_release_any,        'S', wk & sy_months & (e.schools_in_session_count > 0) & (real4 > 0)),
 ('hs_football_friday',     e.hs_football_friday,       'F', None),
 ('hs_football_friday (Sep 1-Nov 15, no Black Friday)', e.hs_football_friday, 'F', ~((idx.month == 11) & (idx.day > 15))),
 ('hs_home_football (per game, fall Fridays)', e.hs_home_football, 'F', None),
 ('hs_football_friday -> next day (Sat)', e.hs_football_friday.shift(1), 'Fs', None),
 ('hs_home_games (per game)', e.hs_home_games,          'A', None),
 ('hs_home_basketball (per game)', e.hs_home_basketball, 'A', None),
 ('hs_rivalry_game',        (e.hs_rivalry_game > 0).astype(float).where(e.hs_rivalry_game.notna()), 'A', None),
 ('hs_playoff_home_games',  (e.hs_playoff_home_games > 0).astype(float).where(e.hs_playoff_home_games.notna()), 'A', None),
]
def fit(y, x, spec, filt):
    df = pd.DataFrame({'y': y}).join(x.rename('x')).join(W)
    if filt is not None: df = df[pd.Series(filt, index=idx).reindex(df.index).fillna(False).values]
    df = df.dropna()
    if spec == 'F': df = df[(df.index.dayofweek == 4) & df.index.month.isin([9, 10, 11])]
    if spec == 'Fs': df = df[(df.index.dayofweek == 5) & df.index.month.isin([9, 10, 11])]
    if len(df) < 60 or df.x.std() == 0: return None
    binary = set(df.x.unique()) <= {0, 1}
    if binary and (df.x.sum() < 8 or (1 - df.x).sum() < 8): return None
    X = pd.DataFrame({'x': df.x.astype(float)}, index=df.index)
    if spec in ('S', 'A'):
        X = X.join(pd.get_dummies(pd.Series(df.index.dayofweek.astype(str) + '_' + df.index.month.astype(str), index=df.index), prefix='dm', drop_first=True, dtype=float))
    else: X = X.join(pd.get_dummies(pd.Series(df.index.month, index=df.index), prefix='m', drop_first=True, dtype=float))
    if df.index.year.nunique() > 1: X = X.join(pd.get_dummies(pd.Series(df.index.year, index=df.index), prefix='y', drop_first=True, dtype=float))
    X = X.join((df[W.columns] - df[W.columns].mean()) / df[W.columns].std())
    X['holiday'] = [float(d in hol) for d in df.index]
    X = sm.add_constant(X.loc[:, (X.std() > 0) | (X.columns == 'x')].astype(float), has_constant='add')
    r = sm.GLM(df.y.astype(float).values, X.values, family=sm.families.Poisson()).fit(scale='X2')
    b, se, p = r.params[1], r.bse[1], r.pvalues[1]
    return dict(kind='yes/no' if binary else 'per unit', pct_change=100 * (np.exp(b) - 1), ci_lo=100 * (np.exp(b - 1.96 * se) - 1),
                ci_hi=100 * (np.exp(b + 1.96 * se) - 1), p=p, n_days=len(df), n_event_days=int(df.x.sum()) if binary else int((df.x > 0).sum()),
                start=str(df.index.min().date()), end=str(df.index.max().date()), mean_daily=df.y.mean())
rows = []
for yn in OUT:
    for pn, x, spec, filt in P:
        r = fit(Y[yn], x, spec, filt)
        if r: rows.append(dict(outcome=yn, predictor=pn, spec=spec, **r))
R = pd.DataFrame(rows); R['q_BH'] = multipletests(R.p, method='fdr_bh')[1]
R.round(4).to_csv('school_correlations.csv', index=False)
with open('schools_out.txt', 'w') as f:
    f.write(__doc__ + '\n\n' + R.sort_values('p').round(4).to_string(index=False) + '\n')
print(R.sort_values('p').round(4).to_string(index=False))

# ---------- charts ----------
NICE = {'school_in_session': 'School day vs weekday off (Eugene 4J)', 'school_in_session (no Christmas-New Year)': 'School day vs weekday off, leaving out Christmas–New Year',
        'schools_in_session_count (per district)': 'Each extra district in class', 'one-off weekday off (4J)': 'Single day off (teacher/holiday) vs school day',
        'early_release_any': 'Early-release day vs normal school day', 'hs_football_friday': 'HS football Friday vs other fall Fridays',
        'hs_football_friday -> next day (Sat)': 'Saturday after HS football Friday',
        'hs_football_friday (Sep 1-Nov 15, no Black Friday)': 'HS football Friday, Sep 1–Nov 15 only', 'hs_home_football (per game, fall Fridays)': 'Each extra HS football game on a fall Friday', 'hs_home_games (per game)': 'Each extra HS home game',
        'hs_home_basketball (per game)': 'Each extra HS home basketball game', 'hs_rivalry_game': 'Big HS rivalry game day', 'hs_playoff_home_games': 'HS playoff game hosted locally'}
C = {'crashes_lane': '#1f77b4', 'crashes_injury_fatal_6cty': '#d62728', 'eugene_police_calls': '#2ca02c', 'springfield_police_calls': '#9467bd'}
preds = [p for p, *_ in P if p in set(R.predictor)]
fig, ax = plt.subplots(figsize=(11, 0.62 * len(preds) * 1.25 + 1.6))
off = {k: (i - 1.5) * 0.18 for i, k in enumerate(OUT)}
for i, pn in enumerate(preds):
    for yn in OUT:
        r = R[(R.predictor == pn) & (R.outcome == yn)]
        if not len(r): continue
        r = r.iloc[0]; yv = i + off[yn]; sig = r.q_BH < 0.05
        ax.errorbar(r['pct_change'], yv, xerr=[[r['pct_change'] - r.ci_lo], [r.ci_hi - r['pct_change']]], fmt='o', color=C[yn],
                    mfc=C[yn] if sig else 'white', ms=6, capsize=2, lw=1.2, label=OUT[yn] if i == 0 else None)
ax.axvline(0, color='k', lw=0.8); ax.set_yticks(range(len(preds))); ax.set_yticklabels([NICE[p] for p in preds]); ax.invert_yaxis()
ax.set_xlabel('% more (+) or fewer (−) incidents that day, after controls'); ax.grid(axis='x', alpha=0.3)
ax.set_title('School days and high-school games vs crashes and police calls')
ax.legend(loc='lower right', fontsize=8.5, title='Filled dot = holds up after correcting for many tests (q<0.05)', title_fontsize=8)
caption(fig, 'Each dot compares like with like (same weekday, month, year, holidays, weather); bars are 95% ranges; filled dots survive multiple-test correction.')
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig('chart_schools_effects.png', dpi=130); plt.close(fig)

# raw averages by type of weekday (school year), Lane crashes and Eugene police calls
cat = pd.Series(np.nan, index=idx, dtype=object)
cat[wk & sy_months & (s4 == 1) & (e.early_release_any == 0)] = 'School day'
cat[wk & sy_months & (s4 == 1) & (e.early_release_any == 1)] = 'Early-release day'
cat[wk & sy_months & (oneoff == 1)] = 'Single day off'
cat[wk & sy_months & (s4 == 0) & (oneoff == 0) & ~xmas & (e.districts_out_count > 0)] = 'Break (not Christmas)'
cat[wk & sy_months & (s4 == 0) & xmas] = 'Christmas–New Year break'
cat[wk & idx.month.isin([7])] = 'Summer weekday (July)'
order = ['School day', 'Early-release day', 'Single day off', 'Break (not Christmas)', 'Christmas–New Year break', 'Summer weekday (July)']
fig, axs = plt.subplots(1, 2, figsize=(13, 5.2))
for ax, yn in zip(axs, ['crashes_lane', 'eugene_police_calls']):
    d = pd.DataFrame({'y': Y[yn], 'c': cat}).dropna(); m = d.groupby('c').y.agg(['mean', 'sem', 'size']).reindex(order).dropna()
    ax.bar(range(len(m)), m['mean'], yerr=1.96 * m['sem'], color=C[yn], alpha=0.8, capsize=3)
    ax.set_xticks(range(len(m))); ax.set_xticklabels([f"{k.replace(' (', chr(10)+'(').replace('–New Year', '–\nNew Year').replace('-release', '-\nrelease')}\n{int(n)} days"  for k, n in zip(m.index, m['size'])], fontsize=8)
    ax.set_title(f'{OUT[yn]} per weekday ({d.index.min().year}–{d.index.max().year})', fontsize=10.5); ax.set_ylabel('average per day')
    lo = m['mean'].min() * 0.85; ax.set_ylim(lo, m['mean'].max() * 1.08)
caption(fig, 'Plain averages (no controls) on weekdays by school status; note the y-axis does not start at zero. See the dot chart for controlled comparisons.')
fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig('chart_schools_weekday_types.png', dpi=130); plt.close(fig)

# HS football Fridays vs other fall Fridays
ff = (idx.dayofweek == 4) & idx.month.isin([9, 10, 11]) & e.hs_football_friday.notna().values
fig, axs = plt.subplots(1, 4, figsize=(13, 4))
for ax, yn in zip(axs, OUT):
    d = pd.DataFrame({'y': Y[yn], 'g': e.hs_football_friday})[ff].dropna()
    m = d.groupby('g').y.agg(['mean', 'sem', 'size'])
    ax.bar([0, 1], m['mean'].reindex([0, 1]), yerr=1.96 * m['sem'].reindex([0, 1]), color=['#bbbbbb', C[yn]], capsize=3)
    ax.set_xticks([0, 1]); ax.set_xticklabels([f'No HS home game\n({int(m["size"].get(0, 0))} Fridays)', f'HS football night\n({int(m["size"].get(1, 0))} Fridays)'], fontsize=8)
    r = R[(R.predictor == 'hs_football_friday') & (R.outcome == yn)]
    t = f'{r['pct_change'].iloc[0]:+.0f}% after controls (q={r.q_BH.iloc[0]:.2f})' if len(r) else ''
    ax.set_title(f'{OUT[yn]}\n{t}', fontsize=9.5); lo = m['mean'].min() * 0.8; ax.set_ylim(lo, m['mean'].max() * 1.12)
caption(fig, 'Fall Fridays with vs without a local HS home football game (bars = plain averages). The gap disappears once late-November/Black Friday is left out, so it is a calendar effect, not football.')
fig.tight_layout(rect=(0, 0.06, 1, 1)); fig.savefig('chart_hs_football_fridays.png', dpi=130); plt.close(fig)
print('charts written')

# ================= schools.html page (published at /incidents/schools.html) =================
import shutil, html, datetime as dt
from zoneinfo import ZoneInfo
def get(pn, yn):
    r = R[(R.predictor == pn) & (R.outcome == yn)]
    return r.iloc[0] if len(r) else None
def say(pn, yn):
    r = get(pn, yn)
    if r is None: return 'not enough days to test'
    f_ = '+.1f' if r['kind'] == 'per unit' else '+.0f'
    return f"{r['pct_change']:{f_}}% (range {r.ci_lo:{f_}}% to {r.ci_hi:{f_}}%){' — holds up' if r.q_BH < 0.05 else ' — not reliable'}"
nsig = int((R.q_BH < 0.05).sum()); nraw = int((R.p < 0.05).sum())
cov = pd.read_csv(os.path.join(REPO, 'data/school_calendar_coverage.csv'))
NM = {'4j': 'Eugene 4J', 'bethel': 'Bethel', 'springfield': 'Springfield', 'junction_city': 'Junction City', 'monroe': 'Monroe', 'harrisburg': 'Harrisburg',
      'creswell': 'Creswell', 'pleasant_hill': 'Pleasant Hill', 'south_lane': 'South Lane (Cottage Grove)'}
def yrs(k):
    s = sorted(int(x[:4]) for x in cov[cov.district_key == k].school_year)
    if not s: return 'none (estimated rule for all years)'
    runs, a = [], s[0]
    for i in range(1, len(s) + 1):
        if i == len(s) or s[i] != s[i - 1] + 1:
            b = s[i - 1]; runs.append(f'{a}-{str(a+1)[2:]}' if a == b else f'{a}-{str(a+1)[2:]} to {b}-{str(b+1)[2:]}')
            if i < len(s): a = s[i]
    return ', '.join(runs)
hs = pd.read_csv(os.path.join(REPO, 'data/hs_sports_games.csv'), dtype=str)
now = dt.datetime.now(ZoneInfo('America/Los_Angeles'))
top = R[R.q_BH < 0.05].sort_values('p')
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>School days, high-school games and crashes — Eugene</title>
<style>body{{font-family:system-ui,sans-serif;background:#10151c;color:#e9edf2;max-width:1100px;margin:0 auto;padding:16px;line-height:1.5}}a{{color:#74c0fc}}
img{{width:100%;background:#fff;border-radius:8px;margin:8px 0}}table{{border-collapse:collapse;margin:8px 0}}td,th{{border:1px solid #334;padding:4px 10px;text-align:left}}
.box{{background:#1a2230;border-radius:10px;padding:12px 16px;margin:14px 0}}.note{{font-size:14px;opacity:.85}}</style></head><body>
<p><a href="../">← Eugene dashboard</a> · <a href="sports.html">Ducks &amp; Beavers games →</a></p>
<h1>🏫🏈 School days &amp; high-school games vs crashes &amp; police calls</h1>
<p class="note">Updated {now:%b %d, %Y %I:%M %p} PT. All dates are Pacific Time calendar days. 9 districts: Eugene 4J, Bethel, Springfield, Junction City, Monroe, Harrisburg, Creswell, Pleasant Hill, South Lane (Cottage Grove). 13 high schools.</p>
<div class="box"><b>Short answer:</b> Lane County has <b>more crashes on school days</b> than on weekdays when schools are off — about {get('school_in_session','crashes_lane')['pct_change']:.0f}% more, even after matching the same weekday, month, year, holidays and weather, and even leaving out the Christmas–New Year break.
Injury crashes go up too, by less. <b>Police calls don't change</b> with school days. High-school football nights looked like they had more injury crashes, but that turned out to be a <b>calendar effect</b> (the Fridays with no game are mostly in late November and Black Friday) — it disappears when those are left out.
We ran {len(R)} comparisons; {nsig} held up after correcting for running so many tests ({nraw} looked interesting on their own).</div>
<h2>What we found</h2><ul>
<li><b>School day vs weekday off (Eugene 4J):</b> Lane crashes {say('school_in_session','crashes_lane')}; injury &amp; deadly crashes {say('school_in_session','crashes_injury_fatal_6cty')}; Eugene police calls {say('school_in_session','eugene_police_calls')}.</li>
<li><b>Same thing, leaving out Christmas–New Year:</b> Lane crashes {say('school_in_session (no Christmas-New Year)','crashes_lane')}.</li>
<li><b>Each extra district in class</b> (0–9): Lane crashes {say('schools_in_session_count (per district)','crashes_lane')}.</li>
<li><b>Single days off</b> (teacher/in-service days, one-day holidays) vs school days: Lane crashes {say('one-off weekday off (4J)','crashes_lane')}; Eugene police calls {say('one-off weekday off (4J)','eugene_police_calls')}.</li>
<li><b>Early-release days</b> vs normal school days: Lane crashes {say('early_release_any','crashes_lane')}; injury crashes {say('early_release_any','crashes_injury_fatal_6cty')}.</li>
<li><b>HS football Friday vs other fall Fridays:</b> injury &amp; deadly crashes {say('hs_football_friday','crashes_injury_fatal_6cty')} — but Sep 1–Nov 15 only: {say('hs_football_friday (Sep 1-Nov 15, no Black Friday)','crashes_injury_fatal_6cty')}, and more games on a Friday doesn't mean more crashes ({say('hs_home_football (per game, fall Fridays)','crashes_injury_fatal_6cty')} per game). Too few no-game Fridays in the police-call years to test.</li>
<li><b>Each extra HS home game</b> (any sport): injury crashes {say('hs_home_games (per game)','crashes_injury_fatal_6cty')} per game — small, and most likely just "school-season days are busier".</li>
<li><b>Big rivalry games</b> (e.g. Thurston–Springfield, Sheldon–South Eugene): Lane crashes {say('hs_rivalry_game','crashes_lane')}; <b>locally hosted playoff games:</b> injury crashes {say('hs_playoff_home_games','crashes_injury_fatal_6cty')}.</li></ul>
<h2>Charts</h2>
<img src="chart_schools_effects.png" alt="dot chart of effects"><p class="note">Each dot compares like with like (same weekday, month, year, holidays, weather); filled dots survive multiple-test correction.</p>
<img src="chart_schools_weekday_types.png" alt="averages by weekday type"><p class="note">Plain averages on weekdays by school status (no controls; y-axis doesn't start at zero).</p>
<img src="chart_hs_football_fridays.png" alt="HS football Fridays"><p class="note">Fall Fridays with vs without a local HS home football game; the gap is a late-November calendar effect.</p>
<h2>Where the school calendars come from</h2>
<p class="note">Real published district calendars (current district websites and older copies saved in the Internet Archive's Wayback Machine). Years with no calendar found use an <b>estimated</b> rule (Wed after Labor Day to mid-June, Thanksgiving Wed–Fri, Dec 21–Jan 3, late-March spring break, federal Monday holidays).</p>
<table><tr><th>District</th><th>School years with a real calendar</th></tr>{''.join(f'<tr><td>{NM[k]}</td><td>{yrs(k)}</td></tr>' for k in NM)}</table>
<p class="note">High-school games: {len(hs):,} varsity home games ({hs.date.min()} to {hs.date.max()}) from MaxPreps schedules — football, boys &amp; girls basketball and soccer, volleyball, baseball, softball — at Sheldon, South Eugene, Churchill, North Eugene, Willamette, Thurston, Springfield, Junction City, Monroe, Harrisburg, Creswell, Pleasant Hill and Cottage Grove, plus locally held neutral-site tournament games. Early seasons (2005–07) are thinner.</p>
<h2>How this was done</h2>
<p class="note">Outcomes: ODOT crashes 2007–2024 (Lane County; injury &amp; deadly crashes in Lane, Linn, Benton, Douglas, Marion, Lincoln) and Eugene/Springfield police calls (Jan 2023–Oct 2026). Quasi-Poisson regression on daily counts. School-day tests use only weekdays in Sep–Jun and control for weekday×month, year, US holidays and weather (rain, low/high temperature, air pressure). Football-Friday tests use only fall Fridays (controls: month, year, holiday, weather). Benjamini–Hochberg correction across all {len(R)} tests ("holds up" = q &lt; 0.05). Full results: <a href="school_correlations.csv">school_correlations.csv</a>. Data columns are in the main dataset (schools_in_session_count, school_4j_in_session, districts_out_count, early_release_any, hs_home_games, hs_football_friday, hs_rivalry_game, …).</p>
</body></html>"""
open('schools.html', 'w', encoding='utf-8').write(page)
D = os.path.join(REPO, 'reports/incidents')
for f in ['schools.html', 'school_correlations.csv', 'schools_out.txt', 'chart_schools_effects.png', 'chart_schools_weekday_types.png', 'chart_hs_football_fridays.png', 'analyze_schools.py']:
    shutil.copy(f, os.path.join(D, f))
print('page written')
