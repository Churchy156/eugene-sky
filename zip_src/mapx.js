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
 async traffic(map,base,lat,lon,st,noteEl){
  const cam=L.layerGroup(),inc=L.layerGroup(),wz=L.layerGroup(),ov={'📷 Traffic cameras':cam,'🚧 Incidents/closures':inc,'🦺 Work zones (WZDx)':wz};
  try{const [cv,d]=await Promise.all([fetch(base+'traffic/coverage.json').then(r=>r.json()),fetch(base+`traffic/${st}.json`).then(r=>r.ok?r.json():null)]);
   const c=(cv.states||{})[st]||{},R=200,near=a=>(a||[]).filter(x=>kmx(lat,lon,x[0],x[1])<R);
   if(d){near(d.cam).forEach(x=>L.circleMarker([x[0],x[1]],{radius:4,color:'#e6edf3',fillColor:'#2f81f7',fillOpacity:1,weight:1}).bindPopup(()=>`<b>${esc(x[2])}</b><br><img src="${esc(x[3])}?t=${Date.now()}" style="width:300px;max-width:70vw" onerror="this.alt='image unavailable'">`,{maxWidth:320}).addTo(cam));
    near(d.inc).forEach(x=>L.circleMarker([x[0],x[1]],{radius:5,color:'#f85149',fillOpacity:.8}).bindPopup(`<b>${esc(x[2])}</b><br>${esc(x[3])}<br><span style="color:#888">${esc(x[4])}</span>`).addTo(inc));
    near(d.wz).forEach(x=>L.circleMarker([x[0],x[1]],{radius:4,color:'#e3b341',fillOpacity:.8}).bindPopup(`<b>${esc(x[2])}</b><br>${esc(x[3])}<br>${esc(x[4])} → ${esc(x[5])}`).addTo(wz))}
   const lab=k=>c[k]?c[k].join(', '):'none for '+st;
   if(noteEl)noteEl.innerHTML=`<b>Traffic coverage for ${st}</b> (snapshot ${new Date(cv.built).toLocaleString([], {timeZoneName:'short'})}, refreshed every 3 h; cameras load live when clicked): cameras — ${esc(lab('cam'))}; incidents — ${esc(lab('inc'))}; work zones — ${esc(lab('wz'))}. States with any feed: ${Object.keys(cv.states).sort().join(', ')}.`;
  }catch(e){if(noteEl)noteEl.textContent='Traffic data unavailable: '+e.message}
  return ov}
};})();
