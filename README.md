# Sports Watchlist — free iPhone web app

This is a **working Progressive Web App** with a saved fixture list, searchable calendar, filters, favourites, an iPhone Home Screen icon, offline caching, and optional automatic fixture refresh.

## Put it on your iPhone for free

1. Create a free GitHub account (if needed).
2. Create a **public** repository named `sports-watchlist`.
3. Upload **all files and folders** in this ZIP into the repository root. Do not upload the ZIP itself.
4. Open repository **Settings → Pages → Build and deployment**. Choose **Deploy from a branch**, select `main` and `/ (root)`, then Save.
5. Wait for GitHub Pages to show a URL such as `https://YOUR-USERNAME.github.io/sports-watchlist/`.
6. On your iPhone, open that URL in **Safari**, tap **Share → Add to Home Screen → Add**.

**No payment card or Apple Developer account required.** GitHub Pages public-repository hosting is generally free.

## Live updates — what works and what doesn't

The Refresh button attempts to load the next 30 days from ESPN's public scoreboard endpoints for NBA, NFL, MLS, Champions League, Premier League, WSL, and Women's Champions League. It combines successful results with the saved fixtures. If a feed is blocked by browser cross-origin restrictions, changes its API, or has incomplete dates, the app displays its saved fixtures and reports how many feeds connected. The feed is **unofficial, undocumented, and not guaranteed**. It is not a true live-score service or a guaranteed complete schedule.

The UK streaming-provider information is **not automatically verified**: NBA is provisionally tagged League Pass, MLS Apple TV, and other newly fetched games "Check broadcaster". The older seeded broadcasts are marked **provisional**. Some original fixture information may be wrong; verify before relying on it. No automated TV-rights source is included.

The app is not a paid API service. It does not use a backend and makes network requests only when opened or refreshed. It does not send push notifications. Favourites use your device's local storage and won't sync between devices.

## Test on a computer

Run `python3 -m http.server 8000` from the unzipped folder, then open `http://localhost:8000`. Opening the HTML file directly (`file://`) won't reliably load JSON or enable PWA installation.

## Future improvements

For reliable scheduled updates, use a free Cloudflare Worker or a GitHub Actions job to collect licensed/approved feeds and publish a consolidated JSON file. Do not rely on unofficial ESPN endpoints as a production guarantee.
