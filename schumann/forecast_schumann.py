#!/usr/bin/env python3
"""Forecast daily Schumann f1 / amplitude 1..14 days ahead; honest held-out validation.

Data: Vernadsky (Antarctica) daily means digitized from Zenodo 5919944 figures (ESTIMATES), 2002-2020.
Split: train 2002-03..2014-12, validation 2015 (model choice only), TEST 2016-01..2020-12 (never touched in fitting).
Baselines: persistence (last observed day), 7-day mean persistence, day-of-year climatology (train),
and climatology + damped anomaly (anomaly * AR coefficient^h fitted on train).
Models: ridge regression and gradient boosting with
  (a) SR history only (+season), (b) + solar/geomagnetic, (c) + moon, (d) + Eugene weather.
Features use only information available at the forecast origin t (moon/season at target day are deterministic).
"""
import os, json, numpy as np, pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(REPO, 'data'); OUT = os.path.join(REPO, 'reports', 'schumann')
TARGETS = ['ver_f1_ns', 'ver_f1_ew', 'ver_a1_ns', 'ver_a1_ew']
HORIZONS = [1, 2, 3, 5, 7, 10, 14, 27]
TRAIN_END, VAL_END = '2014-12-31', '2015-12-31'
SOLAR = ['F107_adj', 'sunspot_n', 'kp_max', 'Ap', 'Dst_min', 'AE_mean', 'omni_sw_V', 'omni_Bz', 'flares_MX', 'log_p10MeV_max']
WX = ['tmax_F', 'tmin_F', 'prcp_in', 'pressure_msl_hPa_era5']

def doy_clim(y, train_mask):
    s = y[train_mask]
    c = s.groupby(s.index.dayofyear).mean()
    c = c.reindex(range(1, 367)).interpolate(limit_direction='both')
    c = pd.concat([c.iloc[-30:], c, c.iloc[:30]]).rolling(31, center=True, min_periods=5).mean().iloc[30:-30]
    c.index = range(1, 367)
    return c

def features(Dd, tg, h, clim, groups):
    y = Dd[tg]; idx = Dd.index; tgt_day = idx + pd.Timedelta(days=h)
    F = pd.DataFrame(index=idx)
    cl_t = pd.Series(clim.reindex(idx.dayofyear).values, idx)
    cl_h = pd.Series(clim.reindex(tgt_day.dayofyear).values, idx)
    yf = y.ffill(limit=3)
    F['anom_t'] = yf - cl_t
    F['anom_t1'] = yf.shift(1) - cl_t.shift(1)
    F['anom_7'] = (y - cl_t).rolling(7, min_periods=3).mean()
    F['anom_30'] = (y - cl_t).rolling(30, min_periods=10).mean()
    F['anom_365'] = (y - cl_t).rolling(365, min_periods=100).mean()
    F['clim_h'] = cl_h
    F['doy_s'] = np.sin(2*np.pi*tgt_day.dayofyear/365.25); F['doy_c'] = np.cos(2*np.pi*tgt_day.dayofyear/365.25)
    if 'solar' in groups:
        for c in SOLAR:
            F[c] = Dd[c]; F[c + '_m7'] = Dd[c].rolling(7, min_periods=3).mean()
        F['F107_m81'] = Dd.F107_adj.rolling(81, min_periods=30).mean()
        F['kp_rec27'] = Dd.kp_max.shift(27 - h) if h < 27 else Dd.kp_max   # 27-day solar rotation recurrence
    if 'moon' in groups:
        md = Dd.moon_dist_km.shift(-h); mi = Dd.moon_illum.shift(-h); ma = Dd.moon_age_days.shift(-h)
        F['moon_dist_h'] = md; F['moon_illum_h'] = mi
        F['moon_age_s'] = np.sin(2*np.pi*ma/29.53); F['moon_age_c'] = np.cos(2*np.pi*ma/29.53)
    if 'wx' in groups:
        for c in WX: F[c] = Dd[c]
    target_anom = y.shift(-h) - cl_h
    return F, target_anom, cl_h

def main():
    Dd = pd.read_csv(os.path.join(D, 'schumann_daily.csv.gz'), index_col=0, parse_dates=True).asfreq('D')
    Dd = Dd[(Dd.index >= '2002-03-01') & (Dd.index <= '2020-12-31')]
    tr = Dd.index <= TRAIN_END; va = (Dd.index > TRAIN_END) & (Dd.index <= VAL_END); te = Dd.index > VAL_END
    res, preds = [], {}
    variants = {'hist': [], 'hist+solar': ['solar'], 'hist+solar+moon': ['solar', 'moon'], 'all(+wx)': ['solar', 'moon', 'wx']}
    for tg in TARGETS:
        clim = doy_clim(Dd[tg], tr)
        for h in HORIZONS:
            F0, ya, cl_h = features(Dd, tg, h, clim, [])
            ok = ya.notna() & F0.anom_t.notna()
            yt = ya + cl_h
            # baselines (predictions of the target value)
            phi = np.corrcoef(F0.anom_t[tr & ok], ya[tr & ok])[0, 1]
            base = {'persistence': Dd[tg].ffill(limit=3),
                    'persist_7d_mean': Dd[tg].rolling(7, min_periods=3).mean(),
                    'climatology': cl_h,
                    'clim+damped_anom': cl_h + phi * F0.anom_t}
            ev = te & ok
            for b, p in base.items():
                e = (yt - p)[ev].abs()
                res.append(dict(target=tg, h=h, model=b, mae=e.mean(), rmse=np.sqrt(((yt - p)[ev]**2).mean()), n=int(e.notna().sum())))
                if h in (1, 7): preds[(tg, h, b)] = p[ev]
            for vn, groups in variants.items():
                F, ya, cl_h = features(Dd, tg, h, clim, groups)
                fitm = tr & ok
                for mname, mdl in [('ridge', make_pipeline(SimpleImputer(), StandardScaler(), RidgeCV(alphas=np.logspace(-2, 4, 25)))),
                                   ('gbm', HistGradientBoostingRegressor(max_iter=300, learning_rate=0.04, max_leaf_nodes=15,
                                                                        min_samples_leaf=40, l2_regularization=1.0, random_state=0))]:
                    mdl.fit(F[fitm], ya[fitm])
                    pa = pd.Series(mdl.predict(F[ok]), F.index[ok])
                    p = pa + cl_h[ok]
                    for split, msk in [('val', va & ok), ('test', ev)]:
                        e = (yt - p)[msk]
                        res.append(dict(target=tg, h=h, model=f'{mname}:{vn}', split=split, mae=e.abs().mean(), rmse=np.sqrt((e**2).mean()), n=int(e.notna().sum())))
                    if h in (1, 7) and vn in ('hist', 'all(+wx)'): preds[(tg, h, f'{mname}:{vn}')] = p[ev]
                    if mname == 'ridge' and vn == 'all(+wx)':
                        coef = pd.Series(mdl[-1].coef_, F.columns)
                        res.append(dict(target=tg, h=h, model='_ridge_coefs', note=json.dumps(coef.round(5).to_dict())))
            print(tg, h, 'done', flush=True)
    R = pd.DataFrame(res); R['split'] = R['split'].fillna('test')
    # skill vs best baseline
    t = R[(R.split == 'test') & ~R.model.str.startswith('_')]
    bb = t[t.model.isin(['persistence', 'persist_7d_mean', 'climatology', 'clim+damped_anom'])].groupby(['target', 'h']).mae.min().rename('best_baseline_mae')
    pers = t[t.model == 'persistence'].set_index(['target', 'h']).mae.rename('persistence_mae')
    clm = t[t.model == 'climatology'].set_index(['target', 'h']).mae.rename('climatology_mae')
    t = t.join(bb, on=['target', 'h']).join(pers, on=['target', 'h']).join(clm, on=['target', 'h'])
    t['skill_vs_persistence'] = 1 - t.mae / t.persistence_mae
    t['skill_vs_climatology'] = 1 - t.mae / t.climatology_mae
    t['skill_vs_best_baseline'] = 1 - t.mae / t.best_baseline_mae
    t.round(5).to_csv(os.path.join(OUT, 'schumann_forecast_skill.csv'), index=False)
    R[R.split == 'val'].round(5).to_csv(os.path.join(OUT, 'schumann_forecast_validation.csv'), index=False)
    R[R.model == '_ridge_coefs'][['target', 'h', 'note']].to_csv(os.path.join(OUT, 'schumann_forecast_ridge_coefs.csv'), index=False)
    P = pd.DataFrame({f'{a}|{b}|{c}': v for (a, b, c), v in preds.items()})
    P['actual_ver_f1_ns'] = Dd.ver_f1_ns; P['actual_ver_f1_ew'] = Dd.ver_f1_ew; P['actual_ver_a1_ns'] = Dd.ver_a1_ns; P['actual_ver_a1_ew'] = Dd.ver_a1_ew
    P = P[P.index > VAL_END]
    P.round(5).to_csv(os.path.join(OUT, 'schumann_forecast_test_predictions.csv.gz'))
    pd.set_option('display.width', 250)
    print(t.pivot_table(index=['target', 'model'], columns='h', values='skill_vs_best_baseline').round(3).to_string())

if __name__ == '__main__':
    main()
