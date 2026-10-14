// Cloudflare Worker: live traffic relay for the Sky & Earth ZIP map.
// GET /traffic/<ST>.json  -> {built, cam:[[lat,lon,name,img]], inc:[[lat,lon,road,desc,time]], wz:[[lat,lon,road,desc,start,end]]}
// Secrets stay here (TRIPCHECK_KEY). Responses are edge-cached for 60 s.
const WZDX = { // no-key WZDx feeds that block browser CORS (from the USDOT WZDx registry)
  OK:'https://oktraffic.org/api/Geojsons/workzones?&access_token=feOPynfHRJ5sdx8tf3IN5yOsGz89TAUuzHsN3V0jo1Fg41LcpoLhIRltaTPmDngD',
  UT:'https://udottraffic.utah.gov/wzdx/udot/v40/data', IA:'https://iowa-atms.cloud-q-free.com/api/rest/dataprism/wzdx/wzdxfeed',
  FL:'https://us-datacloud.one.network/fdot/feed.json?app_key=c4090b04-26de-c9ee-873b2bd9a38c', MN:'https://mn.carsprogram.org/carsapi_v1/api/wzdx',
  MD:'https://filter.ritis.org/wzdx_v4.1/mdot.geojson', AZ:'https://wzdxapi.aztech.org/construction', MO:'https://traveler.modot.org/timconfig/feed/desktop/mo_wzdx.json',
  WI:'https://511wi.gov/api/wzdx', NM:'https://ai.blyncsy.io/wzdx/nmdot/feed', HI:'https://ai.blyncsy.io/wzdx/hidot/feed', NY:'https://511ny.org/api/wzdx',
  KY:'https://storage.googleapis.com/kytc-its-2020-openrecords/public/feeds/WZDx/kytc_wzdx_v4.1.geojson', NJ:'https://smartworkzones.njit.edu/nj/wzdx',
  KS:'https://ks.carsprogram.org/carsapi_v1/api/wzdx', TX:'https://data.austintexas.gov/download/d9mm-cjw9', ID:'https://511.idaho.gov/api/wzdx',
  NC:'https://drivenc.gov/api/wzdx', ND:'https://travelfiles.dot.nd.gov/geojson_nc/wzdx_geojson.json',
  WA:'https://wzdx.wsdot.wa.gov/api/v4/WorkZoneFeed', DE:'https://wzdx.e-dot.com/del_dot_feed_wzdx_v4.1.geojson',
  LA:'https://wzdx.e-dot.com/la_dot_d_feed_wzdx_v4.1.geojson', IN:'https://in.carsprogram.org/carsapi_v1/api/wzdx', MS:'https://api.mdottraffic.com/prod/v3/data/wzdx',
};
const ALLOW = /^https:\/\/churchy156\.github\.io$|^http:\/\/localhost(:\d+)?$/;
const j = async (u, h = {}) => { const r = await fetch(u, { headers: { 'User-Agent': 'eugene-sky-relay', ...h }, cf: { cacheTtl: 60 } }); if (!r.ok) throw new Error(r.status); return r; };
const pt = g => { let c = g && g.coordinates; while (Array.isArray(c) && Array.isArray(c[0])) c = c[0]; return c && c.length > 1 ? [c[1], c[0]] : null; };
async function wzdx(u, h) { const d = await (await j(u, h)).json(); return (d.features || []).map(f => { const p = f.properties || {}, cd = p.core_details || p, q = pt(f.geometry);
  return q && [...q, (cd.road_names || []).join(', ').slice(0, 60), (cd.description || '').slice(0, 200), (p.start_date || '').slice(0, 10), (p.end_date || '').slice(0, 10)]; }).filter(Boolean); }
async function build(st, env) {
  const out = { built: new Date().toISOString(), cam: [], inc: [], wz: [], src: [] };
  const tasks = [];
  if (WZDX[st]) tasks.push(wzdx(WZDX[st]).then(r => { out.wz.push(...r); out.src.push('WZDx'); }));
  if (st === 'OR' && env.TRIPCHECK_KEY) {
    const h = { 'Ocp-Apim-Subscription-Key': env.TRIPCHECK_KEY };
    tasks.push(j('https://api.odot.state.or.us/tripcheck/Incidents', h).then(r => r.json()).then(d => d.incidents.forEach(i => { const s = i.location['start-location'] || {};
      if (s['start-lat']) out.inc.push([s['start-lat'], s['start-long'], i.location['route-id'] || '', (i.headline || '').slice(0, 200), (i['update-time'] || '').slice(0, 16)]); })));
    tasks.push(j('https://api.odot.state.or.us/tripcheck/Cctv/Inventory', h).then(r => r.json()).then(d => d.CCTVInventoryRequest.forEach(c =>
      out.cam.push([c.latitude, c.longitude, c['device-name'], c['cctv-url'].replace('http://', 'https://')]))));
    tasks.push(wzdx('https://api.odot.state.or.us/WZDx/v4.0/Workzones', h).then(r => out.wz.push(...r)));
  }
  if (st === 'CA') {
    tasks.push(j('https://media.chp.ca.gov/sa_xml/sa.xml').then(r => r.text()).then(x => { for (const m of x.matchAll(/<Log ID[\s\S]*?<\/Log>/g)) { const b = m[0], g = t => ((b.match(new RegExp(`<${t}>"?([\\s\\S]*?)"?</${t}>`)) || [])[1] || '');
      const ll = g('LATLON'); if (ll.includes(':') && ll !== '0:0') { const [a, o] = ll.split(':'); out.inc.push([+a / 1e6, -o / 1e6, g('Location').slice(0, 60), g('LogType') + ' — ' + g('LocationDesc'), g('LogTime')]); } } }));
    for (let d = 1; d <= 12; d++) { const n = String(d).padStart(2, '0');
      tasks.push(j(`https://cwwp2.dot.ca.gov/data/d${d}/cctv/cctvStatusD${n}.json`).then(r => r.json()).then(x => x.data.forEach(({ cctv: c }) => {
        const u = c.imageData.static.currentImageURL; if (c.inService !== 'false' && u) out.cam.push([+c.location.latitude, +c.location.longitude, c.location.locationName.slice(0, 80), u]); }))); }
  }
  await Promise.allSettled(tasks);
  return out;
}
let _tok = null, _exp = 0;
async function osToken(env) {
  if (!env.OPENSKY_CLIENT_ID) return null;
  if (_tok && Date.now() < _exp) return _tok;
  const r = await fetch('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'client_credentials', client_id: env.OPENSKY_CLIENT_ID, client_secret: env.OPENSKY_CLIENT_SECRET }) });
  if (!r.ok) throw new Error('token ' + r.status);
  const j = await r.json(); _tok = j.access_token; _exp = Date.now() + (j.expires_in - 120) * 1000; return _tok;
}
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url), origin = req.headers.get('Origin') || '';
    const cors = { 'Access-Control-Allow-Origin': ALLOW.test(origin) ? origin : 'https://churchy156.github.io', 'Vary': 'Origin', 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' };
    if (url.pathname === '/aircraft') { // OpenSky (OAuth2) per ~0.5° cell, 20 s edge cache
      const la = (+url.searchParams.get('lat')).toFixed(1), lo = (+url.searchParams.get('lon')).toFixed(1), di = Math.min(250, +url.searchParams.get('dist') || 60);
      const ck = new Request(`${url.origin}/aircraft?c=${(Math.round(la*2)/2)},${(Math.round(lo*2)/2)},${Math.ceil(di/50)*50}`);
      const hit = await caches.default.match(ck); if (hit) return new Response(hit.body, { headers: { ...cors, 'Cache-Control': 'public, max-age=20' } });
      let body = null, src = 'opensky', dbg = [];
      try {
        const tok = await osToken(env); const d2 = (Math.ceil(di/50)*50) / 60, cla = Math.round(la*2)/2, clo = Math.round(lo*2)/2;
        const r = await fetch(`https://opensky-network.org/api/states/all?extended=1&lamin=${cla - d2}&lomin=${clo - d2 * 1.4}&lamax=${cla + d2}&lomax=${clo + d2 * 1.4}`, { headers: tok ? { Authorization: 'Bearer ' + tok } : {} });
        dbg.push('os ' + r.status + ' rem ' + r.headers.get('X-Rate-Limit-Remaining'));
        if (r.status === 401) _tok = null;
        if (r.ok) { const j = await r.json(); body = { now: j.time, ac: (j.states || []).map(s => ({ hex: s[0], flight: (s[1]||'').trim(), lon: s[5], lat: s[6], alt_baro: s[7] == null ? (s[8] ? 'ground' : null) : Math.round(s[7] * 3.281), gs: s[9] == null ? null : s[9] * 1.944, track: s[10], cat: s[17], country: s[2] })).filter(a => a.lat != null) }; }
      } catch (e) { dbg.push('os err ' + e); }
      const resp = new Response(JSON.stringify({ ...(body || { ac: [] }), src, dbg }), { status: body ? 200 : 502, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=20' } });
      if (body) ctx.waitUntil(caches.default.put(ck, resp.clone()));
      return new Response(resp.body, { status: resp.status, headers: { ...cors, 'Cache-Control': 'public, max-age=20' } });
    }
    if (url.pathname === '/faa') { // FAA NAS airport status (XML), 2 min edge cache
      const ck = new Request(url.origin + '/faa'); let r = await caches.default.match(ck);
      if (!r) { const f = await fetch('https://nasstatus.faa.gov/api/airport-status-information'); r = new Response(await f.text(), { status: f.status, headers: { 'Content-Type': 'application/xml', 'Cache-Control': 'public, max-age=120' } }); if (f.ok) ctx.waitUntil(caches.default.put(ck, r.clone())); }
      return new Response(r.body, { status: r.status, headers: { ...cors, 'Content-Type': 'application/xml', 'Cache-Control': 'public, max-age=120' } });
    }
    const m = url.pathname.match(/^\/traffic\/([A-Z]{2})\.json$/);
    if (!m) return new Response('{"error":"use /traffic/<ST>.json"}', { status: 404, headers: cors });
    const cache = caches.default, key = new Request(url.origin + url.pathname);
    let r = await cache.match(key);
    if (!r) { r = new Response(JSON.stringify(await build(m[1], env)), { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' } }); ctx.waitUntil(cache.put(key, r.clone())); }
    return new Response(r.body, { headers: cors });
  },
};
