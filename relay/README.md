# Live traffic relay (optional, ~1-minute freshness)

Without this, the map already uses the **GitHub Actions relay** (`.github/workflows/live-traffic.yml`, every ~10 min,
published to the `live` branch and read from raw.githubusercontent.com) with the 3-hour site snapshot as fallback.

To get ~60-second freshness, deploy this Cloudflare Worker (free plan: 100k requests/day):

1. Create a free Cloudflare account: https://dash.cloudflare.com/sign-up
2. On any computer with Node.js: `cd relay && npx wrangler login && npx wrangler secret put TRIPCHECK_KEY && npx wrangler deploy`
   (paste the ODOT TripCheck key when asked; it is stored only in Cloudflare).
3. Copy the printed URL (e.g. `https://eugene-sky-traffic.<you>.workers.dev`) into `zip_src/relay.js`:
   `window.TRAFFIC_RELAY='https://eugene-sky-traffic.<you>.workers.dev';` and push.

The map picks whichever source is newest, so nothing breaks if the Worker is down.
