'use strict';
// ---------- 🚗 Driving trips ----------
// Same rules as zip_tools/drive_core.py (the email updates), so the page and the emails agree.
// Sources (free, no keys in the browser): OSRM demo router, Open-Meteo hourly forecast, NWS alerts, Photon place names,
// and our relay (ODOT TripCheck / CHP / state work-zone feeds, the key stays on the server). No live traffic speeds.
const LIVE='https://raw.githubusercontent.com/Churchy156/eugene-sky/live/traffic/';
const TRIPS_URL='https://raw.githubusercontent.com/Churchy156/eugene-sky/main/data/trips.json';
const PASSES=[['Santiam Pass (US 20)',44.4248,-121.8536,4817],['Willamette Pass (OR 58)',43.5955,-122.0357,5128],['McKenzie Pass (OR 242)',44.26,-121.81,5325],
 ['Mt Hood / Government Camp (US 26)',45.3018,-121.7465,4000],['Siskiyou Summit (I-5)',42.075,-122.605,4310],['Sexton Summit (I-5)',42.602,-123.364,1960],
 ['Black Butte Summit (I-5)',41.36,-122.33,3912],['Deadman Pass / Cabbage Hill (I-84)',45.6045,-118.535,3615],['Snoqualmie Pass (I-90)',47.4245,-121.413,3022],
 ['Stevens Pass (US 2)',47.7466,-121.0859,4061],['White Pass (US 12)',46.6376,-121.3912,4500],['Donner Summit (I-80)',39.3233,-120.3283,7227],
 ['Echo Summit (US 50)',38.8126,-120.0303,7382],['Chemult / US 97 high desert',43.22,-121.78,4760]];
const METROS=[['Portland',45.52,-122.68,15,25],['Seattle',47.61,-122.33,15,30],['Tacoma',47.25,-122.44,8,15],['Salem',44.94,-123.03,6,5],['Eugene-Springfield',44.05,-123.05,6,5],
 ['Sacramento',38.58,-121.49,12,20],['San Francisco Bay Area',37.77,-122.27,25,35],['Boise',43.61,-116.2,8,10],['Bend',44.06,-121.31,4,5]];
const RUSH=[[6.5,9.5],[15,18.5]];
const STATE_BOX={OR:[41.9,46.3,-124.7,-116.4],WA:[45.5,49.1,-124.9,-116.9],CA:[32.5,42.1,-124.5,-114.1],ID:[41.9,49.1,-117.3,-111],NV:[35,42.1,-120.1,-114]};
const TZ='America/Los_Angeles';
const mi2=(a,b)=>dist({lat:a[0],lon:a[1]},{lat:b[0],lon:b[1]});
// PT wall-clock "2026-10-30T10:00" <-> epoch ms, regardless of the browser's own time zone
function ptOff(ms){const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:TZ,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).formatToParts(ms).map(x=>[x.type,x.value]));
  return Date.UTC(+p.year,p.month-1,+p.day,+p.hour%24,+p.minute,+p.second)-ms}
function ptToMs(s){const g=Date.parse(s.length===16?s+':00Z':s+'Z');let t=g-ptOff(g);return g-ptOff(t)}
const ptT=ms=>new Date(ms).toLocaleTimeString('en-US',{timeZone:TZ,hour:'numeric',minute:'2-digit'});
const ptD=ms=>new Date(ms).toLocaleDateString('en-US',{timeZone:TZ,weekday:'short',month:'short',day:'numeric'});
const ptParts=ms=>{const o=ptOff(ms),d=new Date(ms+o);return{h:d.getUTCHours()+d.getUTCMinutes()/60,wd:d.getUTCDay(),ymd:d.toISOString().slice(0,10)}};
const fmtMin=m=>{m=Math.round(m);return m>=60?`${Math.floor(m/60)} h ${String(m%60).padStart(2,'0')} min`:`${m} min`};
function classify(t){
  if(/\bclos(ed|ure|ing)\b|blocked|impassable/i.test(t)&&!/shoulder clos|lane clos/i.test(t))return['closure',30];
  if(/no (traffic )?impacts?|no delay/i.test(t))return['notice',0];
  if(/construction|work(ers| zone| is being done)|paving|striping|signage|maintenance|lane clos|shoulder/i.test(t))return['roadwork',3];
  if(/minimal delay|use caution|fire in the area/i.test(t))return['notice',0];
  return['incident',10];
}
async function route(a,b){
  const j=await cj(`https://router.project-osrm.org/route/v1/driving/${a.lon.toFixed(5)},${a.lat.toFixed(5)};${b.lon.toFixed(5)},${b.lat.toFixed(5)}?overview=full&geometries=geojson&annotations=duration`,360);
  if(!j.routes||!j.routes[0])throw new Error('No driving route found between those places.');
  const r=j.routes[0],c=r.geometry.coordinates.map(([x,y])=>[y,x]),ann=r.legs[0].annotation.duration,tot=ann.reduce((s,x)=>s+x,0)||1,k=r.duration/tot;
  const ct=[0];ann.forEach(d=>ct.push(ct[ct.length-1]+d*k));const cm=[0];for(let i=1;i<c.length;i++)cm.push(cm[i-1]+mi2(c[i-1],c[i]));
  return{miles:r.distance/1609.344,secs:r.duration,coords:c,ct:ct.slice(0,c.length),cm};
}
function near(R,p,maxmi){let best=[1e9,0];const dl=maxmi/69+0.02;R.coords.forEach((q,i)=>{if(Math.abs(q[0]-p[0])>dl||Math.abs(q[1]-p[1])>dl*1.5)return;const d=mi2(p,q);if(d<best[0])best=[d,i]});return best}
async function samplePts(R){
  const out=[],step=Math.max(15,R.miles/18);let nx=0;
  R.cm.forEach((m,i)=>{if(m>=nx||i===R.coords.length-1){out.push({i,name:`${Math.round(m)} mi along`,lat:R.coords[i][0],lon:R.coords[i][1]});nx=m+step}});
  await Promise.all(out.map(async s=>{try{const j=await cj(`https://photon.komoot.io/reverse?lat=${s.lat.toFixed(3)}&lon=${s.lon.toFixed(3)}&lang=en&limit=1&radius=20&osm_tag=place:city&osm_tag=place:town&osm_tag=place:village&osm_tag=place:hamlet`,1e5);const p=j.features[0]?.properties;
    const n=p&&p.name;if(n)s.name=`${n}${p.state?', '+(STATE_AB[p.state]||p.state):''}`}catch(e){}}));
  PASSES.forEach(([n,la,lo,ft])=>{const[d,i]=near(R,[la,lo],3);if(d<=3)out.push({i,name:n,lat:la,lon:lo,pass:true,ft})});
  out.sort((a,b)=>a.i-b.i);out.forEach(s=>{s.toff=R.ct[s.i];s.mi=R.cm[s.i]});return out;
}
const STATE_AB={Oregon:'OR',Washington:'WA',California:'CA',Idaho:'ID',Nevada:'NV'};
async function routeWx(S){
  const j=await cj(`https://api.open-meteo.com/v1/forecast?latitude=${S.map(s=>s.lat.toFixed(3))}&longitude=${S.map(s=>s.lon.toFixed(3))}&hourly=temperature_2m,precipitation,snowfall,weather_code,visibility,wind_gusts_10m&timeformat=unixtime&forecast_days=16&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph`,60,{om:true});
  return Array.isArray(j)?j:[j];
}
function wxAt(W,ts){const h=W.hourly,t=h.time;if(!t.length||ts<t[0]-3600||ts>t[t.length-1]+3600)return null;let i=0,bd=1e18;t.forEach((x,k)=>{const d=Math.abs(x-ts);if(d<bd){bd=d;i=k}});
  const g=k=>(h[k]||[])[i];return{temp:g('temperature_2m'),pr:g('precipitation')||0,snow:g('snowfall')||0,code:g('weather_code'),vis:g('visibility'),gust:g('wind_gusts_10m')}}
function wxKind(w){if(!w)return null;const c=w.code||0;
  if(w.snow>=0.01||[71,73,75,77,85,86].includes(c))return'snow';
  if([56,57,66,67].includes(c)||(w.temp!=null&&w.temp<=34&&w.pr>=0.01))return'ice';
  if([65,82].includes(c)||w.pr>=0.2)return'heavy rain';
  if([61,63,80,81,51,53,55].includes(c)||w.pr>=0.02)return'rain';return null}
async function routeAlerts(S){const seen={};
  await Promise.all(S.filter((s,k)=>s.pass||k%2===0).slice(0,10).map(async p=>{try{const j=await cj(`https://api.weather.gov/alerts/active?point=${p.lat.toFixed(3)},${p.lon.toFixed(3)}`,10);
    j.features.forEach(f=>{const a=f.properties;if(a.status!=='Actual'||a.messageType==='Cancel')return;const k=(a.event||'')+'|'+(a.areaDesc||'').slice(0,40);
      if(!seen[k])seen[k]={event:a.event,headline:a.headline||a.event,near:p.name,url:'https://api.weather.gov/alerts/'+a.id}})}catch(e){}}));
  return Object.values(seen)}
function statesOn(R){const s=new Set();R.coords.filter((_,i)=>i%25===0).concat([R.coords[R.coords.length-1]]).forEach(([la,lo])=>{for(const[k,[a,b,c,d]]of Object.entries(STATE_BOX))if(la>=a&&la<=b&&lo>=c&&lo<=d)s.add(k)});return[...s].sort()}
async function roadReports(R){const out={inc:[],wz:[],cam:[],src:[]};
  for(const s of statesOn(R)){let d=null;for(const[u,lbl]of[[RELAY+'/traffic/'+s+'.json','relay'],[LIVE+s+'.json','backup copy']]){try{d=await cj(u,2);out.src.push(`${s} (${lbl}, ${(d.built||'').slice(0,16).replace('T',' ')} UTC)`);break}catch(e){}}
    if(d)['inc','wz','cam'].forEach(k=>out[k].push(...(d[k]||[])));else out.src.push(s+' (road reports unavailable right now)')}
  return out}
async function planDrive(l){
  const a=l.fromLoc,b=l.toLoc,R=await route(a,b),S=await samplePts(R);
  const [W,rr,alerts]=await Promise.all([routeWx(S),roadReports(R),routeAlerts(S)]);
  const driveMin=R.secs/60,base=Math.max(10,Math.round(driveMin*.05)),mode=l.mode==='depart'?'depart':'arrive',tgt=ptToMs(l.when),day=ptParts(tgt).ymd;
  const issues=[];let incMin=0,wzMin=0;
  rr.inc.forEach(x=>{const[d,i]=near(R,[x[0],x[1]],.5);if(d>.5)return;const k='i'+x[2]+'|'+String(x[3]).slice(0,80);if(issues.some(z=>z.key===k))return;const[kd,add]=classify(`${x[2]} ${x[3]}`);incMin+=add;issues.push({key:k,kind:kd,road:x[2],text:x[3],mi:R.cm[i],lat:x[0],lon:x[1],add})});
  rr.wz.forEach(x=>{if(x.length>5&&((x[4]&&x[4]>day)||(x[5]&&x[5]<day)))return;const[d,i]=near(R,[x[0],x[1]],.3);if(d>.3)return;const k='w'+x[2]+'|'+String(x[3]).slice(0,60);if(issues.some(z=>z.key===k))return;
    const add=/no (traffic )?impact|no delay/i.test(x[3])?0:3;wzMin+=add;issues.push({key:k,kind:'work zone',road:x[2],text:x[3],mi:R.cm[i],lat:x[0],lon:x[1],add})});
  incMin=Math.min(incMin,60);wzMin=Math.min(wzMin,15);
  const cams=rr.cam.map(x=>{const[d,i]=near(R,[x[0],x[1]],.4);return d<=.4?{name:x[2],url:x[3],mi:R.cm[i],lat:x[0],lon:x[1]}:null}).filter(Boolean).sort((a,b)=>a.mi-b.mi).slice(0,40);
  let nwsPct=0,nwsMin=0;alerts.forEach(a=>{const e=(a.event||'').toLowerCase();if(/winter storm warning|ice storm|blizzard/.test(e))nwsPct=Math.max(nwsPct,30);else if(/winter weather advisory|winter storm watch|freezing (rain|drizzle|fog)/.test(e))nwsPct=Math.max(nwsPct,15);else if(/high wind|dense fog|flood|dust|smoke/.test(e))nwsMin=10});
  const evaluate=leave=>{const rs=[],wx=[];let worst=0,fog=false,gust=false,icy=false;const pts=[];
    S.forEach((s,k)=>{const ts=leave/1000+s.toff,x=wxAt(W[k],ts),kd=wxKind(x);pts.push({...s,t:ts*1000,w:x,kind:kd});if(!x)return;
      const pct={snow:25,ice:25,'heavy rain':10,rain:5}[kd]||0;if(pct>worst)worst=pct;if(kd)wx.push([kd,s.name,ts]);
      if(x.vis!=null&&x.vis<800)fog=s.name;if((x.gust||0)>=45)gust=s.name;if(s.pass&&x.temp!=null&&x.temp<=32&&!kd)icy=s.name});
    if(worst){const rk={snow:4,ice:4,'heavy rain':2,rain:1},k0=wx.reduce((m,z)=>rk[z[0]]>rk[m[0]]?z:m),pl=[...new Set(wx.filter(z=>z[0]===k0[0]).map(z=>z[1]))].sort().slice(0,3);
      rs.push([worst<25?Math.round(driveMin*worst/100):Math.max(15,Math.round(driveMin*worst/100)),`${k0[0][0].toUpperCase()+k0[0].slice(1)} in the forecast near ${pl.join(', ')} around ${ptT(k0[2]*1000)} PT`+(['snow','ice'].includes(k0[0])?' — carry chains and check TripCheck before the pass':'')])}
    if(fog)rs.push([10,`Fog (under half a mile visibility) near ${fog}`]);if(gust)rs.push([10,`Strong wind gusts (45+ mph) near ${gust}`]);if(icy)rs.push([5,`Below freezing at ${icy} — watch for icy patches`]);
    METROS.forEach(([n,la,lo,rad,ex])=>{const[d,i]=near(R,[la,lo],rad);if(d>rad)return;const t=leave+R.ct[i]*1000,p=ptParts(t);if(p.wd>=1&&p.wd<=5&&RUSH.some(([a,b])=>p.h>=a&&p.h<=b))rs.push([ex,`Usual weekday rush hour in ${n} (you'd be there about ${ptT(t)} PT)`])});
    if(nwsPct)rs.push([Math.round(driveMin*nwsPct/100),'Weather Service alert on the route: '+[...new Set(alerts.filter(a=>/winter|ice storm|blizzard|freezing (rain|drizzle|fog)/i.test(a.event)).map(a=>a.event))].join(', ')]);
    if(nwsMin)rs.push([10,'Weather Service alert on the route: '+[...new Set(alerts.filter(a=>/wind|fog|flood|dust|smoke/i.test(a.event)).map(a=>a.event))].join(', ')]);
    if(incMin)rs.push([incMin,`${issues.filter(z=>['closure','incident','roadwork'].includes(z.kind)&&z.add).length} road report(s) on the route that may slow you`+(issues.some(z=>z.kind==='closure')?' — one sounds like a CLOSURE':'')]);
    if(wzMin)rs.push([wzMin,`${issues.filter(z=>z.kind==='work zone'&&z.add).length} work zone(s) on the route`]);
    const total=Math.ceil((base+rs.reduce((s,r)=>s+r[0],0))/5)*5;return{reasons:[[base,'Normal cushion for a stop and everyday slowdowns'],...rs],buffer:total,points:pts}};
  let leave,E,est;
  if(mode==='arrive'){leave=tgt-R.secs*1e3-base*6e4;for(let n=0;n<2;n++){E=evaluate(leave);leave=tgt-R.secs*1e3-E.buffer*6e4}E=evaluate(leave);leave=tgt-R.secs*1e3-E.buffer*6e4;leave-=leave%3e5}
  else{leave=tgt;E=evaluate(leave)}
  est=leave+R.secs*1e3+(E.buffer-base)*6e4;
  return{mode,leave,tgt,est,miles:R.miles,driveMin,base,...E,issues,alerts,cams,src:rr.src,R};
}
// ---------- editor bits ----------
function driveLegHTML(l,i){return`<div class="leg" data-i="${i}"><b>🚗 Drive</b> <button class="x" data-del="${i}" style="float:right;padding:2px 8px">✕</button><div class="row">
   <label>From<input data-k="from" value="${esc(l.from??'Eugene, OR')}" placeholder="Eugene, OR" size="16"></label>
   <label>To<input data-k="to" value="${esc(l.to)}" placeholder="Bend, OR or a street address" size="20"></label>
   <label>I want to…<select data-k="mode"><option value="arrive"${l.mode!=='depart'?' selected':''}>arrive by</option><option value="depart"${l.mode==='depart'?' selected':''}>leave at</option></select></label>
   <label>Date &amp; time (Pacific)<input type="datetime-local" data-k="when" value="${esc(l.when)}"></label></div></div>`}
function drivesHTML(){const D=trip.legs.filter(l=>l.type==='drive'&&l.fromLoc&&l.toLoc&&l.when);return D.map((l,i)=>`<div class="panel" id="dv${i}"><h2>🚗 Drive: ${esc(l.fromLoc.name.split(',')[0])} → ${esc(l.toLoc.name)}</h2><div class="small">Planning the route, weather and road reports…</div></div>`).join('')}
const KIND_IC={closure:'⛔',incident:'🚨',roadwork:'🚧','work zone':'🚧',notice:'ℹ️'};
async function drivePanels(){
  const D=trip.legs.filter(l=>l.type==='drive'&&l.fromLoc&&l.toLoc&&l.when);
  for(const [i,l] of D.entries()){const el=$('#dv'+i);if(!el)continue;
    try{const p=await planDrive(l);l.plan=p;el.innerHTML=driveHTML(l,p,i);driveMap(p,i)}
    catch(e){console.error(e);el.innerHTML=`<h2>🚗 Drive to ${esc(l.toLoc.name)}</h2><div class="alert">⚠️ Couldn't plan this drive: ${esc(e.message)}</div>`}}
  loadWatched();
}
function driveHTML(l,p,i){
  const head=p.mode==='arrive'?`Leave by <b style="font-size:20px">${ptT(p.leave)} PT</b> on ${ptD(p.leave)} to arrive by ${ptT(p.tgt)} PT.`
    :`Leaving <b>${ptT(p.leave)} PT</b> on ${ptD(p.leave)}, plan to arrive about <b style="font-size:18px">${ptT(p.est)} PT</b>.`;
  const why=p.reasons.map(([m,t])=>`<li>${m} min — ${esc(t)}</li>`).join('');
  const past=p.mode==='arrive'&&p.leave<Date.now()?'<div class="alert">⏰ That leave time has already passed.</div>':'';
  const rr=p.issues.filter(z=>z.kind!=='notice').sort((a,b)=>a.mi-b.mi);
  const pts=p.points.map(s=>{const w=s.w;return`<tr><td style="text-align:left">${s.pass?'⛰️ ':''}${esc(s.name)}${s.ft?` <span class="small">${s.ft.toLocaleString()} ft</span>`:''}</td><td>${Math.round(s.mi)}</td><td>${ptT(s.t)}</td>
    <td>${w?`${WC[w.code]||''}`:'–'}</td><td>${w?f0(w.temp)+'°F':'–'}</td><td>${w?(w.snow>0?w.snow.toFixed(2)+'" snow':w.pr.toFixed(2)+'"'):'–'}</td><td>${w?f0(w.gust):'–'}</td><td>${w&&w.vis!=null?(w.vis/1609).toFixed(1)+' mi':'–'}</td><td>${s.kind?`<b class="warm">${s.kind}</b>`:(w?'<span class="ok">ok</span>':'')}</td></tr>`}).join('');
  const noWx=p.points.every(s=>!s.w);
  const watch={id:'d'+ptParts(p.tgt).ymd.replace(/-/g,'')+'-'+l.toLoc.name.split(',')[0].toLowerCase().replace(/[^a-z]+/g,''),from:l.fromLoc.name,from_lat:+l.fromLoc.lat.toFixed(4),from_lon:+l.fromLoc.lon.toFixed(4),
    to:l.toLoc.name,to_lat:+l.toLoc.lat.toFixed(4),to_lon:+l.toLoc.lon.toFixed(4),[p.mode==='arrive'?'arrive_by':'depart']:l.when};
  const wj=JSON.stringify(watch);
  return`<h2>🚗 Drive: ${esc(l.fromLoc.name.split(',')[0])} → ${esc(l.toLoc.name)} <span class="small">${ptD(p.tgt)}</span></h2>${past}
   <div class="sum">🕒 ${head}</div>
   <div class="row"><span class="tag">${Math.round(p.miles)} miles</span><span class="tag">Normal drive time ${fmtMin(p.driveMin)} (no traffic)</span><span class="tag">Extra time built in: ${fmtMin(p.buffer)}</span>${p.mode==='arrive'?'':`<span class="tag">Delays could add ${fmtMin(p.buffer-p.base)}</span>`}</div>
   <div class="grid"><div><h3>Why the extra time</h3><ul style="padding-left:18px;font-size:13px;margin:4px 0">${why}</ul>
     <div class="small">⚠️ No live traffic speeds here — no free, keyless source has them. Drive time is a map estimate with no traffic; rush hour is a typical-weekday allowance, not a measurement. Check <a href="https://tripcheck.com" style="color:#74c0fc" target="_blank">TripCheck</a> or a traffic app right before you go.</div></div>
    <div><div id="dmap${i}" style="height:280px;border-radius:8px;background:#1d2b3a"></div><div class="small">🔵 route · 🟢 weather points · 🔴 crash/closure · 🟠 roadwork · ▫️ cameras</div></div></div>
   <h3>Weather along the way, at the time you'd pass</h3>${noWx?'<div class="small">This trip is past the 16-day forecast — check back closer to the date.</div>':''}
   <div class="tw"><table><tr><th style="text-align:left">Place</th><th>Mile</th><th>You'd pass (PT)</th><th>Sky</th><th>Temp</th><th>Precip</th><th>Gusts mph</th><th>Visibility</th><th>Road weather</th></tr>${pts}</table></div>
   ${p.alerts.length?'<h3>Weather Service alerts on the route</h3>'+p.alerts.map(a=>`<div class="alert">⚠️ <b>${esc(a.event)}</b> near ${esc(a.near)} — ${esc(a.headline)}</div>`).join(''):'<div class="small ok" style="margin-top:6px">✓ No Weather Service alerts on the route right now.</div>'}
   <h3>Road reports on the route <span class="small">right now</span></h3>${rr.length?rr.slice(0,15).map(z=>`<div class="${['closure','incident'].includes(z.kind)?'alert':'small'}" style="margin:3px 0">${KIND_IC[z.kind]||''} <b>${esc(z.road||'')}</b> mile ${Math.round(z.mi)}: ${esc(z.text)}</div>`).join(''):'<div class="small ok">✓ No crashes, closures or roadwork reported on the route right now.</div>'}
   ${p.cams.length?`<details><summary class="small" style="cursor:pointer">📷 ${p.cams.length} road cameras on the route</summary><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">${p.cams.slice(0,24).map(c=>`<a href="${esc(c.url)}" target="_blank" class="small" style="color:#9fb3c8"><img loading="lazy" src="${esc(c.url)}" style="width:100%;border-radius:6px" alt=""><br>${esc(c.name)} · mile ${Math.round(c.mi)}</a>`).join('')}</div></details>`:''}
   <div class="panel noprint" style="background:#1d2b3a"><h3 style="margin-top:0">📡 Get leave-time and traffic updates by email</h3>
    <div class="small">Trips you type here only live in this browser, so Grok Bot can't see them. To have it watch this drive, copy the line below and send it to Grok Bot (or add it to <code>data/trips.json</code> in the repo).
    You'll get a heads-up at 7 PM PT the night before an early start, a "Leave by" email about 3 hours before you should leave, another if the leave time moves 15+ minutes, and an email if a crash, closure or road-weather alert shows up on the route while you're on the way.</div>
    <div class="row"><input readonly value="${esc(wj)}" style="flex:1;font-family:monospace;font-size:12px" id="dw${i}"><button onclick="navigator.clipboard.writeText('Please watch this drive for me: '+$('#dw${i}').value).then(()=>st('📋 Copied — send it to Grok Bot'),()=>prompt('Copy this:',$('#dw${i}').value))">📋 Copy for Grok Bot</button></div>
    <div id="watched${i}" class="small watched"></div></div>
   <div class="small">Data: route OSRM (OpenStreetMap) · weather Open-Meteo · alerts NWS · road reports ${esc(p.src.join(', ')||'none')}. Checked ${ptT(Date.now())} PT.</div>`;
}
function driveMap(p,i){
  const el=$('#dmap'+i);if(!el)return;if(!window.L){el.innerHTML='<div class="small" style="padding:8px">Map unavailable.</div>';return}
  const m=L.map(el,{scrollWheelZoom:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(m);
  const line=L.polyline(p.R.coords,{color:'#4dabf7',weight:4}).addTo(m);m.fitBounds(line.getBounds(),{padding:[12,12]});
  p.cams.forEach(c=>L.circleMarker([c.lat,c.lon],{radius:3,color:'#ced4da',weight:1,fillOpacity:.7}).bindPopup(`<a href="${esc(c.url)}" target="_blank">📷 ${esc(c.name)}</a>`).addTo(m));
  p.points.forEach(s=>L.circleMarker([s.lat,s.lon],{radius:5,color:s.kind?'#ffd43b':'#69db7c',fillOpacity:.9}).bindPopup(`<b>${esc(s.name)}</b><br>About ${ptT(s.t)} PT${s.w?`<br>${f0(s.w.temp)}°F ${s.kind||''}`:''}`).addTo(m));
  p.issues.filter(z=>z.kind!=='notice').forEach(z=>L.circleMarker([z.lat,z.lon],{radius:6,color:['closure','incident'].includes(z.kind)?'#f03e3e':'#ff922b',fillOpacity:.9}).bindPopup(`<b>${esc(z.road||'')}</b> ${esc(z.text)}`).addTo(m));
}
async function loadWatched(){
  let j=null;try{j=await cj(TRIPS_URL+'?'+Math.floor(Date.now()/3e5),5)}catch(e){}
  const now=Date.now(),T=(j&&j.trips||[]).filter(t=>{try{return ptToMs(t.arrive_by||t.depart)+8*36e5>now}catch(e){return false}});
  document.querySelectorAll('.watched').forEach(el=>el.innerHTML=j?(T.length?'👀 Grok Bot is watching: '+T.map(t=>`${esc((t.to||'').split(',')[0])} (${t.arrive_by?'arrive by':'leave at'} ${ptD(ptToMs(t.arrive_by||t.depart))} ${ptT(ptToMs(t.arrive_by||t.depart))} PT)`).join(' · '):'No drives are being watched right now.'):'');
}
