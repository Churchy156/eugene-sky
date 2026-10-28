"""Plain-English display labels for every variable shown on charts, pages and maps.

DISPLAY ONLY: data/CSV column names stay as they are. Use:
    from labels import label, explain, wrap, caption
    label('kp_max')  -> 'Geomagnetic storm level (0–9)'
`python labels.py` rewrites labels.json (same dictionary, for the web pages).
"""
import json, os, textwrap

ANT, ARC, SIB = 'Antarctica (Vernadsky)', 'Arctic (Svalbard)', 'Siberia (Tomsk)'
STATIONS = {'ver': ANT, 'vernadsky': ANT, 'sou': ARC, 'sousy': ARC, 'svalbard': ARC, 'tomsk': SIB}

# name -> (short label, one-line explanation)
L = {}
def _a(names, lab, exp=''):
    for n in (names if isinstance(names, (list, tuple)) else [names]): L[n] = (lab, exp)

# ---------------- Schumann resonance (the Earth's natural "hum") ----------------
_TONE = 'The Earth–sky cavity hums at about 7.8 Hz, driven by lightning worldwide. This is the pitch of that main hum.'
_STR = 'How loud the main ~7.8 Hz hum is (relative units, not comparable between stations).'
for st, nm in [('ver', ANT), ('sou', ARC)]:
    for ax, axn in [('ns', 'north-south'), ('ew', 'east-west')]:
        _a(f'{st}_f1_{ax}', f'Main Schumann tone, {nm}, {axn} sensor (Hz)', _TONE)
        _a(f'{st}_a1_{ax}', f'Schumann signal strength, {nm}, {axn} sensor', _STR)
        _a(f'{st}_a2_{ax}', f'2nd Schumann tone strength, {nm}, {axn} sensor', 'Loudness of the 2nd hum (~14 Hz).')
        _a(f'{st}_a3_{ax}', f'3rd Schumann tone strength, {nm}, {axn} sensor', 'Loudness of the 3rd hum (~20 Hz).')
_a('tomsk_F1', f'Main Schumann tone, {SIB} (Hz)', _TONE)
_a('tomsk_F2', f'2nd Schumann tone, {SIB} (Hz)', 'Pitch of the 2nd hum (~14 Hz).')
_a('tomsk_F3', f'3rd Schumann tone, {SIB} (Hz)'); _a('tomsk_F4', f'4th Schumann tone, {SIB} (Hz)')
_a('tomsk_A1', f'Schumann signal strength, {SIB}', _STR)
for k in (2, 3, 4): _a(f'tomsk_A{k}', f'Strength of Schumann tone {k}, {SIB}')
_a('tomsk_Q1', f'Sharpness of the main Schumann tone, {SIB}', 'Higher = a cleaner, narrower hum.')
for k in (2, 3, 4): _a(f'tomsk_Q{k}', f'Sharpness of Schumann tone {k}, {SIB}')
_a(['f1', 'f1_NS', 'f1_ns'], 'Main Schumann tone, north-south sensor (Hz)', _TONE)
_a(['f1_EW', 'f1_ew'], 'Main Schumann tone, east-west sensor (Hz)', _TONE)
_a(['A1', 'a1'], 'Schumann signal strength', _STR)

# ---------------- Sun & space weather ----------------
_a(['Kp', 'kp_max', 'omni_Kp_max', 'Kp_max'], 'Geomagnetic storm level (0–9)', "How shaken Earth's magnetic field is. 5+ is a storm; 7+ is strong.")
_a('kp_sum', 'Geomagnetic storm level, all-day total', 'The day\'s eight 3-hour storm levels added up.')
_a(['Ap', 'ap'], 'Magnetic field disturbance, daily average', 'Another daily measure of geomagnetic storminess (bigger = stormier).')
_a('storm_Kp>=5', 'Geomagnetic storm day (level 5+)', 'Days when the storm level reached 5 or more.')
_a(['Dst', 'Dst_min'], 'Magnetic storm depth', 'How far the magnetic field dips during a storm. More negative = stronger storm.')
_a(['AE', 'AE_mean'], 'Northern lights activity', 'Strength of the electric currents that light up the aurora.')
_a(['F107_adj', 'f107', 'F10.7', 'F107'], "Sun's radio brightness", 'Radio glow from the Sun; rises and falls with the 11-year sunspot cycle.')
_a(['sunspot_n', 'R'], 'Sunspot count', 'Number of dark spots on the Sun; peaks every ~11 years.')
_a(['Bz', 'Bz_gsm', 'omni_Bz', 'sw_Bz_gsm_nT'], 'Solar wind magnetic direction', 'Negative (southward) lets solar energy into Earth\'s field more easily.')
_a(['sw_V', 'omni_sw_V', 'sw_speed_kms', 'solar_wind_speed'], 'Solar wind speed', 'How fast the stream of particles from the Sun is moving (km/s).')
_a(['sw_N', 'omni_sw_N', 'sw_density_cc'], 'Solar wind density', 'How many solar-wind particles per cubic centimetre.')
_a(['sw_P', 'omni_sw_P'], 'Solar wind pressure', 'How hard the solar wind pushes on Earth\'s magnetic field.')
_a(['log_p10MeV', 'log_p10MeV_max', 'p10MeV'], 'Solar radiation storm level', 'Amount of high-energy protons from the Sun (log scale).')
_a('flare_max_class', 'Biggest solar flare that day', '0 = none, 1 = small (C), 2 = medium (M), 3 = big (X).')
_a('flares_C', 'Small solar flares (C-class), count'); _a('flares_M', 'Medium solar flares (M-class), count')
_a('flares_X', 'Big solar flares (X-class), count'); _a('flares_MX', 'Medium + big solar flares, count')

# ---------------- Moon & tides ----------------
_a(['moon_illum', 'moon_illum_eph'], 'Moon brightness (0 = new, 1 = full)', 'Share of the Moon that is lit.')
_a('moon_age_days', 'Days since new moon')
_a('moon_dist_km', "Moon's distance from Earth", 'Closer moon = slightly stronger tides.')
_a('full_moon(±1d)', 'Full moon (± 1 day)')
_a(['tide_range_ft', 'tide_range'], 'Tide range at the coast (ft)', 'Gap between high and low tide that day.')

# ---------------- Eugene weather ----------------
_a(['tmax_F', 'tmax'], 'Daily high temperature (°F)'); _a('tmin_F', 'Daily low temperature (°F)')
_a(['prcp_in', 'rain_in'], 'Rain (inches)'); _a('snow_in', 'Snow (inches)')
_a(['pressure_msl_hPa_era5', 'pressure_msl'], 'Air pressure', 'Barometer reading. Low pressure usually means stormy weather.')
_a('pressure_change_24h', 'Air pressure change since yesterday')
_a('wind_avg_mph', 'Average wind (mph)')
_a('tmin_freezing', 'Freezing night (low at or below 32°F)')
_a('rain_day(>0.1in)', 'Rainy day (over 0.1 inch)'); _a('snow_day', 'Snow day')
_a('first_rain_after_7dry', 'First rain after a dry week', 'Oil builds up on roads in dry spells, so the first rain is slick.')
_a('daylight_hours', 'Hours of daylight'); _a('sunset_hour_local', 'Sunset time (hour, PT)')

# ---------------- Air & health ----------------
_a(['pm25', 'pm25_ugm3_cams', 'pm25_epa_lane_mean'], 'Smoke & dust in the air (PM2.5)', 'Tiny particles from smoke, dust and exhaust (µg/m³).')
_a('lane_pm25_log', 'Smoke & dust in the air, Lane County (PM2.5)')
_a(['us_aqi_max', 'us_aqi_max_cams'], 'Air quality index, worst hour (forecast model)', '0–50 good, 100+ unhealthy for sensitive groups.')
_a(['epa_aqi_official', 'aqi_epa_aqs_lane'], 'Air quality index (official EPA)')
_a(['covid_wastewater_log10', 'ww_sarscov2_log10_lane'], 'COVID level in Lane County wastewater')
_a(['covid_hosp_rate_or', 'resp_hosp_covid_rate_or'], 'COVID hospital admissions, Oregon')
_a(['flu_hosp_rate_or', 'resp_hosp_flu_rate_or'], 'Flu hospital admissions, Oregon')
_a(['rsv_hosp_rate_or', 'resp_hosp_rsv_rate_or'], 'RSV hospital admissions, Oregon')

# ---------------- Earthquakes, volcanoes, tsunamis ----------------
_a(['eq_500km_M2.5plus', 'quakes_500km_M2.5+', 'oregon_quakes_500km_M2.5+'], 'Quakes within 500 km of Eugene (M2.5+)')
_a('eq_500km_maxmag', 'Biggest quake within 500 km (magnitude)')
_a('eq_global_M6plus', 'Big quakes worldwide (M6+), count'); _a('eq_global_maxmag', 'Biggest quake worldwide (magnitude)')
_a('rof_eq_M5plus', 'Ring of Fire quakes M5+'); _a('rof_eq_M6plus', 'Ring of Fire quakes M6+'); _a('rof_eq_M7plus', 'Ring of Fire quakes M7+')
_a('rof_eq_maxmag', 'Biggest Ring of Fire quake (magnitude)')
_a('nz_eq_M4plus', 'New Zealand quakes M4+'); _a('nz_eq_M5plus', 'New Zealand quakes M5+'); _a('nz_eq_maxmag', 'Biggest New Zealand quake (magnitude)')
_a(['volc_erupting_rof', 'ring_of_fire_volcanoes_erupting', 'RoF volcanoes erupting'], 'Ring of Fire volcanoes erupting')
_a('volc_erupting_global', 'Volcanoes erupting worldwide'); _a('volc_new_eruptions_rof', 'New Ring of Fire eruptions')
_a(['tsunami_events_rof'], 'Pacific tsunamis'); _a('tsunami_events_global', 'Tsunamis worldwide')
_a(['ring_of_fire_M6+_day', 'RoF quake M6+ day'], 'Day with a Ring of Fire quake M6+')
_a('RoF quake M7+ day', 'Day with a Ring of Fire quake M7+')
_a(['nz_quake_M5+_day', 'NZ quake M5+ day'], 'Day with a New Zealand quake M5+')
_a(['ring_of_fire_tsunami_day', 'RoF tsunami event day'], 'Day with a Pacific tsunami')
_a('RoF new eruption day', 'Day a new Ring of Fire eruption started')
_a('NZ M4+ count (log)', 'Number of New Zealand quakes M4+')
_a('RoF M5+ count (log)', 'Number of Ring of Fire quakes M5+')
_a('RoF M5+ count (positive control)', 'Ring of Fire aftershocks M5+ (method check)', 'Big quakes really do cause aftershocks, so this should show a clear effect.')

# ---------------- Crashes, police ----------------
_a('crashes_all_6cty', 'Crashes, 6 nearby counties', 'Lane, Linn, Benton, Douglas, Marion and Lincoln (ODOT, 2007–2024).')
_a('crashes_lane', 'Crashes, Lane County')
_a('crashes_injury_fatal_6cty', 'Injury & deadly crashes, 6 counties')
_a('fatal_crashes_FARS_9cty', 'Deadly crashes, 9 counties (since 1975)')
_a('eugene_police_calls', 'Eugene police calls'); _a('springfield_police_calls', 'Springfield police calls')

# ---------------- Sports within 100 mi ----------------
_a(['ducks_home_football', 'ev_ducks_fb_home'], 'Ducks home football game'); _a('osu_home_football', 'Beavers home football game')
_a(['major_home_game(UO/OSU FB)', 'major_home_game'], 'Ducks or Beavers home football game')
_a('major_home_game_next_day', 'Day after a Ducks/Beavers home football game')
_a('ducks_home_mbb', "Ducks men's basketball home game"); _a('osu_home_mbb', "Beavers men's basketball home game")
_a('ducks_home_wbb', "Ducks women's basketball home game"); _a('osu_home_wbb', "Beavers women's basketball home game")
_a(['milb_home_game', 'milb_home_games'], 'Minor-league baseball home game'); _a('hayward_major_meet', 'Big track meet at Hayward Field')
_a('games_within_100mi', 'Sports games within 100 mi'); _a('games_within_100mi (per game)', 'Each extra game within 100 mi')
_a(['football_attendance (per 10k, game days only)', 'football_attendance_100mi'], 'Each extra 10,000 football fans (game days)')
_a('est_attendance_100mi', 'Estimated fans at games within 100 mi'); _a('football_kickoff_hour', 'Football kickoff time (hour, PT)')
_a('ev_us_holiday', 'US holiday')

# ---------------- Statistics words ----------------
_a(['q_fdr', 'q', 'q-value', 'q_value'], "Chance it's a fluke (after correction)", 'Adjusted for running many tests. Under 0.05 = probably real.')
_a(['p', 'p_value', 'p_one_sided', 'p_circshift'], "Chance it's a fluke (single test)", 'Below 0.05 looks interesting, but with many tests some will by luck.')
_a(['partial_r', 'spearman_r', 'r'], 'Link strength (−1 to +1)', '0 = no link; + = rise together; − = one rises as the other falls.')
_a('beta_per_sd', 'Change per typical swing', 'How much it changes when the other thing moves by one typical amount.')
_a(['lag', 'lag_days'], 'Days later'); _a('pct_change', '% change'); _a('n_days', 'Days of data')
_a('skill', 'Forecast improvement'); _a('skill_vs_best_baseline', 'Forecast improvement over the best simple guess')
_a('mae_model', 'Typical forecast error'); _a('mae_baseline', 'Typical error of the simple guess')
_a('best_baseline', 'Simple guess it was compared with'); _a('h', 'Days ahead'); _a('model', 'Forecast method'); _a('target', 'What is forecast'); _a('predictor', 'Possible cause')

# Forecast methods and events
MODELS = {'persistence': 'Simple guess: tomorrow = today', 'persist_7d_mean': "Simple guess: last week's average",
          'climatology': 'Simple guess: usual value for the time of year', 'clim+damped_anom': 'Simple guess: usual value + fading recent difference',
          'ridge:hist': 'Our forecast: recent history only', 'gbm:hist': 'Machine-learning forecast: recent history only',
          'ridge:hist+solar': 'Our forecast: history + Sun data', 'gbm:hist+solar': 'Machine-learning forecast: history + Sun data',
          'ridge:hist+solar+moon': 'Our forecast: history + Sun + Moon', 'gbm:hist+solar+moon': 'Machine-learning forecast: history + Sun + Moon',
          'ridge:all(+wx)': 'Our forecast: history + Sun + Moon + weather', 'gbm:all(+wx)': 'Machine-learning forecast: everything'}
EVENTS = {'proton_event_10pfu': 'Solar radiation storm', 'storm_Kp7': 'Strong geomagnetic storm (level 7+)', 'X_flare_day': 'Big (X-class) solar flare'}
SEASONS = {'DJF': 'Winter (Dec–Feb)', 'MAM': 'Spring (Mar–May)', 'JJA': 'Summer (Jun–Aug)', 'SON': 'Fall (Sep–Nov)'}
for d in (MODELS, EVENTS, SEASONS):
    for k, v in d.items(): L.setdefault(k, (v, ''))

def label(n): return L.get(n, (str(n), ''))[0]
def explain(n): return L.get(n, ('', ''))[1]
def wrap(n, width=28): return '\n'.join(textwrap.wrap(label(n), width)) or str(n)

def caption(fig, text, fontsize=10.5, bottom=0.0):
    """Put a one-sentence 'how to read this' caption under a matplotlib figure and make room for it."""
    lines = textwrap.wrap(text, int(fig.get_figwidth() * 13))
    h = 0.03 + 0.022 * len(lines) * 10 / fig.get_figheight()
    fig.tight_layout(rect=[0, h, 1, 1])
    fig.text(0.5, 0.01, '\n'.join(lines), ha='center', va='bottom', fontsize=fontsize, color='#333',
             bbox=dict(boxstyle='round,pad=0.4', fc='#f4f6f8', ec='#ccd'))

def to_json(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'labels.json')
    json.dump({k: {'label': a, 'explain': b} for k, (a, b) in sorted(L.items())}, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return path

if __name__ == '__main__':
    print(to_json(), len(L), 'labels')
