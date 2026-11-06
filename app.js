
(()=>{
'use strict';

const $=id=>document.getElementById(id);
const TZ='Europe/London';

const TODAY=()=>{
  const p=new Intl.DateTimeFormat('en-GB',{
    timeZone:TZ,
    year:'numeric',
    month:'2-digit',
    day:'2-digit'
  }).formatToParts(new Date());
  const v=t=>p.find(x=>x.type===t).value;
  return `${v('year')}-${v('month')}-${v('day')}`;
};

const STORE='sports-watchlist-favorites-v1';
const CACHE='sports-watchlist-live-v3';
const OLD='sports-watchlist-live-v1';

const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({
  '&':'&amp;',
  '<':'&lt;',
  '>':'&gt;',
  '"':'&quot;',
  "'":'&#39;'
}[c]));

const addDays=(d,n)=>{
  const x=new Date(d+'T12:00:00Z');
  x.setUTCDate(x.getUTCDate()+n);
  return x.toISOString().slice(0,10);
};

const uk=(iso,fmt)=>new Intl.DateTimeFormat('en-GB',{
  timeZone:TZ,
  ...fmt
}).format(new Date(iso));

const safeRead=(k,fallback)=>{
  try{
    return JSON.parse(localStorage.getItem(k))??fallback;
  }catch{
    return fallback;
  }
};

const normalize=g=>({
  ...g,
  id:g.id||[g.date,g.time,g.sport,g.title].join('|'),
  time:g.time||'TBC',
  service:g.service||'Check broadcaster',
  source:g.source||'Saved list'
});

const NBA_TEAMS=[
  '76ers','Bucks','Bulls','Cavaliers','Celtics',
  'Clippers','Grizzlies','Hawks','Heat','Hornets',
  'Jazz','Kings','Knicks','Lakers','Magic',
  'Mavericks','Nets','Nuggets','Pacers','Pelicans',
  'Pistons','Raptors','Rockets','Spurs','Suns',
  'Thunder','Timberwolves','Trail Blazers',
  'Warriors','Wizards'
];

const clean=s=>String(s||'')
  .toLowerCase()
  .replace(/[^a-z0-9 ]/g,'')
  .replace(/\s+/g,' ')
  .trim();

function teamName(s,g){
  const name=clean(s);
  if(g.sport==='NBA'){
    const match=NBA_TEAMS.find(
      t=>name===clean(t)||name.endsWith(' '+clean(t))
    );
    if(match)return clean(match);
  }
  return name;
}

function key(g){
  const parts=String(g.title||'')
    .split(/\s+at\s+|\s+vs\.?\s+/i);

  if(parts.length===2){
    return [
      g.sport,
      g.competition||'',
      g.date,
      teamName(parts[0],g),
      teamName(parts[1],g)
    ].join('|');
  }

  return [
    g.sport,
    g.competition||'',
    g.date,
    clean(g.title)
  ].join('|');
}

const ALLOWED=new Set([
  'bbc iplayer','itvx','disney+',
  'prime','prime video','amazon prime',
  'channel 4','channel 5','5action',
  'netflix','apple tv',
  'league pass','nba league pass'
]);

const canonical=s=>String(s||'')
  .trim()
  .toLowerCase()
  .replace(/\s+/g,' ');

function watchable(g){
  const competition=canonical(g.competition);
  const sport=canonical(g.sport);
  const service=canonical(g.service);

  if(sport==='nba'&&competition==='nba')return true;
  if(sport==='mls'&&competition==='mls')return true;
  if(sport==='mlb'&&competition==='mlb')return true;

  const verified=
    g.broadcastVerified===true||
    g.ukBroadcastVerified===true;

  return verified&&ALLOWED.has(service);
}

const GENDER_STORE='sports-watchlist-gender-filter-v1';

let genderFilter=safeRead(GENDER_STORE,'all');

if(!['all','men','women'].includes(genderFilter)){
  genderFilter='all';
}

function eventGender(g){
  const competition=canonical(g.competition);
  const title=canonical(g.title);
  const sport=canonical(g.sport);

  if(/\b(women|womens|women's|female|ladies|girls|wsl|nwsl|uwcl|wnba|wta)\b/.test(competition+' '+title)){
    return 'women';
  }

  if(/\b(men|mens|men's|male|boys)\b/.test(competition)){
    return 'men';
  }

  if(['nba','nfl','mls','mlb'].includes(sport)){
    return 'men';
  }

  if([
    'premier league',
    'champions league',
    'uefa nations league',
    'nations championship',
    'nations championship finals'
  ].includes(competition)){
    return 'men';
  }

  return 'unknown';
}

const FAVORITES_V2='sports-watchlist-favorites-v2';
const favoriteKey=g=>key(g);

let seed=[];
let live=[];
let view='upcoming';
let sport='All';
let service='All';
let query='';
let date=TODAY();

let favorites=new Set(safeRead(FAVORITES_V2,[]));
let legacyFavorites=new Set(safeRead(STORE,[]));

let lastRefresh=0;
let updating=false;

const EXCLUDE_STORE='sports-watchlist-excluded-sports-v1';

let excludedSports=new Set(safeRead(EXCLUDE_STORE,[]));
let excludeMode=false;

const saveExcluded=()=>localStorage.setItem(
  EXCLUDE_STORE,
  JSON.stringify([...excludedSports])
);

/* EXISTING FIXTURE HANDLING */

function allGames(){
  const m=new Map();

  seed.forEach(g=>{
    g=normalize(g);
    m.set(key(g),g);
  });

  live.forEach(g=>{
    g=normalize(g);

    const k=key(g);
    const old=m.get(k);

    m.set(k,old?{
      ...old,
      ...g,
      priority:old.priority||g.priority,
      service:g.service,
      source:'Live fixture feed',
      broadcastVerified:
        g.broadcastVerified===true||
        g.ukBroadcastVerified===true
    }:g);
  });

  return [...m.values()]
    .filter(watchable)
    .map(g=>{
      if(
        canonical(g.sport)==='nba'&&
        canonical(g.competition)==='nba'
      ){
        return {...g,service:'League Pass'};
      }

      if(
        canonical(g.sport)==='mls'&&
        canonical(g.competition)==='mls'
      ){
        return {...g,service:'Apple TV'};
      }

      if(
        canonical(g.sport)==='mlb'&&
        canonical(g.competition)==='mlb'
      ){
        return {...g,service:'MLB.TV'};
      }

      return g;
    })
    .sort((a,b)=>
      a.date.localeCompare(b.date)||
      (
        a.time==='TBC'?1:
        b.time==='TBC'?-1:
        a.time.localeCompare(b.time)
      )||
      a.title.localeCompare(b.title)
    );
}

function chips(id,values,current,cb){
  $(id).innerHTML=values.map(v=>`
    <button
      class="chip ${v===current?'active':''}"
      data-v="${escape(v)}">
      ${escape(v)}
    </button>
  `).join('');

  $(id).querySelectorAll('button').forEach(b=>{
    b.onclick=()=>{
      cb(b.dataset.v);
      render();
    };
  });
}

function render(){
  const games=allGames();

  let migrated=false;

  for(const g of games){
    if(legacyFavorites.has(g.id)){
      favorites.add(favoriteKey(g));
      legacyFavorites.delete(g.id);
      migrated=true;
    }
  }

  if(migrated){
    localStorage.setItem(
      FAVORITES_V2,
      JSON.stringify([...favorites])
    );

    localStorage.setItem(
      STORE,
      JSON.stringify([...legacyFavorites])
    );
  }

  const sports=[
    'All',
    ...new Set(games.map(g=>g.sport))
  ];

  const services=[
    'All',
    ...new Set(games.map(g=>g.service))
  ];

  if(!sports.includes(sport))sport='All';
  if(!services.includes(service))service='All';

  const sportsBox=$('sports');

  sportsBox.innerHTML=`
    <div style="width:100%;display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:9px">
      <button
        id="sportMode"
        class="chip ${excludeMode?'active':''}"
        type="button"
        aria-pressed="${excludeMode}">
        ${excludeMode?'✓ Exclude sports':'⊖ Exclude sports'}
      </button>

      ${excludeMode?`
        <button id="clearExcluded" class="chip" type="button">
          Clear exclusions
        </button>
        <span style="font-size:12px;opacity:.8">
          Select sports to hide
        </span>
      `:''}
    </div>
  `+sports.map(v=>`
    <button
      class="chip ${
        excludeMode
          ?(excludedSports.has(v)?'active':'')
          :(v===sport?'active':'')
      }"
      data-v="${escape(v)}"
      type="button"
      aria-pressed="${
        excludeMode?excludedSports.has(v):v===sport
      }">
      ${excludeMode&&excludedSports.has(v)?'✕ ':''}${escape(v)}
    </button>
  `).join('');

  $('sportMode').onclick=()=>{
    excludeMode=!excludeMode;
    render();
  };

  if(excludeMode){
    $('clearExcluded').onclick=()=>{
      excludedSports.clear();
      saveExcluded();
      render();
    };
  }

  sportsBox.querySelectorAll('button[data-v]').forEach(b=>{
    b.onclick=()=>{
      const v=b.dataset.v;

      if(excludeMode){
        if(v==='All'){
          excludedSports.clear();
        }else if(excludedSports.has(v)){
          excludedSports.delete(v);
        }else{
          excludedSports.add(v);
        }
        saveExcluded();
      }else{
        sport=v;
      }

      render();
    };
  });

  let genderBox=$('genderFilters');

  if(!genderBox){
    genderBox=document.createElement('div');
    genderBox.id='genderFilters';
    genderBox.style.cssText=
      'display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0';

    $('sports').insertAdjacentElement(
      'afterend',
      genderBox
    );
  }

  genderBox.innerHTML=`
    <span style="font-size:12px;opacity:.8;margin-right:3px">
      Competition
    </span>
  `+[
    ['all','All'],
    ['men',"Men’s only"],
    ['women',"Women’s only"]
  ].map(([v,label])=>`
    <button
      type="button"
      class="chip ${genderFilter===v?'active':''}"
      data-gender="${v}"
      aria-pressed="${genderFilter===v}">
      ${label}
    </button>
  `).join('');

  genderBox.querySelectorAll('button').forEach(b=>{
    b.onclick=()=>{
      genderFilter=b.dataset.gender;

      localStorage.setItem(
        GENDER_STORE,
        JSON.stringify(genderFilter)
      );

      render();
    };
  });

  chips(
    'services',
    services,
    service,
    v=>service=v
  );

  $('date').value=date;

  document.querySelectorAll('#views button').forEach(
    b=>b.classList.toggle(
      'active',
      b.dataset.view===view
    )
  );

  const list=games.filter(g=>
    (
      genderFilter==='all'||
      eventGender(g)===genderFilter
    )&&
    (
      excludeMode
        ?!excludedSports.has(g.sport)
        :(sport==='All'||g.sport===sport)
    )&&
    (service==='All'||g.service===service)&&
    (
      !query||
      (
        g.title+' '+
        g.sport+' '+
        (g.competition||'')+' '+
        g.service
      ).toLowerCase().includes(query)
    )&&
    (
      view!=='faves'||
      favorites.has(favoriteKey(g))
    )&&
    (
      view!=='upcoming'||
      (
        g.date>=date&&
        g.date<addDays(date,30)
      )
    )
  );

  $('gameCount').textContent=list.length;

  $('dayCount').textContent=
    new Set(list.map(g=>g.date)).size;

  $('favCount').textContent=
    favorites.size+legacyFavorites.size;

  const groups=list.reduce(
    (o,g)=>((o[g.date]??=[]).push(g),o),
    {}
  );

  $('results').innerHTML=list.length
    ?Object.entries(groups).map(([d,gs])=>`
      <section class="day">
        <div class="dayhead">
          <strong>
            ${escape(uk(d+'T12:00:00Z',{
              weekday:'long',
              day:'numeric',
              month:'long'
            }))}
          </strong>
          <span>
            ${gs.length} fixture${gs.length===1?'':'s'}
          </span>
        </div>

        ${gs.map(g=>`
          <div class="game">
            <div class="time">
              ${escape(g.time)}
            </div>

            <div>
              <div class="match">
                ${g.priority?'★ ':''}${escape(g.title)}
              </div>

              <div class="meta">
                ${escape(g.sport)}
                · ${escape(g.competition||'')}
                · ${escape(g.service)}
                ${g.liveStatus
                  ?' · '+escape(g.liveStatus)
                  :''}
              </div>
            </div>

            <button
              class="star ${
                favorites.has(favoriteKey(g))
                  ?'on'
                  :''
              }"
              data-id="${escape(favoriteKey(g))}"
              aria-label="Save fixture">
              ${
                favorites.has(favoriteKey(g))
                  ?'★'
                  :'☆'
              }
            </button>
          </div>
        `).join('')}
      </section>
    `).join('')
    :`
      <div class="empty">
        No watchable fixtures found for these filters
        or dates. Unverified UK broadcasts are hidden.
      </div>
    `;

  $('results').querySelectorAll('.star').forEach(b=>{
    b.onclick=()=>{
      if(favorites.has(b.dataset.id)){
        favorites.delete(b.dataset.id);
      }else{
        favorites.add(b.dataset.id);
      }

      localStorage.setItem(
        FAVORITES_V2,
        JSON.stringify([...favorites])
      );

      render();
    };
  });
}

/* LIVE UPDATES */

async function refresh(){
  if(updating)return;

  updating=true;

  const b=$('refresh');
  b.disabled=true;
  b.textContent='↻ Checking…';

  try{
    const response=await fetch(
      './live-fixtures.json?t='+Date.now(),
      {cache:'no-store'}
    );

    if(!response.ok){
      throw Error('HTTP '+response.status);
    }

    const data=await response.json();

    if(!Array.isArray(data.items)){
      throw Error('Missing fixture list');
    }

    live=data.items.map(normalize);

    const at=data.updatedAt||new Date().toISOString();

    localStorage.setItem(
      CACHE,
      JSON.stringify({at,items:live})
    );

    lastRefresh=Date.now();

    const n=data.successfulChecks??0;
    const total=data.totalChecks??0;

    $('status').textContent=
      `Server checked ${
        new Date(at).toLocaleString('en-GB',{
          timeZone:TZ
        })
      } · ${n}/${total} feed checks successful${
        n<total?' · partial coverage':''
      } · only watchable fixtures shown`;

  }catch(e){
    $('status').textContent=live.length
      ?'Could not reach server update. Showing cached watchable fixtures.'
      :'No live schedule available yet. Run the GitHub Actions update once.';
  }

  updating=false;
  b.disabled=false;
  b.textContent='↻ Refresh';

  render();
}

/* ORIGINAL APP INITIALISATION */

async function init(){
  date=TODAY();
  $('date').value=date;

  $('date').onchange=e=>{
    date=e.target.value;
    render();
  };

  $('prev').onclick=()=>{
    date=addDays(date,-1);
    render();
  };

  $('next').onclick=()=>{
    date=addDays(date,1);
    render();
  };

  $('reset').onclick=()=>{
    date=TODAY();
    render();
  };

  $('search').oninput=e=>{
    query=e.target.value.toLowerCase().trim();
    render();
  };

  document.querySelectorAll('#views button').forEach(b=>{
    b.onclick=()=>{
      view=b.dataset.view;
      render();
    };
  });

  $('refresh').onclick=refresh;

  try{
    const r=await fetch(
      './seed.json?v=4',
      {cache:'no-store'}
    );

    if(!r.ok)throw Error();

    const data=await r.json();

    seed=Array.isArray(data)
      ?data.map(normalize)
      :[];

  }catch{
    $('status').textContent=
      'Saved fixture list could not be loaded.';
  }

  const cached=
    safeRead(CACHE,null)||
    safeRead(OLD,null);

  if(cached?.items&&Array.isArray(cached.items)){
    live=cached.items.map(normalize);

    lastRefresh=
      new Date(cached.at).getTime()||0;

    $('status').textContent=
      `Cached fixtures from ${
        new Date(cached.at).toLocaleString('en-GB',{
          timeZone:TZ
        })
      } · only watchable fixtures shown`;
  }

  render();
  refresh();

  document.addEventListener(
    'visibilitychange',
    ()=>{
      if(!document.hidden){
        if(date===addDays(TODAY(),-1)){
          date=TODAY();
        }

        render();

        if(Date.now()-lastRefresh>15*60*1000){
          refresh();
        }
      }
    }
  );

  setInterval(()=>{
    if(
      !document.hidden&&
      Date.now()-lastRefresh>15*60*1000
    ){
      refresh();
    }
  },5*60*1000);

  if(
    'serviceWorker' in navigator&&
    location.protocol==='https:'
  ){
    navigator.serviceWorker
      .register('./sw.js')
      .catch(()=>{});
  }
}

/* NEW MOBILE BOTTOM NAVIGATION */

function installMobileDock(){
  if(document.getElementById('sportsMobileDock')){
    return;
  }

  const style=document.createElement('style');

  style.textContent=`
    .sports-mobile-dock {
      display:none;
    }

    @media(max-width:700px) {
      .shell {
        padding-bottom:max(
          110px,
          calc(env(safe-area-inset-bottom,0px) + 88px)
        )!important;
      }

      .sports-mobile-dock {
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:5px;
        position:fixed;
        z-index:200;
        bottom:0;
        left:0;
        right:0;
        padding:
          8px 10px
          max(9px,env(safe-area-inset-bottom,0px));
        background:linear-gradient(
          180deg,
          #621723,
          #28070e 90%
        );
        border-top:2px solid #e5b16d;
        box-shadow:0 -10px 28px #120207bd;
      }

      .sports-mobile-dock button {
        display:flex;
        flex-direction:column;
        justify-content:center;
        align-items:center;
        gap:4px;
        min-height:54px;
        min-width:0;
        padding:5px 2px;
        border:1px solid transparent;
        border-radius:12px;
        background:none;
        color:#d9b59b;
        font:700 11px/1.2 Arial,sans-serif;
      }

      .sports-mobile-dock button[aria-current=page] {
        background:linear-gradient(
          #af2736,
          #72111e
        );
        border-color:#e4af6f;
        color:#ffedc6;
      }

      .sports-mobile-dock svg {
        width:23px;
        height:23px;
        stroke:currentColor;
        stroke-width:1.8;
        stroke-linecap:round;
        stroke-linejoin:round;
        fill:none;
      }

      /* Saved is now in the dock on mobile. */
      #views button[data-view=faves] {
        display:none;
      }

      #views {
        grid-template-columns:
          repeat(2,minmax(0,1fr));
      }
    }
  `;

  document.head.append(style);

  const dock=document.createElement('nav');
  dock.id='sportsMobileDock';
  dock.className='sports-mobile-dock';

  dock.setAttribute(
    'aria-label',
    'Quick navigation'
  );

  dock.innerHTML=`
    <button
      type="button"
      data-dock="schedule"
      aria-current="page"
      aria-label="Upcoming schedule">

      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3" y="5" width="18" height="16" rx="2"/>
        <path d="M7 3v4M17 3v4M3 10h18M8 14h3M8 18h3"/>
      </svg>

      <span>Schedule</span>
    </button>

    <button
      type="button"
      data-dock="saved"
      aria-label="Saved fixtures">

      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 4h12v17l-6-4-6 4z"/>
      </svg>

      <span>Saved</span>
    </button>

    <button
      type="button"
      data-dock="today"
      aria-label="Today's schedule">

      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9"/>
        <path d="M12 7v5l3 2"/>
      </svg>

      <span>Today</span>
    </button>

    <button
      type="button"
      data-dock="filters"
      aria-label="Sport and service filters">

      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16"/>
        <circle cx="9" cy="7" r="2" fill="#4a1020"/>
        <circle cx="16" cy="12" r="2" fill="#4a1020"/>
        <circle cx="11" cy="17" r="2" fill="#4a1020"/>
      </svg>

      <span>Filters</span>
    </button>
  `;

  document.body.append(dock);

  function mark(name){
    dock.querySelectorAll('button').forEach(b=>{
      if(b.dataset.dock===name){
        b.setAttribute('aria-current','page');
      }else{
        b.removeAttribute('aria-current');
      }
    });
  }

  function scrollToElement(el){
    el?.scrollIntoView({
      behavior:'smooth',
      block:'start'
    });
  }

  dock.addEventListener('click',event=>{
    const b=event.target.closest(
      'button[data-dock]'
    );

    if(!b)return;

    switch(b.dataset.dock){

      case 'schedule':
        view='upcoming';
        mark('schedule');
        render();
        scrollToElement($('results'));
        break;

      case 'saved':
        view='faves';
        mark('saved');
        render();
        scrollToElement($('results'));
        break;

      case 'today':
        date=TODAY();
        view='upcoming';
        mark('today');
        render();
        scrollToElement($('results'));
        break;

      case 'filters':{
        const panel=$('sportPanel');

        if(
          panel&&
          !panel.classList.contains('open')
        ){
          $('sportToggle')?.click();
        }

        mark('filters');
        scrollToElement(
          $('sportToggle')||$('sports')
        );
        break;
      }
    }
  });

  document.querySelectorAll(
    '#views button'
  ).forEach(b=>{
    b.addEventListener('click',()=>{
      mark(
        b.dataset.view==='faves'
          ?'saved'
          :'schedule'
      );
    });
  });

  $('sportToggle')?.addEventListener(
    'click',
    ()=>mark('filters')
  );

  $('serviceToggle')?.addEventListener(
    'click',
    ()=>mark('filters')
  );
}

/* START APP */

installMobileDock();
init();

})();
