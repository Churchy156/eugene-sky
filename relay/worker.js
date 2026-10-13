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
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url), origin = req.headers.get('Origin') || '';
    const cors = { 'Access-Control-Allow-Origin': ALLOW.test(origin) ? origin : 'https://churchy156.github.io', 'Vary': 'Origin', 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' };
    if (url.pathname === '/aircraft') { // proxy adsb.lol (no browser CORS); 15 s edge cache per ~0.1° cell
      const la = (+url.searchParams.get('lat')).toFixed(1), lo = (+url.searchParams.get('lon')).toFixed(1), di = Math.min(250, +url.searchParams.get('dist') || 60);
      const H = { headers: { 'User-Agent': 'eugene-sky-relay/1.0 (+https://github.com/Churchy156/eugene-sky; churchy156.github.io)' }, cf: { cacheTtl: 15, cacheEverything: true } };
      let body = null, src = 'adsb.lol', dbg = [];
      try { const r = await fetch(`https://api.adsb.lol/v2/point/${la}/${lo}/${di}`, H); dbg.push('lol ' + r.status); if (r.ok) body = await r.json(); else dbg.push((await r.text()).slice(0, 120)); } catch (e) { dbg.push('lol err ' + e); }
      if (!body) { src = 'adsb.fi'; try { const r = await fetch(`https://opendata.adsb.fi/api/v2/lat/${la}/lon/${lo}/dist/${di}`, H); dbg.push('fi ' + r.status); if (r.ok) { const j = await r.json(); body = { ac: j.aircraft || j.ac || [], now: j.now }; } } catch (e) { dbg.push('fi err ' + e); } }
      if (!body || !(body.ac || []).length) { src = 'opensky'; try { const d2 = di / 60; const r = await fetch(`https://opensky-network.org/api/states/all?lamin=${+la - d2}&lomin=${+lo - d2 * 1.4}&lamax=${+la + d2}&lomax=${+lo + d2 * 1.4}`, H); dbg.push('os ' + r.status);
        if (r.ok) { const j = await r.json(); body = { now: j.time, ac: (j.states || []).map(s => ({ hex: s[0], flight: s[1], lon: s[5], lat: s[6], alt_baro: s[7] == null ? (s[8] ? 'ground' : null) : Math.round(s[7] * 3.281), gs: s[9] == null ? null : s[9] * 1.944, track: s[10], cat: s[17], country: s[2] })) }; } } catch (e) { dbg.push('os err ' + e); } }
      return new Response(JSON.stringify({ ...(body || { ac: [] }), src, dbg }), { status: body ? 200 : 502, headers: { ...cors, 'Cache-Control': 'public, max-age=15' } });
    }
    const m = url.pathname.match(/^\/traffic\/([A-Z]{2})\.json$/);
    if (!m) return new Response('{"error":"use /traffic/<ST>.json"}', { status: 404, headers: cors });
    const cache = caches.default, key = new Request(url.origin + url.pathname);
    let r = await cache.match(key);
    if (!r) { r = new Response(JSON.stringify(await build(m[1], env)), { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' } }); ctx.waitUntil(cache.put(key, r.clone())); }
    return new Response(r.body, { headers: cors });
  },
};
