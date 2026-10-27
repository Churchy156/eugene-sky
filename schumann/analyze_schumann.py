#!/usr/bin/env python3
"""Schumann resonance (SR) correlation analysis. ALL SR values are image-digitized ESTIMATES.

Daily model (mirrors reports/incidents/analyze_ringfire.py): OLS of SR daily mean on one standardized
predictor (lag 0-3 d) + weekday, month, year, US-holiday fixed effects; HAC (Newey-West, 7 d) SEs;
Benjamini-Hochberg q across all daily tests.  Year FE removes the solar-cycle-scale signal, so a separate
'long-term' family (month FE + no year FE, HAC 60 d) tests slow solar drivers.
Hourly model: SR anomaly vs (year, month, UT-hour) means; drivers at lags 0..72 h; HAC 48 h; BH.
"""
import os, json, numpy as np, pandas as pd, statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(REPO, 'data'); OUT = os.path.join(REPO, 'reports', 'schumann')
os.makedirs(OUT, exist_ok=True)

TARGETS = {'ver_f1_ns': 'Vernadsky f1 NS (Hz)', 'ver_f1_ew': 'Vernadsky f1 EW (Hz)',
           'ver_a1_ns': 'Vernadsky A1 NS (rel dB)', 'ver_a1_ew': 'Vernadsky A1 EW (rel dB)',
           'sou_f1_ns': 'SOUSY f1 NS (Hz)', 'tomsk_F1': 'Tomsk F1 (Hz)', 'tomsk_A1': 'Tomsk A1 (rel)'}
PRED = ['sunspot_n', 'F107_adj', 'flares_MX', 'flare_max_class', 'kp_max', 'Ap', 'Dst_min', 'AE_mean',
        'omni_sw_V', 'omni_Bz', 'omni_sw_P', 'log_p10MeV_max', 'moon_illum', 'moon_dist_km',
        'tmax_F', 'tmin_F', 'prcp_in', 'pressure_msl_hPa_era5']
LONG_PRED = ['sunspot_n', 'F107_adj']

def fe_design(idx, year=True, hol=None):
    X = pd.DataFrame(index=idx)
    X = X.join(pd.get_dummies(idx.dayofweek, prefix='dow', drop_first=True).set_index(idx).astype(float))
    X = X.join(pd.get_dummies(idx.month, prefix='m', drop_first=True).set_index(idx).astype(float))
    if year:
        X = X.join(pd.get_dummies(idx.year, prefix='y', drop_first=True).set_index(idx).astype(float))
    else:
        X['trend'] = (idx - idx[0]).days / 3652.5
    if hol is not None: X['holiday'] = hol.reindex(idx).fillna(0).astype(float).values
    return X

def fit(y, x, year=True, hac=7, hol=None):
    m = y.notna() & x.notna()
    if m.sum() < 60: return None
    yy, xx = y[m], x[m]
    xs = (xx - xx.mean()) / xx.std()
    if xs.std() == 0 or not np.isfinite(xs.std()): return None
    X = fe_design(yy.index, year, hol if hol is not None else None)
    X.insert(0, 'x', xs.values); X = sm.add_constant(X, has_constant='add')
    X = X.loc[:, X.std() > 0].assign(const=1.0)
    r = sm.OLS(yy.values, X.values).fit(cov_type='HAC', cov_kwds={'maxlags': hac})
    i = list(X.columns).index('x')
    b, se, p = r.params[i], r.bse[i], r.pvalues[i]
    t = b / se; dfree = r.df_resid
    return dict(beta_per_sd=b, ci_lo=b - 1.96*se, ci_hi=b + 1.96*se, p=p,
                partial_r=t/np.sqrt(t*t + dfree), n_days=int(m.sum()),
                start=str(yy.index.min().date()), end=str(yy.index.max().date()))

def main():
    Dd = pd.read_csv(os.path.join(D, 'schumann_daily.csv.gz'), index_col=0, parse_dates=True)
    Dd = Dd.asfreq('D')
    hol = Dd.get('ev_us_holiday')
    rows = []
    for tg in TARGETS:
        if tg not in Dd or Dd[tg].notna().sum() < 60: continue
        y = Dd[tg]
        for pr in PRED:
            if pr not in Dd: continue
            for L in range(4):
                r = fit(y, Dd[pr].shift(L), True, 7, hol)
                if r: rows.append(dict(family='daily', target=tg, predictor=pr, lag=L, **r))
    R = pd.DataFrame(rows)
    R['q_fdr'] = multipletests(R.p, method='fdr_bh')[1]
    # long-term family: monthly means, no year FE
    rows = []
    M = Dd.resample('MS').mean(numeric_only=True)
    for tg in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew', 'sou_f1_ns']:
        for pr in LONG_PRED:
            y = M[tg]; x = M[pr]; m = y.notna() & x.notna()
            if m.sum() < 24: continue
            mo = pd.get_dummies(M.index[m].month, prefix='m', drop_first=True).astype(float)
            X = sm.add_constant(pd.concat([((x[m]-x[m].mean())/x[m].std()).reset_index(drop=True), mo], axis=1))
            fr = sm.OLS(y[m].values, X.values).fit(cov_type='HAC', cov_kwds={'maxlags': 12})
            b, se = fr.params[1], fr.bse[1]; t = b/se
            rows.append(dict(family='monthly_longterm', target=tg, predictor=pr, lag=0, beta_per_sd=b, ci_lo=b-1.96*se,
                             ci_hi=b+1.96*se, p=fr.pvalues[1], partial_r=t/np.sqrt(t*t+fr.df_resid), n_days=int(m.sum()),
                             start=str(y[m].index.min().date()), end=str(y[m].index.max().date())))
    RL = pd.DataFrame(rows); RL['q_fdr'] = multipletests(RL.p, method='fdr_bh')[1]
    # hourly family
    H = pd.read_csv(os.path.join(D, 'schumann_hourly_drivers.csv.gz'), index_col=0, parse_dates=True).asfreq('h')
    HP = ['Kp', 'Dst', 'AE', 'sw_V', 'Bz_gsm', 'sw_P', 'log_p10MeV', 'f107']
    rows = []
    for tg in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']:
        y = H[tg]
        an = y - y.groupby([y.index.year, y.index.month, y.index.hour]).transform('mean')
        for pr in HP:
            for L in [0, 1, 3, 6, 12, 24, 48, 72]:
                x = H[pr].shift(L); m = an.notna() & x.notna()
                if m.sum() < 500: continue
                xs = (x[m]-x[m].mean())/x[m].std()
                fr = sm.OLS(an[m].values, sm.add_constant(xs.values)).fit(cov_type='HAC', cov_kwds={'maxlags': 48})
                b, se = fr.params[1], fr.bse[1]; t = b/se
                rows.append(dict(family='hourly', target=tg, predictor=pr, lag=L, beta_per_sd=b, ci_lo=b-1.96*se, ci_hi=b+1.96*se,
                                 p=fr.pvalues[1], partial_r=t/np.sqrt(t*t+fr.df_resid), n_days=int(m.sum()),
                                 start=str(an[m].index.min()), end=str(an[m].index.max())))
    RH = pd.DataFrame(rows); RH['q_fdr'] = multipletests(RH.p, method='fdr_bh')[1]
    ALL = pd.concat([R, RL, RH], ignore_index=True)
    ALL['q_fdr_all'] = multipletests(ALL.p, method='fdr_bh')[1]
    ALL['target_label'] = ALL.target.map(TARGETS)
    ALL.round(6).sort_values(['family', 'p']).to_csv(os.path.join(OUT, 'schumann_correlations.csv'), index=False)
    # diurnal cycle
    di = []
    for tg in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew', 'sou_f1_ns', 'sou_f1_ew', 'tomsk_F1', 'tomsk_A1', 'tomsk_F2', 'tomsk_Q1']:
        if tg not in H: continue
        s = H[tg].dropna()
        if len(s) < 200: continue
        season = s.index.month.map({12: 'DJF', 1: 'DJF', 2: 'DJF', 3: 'MAM', 4: 'MAM', 5: 'MAM', 6: 'JJA', 7: 'JJA', 8: 'JJA', 9: 'SON', 10: 'SON', 11: 'SON'})
        g = s.groupby([season, s.index.hour]).agg(['mean', 'std', 'count'])
        for (se, hr), r in g.iterrows():
            di.append(dict(series=tg, season=se, hour_utc=hr, mean=r['mean'], sd=r['std'], n=int(r['count'])))
        for hr, r in s.groupby(s.index.hour).agg(['mean', 'std', 'count']).iterrows():
            di.append(dict(series=tg, season='ALL', hour_utc=hr, mean=r['mean'], sd=r['std'], n=int(r['count'])))
    pd.DataFrame(di).round(5).to_csv(os.path.join(OUT, 'schumann_diurnal.csv'), index=False)
    # superposed epoch: proton events (>=10 pfu at >10 MeV) and Kp>=7 storms, f1 daily anomaly (vs 61d centred median)
    ep = []
    for ev, cond in [('proton_event_10pfu', Dd.log_p10MeV_max >= 1), ('storm_Kp7', Dd.omni_Kp_max >= 7), ('X_flare_day', Dd.flares_X > 0)]:
        on = cond & ~cond.shift(1, fill_value=False)
        days = Dd.index[on.fillna(False)]
        for tg in ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']:
            an = Dd[tg] - Dd[tg].rolling(61, center=True, min_periods=20).median()
            for L in range(-5, 11):
                v = an.reindex(days + pd.Timedelta(days=L)).dropna()
                if len(v) < 3: continue
                ep.append(dict(event=ev, target=tg, lag=L, mean_anom=v.mean(), se=v.std()/np.sqrt(len(v)), n_events=len(v)))
    pd.DataFrame(ep).round(5).to_csv(os.path.join(OUT, 'schumann_epoch.csv'), index=False)
    print(ALL.groupby('family').apply(lambda g: pd.Series({'tests': len(g), 'p<0.05': (g.p < .05).sum(), 'q<0.05': (g.q_fdr < .05).sum()})))
    for fam in ['daily', 'monthly_longterm', 'hourly']:
        print('\n==', fam); print(ALL[ALL.family == fam].sort_values('p').head(25)[['target', 'predictor', 'lag', 'beta_per_sd', 'ci_lo', 'ci_hi', 'partial_r', 'p', 'q_fdr', 'n_days']].round(5).to_string())

if __name__ == '__main__':
    main()
