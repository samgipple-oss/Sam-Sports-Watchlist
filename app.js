
(() => {
'use strict';

const $ = id => document.getElementById(id);
const TZ = 'Europe/London';

const TODAY = () => {
  const p = new Intl.DateTimeFormat('en-GB', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date());

  const v = t => p.find(x => x.type === t).value;
  return `${v('year')}-${v('month')}-${v('day')}`;
};

const STORE = 'sports-watchlist-favorites-v1';
const CACHE = 'sports-watchlist-live-v3';
const OLD = 'sports-watchlist-live-v1';
const FAVORITES_V2 = 'sports-watchlist-favorites-v2';
const GENDER_STORE = 'sports-watchlist-gender-filter-v1';
const EXCLUDE_STORE = 'sports-watchlist-excluded-sports-v1';

const escape = s =>
  String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c]));

const addDays = (d, n) => {
  const x = new Date(d + 'T12:00:00Z');
  x.setUTCDate(x.getUTCDate() + n);
  return x.toISOString().slice(0, 10);
};

const uk = (iso, fmt) =>
  new Intl.DateTimeFormat('en-GB', {
    timeZone: TZ,
    ...fmt
  }).format(new Date(iso));

const safeRead = (k, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(k)) ?? fallback;
  } catch {
    return fallback;
  }
};

const normalize = g => ({
  ...g,
  id: g.id || [g.date, g.time, g.sport, g.title].join('|'),
  time: g.time || 'TBC',
  service: g.service || 'Check broadcaster',
  source: g.source || 'Saved list'
});

const canonical = s =>
  String(s || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');

const clean = s =>
  String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const NBA_TEAMS = [
  '76ers', 'Bucks', 'Bulls', 'Cavaliers',
  'Celtics', 'Clippers', 'Grizzlies', 'Hawks',
  'Heat', 'Hornets', 'Jazz', 'Kings',
  'Knicks', 'Lakers', 'Magic', 'Mavericks',
  'Nets', 'Nuggets', 'Pacers', 'Pelicans',
  'Pistons', 'Raptors', 'Rockets', 'Spurs',
  'Suns', 'Thunder', 'Timberwolves',
  'Trail Blazers', 'Warriors', 'Wizards'
];

function teamName(s, g) {
  const name = clean(s);

  if (g.sport === 'NBA') {
    const match = NBA_TEAMS.find(
      t => name === clean(t) ||
        name.endsWith(' ' + clean(t))
    );

    if (match) return clean(match);
  }

  return name;
}

function key(g) {
  const parts = String(g.title || '')
    .split(/\s+at\s+|\s+vs\.?\s+/i);

  if (parts.length === 2) {
    return [
      g.sport,
      g.competition || '',
      g.date,
      teamName(parts[0], g),
      teamName(parts[1], g)
    ].join('|');
  }

  return [
    g.sport,
    g.competition || '',
    g.date,
    clean(g.title)
  ].join('|');
}

const favoriteKey = g => key(g);

const ALLOWED = new Set([
  'bbc iplayer',
  'itvx',
  'disney+',
  'prime',
  'prime video',
  'amazon prime',
  'channel 4',
  'channel 5',
  '5action',
  'netflix',
  'apple tv',
  'league pass',
  'nba league pass'
]);

function watchable(g) {
  const competition = canonical(g.competition);
  const sport = canonical(g.sport);
  const service = canonical(g.service);

  if (sport === 'nba' && competition === 'nba') return true;
  if (sport === 'mls' && competition === 'mls') return true;
  if (sport === 'mlb' && competition === 'mlb') return true;

  const verified =
    g.broadcastVerified === true ||
    g.ukBroadcastVerified === true;

  return verified && ALLOWED.has(service);
}

/*
  FINISHED-GAME DETECTION

  A game is considered finished ONLY if its
  fixture data explicitly confirms completion.

  We do not guess from the scheduled start time.

  Postponed, suspended, delayed and unknown
  statuses are not treated as completed.
*/

function confirmedFinal(g) {
  if (!g || typeof g !== 'object') return false;

  const status = g.status;

  if (
    g.completed === true ||
    g.isCompleted === true ||
    g.isFinal === true ||
    g._confirmedFinal === true ||
    status?.completed === true ||
    status?.type?.completed === true
  ) {
    return true;
  }

  const finalCodes = new Set([
    'final',
    'ft',
    'finished',
    'completed',
    'full time',
    'fulltime',
    'game over',
    'aet',
    'after extra time',
    'after penalties',
    'final ot',
    'final so',
    'final pens',
    'final pk',
    'status final',
    'status full time'
  ]);

  const fields = [
    g.liveStatus,
    g.statusText,
    g.statusName,
    g.state,
    typeof status === 'string' ? status : null,
    status?.name,
    status?.description,
    status?.detail,
    status?.shortDetail,
    status?.state,
    status?.type?.name,
    status?.type?.description,
    status?.type?.detail,
    status?.type?.shortDetail
  ];

  return fields.some(value => {
    if (typeof value !== 'string') return false;

    const s = canonical(
      value.replace(/_/g, ' ').replace(/-/g, ' ')
    );

    if (finalCodes.has(s)) return true;

    return /^final(?:\s|$)/.test(s) ||
      /^ft(?:\s|$)/.test(s) ||
      /^full time(?:\s|$)/.test(s) ||
      /^finished(?:\s|$)/.test(s) ||
      /^completed(?:\s|$)/.test(s);
  });
}

/*
  Determine status directly from the current
  fixture record before it is displayed.
*/

function liveGame(g) {
  const item = normalize(g);

  return {
    ...item,
    _confirmedFinal: confirmedFinal(item)
  };
}

function eventGender(g) {
  const competition = canonical(g.competition);
  const title = canonical(g.title);
  const sport = canonical(g.sport);

  if (
    /\b(women|womens|women's|female|ladies|girls|wsl|nwsl|uwcl|wnba|wta)\b/
      .test(competition + ' ' + title)
  ) {
    return 'women';
  }

  if (/\b(men|mens|men's|male|boys)\b/.test(competition)) {
    return 'men';
  }

  if (['nba', 'nfl', 'mls', 'mlb'].includes(sport)) {
    return 'men';
  }

  if ([
    'premier league',
    'champions league',
    'uefa nations league',
    'nations championship',
    'nations championship finals'
  ].includes(competition)) {
    return 'men';
  }

  return 'unknown';
}

let genderFilter = safeRead(GENDER_STORE, 'all');

if (!['all', 'men', 'women'].includes(genderFilter)) {
  genderFilter = 'all';
}

let seed = [];
let live = [];

let view = 'upcoming';
let sport = 'All';
let service = 'All';
let query = '';
let date = TODAY();

let favorites = new Set(
  safeRead(FAVORITES_V2, [])
);

let legacyFavorites = new Set(
  safeRead(STORE, [])
);

let excludedSports = new Set(
  safeRead(EXCLUDE_STORE, [])
);

let excludeMode = false;
let lastRefresh = 0;
let updating = false;

const saveExcluded = () =>
  localStorage.setItem(
    EXCLUDE_STORE,
    JSON.stringify([...excludedSports])
  );

/*
  COMBINE SEED AND LIVE GAMES
*/

function allGames() {
  const m = new Map();

  seed.forEach(g => {
    const item = normalize(g);
    m.set(key(item), item);
  });

  live.forEach(g => {
    const item = liveGame(g);
    const k = key(item);
    const old = m.get(k);

    if (old) {
      m.set(k, {
        ...old,
        ...item,
        priority: old.priority || item.priority,
        service: item.service,
        source: 'Live fixture feed',
        broadcastVerified:
          item.broadcastVerified === true ||
          item.ukBroadcastVerified === true
      });
    } else {
      m.set(k, item);
    }
  });

  return [...m.values()]
    .filter(watchable)
    .map(g => {
      const item = {
        ...g,
        _confirmedFinal: confirmedFinal(g)
      };

      if (
        canonical(item.sport) === 'nba' &&
        canonical(item.competition) === 'nba'
      ) {
        return {
          ...item,
          service: 'League Pass'
        };
      }

      if (
        canonical(item.sport) === 'mls' &&
        canonical(item.competition) === 'mls'
      ) {
        return {
          ...item,
          service: 'Apple TV'
        };
      }

      if (
        canonical(item.sport) === 'mlb' &&
        canonical(item.competition) === 'mlb'
      ) {
        return {
          ...item,
          service: 'MLB.TV'
        };
      }

      return item;
    })
    .sort((a, b) =>
      a.date.localeCompare(b.date) ||
      (
        a.time === 'TBC'
          ? 1
          : b.time === 'TBC'
            ? -1
            : a.time.localeCompare(b.time)
      ) ||
      a.title.localeCompare(b.title)
    );
}

/*
  FILTER BUTTONS
*/

function chips(id, values, current, cb) {
  $(id).innerHTML = values.map(v =>
    `<button class="chip ${
      v === current ? 'active' : ''
    }" data-v="${escape(v)}">${escape(v)}</button>`
  ).join('');

  $(id).querySelectorAll('button').forEach(b => {
    b.onclick = () => {
      cb(b.dataset.v);
      render();
    };
  });
}

/*
  MAIN RENDER
*/

function render() {
  const games = allGames();

  let migrated = false;

  for (const g of games) {
    if (legacyFavorites.has(g.id)) {
      favorites.add(favoriteKey(g));
      legacyFavorites.delete(g.id);
      migrated = true;
    }
  }

  if (migrated) {
    localStorage.setItem(
      FAVORITES_V2,
      JSON.stringify([...favorites])
    );

    localStorage.setItem(
      STORE,
      JSON.stringify([...legacyFavorites])
    );
  }

  const sports = [
    'All',
    ...new Set(games.map(g => g.sport))
  ];

  const services = [
    'All',
    ...new Set(games.map(g => g.service))
  ];

  if (!sports.includes(sport)) sport = 'All';
  if (!services.includes(service)) service = 'All';

  const sportsBox = $('sports');

  sportsBox.innerHTML =
    `<div style="width:100%;display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:9px">
      <button id="sportMode"
        class="chip ${excludeMode ? 'active' : ''}"
        type="button"
        aria-pressed="${excludeMode}">
        ${excludeMode
          ? '✓ Exclude sports'
          : '⊖ Exclude sports'}
      </button>
      ${excludeMode
        ? '<button id="clearExcluded" class="chip" type="button">Clear exclusions</button><span style="font-size:12px;opacity:.8">Select sports to hide</span>'
        : ''}
    </div>` +

    sports.map(v =>
      `<button class="chip ${
        excludeMode
          ? (excludedSports.has(v) ? 'active' : '')
          : (v === sport ? 'active' : '')
      }"
      data-v="${escape(v)}"
      type="button"
      aria-pressed="${
        excludeMode
          ? excludedSports.has(v)
          : v === sport
      }">${
        excludeMode && excludedSports.has(v)
          ? '✕ '
          : ''
      }${escape(v)}</button>`
    ).join('');

  $('sportMode').onclick = () => {
    excludeMode = !excludeMode;
    render();
  };

  if (excludeMode) {
    $('clearExcluded').onclick = () => {
      excludedSports.clear();
      saveExcluded();
      render();
    };
  }

  sportsBox
    .querySelectorAll('button[data-v]')
    .forEach(b => {
      b.onclick = () => {
        const v = b.dataset.v;

        if (excludeMode) {
          if (v === 'All') {
            excludedSports.clear();
          } else if (excludedSports.has(v)) {
            excludedSports.delete(v);
          } else {
            excludedSports.add(v);
          }

          saveExcluded();
        } else {
          sport = v;
        }

        render();
      };
    });

  let genderBox = $('genderFilters');

  if (!genderBox) {
    genderBox = document.createElement('div');

    genderBox.id = 'genderFilters';

    genderBox.style.cssText =
      'display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0';

    $('sports').insertAdjacentElement(
      'afterend',
      genderBox
    );
  }

  genderBox.innerHTML =
    '<span style="font-size:12px;opacity:.8;margin-right:3px">Competition</span>' +

    [
      ['all', 'All'],
      ['men', 'Men’s only'],
      ['women', 'Women’s only']
    ].map(([v, label]) =>
      `<button
        type="button"
        class="chip ${
          genderFilter === v ? 'active' : ''
        }"
        data-gender="${v}"
        aria-pressed="${
          genderFilter === v
        }">${label}</button>`
    ).join('');

  genderBox
    .querySelectorAll('button')
    .forEach(b => {
      b.onclick = () => {
        genderFilter = b.dataset.gender;

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
    v => service = v
  );

  $('date').value = date;

  document.querySelectorAll('#views button')
    .forEach(b => {
      b.classList.toggle(
        'active',
        b.dataset.view === view
      );
    });

  /*
    IMPORTANT CHANGE:

    Upcoming: Hide confirmed finished games.
    Saved: Hide confirmed finished games.
    All dates: Keep every game.

    Never hide a game simply because its
    start time has passed.
  */

  const list = games.filter(g => {
    if (
      genderFilter !== 'all' &&
      eventGender(g) !== genderFilter
    ) {
      return false;
    }

    if (excludeMode) {
      if (excludedSports.has(g.sport)) {
        return false;
      }
    } else if (
      sport !== 'All' &&
      g.sport !== sport
    ) {
      return false;
    }

    if (
      service !== 'All' &&
      g.service !== service
    ) {
      return false;
    }

    if (query) {
      const searchable = (
        g.title + ' ' +
        g.sport + ' ' +
        (g.competition || '') + ' ' +
        g.service
      ).toLowerCase();

      if (!searchable.includes(query)) {
        return false;
      }
    }

    if (view === 'faves') {
      return (
        favorites.has(favoriteKey(g)) &&
        !g._confirmedFinal
      );
    }

    if (view === 'upcoming') {
      return (
        !g._confirmedFinal &&
        g.date >= date &&
        g.date < addDays(date, 30)
      );
    }

    // All dates: show finished and unfinished.
    return true;
  });

  $('gameCount').textContent = list.length;

  $('dayCount').textContent =
    new Set(list.map(g => g.date)).size;

  /*
    Count only favourites that are not
    confirmed finished.
  */

  const activeSaved = games.filter(g =>
    favorites.has(favoriteKey(g)) &&
    !g._confirmedFinal
  ).length;

  $('favCount').textContent =
    activeSaved + legacyFavorites.size;

  const groups = list.reduce((o, g) => {
    (o[g.date] ??= []).push(g);
    return o;
  }, {});

  $('results').innerHTML = list.length
    ? Object.entries(groups).map(([d, gs]) =>
      `<section class="day">
        <div class="dayhead">
          <strong>${escape(uk(
            d + 'T12:00:00Z',
            {
              weekday: 'long',
              day: 'numeric',
              month: 'long'
            }
          ))}</strong>
          <span>${gs.length} fixture${
            gs.length === 1 ? '' : 's'
          }</span>
        </div>

        ${gs.map(g =>
          `<div class="game">
            <div class="time">${escape(g.time)}</div>

            <div>
              <div class="match">${
                g.priority ? '★ ' : ''
              }${escape(g.title)}</div>

              <div class="meta">
                ${escape(g.sport)} ·
                ${escape(g.competition || '')} ·
                ${escape(g.service)}
                ${g.liveStatus
                  ? ' · ' + escape(g.liveStatus)
                  : ''}
              </div>
            </div>

            <button
              class="star ${
                favorites.has(favoriteKey(g))
                  ? 'on'
                  : ''
              }"
              data-id="${escape(favoriteKey(g))}"
              aria-label="Save fixture">${
                favorites.has(favoriteKey(g))
                  ? '★'
                  : '☆'
              }</button>
          </div>`
        ).join('')}
      </section>`
    ).join('')

    : '<div class="empty">No watchable fixtures found for these filters or dates. Unverified UK broadcasts are hidden.</div>';

  $('results')
    .querySelectorAll('.star')
    .forEach(b => {
      b.onclick = () => {
        if (favorites.has(b.dataset.id)) {
          favorites.delete(b.dataset.id);
        } else {
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

/*
  FETCH LIVE SCHEDULE
*/

async function refresh() {
  if (updating) return;

  updating = true;

  const b = $('refresh');
  b.disabled = true;
  b.textContent = '↻ Checking…';

  try {
    const response = await fetch(
      './live-fixtures.json?t=' + Date.now(),
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw Error('HTTP ' + response.status);
    }

    const data = await response.json();

    if (!Array.isArray(data.items)) {
      throw Error('Missing fixture list');
    }

    live = data.items.map(liveGame);

    const at =
      data.updatedAt || new Date().toISOString();

    localStorage.setItem(
      CACHE,
      JSON.stringify({
        at,
        items: live
      })
    );

    lastRefresh = Date.now();

    const n = data.successfulChecks ?? 0;
    const total = data.totalChecks ?? 0;

    $('status').textContent =
      `Server checked ${
        new Date(at).toLocaleString(
          'en-GB',
          { timeZone: TZ }
        )
      } · ${n}/${total} feed checks successful${
        n < total
          ? ' · partial coverage'
          : ''
      } · only watchable fixtures shown`;

  } catch (e) {
    $('status').textContent = live.length
      ? 'Could not reach server update. Showing cached watchable fixtures.'
      : 'No live schedule available yet. Run the GitHub Actions update once.';
  }

  updating = false;
  b.disabled = false;
  b.textContent = '↻ Refresh';

  render();
}

/*
  INITIALISE APP
*/

async function init() {
  date = TODAY();
  $('date').value = date;

  $('date').onchange = e => {
    date = e.target.value;
    render();
  };

  $('prev').onclick = () => {
    date = addDays(date, -1);
    render();
  };

  $('next').onclick = () => {
    date = addDays(date, 1);
    render();
  };

  $('reset').onclick = () => {
    date = TODAY();
    render();
  };

  $('search').oninput = e => {
    query = e.target.value
      .toLowerCase()
      .trim();

    render();
  };

  document.querySelectorAll('#views button')
    .forEach(b => {
      b.onclick = () => {
        view = b.dataset.view;
        render();
      };
    });

  $('refresh').onclick = refresh;

  try {
    const r = await fetch(
      './seed.json?v=4',
      { cache: 'no-store' }
    );

    if (!r.ok) throw Error();

    const data = await r.json();

    seed = Array.isArray(data)
      ? data.map(normalize)
      : [];

  } catch {
    $('status').textContent =
      'Saved fixture list could not be loaded.';
  }

  const cached =
    safeRead(CACHE, null) ||
    safeRead(OLD, null);

  if (
    cached?.items &&
    Array.isArray(cached.items)
  ) {
    live = cached.items.map(liveGame);

    lastRefresh =
      new Date(cached.at).getTime() || 0;

    $('status').textContent =
      `Cached fixtures from ${
        new Date(cached.at).toLocaleString(
          'en-GB',
          { timeZone: TZ }
        )
      } · only watchable fixtures shown`;
  }

  render();
  refresh();

  document.addEventListener(
    'visibilitychange',
    () => {
      if (!document.hidden) {
        if (date === addDays(TODAY(), -1)) {
          date = TODAY();
        }

        render();

        if (
          Date.now() - lastRefresh >
          15 * 60 * 1000
        ) {
          refresh();
        }
      }
    }
  );

  setInterval(() => {
    if (
      !document.hidden &&
      Date.now() - lastRefresh >
      15 * 60 * 1000
    ) {
      refresh();
    }
  }, 5 * 60 * 1000);

  if (
    'serviceWorker' in navigator &&
    location.protocol === 'https:'
  ) {
    navigator.serviceWorker
      .register('./sw.js')
      .catch(() => {});
  }
}

init();

})();
