(()=>{'use strict';
const $=id=>document.getElementById(id),TZ='Europe/London',TODAY=()=>new Intl.DateTimeFormat('en-CA',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const STORE='sports-watchlist-favorites-v1',CACHE='sports-watchlist-live-v3',OLD='sports-watchlist-live-v1';
const FEEDS=[['NBA','NBA','basketball/nba'],['NFL','NFL','football/nfl'],['MLS','MLS','soccer/usa.1'],['Football','Champions League','soccer/uefa.champions'],['Football','Premier League','soccer/eng.1'],['Football','WSL','soccer/eng.w.1'],['Football','Women’s Champions League','soccer/uefa.wchampions'],['Rugby','Rugby Union','rugby/164']];
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const addDays=(d,n)=>{const x=new Date(d+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10)};
const uk=(iso,fmt)=>new Intl.DateTimeFormat('en-GB',{timeZone:TZ,...fmt}).format(new Date(iso));
const isoDate=iso=>{const p=new Intl.DateTimeFormat('en-GB',{timeZone:TZ,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(iso));const f=t=>p.find(x=>x.type===t).value;return `${f('year')}-${f('month')}-${f('day')}`};
const safeRead=(k,fallback)=>{try{return JSON.parse(localStorage.getItem(k))??fallback}catch{return fallback}};
let seed=[],live=[],view='upcoming',sport='All',service='All',query='',date=TODAY(),favorites=new Set(safeRead(STORE,[])),lastRefresh=0,updating=false;
function normalize(g){return {...g,id:g.id||[g.date,g.time,g.sport,g.title].join('|'),time:g.time||'TBC',service:g.service||'Check broadcaster',source:g.source||'Saved list'}}
function key(g){return [g.sport,g.date,g.title.toLowerCase().replace(/[^a-z0-9]/g,'')].join('|')}
function allGames(){const m=new Map();seed.forEach(g=>m.set(key(g),normalize(g)));live.forEach(g=>{const k=key(g),old=m.get(k);m.set(k,old?{...old,time:g.time,liveStatus:g.liveStatus,source:'Live fixture feed'}:normalize(g))});return [...m.values()].sort((a,b)=>a.date.localeCompare(b.date)||(a.time==='TBC'?1:b.time==='TBC'?-1:a.time.localeCompare(b.time))||a.title.localeCompare(b.title))}
function chips(id,values,current,cb){$(id).innerHTML=values.map(v=>`<button class="chip ${v===current?'active':''}" data-v="${escape(v)}">${escape(v)}</button>`).join('');$(id).querySelectorAll('button').forEach(b=>b.onclick=()=>{cb(b.dataset.v);render()})}
function render(){const games=allGames();chips('sports',['All',...new Set(games.map(g=>g.sport))],sport,v=>sport=v);chips('services',['All','League Pass','Apple TV','BBC iPlayer','ITVX','Disney+','Prime','Channel 5','Check broadcaster'],service,v=>service=v);$('date').value=date;document.querySelectorAll('#views button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));let list=games.filter(g=>(sport==='All'||g.sport===sport)&&(service==='All'||g.service.toLowerCase().includes(service.toLowerCase()))&&(!query||(g.title+' '+g.sport+' '+(g.competition||'')+' '+g.service).toLowerCase().includes(query))&&(view!=='faves'||favorites.has(g.id))&&(view!=='upcoming'||(g.date>=date&&g.date<addDays(date,30))));$('gameCount').textContent=list.length;$('dayCount').textContent=new Set(list.map(g=>g.date)).size;$('favCount').textContent=favorites.size;const groups=list.reduce((o,g)=>((o[g.date]??=[]).push(g),o),{});$('results').innerHTML=list.length?Object.entries(groups).map(([d,gs])=>`<section class="day"><div class="dayhead"><strong>${escape(uk(d+'T12:00:00Z',{weekday:'long',day:'numeric',month:'long'}))}</strong><span>${gs.length} fixture${gs.length===1?'':'s'}</span></div>${gs.map(g=>`<div class="game"><div class="time">${escape(g.time)}</div><div><div class="match">${g.priority?'★ ':''}${escape(g.title)}</div><div class="meta">${escape(g.sport)} · ${escape(g.competition||'')} · ${escape(g.service)}${g.source==='Saved list'?'<span class="provisional"> · provisional</span>':''}${g.liveStatus?' · '+escape(g.liveStatus):''}</div></div><button class="star ${favorites.has(g.id)?'on':''}" data-id="${escape(g.id)}" aria-label="Save fixture">${favorites.has(g.id)?'★':'☆'}</button></div>`).join('')}</section>`).join(''):'<div class="empty">No fixtures found. Free feeds may not cover this competition or date. Try Refresh or a different filter.</div>';$('results').querySelectorAll('.star').forEach(b=>b.onclick=()=>{favorites.has(b.dataset.id)?favorites.delete(b.dataset.id):favorites.add(b.dataset.id);localStorage.setItem(STORE,JSON.stringify([...favorites]));render()})}
async function refresh(){
 if(updating)return;updating=true;
 const b=$('refresh');b.disabled=true;b.textContent='↻ Checking…';
 try{
  const response=await fetch('./live-fixtures.json?t='+Date.now(),{cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const data=await response.json();
  if(!Array.isArray(data.items))throw Error('Missing fixture list');
  live=data.items.map(normalize);
  const at=data.updatedAt||new Date().toISOString();
  localStorage.setItem(CACHE,JSON.stringify({at,items:live}));
  lastRefresh=Date.now();
  const n=data.successfulChecks??0,total=data.totalChecks??0;
  $('status').textContent=`Server checked ${new Date(at).toLocaleString('en-GB',{timeZone:TZ})} · ${n}/${total} feeds successful${n<total?' · partial coverage':''}`;
 }catch(e){$('status').textContent=live.length?'Could not reach server update. Showing saved fixtures.':'No live schedule available yet. Run the GitHub Actions update once.'}
 updating=false;b.disabled=false;b.textContent='↻ Refresh';render();
}
async function init(){date=TODAY();$('date').value=date;$('date').onchange=e=>{date=e.target.value;render()};$('prev').onclick=()=>{date=addDays(date,-1);render()};$('next').onclick=()=>{date=addDays(date,1);render()};$('reset').onclick=()=>{date=TODAY();render()};$('search').oninput=e=>{query=e.target.value.toLowerCase().trim();render()};document.querySelectorAll('#views button').forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});$('refresh').onclick=refresh;
try{const r=await fetch('./seed.json?v=4',{cache:'no-store'});if(!r.ok)throw Error();seed=(await r.json()).map(normalize)}catch{$('status').textContent='Saved fixture list could not be loaded.'}
const cached=safeRead(CACHE,null)||safeRead(OLD,null);if(cached?.items){live=cached.items;lastRefresh=new Date(cached.at).getTime()||0;$('status').textContent=`Last successful update: ${new Date(cached.at).toLocaleString('en-GB',{timeZone:TZ})}`}
render();refresh();document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(date===addDays(TODAY(),-1))date=TODAY();render();if(Date.now()-lastRefresh>15*60*1000)refresh()}});setInterval(()=>{if(!document.hidden&&Date.now()-lastRefresh>15*60*1000)refresh()},5*60*1000);if('serviceWorker'in navigator&&location.protocol==='https:')navigator.serviceWorker.register('./sw.js').catch(()=>{})}
init();})();
