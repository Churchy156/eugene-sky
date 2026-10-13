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
// Overhead layers: satellites (CelesTrak OMM cached on live branch, SGP4 in-browser via satellite.js), terminator, aurora oval, visible passes.
MapX.sats=function(map,LC,statusEl){
 const RAW='https://raw.githubusercontent.com/Churchy156/eugene-sky/live/sats/',CT='https://celestrak.org/NORAD/elements/gp.php?FORMAT=json&GROUP=';
 let el=null;if(statusEl){el=document.createElement('div');el.style.cssText='font:12px system-ui;margin-top:4px';statusEl.after(el)}
 const say=(k,h)=>{if(!el)return;MapX._ss=MapX._ss||{};MapX._ss[k]=h;el.innerHTML=Object.values(MapX._ss).filter(Boolean).join('<br>')};
 const lib=()=>window.satellite?Promise.resolve():(MapX._satLib=MapX._satLib||new Promise((ok,no)=>{const s=document.createElement('script');s.src='https://unpkg.com/satellite.js@6.0.0/dist/satellite.min.js';s.onload=ok;s.onerror=no;document.head.appendChild(s)}));
 const cache={},grp=g=>cache[g]=cache[g]||fetch(RAW+g+'.json?t='+Math.floor(Date.now()/3.6e6)).then(r=>{if(!r.ok)throw 0;return r.json()}).catch(()=>fetch(CT+g).then(r=>r.json()))
   .then(a=>a.map(o=>{try{return{n:o.OBJECT_NAME,id:o.NORAD_CAT_ID,ep:o.EPOCH,r:satellite.json2satrec(o)}}catch(e){return null}}).filter(Boolean));
 const R=L.canvas({padding:.2}),D2R=Math.PI/180;
 const pos=(s,d)=>{const p=satellite.propagate(s.r,d);if(!p||!p.position)return null;const g=satellite.eciToGeodetic(p.position,satellite.gstime(d)),v=p.velocity;
  return{lat:satellite.degreesLat(g.latitude),lon:satellite.degreesLong(g.longitude),alt:g.height,v:Math.hypot(v.x,v.y,v.z),eci:p.position}};
 const info=(s,p,tag)=>`<b>${MapX.esc(s.n)}</b> · ${tag}<br>NORAD ${s.id} · alt ${Math.round(p.alt)} km (${Math.round(p.alt*0.6214)} mi) · ${p.v.toFixed(2)} km/s (${Math.round(p.v*2237)} mph)<br>${p.lat.toFixed(2)}°, ${p.lon.toFixed(2)}° · elements ${MapX.esc((s.ep||'').slice(0,16))}Z`;
 const mkSat=(name,groups,o)=>{const lay=L.layerGroup();LC.addOverlay(lay,name);let t=null,list=null,mk=new Map();
  const tick=async()=>{if(!map.hasLayer(lay))return;try{await lib();if(!list){say(name,name+': loading elements…');list=(await Promise.all(groups.map(grp))).flat()}
   const d=new Date(),b=map.getBounds().pad(.1);let shown=0,tot=0;const seen=new Set();
   for(const s of list){const p=pos(s,d);if(!p||isNaN(p.lat))continue;tot++;let m=mk.get(s.id);
    const inb=b.contains([p.lat,p.lon])&&shown<o.cap;if(!inb){if(m){lay.removeLayer(m);mk.delete(s.id)}continue}shown++;seen.add(s.id);
    if(!m){m=L.circleMarker([p.lat,p.lon],{renderer:R,radius:o.r,color:o.c,weight:o.w||0,fillColor:o.c,fillOpacity:.9}).addTo(lay);if(o.label)m.bindTooltip(s.n.replace(/\s*\(.*\)/,''),{permanent:true,direction:'right',className:'',offset:[6,0]});mk.set(s.id,m)}
    else m.setLatLng([p.lat,p.lon]);m._s=s;m.bindPopup(()=>{const q=pos(m._s,new Date());return info(m._s,q,name)})}
   if(o.track)o.track(list,d);
   say(name,`${name}: <b>${tot}</b> tracked, ${shown} drawn in view${shown>=o.cap?' (cap '+o.cap+')':''} · SGP4 every ${o.dt/1000}s`)}catch(e){say(name,name+': load error '+MapX.esc(e.message||e))}};
  map.on('overlayadd layeradd',e=>{if(e.layer===lay){tick();clearInterval(t);t=setInterval(tick,o.dt)}});
  map.on('layerremove',e=>{if(e.layer===lay){clearInterval(t);lay.clearLayers();mk.clear();say(name,'')}});map.on('moveend',tick);return lay};
 const L1=mkSat('🛰️ Starlink',['starlink'],{cap:4000,r:2,c:'#e6edf3',dt:8000});
 const trk=L.layerGroup();
 const L2=mkSat('🚀 ISS + Tiangong',['stations'],{cap:60,r:5,c:'#f2cc60',w:1,dt:5000,label:1,track:(list,d)=>{if(d-(trk._t||0)<60000&&trk.getLayers().length)return;trk._t=+d;trk.clearLayers();
   list.filter(s=>/^ISS \(ZARYA\)|^CSS \(TIANHE\)/.test(s.n)).forEach(s=>{let seg=[],last=null;const segs=[];
    for(let m=-45;m<=95;m+=1){const p=pos(s,new Date(+d+m*6e4));if(!p)continue;if(last!=null&&Math.abs(p.lon-last)>180){segs.push(seg);seg=[]}seg.push([p.lat,p.lon]);last=p.lon}segs.push(seg);
    segs.forEach(g=>L.polyline(g,{color:/ISS/.test(s.n)?'#f2cc60':'#ff7b72',weight:1.5,opacity:.8,dashArray:'4 4',interactive:false}).addTo(trk))});trk.addTo(L2)}});
 mkSat('🧭 GPS/GNSS sats',['gps-ops','glo-ops','galileo','beidou'],{cap:400,r:3,c:'#3fb950',dt:10000});
 mkSat('🌦️ Weather sats (NOAA/GOES/etc)',['weather','goes'],{cap:300,r:3.5,c:'#58a6ff',dt:10000});
 // Day/night terminator
 const term=L.layerGroup();LC.addOverlay(term,'🌗 Day/night');
 const sun=d=>{const n=(d/864e5)+2440587.5-2451545,Lm=(280.46+.9856474*n)%360,g=(357.528+.9856003*n)*D2R,lam=(Lm+1.915*Math.sin(g)+.02*Math.sin(2*g))*D2R,eps=(23.439-4e-7*n)*D2R;
  const dec=Math.asin(Math.sin(eps)*Math.sin(lam)),ra=Math.atan2(Math.cos(eps)*Math.sin(lam),Math.cos(lam)),gmst=(18.697374558+24.06570982441908*n)%24*15*D2R;return{dec,ra,gmst,lon:((ra-gmst)/D2R+540)%360-180,lat:dec/D2R}};
 const drawT=()=>{if(!map.hasLayer(term))return;term.clearLayers();const s=sun(new Date()),pts=[];
  for(let lo=-180;lo<=180;lo+=2){const la=Math.atan(-Math.cos((lo-s.lon)*D2R)/Math.tan(s.dec))/D2R;pts.push([la,lo])}const pole=s.dec>0?-90:90;
  L.polygon([[pole,-180],...pts,[pole,180]],{color:'#000',weight:0,fillColor:'#000',fillOpacity:.32,interactive:false}).addTo(term);
  L.circleMarker([s.lat,s.lon],{radius:7,color:'#ffd33d',fillColor:'#ffd33d',fillOpacity:1}).bindTooltip('☀️ Subsolar point').addTo(term)};
 map.on('overlayadd layeradd',e=>{if(e.layer===term)drawT()});setInterval(drawT,60000);
 // Aurora oval (NOAA SWPC OVATION, ~30-90 min forecast)
 const aur=L.layerGroup();LC.addOverlay(aur,'🌌 Aurora oval');
 const drawA=async()=>{if(!map.hasLayer(aur))return;try{const j=await fetch('https://services.swpc.noaa.gov/json/ovation_aurora_latest.json').then(r=>r.json());aur.clearLayers();let n=0;
   j.coordinates.forEach(([lo,la,v])=>{if(v<8)return;n++;lo=lo>180?lo-360:lo;L.rectangle([[la-.5,lo-.5],[la+.5,lo+.5]],{renderer:R,weight:0,fillColor:v>50?'#ff4d6d':v>25?'#f2cc60':'#3fb950',fillOpacity:Math.min(.7,.15+v/80),interactive:false}).addTo(aur)});
   say('aur',`🌌 Aurora (NOAA OVATION) forecast for ${new Date(j['Forecast Time']).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}: ${n} cells ≥8% probability (green ≥8, yellow ≥25, red ≥50)`)}catch(e){say('aur','🌌 Aurora load error')}};
 map.on('overlayadd layeradd',e=>{if(e.layer===aur)drawA()});map.on('layerremove',e=>{if(e.layer===aur)say('aur','')});setInterval(drawA,15*60000);
 // Visible passes over the chosen location (map center unless MapX.home set)
 MapX.passes=async(lat,lon)=>{await lib();const obs={latitude:lat*D2R,longitude:lon*D2R,height:.1},list=[...await grp('stations'),...await grp('visual')],seen=new Set(),out=[],t0=Date.now();
  const sunEl=d=>{const s=sun(d),H=s.gmst+lon*D2R-s.ra;return Math.asin(Math.sin(lat*D2R)*Math.sin(s.dec)+Math.cos(lat*D2R)*Math.cos(s.dec)*Math.cos(H))/D2R};
  const lit=(p,d)=>{const s=sun(d),u=[Math.cos(s.dec)*Math.cos(s.ra),Math.cos(s.dec)*Math.sin(s.ra),Math.sin(s.dec)],r=p.eci,dot=r.x*u[0]+r.y*u[1]+r.z*u[2];if(dot>0)return true;return Math.hypot(r.x-dot*u[0],r.y-dot*u[1],r.z-dot*u[2])>6371};
  for(const s of list){if(seen.has(s.id)||(/^(ISS|CSS) \(/.test(s.n)&&!/ISS \(ZARYA\)|CSS \(TIANHE\)/.test(s.n)))continue;seen.add(s.id);const bright=/ISS \(ZARYA\)|CSS \(TIANHE\)/.test(s.n);let cur=null;
   for(let m=0;m<36*60;m+=1){const d=new Date(t0+m*6e4),p=satellite.propagate(s.r,d);if(!p||!p.position)break;const la=satellite.ecfToLookAngles(obs,satellite.eciToEcf(p.position,satellite.gstime(d))),el=la.elevation/D2R;
    if(el>10&&sunEl(d)<-6&&lit({eci:p.position},d)){if(!cur)cur={s,start:d,max:el,az:la.azimuth/D2R};else if(el>cur.max){cur.max=el}cur.end=d}else if(cur){out.push(cur);cur=null;if(!bright)break}}
   if(cur)out.push(cur)}
  out.sort((a,b)=>(b.s.n.match(/ISS|CSS/)?1:0)-(a.s.n.match(/ISS|CSS/)?1:0)||a.start-b.start);const pr=out.filter(x=>/ISS|CSS/.test(x.s.n)).slice(0,6).concat(out.filter(x=>!/ISS|CSS/.test(x.s.n)).sort((a,b)=>a.start-b.start).slice(0,12));
  const dir=a=>['N','NE','E','SE','S','SW','W','NW'][Math.round(a/45)%8],f=d=>d.toLocaleString([], {weekday:'short',hour:'numeric',minute:'2-digit'});
  return `<b>🔭 Visible passes, next 36 h</b> near ${lat.toFixed(2)}, ${lon.toFixed(2)}<br><small>sat sunlit, sky dark (sun &lt; −6°), &gt;10° up · 1-min steps</small><table style="font-size:12px">`+
   (pr.length?pr.map(x=>`<tr><td>${MapX.esc(x.s.n.replace(/\s*\(.*\)/,''))}${/ISS|CSS/.test(x.s.n)?' ⭐':''}</td><td>${f(x.start)}</td><td>${Math.round((x.end-x.start)/6e4)+1} min</td><td>max ${Math.round(x.max)}°, rises ${dir(x.az)}</td></tr>`).join(''):'<tr><td>No visible passes found (daylight or no dark-sky windows).</td></tr>')+'</table>'};
 const pb=L.layerGroup();LC.addOverlay(pb,'🔭 Visible passes');
 map.on('overlayadd layeradd',async e=>{if(e.layer!==pb)return;const c=MapX.home||map.getCenter();say('pass','🔭 Computing passes…');try{const h=await MapX.passes(c.lat,c.lng);say('pass','');L.popup({maxWidth:420}).setLatLng(c).setContent(h).openOn(map)}catch(er){say('pass','🔭 pass error '+MapX.esc(er.message||er))}setTimeout(()=>map.removeLayer(pb),50)});
 return L1};
