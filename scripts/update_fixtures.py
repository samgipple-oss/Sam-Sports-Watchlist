#!/usr/bin/env python3
"""Fetch public ESPN scoreboards server-side for a rolling 35-day window.
Uses Python standard library only. Partial failures are recorded, not hidden.
"""
import datetime as dt
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'live-fixtures.json'
TZ = ZoneInfo('Europe/London')
FEEDS = [
    ('NBA', 'NBA', 'basketball/nba', 'League Pass'),
    ('NFL', 'NFL', 'football/nfl', 'Check broadcaster'),
    ('MLS', 'MLS', 'soccer/usa.1', 'Apple TV'),
    ('Football', 'Champions League', 'soccer/uefa.champions', 'Check broadcaster'),
    ('Football', 'Premier League', 'soccer/eng.1', 'Check broadcaster'),
    ('Football', 'WSL', 'soccer/eng.w.1', 'Check broadcaster'),
    ('Football', 'Women’s Champions League', 'soccer/uefa.wchampions', 'Check broadcaster'),
    ('Rugby', 'Rugby Union', 'rugby/164', 'Check broadcaster'),
]

def fetch(job):
    sport, competition, path, service, start, end = job
    dates = start.strftime('%Y%m%d') + '-' + end.strftime('%Y%m%d')
    url = f'https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?' + urllib.parse.urlencode({'dates': dates, 'limit': 300})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 SportsWatchlist/1.0', 'Accept': 'application/json'})
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                obj = json.load(response)
            if not isinstance(obj.get('events'), list):
                raise ValueError('No events array')
            fixtures = []
            for event in obj['events']:
                try:
                    competitors = event['competitions'][0]['competitors']
                    if len(competitors) < 2:
                        continue
                    away = next((x for x in competitors if x.get('homeAway') == 'away'), competitors[0])
                    home = next((x for x in competitors if x.get('homeAway') == 'home'), competitors[1])
                    timestamp = dt.datetime.fromisoformat(event['date'].replace('Z', '+00:00')).astimezone(TZ)
                    if not start <= timestamp.date() <= end:
                        continue
                    name = lambda x: x.get('team', {}).get('displayName') or x.get('team', {}).get('name') or 'TBC'
                    fixtures.append({
                        'id': f'espn:{path}:{event["id"]}',
                        'date': timestamp.date().isoformat(),
                        'time': timestamp.strftime('%H:%M'),
                        'sport': sport, 'competition': competition,
                        'title': f'{name(away)} at {name(home)}',
                        'service': service, 'source': 'Scheduled data feed',
                        'liveStatus': event.get('status', {}).get('type', {}).get('description', '')
                    })
                except (KeyError, ValueError, TypeError):
                    continue
            return (path, start.isoformat(), True, fixtures, None)
        except Exception as exc:
            last_error = str(exc)
            if attempt == 0:
                time.sleep(0.5)
    return (path, start.isoformat(), False, [], last_error)

def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)
    jobs = []
    for feed in FEEDS:
        for offset in range(0, 35, 7):
            a = today + dt.timedelta(days=offset)
            jobs.append((*feed, a, min(a + dt.timedelta(days=6), end)))
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(fetch, job) for job in jobs]):
            results.append(future.result())
    successful = [r for r in results if r[2]]
    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except (ValueError, OSError):
            pass
    # Do not erase previously obtained fixtures on partial feed failures.
    fixtures = {g['id']: g for g in existing.get('items', []) if today.isoformat() <= g.get('date', '') <= end.isoformat() and g.get('id')}
    for _, _, _, games, _ in successful:
        for game in games:
            fixtures[game['id']] = game
    coverage = [{'feed': r[0], 'weekStart': r[1], 'ok': r[2], **({'error': r[4][:180]} if r[4] else {})} for r in sorted(results, key=lambda x: (x[0], x[1]))]
    payload = {
        'updatedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'successfulChecks': len(successful), 'totalChecks': len(results),
        'items': sorted(fixtures.values(), key=lambda g: (g['date'], g['time'], g['title'])),
        'coverage': coverage,
        'note': 'Public feeds are best-effort; UK TV rights are not verified.'
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(f"Updated: {len(fixtures)} fixtures; {len(successful)}/{len(results)} checks succeeded")
    for feed, week_start, ok, games, error in sorted(
        results, key=lambda r: (r[0], r[1])
    ):
        if not ok:
            print(f"FAILED {feed} ({week_start}): {error}", flush=True)
        else:
            print(
                f"OK {feed} ({week_start}): {len(games)} fixtures",
                flush=True
            )

    if not successful:
        raise RuntimeError(
            "All sports feeds failed. See individual errors above."
        )

if __name__ == '__main__':
    main()
