# Power outage & grid sources — Steven's utilities (EWEB, Emerald PUD, Blachly-Lane, Pacific Power)
Daily report "Power & grid" uses `zip_tools/power_feeds.py`; every feed is the public JSON the utility's own outage map loads (no login, no key).

| Utility / source | Live feed | Daily column (from 2026-10-28, no history) | Outage map |
|---|---|---|---|
| EWEB | ArcGIS FeatureServer `services7.arcgis.com/6AM8yPAeyXiPc9eF/.../PublicOutageMap_Public_View/FeatureServer/0` | outage_live_eweb_cust_out_max | https://www.eweb.org/outages-and-safety/power-outages/power-outage-map |
| Emerald PUD | NISC hosted map data `https://outagemap-data.cloud.coop/epud/Hosted_Outage_Map/summary.json` (outages + Territory/ZIP regions) | outage_live_epud_cust_out_max | https://epud.outagemap.coop/ |
| Blachly-Lane Electric | NISC hosted map data `https://outagemap-data.cloud.coop/blachlylane/Hosted_Outage_Map/summary.json` (outages + Cities/Substation regions) | outage_live_blachly_cust_out_max | https://blachlylane.outagemap.coop/ |
| Pacific Power | `https://www.pacificpower.net/etc/pcorp/datafiles/outagemap/mapOR.json` (points, customers, cause, ETR, ZIP) + `listOR.json` (by ZIP/county) | outage_live_pacific_near_cust_out_max (≤45 mi of Eugene), outage_live_pacific_or_cust_out_max (Oregon) | https://www.pacificpower.net/outages-safety.html |
| BPA transmission interruptions | Outages/DIR/TODAY.HTM (rolling week); report shows ≤4 Eugene-district lines near Eugene | – | https://transmission.bpa.gov/Business/Operations/Outages/ |
| BPA BA load & generation | baltwg.txt (5-min, last 7 days) | bpa_* columns | https://transmission.bpa.gov/Business/Operations/Wind/ |
| ORNL EAGLE-I (all utilities, county level, 15-min) | n/a | 2014-11 → 2025 | https://doi.org/10.6084/m9.figshare.24237376 |

Not in the report (one-line footnote only): Consumers Power Inc (feed https://outage.cpi.coop/data/outages.json, still logged as outage_live_cpi_cust_out_max), Springfield Utility Board https://www.subutil.org/, Lane Electric https://www.laneelectric.com/, Central Lincoln PUD, Douglas Electric, PGE.
