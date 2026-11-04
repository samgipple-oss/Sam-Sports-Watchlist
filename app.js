(()=>{'use strict';
const $=id=>document.getElementById(id),TZ='Europe/London';
const TODAY=()=>{const p=new Intl.DateTimeFormat('en-GB',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const v=t=>p.find(x=>x.type===t).value;return `${v('year')}-${v('month')}-${v('day')}`};
const STORE='sports-watchlist-favorites-v1',CACHE='sports-watchlist-live-v3',OLD='sports-watchlist-live-v1';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const addDays=(d,n)=>{const x=new Date(d+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10)};
const uk=(iso,fmt)=>new Intl.DateTimeFormat('en-GB',{timeZone:TZ,...fmt}).format(new Date(iso));
const safeRead=(k,fallback)=>{try{return JSON.parse(localStorage.getItem(k))??fallback}catch{return fallback}};
const normalize=g=>({...g,id:g.id||[g.date,g.time,g.sport,g.title].join('|'),time:g.time||'TBC',service:g.service||'Check broadcaster',source:g.source||'Saved list'});
// Team nicknames normalize seed abbreviations against ESPN's full names.
const NBA_TEAMS=['76ers','Bucks','Bulls','Cavaliers','Celtics','Clippers','Grizzlies','Hawks','Heat','Hornets','Jazz','Kings','Knicks','Lakers','Magic','Mavericks','Nets','Nuggets','Pacers','Pelicans','Pistons','Raptors','Rockets','Spurs','Suns','Thunder','Timberwolves','Trail Blazers','Warriors','Wizards'];
const clean=s=>String(s||'').toLowerCase().replace(/[^a-z0-9 ]/g,'').replace(/\s+/g,' ').trim();
function teamName(s,g){const name=clean(s);if(g.sport==='NBA'){const match=NBA_TEAMS.find(t=>name===clean(t)||name.endsWith(' '+clean(t)));if(match)return clean(match)}return name}
function key(g){const parts=String(g.title||'').split(/\s+at\s+|\s+vs\.?\s+/i);if(parts.length===2)return [g.sport,g.competition||'',g.date,teamName(parts[0],g),teamName(parts[1],g)].join('|');return [g.sport,g.competition||'',g.date,clean(g.title)].join('|')}
// ESPN supplies fixtures, NOT UK TV rights. Only the two services with
// competition-wide access are auto-accepted. All other games require an
// explicit, individually verified broadcast flag in the fixture data.
const ALLOWED=new Set(['bbc iplayer','itvx','disney+','prime','prime video','amazon prime','channel 4','channel 5','5action','netflix','apple tv','league pass','nba league pass']);
const canonical=s=>String(s||'').trim().toLowerCase().replace(/\s+/g,' ');
function watchable(g){
 const competition=canonical(g.competition),sport=canonical(g.sport),service=canonical(g.service);
 if(sport==='nba'&&competition==='nba')return true;
 if(sport==='mls'&&competition==='mls')return true;
 // Verified is intentionally strict: a service label or a provisional seed
 // entry alone is NOT proof that the match is available to watch in the UK.
 const verified=g.broadcastVerified===true||g.ukBroadcastVerified===true;
 return verified&&ALLOWED.has(service);
}
let seed=[],live=[],view='upcoming',sport='All',service='All',query='',date=TODAY(),favorites=new Set(safeRead(STORE,[])),lastRefresh=0,updating=false;
function allGames(){
 const m=new Map();
 seed.forEach(g=>{g=normalize(g);m.set(key(g),g)});
 live.forEach(g=>{g=normalize(g);const k=key(g),old=m.get(k);
  // Prefer the live event's schedule, but never transfer an unverified
  // broadcaster label from the seed into an ESPN event as proof of rights.
  m.set(k,old?{...old,...g,priority:old.priority||g.priority,service:g.service,source:'Live fixture feed',broadcastVerified:g.broadcastVerified===true||g.ukBroadcastVerified===true}:g);
 });
 return [...m.values()].filter(watchable).map(g=>{
  if(canonical(g.sport)==='nba'&&canonical(g.competition)==='nba')return {...g,service:'League Pass'};
  if(canonical(g.sport)==='mls'&&canonical(g.competition)==='mls')return {...g,service:'Apple TV'};
  return g;
 }).sort((a,b)=>a.date.localeCompare(b.date)||(a.time==='TBC'?1:b.time==='TBC'?-1:a.time.localeCompare(b.time))||a.title.localeCompare(b.title));
}
function chips(id,values,current,cb){$(id).innerHTML=values.map(v=>`<button class="chip ${v===current?'active':''}" data-v="${escape(v)}">${escape(v)}</button>`).join('');$(id).querySelectorAll('button').forEach(b=>b.onclick=()=>{cb(b.dataset.v);render()})}
function render(){
 const games=allGames();
 const sports=['All',...new Set(games.map(g=>g.sport))];
 const services=['All',...new Set(games.map(g=>g.service))];
 if(!sports.includes(sport))sport='All';if(!services.includes(service))service='All';
 chips('sports',sports,sport,v=>sport=v);chips('services',services,service,v=>service=v);
 $('date').value=date;document.querySelectorAll('#views button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 const list=games.filter(g=>(sport==='All'||g.sport===sport)&&(service==='All'||g.service===service)&&(!query||(g.title+' '+g.sport+' '+(g.competition||'')+' '+g.service).toLowerCase().includes(query))&&(view!=='faves'||favorites.has(g.id))&&(view!=='upcoming'||(g.date>=date&&g.date<addDays(date,30))));
 $('gameCount').textContent=list.length;$('dayCount').textContent=new Set(list.map(g=>g.date)).size;$('favCount').textContent=favorites.size;
 const groups=list.reduce((o,g)=>((o[g.date]??=[]).push(g),o),{});
 $('results').innerHTML=list.length?Object.entries(groups).map(([d,gs])=>`<section class="day"><div class="dayhead"><strong>${escape(uk(d+'T12:00:00Z',{weekday:'long',day:'numeric',month:'long'}))}</strong><span>${gs.length} fixture${gs.length===1?'':'s'}</span></div>${gs.map(g=>`<div class="game"><div class="time">${escape(g.time)}</div><div><div class="match">${g.priority?'★ ':''}${escape(g.title)}</div><div class="meta">${escape(g.sport)} · ${escape(g.competition||'')} · ${escape(g.service)}${g.liveStatus?' · '+escape(g.liveStatus):''}</div></div><button class="star ${favorites.has(g.id)?'on':''}" data-id="${escape(g.id)}" aria-label="Save fixture">${favorites.has(g.id)?'★':'☆'}</button></div>`).join('')}</section>`).join(''):'<div class="empty">No watchable fixtures found for these filters or dates. Unverified UK broadcasts are hidden.</div>';
 $('results').querySelectorAll('.star').forEach(b=>b.onclick=()=>{favorites.has(b.dataset.id)?favorites.delete(b.dataset.id):favorites.add(b.dataset.id);localStorage.setItem(STORE,JSON.stringify([...favorites]));render()});
}
async function refresh(){
 if(updating)return;updating=true;const b=$('refresh');b.disabled=true;b.textContent='↻ Checking…';
 try{
  const response=await fetch('./live-fixtures.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);
  const data=await response.json();if(!Array.isArray(data.items))throw Error('Missing fixture list');
  live=data.items.map(normalize);const at=data.updatedAt||new Date().toISOString();localStorage.setItem(CACHE,JSON.stringify({at,items:live}));lastRefresh=Date.now();
  const n=data.successfulChecks??0,total=data.totalChecks??0;
  $('status').textContent=`Server checked ${new Date(at).toLocaleString('en-GB',{timeZone:TZ})} · ${n}/${total} feed checks successful${n<total?' · partial coverage':''} · only watchable fixtures shown`;
 }catch(e){$('status').textContent=live.length?'Could not reach server update. Showing cached watchable fixtures.':'No live schedule available yet. Run the GitHub Actions update once.'}
 updating=false;b.disabled=false;b.textContent='↻ Refresh';render();
}
async function init(){
 date=TODAY();$('date').value=date;$('date').onchange=e=>{date=e.target.value;render()};$('prev').onclick=()=>{date=addDays(date,-1);render()};$('next').onclick=()=>{date=addDays(date,1);render()};$('reset').onclick=()=>{date=TODAY();render()};$('search').oninput=e=>{query=e.target.value.toLowerCase().trim();render()};document.querySelectorAll('#views button').forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});$('refresh').onclick=refresh;
 try{const r=await fetch('./seed.json?v=4',{cache:'no-store'});if(!r.ok)throw Error();const data=await r.json();seed=Array.isArray(data)?data.map(normalize):[]}catch{$('status').textContent='Saved fixture list could not be loaded.'}
 const cached=safeRead(CACHE,null)||safeRead(OLD,null);if(cached?.items&&Array.isArray(cached.items)){live=cached.items.map(normalize);lastRefresh=new Date(cached.at).getTime()||0;$('status').textContent=`Cached fixtures from ${new Date(cached.at).toLocaleString('en-GB',{timeZone:TZ})} · only watchable fixtures shown`}
 render();refresh();document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(date===addDays(TODAY(),-1))date=TODAY();render();if(Date.now()-lastRefresh>15*60*1000)refresh()}});setInterval(()=>{if(!document.hidden&&Date.now()-lastRefresh>15*60*1000)refresh()},5*60*1000);if('serviceWorker'in navigator&&location.protocol==='https:')navigator.serviceWorker.register('./sw.js').catch(()=>{});
}
init();})();
