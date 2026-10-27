# Schumann resonance (SR): historical dataset, correlations and forecast

**Every SR number in this folder is a digitized estimate** read off published charts. None of it is an instrument data feed.

## Pipeline
| step | script | output |
|---|---|---|
| Vernadsky (Antarctica, Zenodo daily NS/EW f1 line charts + spectrograms), SOUSY (Svalbard) | `digitize_vernadsky.py <zipdir> <out> ver|sou` | /workspace/sr_raw/vern_hourly.csv, sou_hourly.csv (box only) |
| Tomsk (sosrff.tsu.ru → sos70.ru F/A/Q charts, Internet Archive snapshots 2011–2026 + live) | `digitize_tomsk.py OUT IMG...` (tesseract OCR of axis labels and dates) | /workspace/sr_raw/tomsk_hourly_raw.csv |
| QA, merge with OMNI2 hourly, Eugene env daily, ephem moon distance | `build_schumann.py` | data/schumann_{vernadsky,sousy,tomsk}_hourly.csv.gz, schumann_hourly_drivers.csv.gz, schumann_daily.csv.gz |
| Correlations (daily FE-OLS + HAC + BH; monthly long-term; hourly anomalies; diurnal; superposed epoch) | `analyze_schumann.py` | reports/schumann/schumann_correlations.csv, _diurnal.csv, _epoch.csv |
| Forecast 1–27 d (ridge / gradient boosting vs persistence, 7-day mean, DOY climatology, damped anomaly). Train ≤2014, validate 2015, test 2016–2020 | `forecast_schumann.py`, `forecast_significance.py` | reports/schumann/schumann_forecast_*.csv |
| Charts + page | `make_schumann_charts.py` | reports/schumann/*.png, reports/schumann/schumann.html (copied to site/ by update.yml) |
| Live capture (GitHub Actions `.github/workflows/schumann.yml`, every 6 h) | `capture_tomsk_live.py` | data/schumann_tomsk_live.csv |

## Caveats
- **Frequency:** digitization error is about ±0.003–0.005 Hz for Vernadsky/SOUSY and about ±0.01–0.02 Hz for Tomsk. Values are clipped to each chart's axis range (Vernadsky 7.5–8.2 Hz). The Vernadsky legend box hides f1 above about 8.12 Hz from roughly 17:30 to 23:20 UT.
- **Amplitude:** Vernadsky amplitudes are relative dB from the spectrogram colormap, quantized to about 0.6 dB, and not calibrated. Tomsk amplitudes are in chart units.
- **Bad and dead hours:** hours where the channel is dead (power at the colormap floor), saturated or covered by the legend are set to NaN. One example is Vernadsky NS from Aug 2009 to Apr 2010.
- **Tomsk timing and sampling:** Tomsk times assume the charts use Asia/Tomsk local time. The record is sparse (snapshot dates only), so 862 valid days in total.
- **No cross-station agreement:** stations do not agree day to day. Ver-vs-SOUSY f1 daily r is about −0.3. Tomsk vs the 2024 reference series (used only for validation, not republished) gives hourly r of about −0.16. So the results here are station-specific.
- **Solar cycle:** year fixed effects absorb the solar cycle, which is tested separately on monthly means (no year FE).
- **Missing drivers:** no lightning data was available. Eugene weather is a local negative control, not a physical driver of a global resonance.
