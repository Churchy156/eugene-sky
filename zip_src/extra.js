// Local "Eugene-style" data for any ZIP: county fatal crashes (FARS), power outages (EAGLE-I) + utilities,
// game days (ESPN, prebuilt), city police/311/crash open data (Socrata), correlations.
const X={fars:null,eag:null,games:null,city:[],cityData:{},util:[],meta:null};
const CITY=[ // open-data daily counts (Socrata, CORS ok). kind: police | 311 | crash
 {c:'Seattle',la:47.61,lo:-122.33,dom:'data.seattle.gov',id:'33kz-ixgy',f:'cad_event_original_time_queued',k:'police',lab:'Seattle Police CAD calls'},
 {c:'Seattle',la:47.61,lo:-122.33,dom:'data.seattle.gov',id:'kzjm-xkqj',f:'datetime',k:'fire',lab:'Seattle Fire 911 dispatches'},
 {c:'San Francisco',la:37.77,lo:-122.42,dom:'data.sf.gov',id:'gnap-fj3t',f:'received_datetime',k:'police',lab:'SFPD calls for service (real-time)'},
 {c:'Chicago',la:41.88,lo:-87.63,dom:'data.cityofchicago.org',id:'ijzp-q8t2',f:'date',k:'police',lab:'Chicago crime reports'},
 {c:'Chicago',la:41.88,lo:-87.63,dom:'data.cityofchicago.org',id:'85ca-t3if',f:'crash_date',k:'crash',lab:'Chicago traffic crashes (all)'},
 {c:'New York',la:40.71,lo:-74.0,dom:'data.cityofnewyork.us',id:'n2zq-pubd',f:'incident_date',k:'police',lab:'NYPD calls for service (YTD, lagged)'},
 {c:'New York',la:40.71,lo:-74.0,dom:'data.cityofnewyork.us',id:'erm2-nwe9',f:'created_date',k:'311',lab:'NYC 311 requests'},
 {c:'New York',la:40.71,lo:-74.0,dom:'data.cityofnewyork.us',id:'h9gi-nx95',f:'crash_date',k:'crash',lab:'NYC motor vehicle collisions (all)'},
 {c:'Cincinnati',la:39.10,lo:-84.51,dom:'data.cincinnati-oh.gov',id:'gexm-h6bt',f:'create_time_incident',k:'police',lab:'Cincinnati police CAD calls'},
 {c:'Austin',la:30.27,lo:-97.74,dom:'data.austintexas.gov',id:'22de-7rzg',f:'response_datetime',k:'police',lab:'Austin 911 police responses'},
 {c:'Los Angeles',la:34.05,lo:-118.24,dom:'data.lacity.org',id:'2nrs-mtv8',f:'date_occ',k:'police',lab:'LAPD crime reports (2020–2024)'},
 {c:'New Orleans',la:29.95,lo:-90.07,dom:'data.nola.gov',id:'3pha-hum9',f:'timecreate',k:'police',lab:'New Orleans calls for service (2021)'},
];
function holiday(s){const y=+s.slice(0,4),m=+s.slice(5,7),d=+s.slice(8,10),wd=new Date(s+'T12:00:00Z').getUTCDay(),nth=Math.ceil(d/7),last=d+7>new Date(Date.UTC(y,m,0)).getUTCDate();
 return (m==1&&d==1)||(m==1&&wd==1&&nth==3)||(m==2&&wd==1&&nth==3)||(m==5&&wd==1&&last)||(m==6&&d==19&&y>=2021)||(m==7&&d==4)||(m==9&&wd==1&&nth==1)||(m==11&&d==11)||(m==11&&wd==4&&nth==4)||(m==12&&d==25)}
function decode(j,c){const a=j.c[c];if(!a)return null;const m={};let t=Date.parse(j.base+'T12:00:00Z'),p=0;for(let i=0;i<a.length;i+=2){p+=a[i];m[new Date(t+p*864e5).toISOString().slice(0,10)]=a[i+1]}m._first=j.base;return m}
function cnt(m,s,e,zero=true){let t=0,n=0;for(let d=s;d<=e;d=addD(d,1)){const x=m[d];if(x!=null){t+=x;n++}else if(zero){n++}}return n?t:null}
function effects(m,from,to,noGame){ // mean of series on weather/holiday days vs baseline
 const g={base:[],rain:[],heavy:[],snow:[],freeze:[],hol:[],game:[],wind:[]};
 for(let d=from;d<=to;d=addD(d,1)){const w=W[d];if(!w)continue;const x=m[d]??0,r=w.precipitation_sum||0,sn=w.snowfall_sum||0,fr=(w.temperature_2m_min??99)<=32,h=holiday(d),gm=X.gday&&X.gday[d];
  if(r>=.1)g.rain.push(x);if(r>=1)g.heavy.push(x);if(sn>0)g.snow.push(x);if(fr)g.freeze.push(x);if(h)g.hol.push(x);if(gm)g.game.push(x);if((w.wind_speed_10m_max||0)>=30)g.wind.push(x);
  if(r<.1&&!sn&&!h)g.base.push(x)}
 const mean=a=>a.reduce((p,c)=>p+c,0)/a.length,b=mean(g.base);
 const L={rain:'Rain ≥0.1"',heavy:'Rain ≥1"',snow:'Snow',freeze:'Freezing night',hol:'Holiday',game:'Home game ≤50 mi',wind:'Wind ≥30 mph'};
 return Object.keys(L).filter(k=>!(noGame&&k=='game')).map(k=>g[k].length>=5&&b>0?`<div>${L[k]}: <b class="${mean(g[k])>=b?'up':'dn'}">${((mean(g[k])/b-1)*100).toFixed(0)}%</b> <span class="small">(${g[k].length} days)</span></div>`:`<div>${L[k]}: <span class="small">too few days</span></div>`).join('')+`<div class="small">vs dry, snow-free, non-holiday days (avg ${b.toFixed(2)}/day, ${g.base.length} days), ${from} → ${to}.</div>`}
async function loadExtra(){
 const P=['xFars','xPow','xGame','xCity'];P.forEach(p=>$(p+'N').textContent='loading…');
 X.meta=X.meta||await J('data/meta.json').catch(()=>({}));
 try{const a=await J(`https://geo.fcc.gov/api/census/area?lat=${LOC.lat}&lon=${LOC.lon}&format=json`);const r=a.results[0];LOC.fips=r.county_fips;LOC.county=r.county_name;LOC.sfips=r.state_fips;
  $('place').innerHTML+=` <span class="small">· ${r.county_name} (FIPS ${r.county_fips})</span>`}catch(e){LOC.fips=null}
 X.fars=X.eag=null;
 if(LOC.fips){const [f,e]=await Promise.all([J(`data/fars/${LOC.sfips}.json`).catch(()=>null),J(`data/eaglei/${LOC.sfips}.json`).catch(()=>null)]);
  X.fars=f&&(decode(f,LOC.fips.slice(2))||{_first:f.base});X.eag=e&&decode(e,LOC.fips.slice(2))}
 // utilities
 J(`https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0/query?geometry=${LOC.lon},${LOC.lat}&geometryType=esriGeometryPoint&inSR=4326&outFields=NAME,WEBSITE,TYPE,CUSTOMERS,TELEPHONE&returnGeometry=false&f=json`).then(r=>{
  X.util=r.features.map(f=>f.attributes);$('xUtil').innerHTML='<b>Utilities serving this point</b> (HIFLD/EIA-861): '+(X.util.length?X.util.map(u=>`<div>${MapX.esc(u.NAME)} <span class="small">${u.TYPE||''}${u.CUSTOMERS>100?' · '+u.CUSTOMERS.toLocaleString()+' customers':''}</span> ${u.WEBSITE&&u.WEBSITE!='NOT AVAILABLE'?`<a target=_blank href="${MapX.esc(/^http/.test(u.WEBSITE)?u.WEBSITE:'http://'+u.WEBSITE)}">website / outage map</a>`:''}</div>`).join(''):'none found')+
  `<div class="small">Live county outage totals: <a target=_blank href="https://poweroutage.us/">poweroutage.us</a> (no free API). History below: ORNL EAGLE-I.</div>`}).catch(()=>$('xUtil').textContent='Utility lookup unavailable');
 // games
 X.games=X.games||await J('data/games.json').catch(()=>({g:[]}));
 X.near=X.games.g.filter(g=>MapX.km(LOC.lat,LOC.lon,g[3],g[4])<=80);X.gday={};X.near.forEach(g=>(X.gday[g[0]]=X.gday[g[0]]||[]).push(g));
 // city open data
 X.city=CITY.filter(c=>MapX.km(LOC.lat,LOC.lon,c.la,c.lo)<=40);X.cityData={};
 await Promise.all(X.city.map(async c=>{const from=addD(iso(new Date()),-1100);
  try{const u=`https://${c.dom}/resource/${c.id}.json?$select=date_trunc_ymd(${c.f}) as d,count(*) as n&$where=${c.f}>'${from}T00:00:00'&$group=d&$order=d&$limit=5000`;
   const r=await J(encodeURI(u));const m={};r.forEach(x=>{if(x.d)m[x.d.slice(0,10)]=+x.n});X.cityData[c.id]=m}catch(e){X.cityData[c.id]=null}}));
 render();
}
function renderExtra(s,D,ps,pe,days){ if(!LOC||LOC.fips===undefined)return;
 const N=days.length,pct=(a,b)=>a==null||b==null||!b?'':` <span class="${a>=b?'up':'dn'}">${a>=b?'▲':'▼'}${Math.abs(a/b*100-100).toFixed(0)}%</span>`;
 const cards=[];
 // FARS
 const fl=(X.meta||{}).fars_last_year||2024;
 if(X.fars){const f=X.fars,inR=D.slice(0,4)<=fl&&s>='1975';const c=inR?cnt(f,s,D):null,pr=inR?cnt(f,ps,pe):null;
  let nm=[];for(let y=1975;y<=Math.min(fl,+D.slice(0,4)-1);y++){const dy=+D.slice(0,4)-y;nm.push(cnt(f,(+s.slice(0,4)-dy)+s.slice(4),y+D.slice(4)))}const nv=nm.length?nm.reduce((a,b)=>a+b,0)/nm.length:null;
  cards.push(`<div class="card"><div class="t">Fatal crashes · ${LOC.county} · ${per}</div><div class="v">${c==null?'—':c}</div><div class="c">${c==null?'FARS covers 1975–'+fl:'vs prior '+pr+pct(c,pr)+' · normal '+(nv??0).toFixed(1)}</div></div>`);
  const y5=[];for(let y=fl-4;y<=fl;y++)y5.push(cnt(f,y+'-01-01',y+'-12-31'));
  $('xFarsN').innerHTML=`NHTSA FARS, ${LOC.county}: ${y5.join(', ')} fatal crashes in ${fl-4}–${fl}. All-severity crash data: ${X.city.some(c=>c.k=='crash')?'city dataset below':'not available here as an open daily feed (most state DOT crash databases are request-only; open APIs found for NYC and Chicago).'}<br><b>Weather/holiday effects on daily fatal crashes (2000–${fl})</b>${effects(f,'2000-01-01',fl+'-12-31')}`;
  ch('cFars','bar',days,[['Fatal crashes',days.map(d=>d.slice(0,4)<=fl?(f[d]||0):null),'#f85149']])}
 else $('xFarsN').textContent='No FARS data for this county.';
 // EAGLE-I
 if(X.eag){const e=X.eag,last=(X.meta||{}).eaglei_last||'2025-12-31';let mx=0,md='';days.forEach(d=>{if((e[d]||0)>mx){mx=e[d];md=d}});
  cards.push(`<div class="card"><div class="t">Peak customers out · ${per}</div><div class="v">${D<'2014-01-01'||s>last?'—':mx.toLocaleString()}</div><div class="c">${D<'2014'||s>last?'EAGLE-I 2014–'+last.slice(0,4):md?'on '+md:'no outages ≥10'}</div></div>`);
  $('xPowN').innerHTML=`ORNL EAGLE-I peak customers without power (daily, county) 2014–${last}. Live/current outages: utility outage maps above.<br><b>Weather effects on daily outage peaks (2015–${last.slice(0,4)})</b>${effects(e,'2015-01-01',last,true)}`;
  ch('cPow','bar',days,[['Peak customers out',days.map(d=>d>=  '2014-11-01'&&d<=last?(e[d]||0):null),'#e3b341']])}
 else $('xPowN').textContent='No EAGLE-I outage history for this county (or none ≥10 customers).';
 // games
 const gw=X.near.filter(g=>g[0]>=s&&g[0]<=D),today=iso(new Date()),up=X.near.filter(g=>g[0]>=today).slice(0,12);
 cards.push(`<div class="card"><div class="t">Home games ≤50 mi · ${per}</div><div class="v">${gw.length}</div><div class="c">${[...new Set(gw.map(g=>g[1]))].join(', ')||'none'}</div></div>`);
 const teams=[...new Set(X.near.map(g=>g[1]+': '+g[2]))].sort();
 $('xGameN').innerHTML=`<b>Teams with home games within 50 mi</b> (ESPN, 2019→upcoming; FBS football, D1 men's basketball, NFL, NBA, WNBA, MLB, NHL, MLS): ${teams.length?MapX.esc(teams.join(' · ')):'none'}<br><b>Upcoming:</b> ${up.length?up.map(g=>`${g[0]} ${g[1]} ${MapX.esc(g[2])}`).join(' · '):'none scheduled in data'}${gw.length?'<br><b>In window:</b> '+gw.slice(-15).map(g=>`${g[0]} ${MapX.esc(g[2])}`).join(' · '):''}`;
 ch('cGame','bar',days,[['Home games',days.map(d=>(X.gday[d]||[]).length),'#a371f7']]);
 // city
 if(!X.city.length){$('xCityN').innerHTML=`No open police/911/311 calls dataset in our lookup within 25 mi of ${LOC.name}. Cities covered: ${[...new Set(CITY.map(c=>c.c))].join(', ')}. (Eugene/Springfield dispatch logs are on the Eugene dashboard.)`;ch('cCity','line',[],[])}
 else{const sets=[],col=['#58a6ff','#3fb950','#f78166','#d2a8ff'];let html='';
  X.city.forEach((c,i)=>{const m=X.cityData[c.id];if(!m){html+=`<div>${c.lab}: unavailable</div>`;return}
   const keys=Object.keys(m).sort(),lo=keys[0],hi=keys[keys.length-1],a=cnt(m,s,D,false),b=cnt(m,ps,pe,false);
   cards.push(`<div class="card"><div class="t">${c.lab} · ${per}</div><div class="v">${a==null?'—':a.toLocaleString()}</div><div class="c">${a==null?'data '+lo+'→'+hi:'vs prior '+(b??'—').toLocaleString()+pct(a,b)}</div></div>`);
   html+=`<div><b>${c.lab}</b> <span class="small">(${c.dom}, ${lo}→${hi}; last 3 yrs loaded)</span>${keys.length>60?effects(m,lo,addD(hi,-1)):''}</div>`;
   sets.push([c.lab,days.map(d=>m[d]??null),col[i%4],0,i?'y1':'y'])});
  $('xCityN').innerHTML=html;ch('cCity','line',days,sets.slice(0,2))}
 $('cards').insertAdjacentHTML('beforeend',cards.join(''));
}
