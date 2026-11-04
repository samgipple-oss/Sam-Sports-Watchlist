# Sports Watchlist — automatic free updates

This version uses **GitHub Actions** to download ESPN public scoreboard schedules every six hours. Your iPhone app reads the generated `live-fixtures.json` from its own GitHub Pages site, avoiding browser cross-origin restrictions.

## Install into your existing GitHub Pages repository

1. Upload/replace the top-level files `app.js`, `sw.js`, `seed.json`, `index.html`, `style.css`, `manifest.webmanifest`, `live-fixtures.json` and the `icons` folder as needed. **Do not upload the enclosing folder.**
2. **Important:** GitHub's browser upload may not allow uploading into `.github/workflows/` as intended. On the repository home page choose **Add file → Create new file**. In the filename field enter exactly `.github/workflows/update-fixtures.yml` and paste the contents of that file from the ZIP. Commit to `main`.
3. For `scripts/update_fixtures.py`, choose **Add file → Create new file**, name it `scripts/update_fixtures.py`, paste its contents and commit. Or use GitHub Desktop to upload the entire folder structure.
4. Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions** (if available), then Save. This lets the scheduled job commit its JSON data file.
5. Go to **Actions → Refresh sports fixtures → Run workflow → Run workflow**. Wait for the green check. Open `live-fixtures.json` in the repository to see how many requests succeeded.
6. GitHub Pages automatically republishes when the JSON changes. Reload your iPhone app; it displays a timestamp and feed success count.

## Limitations

- Public ESPN endpoints are unofficial for this purpose; access, competition coverage, date ranges and rate limits can change. A successful response with zero games does not prove no games exist.
- Scheduled GitHub Actions can be delayed. In public repositories, GitHub may disable scheduled workflows after extended inactivity. You can trigger manually from the Actions tab.
- The initial 323 saved schedule entries remain available as provisional entries. The app may display duplicates when the saved name and live feed name differ.
- The app does not independently verify UK streaming rights; non-NBA/non-MLS live fixtures show **Check broadcaster**.
- The site updates on open/refresh, not by push notification while closed.
- Free GitHub usage is subject to GitHub's terms and quotas.
