// Sky.js: aircraft, airports/FAA, NASA (FIRMS, EONET, GIBS, POWER, DONKI, NeoWs, ISS), cyber (KEV, NVD, IODA, ISC, abuse.ch).
const Sky={RAW:'https://raw.githubusercontent.com/Churchy156/eugene-sky/live/',L:{},T:{},data:{}};
(function(){const esc=MapX.esc,km=MapX.km,tget=u=>fetch(u,{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null);
const yday=()=>new Date(Date.now()-864e5).toISOString().slice(0,10);
const ago=b=>b?Math.round((Date.now()-Date.parse(b))/6e4)+' min ago':'?';
const fresh=async(name)=>{const [a,b]=await Promise.all([tget(Sky.RAW+'live/'+name+'?t='+Date.now()),tget('data/live/'+name)]);return [a,b].filter(Boolean).sort((x,y)=>String(y.built).localeCompare(String(x.built)))[0]||null};
Sky.map=function(map,LC){const g=n=>Sky.L[n]=L.layerGroup();
 ['🛫 Airports + FAA delays','🔥 Fire hotspots (NASA FIRMS, 24 h)','🌋 Natural events (NASA EONET)','🛰 ISS position','🔐 Internet outages (IODA, 14 d)'].forEach(n=>{g(n);LC.addOverlay(Sky.L[n],n)});
 const gibs=(id,lvl,ext,lab)=>{const l=L.tileLayer(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${id}/default/${yday()}/GoogleMapsCompatible_Level${lvl}/{z}/{y}/{x}.${ext}`,{maxNativeZoom:lvl,maxZoom:18,opacity:.75,attribution:'NASA GIBS'});LC.addOverlay(l,'🛰 NASA '+lab+' ('+yday()+')')};
 gibs('MODIS_Terra_CorrectedReflectance_TrueColor',9,'jpg','MODIS true color');gibs('VIIRS_SNPP_CorrectedReflectance_TrueColor',9,'jpg','VIIRS true color');
 gibs('MODIS_Combined_Value_Added_AOD',6,'png','aerosol (smoke/dust)');gibs('MODIS_Terra_NDSI_Snow_Cover',8,'png','snow cover');gibs('VIIRS_SNPP_DayNightBand_At_Sensor_Radiance',8,'png','night lights');
 Sky.L['🔥 Fire hotspots (NASA FIRMS, 24 h)'].addTo(map);Sky.L['✈️ Live aircraft']=MapX.aircraft(map,LC,$('skyAir'));Sky.L['✈️ Live aircraft'].addTo(map);MapX.sats(map,LC,$('skyAir'));};
Sky.planes=()=>{};
Sky.load=async function(){const {lat,lon}=LOC;Object.entries(Sky.L).forEach(([k,l])=>{if(!/aircraft/.test(k))l.clearLayers()});clearInterval(Sky.T.p);clearInterval(Sky.T.i);clearInterval(Sky.T.f);
 $('skyAirFrame').src=`https://globe.adsb.lol/?lat=${lat.toFixed(3)}&lon=${lon.toFixed(3)}&zoom=9&hideSidebar&hideButtons`;
 Sky.planes();Sky.T.p=setInterval(Sky.planes,20000);
 // airports + FAA
 const [ap,faa]=await Promise.all([Sky.data.ap||tget('data/airports.json'),fresh('faa.json')]);Sky.data.ap=ap;const dl={};(faa?.a||[]).forEach(x=>(dl[x[0]]=dl[x[0]]||[]).push(x));
 (ap||[]).filter(a=>km(lat,lon,a[2],a[3])<250).forEach(a=>{const d=dl[a[0]];L.circleMarker([a[2],a[3]],{radius:a[4]=='l'?7:4,color:d?'#f85149':'#d2a8ff',fillOpacity:.7,weight:1}).bindTooltip(`<b>${esc(a[0])}</b> ${esc(a[1])}${d?'<br>'+d.map(x=>`⚠️ ${esc(x[1])}: ${esc(x[2])} ${esc(x[3])}`).join('<br>'):'<br>no FAA delays'}`).addTo(Sky.L['🛫 Airports + FAA delays'])});
 $('skyFaa').innerHTML=`<b>FAA airport status</b> (${faa?ago(faa.built):'n/a'}): `+((faa?.a||[]).length?faa.a.map(x=>`<div>⚠️ <b>${esc(x[0])}</b> ${esc(x[1])} — ${esc(x[2])} ${esc(x[3])}</div>`).join(''):'no delays or closures nationwide.');
 // FIRMS
 const drawF=async()=>{const f=await fresh('firms.json');const l=Sky.L['🔥 Fire hotspots (NASA FIRMS, 24 h)'];l.clearLayers();if(!f){$('skyFire').textContent='FIRMS hotspots unavailable';return}
  const nr=f.p.filter(p=>km(lat,lon,p[0],p[1])<400);nr.forEach(p=>L.circleMarker([p[0],p[1]],{radius:3+Math.min(6,p[2]/20),color:'#ff7b00',fillColor:'#ffd33d',fillOpacity:.9,weight:1}).bindTooltip(`🔥 ${esc(p[5])} ${esc(p[4])} UTC · FRP ${p[2]} MW · conf ${esc(p[3])}`).addTo(l));
  const n100=nr.filter(p=>km(lat,lon,p[0],p[1])<160).length;$('skyFire').innerHTML=`NASA FIRMS satellite fire detections, last 24 h: <b>${n100}</b> within 100 mi, ${nr.length} within 250 mi, ${f.p.length} US-wide (relay ${ago(f.built)}).`};
 drawF();Sky.T.f=setInterval(drawF,300000);
 // EONET
 tget('https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=60').then(j=>{(j?.events||[]).forEach(e=>{const g=e.geometry[e.geometry.length-1];if(!g||g.type!='Point')return;const [x,y]=g.coordinates;
  L.marker([y,x],{icon:L.divIcon({className:'',html:'<div style="font-size:16px">'+({wildfires:'🔥',severeStorms:'🌀',volcanoes:'🌋',seaLakeIce:'🧊',floods:'🌊',earthquakes:'〰️',landslides:'⛰️',drought:'☀️',dustHaze:'🌫'}[e.categories[0].id]||'❗')+'</div>',iconSize:[16,16]})}).bindTooltip(`<b>${esc(e.title)}</b><br>${esc(e.categories[0].title)} · ${esc(g.date.slice(0,10))}`).addTo(Sky.L['🌋 Natural events (NASA EONET)'])})});
 // ISS
 const iss=async()=>{const j=await tget('https://api.wheretheiss.at/v1/satellites/25544');if(!j)return;const l=Sky.L['🛰 ISS position'];l.clearLayers();
  L.marker([j.latitude,j.longitude],{icon:L.divIcon({className:'',html:'<div style="font-size:22px">🛰</div>',iconSize:[22,22]})}).bindTooltip(`ISS · ${Math.round(j.altitude)} km · ${Math.round(j.velocity)} km/h · ${j.visibility}<br>${Math.round(km(lat,lon,j.latitude,j.longitude))} km from you`).addTo(l);
  $('skyIss').innerHTML=`ISS now: ${j.latitude.toFixed(1)}, ${j.longitude.toFixed(1)} · ${Math.round(km(lat,lon,j.latitude,j.longitude)).toLocaleString()} km away (${j.visibility}).`};iss();Sky.T.i=setInterval(iss,10000);
 // IODA (state centroids)
 const [cy,sc]=await Promise.all([Sky.data.cy||tget('data/cyber_pub.json'),Sky.data.sc||tget('data/state_centroids.json')]);Sky.data.cy=cy;Sky.data.sc=sc;
 const SN={Alabama:'AL',Alaska:'AK',Arizona:'AZ',Arkansas:'AR',California:'CA',Colorado:'CO',Connecticut:'CT',Delaware:'DE',Florida:'FL',Georgia:'GA',Hawaii:'HI',Idaho:'ID',Illinois:'IL',Indiana:'IN',Iowa:'IA',Kansas:'KS',Kentucky:'KY',Louisiana:'LA',Maine:'ME',Maryland:'MD',Massachusetts:'MA',Michigan:'MI',Minnesota:'MN',Mississippi:'MS',Missouri:'MO',Montana:'MT',Nebraska:'NE',Nevada:'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND',Ohio:'OH',Oklahoma:'OK',Oregon:'OR',Pennsylvania:'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD',Tennessee:'TN',Texas:'TX',Utah:'UT',Vermont:'VT',Virginia:'VA',Washington:'WA','West Virginia':'WV',Wisconsin:'WI',Wyoming:'WY','District of Columbia':'DC'};
 const by={};(cy?.ioda_recent||[]).forEach(e=>(by[e[1]]=by[e[1]]||[]).push(e));
 Object.entries(by).forEach(([n,a])=>{const c=sc&&sc[SN[n]];if(!c)return;L.circleMarker(c,{radius:6+Math.min(14,a.length),color:'#d2a8ff',fillColor:'#a371f7',fillOpacity:.5}).bindTooltip(`<b>${esc(n)}</b>: ${a.length} internet outage signal(s), 14 d<br>`+a.slice(0,5).map(e=>`${new Date(e[0]*1e3).toLocaleString()} · ${Math.round(e[2]/60)} min · ${esc(e[3])}`).join('<br>')).addTo(Sky.L['🔐 Internet outages (IODA, 14 d)'])});
 Sky.data.donki=Sky.data.donki||await tget('data/donki.json');
 if(typeof render=='function')render();
};
Sky.render=function(s,D,days){const cy=Sky.data.cy,dk=Sky.data.donki,cards=[];
 if(dk){const w=dk.ev.filter(e=>e[0].slice(0,10)>=s&&e[0].slice(0,10)<=D),c=t=>w.filter(e=>e[1]==t).length,mx=w.filter(e=>e[1]=='FLR'&&/^[MX]/.test(e[2])).length;
  cards.push(`<div class="card"><div class="t">NASA DONKI · ${per}</div><div class="v">${c('CME')} CMEs</div><div class="c">${w.filter(e=>e[1]=='CME'&&e[3]).length} Earth-directed · ${mx} M/X flares · ${c('GST')} storms</div></div>`);
  $('skyDonki').innerHTML=`<b>Space-weather events (NASA/CCMC DONKI, ${s} → ${D})</b>`+(w.length?w.slice(-25).reverse().map(e=>`<div>${e[0].replace('T',' ')} UTC · <b>${e[1]}</b> ${esc(e[2])} ${esc(e[3])} ${e[4]?`<a target=_blank href="${esc(e[4])}">details</a>`:''}</div>`).join(''):'<div>none</div>')+
   `<b>Near-Earth asteroids, next 7 days (NeoWs)</b>`+dk.neo.slice(0,8).map(n=>`<div>${n[0]} · ${esc(n[1])} · ~${n[2]} m · ${n[4]} lunar distances${n[3]?' · ⚠️ potentially hazardous':''}</div>`).join('');
  ch('cDonki','bar',days,[['CMEs',days.map(d=>w.filter(e=>e[1]=='CME'&&e[0].startsWith(d)).length),'#ffa657'],['M/X flares',days.map(d=>w.filter(e=>e[1]=='FLR'&&/^[MX]/.test(e[2])&&e[0].startsWith(d)).length),'#f85149'],['Geomagnetic storms',days.map(d=>w.filter(e=>e[1]=='GST'&&e[0].startsWith(d)).length),'#a371f7']])}
 if(cy){const dd=cy.daily,sum=(k,a,b)=>{let t=0,n=0;for(let d=a;d<=b;d=addD(d,1))if(dd[d]&&dd[d][k]!=null){t+=dd[d][k];n++}return n?t:null};
  const ps=addD(s,-days.length),pe=addD(s,-1),pc=(a,b)=>a==null||b==null||!b?'':` <span class="${a>=b?'up':'dn'}">${a>=b?'▲':'▼'}${Math.abs(a/b*100-100).toFixed(0)}%</span>`;
  [['CISA KEV added','kev'],['Critical CVEs (NVD)','nvd_crit'],['US internet outage signals (IODA)','ioda_us']].forEach(([t,k])=>{const a=sum(k,s,D),b=sum(k,ps,pe);cards.push(`<div class="card"><div class="t">${t} · ${per}</div><div class="v">${a??'—'}</div><div class="c">${a==null?'no data for window':'vs prior '+(b??'—')+pc(a,b)}</div></div>`)});
  ch('cCyber','line',days,[['KEV added',days.map(d=>dd[d]?.kev??(d<iso(new Date())&&d>='2021-11-03'?0:null)),'#f85149'],['Critical CVEs',days.map(d=>dd[d]?.nvd_crit??null),'#ffa657'],['High CVEs',days.map(d=>dd[d]?.nvd_high??null),'#e3b341'],['IODA US outage signals',days.map(d=>dd[d]?.ioda_us??null),'#a371f7'],['SANS ISC attack sources (k)',days.map(d=>dd[d]?.isc_src!=null?Math.round(dd[d].isc_src/1000):null),'#58a6ff',0,'y1']]);
  const fc={};(cy.feodo||[]).forEach(x=>fc[x[3]]=(fc[x[3]]||0)+1);
  $('skyCyber').innerHTML=`SANS Internet Storm Center Infocon: <b style="color:${cy.infocon}">${esc(cy.infocon)}</b> · top attacked ports: ${(cy.topports||[]).slice(0,6).map(p=>p[0]).join(', ')} · CISA KEV total ${cy.kev_total||'?'} · Feodo botnet C2 servers tracked: ${(cy.feodo||[]).length} (${(cy.feodo||[]).filter(x=>x[2]=='online').length} online; by country: ${Object.entries(fc).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,v])=>k+' '+v).join(', ')}) · data ${ago(cy.built)}.
   <br><b>Latest KEV additions</b>${(cy.kev_recent||[]).slice(0,6).map(k=>`<div>${k[0]} · <b>${esc(k[1])}</b> ${esc(k[2])} ${esc(k[3])}${k[5]=='Known'?' · ransomware':''}</div>`).join('')}
   <b>Correlation check</b> (Spearman, daily): ${(cy.corr||[]).filter(c=>/kp|outage/.test(c[1])).map(c=>`${c[0]}↔${c[1].replace('outage_lane_cust_out_peak','Lane outages')}: ${c[2]} (n=${c[3]})`).join(' · ')||'not enough overlap yet'} — values near 0 mean no relationship; cyber activity is driven by people, not space weather.
   <div class="small">Needs free keys to add: Cloudflare Radar (attack/traffic trends, API token), GreyNoise (community key), Shadowserver (registration). BGP hijack feeds (GRIP/BGPStream) have no stable open API.</div>`}
 $('cards').insertAdjacentHTML('beforeend',cards.join(''));
 // NASA POWER irradiance for window (cached per location+window)
 const k=LOC.lat.toFixed(2)+LOC.lon.toFixed(2)+s+D;if(Sky._pw!==k){Sky._pw=k;const e=D>addD(iso(new Date()),-3)?addD(iso(new Date()),-3):D;
  tget(`https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_SFC_UV_INDEX&community=RE&longitude=${LOC.lon}&latitude=${LOC.lat}&start=${s.replace(/-/g,'')}&end=${e.replace(/-/g,'')}&format=JSON`).then(j=>{if(!j)return;const P=j.properties.parameter,f=a=>days.map(d=>{const v=a&&a[d.replace(/-/g,'')];return v==null||v<-900?null:v});
   ch('cPower','line',days,[['All-sky solar kWh/m²/day',f(P.ALLSKY_SFC_SW_DWN),'#e3b341'],['Clear-sky',f(P.CLRSKY_SFC_SW_DWN),'#e3b34155',1],['UV index',f(P.ALLSKY_SFC_UV_INDEX),'#f778ba',0,'y1']])})}
};})();
