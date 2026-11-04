#!/usr/bin/env python3
"""Refresh ESPN fixtures and attach conservative UK viewing entitlements.

Optional broadcast-overrides.json maps ESPN fixture IDs to verified UK services.
Unknown football broadcasts remain hidden by the strict front-end filter.
"""
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'live-fixtures.json'
OVERRIDES = ROOT / 'broadcast-overrides.json'
TZ = ZoneInfo('Europe/London')
FEEDS = [
    ('NBA', 'NBA', 'basketball/nba', 'League Pass'),
    ('NFL', 'NFL', 'football/nfl', 'Check broadcaster'),
    ('MLS', 'MLS', 'soccer/usa.1', 'Apple TV'),
    ('Football', 'Champions League', 'soccer/uefa.champions', 'Check broadcaster'),
    ('Football', 'Premier League', 'soccer/eng.1', 'Check broadcaster'),
    ('Football', 'WSL', 'soccer/eng.w.1', 'Check broadcaster'),
    ('Football', 'Women’s Champions League', 'soccer/uefa.wchampions', 'Disney+'),
]
ALLOWED = {
    'League Pass', 'Apple TV', 'Disney+', 'Prime', 'Prime Video',
    'BBC iPlayer', 'ITVX', 'Channel 4', 'Channel 5', '5Action', 'Netflix',
}

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'INFO: {path.name}: {exc}', flush=True)
        return default

def fetch(job):
    sport, competition, path, service, day, today, end = job
    url = 'https://site.api.espn.com/apis/site/v2/sports/' + path + '/scoreboard?' + urllib.parse.urlencode({'dates': day.strftime('%Y%m%d'), 'limit': 300})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; SportsWatchlist/1.1)', 'Accept': 'application/json'})
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
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
                    def name(side):
                        team = side.get('team') or {}
                        return team.get('displayName') or team.get('name') or 'TBC'
                    games.append({
                        'id': f'espn:{path}:{event["id"]}',
                        'date': when.date().isoformat(),
                        'time': when.strftime('%H:%M'),
                        'sport': sport,
                        'competition': competition,
                        'title': f'{name(away)} at {name(home)}',
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

def entitlement(game, overrides, old):
    """Only claim verified broadcasts when supported by explicit evidence."""
    game = dict(game)
    gid = game['id']
    if game['sport'] == 'NBA':
        game.update(service='League Pass', broadcastVerified=True)
    elif game['sport'] == 'MLS':
        game.update(service='Apple TV', broadcastVerified=True)
    elif game['competition'] == 'Women’s Champions League':
        game.update(service='Disney+', broadcastVerified=True)
    else:
        game.update(service='Check broadcaster', broadcastVerified=False)

    # Overrides must be manually verified against an actual UK match listing.
    entry = overrides.get(gid)
    if isinstance(entry, dict):
        service = entry.get('service')
        evidence = entry.get('sourceUrl')
        if service in ALLOWED and isinstance(evidence, str) and evidence.startswith('https://'):
            game.update(service=service, broadcastVerified=True, broadcastSource=evidence)
        else:
            print(f'WARNING: ignored invalid broadcast override for {gid}', flush=True)
    elif gid in old and old[gid].get('broadcastVerified') is True:
        previous = old[gid]
        if previous.get('service') in ALLOWED and previous.get('broadcastSource', '').startswith('https://'):
            game.update(service=previous['service'], broadcastVerified=True, broadcastSource=previous['broadcastSource'])
    return game

def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)
    days = [today + dt.timedelta(days=n) for n in range(36)]
    existing = read_json(OUT, {})
    if not isinstance(existing, dict):
        existing = {}
    old = {g['id']: g for g in existing.get('items', []) if isinstance(g, dict) and isinstance(g.get('id'), str)}
    overrides = read_json(OVERRIDES, {})
    if not isinstance(overrides, dict):
        overrides = {}
    jobs = [(*feed, day, today, end) for feed in FEEDS for day in days]
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(fetch, jobs))
    successful = [r for r in results if r[2]]
    failed = [r for r in results if not r[2]]
    for path, day, _, _, error in failed:
        print(f'FAILED {path} ({day}): {error}', flush=True)
    if not successful:
        raise RuntimeError('All ESPN feeds failed; existing schedule unchanged')
    successful_ids = {(path, day) for path, day, ok, _, _ in successful}
    merged = {}
    for _, _, _, games, _ in successful:
        for game in games:
            merged[game['id']] = entitlement(game, overrides, old)
    for gid, game in old.items():
        game_date = game.get('date', '')
        if not isinstance(game_date, str) or not today.isoformat() <= game_date <= end.isoformat() or gid in merged:
            continue
        if not gid.startswith('espn:'):
            # Preserve manually entered games, but never automatically trust their broadcaster.
            merged[gid] = game
            continue
        try:
            path = gid.split(':', 2)[1]
            local_day = dt.date.fromisoformat(game_date)
        except (IndexError, ValueError):
            continue
        relevant = [local_day - dt.timedelta(days=1), local_day]
        if not all((path, d.isoformat()) in successful_ids for d in relevant if d >= today):
            merged[gid] = entitlement(game, overrides, old)
    coverage = [{'feed': path, 'date': day, 'ok': ok, **({'error': error[:180]} if error else {})} for path, day, ok, _, error in sorted(results, key=lambda r: (r[0], r[1]))]
    payload = {
        'updatedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'successfulChecks': len(successful),
        'totalChecks': len(results),
        'items': sorted(merged.values(), key=lambda g: (g.get('date', ''), g.get('time', ''), g.get('title', ''))),
        'coverage': coverage,
        'note': 'NBA, MLS and Women’s Champions League have competition-level access rules. Other UK broadcast rights require verified per-fixture overrides.',
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Updated: {len(merged)} fixtures; {len(successful)}/{len(results)} checks succeeded; {sum(g.get("broadcastVerified") is True for g in merged.values())} watchable', flush=True)

if __name__ == '__main__':
    main()
