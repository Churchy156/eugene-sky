// Shared map extras: animated radar, satellite, traffic cams/incidents/work zones.
(function(){
const kmx=(a,b,c,d)=>{const R=6371,r=Math.PI/180,x=Math.sin((c-a)*r/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2;return 2*R*Math.asin(Math.sqrt(x))};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
window.MapX={esc,km:kmx,
 // returns {overlays} to add to a layers control
 weather(map,lon){
  const ov={}, panel=L.control({position:'bottomleft'});
  const radar=L.layerGroup(), sat=L.layerGroup(), nex=L.tileLayer('https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png',{opacity:.6,attribution:'NEXRAD via Iowa Mesonet'});
  const east=lon>-100, ir=L.tileLayer(`https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/goes-${east?'east':'west'}-ir-4km-900913/{z}/{x}/{y}.png`,{opacity:.5,attribution:'GOES via Iowa Mesonet'});
  const vis=L.tileLayer(`https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/goes-${east?'east':'west'}-vis-1km-900913/{z}/{x}/{y}.png`,{opacity:.5,attribution:'GOES via Iowa Mesonet'});
  ir.addTo(sat);
  if(window.TOMTOM_KEY)ov['🚦 Live traffic flow (TomTom)']=L.tileLayer(`https://api.tomtom.com/traffic/map/4/tile/flow/relative0/{z}/{x}/{y}.png?key=${window.TOMTOM_KEY}`,{opacity:.85,attribution:'Traffic © TomTom'});
  ov['🌧 Radar loop (RainViewer, ~2 h)']=radar; ov['🌧 NEXRAD now (IEM)']=nex; ov['☁️ Satellite IR (GOES)']=sat; ov['☁️ Satellite visible (GOES, daytime)']=vis;
  let frames=[],i=0,timer=null,op=.65,lyr=[];
  panel.onAdd=()=>{const d=L.DomUtil.create('div');d.style.cssText='background:#16212dee;color:#e6edf3;padding:6px 8px;border-radius:8px;font:12px system-ui';
   d.innerHTML=`<button id="rvPlay" style="padding:2px 8px">⏸</button> <span id="rvT">radar…</span><br>opacity <input id="rvOp" type="range" min="0" max="100" value="65" style="width:110px;vertical-align:middle">`;
   L.DomEvent.disableClickPropagation(d);return d};
  panel.addTo(map);
  const show=k=>{lyr.forEach((l,j)=>l.setOpacity(j==k?op:0));const f=frames[k];if(f)document.getElementById('rvT').textContent='Radar '+new Date(f.time*1e3).toLocaleTimeString([], {hour:'numeric',minute:'2-digit',timeZoneName:'short'})+(k==frames.length-1?' (latest)':'')};
  const play=()=>{if(timer)return;timer=setInterval(()=>{i=(i+1)%frames.length;show(i)},600);document.getElementById('rvPlay').textContent='⏸'};
  const pause=()=>{clearInterval(timer);timer=null;document.getElementById('rvPlay').textContent='▶'};
  setTimeout(()=>{document.getElementById('rvPlay').onclick=()=>timer?pause():play();
   document.getElementById('rvOp').oninput=e=>{op=e.target.value/100;show(i);[nex,ir,vis].forEach(l=>l.setOpacity(op))}},0);
  fetch('https://api.rainviewer.com/public/weather-maps.json').then(r=>r.json()).then(j=>{frames=j.radar.past;
   lyr=frames.map(f=>L.tileLayer(`${j.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`,{opacity:0,maxNativeZoom:7,maxZoom:18,attribution:'RainViewer'}).addTo(radar));
   i=frames.length-1;show(i);play()}).catch(()=>{document.getElementById('rvT').textContent='RainViewer unavailable'});
  return ov},
 // Live traffic: relay (Cloudflare Worker, if configured) > GitHub 'live' branch (10-min Actions relay) > 3-h site snapshot.
 // Plus WZDx feeds that allow browser CORS are fetched directly. Auto-refresh every 3 min.
 RELAY: window.TRAFFIC_RELAY||'', RAW:'https://raw.githubusercontent.com/Churchy156/eugene-sky/live/traffic/',
 DIRECT:{WA:'https://wzdx.wsdot.wa.gov/api/v4/WorkZoneFeed',DE:'https://wzdx.e-dot.com/del_dot_feed_wzdx_v4.1.geojson',LA:'https://wzdx.e-dot.com/la_dot_d_feed_wzdx_v4.1.geojson',IN:'https://in.carsprogram.org/carsapi_v1/api/wzdx',MS:'https://api.mdottraffic.com/prod/v3/data/wzdx'},
 async traffic(map,base,lat,lon,st,noteEl){
  const cam=L.layerGroup(),inc=L.layerGroup(),wz=L.layerGroup(),ov={'📷 Traffic cameras':cam,'🚧 Incidents/closures':inc,'🦺 Work zones (WZDx)':wz};
  const R=200,near=a=>(a||[]).filter(x=>kmx(lat,lon,x[0],x[1])<R),bust=u=>u+(u.includes('?')?'&':'?')+'t='+Date.now();
  const tget=u=>fetch(u,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
  let cv=null;
  const draw=async()=>{
   const cands=[];
   if(this.RELAY)cands.push(['Cloudflare relay (live)',tget(this.RELAY+'/traffic/'+st+'.json')]);
   cands.push(['GitHub Actions relay (~10 min)',tget(bust(this.RAW+st+'.json'))],['site snapshot (~3 h)',tget(base+`traffic/${st}.json`)]);
   const got=(await Promise.all(cands.map(c=>c[1]))).map((d,i)=>[cands[i][0],d]).filter(x=>x[1]);
   cv=cv||await tget(base+'traffic/coverage.json')||{states:{}};
   got.sort((a,b)=>String(b[1].built).localeCompare(String(a[1].built)));const [src,d]=got[0]||['none',{cam:[],inc:[],wz:[]}];
   let wzrows=d.wz||[],direct='';
   if(this.DIRECT[st]){const j=await tget(this.DIRECT[st]);if(j&&j.features){wzrows=[];j.features.forEach(f=>{const p=f.properties||{},cd=p.core_details||p;let c=f.geometry&&f.geometry.coordinates;while(Array.isArray(c)&&Array.isArray(c[0]))c=c[0];
     if(c)wzrows.push([c[1],c[0],(cd.road_names||[]).join(', '),cd.description||'',(p.start_date||'').slice(0,10),(p.end_date||'').slice(0,10)])});direct=` · work zones fetched live from ${st} DOT in your browser`}}
   cam.clearLayers();inc.clearLayers();wz.clearLayers();
   near(d.cam).forEach(x=>{const m=L.circleMarker([x[0],x[1]],{radius:5,color:'#e6edf3',fillColor:'#2f81f7',fillOpacity:1,weight:1});
    const now=()=>new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit',timeZoneName:'short'});
    m.bindTooltip(()=>`<div style="width:240px"><b>${esc(x[2])}</b><br><img src="${esc(bust(x[3]))}" style="width:240px;display:block" alt="loading…" onerror="this.alt='image unavailable'"><span style="color:#888">latest image · loaded ${now()}</span></div>`,{direction:'top',opacity:1,sticky:false});
    m.bindPopup(()=>`<b>${esc(x[2])}</b><br><img src="${esc(bust(x[3]))}" style="width:420px;max-width:80vw" onerror="this.alt='image unavailable'"><br><span style="color:#888">loaded ${now()} · click again to refresh</span>`,{maxWidth:440});
    m.on('click',()=>m.closeTooltip());m.addTo(cam)});
   near(d.inc).forEach(x=>L.circleMarker([x[0],x[1]],{radius:5,color:'#f85149',fillOpacity:.8}).bindPopup(`<b>${esc(x[2])}</b><br>${esc(x[3])}<br><span style="color:#888">${esc(x[4])}</span>`).addTo(inc));
   near(wzrows).forEach(x=>L.circleMarker([x[0],x[1]],{radius:4,color:'#e3b341',fillOpacity:.8}).bindPopup(`<b>${esc(x[2])}</b><br>${esc(x[3])}<br>${esc(x[4])} → ${esc(x[5])}`).addTo(wz));
   const c=(cv.states||{})[st]||{},lab=k=>c[k]?c[k].join(', '):'none for '+st,ago=d.built?Math.round((Date.now()-Date.parse(d.built))/6e4):null;
   if(noteEl)noteEl.innerHTML=`<b>Traffic ${st}</b> — source: ${esc(src)}, data ${ago==null?'?':ago+' min old'} (fetched ${new Date().toLocaleTimeString([], {hour:'numeric',minute:'2-digit',timeZoneName:'short'})}, auto-refresh every 3 min${direct}). Cameras: ${esc(lab('cam'))} (hover = live thumbnail); incidents: ${esc(lab('inc'))}; work zones: ${esc(lab('wz'))}. States with any feed: ${Object.keys(cv.states||{}).sort().join(', ')}.`};
  await draw();clearInterval(this._t);this._t=setInterval(draw,180000);
  return ov}
};})();
