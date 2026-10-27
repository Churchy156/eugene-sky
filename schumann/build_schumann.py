#!/usr/bin/env python3
"""Build Schumann-resonance (SR) hourly/daily datasets + predictors.

Inputs (box-local raw dirs, not in repo):
  vern_hourly.csv / sou_hourly.csv  from digitize_vernadsky.py (Zenodo 5919944, CC-BY-4.0)
  tomsk_hourly_raw.csv              from digitize_tomsk.py (Wayback + live sos70.ru charts)
  omni2_YYYY.dat                    NASA OMNI2 hourly (Kp, Dst, AE, SW, protons, F10.7, R)
  data/eugene_env_daily.csv.gz      repo daily dataset (sunspots, F10.7, flares, moon, Eugene weather)
Outputs (repo):
  data/schumann_vernadsky_hourly.csv.gz, data/schumann_sousy_hourly.csv.gz,
  data/schumann_tomsk_hourly.csv.gz, data/schumann_daily.csv.gz, data/schumann_hourly_drivers.csv.gz
All SR values are ESTIMATES digitized from published images.
"""
import os, glob, numpy as np, pandas as pd, ephem
RAW = os.environ.get('SR_RAW', '/workspace/sr_raw')
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(REPO, 'data')

def qa_station(df, has_amp=True):
    d = df.copy()
    for c in ('ns', 'ew'):
        bad = (d[f'f1_{c}_cov'] < 0.5) | (d[f'f1_{c}_clipfrac'] > 0.3)
        d.loc[bad, f'f1_{c}'] = np.nan
        if has_amp and f'a1_{c}' in d:
            # channel dead: 7-8 Hz power at the colormap floor (e.g. Vernadsky NS Aug 2009-Apr 2010) -> f1 is meaningless too
            dead = d[f'a1_{c}'] <= -33.0
            d.loc[dead, f'f1_{c}'] = np.nan
            badA = dead |  (d[f'a1_{c}'] >= 4.0) | (d[f'badfrac_{c}'] > 0.05) | (d[f'bg_{c}'] > -20)
            for k in ('a1', 'a2', 'a3'):
                d.loc[badA, f'{k}_{c}'] = np.nan
            d[f'amp_flag_{c}'] = badA.astype(int)
    # outliers vs 30-day rolling median of the same UT hour (robust 6 MAD)
    for c in ('f1_ns', 'f1_ew'):
        s = d[c]
        med = s.groupby(s.index.hour).transform(lambda x: x.rolling(30, center=True, min_periods=10).median())
        res = s - med
        mad = res.abs().rolling(24*60, center=True, min_periods=200).median()
        d.loc[res.abs() > 6*1.4826*mad, c] = np.nan
    return d

def load_omni():
    cols = {16: 'Bz_gsm', 23: 'sw_N', 24: 'sw_V', 28: 'sw_P', 38: 'Kp10', 39: 'R', 40: 'Dst', 41: 'AE', 45: 'p10MeV', 49: 'ap', 50: 'f107'}
    fills = {'Bz_gsm': 999.9, 'sw_N': 999.9, 'sw_V': 9999., 'sw_P': 99.99, 'Kp10': 99, 'R': 999, 'Dst': 99999, 'AE': 9999,
             'p10MeV': 99999.99, 'ap': 999, 'f107': 999.9}
    fr = []
    for f in sorted(glob.glob(os.path.join(RAW, 'omni', 'omni2_*.dat'))):
        a = pd.read_csv(f, sep=r'\s+', header=None)
        t = pd.to_datetime(a[0].astype(str), format='%Y') + pd.to_timedelta(a[1] - 1, 'D') + pd.to_timedelta(a[2], 'h')
        o = pd.DataFrame({n: a[i].astype(float) for i, n in cols.items()}); o.index = t
        for n, fv in fills.items(): o.loc[o[n] >= fv * 0.999, n] = np.nan
        o['Kp'] = o.pop('Kp10') / 10
        fr.append(o)
    o = pd.concat(fr).sort_index()
    o['log_p10MeV'] = np.log10(o.p10MeV.clip(lower=0.01))
    return o

def moon_cols(idx):
    dist, illum, alt_tomsk = [], [], []
    for t in idx:
        m = ephem.Moon(t.strftime('%Y/%m/%d %H:%M'))
        dist.append(m.earth_distance * 149597870.7); illum.append(m.moon_phase)
    return pd.DataFrame({'moon_dist_km': dist, 'moon_illum_eph': illum}, index=idx)

def main():
    v = pd.read_csv(os.path.join(RAW, 'vern_hourly.csv'), index_col=0, parse_dates=True)
    v = qa_station(v)
    s = pd.read_csv(os.path.join(RAW, 'sou_hourly.csv'), index_col=0, parse_dates=True)
    s = qa_station(s, has_amp=False)
    s = s[[c for c in s.columns if c.startswith('f1_')]]
    v.round(4).to_csv(os.path.join(D, 'schumann_vernadsky_hourly.csv.gz'))
    s.round(4).to_csv(os.path.join(D, 'schumann_sousy_hourly.csv.gz'))
    # Tomsk: long -> wide, median over overlapping snapshots
    tp = os.path.join(RAW, 'tomsk_hourly_raw.csv')
    tw = None
    if os.path.exists(tp):
        t = pd.read_csv(tp, parse_dates=['time_utc'])
        lp = os.path.join(D, 'schumann_tomsk_live.csv')   # appended by .github/workflows/schumann.yml
        if os.path.exists(lp):
            t = pd.concat([t, pd.read_csv(lp, parse_dates=['time_utc'])], ignore_index=True)
        t = t[(t['clip'] == 0) & (t['ncal'] >= 3) & (t['cov'] >= 0.34)]
        g = t.groupby(['time_utc', 'var']).value
        tw = g.median().unstack()
        tw.columns = [f'tomsk_{c}' for c in tw.columns]
        tw['tomsk_nsnap'] = t.groupby('time_utc').src.nunique()
        # plausibility
        rng = {'F1': (7.0, 8.8), 'F2': (12.5, 15.5), 'F3': (18, 22.5), 'F4': (23, 28.5),
               'A1': (0, 60), 'A2': (0, 60), 'A3': (0, 60), 'A4': (0, 60), 'Q1': (1, 40), 'Q2': (1, 40), 'Q3': (1, 40), 'Q4': (1, 40)}
        for k, (lo, hi) in rng.items():
            c = f'tomsk_{k}'
            if c in tw: tw.loc[(tw[c] < lo) | (tw[c] > hi), c] = np.nan
        tw.round(4).to_csv(os.path.join(D, 'schumann_tomsk_hourly.csv.gz'))
    # hourly drivers merged (Vernadsky period + Tomsk)
    o = load_omni()
    H = v[['f1_ns', 'f1_ew', 'a1_ns', 'a1_ew', 'a2_ns', 'a2_ew', 'a3_ns', 'a3_ew']].add_prefix('ver_')
    H = H.join(s[['f1_ns', 'f1_ew']].add_prefix('sou_'), how='outer')
    if tw is not None: H = H.join(tw, how='outer')
    H = H.join(o, how='left')
    H.round(4).to_csv(os.path.join(D, 'schumann_hourly_drivers.csv.gz'))
    # daily (require >=18 valid hours for SR means)
    def dmean(x):
        n = x.resample('D').count(); m = x.resample('D').mean()
        return m.where(n >= 18)
    Dd = pd.DataFrame({c: dmean(H[c]) for c in H.columns if c.startswith(('ver_', 'sou_'))})
    if tw is not None:
        for c in tw.columns:
            if c == 'tomsk_nsnap': continue
            n = tw[c].resample('D').count(); Dd = Dd.join(tw[c].resample('D').mean().where(n >= 12).rename(c), how='outer')
    od = o.resample('D').agg({'Kp': 'max', 'Dst': 'min', 'AE': 'mean', 'sw_V': 'mean', 'sw_N': 'mean', 'sw_P': 'mean',
                              'Bz_gsm': 'mean', 'log_p10MeV': 'max'})
    od.columns = ['omni_Kp_max', 'Dst_min', 'AE_mean', 'omni_sw_V', 'omni_sw_N', 'omni_sw_P', 'omni_Bz', 'log_p10MeV_max']
    Dd = Dd.join(od, how='left')
    e = pd.read_csv(os.path.join(D, 'eugene_env_daily.csv.gz'), parse_dates=['date']).set_index('date')
    ecols = ['sunspot_n', 'F107_adj', 'flares_C', 'flares_M', 'flares_X', 'kp_max', 'kp_sum', 'Ap', 'sw_speed_kms', 'sw_Bz_gsm_nT',
             'sw_density_cc', 'moon_illum', 'moon_age_days', 'tmax_F', 'tmin_F', 'prcp_in', 'pressure_msl_hPa_era5', 'wind_avg_mph', 'ev_us_holiday']
    Dd = Dd.join(e[[c for c in ecols if c in e]], how='left')
    Dd['flare_max_class'] = np.select([Dd.flares_X > 0, Dd.flares_M > 0, Dd.flares_C > 0], [3, 2, 1], 0).astype(float)
    Dd.loc[Dd.flares_C.isna(), 'flare_max_class'] = np.nan
    Dd['flares_MX'] = Dd.flares_M + Dd.flares_X
    mc = moon_cols(Dd.index + pd.Timedelta(hours=12)); mc.index = Dd.index
    Dd = Dd.join(mc)
    Dd.index.name = 'date'
    Dd.round(4).to_csv(os.path.join(D, 'schumann_daily.csv.gz'))
    print('daily', Dd.shape, Dd.index.min(), Dd.index.max())
    print(Dd.filter(regex='^(ver|sou|tomsk)_').notna().sum())

if __name__ == '__main__':
    main()
