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
 ['Echo Summit (US 50)',38.8126,-120.0303,7382],['Chemult / US 97 high desert',43.22,-121.78,4760],
 ['Bozeman Pass (I-90)',45.6617,-110.8069,5702],['Homestake Pass (I-90)',45.9203,-112.4136,6329],['Lookout Pass (I-90)',47.4566,-115.6966,4710],
 ['Fourth of July Pass (I-90)',47.6247,-116.5197,3081],['MacDonald Pass (US 12)',46.5603,-112.3103,6320],['Lolo Pass (US 12)',46.6347,-114.5797,5233],
 ['Blue Mountains / Emigrant Hill (I-84)',45.47,-118.43,4193],['Ladd Canyon (I-84)',45.17,-117.98,3800],['Sherman Summit (I-80 WY)',41.14,-105.38,8640],
 ['Vail Pass (I-70)',39.53,-106.22,10662],['Eisenhower Tunnel (I-70)',39.68,-105.92,11158]];
// name, lat, lon, radius mi, extra min at weekday rush (local time of that city)
const METROS=[['Portland',45.52,-122.68,15,25],['Seattle',47.61,-122.33,15,30],['Tacoma',47.25,-122.44,8,15],['Salem',44.94,-123.03,6,5],['Eugene-Springfield',44.05,-123.05,6,5],
 ['Sacramento',38.58,-121.49,12,20],['San Francisco Bay Area',37.77,-122.27,25,35],['Boise',43.61,-116.2,8,10],['Bend',44.06,-121.31,4,5],
 ['Spokane',47.66,-117.42,8,10],['Billings',45.78,-108.5,6,5],['Fargo-Moorhead',46.88,-96.79,6,5],['Minneapolis-St Paul',44.97,-93.2,18,30],
 ['Madison',43.07,-89.4,8,10],['Milwaukee',43.04,-87.93,10,15],['Chicago',41.88,-87.66,22,40],['Denver',39.74,-104.99,15,25]];
const RUSH=[[6.5,9.5],[15,18.5]];
// Which states our road-report relay covers, and with what (honest list for the page)
const FEEDS={OR:'crashes, closures, roadwork and cameras (TripCheck)',CA:'CHP incidents and cameras (no work zones)'};
'UT IA FL MN MD AZ MO WI NM HI NY KY NJ KS TX ID NC ND WA DE LA IN MS'.split(' ').forEach(s=>FEEDS[s]='planned roadwork only — no crash or closure reports');
const CAMSRC={WA:'cameras (WSDOT)',IL:'cameras (IDOT Gateway / Travel Midwest, CC BY-SA 2.0)',ND:'cameras (NDDOT travel info, provided as-is with no warranty)',WI:'cameras (511WI)',ID:'cameras (511 Idaho)'};
const NOEMBED=new Set(['IL']);// Travel Midwest refuses pictures embedded on other sites, so IL cameras are links
const CAMNOTE={IL:'Illinois camera images: IDOT Gateway / Travel Midwest, licensed CC BY-SA 2.0; their server does not allow showing them inside other sites, so tap to open each one.',ND:'North Dakota camera images come from NDDOT travel info and are provided as-is, with no warranty or liability; check conditions yourself.'};
const S511={OR:'https://tripcheck.com',WA:'https://wsdot.com/travel/real-time/map',ID:'https://511.idaho.gov',MT:'https://www.511mt.net',ND:'https://travel.dot.nd.gov',
 MN:'https://511mn.org',WI:'https://511wi.gov',IL:'https://www.gettingaroundillinois.com',SD:'https://sd511.org',WY:'https://www.wyoroad.info',IA:'https://511ia.org',
 IN:'https://511in.org',CA:'https://quickmap.dot.ca.gov',NV:'https://www.nvroads.com',UT:'https://udottraffic.utah.gov',CO:'https://www.cotrip.org'};
const STATE_AB={Alabama:'AL',Alaska:'AK',Arizona:'AZ',Arkansas:'AR',California:'CA',Colorado:'CO',Connecticut:'CT',Delaware:'DE',Florida:'FL',Georgia:'GA',Hawaii:'HI',Idaho:'ID',Illinois:'IL',
 Indiana:'IN',Iowa:'IA',Kansas:'KS',Kentucky:'KY',Louisiana:'LA',Maine:'ME',Maryland:'MD',Massachusetts:'MA',Michigan:'MI',Minnesota:'MN',Mississippi:'MS',Missouri:'MO',Montana:'MT',
 Nebraska:'NE',Nevada:'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND',Ohio:'OH',Oklahoma:'OK',Oregon:'OR',
 Pennsylvania:'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD',Tennessee:'TN',Texas:'TX',Utah:'UT',Vermont:'VT',Virginia:'VA',Washington:'WA','West Virginia':'WV',
 Wisconsin:'WI',Wyoming:'WY','District of Columbia':'DC'};
const TZ='America/Los_Angeles';     // default zone (Steven's home) when a place's zone isn't known yet
const DAY_MAX=600,DAY_AIM=540;      // over ~10 h of map driving → suggest overnight stops, aiming for ~9 h a day
const mi2=(a,b)=>dist({lat:a[0],lon:a[1]},{lat:b[0],lon:b[1]});
// wall-clock "2026-10-30T07:00" in a given zone <-> epoch ms, regardless of the browser's own time zone
function tzOff(ms,tz=TZ){const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:tz,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).formatToParts(ms).map(x=>[x.type,x.value]));
  return Date.UTC(+p.year,p.month-1,+p.day,+p.hour%24,+p.minute,+p.second)-ms}
function tzToMs(s,tz=TZ){const g=Date.parse(s.length===16?s+':00Z':s+'Z');let t=g-tzOff(g,tz);return g-tzOff(t,tz)}
const ptOff=ms=>tzOff(ms),ptToMs=s=>tzToMs(s);
// short zone label: CDT/CST → CT, MDT → MT, PDT → PT
const zab=(ms,tz=TZ)=>{const n=(new Intl.DateTimeFormat('en-US',{timeZone:tz,timeZoneName:'short'}).formatToParts(ms).find(x=>x.type==='timeZoneName')||{}).value||'';return n.replace(/^(AK|H|[ECMPA])[SD]T$/,'$1T')};
const ptT=(ms,tz=TZ)=>new Date(ms).toLocaleTimeString('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit'});
const ptD=(ms,tz=TZ)=>new Date(ms).toLocaleDateString('en-US',{timeZone:tz,weekday:'short',month:'short',day:'numeric'});
const tT=(ms,tz=TZ)=>ptT(ms,tz)+' '+zab(ms,tz);                       // "7:00 AM CT"
const tDT=(ms,tz=TZ)=>`${ptD(ms,tz).split(',')[0]} ${tT(ms,tz)}`;      // "Fri 7:00 AM CT"
const ptParts=(ms,tz=TZ)=>{const o=tzOff(ms,tz),d=new Date(ms+o);return{h:d.getUTCHours()+d.getUTCMinutes()/60,wd:d.getUTCDay(),ymd:d.toISOString().slice(0,10)}};
const fmtMin=m=>{m=Math.round(m);return m>=60?`${Math.floor(m/60)} h ${String(m%60).padStart(2,'0')} min`:`${m} min`};
function classify(t){
  if(/\bclos(ed|ure|ing)\b|blocked|impassable/i.test(t)&&!/shoulder clos|lane clos/i.test(t))return['closure',30];
  if(/no (traffic )?impacts?|no delay/i.test(t))return['notice',0];
  if(/construction|work(ers| zone| is being done)|paving|striping|signage|maintenance|lane clos|shoulder/i.test(t))return['roadwork',3];
  if(/minimal delay|use caution|fire in the area/i.test(t))return['notice',0];
  return['incident',10];
}
// Route from OSRM, thinned to a point every ~0.15 mi so long drives stay small in the browser cache
async function route(a,b){
  const u=`https://router.project-osrm.org/route/v1/driving/${a.lon.toFixed(5)},${a.lat.toFixed(5)};${b.lon.toFixed(5)},${b.lat.toFixed(5)}?overview=full&geometries=geojson&annotations=duration`,key='rt:'+u;
  try{const c=JSON.parse(localStorage.getItem(key)||'null');if(c&&Date.now()-c.t<360*6e4)return c.d}catch(e){}
  const res=await fetch(u);if(!res.ok)throw new Error('Route service error '+res.status+' — try again in a minute.');const j=await res.json();
  if(!j.routes||!j.routes[0])throw new Error('No driving route found between those places.');
  const r=j.routes[0],c=r.geometry.coordinates.map(([x,y])=>[y,x]),ann=r.legs[0].annotation.duration,tot=ann.reduce((s,x)=>s+x,0)||1,k=r.duration/tot;
  const ct=[0];ann.forEach(d=>ct.push(ct[ct.length-1]+d*k));
  const C=[c[0]],T=[0],M=[0];let cum=0,last=0;
  for(let i=1;i<c.length;i++){cum+=mi2(c[i-1],c[i]);if(cum-last>=.15||i===c.length-1){C.push([+c[i][0].toFixed(5),+c[i][1].toFixed(5)]);T.push(Math.round(ct[Math.min(i,ct.length-1)]));M.push(+cum.toFixed(3));last=cum}}
  const d={miles:r.distance/1609.344,secs:r.duration,coords:C,ct:T,cm:M};
  try{localStorage.setItem(key,JSON.stringify({t:Date.now(),d}))}catch(e){pruneCache();try{localStorage.setItem(key,JSON.stringify({t:Date.now(),d}))}catch(e2){}}
  return d;
}
function near(R,p,maxmi){let best=[1e9,0];const dl=maxmi/69+0.02;if(!R.bb){R.bb=[90,-90,180,-180];R.coords.forEach(([a,o])=>{R.bb=[Math.min(R.bb[0],a),Math.max(R.bb[1],a),Math.min(R.bb[2],o),Math.max(R.bb[3],o)]})}
  if(p[0]<R.bb[0]-dl||p[0]>R.bb[1]+dl||p[1]<R.bb[2]-dl*1.5||p[1]>R.bb[3]+dl*1.5)return best;
  R.coords.forEach((q,i)=>{if(Math.abs(q[0]-p[0])>dl||Math.abs(q[1]-p[1])>dl*1.5)return;const d=mi2(p,q);if(d<best[0])best=[d,i]});return best}
async function pool(items,n,fn){const out=[];let k=0;await Promise.all(Array.from({length:Math.min(n,items.length)},async()=>{while(k<items.length){const i=k++;try{out[i]=await fn(items[i])}catch(e){out[i]=null}}}));return out}
const townQ=(la,lo,rad=20,big=false)=>`https://photon.komoot.io/reverse?lat=${la.toFixed(3)}&lon=${lo.toFixed(3)}&lang=en&limit=4&radius=${rad}&osm_tag=place:city&osm_tag=place:town`+(big?'':'&osm_tag=place:village&osm_tag=place:hamlet');
const JUNK=/mobile|trailer|estates|manor|subdivision|village of|(rv|home) park|apartments/i;
const townName=j=>{const p=(j.features||[]).map(f=>f.properties).find(p=>p&&p.name&&!JUNK.test(p.name));return p?`${p.name}${p.state?', '+(STATE_AB[p.state]||p.state):''}`:null};
async function samplePts(R){
  const out=[],step=Math.max(15,R.miles/24);let nx=0;
  R.cm.forEach((m,i)=>{if(m>=nx||i===R.coords.length-1){out.push({i,name:`${Math.round(m)} mi along`,lat:R.coords[i][0],lon:R.coords[i][1]});nx=m+step}});
  await pool(out,6,async s=>{const j=await cj(townQ(s.lat,s.lon),1e5);const n=townName(j);if(n)s.name=n});
  PASSES.forEach(([n,la,lo,ft])=>{const[d,i]=near(R,[la,lo],3);if(d<=3)out.push({i,name:n,lat:la,lon:lo,pass:true,ft})});
  out.sort((a,b)=>a.i-b.i);out.forEach(s=>{s.toff=R.ct[s.i];s.mi=R.cm[s.i]});return out;
}
// States the route actually crosses: ask Photon which state each spot is in, every ~30 miles
async function statesOn(R){const P=[];let nx=0;R.cm.forEach((m,i)=>{if(m>=nx||i===R.coords.length-1){P.push(R.coords[i]);nx=m+30}});
  const r=await pool(P,6,async([la,lo])=>{const j=await cj(`https://photon.komoot.io/reverse?lat=${la.toFixed(2)}&lon=${lo.toFixed(2)}&lang=en&limit=1`,1e5);const p=j.features[0]?.properties;return p&&p.countrycode==='US'&&STATE_AB[p.state]});
  const seen=[];r.forEach(s=>{if(s&&!seen.includes(s))seen.push(s)});return seen}
async function routeWx(S){const out=[];
  for(let k=0;k<S.length;k+=40){const B=S.slice(k,k+40);
    const j=await cj(`https://api.open-meteo.com/v1/forecast?latitude=${B.map(s=>s.lat.toFixed(3))}&longitude=${B.map(s=>s.lon.toFixed(3))}&hourly=temperature_2m,precipitation,snowfall,weather_code,visibility,wind_gusts_10m&timeformat=unixtime&timezone=auto&forecast_days=16&temperature_unit=fahrenheit&precipitation_unit=inch&wind_speed_unit=mph`,60,{om:true});
    out.push(...(Array.isArray(j)?j:[j]))}
  return out}
function wxAt(W,ts){const h=W.hourly,t=h.time;if(!t.length||ts<t[0]-3600||ts>t[t.length-1]+3600)return null;let i=0,bd=1e18;t.forEach((x,k)=>{const d=Math.abs(x-ts);if(d<bd){bd=d;i=k}});
  const g=k=>(h[k]||[])[i];return{temp:g('temperature_2m'),pr:g('precipitation')||0,snow:g('snowfall')||0,code:g('weather_code'),vis:g('visibility'),gust:g('wind_gusts_10m')}}
function wxKind(w){if(!w)return null;const c=w.code||0;
  if(w.snow>=0.01||[71,73,75,77,85,86].includes(c))return'snow';
  if([56,57,66,67].includes(c)||(w.temp!=null&&w.temp<=34&&w.pr>=0.01))return'ice';
  if([65,82].includes(c)||w.pr>=0.2)return'heavy rain';
  if([61,63,80,81,51,53,55].includes(c)||w.pr>=0.02)return'rain';return null}
async function routeAlerts(S){const seen={};const P=S.filter((s,k)=>s.pass||k%2===0||k===S.length-1).slice(0,18);
  await pool(P,6,async p=>{const j=await cj(`https://api.weather.gov/alerts/active?point=${p.lat.toFixed(3)},${p.lon.toFixed(3)}`,10);
    j.features.forEach(f=>{const a=f.properties;if(a.status!=='Actual'||a.messageType==='Cancel')return;const k=(a.event||'')+'|'+(a.areaDesc||'').slice(0,40);
      if(!seen[k])seen[k]={event:a.event,headline:a.headline||a.event,near:p.name,url:'https://api.weather.gov/alerts/'+a.id}})});
  return Object.values(seen)}
async function roadReports(states){const out={inc:[],wz:[],cam:[],src:[],cov:[],camBy:{}};
  await Promise.all(states.map(async s=>{
    // Ask the relay and the 10-min backup copy together and merge them: the relay may only have roadwork for a state while the backup copy also has its cameras.
    const got=(await Promise.all([[RELAY+'/traffic/'+s+'.json','relay'],[LIVE+s+'.json','backup copy']].map(([u,l])=>cj(u,2).then(d=>({d,l}),()=>null)))).filter(z=>z&&z.d);
    const n=z=>(z.d.inc||[]).length+(z.d.wz||[]).length,rep=got.find(z=>n(z))||null,seen=new Set(),cams=[],used=new Set();
    if(rep){out.inc.push(...(rep.d.inc||[]));out.wz.push(...(rep.d.wz||[]));used.add(rep)}
    got.forEach(z=>(z.d.cam||[]).forEach(c=>{if(!seen.has(c[3])){seen.add(c[3]);cams.push([...c,s]);used.add(z)}}));out.cam.push(...cams);
    used.forEach(z=>out.src.push(`${s} (${z.l}, ${(z.d.built||'').slice(0,16).replace('T',' ')} UTC)`));
    const has=!!(rep||cams.length),what=has?[rep?(FEEDS[s]||'road reports'):'',cams.length&&!/camera/.test(rep?FEEDS[s]||'':'')?(CAMSRC[s]||'cameras'):''].filter(Boolean).join(' + '):(FEEDS[s]?'feed unavailable right now':'no free road-report feed');
    out.cov.push({st:s,ok:has,what,url:S511[s],nCam:cams.length})}));
  out.cov.sort((a,b)=>states.indexOf(a.st)-states.indexOf(b.st));return out}
// Driving schedule. One day: leave + map time. Longer than ~10 h: split into even days of ≤ ~9 h, overnight near a town,
// and start each next day at the same local clock time as the first morning (in the stop's own time zone).
function makeDays(R,S){const driveMin=R.secs/60;if(driveMin<=DAY_MAX)return[{t0:0,t1:R.secs}];
  const n=Math.ceil(driveMin/DAY_AIM),D=[];for(let k=0;k<n;k++)D.push({t0:R.secs*k/n,t1:R.secs*(k+1)/n});
  D.forEach((d,k)=>{if(k===n-1)return;let i=R.ct.findIndex(t=>t>=d.t1);if(i<0)i=R.ct.length-1;d.stopI=i;d.stopMi=R.cm[i];
    let best=S[0],bd=1e9;S.forEach(s=>{const x=Math.abs(s.i-i);if(x<bd){bd=x;best=s}});d.tz=best.tz||TZ});return D}
// name each overnight stop after a real town (city/town first) and use that spot's own time zone
async function nameStops(R,D){const X=D.filter(d=>d.stopI!=null);if(!X.length)return;
  // walk outward along the route (0, ±6, ±12 … ±42 mi) and take the first real town right on it
  await pool(X,2,async d=>{let n=null;for(const off of[0,-6,6,-12,12,-18,18,-24,24,-30,30,-36,36,-42,42]){const m=d.stopMi+off;let i=R.cm.findIndex(x=>x>=m);if(i<0)continue;
      try{n=townName(await cj(townQ(R.coords[i][0],R.coords[i][1],6,true),1e5))}catch(e){}if(n){d.stopI=i;d.stopMi=R.cm[i];break}}
    if(!n){const[la,lo]=R.coords[d.stopI];try{n=townName(await cj(townQ(la,lo,30,true),1e5))}catch(e){}}d.stop=n||`mile ${Math.round(d.stopMi)}`;d.t1s=R.ct[d.stopI]});
  // split the days at the chosen towns
  D.forEach((d,k)=>{if(d.t1s!=null){d.t1=d.t1s;if(D[k+1])D[k+1].t0=d.t1s}});
  try{const j=await cj(`https://api.open-meteo.com/v1/forecast?latitude=${X.map(d=>R.coords[d.stopI][0].toFixed(3))}&longitude=${X.map(d=>R.coords[d.stopI][1].toFixed(3))}&hourly=temperature_2m&forecast_days=1&timezone=auto`,1e4,{om:true});
    (Array.isArray(j)?j:[j]).forEach((w,k)=>{if(w&&w.timezone&&w.timezone!=='GMT')X[k].tz=w.timezone})}catch(e){}}
function schedule(D,mode,tgt,frac,tzA,tzB){const f=1+frac,n=D.length,st=new Array(n);
  if(n===1){return null}
  if(mode==='depart'){st[0]=tgt;const hm=ptParts(tgt,tzA).h;for(let k=1;k<n;k++){const end=st[k-1]+(D[k-1].t1-D[k-1].t0)*f*1e3,tz=D[k-1].tz;
      let ymd=ptParts(end,tz).ymd;const nd=new Date(Date.parse(ymd+'T00:00:00Z')+864e5).toISOString().slice(0,10);st[k]=tzToMs(`${nd}T${String(Math.floor(hm)).padStart(2,'0')}:${String(Math.round(hm%1*60)).padStart(2,'0')}`,tz)}}
  else{st[n-1]=tgt-(D[n-1].t1-D[n-1].t0)*f*1e3;const hm=ptParts(st[n-1],D[n-2].tz).h;for(let k=n-2;k>=0;k--){const nx=st[k+1],tz=D[k].tz;
      const pd=new Date(Date.parse(ptParts(nx,tz).ymd+'T00:00:00Z')-864e5).toISOString().slice(0,10);let s0=tzToMs(`${pd}T${String(Math.floor(hm)).padStart(2,'0')}:${String(Math.round(hm%1*60)).padStart(2,'0')}`,k===0?tzA:D[k-1].tz);
      const need=(D[k].t1-D[k].t0)*f*1e3;if(s0+need>nx-8*36e5)s0=nx-8*36e5-need;st[k]=s0}
    st[0]-=st[0]%3e5}
  const at=t=>{let k=D.findIndex(d=>t<=d.t1);if(k<0)k=n-1;return st[k]+(t-D[k].t0)*f*1e3};
  return{starts:st,at,end:st[n-1]+(D[n-1].t1-D[n-1].t0)*f*1e3}}
async function planDrive(l){
  const a=l.fromLoc,b=l.toLoc,R=await route(a,b),[S,states]=await Promise.all([samplePts(R),statesOn(R).catch(()=>[])]);
  const [W,rr,alerts]=await Promise.all([routeWx(S),roadReports(states),routeAlerts(S)]);
  S.forEach((s,k)=>s.tz=(W[k]&&W[k].timezone&&W[k].timezone!=='GMT')?W[k].timezone:TZ);
  const tzA=S[0].tz,tzB=S[S.length-1].tz;
  const driveMin=R.secs/60,base=Math.max(10,Math.round(driveMin*.05)),mode=l.mode==='depart'?'depart':'arrive';
  const tzIn=mode==='depart'?tzA:tzB,tgt=tzToMs(l.when,tzIn),day=ptParts(tgt,tzIn).ymd;
  const D=makeDays(R,S);
  await nameStops(R,D);
  const issues=[];let incMin=0,wzMin=0;
  rr.inc.forEach(x=>{const[d,i]=near(R,[x[0],x[1]],.5);if(d>.5)return;const k='i'+x[2]+'|'+String(x[3]).slice(0,80);if(issues.some(z=>z.key===k))return;const[kd,add]=classify(`${x[2]} ${x[3]}`);incMin+=add;issues.push({key:k,kind:kd,road:x[2],text:x[3],mi:R.cm[i],lat:x[0],lon:x[1],add})});
  const lastDay=D.length>1?new Date(tgt+D.length*864e5).toISOString().slice(0,10):day;
  rr.wz.forEach(x=>{if(x.length>5&&((x[4]&&x[4]>lastDay)||(x[5]&&x[5]<day)))return;const[d,i]=near(R,[x[0],x[1]],.3);if(d>.3)return;const k='w'+x[2]+'|'+String(x[3]).slice(0,60);if(issues.some(z=>z.key===k))return;
    const add=/no (traffic )?impact|no delay/i.test(x[3])?0:3;wzMin+=add;issues.push({key:k,kind:'work zone',road:x[2],text:x[3],mi:R.cm[i],lat:x[0],lon:x[1],add})});
  incMin=Math.min(incMin,60);wzMin=Math.min(wzMin,D.length>1?30:15);
  // Cameras: within ~1.5 mi of the route, then only the nearest few per 50-mile stretch so long drives get an even spread instead of one city's worth.
  const SEG=50,PER=R.miles<200?3:2,bins={};
  rr.cam.forEach(x=>{const[d,i]=near(R,[x[0],x[1]],1.5);if(d>1.5)return;const b=Math.floor(R.cm[i]/SEG);(bins[b]=bins[b]||[]).push({name:x[2],url:x[3],mi:R.cm[i],lat:x[0],lon:x[1],st:x[4],d})});
  const cams=Object.values(bins).flatMap(a=>a.sort((p,q)=>p.d-q.d).slice(0,PER)).sort((a,b)=>a.mi-b.mi);
  rr.cov.forEach(c=>c.onRoute=cams.filter(z=>z.st===c.st).length);
  let nwsPct=0,nwsMin=0;alerts.forEach(a=>{const e=(a.event||'').toLowerCase();if(/winter storm warning|ice storm|blizzard/.test(e))nwsPct=Math.max(nwsPct,30);else if(/winter weather advisory|winter storm watch|freezing (rain|drizzle|fog)/.test(e))nwsPct=Math.max(nwsPct,15);else if(/high wind|dense fog|flood|dust|smoke/.test(e))nwsMin=10});
  const tzNear=i=>{let best=S[0],bd=1e9;S.forEach(s=>{const x=Math.abs(s.i-i);if(x<bd){bd=x;best=s}});return best.tz||TZ};
  const evaluate=at=>{const rs=[],wx=[];let worst=0,fog=false,gust=false,icy=false;const pts=[];
    S.forEach((s,k)=>{const ms=at(s.toff),ts=ms/1000,x=wxAt(W[k],ts),kd=wxKind(x);pts.push({...s,t:ms,w:x,kind:kd});if(!x)return;
      const pct={snow:25,ice:25,'heavy rain':10,rain:5}[kd]||0;if(pct>worst)worst=pct;if(kd)wx.push([kd,s.name,ms,s.tz]);
      if(x.vis!=null&&x.vis<800)fog=s.name;if((x.gust||0)>=45)gust=s.name;if(s.pass&&x.temp!=null&&x.temp<=32&&!kd)icy=s.name});
    if(worst){const rk={snow:4,ice:4,'heavy rain':2,rain:1},k0=wx.reduce((m,z)=>rk[z[0]]>rk[m[0]]?z:m),pl=[...new Set(wx.filter(z=>z[0]===k0[0]).map(z=>z[1]))].sort().slice(0,3);
      rs.push([worst<25?Math.round(driveMin*worst/100):Math.max(15,Math.round(driveMin*worst/100)),`${k0[0][0].toUpperCase()+k0[0].slice(1)} in the forecast near ${pl.join(', ')} around ${D.length>1?tDT(k0[2],k0[3]):tT(k0[2],k0[3])}`+(['snow','ice'].includes(k0[0])?' — carry chains and check the state road report before the passes':'')])}
    if(fog)rs.push([10,`Fog (under half a mile visibility) near ${fog}`]);if(gust)rs.push([10,`Strong wind gusts (45+ mph) near ${gust}`]);if(icy)rs.push([5,`Below freezing at ${icy} — watch for icy patches`]);
    METROS.forEach(([n,la,lo,rad,ex])=>{const[d,i]=near(R,[la,lo],rad);if(d>rad)return;const t=at(R.ct[i]),tz=tzNear(i),p=ptParts(t,tz);if(p.wd>=1&&p.wd<=5&&RUSH.some(([a,b])=>p.h>=a&&p.h<=b))rs.push([ex,`Usual weekday rush hour in ${n} (you'd be there about ${D.length>1?tDT(t,tz):tT(t,tz)})`])});
    if(nwsPct)rs.push([Math.round(driveMin*nwsPct/100),'Weather Service alert on the route: '+[...new Set(alerts.filter(a=>/winter|ice storm|blizzard|freezing (rain|drizzle|fog)/i.test(a.event)).map(a=>a.event))].join(', ')]);
    if(nwsMin)rs.push([10,'Weather Service alert on the route: '+[...new Set(alerts.filter(a=>/wind|fog|flood|dust|smoke/i.test(a.event)).map(a=>a.event))].join(', ')]);
    if(incMin)rs.push([incMin,`${issues.filter(z=>['closure','incident','roadwork'].includes(z.kind)&&z.add).length} road report(s) on the route that may slow you`+(issues.some(z=>z.kind==='closure')?' — one sounds like a CLOSURE':'')]);
    if(wzMin)rs.push([wzMin,`${issues.filter(z=>z.kind==='work zone'&&z.add).length} work zone(s) on the route`]);
    const total=Math.ceil((base+rs.reduce((s,r)=>s+r[0],0))/5)*5;return{reasons:[[base,D.length>1?'Normal cushion for gas, food and rest stops and everyday slowdowns':'Normal cushion for a stop and everyday slowdowns'],...rs],buffer:total,points:pts}};
  let leave,E,est,SC=null;
  if(D.length===1){const at0=lv=>t=>lv+t*1e3;
    if(mode==='arrive'){leave=tgt-R.secs*1e3-base*6e4;for(let n=0;n<2;n++){E=evaluate(at0(leave));leave=tgt-R.secs*1e3-E.buffer*6e4}E=evaluate(at0(leave));leave=tgt-R.secs*1e3-E.buffer*6e4;leave-=leave%3e5}
    else{leave=tgt;E=evaluate(at0(leave))}
    est=leave+R.secs*1e3+(E.buffer-base)*6e4}
  else{let frac=base/driveMin;for(let n=0;n<3;n++){SC=schedule(D,mode,tgt,frac,tzA,tzB);E=evaluate(SC.at);frac=E.buffer/driveMin}
    SC=schedule(D,mode,tgt,frac,tzA,tzB);leave=SC.starts[0];est=SC.end;
    D.forEach((d,k)=>{d.start=SC.starts[k];d.end=SC.starts[k]+(d.t1-d.t0)*(1+frac)*1e3;d.tzStart=k===0?tzA:D[k-1].tz;d.tzEnd=k===D.length-1?tzB:d.tz;d.driveMin=(d.t1-d.t0)/60;
      d.from=k===0?a.name.split(',').slice(0,2).join(','):D[k-1].stop;d.to=k===D.length-1?b.name.split(',').slice(0,2).join(','):d.stop})}
  let oneDay=null;if(D.length===2&&mode==='depart'&&driveMin<=14*60)oneDay=leave+(R.secs*(1+E.buffer/driveMin))*1e3;
  return{mode,leave,tgt,est,oneDay,miles:R.miles,driveMin,base,...E,issues,alerts,cams,src:rr.src,cov:rr.cov,R,days:D,tzA,tzB,states};
}
// ---------- editor bits ----------
function driveLegHTML(l,i){return`<div class="leg" data-i="${i}"><b>🚗 Drive</b> <button class="x" data-del="${i}" style="float:right;padding:2px 8px">✕</button><div class="row">
   <label>From<input data-k="from" value="${esc(l.from??'Eugene, OR')}" placeholder="Eugene, OR" size="16"></label>
   <label>To<input data-k="to" value="${esc(l.to)}" placeholder="Bend, OR or a street address" size="20"></label>
   <label>I want to…<select data-k="mode"><option value="arrive"${l.mode!=='depart'?' selected':''}>arrive by</option><option value="depart"${l.mode==='depart'?' selected':''}>leave at</option></select></label>
   <label title="Leave at: local time where you start. Arrive by: local time at the destination.">Date &amp; time (local)<input type="datetime-local" data-k="when" value="${esc(l.when)}"></label></div></div>`}
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
  const A=p.tzA,B=p.tzB,multi=p.days.length>1;
  const head=p.mode==='arrive'?`Leave by <b style="font-size:20px">${tT(p.leave,A)}</b> on ${ptD(p.leave,A)} to arrive by ${tT(p.tgt,B)}${multi?' on '+ptD(p.tgt,B):''}.`
    :`Leaving <b>${tT(p.leave,A)}</b> on ${ptD(p.leave,A)}, plan to arrive about <b style="font-size:18px">${tT(p.est,B)}</b>${multi||ptD(p.est,B)!==ptD(p.leave,A)?' on '+ptD(p.est,B):''}.`;
  const zones=[...new Set(p.points.map(s=>zab(s.t,s.tz)))];
  const dayHTML=multi?`<h3>🛏️ Suggested overnight stops <span class="small">(${p.days.length} days, about ${fmtMin(p.driveMin/p.days.length)} of driving each)</span></h3><ol style="padding-left:20px;font-size:13px;margin:4px 0">${p.days.map((d,k)=>`<li><b>${ptD(d.start,d.tzStart)}</b>: leave ${esc(d.from)} ${tT(d.start,d.tzStart)} → ${k===p.days.length-1?'arrive':'stay overnight near <b>'+esc(d.to)+'</b>, about'} ${tT(d.end,d.tzEnd)} · ${Math.round((k===p.days.length-1?p.miles:d.stopMi)-(k?p.days[k-1].stopMi:0))} mi, ${fmtMin(d.driveMin)} driving</li>`).join('')}</ol>
     <div class="small">Over about 10 hours of driving is a lot for one day, so the drive is split into even days. Each morning starts at the same local clock time as the first. Any town near the stop works; book a room ahead in winter.${p.oneDay?` If you'd rather push through in one long day, you'd get in about <b>${tDT(p.oneDay,B)}</b> (${fmtMin(p.driveMin+p.buffer)} with stops) — only with two drivers or plenty of rest.`:''}</div>`
    :(p.driveMin>480?'<div class="small warm">Long day: plan a real break every 2 hours or so.</div>':'');
  const cov=p.cov.length?`<h3>Which states have road reports</h3><ul style="padding-left:18px;font-size:13px;margin:4px 0">${p.cov.map(c=>`<li>${c.ok?'✅':'⚠️'} <b>${c.st}</b>: ${esc(c.what)}${c.nCam?` · ${c.onRoute||0} camera${c.onRoute===1?'':'s'} shown on this route`:''}${c.url?` — <a href="${c.url}" target="_blank" style="color:#74c0fc">${c.st} 511</a>`:''}</li>`).join('')}</ul>${p.cov.some(c=>!c.ok||/roadwork only/.test(c.what))?'<div class="small">Where it says roadwork only or no feed, crashes and closures there will NOT show here. Check that state\'s 511 link before you drive that part.</div>':''}`:'';
  const why=p.reasons.map(([m,t])=>`<li>${m} min — ${esc(t)}</li>`).join('');
  const past=p.leave<Date.now()?'<div class="alert">⏰ That leave time has already passed.</div>':'';
  const rr=p.issues.filter(z=>z.kind!=='notice').sort((a,b)=>a.mi-b.mi);
  const pts=p.points.map(s=>{const w=s.w;return`<tr><td style="text-align:left">${s.pass?'⛰️ ':''}${esc(s.name)}${s.ft?` <span class="small">${s.ft.toLocaleString()} ft</span>`:''}</td><td>${Math.round(s.mi)}</td><td>${multi?tDT(s.t,s.tz):tT(s.t,s.tz)}</td>
    <td>${w?`${WC[w.code]||''}`:'–'}</td><td>${w?f0(w.temp)+'°F':'–'}</td><td>${w?(w.snow>0?w.snow.toFixed(2)+'" snow':w.pr.toFixed(2)+'"'):'–'}</td><td>${w?f0(w.gust):'–'}</td><td>${w&&w.vis!=null?(w.vis/1609).toFixed(1)+' mi':'–'}</td><td>${s.kind?`<b class="warm">${s.kind}</b>`:(w?'<span class="ok">ok</span>':'')}</td></tr>`}).join('');
  const noWx=p.points.every(s=>!s.w);
  const watch={id:'d'+ptParts(p.tgt,p.mode==='arrive'?B:A).ymd.replace(/-/g,'')+'-'+l.toLoc.name.split(',')[0].toLowerCase().replace(/[^a-z]+/g,''),from:l.fromLoc.name,from_lat:+l.fromLoc.lat.toFixed(4),from_lon:+l.fromLoc.lon.toFixed(4),
    to:l.toLoc.name,to_lat:+l.toLoc.lat.toFixed(4),to_lon:+l.toLoc.lon.toFixed(4),[p.mode==='arrive'?'arrive_by':'depart']:l.when,...((p.mode==='arrive'?B:A)!==TZ?{tz:p.mode==='arrive'?B:A}:{}),...(multi?{long:true}:{})};
  const wj=JSON.stringify(watch);
  return`<h2>🚗 Drive: ${esc(l.fromLoc.name.split(',')[0])} → ${esc(l.toLoc.name)} <span class="small">${ptD(p.leave,A)}</span></h2>${past}
   <div class="sum">🕒 ${head}</div>
   <div class="row"><span class="tag">${Math.round(p.miles)} miles</span><span class="tag">${multi?'Total driving':'Normal drive time'} ${fmtMin(p.driveMin)} (no traffic)</span>${multi?`<span class="tag">${p.days.length} days</span>`:''}${zones.length>1?`<span class="tag">Time zones: ${zones.join(' → ')}</span>`:''}<span class="tag">Extra time built in: ${fmtMin(p.buffer)}</span>${p.mode==='arrive'?'':`<span class="tag">Delays could add ${fmtMin(p.buffer-p.base)}</span>`}</div>
   <div class="grid"><div><h3>Why the extra time</h3><ul style="padding-left:18px;font-size:13px;margin:4px 0">${why}</ul>
     <div class="small">⚠️ No live traffic speeds here — no free, keyless source has them. Drive time is a map estimate with no traffic (on long interstate drives it often runs a bit long); rush hour is a typical-weekday allowance, not a measurement. Check the state 511 links below or a traffic app right before you go.</div></div>
    <div><div id="dmap${i}" style="height:280px;border-radius:8px;background:#1d2b3a"></div><div class="small">🔵 route · 🟢 weather points · 🔴 crash/closure · 🟠 roadwork · ▫️ cameras</div></div></div>
   ${dayHTML}
   <h3>Weather along the way, at the time you'd pass</h3>${noWx?'<div class="small">This trip is past the 16-day forecast — check back closer to the date.</div>':''}
   <div class="tw"><table><tr><th style="text-align:left">Place</th><th>Mile</th><th>You'd pass (local time)</th><th>Sky</th><th>Temp</th><th>Precip</th><th>Gusts mph</th><th>Visibility</th><th>Road weather</th></tr>${pts}</table></div>
   ${p.alerts.length?'<h3>Weather Service alerts on the route</h3>'+p.alerts.map(a=>`<div class="alert">⚠️ <b>${esc(a.event)}</b> near ${esc(a.near)} — ${esc(a.headline)}</div>`).join(''):'<div class="small ok" style="margin-top:6px">✓ No Weather Service alerts on the route right now.</div>'}
   <h3>Road reports on the route <span class="small">right now</span></h3>${rr.length?rr.slice(0,15).map(z=>`<div class="${['closure','incident'].includes(z.kind)?'alert':'small'}" style="margin:3px 0">${KIND_IC[z.kind]||''} <b>${esc(z.road||'')}</b> mile ${Math.round(z.mi)}: ${esc(z.text)}</div>`).join(''):'<div class="small ok">✓ No crashes, closures or roadwork reported on the route right now.</div>'}
   ${cov}
   ${p.cams.length?`<details><summary class="small" style="cursor:pointer">📷 ${p.cams.length} road cameras on the route</summary><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">${p.cams.slice(0,60).map(c=>`<a href="${esc(c.url)}" target="_blank" class="small" style="color:#9fb3c8">${NOEMBED.has(c.st)?'<div style="padding:18px 6px;border:1px dashed #456;border-radius:6px;text-align:center">📷 open picture</div>':`<img loading="lazy" src="${esc(c.url)}" style="width:100%;border-radius:6px" alt="">`}<br>${esc(c.name)}${c.st?' ('+c.st+')':''} · mile ${Math.round(c.mi)}</a>`).join('')}</div><div class="small">Up to ${p.miles<200?3:2} cameras closest to the road in each 50-mile stretch. Camera pictures only: no keyless source gives live traffic speeds, so none are shown.${[...new Set(p.cams.map(c=>c.st))].filter(st=>CAMNOTE[st]).map(st=>' '+esc(CAMNOTE[st])).join('')}</div></details>`:''}
   <div class="panel noprint" style="background:#1d2b3a"><h3 style="margin-top:0">📡 Get leave-time and traffic updates by email</h3>
    <div class="small">Trips you type here only live in this browser, so Grok Bot can't see them. To have it watch this drive, copy the line below and send it to Grok Bot (or add it to <code>data/trips.json</code> in the repo).
    You'll get a heads-up at 7 PM the night before an early start, a "Leave by" email about 3 hours before you should leave, another if the leave time moves 15+ minutes, and an email if a crash, closure or road-weather alert shows up on the route while you're on the way.</div>
    <div class="row"><input readonly value="${esc(wj)}" style="flex:1;font-family:monospace;font-size:12px" id="dw${i}"><button onclick="navigator.clipboard.writeText('Please watch this drive for me: '+$('#dw${i}').value).then(()=>st('📋 Copied — send it to Grok Bot'),()=>prompt('Copy this:',$('#dw${i}').value))">📋 Copy for Grok Bot</button></div>
    <div id="watched${i}" class="small watched"></div></div>
   <div class="small">Data: route OSRM (OpenStreetMap) · weather Open-Meteo · alerts NWS · road reports ${esc(p.src.join(', ')||'none')}. Checked ${ptT(Date.now())} PT.</div>`;
}
function driveMap(p,i){
  const el=$('#dmap'+i);if(!el)return;if(!window.L){el.innerHTML='<div class="small" style="padding:8px">Map unavailable.</div>';return}
  const m=L.map(el,{scrollWheelZoom:false});L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(m);
  const line=L.polyline(p.R.coords,{color:'#4dabf7',weight:4}).addTo(m);m.fitBounds(line.getBounds(),{padding:[12,12]});
  p.cams.forEach(c=>L.circleMarker([c.lat,c.lon],{radius:3,color:'#ced4da',weight:1,fillOpacity:.7}).bindPopup(`<a href="${esc(c.url)}" target="_blank">📷 ${esc(c.name)}</a>`).addTo(m));
  p.points.forEach(s=>L.circleMarker([s.lat,s.lon],{radius:5,color:s.kind?'#ffd43b':'#69db7c',fillOpacity:.9}).bindPopup(`<b>${esc(s.name)}</b><br>About ${tDT(s.t,s.tz)}${s.w?`<br>${f0(s.w.temp)}°F ${s.kind||''}`:''}`).addTo(m));
  p.issues.filter(z=>z.kind!=='notice').forEach(z=>L.circleMarker([z.lat,z.lon],{radius:6,color:['closure','incident'].includes(z.kind)?'#f03e3e':'#ff922b',fillOpacity:.9}).bindPopup(`<b>${esc(z.road||'')}</b> ${esc(z.text)}`).addTo(m));
}
async function loadWatched(){
  let j=null;try{j=await cj(TRIPS_URL+'?'+Math.floor(Date.now()/3e5),5)}catch(e){}
  const now=Date.now(),tm=t=>tzToMs(t.arrive_by||t.depart,t.tz||TZ),T=(j&&j.trips||[]).filter(t=>{try{return tm(t)+72*36e5>now}catch(e){return false}});
  document.querySelectorAll('.watched').forEach(el=>el.innerHTML=j?(T.length?'👀 Grok Bot is watching: '+T.map(t=>`${esc((t.to||'').split(',')[0])} (${t.arrive_by?'arrive by':'leave at'} ${ptD(tm(t),t.tz||TZ)} ${tT(tm(t),t.tz||TZ)})`).join(' · '):'No drives are being watched right now.'):'');
}
