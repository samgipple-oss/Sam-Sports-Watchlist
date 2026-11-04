
#!/usr/bin/env python3
"""Update a rolling 35-day UK sports calendar from ESPN scoreboards.

Uses individual-day requests, logs failures, and preserves existing
fixtures when a request fails. Python standard library only.
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
OUT = ROOT / "live-fixtures.json"
TZ = ZoneInfo("Europe/London")

FEEDS = [
    ("NBA", "NBA", "basketball/nba", "League Pass"),
    ("NFL", "NFL", "football/nfl", "Check broadcaster"),
    ("MLS", "MLS", "soccer/usa.1", "Apple TV"),
    ("Football", "Champions League", "soccer/uefa.champions", "Check broadcaster"),
    ("Football", "Premier League", "soccer/eng.1", "Check broadcaster"),
    ("Football", "WSL", "soccer/eng.w.1", "Check broadcaster"),
    ("Football", "Women’s Champions League", "soccer/uefa.wchampions", "Check broadcaster"),
    ("Rugby", "Rugby Union", "rugby/164", "Check broadcaster"),
]


def fetch(job):
    sport, competition, path, service, day, today, end = job

    url = (
        "https://site.api.espn.com/apis/site/v2/sports/"
        + path
        + "/scoreboard?"
        + urllib.parse.urlencode({
            "dates": day.strftime("%Y%m%d"),
            "limit": 300,
        })
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SportsWatchlist/1.0)",
            "Accept": "application/json",
        },
    )

    error = None

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)

            if not isinstance(data, dict) or not isinstance(data.get("events"), list):
                raise ValueError("Missing events array")

            games = []

            for event in data["events"]:
                try:
                    competitors = event["competitions"][0]["competitors"]

                    if len(competitors) < 2:
                        continue

                    away = next(
                        (c for c in competitors if c.get("homeAway") == "away"),
                        competitors[0],
                    )
                    home = next(
                        (c for c in competitors if c.get("homeAway") == "home"),
                        competitors[1],
                    )

                    when = dt.datetime.fromisoformat(
                        event["date"].replace("Z", "+00:00")
                    ).astimezone(TZ)

                    if not today <= when.date() <= end:
                        continue

                    def team_name(side):
                        team = side.get("team") or {}
                        return (
                            team.get("displayName")
                            or team.get("name")
                            or "TBC"
                        )

                    games.append({
                        "id": f'espn:{path}:{event["id"]}',
                        "date": when.date().isoformat(),
                        "time": when.strftime("%H:%M"),
                        "sport": sport,
                        "competition": competition,
                        "title": f"{team_name(away)} at {team_name(home)}",
                        "service": service,
                        "source": "Scheduled data feed",
                        "liveStatus": (
                            event.get("status", {})
                            .get("type", {})
                            .get("description", "")
                        ),
                    })

                except (KeyError, ValueError, TypeError, IndexError, AttributeError):
                    continue

            return path, day.isoformat(), True, games, None

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))

    return path, day.isoformat(), False, [], error


def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)

    # Include an extra UTC day for UK timezone boundaries.
    days = [
        today + dt.timedelta(days=n)
        for n in range(36)
    ]

    jobs = [
        (*feed, day, today, end)
        for feed in FEEDS
        for day in days
    ]

    results = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(fetch, job)
            for job in jobs
        ]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            path, day, ok, games, error = result

            if not ok:
                print(
                    f"FAILED {path} ({day}): {error}",
                    flush=True,
                )

    successful = [r for r in results if r[2]]
    failed = [r for r in results if not r[2]]

    print(
        f"Checks: {len(successful)}/{len(results)} successful; "
        f"{sum(len(r[3]) for r in successful)} raw fixtures; "
        f"{len(failed)} failures",
        flush=True,
    )

    if not successful:
        raise RuntimeError(
            "All ESPN feeds failed; existing live-fixtures.json was left unchanged."
        )

    existing = {}

    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(
                f"WARNING: Could not read existing schedule: {exc}",
                flush=True,
            )

    if not isinstance(existing, dict):
        existing = {}

    successful_ids = set()
    fresh = {}

    for path, day, ok, games, _ in successful:
        successful_ids.add((path, day))

        for game in games:
            fresh[game["id"]] = game

    merged = dict(fresh)

    # Preserve old fixtures where their feed was not refreshed.
    for game in existing.get("items", []):
        if not isinstance(game, dict):
            continue

        game_id = game.get("id")
        game_date = game.get("date", "")

        if not isinstance(game_id, str) or not isinstance(game_date, str):
            continue

        if not today.isoformat() <= game_date <= end.isoformat():
            continue

        if game_id in merged:
            continue

        if not game_id.startswith("espn:"):
            merged[game_id] = game
            continue

        try:
            path = game_id.split(":", 2)[1]
            local_day = dt.date.fromisoformat(game_date)
        except (IndexError, ValueError):
            continue

        relevant = [
            local_day - dt.timedelta(days=1),
            local_day,
        ]

        if not all(
            (path, d.isoformat()) in successful_ids
            for d in relevant
            if d >= today
        ):
            merged[game_id] = game

    coverage = [
        {
            "feed": path,
            "date": day,
            "ok": ok,
            **({"error": error[:180]} if error else {}),
        }
        for path, day, ok, _, error in sorted(
            results,
            key=lambda r: (r[0], r[1]),
        )
    ]

    payload = {
        "updatedAt": dt.datetime.now(
            dt.timezone.utc
        ).isoformat(),
        "successfulChecks": len(successful),
        "totalChecks": len(results),
        "items": sorted(
            merged.values(),
            key=lambda g: (
                g.get("date", ""),
                g.get("time", ""),
                g.get("title", ""),
            ),
        ),
        "coverage": coverage,
        "note": (
            "Public feeds are best-effort; "
            "UK TV rights are not verified."
        ),
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f"Updated: {len(merged)} fixtures; "
        f"{len(successful)}/{len(results)} checks succeeded",
        flush=True,
    )

    if failed:
        print(
            f"WARNING: {len(failed)} requests failed. "
            "Existing data retained where needed.",
            flush=True,
        )


if __name__ == "__main__":
    main()
