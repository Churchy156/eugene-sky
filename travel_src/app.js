'use strict';
const RELAY='https://eugene-sky-traffic.eugene-sky.workers.dev';
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const st=m=>$('#status').innerHTML=m;
let AP=[],APX={},trip={home:null,legs:[]},charts=[];
// ---------- cache + polite fetch ----------
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let lastOM=0;
async function cj(url,ttlMin,{om=false,text=false}={}){
  const k='tc:'+url;try{const c=JSON.parse(localStorage.getItem(k)||'null');if(c&&Date.now()-c.t<ttlMin*6e4)return c.d}catch(e){}
  if(om){const w=lastOM+350-Date.now();if(w>0)await sleep(w);lastOM=Date.now()}
  let r;for(let i=0;i<3;i++){r=await fetch(url);if(r.status!==429)break;st('⏳ Open-Meteo rate limit — waiting a few seconds…');await sleep(4000*(i+1))}
  if(!r.ok){const old=JSON.parse(localStorage.getItem(k)||'null');if(old)return old.d;throw new Error(r.status+' '+url.split('?')[0])}
  const d=text?await r.text():await r.json();
  try{localStorage.setItem(k,JSON.stringify({t:Date.now(),d}))}catch(e){pruneCache();try{localStorage.setItem(k,JSON.stringify({t:Date.now(),d}))}catch(e2){}}
  return d;
}
function pruneCache(){const ks=Object.keys(localStorage).filter(k=>k.startsWith('tc:'));ks.map(k=>[k,JSON.parse(localStorage.getItem(k)).t]).sort((a,b)=>a[1]-b[1]).slice(0,Math.ceil(ks.length/2)).forEach(([k])=>localStorage.removeItem(k))}
const r2=x=>Math.round(x*100)/100;
// ---------- dates ----------
const ymd=d=>d.toISOString().slice(0,10);
const addD=(s,n)=>{const d=new Date(s+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return ymd(d)};
const days=(a,b)=>{const o=[];for(let d=a;d<=b;d=addD(d,1))o.push(d);return o};
const today=()=>{const d=new Date();return new Date(d-d.getTimezoneOffset()*6e4).toISOString().slice(0,10)};
const fmtD=s=>new Date(s+'T12:00:00Z').toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',timeZone:'UTC'});
// ---------- geocoding ----------
async function geocode(q){
  q=q.trim();if(!q)throw new Error('empty');
  if(/^\d{5}$/.test(q)){const j=await cj('https://api.zippopotam.us/us/'+q,1e5);const p=j.places[0];return{name:`${p['place name']}, ${p['state abbreviation']} ${q}`,lat:+p.latitude,lon:+p.longitude,cc:'US'}}
  const a=apFind(q);if(a&&q.length===3)return a;
  if(/\d/.test(q)||q.split(',').length>2){const j=await cj('https://nominatim.openstreetmap.org/search?format=json&limit=1&addressdetails=1&q='+encodeURIComponent(q),1e5);if(j[0])return{name:j[0].display_name.split(',').slice(0,3).join(','),lat:+j[0].lat,lon:+j[0].lon,cc:(j[0].address?.country_code||'').toUpperCase()}}
  const nm=q.split(',')[0];const j=await cj('https://geocoding-api.open-meteo.com/v1/search?count=5&name='+encodeURIComponent(nm),1e5,{om:true});
  let rs=j.results||[];const rest=q.split(',').slice(1).join(' ').trim().toLowerCase();
  if(rest){const f=rs.filter(r=>[r.admin1,r.country,r.country_code].some(x=>x&&(x.toLowerCase().startsWith(rest)||rest.startsWith(x.toLowerCase()))));if(f.length)rs=f}
  const r=rs[0]||(j.results||[])[0];if(!r)throw new Error('Place not found: '+q);
  return{name:[r.name,r.admin1,r.country_code].filter(Boolean).join(', '),lat:r.latitude,lon:r.longitude,cc:r.country_code};
}
function apFind(q){q=q.trim();const m=q.match(/^([A-Za-z]{3})\b/);if(m&&APX[m[1].toUpperCase()])return APX[m[1].toUpperCase()];
  const l=q.toLowerCase();const a=AP.find(a=>a[2]&&a[2].toLowerCase()===l)||AP.find(a=>a[1].toLowerCase().includes(l));return a?APX[a[0]]:null}
// ---------- weather data ----------
const DV='temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max,relative_humidity_2m_mean,sunrise,sunset,daylight_duration';
const U='&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=auto';
const FC={},HI={};
async function loadForecasts(locs){ // batched multi-location request, cached 1 h per location
  const need=[];for(const l of locs){const k=r2(l.lat)+','+r2(l.lon);if(FC[k])continue;const c=JSON.parse(localStorage.getItem('fc:'+k)||'null');if(c&&Date.now()-c.t<36e5){FC[k]=c.d;continue}if(!need.find(n=>n.k===k))need.push({k,lat:r2(l.lat),lon:r2(l.lon)})}
  for(let i=0;i<need.length;i+=10){const b=need.slice(i,i+10);
    let j=await cj(`https://api.open-meteo.com/v1/forecast?latitude=${b.map(x=>x.lat)}&longitude=${b.map(x=>x.lon)}&daily=${DV}&hourly=temperature_2m,precipitation_probability,wind_speed_10m,weather_code,visibility&forecast_days=16${U}`,60,{om:true});
    if(!Array.isArray(j))j=[j];b.forEach((x,n)=>{FC[x.k]=j[n];try{localStorage.setItem('fc:'+x.k,JSON.stringify({t:Date.now(),d:j[n]}))}catch(e){pruneCache()}})}
}
async function loadHist(l){ // 20 yrs ERA5, cached 30 days
  const k=r2(l.lat)+','+r2(l.lon);if(HI[k])return HI[k];const y=new Date().getFullYear(),end=addD(today(),-7);
  const j=await cj(`https://archive-api.open-meteo.com/v1/archive?latitude=${r2(l.lat)}&longitude=${r2(l.lon)}&start_date=${y-20}-01-01&end_date=${end}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,daylight_duration${U}`,43200,{om:true});
  const by={},d=j.daily;d.time.forEach((t,i)=>{const md=t.slice(5);(by[md]=by[md]||[]).push({y:+t.slice(0,4),hi:d.temperature_2m_max[i],lo:d.temperature_2m_min[i],p:d.precipitation_sum[i],h:d.relative_humidity_2m_mean[i],dl:d.daylight_duration[i]})});
  return HI[k]=by;
}
const avg=a=>{a=a.filter(x=>x!=null);return a.length?a.reduce((s,x)=>s+x,0)/a.length:null};
function normal(by,date){ // ±3-day window around calendar date
  const rows=[];for(let o=-3;o<=3;o++){const md=addD(date,o).slice(5);(by[md]||[]).forEach(r=>rows.push({...r,o}))}
  const ex=rows.filter(r=>r.o===0),ly=ex.find(r=>r.y===+date.slice(0,4)-1)||ex.filter(r=>r.y<+date.slice(0,4)).sort((a,b)=>b.y-a.y)[0];
  const his=ex.map(r=>r.hi).filter(x=>x!=null),los=ex.map(r=>r.lo).filter(x=>x!=null);
  const recHi=ex.reduce((m,r)=>r.hi!=null&&(!m||r.hi>m.hi)?r:m,null),recLo=ex.reduce((m,r)=>r.lo!=null&&(!m||r.lo<m.lo)?r:m,null);
  return{hi:avg(rows.map(r=>r.hi)),lo:avg(rows.map(r=>r.lo)),rain:rows.length?100*rows.filter(r=>r.p>=0.01).length/rows.length:null,pr:avg(rows.map(r=>r.p)),hum:avg(rows.map(r=>r.h)),dl:avg(ex.map(r=>r.dl)),
    recHi:recHi&&{v:recHi.hi,y:recHi.y},recLo:recLo&&{v:recLo.lo,y:recLo.y},ly,n:ex.length,p10:his.length?his.sort((a,b)=>a-b)[Math.floor(his.length*.1)]:null,p90:his.length?his[Math.floor(his.length*.9)]:null,lo10:los.length?los.sort((a,b)=>a-b)[Math.floor(los.length*.1)]:null}
}
function dayInfo(l,date,by){
  const f=FC[r2(l.lat)+','+r2(l.lon)],i=f?f.daily.time.indexOf(date):-1,n=by?normal(by,date):null;
  if(i>=0){const d=f.daily;return{src:'forecast',hi:d.temperature_2m_max[i],lo:d.temperature_2m_min[i],pp:d.precipitation_probability_max[i],pr:d.precipitation_sum[i],wind:d.wind_speed_10m_max[i],uv:d.uv_index_max[i],hum:d.relative_humidity_2m_mean[i],sr:d.sunrise[i]?.slice(11),ss:d.sunset[i]?.slice(11),dl:d.daylight_duration[i]/3600,n}}
  return n?{src:'typical',hi:n.hi,lo:n.lo,pp:n.rain,pr:n.pr,wind:null,uv:null,hum:n.hum,dl:n.dl/3600,n}:null;
}
// ---------- trip model ----------
function stops(){ // destinations with date ranges
  const o=[];const L=trip.legs;
  L.filter(l=>l.type==='hotel'&&l.loc&&l.in&&l.out).forEach(l=>o.push({name:l.name?`${l.name} — ${l.loc.name}`:l.loc.name,loc:l.loc,a:l.in,b:addD(l.out,-1)<l.in?l.in:l.out,nights:Math.max(1,(new Date(l.out)-new Date(l.in))/864e5)}));
  if(!o.length){const F=L.filter(l=>l.type==='flight'&&l.toAp&&l.dep).sort((a,b)=>a.dep<b.dep?-1:1);
    F.forEach((f,i)=>{if(trip.home&&dist(f.toAp,trip.home)<80)return;const a=(f.arr||f.dep).slice(0,10),nx=F[i+1],b=nx?nx.dep.slice(0,10):a;o.push({name:f.toAp.name,loc:f.toAp,a,b,nights:Math.max(1,(new Date(b)-new Date(a))/864e5)})})}
  return o.sort((x,y)=>x.a<y.a?-1:1);
}
function dist(a,b){const R=3959,t=Math.PI/180,dl=(b.lat-a.lat)*t,dn=(b.lon-a.lon)*t,h=Math.sin(dl/2)**2+Math.cos(a.lat*t)*Math.cos(b.lat*t)*Math.sin(dn/2)**2;return 2*R*Math.asin(Math.sqrt(h))}
// ---------- editor ----------
function legHTML(l,i){
  if(l.type==='flight')return`<div class="leg" data-i="${i}"><b>✈️ Flight</b> <button class="x" data-del="${i}" style="float:right;padding:2px 8px">✕</button><div class="row">
   <label>Flight # (optional)<input data-k="fl" value="${esc(l.fl)}" placeholder="AS 2105" size="9"></label>
   <label>From<input data-k="from" list="aplist" value="${esc(l.from)}" placeholder="EUG" size="12"></label>
   <label>To<input data-k="to" list="aplist" value="${esc(l.to)}" placeholder="HNL" size="12"></label>
   <label>Departs (local)<input type="datetime-local" data-k="dep" value="${esc(l.dep)}"></label>
   <label>Arrives (local)<input type="datetime-local" data-k="arr" value="${esc(l.arr)}"></label></div></div>`;
  return`<div class="leg" data-i="${i}"><b>🏨 Hotel stay</b> <button class="x" data-del="${i}" style="float:right;padding:2px 8px">✕</button><div class="row">
   <label>Hotel name (optional)<input data-k="name" value="${esc(l.name)}" placeholder="Hilton Hawaiian Village" size="18"></label>
   <label>City or address<input data-k="where" value="${esc(l.where)}" placeholder="Honolulu, HI" size="20"></label>
   <label>Check-in<input type="date" data-k="in" value="${esc(l.in)}"></label>
   <label>Check-out<input type="date" data-k="out" value="${esc(l.out)}"></label></div></div>`;
}
function drawLegs(){$('#legs').innerHTML=trip.legs.map(legHTML).join('')||'<div class="small">No legs yet — add a flight or hotel stay, or pick a sample trip.</div>';$('#homeName').textContent=trip.home?'Home: '+trip.home.name:''}
$('#legs').addEventListener('input',e=>{const k=e.target.dataset.k,i=e.target.closest('.leg')?.dataset.i;if(k&&i!=null){trip.legs[i][k]=e.target.value;save()}});
$('#legs').addEventListener('click',e=>{const d=e.target.dataset.del;if(d!=null){trip.legs.splice(+d,1);save();drawLegs()}});
$('#addF').onclick=()=>{const p=trip.legs.filter(l=>l.type==='flight').pop();trip.legs.push({type:'flight',from:p?.to||'',to:p?.from||''});drawLegs();save()};
$('#addH').onclick=()=>{const p=trip.legs.filter(l=>l.type==='flight').pop();trip.legs.push({type:'hotel',where:p&&APX[(p.to||'').slice(0,3).toUpperCase()]?.city||'',in:p?.arr?.slice(0,10)||p?.dep?.slice(0,10)||''});drawLegs();save()};
$('#clear').onclick=()=>{if(confirm('Clear this trip?')){trip={home:trip.home,legs:[]};save();drawLegs();$('#out').innerHTML='';st('')}};
function packTrip(){return{h:trip.home&&{n:trip.home.name,a:r2(trip.home.lat),o:r2(trip.home.lon)},l:trip.legs.map(({loc,fromAp,toAp,...r})=>r)}}
function unpack(p){return{home:p.h&&{name:p.h.n,lat:p.h.a,lon:p.h.o},legs:p.l||[]}}
function save(){localStorage.setItem('travel_trip',JSON.stringify(packTrip()));history.replaceState(null,'','#t='+btoa(unescape(encodeURIComponent(JSON.stringify(packTrip())))))}
$('#share').onclick=async()=>{save();try{await navigator.clipboard.writeText(location.href);st('🔗 Share link copied — anyone opening it sees this trip.')}catch(e){prompt('Copy this link:',location.href)}};
$('#homeGo').onclick=async()=>{try{trip.home=await geocode($('#homeQ').value);save();drawLegs()}catch(e){st('⚠️ '+e.message)}};
$('#homeQ').onkeydown=e=>{if(e.key==='Enter')$('#homeGo').click()};
$('#homeMe').onclick=()=>navigator.geolocation.getCurrentPosition(async p=>{const lat=p.coords.latitude,lon=p.coords.longitude;let name=`${lat.toFixed(2)}, ${lon.toFixed(2)}`;
  try{const j=await cj(`https://nominatim.openstreetmap.org/reverse?format=json&zoom=10&lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}`,1e5);name=[j.address.city||j.address.town||j.address.village||j.address.county,j.address.state].filter(Boolean).join(', ')}catch(e){}
  trip.home={name,lat,lon};save();drawLegs()},e=>st('⚠️ Location unavailable: '+e.message));
$('#samples').onchange=e=>{const v=e.target.value;e.target.value='';if(!v)return;const t=today();
  if(v==='hnl'){const d=addD(t,7);trip={home:{name:'Eugene, OR 97401',lat:44.05,lon:-123.09},legs:[
    {type:'flight',fl:'AS 2105',from:'EUG',to:'HNL',dep:d+'T08:00',arr:d+'T13:30'},{type:'hotel',name:'Waikiki Beach hotel',where:'Honolulu, HI',in:d,out:addD(d,5)},
    {type:'flight',fl:'AS 2106',from:'HNL',to:'EUG',dep:addD(d,5)+'T14:30',arr:addD(d,5)+'T22:30'}]}}
  else{const y=new Date().getFullYear(),d=(t>y+'-12-18'?y+1:y)+'-12-18';trip={home:{name:'Eugene, OR 97401',lat:44.05,lon:-123.09},legs:[
    {type:'flight',fl:'UA 5432',from:'EUG',to:'DEN',dep:d+'T06:10',arr:d+'T09:40'},{type:'hotel',name:'',where:'1600 California St, Denver, CO',in:d,out:addD(d,4)},
    {type:'flight',fl:'UA 5433',from:'DEN',to:'EUG',dep:addD(d,4)+'T18:00',arr:addD(d,4)+'T19:50'}]}}
  save();drawLegs();run()};
// ---------- run ----------
$('#run').onclick=()=>run();
async function run(){
  try{
    charts.forEach(c=>c.destroy());charts=[];$('#out').innerHTML='';
    if(!trip.home){if($('#homeQ').value)trip.home=await geocode($('#homeQ').value);else throw new Error('Set your home location first.')}
    st('📍 Looking up places…');
    for(const l of trip.legs){if(l.type==='flight'){l.fromAp=apFind(l.from||'');l.toAp=apFind(l.to||'');if(!l.fromAp&&l.from)l.fromAp=await geocode(l.from);if(!l.toAp&&l.to)l.toAp=await geocode(l.to)}
      else if(l.where){l.loc=await geocode(l.where)}}
    const S=stops();if(!S.length)throw new Error('Add at least one hotel stay or flight with a date.');
    const locs=[trip.home,...S.map(s=>s.loc),...trip.legs.filter(l=>l.type==='flight').flatMap(f=>[f.fromAp,f.toAp]).filter(Boolean)];
    st('🌤️ Loading forecasts (one batched request)…');await loadForecasts(locs);
    const hist={};for(const l of [trip.home,...S.map(s=>s.loc)]){st('📚 Loading 20 years of history for '+esc(l.name)+'…');hist[r2(l.lat)+','+r2(l.lon)]=await loadHist(l)}
    const H=l=>hist[r2(l.lat)+','+r2(l.lon)];
    let html='';
    S.forEach((s,si)=>{s.days=days(s.a,s.b).map(d=>({d,...dayInfo(s.loc,d,H(s.loc))}));s.home=days(s.a,s.b).map(d=>({d,...dayInfo(trip.home,d,H(trip.home))}))});
    html+=flightsHTML();
    S.forEach((s,si)=>html+=stopHTML(s,si));
    html+=packHTML(S);
    $('#out').innerHTML=html;
    S.forEach((s,si)=>chart(s,si,H(s.loc)));
    st('✅ Updated '+new Date().toLocaleTimeString()+'. <span class="small">Cached locally — reloading is free.</span>');
    extras(S);
  }catch(e){console.error(e);st('⚠️ '+esc(e.message))}
}
const f0=x=>x==null||isNaN(x)?'–':Math.round(x);
const tagS=s=>s==='forecast'?'<span class="tag">forecast</span>':'<span class="tag" title="20-year average for this date">typical</span>';
function stopHTML(s,si){
  const rows=s.days.map(d=>{const n=d.n;return`<tr><td>${fmtD(d.d)}</td><td>${tagS(d.src)}</td><td class="warm">${f0(d.hi)}°</td><td class="cool">${f0(d.lo)}°</td><td>${f0(d.pp)}%</td><td>${d.pr==null?'–':d.pr.toFixed(2)+'"'}</td><td>${f0(d.wind)}</td><td>${d.uv==null?'–':d.uv.toFixed(0)}</td><td>${f0(d.hum)}%</td><td>${d.sr?d.sr+'–'+d.ss:(d.dl?d.dl.toFixed(1)+' h':'–')}</td>
   <td>${n?f0(n.hi)+'° / '+f0(n.lo)+'°':'–'}</td><td>${n?f0(n.rain)+'%':'–'}</td><td>${n&&n.recHi?`${f0(n.recHi.v)}° (${n.recHi.y})`:'–'}</td><td>${n&&n.recLo?`${f0(n.recLo.v)}° (${n.recLo.y})`:'–'}</td><td>${n&&n.ly?`${f0(n.ly.hi)}°/${f0(n.ly.lo)}° ${n.ly.p>=0.01?'🌧'+n.ly.p.toFixed(2)+'"':'dry'}`:'–'}</td></tr>`}).join('');
  return`<div class="panel"><h2>📍 ${esc(s.name)} <span class="small">${fmtD(s.a)} → ${fmtD(s.b)} · ${s.nights} night${s.nights>1?'s':''}</span></h2>
   ${compareHTML(s)}
   <div class="grid"><div><canvas id="ch${si}"></canvas></div><div id="aq${si}" class="small">Air quality loading…</div></div>
   <h3>Day by day</h3><div class="tw"><table><tr><th>Date</th><th></th><th>High</th><th>Low</th><th>Rain chance</th><th>Rain</th><th>Wind mph</th><th>UV</th><th>Humidity</th><th>Sun</th><th>Avg hi/lo (20y)</th><th>Rain days</th><th>Record high</th><th>Record low</th><th>Last year</th></tr>${rows}</table></div>
   <div id="al${si}"></div></div>`;
}
function compareHTML(s){
  const D=s.days,Hm=s.home,a=k=>avg(D.map(d=>d[k])),b=k=>avg(Hm.map(d=>d[k]));
  const rows=[['High','hi','°F'],['Low','lo','°F'],['Rain chance','pp','%'],['Humidity','hum','%'],['UV index','uv',''],['Daylight','dl',' h']].map(([t,k,u])=>{const x=a(k),y=b(k);const df=x!=null&&y!=null?x-y:null;
    return`<tr><td>${t}</td><td>${x==null?'–':(k==='dl'?x.toFixed(1):Math.round(x))+u}</td><td>${y==null?'–':(k==='dl'?y.toFixed(1):Math.round(y))+u}</td><td class="${df>0?'warm':'cool'}">${df==null?'':(df>0?'+':'')+(k==='dl'?df.toFixed(1):Math.round(df))+u}</td></tr>`}).join('');
  return`<div class="sum">${summary(a,b)}</div><div class="tw"><table class="cmp" style="max-width:520px"><tr><th></th><th>${esc(s.loc.name.split(',')[0])}</th><th>🏠 ${esc(trip.home.name.split(',')[0])}</th><th>diff</th></tr>${rows}</table></div>`;
}
function summary(a,b){
  const dh=a('hi')-b('hi'),dhu=(a('hum')??0)-(b('hum')??0),dr=(a('pp')??0)-(b('pp')??0),p=[];
  p.push(Math.abs(dh)<4?'About the same temperature as home':`${Math.abs(Math.round(dh))}°F ${dh>0?'warmer':'colder'} than home`);
  const dl=a('lo')-b('lo');if(Math.abs(dl-dh)>=8)p.push(`nights ${Math.abs(Math.round(dl))}°F ${dl>0?'warmer':'colder'}`);
  if(Math.abs(dhu)>=10)p.push(dhu>0?'noticeably more humid':'much drier air');
  if(Math.abs(dr)>=15)p.push(dr>0?'rainier':'drier');
  let adv=dl<-8&&dh<=8?'bring warmer layers for cold mornings and nights':dh>8?'pack lighter layers':dh<-8?'bring warmer layers than you wear at home':'pack what you\'d wear at home this week';
  if((a('uv')??0)>=7)adv+=', plus serious sun protection';
  return'🧭 '+p.join(', ')+' — '+adv+'.';
}
function chart(s,si,by){
  const el=$('#ch'+si);if(!el)return;const t=today();
  const ds=days(addD(s.a,-3)<t?(s.a<t?s.a:t):addD(s.a,-3),addD(s.b,3));const N=ds.map(d=>normal(by,d)),F=ds.map(d=>dayInfo(s.loc,d,null));
  charts.push(new Chart(el,{type:'line',data:{labels:ds.map(d=>d.slice(5)),datasets:[
    {label:'Typical high (10–90%)',data:N.map(n=>n.p90),borderWidth:0,pointRadius:0,backgroundColor:'rgba(247,129,102,.18)',fill:'+1'},
    {label:'_',data:N.map(n=>n.p10),borderWidth:0,pointRadius:0},
    {label:'Avg high',data:N.map(n=>n.hi),borderColor:'#f7816688',borderDash:[4,4],pointRadius:0},
    {label:'Avg low',data:N.map(n=>n.lo),borderColor:'#58a6ff88',borderDash:[4,4],pointRadius:0},
    {label:'Forecast high',data:F.map(f=>f?.hi??null),borderColor:'#f78166',backgroundColor:'#f78166'},
    {label:'Forecast low',data:F.map(f=>f?.lo??null),borderColor:'#58a6ff',backgroundColor:'#58a6ff'}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#9fb3c8',boxWidth:10,filter:i=>i.text!=='_'}},title:{display:true,text:'Forecast vs 20-year history (°F)',color:'#e6edf3'}},
      scales:{x:{ticks:{color:'#9fb3c8'}},y:{ticks:{color:'#9fb3c8'},grid:{color:'#243445'}}}}}));
  el.parentElement.style.height='260px';
}
function flightsHTML(){
  const F=trip.legs.filter(l=>l.type==='flight'&&l.fromAp&&l.toAp&&l.dep);if(!F.length)return'';
  return`<div class="panel"><h2>✈️ Flight days</h2><div class="grid">${F.map((f,i)=>{const end=(ap,t,lbl)=>{const w=hourly(ap,t);return`<div><b>${lbl} ${esc(ap.code||'')} </b><span class="small">${esc(ap.name)}</span><br>${t?t.replace('T',' '):''} — ${w}<div id="fa_${i}_${lbl}" class="small"></div></div>`};
    return`<div class="leg"><b>${esc(f.fl||'Flight')}</b> ${esc(f.fromAp.code||'')} → ${esc(f.toAp.code||'')} <span class="small">${Math.round(dist(f.fromAp,f.toAp))} mi</span>${end(f.fromAp,f.dep,'Depart')}${end(f.toAp,f.arr||f.dep,'Arrive')}</div>`}).join('')}</div><div id="swpc" class="small" style="margin-top:6px"></div></div>`;
}
const WC={0:'☀️ clear',1:'🌤 mostly clear',2:'⛅ partly cloudy',3:'☁️ overcast',45:'🌫 fog',48:'🌫 freezing fog',51:'🌦 drizzle',53:'🌦 drizzle',55:'🌧 heavy drizzle',61:'🌧 light rain',63:'🌧 rain',65:'🌧 heavy rain',66:'🧊 freezing rain',67:'🧊 freezing rain',71:'🌨 light snow',73:'🌨 snow',75:'❄️ heavy snow',77:'🌨 snow grains',80:'🌦 showers',81:'🌧 showers',82:'⛈ heavy showers',85:'🌨 snow showers',86:'❄️ snow showers',95:'⛈ thunderstorm',96:'⛈ t-storm + hail',99:'⛈ t-storm + hail'};
function hourly(ap,t){
  const f=FC[r2(ap.lat)+','+r2(ap.lon)];if(!t)return'';const h=t.slice(0,13)+':00',i=f?f.hourly.time.indexOf(h):-1;
  if(i<0){const k=hist_any(ap,t.slice(0,10));return k?`beyond forecast range · typical ${f0(k.hi)}°/${f0(k.lo)}°F`:'beyond forecast range'}
  const H=f.hourly,vis=H.visibility[i];return`${WC[H.weather_code[i]]||''} ${f0(H.temperature_2m[i])}°F · rain ${f0(H.precipitation_probability[i])}% · wind ${f0(H.wind_speed_10m[i])} mph${vis!=null&&vis<5000?` · <b>low visibility ${(vis/1609).toFixed(1)} mi</b>`:''}`;
}
function hist_any(ap,d){let best=null,bd=60;for(const k in HI){const[la,lo]=k.split(',').map(Number),dd=dist(ap,{lat:la,lon:lo});if(dd<bd){bd=dd;best=k}}return best?normal(HI[best],d):null}
// ---------- packing ----------
function packHTML(S){
  const D=S.flatMap(s=>s.days),nights=S.reduce((a,s)=>a+s.nights,0),nd=Math.max(1,nights);
  const hi=Math.max(...D.map(d=>d.hi??-99)),lo=Math.min(...D.map(d=>d.lo??199)),wetDays=D.filter(d=>(d.pp??0)>=40||(d.pr??0)>=0.1).length,maxUV=Math.max(0,...D.map(d=>d.uv??0)),
    avgHi=avg(D.map(d=>d.hi)),hum=avg(D.map(d=>d.hum))??50,wind=Math.max(0,...D.map(d=>d.wind??0)),cap=n=>Math.min(n,7),L=[];
  const add=(cat,t)=>L.push([cat,t]);
  add('Basics',`${cap(nd+1)} × underwear & socks`);add('Basics','Toiletries, meds, chargers, ID/passport');
  if(avgHi>=78){add('Clothes',`${cap(nd+1)} × t-shirts / tanks`);add('Clothes',`${cap(Math.ceil(nd/2)+1)} × shorts or skirts`);add('Clothes','Sandals + 1 pair walking shoes')}
  else if(avgHi>=62){add('Clothes',`${cap(nd)} × short-sleeve tops`);add('Clothes',`${cap(Math.ceil(nd/2))} × long-sleeve tops`);add('Clothes',`${cap(Math.ceil(nd/3)+1)} × pants/jeans`);add('Clothes','Light sweater or hoodie')}
  else if(avgHi>=45){add('Clothes',`${cap(nd)} × long-sleeve tops`);add('Clothes',`${cap(Math.ceil(nd/3)+1)} × pants/jeans`);add('Clothes','2 × warm mid-layers (fleece/sweater)');add('Clothes','Medium jacket')}
  else{add('Clothes',`${cap(nd)} × base layers / thermals`);add('Clothes',`${cap(Math.ceil(nd/3)+1)} × warm pants`);add('Clothes','2 × fleece or wool sweaters');add('Clothes','Insulated winter coat')}
  if(lo<=35){add('Cold','Gloves, warm hat, scarf');add('Cold','Wool socks');}
  if(lo<=25)add('Cold','Insulated waterproof boots (ice/snow likely)');
  if(hi-lo>=25)add('Clothes',`Layers — temps swing ${Math.round(lo)}° to ${Math.round(hi)}°F`);
  if(wetDays){add('Rain',`Rain jacket${wetDays>=Math.ceil(D.length/2)?' + compact umbrella':''} (${wetDays} wet day${wetDays>1?'s':''} likely)`);if(wetDays>=2||D.some(d=>(d.pr??0)>=0.5))add('Rain','Waterproof shoes')}
  if(maxUV>=6||avgHi>=80){add('Sun',`Sunscreen SPF 30+${maxUV?` (UV up to ${Math.round(maxUV)})`:''}`);add('Sun','Sunglasses + hat')}
  if(avgHi>=75){add('Fun','Swimwear + cover-up');add('Fun','Reef-safe sunscreen if heading to the ocean')}
  if(hum>=75&&avgHi>=75)add('Clothes','Breathable/quick-dry fabrics (humid)');
  if(wind>=25)add('Clothes',`Windbreaker (gusts to ${Math.round(wind)} mph)`);
  if(hum<35)add('Basics','Lip balm & lotion (dry air)');
  if(nd>7)add('Basics','Plan a laundry stop (counts capped at 7 days)');
  const cats=[...new Set(L.map(x=>x[0]))];window._pack=L;
  return`<div class="panel pack"><h2>🎒 Packing list <span class="small">${D.length} day${D.length>1?'s':''} · ${nights} night${nights!==1?'s':''} · ${Math.round(lo)}–${Math.round(hi)}°F</span></h2>
   <div class="grid">${cats.map(c=>`<div><h3>${c}</h3><ul style="padding:0">${L.filter(x=>x[0]===c).map(x=>`<li><label><input type="checkbox">${esc(x[1])}</label></li>`).join('')}</ul></div>`).join('')}</div>
   <div class="row noprint"><button onclick="navigator.clipboard.writeText(_pack.map(x=>'☐ '+x[1]).join('\\n')).then(()=>st('📋 Packing list copied'))">📋 Copy list</button><button onclick="print()">🖨️ Print</button></div></div>`;
}
// ---------- extras: AQ, alerts, FAA, SWPC ----------
async function extras(S){
  for(const [si,s] of S.entries()){
    try{const j=await cj(`https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${r2(s.loc.lat)}&longitude=${r2(s.loc.lon)}&hourly=us_aqi,pm2_5&forecast_days=5&timezone=auto`,120,{om:true});
      const by={};j.hourly.time.forEach((t,i)=>{const d=t.slice(0,10);by[d]=Math.max(by[d]??0,j.hourly.us_aqi[i]??0)});
      const cat=v=>v<=50?['Good','#69db7c']:v<=100?['Moderate','#ffd43b']:v<=150?['Unhealthy for sensitive','#ff922b']:v<=200?['Unhealthy','#f03e3e']:['Very unhealthy','#ae3ec9'];
      $('#aq'+si).innerHTML='<b>🌬️ Air quality (US AQI, daily max — next 5 days)</b><br>'+Object.entries(by).map(([d,v])=>{const[c,col]=cat(v);return`${fmtD(d)}: <b style="color:${col}">${v} ${c}</b>`}).join('<br>')+(s.a>addD(today(),4)?'<br><span class="small">Trip is beyond the 5-day AQ forecast; check again closer to departure.</span>':'')}
    catch(e){$('#aq'+si).textContent='Air quality unavailable ('+e.message+')'}
    if((s.loc.cc||'')==='US'||(s.loc.lon<-60&&s.loc.lat>18))try{const j=await cj(`https://api.weather.gov/alerts/active?point=${s.loc.lat.toFixed(3)},${s.loc.lon.toFixed(3)}`,10);
      $('#al'+si).innerHTML=j.features.length?j.features.map(a=>`<div class="alert">⚠️ <b>${esc(a.properties.event)}</b> — ${esc(a.properties.headline)}</div>`).join(''):'<div class="small ok">✓ No active NWS alerts here right now.</div>'}catch(e){}
  }
  const F=trip.legs.filter(l=>l.type==='flight'&&l.fromAp&&l.toAp&&l.dep);if(!F.length)return;
  let faa=null;try{const x=await cj(RELAY+'/faa',3,{text:true});faa=new DOMParser().parseFromString(x,'text/xml')}catch(e){}
  F.forEach((f,i)=>[[f.fromAp,'Depart'],[f.toAp,'Arrive']].forEach(async([ap,lbl])=>{const el=$(`#fa_${i}_${lbl}`);if(!el)return;let h=[];
    if(faa&&ap.cc==='US'){const hits=[...faa.querySelectorAll('ARPT')].filter(n=>n.textContent===ap.code).map(n=>n.parentElement);
      h.push(hits.length?hits.map(p=>`<span class="warm">FAA now: ${esc(p.tagName.replace(/_/g,' '))} — ${esc(p.querySelector('Reason')?.textContent||'')} ${esc(p.querySelector('Avg')?.textContent||p.querySelector('Max')?.textContent||'')}</span>`).join('<br>'):'<span class="ok">FAA now: no reported delays</span>')}
    if(ap.cc==='US')try{const j=await cj(`https://api.weather.gov/alerts/active?point=${ap.lat.toFixed(3)},${ap.lon.toFixed(3)}`,10);j.features.slice(0,3).forEach(a=>h.push(`⚠️ ${esc(a.properties.event)}`))}catch(e){}
    el.innerHTML=h.join('<br>')}));
  try{const k=await cj('https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json',60);const rows=Array.isArray(k[0])?k.slice(1).map(r=>({t:r[0],kp:+r[1]})):k.map(r=>({t:r.time_tag,kp:+r.kp}));
    const mx=Math.max(...rows.filter(r=>r.t>=new Date().toISOString().slice(0,10)).map(r=>r.kp));
    $('#swpc').innerHTML=`🛰️ Space weather (fun extra): max Kp forecast next 3 days = <b>${mx.toFixed(1)}</b>${mx>=5?' — geomagnetic storm: polar routes may see HF radio issues, and you might catch an aurora from a window seat!':' — quiet; no effect on flights expected.'}`}catch(e){}
}
// ---------- init ----------
(async()=>{
  AP=await fetch('airports.json').then(r=>r.json());AP.forEach(a=>APX[a[0]]={code:a[0],name:`${a[0]} — ${a[1]}`,city:a[2],cc:a[3],lat:a[4],lon:a[5]});
  $('#aplist').innerHTML=AP.filter(a=>a[3]==='US'||/International/.test(a[1])).map(a=>`<option value="${a[0]} ${esc(a[2])}">${esc(a[1])}</option>`).join('');
  const h=location.hash.match(/#t=(.+)/);let p=null;try{p=h?JSON.parse(decodeURIComponent(escape(atob(h[1])))):JSON.parse(localStorage.getItem('travel_trip')||'null')}catch(e){}
  if(p)trip=unpack(p);drawLegs();if(trip.home)$('#homeQ').value=trip.home.name;
  if(trip.legs.length&&trip.home)run();else st('Set your home, then add flights and hotel stays — or pick a sample trip.');
})();
