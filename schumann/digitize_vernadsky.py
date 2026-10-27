"""Digitize Vernadsky (Antarctica) Schumann resonance figures from Zenodo 10.5281/zenodo.5919944.

Two figure types per day (MATLAB, fixed 600x449 layout, verified constant across 2002-2020):
  l YYYYMMDD000000f.png  first-mode frequency, NS (blue) and EW (orange) antenna, 0-24 UT, y 7.5-8.2 Hz
  l YYYYMMDD000000.png   spectrogram, NS (top) / EW (bottom), 0-~48.6 Hz, jet colormap, colorbar 0..-30 dB

Outputs hourly UT rows: f1_ns, f1_ew (Hz, digitized line), a1/a2/a3 _ns/_ew (dB, relative, uncalibrated,
peak colour in the 6-10 / 12.5-16 / 18-23 Hz bands), plus QA columns.
ALL VALUES ARE ESTIMATES read from images, not the station's original numbers.
"""
import sys, os, glob, zipfile, io, re
import numpy as np
from PIL import Image
from multiprocessing import Pool
from scipy.spatial import cKDTree

BG = np.array([0, 255, 255])  # transparent colour of the PNGs
# ---- frequency plot calibration (pixels) ----
FX0, FX1 = 33, 554            # x pixel of 0 UT and 24 UT
FY_TOP, FY_BOT = 21, 414      # y pixel of 8.2 Hz and 7.5 Hz
BLUE = np.array([0, 114, 189]); ORANGE = np.array([217, 83, 25])
# ---- spectrogram calibration ----
SX0, SX1 = 33, 554
PANELS = {'ns': (34, 214), 'ew': (234, 414)}  # top row, bottom row (0 Hz at bottom+0.5)
PX_PER_HZ = 3.7
CB_COL = 569
CB_LABEL_ROWS = {0: 57.5, -10: 102.5, -20: 147.5, -30: 192.5}  # top panel colourbar ticks
BANDS = {'a1': (6.0, 10.0), 'a2': (12.5, 16.0), 'a3': (18.0, 23.0)}


def colorbar_lut(rgb):
    rows = np.arange(PANELS['ns'][0] + 1, PANELS['ns'][1])
    cols = rgb[rows, CB_COL]
    # dB per row from tick labels: linear fit
    ks = np.array(list(CB_LABEL_ROWS.values())); vs = np.array(list(CB_LABEL_ROWS.keys()))
    m, b = np.polyfit(ks, vs, 1)
    return cols.astype(float), rows * m + b


SOU_COLS = (('ns', np.array([0, 0, 255])), ('ew', np.array([0, 128, 0])))


def read_freq(rgb, station='ver'):
    h, w, _ = rgb.shape
    fx0, fx1, fyt, fyb = FX0, FX1, FY_TOP, FY_BOT
    if station == 'sou' and (h, w) == (449, 600):
        station = 'ver'      # most SOUSY figures use the same MATLAB style as Vernadsky
    if station == 'sou':
        if (h, w) != (450, 600):
            return None, 'bad_size'
        fx0, fx1, fyt, fyb = 33, 555, 20, 416
    elif (h, w) != (449, 600):
        return None, 'bad_size'
    d = (np.abs(rgb - [38, 38, 38]).sum(2) < 60)
    mask = np.zeros((h, w), bool)
    # legend box detection
    rws = [r for r in range(fyt + 1, fyb) if d[r, fx0 + 1:fx1].sum() > 50]
    if station == 'sou':   # SOUSY: black dotted grid, fixed legend position
        rws = []
        mask[25:76, 405:556] = True
    if len(rws) >= 2:
        r0, r1 = min(rws), max(rws)
        cs = np.where(d[r0, fx0 + 1:fx1])[0] + fx0 + 1
        mask[r0:r1 + 1, cs.min():cs.max() + 1] = True
    out = {}
    for name, col in (SOU_COLS if station == 'sou' else (('ns', BLUE), ('ew', ORANGE))):
        m = (np.abs(rgb - col).sum(2) < 90) & ~mask
        vals = np.full(fx1 - fx0, np.nan); clip = np.zeros(fx1 - fx0, bool)
        for i, x in enumerate(range(fx0 + 1, fx1)):
            rr = np.where(m[fyt:fyb + 1, x])[0]
            if len(rr) == 0 or len(rr) > 25:   # nothing, or vertical jump/garbage
                continue
            # line may have a vertical segment -> take median
            y = np.median(rr) + fyt
            vals[i] = 8.2 - (y - fyt) / (fyb - fyt) * 0.7
            clip[i] = (rr.min() <= 2) or (rr.max() + fyt >= fyb - 2)
        out[name] = (vals, clip)
    return out, 'ok'


def read_spec(rgb):
    if rgb.shape[:2] != (449, 600):
        return None
    lut_c, lut_v = colorbar_lut(rgb)
    out = {}
    for pn, (top, bot) in PANELS.items():
        sub = rgb[top + 1:bot, SX0 + 1:SX1].astype(float)
        H, W, _ = sub.shape
        flat = sub.reshape(-1, 3)
        # nearest colourbar colour
        dmin, idx = cKDTree(lut_c).query(flat)
        val = lut_v[idx].reshape(H, W)
        bad = (dmin > 40).reshape(H, W)        # white specks / text / not on colourmap
        val[bad] = np.nan
        freqs = (bot + 0.5 - (np.arange(top + 1, bot) + 0.5)) / PX_PER_HZ
        for band, (lo, hi) in BANDS.items():
            sel = (freqs >= lo) & (freqs <= hi)
            v = val[sel]
            with np.errstate(all='ignore'):
                out[f'{band}_{pn}'] = np.nanmax(v, 0)
        # broadband background 30-45 Hz (interference indicator)
        sel = (freqs >= 30) & (freqs <= 45)
        with np.errstate(all='ignore'):
            out[f'bg_{pn}'] = np.nanmedian(val[sel], 0)
            out[f'badfrac_{pn}'] = np.isnan(val).mean(0)
    return out


def hourly(arr, ncol):
    xh = (np.arange(ncol) + 0.5) / ncol * 24
    res = []
    for hr in range(24):
        s = arr[(xh >= hr) & (xh < hr + 1)]
        s = s[~np.isnan(s)]
        res.append((np.mean(s) if len(s) else np.nan, len(s) / max(1, ((xh >= hr) & (xh < hr + 1)).sum())))
    return res


def process_day(args):
    zpath, fname_f, fname_s, date = args[:4]
    station = args[4] if len(args) > 4 else 'ver'
    if station == 'sou':
        fname_s = None   # SOUSY spectrogram uses a different scale; frequency only
    rows = []
    try:
        z = zipfile.ZipFile(zpath)
        fr = sp = None
        if fname_f:
            fr, st = read_freq(np.array(Image.open(io.BytesIO(z.read(fname_f))).convert('RGB')).astype(int), station)
        if fname_s:
            sp = read_spec(np.array(Image.open(io.BytesIO(z.read(fname_s))).convert('RGB')).astype(int))
    except Exception as e:
        return [dict(date=date, hour=h, err=str(e)[:80]) for h in range(24)]
    rec = {h: dict(date=date, hour=h) for h in range(24)}
    if fr:
        for c in ('ns', 'ew'):
            vals, clip = fr[c]
            hv = hourly(vals, len(vals)); hc = hourly(clip.astype(float), len(clip))
            for h in range(24):
                rec[h][f'f1_{c}'] = hv[h][0]; rec[h][f'f1_{c}_cov'] = hv[h][1]; rec[h][f'f1_{c}_clipfrac'] = hc[h][0]
    if sp:
        for k, arr in sp.items():
            hv = hourly(arr, len(arr))
            for h in range(24):
                rec[h][k] = hv[h][0]
    return list(rec.values())


def jobs(zdir, prefix='l', station='ver'):
    out = []
    for zp in sorted(glob.glob(os.path.join(zdir, 'Ver_*.zip' if station == 'ver' else 'Sou_*.zip'))):
        names = zipfile.ZipFile(zp).namelist()
        byday = {}
        for n in names:
            m = re.search(prefix + r'(\d{8})\d{6}(f?)\.png$', n)
            if m:
                byday.setdefault(m.group(1), {})['f' if m.group(2) else 's'] = n
        for d, v in sorted(byday.items()):
            out.append((zp, v.get('f'), v.get('s'), f'{d[:4]}-{d[4:6]}-{d[6:]}', station))
    return out


if __name__ == '__main__':
    import pandas as pd
    zdir = sys.argv[1]; outcsv = sys.argv[2]
    st = sys.argv[3] if len(sys.argv) > 3 else 'ver'
    J = jobs(zdir, prefix='l' if st == 'ver' else 's', station=st)
    print(len(J), 'days')
    with Pool(max(1, os.cpu_count() - 1)) as p:
        allrows = [r for rs in p.imap(process_day, J, chunksize=8) for r in rs]
    df = pd.DataFrame(allrows)
    df['time_utc'] = pd.to_datetime(df['date']) + pd.to_timedelta(df['hour'], unit='h')
    df = df.drop(columns=['date', 'hour']).set_index('time_utc').sort_index()
    df.round(4).to_csv(outcsv)
    print(df.describe().T)
