"""Block-bootstrap test (30-day blocks) of MAE gain of each model over the best baseline on the 2016-2020 test set."""
import os, numpy as np, pandas as pd
R = os.path.join(os.path.dirname(__file__), '..', 'reports', 'schumann')
p = pd.read_csv(os.path.join(R, 'schumann_forecast_test_predictions.csv.gz'), parse_dates=['date']).set_index('date').asfreq('D')
BASE = ['persistence', 'persist_7d_mean', 'climatology', 'clim+damped_anom']
rng = np.random.default_rng(0); rows = []
for col in p.columns:
    if '|' not in col: continue
    t, h, m = col.split('|')
    if m in BASE: continue
    a = p['actual_' + t].shift(-int(h))   # rows are forecast origin dates; verify at origin+h
    bm = min(BASE, key=lambda b: (p[f'{t}|{h}|{b}'] - a).abs().mean())
    e1 = (p[col] - a).abs(); e0 = (p[f'{t}|{h}|{bm}'] - a).abs()
    ok = e1.notna() & e0.notna(); d = (e0 - e1)[ok].values; n = len(d); B = 30
    starts = np.arange(0, n - B)
    boots = []
    for _ in range(2000):
        idx = np.concatenate([np.arange(s, s + B) for s in rng.choice(starts, n // B + 1)])[:n]
        boots.append(d[idx].mean())
    boots = np.array(boots)
    if m == 'ridge:all(+wx)':   # does adding solar+moon+weather beat history-only ridge?
        e2 = (p[f'{t}|{h}|ridge:hist'] - a).abs(); d2 = (e2 - e1)[ok & e2.notna()].values
        b2 = np.array([d2[np.concatenate([np.arange(s, s + B) for s in rng.choice(np.arange(len(d2) - B), len(d2) // B + 1)])[:len(d2)]].mean() for _ in range(2000)])
        rows.append(dict(target=t, h=int(h), model='ridge:all vs ridge:hist', best_baseline='ridge:hist', mae_model=e1[ok].mean(), mae_baseline=e2[ok].mean(),
                         skill=1 - e1[ok].mean() / e2[ok].mean(), gain_ci_lo=np.percentile(b2, 2.5), gain_ci_hi=np.percentile(b2, 97.5), p_one_sided=(b2 <= 0).mean(), n=len(d2)))
    rows.append(dict(target=t, h=int(h), model=m, best_baseline=bm, mae_model=e1[ok].mean(), mae_baseline=e0[ok].mean(),
                     skill=1 - e1[ok].mean() / e0[ok].mean(), gain_ci_lo=np.percentile(boots, 2.5), gain_ci_hi=np.percentile(boots, 97.5),
                     p_one_sided=(boots <= 0).mean(), n=n))
o = pd.DataFrame(rows).sort_values(['target', 'h', 'model'])
o.round(5).to_csv(os.path.join(R, 'schumann_forecast_significance.csv'), index=False)
print(o.round(4).to_string())
