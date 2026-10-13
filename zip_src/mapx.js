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
  if(window.TOMTOM_KEY)ov['🚦 Traffic incidents (TomTom)']=L.tileLayer(`https://api.tomtom.com/traffic/map/4/tile/incidents/s3/{z}/{x}/{y}.png?key=${window.TOMTOM_KEY}`,{opacity:.9,attribution:'Traffic © TomTom'});
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
// One-tap horizontal layer buttons (gold = on) + mobile slide-up details sheet.
MapX.buttons=function(map,LC,bar){
 if(!document.getElementById('mxcss')){const st=document.createElement('style');st.id='mxcss';st.textContent=`.leaflet-control-layers{display:none!important}
 .mxbar{display:flex;gap:6px;overflow-x:auto;padding:6px 2px;scrollbar-width:thin;-webkit-overflow-scrolling:touch}
 .mxbar button{flex:0 0 auto;white-space:nowrap;border-radius:18px;padding:6px 12px;border:1px solid #3a4a5c;background:#1d2b3a;color:#cfd8e3;font:13px system-ui;cursor:pointer}
 .mxbar button.on{background:#d4a72c;border-color:#f2cc60;color:#111;font-weight:600}
 .mxsheet{position:fixed;left:0;right:0;bottom:0;z-index:2000;background:#16212df5;color:#e6edf3;border-radius:14px 14px 0 0;box-shadow:0 -4px 18px #0008;transform:translateY(calc(100% - 44px));transition:transform .25s;max-height:60vh;display:none}
 .mxsheet.open{transform:none}.mxsheet .hd{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;font:600 14px system-ui}
 .mxsheet .bd{padding:0 14px 14px;overflow:auto;max-height:calc(60vh - 44px);font:13px system-ui}.mxsheet .bd img{max-width:100%}
 @media(max-width:700px){.mxsheet.has{display:block}}`;document.head.appendChild(st)}
 const btns=new Map(),mk=(l,n)=>{const b=document.createElement('button');b.textContent=n;b.className=map.hasLayer(l)?'on':'';
  b.onclick=()=>{map.hasLayer(l)?map.removeLayer(l):map.addLayer(l)};btns.set(l,b);bar.appendChild(b)};
 Object.values(LC._layers||[]).forEach(o=>o.overlay&&mk(o.layer,o.name));
 const add=LC.addOverlay.bind(LC),rm=LC.removeLayer.bind(LC);
 LC.addOverlay=(l,n)=>{add(l,n);mk(l,n);return LC};LC.removeLayer=l=>{rm(l);const b=btns.get(l);if(b){b.remove();btns.delete(l)}return LC};
 const sync=e=>{const b=btns.get(e.layer);if(b)b.className=map.hasLayer(e.layer)?'on':''};map.on('layeradd layerremove',sync);
 // details sheet on phones
 const sh=document.createElement('div');sh.className='mxsheet';sh.innerHTML='<div class="hd"><span id="mxT">Details</span><button id="mxB" style="border-radius:14px;padding:4px 12px;background:#d4a72c;border:0;color:#111;font-weight:600">Hide</button></div><div class="bd" id="mxD"></div>';document.body.appendChild(sh);
 sh.querySelector('#mxB').onclick=()=>{sh.classList.toggle('open');sh.querySelector('#mxB').textContent=sh.classList.contains('open')?'Hide':'Details'};
 map.on('popupopen',e=>{if(innerWidth>700)return;const c=e.popup.getContent();const h=typeof c=='function'?c(e.popup._source):c;
  sh.querySelector('#mxD').innerHTML=typeof h=='string'?h:(h.outerHTML||'');sh.classList.add('has','open');sh.querySelector('#mxB').textContent='Hide';map.closePopup()});
 return btns};
// Native live-aircraft layer via the Cloudflare relay (bounds-based, zoom >= 5, capped).
MapX.aircraft=function(map,LC,statusEl){
 const lay=L.layerGroup(),name='✈️ Live aircraft';LC.addOverlay(lay,name);let t=null,busy=false;
 const say=h=>{if(statusEl)statusEl.innerHTML=h};
 const load=async()=>{if(!map.hasLayer(lay)||busy)return;
  if(map.getZoom()<5){lay.clearLayers();say('✈️ Zoom in (level 5+) to load live aircraft for the visible area.');return}
  busy=true;const c=map.getCenter(),b=map.getBounds(),r=Math.max(10,Math.min(250,Math.round(b.getNorthEast().distanceTo(c)/1852)));
  try{if(!MapX._ac||Date.now()-MapX._acT>60000){const k=await fetch('https://raw.githubusercontent.com/Churchy156/eugene-sky/live/aircraft.json?t='+Math.floor(Date.now()/60000)).then(x=>x.json());MapX._ac={src:'OpenSky',time:k.time,ac:k.ac.map(v=>({hex:v[0],flight:v[1],lat:v[2],lon:v[3],alt_baro:v[4]=='g'?'ground':v[4],gs:v[5],track:v[6],cat:v[7],country:v[8]}))};MapX._acT=Date.now()}
   const j=MapX._ac,age=Math.round((Date.now()/1000-j.time)/60);
   let ac=(j.ac||[]).filter(a=>a.lat!=null&&b.contains([a.lat,a.lon]));const tot=ac.length;if(ac.length>600)ac=ac.filter((_,i)=>i%Math.ceil(tot/600)==0);
   lay.clearLayers();const n={mil:0,com:0,pvt:0};
   ac.forEach(a=>{const cs=(a.flight||'').trim(),mil=(a.dbFlags&1)==1,com=/^[A-Z]{3}\d/.test(cs),k=mil?'mil':com?'com':'pvt';n[k]++;const col={mil:'#f85149',com:'#58a6ff',pvt:'#3fb950'}[k],h=a.track??a.true_heading??0;
    L.marker([a.lat,a.lon],{icon:L.divIcon({className:'',html:`<div style="transform:rotate(${h}deg);color:${col};font-size:17px;line-height:17px;text-shadow:0 0 2px #000,0 0 2px #000">✈</div>`,iconSize:[17,17],iconAnchor:[8,8]}),zIndexOffset:500})
     .bindTooltip(`<b>${MapX.esc(cs||a.r||a.hex)}</b> ${MapX.esc(a.t||'')} · ${k=='mil'?'military':k=='com'?'airline':'private/GA'}<br>${a.alt_baro??'?'} ft · ${Math.round(a.gs||0)} kt · hdg ${Math.round(h)}°${a.r?' · '+MapX.esc(a.r):''}`).addTo(lay)});
   say(tot?`✈️ <b>${tot}</b> aircraft in view${tot>ac.length?' (showing '+ac.length+')':''}: airline ${n.com}, private/GA ${n.pvt}, military ${n.mil} · OpenSky snapshot ${new Date(j.time*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})} (${age} min old; updates ~every 2.5–10 min)`
     :`✈️ No aircraft returned (${MapX.esc(j.src||'')}${j.dbg?': '+MapX.esc(j.dbg.filter(x=>x.length<20).join(', ')):''}). No planes in this view in the latest snapshot.`)}catch(e){say('✈️ Aircraft relay error: '+MapX.esc(e.message))}
  busy=false};
 map.on('moveend',load);map.on('overlayadd layeradd',e=>{if(e.layer===lay)load()});map.on('layerremove',e=>{if(e.layer===lay)lay.clearLayers()});
 clearInterval(t);t=setInterval(load,20000);return lay};
