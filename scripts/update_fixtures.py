#!/usr/bin/env python3
"""Update a rolling 35-day UK sports calendar from ESPN's public scoreboards.

Uses single-day requests because ESPN's scoreboard no longer accepts date ranges.
Standard library only; failed requests are logged and existing data is preserved.
"""
import datetime as dt
import json
import pathlib
import time
import urllib.error
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
    sport, competition, path, service, day, today, end = job
    url = ('https://site.api.espn.com/apis/site/v2/sports/' + path + '/scoreboard?'
           + urllib.parse.urlencode({'dates': day.strftime('%Y%m%d'), 'limit': 300}))
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; SportsWatchlist/1.0)',
        'Accept': 'application/json',
    })
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get('events'), list):
                raise ValueError('Missing events array')
            games = []
            for event in data['events']:
                try:
                    competitors = event['competitions'][0]['competitors']
                    if len(competitors) < 2:
                        continue
                    away = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[0])
                    home = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[1])
                    when = dt.datetime.fromisoformat(event['date'].replace('Z', '+00:00')).astimezone(TZ)
                    if not today <= when.date() <= end:
                        continue
                    def team_name(side):
                        team = side.get('team') or {}
                        return team.get('displayName') or team.get('name') or 'TBC'
                    games.append({
                        'id': f'espn:{path}:{event["id"]}',
                        'date': when.date().isoformat(),
                        'time': when.strftime('%H:%M'),
                        'sport': sport,
                        'competition': competition,
                        'title': f'{team_name(away)} at {team_name(home)}',
                        'service': service,
                        'source': 'Scheduled data feed',
                        'liveStatus': event.get('status', {}).get('type', {}).get('description', ''),
                    })
                except (KeyError, ValueError, TypeError, IndexError, AttributeError):
                    continue
            return path, day.isoformat(), True, games, None
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    return path, day.isoformat(), False, [], error


def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)
    # One extra UTC date catches games just after midnight in UK local time.
    days = [today + dt.timedelta(days=n) for n in range(36)]
    jobs = [(*feed, day, today, end) for feed in FEEDS for day in days]
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fetch, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            path, day, ok, games, error = result
            if not ok:
                print(f'FAILED {path} ({day}): {error}', flush=True)
