// GeoNet (NZ) + Pacific Ring of Fire layers for the World view.
// RF.init(map, LC, detEl, panelEl) — adds overlays synchronously (so MapX.buttons lists them), fills them async.
// Data: live fetch where the source allows CORS (GeoNet, USGS); otherwise the 10-min relay snapshot on the 'live'
// branch, falling back to the 3-hourly CI snapshot ../zip/data/ringfire.json.
window.RF=(()=>{
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const LIVE='https://raw.githubusercontent.com/Churchy156/eugene-sky/live/live/ringfire.json',SNAP='../zip/data/ringfire.json';
const VCOL=['#3fb950','#e3b341','#f0883e','#f85149'],VNAME=['Normal','Advisory / yellow','Watch / orange','Warning / red'];
const ago=t=>{const m=(Date.now()-Date.parse(t))/6e4;return isNaN(m)?'':m<90?Math.round(m)+' min ago':m<2880?Math.round(m/60)+' h ago':Math.round(m/1440)+' d ago'};
const when=t=>{const d=new Date(t);return isNaN(d)?esc(t):d.toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'})+' ('+ago(t)+')'};
const J=u=>fetch(u,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()});
const mmiCol=m=>['#9fb3c8','#9fb3c8','#74c0fc','#3fb950','#e3b341','#f0883e','#f85149','#d1242f','#a40e26'][Math.max(0,Math.min(8,m|0))];
function init(map,LC,det,panel){
 const ov=n=>{const g=L.layerGroup();LC.addOverlay(g,n);return g};
 const L_nz=ov('🇳🇿 GeoNet NZ quakes (felt, MMI 3+)'),L_val=ov('🌋 Volcano alert levels (NZ · US · Japan · PH · Indonesia)'),
  L_ring=ov('🔥 Ring of Fire outline'),L_pl=ov('🧩 Plate boundaries (quake faults, PB2002)'),L_pq=ov('💥 Ring of Fire quakes M4.5+ (7 d, USGS)'),
  L_ts=ov('🌊 Tsunami alerts (PTWC / NTWC)'),L_er=ov('🌋 Erupting volcanoes (Smithsonian GVP, continuing)'),
  L_th=ov('📜 NCEI tsunami hazard history since 1950'),L_id=ov('🇮🇩 BMKG Indonesia quakes M5+'),L_int=ov('📳 GeoNet quake shaking intensity (measured)');
 const show=h=>{if(det)det.innerHTML=h};
 const pop=(lay,h)=>lay.bindPopup(h,{maxWidth:320}).on('popupopen',()=>show(h));
 const S={status:{}};let mask=null;
 const inRof=(la,lo)=>mask&&mask.has(Math.floor(la)+','+Math.floor(((lo+180)%360+360)%360-180));
 const st=()=>{if(!panel)return;const v=(S.volcanoes||[]).filter(x=>x.level>0).sort((a,b)=>b.level-a.level),ts=(S.tsunami||[]),act=ts.filter(t=>t.active),pq=S._pq||[];
  panel.innerHTML=`<b>🔥 Ring of Fire now</b> <span style="color:#9fb3c8">(snapshot ${S.built?when(S.built):'loading…'}${S._src?' · '+S._src:''})</span><br>
  🌊 Tsunami: ${act.length?act.map(t=>`<b style="color:#f85149">${esc(t.category)}</b> — ${esc(t.title)} (${esc(t.center)}, ${when(t.t)}) <a target=_blank href="${esc(t.url)}">bulletin</a>`).join('<br>'):'<b style="color:#3fb950">no active warnings/advisories/watches</b>'+(ts.length?` · latest message: ${esc(ts[0].category)} — ${esc(ts[0].title)}, ${when(ts[0].t)}`:'')}<br>
  💥 Pacific M6+ in last 7 d: ${pq.filter(q=>q.mag>=6).map(q=>`<b>M${q.mag}</b> ${esc(q.place)} (${when(q.t)})`).join('; ')||'none'} · M4.5+ count: ${pq.length}<br>
  🌋 Elevated volcanoes (${v.length}): ${v.map(x=>`<span style="color:${VCOL[x.level]}">●</span> ${esc(x.name)} <span style="color:#9fb3c8">${esc(x.native)}</span>`).join(', ')||'none'}<br>
  🇳🇿 GeoNet: ${(S.geonet_news||[]).slice(0,2).map(n=>`<a target=_blank href="${esc(n.url)}">${esc(n.title)}</a> (${when(n.t)})`).join(' · ')}<br>
  <span style="color:#9fb3c8;font-size:11px">Sources: ${Object.entries(S.status||{}).map(([k,v])=>`${esc(k)} ${/^ok/.test(v)?'✓':'✗ '+esc(v)}`).join(' · ')}</span>`};
 // static: ring + plates + mask
 J('../zip/data/plates_rof.json').then(P=>{
  P.ring.forEach(r=>{const l=L.polyline(r.p,{color:r.c=='CTF'?'#f0883e':'#f85149',weight:r.c=='SUB'?3:2,opacity:.85,dashArray:r.c=='CTF'?'6 4':null});
   pop(l,`<b>🔥 Pacific Ring of Fire</b><br>${{SUB:'Subduction zone',OCB:'Ocean–continent convergent boundary',CTF:'Continental transform fault'}[r.c]||esc(r.c)}<br><span style="color:#9fb3c8">Approximate outline from PB2002 plate-boundary steps (Bird 2003). Quakes within ~400 km count as "Ring of Fire" in the daily dataset.</span>`);l.addTo(L_ring)});
  P.plates.forEach(b=>{const l=L.polyline(b.p,{color:b.t=='subduction'?'#ff7b72':'#a5d6ff',weight:1.2,opacity:.7});pop(l,`<b>🧩 Plate boundary ${esc(b.n)}</b><br>${b.t?esc(b.t):'ridge / transform / other'}<br><span style="color:#9fb3c8">PB2002 (Bird 2003)</span>`);l.addTo(L_pl)})}).catch(e=>console.warn('plates',e));
 const mp=J('../zip/data/rof_mask.json').then(m=>{mask=new Set(m.cells.map(c=>c[0]+','+c[1]))}).catch(()=>{});
 // GeoNet live (CORS *)
 const nzq=q=>{L_nz.clearLayers();q.forEach(e=>{const h=`<b>🇳🇿 M${(+e.mag).toFixed(1)} ${esc(e.place)}</b><br>${when(e.t)}<br>Depth ${(+e.depth).toFixed(0)} km · MMI ${esc(e.mmi)} · quality ${esc(e.quality)}<br><a target=_blank href="${esc(e.url)}">GeoNet event page</a>`;
  pop(L.circleMarker([e.lat,e.lon],{radius:Math.max(3,e.mag*2),color:mmiCol(e.mmi),weight:1,fillOpacity:.55}).bindTooltip(`M${(+e.mag).toFixed(1)} ${esc(e.place)}`),h).addTo(L_nz)})};
 fetch('https://api.geonet.org.nz/quake?MMI=3',{headers:{Accept:'application/vnd.geo+json;version=2'}}).then(r=>r.json()).then(j=>nzq(j.features.filter(f=>f.properties.quality!='deleted').map(f=>({lat:f.geometry.coordinates[1],lon:f.geometry.coordinates[0],t:f.properties.time,mag:f.properties.magnitude,depth:f.properties.depth,mmi:f.properties.mmi,place:f.properties.locality,quality:f.properties.quality,url:'https://www.geonet.org.nz/earthquake/'+f.properties.publicID})))).catch(()=>S._nzFallback=true);
 // USGS live (CORS *), filtered to the Ring of Fire mask
 const pq=q=>{S._pq=q;L_pq.clearLayers();q.forEach(e=>{const h=`<b>💥 M${e.mag} ${esc(e.place)}</b><br>${when(e.t)}<br>Depth ${(+e.depth).toFixed(0)} km${e.tsunami?' · <b>tsunami flag</b>':''}${e.alert?' · PAGER '+esc(e.alert):''}<br><a target=_blank href="${esc(e.url)}">USGS event page</a>`;
  pop(L.circleMarker([e.lat,e.lon],{radius:Math.max(3,(e.mag-3)*3),color:e.mag>=6?'#f85149':'#f0883e',weight:1,fillOpacity:.5}).bindTooltip(`M${e.mag} ${esc(e.place)}`),h).addTo(L_pq)});st()};
 mp.then(()=>J('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson')).then(j=>pq(j.features.filter(f=>inRof(f.geometry.coordinates[1],f.geometry.coordinates[0])).map(f=>({id:f.id,lat:f.geometry.coordinates[1],lon:f.geometry.coordinates[0],depth:f.geometry.coordinates[2],t:new Date(f.properties.time).toISOString(),mag:f.properties.mag,place:f.properties.place,tsunami:f.properties.tsunami,alert:f.properties.alert,url:f.properties.url})))).catch(()=>S._pqFallback=true);
 // snapshots: newest of live relay and CI snapshot; CI snapshot also has NCEI history + GVP continuing
 Promise.allSettled([J(LIVE),J(SNAP)]).then(([a,b])=>{const A=a.value,B=b.value,use=A&&(!B||A.built>=B.built)?A:B;if(!use){if(panel)panel.textContent='Ring of Fire snapshot unavailable.';return}
  Object.assign(S,use);S._src=use===A?'10-min relay':'3-hourly build';if(B){S.ncei_tsunamis=B.ncei_tsunamis;S.gvp_continuing=B.gvp_continuing}
  if(S._nzFallback)nzq(S.geonet_quakes||[]);if(S._pqFallback||!S._pq)pq(S.usgs_rof||[]);
  (S.volcanoes||[]).forEach(v=>{if(v.lat==null)return;const h=`<b>🌋 ${esc(v.name)}</b> — <span style="color:${VCOL[v.level]}">${VNAME[v.level]}</span><br>${esc(v.src)}: ${esc(v.native)}${v.obs?' ('+esc(v.obs)+')':''}${v.activity?'<br>'+esc(v.activity):''}${v.hazards?'<br><i>'+esc(v.hazards)+'</i>':''}${v.sent?'<br>Issued '+when(v.sent):''}<br><a target=_blank href="${esc(v.url)}">source</a>`;
   pop(L.circleMarker([v.lat,v.lon],{radius:v.level?7:4,color:'#111',weight:1,fillColor:VCOL[v.level],fillOpacity:.95}).bindTooltip(`${esc(v.name)}: ${esc(v.native)}`),h).addTo(L_val)});
  (S.tsunami||[]).forEach(t=>{if(t.lat==null)return;const h=`<b>🌊 ${esc(t.center)}: ${esc(t.category)}</b>${t.active?' <b style="color:#f85149">ACTIVE</b>':' (not active)'}<br>${esc(t.title)}${t.mag?' · M'+t.mag:''}<br>${when(t.t)}<br><span style="font-size:12px">${esc(t.summary)}</span><br><a target=_blank href="${esc(t.url)}">bulletin</a>`;
   pop(L.circleMarker([t.lat,t.lon],{radius:t.active?12:7,color:t.active?'#f85149':'#58a6ff',weight:2,fillOpacity:.25}),h).addTo(L_ts)});
  (S.gvp_continuing||[]).forEach(v=>pop(L.marker([v.lat,v.lon],{icon:L.divIcon({html:'🌋',className:'',iconSize:[18,18]})}).bindTooltip(esc(v.name)),`<b>🌋 ${esc(v.name)}</b><br>Erupting since ${esc(v.since)} (Smithsonian GVP; continuing)<br><a target=_blank href="${esc(v.url)}">GVP volcano page</a>`).addTo(L_er));
  (S.ncei_tsunamis||[]).forEach(e=>pop(L.circleMarker([e.lat,e.lon],{radius:e.deaths>100?7:e.h>3?5:3,color:e.deaths>0?'#f85149':'#58a6ff',weight:1,fillOpacity:.5}),`<b>📜 Tsunami ${esc(e.t)}</b><br>${esc(e.place)} (${esc(e.country)})${e.mag?'<br>Quake M'+e.mag:''}${e.h!=null?'<br>Max water height '+e.h+' m':''}${e.deaths?'<br>Deaths: '+e.deaths:''}<br><a target=_blank href="https://www.ngdc.noaa.gov/hazel/view/hazards/tsunami/event-more-info/${esc(e.id)}">NCEI record</a>`).addTo(L_th));
  (S.bmkg||[]).forEach(e=>pop(L.circleMarker([e.lat,e.lon],{radius:Math.max(3,(e.mag-3)*3),color:'#d2a8ff',weight:1,fillOpacity:.5}),`<b>🇮🇩 M${e.mag} ${esc(e.place)}</b><br>${when(e.t)} · depth ${esc(e.depth)}<br>${esc(e.tsunami)}<br><a target=_blank href="${esc(e.url)}">BMKG</a>`).addTo(L_id));
  (S.geonet_intensity||[]).forEach(([la,lo,m])=>L.circleMarker([la,lo],{radius:3,stroke:false,fillColor:mmiCol(m),fillOpacity:.8}).bindTooltip('MMI '+m).addTo(L_int));
  st()});
 st();RF.map=map;RF.layers={nz:L_nz,val:L_val,ring:L_ring,plates:L_pl,pq:L_pq,ts:L_ts,er:L_er,th:L_th,id:L_id,int:L_int};return {S}}
return {init}})();
