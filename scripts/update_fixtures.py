
#!/usr/bin/env python3
"""Automatic UK sports watchlist updater. Standard Python only."""

import datetime as dt
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "live-fixtures.json"
OVERRIDES = ROOT / "broadcast-overrides.json"
CURATED = ROOT / "verified-broadcasts.json"
TZ = ZoneInfo("Europe/London")

GUIDE_URL = "https://www.wheresthematch.com/rugby-union-internationals-on-tv/"
RUGBY_TV_URL = "https://www.radiotimes.com/tv/sport/rugby-union/nations-championship-2026-tv/"
NFL_TV_URL = "https://www.radiotimes.com/tv/sport/nfl/live-nfl-today-tv/"

FEEDS = [
    ("NBA", "NBA", "basketball/nba", "League Pass"),
    ("MLB", "MLB", "baseball/mlb", "MLB.TV"),
    ("NFL", "NFL", "football/nfl", "Check broadcaster"),
    ("MLS", "MLS", "soccer/usa.1", "Apple TV"),
    ("Football", "Champions League", "soccer/uefa.champions", "Check broadcaster"),
    ("Football", "Premier League", "soccer/eng.1", "Check broadcaster"),
    ("Football", "WSL", "soccer/eng.w.1", "Check broadcaster"),
    ("Football", "UEFA Nations League", "soccer/uefa.nations", "Check broadcaster"),
    ("Football", "Women’s Champions League", "soccer/uefa.wchampions", "Disney+"),
]

ALLOWED = {
    "League Pass", "MLB.TV", "Apple TV", "Disney+",
    "Prime", "Prime Video", "BBC iPlayer", "ITVX",
    "Channel 4", "Channel 5", "5Action", "Netflix",
}

RUGBY_2026 = [
    ("11-06", "20:10", "Ireland", "Argentina"),
    ("11-07", "11:40", "Italy", "South Africa"),
    ("11-07", "14:10", "Scotland", "New Zealand"),
    ("11-07", "16:40", "Wales", "Japan"),
    ("11-07", "20:10", "France", "Fiji"),
    ("11-08", "15:10", "England", "Australia"),
    ("11-13", "20:10", "France", "South Africa"),
    ("11-14", "11:40", "Italy", "Argentina"),
    ("11-14", "14:10", "Wales", "New Zealand"),
    ("11-14", "16:40", "England", "Japan"),
    ("11-14", "20:10", "Ireland", "Fiji"),
    ("11-15", "15:10", "Scotland", "Australia"),
    ("11-21", "14:10", "England", "New Zealand"),
    ("11-21", "14:10", "Scotland", "Japan"),
    ("11-21", "16:40", "Ireland", "South Africa"),
    ("11-21", "16:40", "Italy", "Fiji"),
    ("11-21", "20:10", "France", "Argentina"),
    ("11-21", "20:10", "Wales", "Australia"),
]

RUGBY_FINALS = [
    ("11-27", "16:40", "Northern 6", "Southern 6"),
    ("11-27", "20:10", "Northern 3", "Southern 3"),
    ("11-28", "13:10", "Northern 5", "Southern 5"),
    ("11-28", "16:40", "Northern 2", "Southern 2"),
    ("11-29", "13:10", "Northern 4", "Southern 4"),
    ("11-29", "16:40", "Northern 1", "Southern 1"),
]

NFL_FREE_2026 = {
    (
        "2026-11-08",
        frozenset(("new york jets", "kansas city chiefs")),
    ): "5Action",
    (
        "2026-11-08",
        frozenset(("green bay packers", "new england patriots")),
    ): "Channel 5",
}


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def download(url, timeout=18):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SamSportsWatchlist/2.0)",
            "Accept": "text/html,application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def fetch(job):
    sport, competition, path, service, day, today, end = job
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/"
        + path
        + "/scoreboard?"
        + urllib.parse.urlencode(
            {"dates": day.strftime("%Y%m%d"), "limit": 300}
        )
    )
    error = None

    for attempt in range(3):
        try:
            data = json.loads(download(url))
            if not isinstance(data.get("events"), list):
                raise ValueError("Missing events array")

            games = []

            for event in data["events"]:
                try:
                    competitors = event["competitions"][0]["competitors"]
                    if len(competitors) < 2:
                        continue

                    away = next(
                        (
                            c for c in competitors
                            if c.get("homeAway") == "away"
                        ),
                        competitors[0],
                    )
                    home = next(
                        (
                            c for c in competitors
                            if c.get("homeAway") == "home"
                        ),
                        competitors[1],
                    )

                    when = dt.datetime.fromisoformat(
                        event["date"].replace("Z", "+00:00")
                    ).astimezone(TZ)

                    if not today <= when.date() <= end:
                        continue

                    def team(c):
                        obj = c.get("team") or {}
                        return (
                            obj.get("displayName")
                            or obj.get("name")
                            or "TBC"
                        )

                    games.append(
                        {
                            "id": f'espn:{path}:{event["id"]}',
                            "date": when.date().isoformat(),
                            "time": when.strftime("%H:%M"),
                            "sport": sport,
                            "competition": competition,
                            "title": f"{team(away)} at {team(home)}",
                            "service": service,
                            "source": "Scheduled data feed",
                            "liveStatus": event.get("status", {})
                            .get("type", {})
                            .get("description", ""),
                        }
                    )

                except (
                    KeyError, ValueError, TypeError,
                    IndexError, AttributeError,
                ):
                    continue

            return path, day.isoformat(), True, games, None

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))

    return path, day.isoformat(), False, [], error


def nations_service(g):
    if g.get("competition") != "UEFA Nations League":
        return None

    teams = [
        t.strip().casefold()
        for t in g.get("title", "").split(" at ")
    ]

    if "england" in teams:
        return "ITVX"

    if any(
        t in teams
        for t in ("scotland", "wales", "northern ireland")
    ):
        return "BBC iPlayer"

    return None


def nfl_service(g):
    if g.get("sport") != "NFL":
        return None

    teams = g.get("title", "").casefold().split(" at ")
    if len(teams) != 2:
        return None

    return NFL_FREE_2026.get(
        (g["date"], frozenset(teams))
    )


def entitlement(game, overrides, old):
    g = dict(game)
    service, evidence = None, None

    if g["sport"] == "NBA":
        service = "League Pass"
    elif g["sport"] == "MLB":
        service = "MLB.TV"
    elif g["sport"] == "MLS":
        service = "Apple TV"
    elif g["competition"] == "Women’s Champions League":
        service = "Disney+"
    elif nations_service(g):
        service = nations_service(g)
        evidence = "https://www.uefa.com/uefanationsleague/"
    elif nfl_service(g):
        service = nfl_service(g)
        evidence = NFL_TV_URL

    if service:
        g.update(service=service, broadcastVerified=True)
        if evidence:
            g["broadcastSource"] = evidence
    else:
        g.update(
            service="Check broadcaster",
            broadcastVerified=False,
        )

    override = overrides.get(g["id"])

    if isinstance(override, dict):
        svc = override.get("service")
        url = override.get("sourceUrl")

        if (
            svc in ALLOWED
            and isinstance(url, str)
            and url.startswith("https://")
        ):
            g.update(
                service=svc,
                broadcastVerified=True,
                broadcastSource=url,
            )

    elif g["id"] in old:
        prior = old[g["id"]]

        if (
            prior.get("broadcastVerified") is True
            and prior.get("service") in ALLOWED
            and str(prior.get("broadcastSource", ""))
            .startswith("https://")
        ):
            g.update(
                service=prior["service"],
                broadcastVerified=True,
                broadcastSource=prior["broadcastSource"],
            )

    return g


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.depth = 0
        self.cells = []
        self.current = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.depth += 1
            if self.depth == 1:
                self.cells = []
        elif tag in ("td", "th") and self.depth:
            self.in_cell = True
            self.current = []

    def handle_data(self, data):
        if self.in_cell:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.cells.append(
                " ".join(" ".join(self.current).split())
            )
            self.in_cell = False
        elif tag == "tr" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.cells:
                self.rows.append(self.cells)


def rugby_from_tv_guide(today, end):
    try:
        raw = download(GUIDE_URL)
    except Exception as exc:
        print(
            f"INFO: UK rugby TV guide unavailable: {exc}",
            flush=True,
        )
        return []

    parser = TableRows()
    parser.feed(raw)
    out = []

    monthnames = {
        m.lower(): i
        for i, m in enumerate(
            (
                "January", "February", "March", "April",
                "May", "June", "July", "August",
                "September", "October", "November",
                "December",
            ),
            1,
        )
    }

    for cells in parser.rows:
        joined = " ".join(cells)

        if not re.search(
            r"\bITVX\b|\bBBC iPlayer\b", joined, re.I
        ):
            continue

        date_match = re.search(
            r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"([A-Za-z]+)\s+(\d{4})\s+"
            r"(\d{1,2}):(\d{2})",
            joined,
            re.I,
        )

        if not date_match:
            continue

        dd, month, year, hh, mm = date_match.groups()

        if month.lower() not in monthnames:
            continue

        try:
            date = dt.date(
                int(year),
                monthnames[month.lower()],
                int(dd),
            )
        except ValueError:
            continue

        if not today <= date <= end:
            continue

        match = re.search(
            r"([A-Za-z][A-Za-z .'-]+?)\s+"
            r"v(?:s\.?)?\s+"
            r"([A-Za-z][A-Za-z .'-]+?)"
            r"(?=\s+(?:Nations|Rugby|Fri|Sat|Sun|"
            r"Mon|Tue|Wed|Thu|\d)|$)",
            joined,
            re.I,
        )

        if not match:
            continue

        home, away = (
            s.strip() for s in match.groups()
        )

        if len(home) > 45 or len(away) > 45:
            continue

        service = (
            "ITVX"
            if re.search(r"\bITVX\b", joined, re.I)
            else "BBC iPlayer"
        )

        out.append(
            {
                "id": (
                    f"ukrugby:{date}:"
                    f"{re.sub('[^a-z0-9]+', '-', home.lower())}:"
                    f"{re.sub('[^a-z0-9]+', '-', away.lower())}"
                ),
                "date": date.isoformat(),
                "time": f"{int(hh):02d}:{mm}",
                "sport": "Rugby",
                "competition": "Rugby Union",
                "title": f"{home} vs {away}",
                "service": service,
                "source": "UK rugby TV guide",
                "broadcastVerified": True,
                "broadcastSource": GUIDE_URL,
            }
        )

    print(
        f"UK rugby TV guide: {len(out)} parsable fixtures",
        flush=True,
    )
    return out


# Updated URLs for tennis, rugby league and club rugby.
EXTRA_GUIDES = (
    (
        "Tennis",
        "https://www.wheresthematch.com/live-tennis-on-tv/",
    ),
    (
        "Rugby League",
        "https://www.wheresthematch.com/live-rugby-league-on-tv/",
    ),
    (
        "Rugby",
        "https://www.wheresthematch.com/gallagher-premiership-rugby-on-tv/",
    ),
    (
        "Rugby",
        "https://www.wheresthematch.com/live-rugby-union-on-tv/",
    ),
)

MONTH_NUMBERS = {
    m.lower(): i
    for i, m in enumerate(
        (
            "January", "February", "March", "April",
            "May", "June", "July", "August",
            "September", "October", "November",
            "December",
        ),
        1,
    )
}


def free_service(broadcasters):
    """Identify only explicitly listed free UK broadcasters."""
    b = " ".join(broadcasters)

    if re.search(
        r"BBC\s*iPlayer|BBC\s*Sport\s*Website|"
        r"BBC\s*(?:One|Two|1|2)(?!\d)",
        b, re.I,
    ):
        return "BBC iPlayer"

    if re.search(
        r"ITVX|ITV\s*[14](?!\d)",
        b, re.I,
    ):
        return "ITVX"

    if re.search(
        r"Channel\s*4(?!\d)",
        b, re.I,
    ):
        return "Channel 4"

    if re.search(
        r"5Action",
        b, re.I,
    ):
        return "5Action"

    if re.search(
        r"Channel\s*5(?!\d)",
        b, re.I,
    ):
        return "Channel 5"

    return None


def extra_free_sport_from_guide(sport, url, today, end):
    """Read fixture rows and retain only free UK broadcasts."""
    try:
        raw = download(url)
        parser = TableRows()
        parser.feed(raw)

    except Exception as exc:
        print(
            f"WARNING: {sport} TV guide unavailable "
            f"({url}): {exc}",
            flush=True,
        )
        return []

    out = []
    dated = 0

    date_pattern = re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"([A-Za-z]+)\s+(20\d{2})\s+"
        r"(\d{1,2}):(\d{2})",
        re.I,
    )

    for cells in parser.rows:
        if len(cells) < 3:
            continue

        # Expected columns:
        # Fixture | Date/time | Competition | Broadcasters
        date_cell = next(
            (
                c for c in cells[1:-1]
                if date_pattern.search(c)
            ),
            None,
        )

        if not date_cell:
            continue

        match = date_pattern.search(date_cell)
        dd, month, year, hour, minute = match.groups()

        try:
            date = dt.date(
                int(year),
                MONTH_NUMBERS[month.lower()],
                int(dd),
            )
        except (KeyError, ValueError):
            continue

        if not today <= date <= end:
            continue

        dated += 1

        # Only inspect the broadcaster column.
        service = free_service(cells[-1:])

        if not service:
            continue

        title = re.sub(
            r"\s+", " ", cells[0]
        ).strip()

        title = re.sub(
            r"\s*Image.*$",
            "",
            title,
            flags=re.I,
        ).strip()

        if not 4 <= len(title) <= 130:
            continue

        competition_cell = " ".join(
            cells[2:-1]
        ).strip()

        if sport == "Tennis":
            if not re.search(
                r"tennis|ATP|WTA|Wimbledon|Grand Slam",
                title + " " + competition_cell,
                re.I,
            ):
                continue

            competition = (
                competition_cell or "Tennis"
            )

        elif sport == "Rugby League":
            if not re.search(
                r"rugby league|super league|challenge cup|NRL",
                title + " " + competition_cell,
                re.I,
            ):
                continue

            competition = (
                competition_cell or "Rugby League"
            )

        else:
            if not re.search(
                r"\b(v|vs)\b",
                title,
                re.I,
            ):
                continue

            if re.search(
                r"Nations Championship|International|"
                r"Six Nations|World Cup",
                competition_cell,
                re.I,
            ):
                continue

            competition = (
                competition_cell
                or "Club Rugby / Rugby Union"
            )

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            title.lower(),
        ).strip("-")[:90]

        identifier = (
            f"freeguide:"
            f"{sport.lower().replace(' ', '-')}:"
            f"{date}:{hour}:{minute}:{slug}"
        )

        out.append(
            {
                "id": identifier,
                "date": date.isoformat(),
                "time": f"{int(hour):02d}:{minute}",
                "sport": sport,
                "competition": competition,
                "title": title,
                "service": service,
                "broadcastVerified": True,
                "broadcastSource": url,
                "source": "UK free-to-air TV listing",
            }
        )

    print(
        f"{sport} TV guide: "
        f"{len(parser.rows)} table rows; "
        f"{dated} dated upcoming fixtures; "
        f"{len(out)} free UK fixtures ({url})",
        flush=True,
    )

    if not parser.rows:
        print(
            f"WARNING: {sport} guide returned no HTML "
            f"table rows; website layout may have changed",
            flush=True,
        )

    return out


def add_extra_free_sports(merged, today, end):
    existing = {
        (
            g.get("sport", "").casefold(),
            g.get("date"),
            re.sub(
                r"[^a-z0-9]+",
                "",
                g.get("title", "").casefold(),
            ),
        )
        for g in merged.values()
    }

    added = {}

    for sport, url in EXTRA_GUIDES:
        count = 0

        for g in extra_free_sport_from_guide(
            sport, url, today, end
        ):
            k = (
                sport.casefold(),
                g["date"],
                re.sub(
                    r"[^a-z0-9]+",
                    "",
                    g["title"].casefold(),
                ),
            )

            if k in existing:
                continue

            merged[g["id"]] = g
            existing.add(k)
            count += 1

        added[sport] = added.get(sport, 0) + count

    print(
        "Extra free sports added: " + repr(added),
        flush=True,
    )


def rugby_2026(today, end):
    out = []

    for md, tm, home, away in RUGBY_2026 + RUGBY_FINALS:
        date = dt.date.fromisoformat("2026-" + md)

        if not today <= date <= end:
            continue

        finals = (
            md, tm, home, away
        ) in RUGBY_FINALS

        out.append(
            {
                "id": (
                    f"nationschampionship:2026:{md}:{tm}"
                ),
                "date": date.isoformat(),
                "time": tm,
                "sport": "Rugby",
                "competition": (
                    "Nations Championship Finals"
                    if finals
                    else "Nations Championship"
                ),
                "title": f"{home} vs {away}",
                "service": "ITVX",
                "broadcastVerified": True,
                "broadcastSource": RUGBY_TV_URL,
                "source": (
                    "Published 2026 Nations Championship schedule"
                ),
            }
        )

    return out


def merge_curated(merged, entries, today, end):
    applied = 0

    for e in entries:
        if not isinstance(e, dict):
            continue

        required = (
            "id", "date", "time", "sport",
            "competition", "title", "service", "sourceUrl",
        )

        if not all(
            isinstance(e.get(k), str) and e[k].strip()
            for k in required
        ):
            continue

        if not (
            today.isoformat()
            <= e["date"]
            <= end.isoformat()
        ):
            continue

        if (
            e["service"] not in ALLOWED
            or not e["sourceUrl"].startswith("https://")
        ):
            continue

        existing = next(
            (
                g for g in merged.values()
                if (
                    g.get("sport") == e["sport"]
                    and g.get("date") == e["date"]
                    and g.get("title", "").casefold()
                    == e["title"].casefold()
                )
            ),
            None,
        )

        if existing:
            existing.update(
                service=e["service"],
                broadcastVerified=True,
                broadcastSource=e["sourceUrl"],
            )
        else:
            merged[e["id"]] = {
                k: e[k]
                for k in (
                    "id", "date", "time", "sport",
                    "competition", "title", "service",
                )
            }

            merged[e["id"]].update(
                source="Verified UK broadcast list",
                broadcastVerified=True,
                broadcastSource=e["sourceUrl"],
            )

        applied += 1

    return applied


PRIME_UCL_GUIDE = (
    "https://www.live-footballontv.com/"
    "live-champions-league-football-on-tv.html"
)

PRIME_UCL_CONFIRMED = {
    ("2026-11-24", "arsenal", "borussia dortmund"),
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(html.unescape(data.strip()))


def normalize_club(name):
    name = name.casefold()
    name = re.sub(
        r"\b(fc|cf|afc|ssc|fk|rc|ac|club)\b",
        "",
        name,
    )
    name = re.sub(
        r"[^a-z0-9]+", " ", name
    ).strip()

    aliases = {
        "bvb": "borussia dortmund",
        "dortmund": "borussia dortmund",
        "arsenal fc": "arsenal",
        "man city": "manchester city",
        "man utd": "manchester united",
        "psg": "paris saint germain",
        "inter milan": "internazionale",
        "inter": "internazionale",
        "atletico madrid": "atletico madrid",
    }

    return aliases.get(name, name)


def prime_ucl_from_uk_guide(today, end):
    selections = set(PRIME_UCL_CONFIRMED)

    try:
        raw = download(PRIME_UCL_GUIDE)
        parser = PlainText()
        parser.feed(raw)

        lines = [
            re.sub(r"\s+", " ", x).strip()
            for x in parser.parts
        ]

        month_names = {
            name.lower(): i
            for i, name in enumerate(
                (
                    "January", "February", "March",
                    "April", "May", "June",
                    "July", "August", "September",
                    "October", "November", "December",
                ),
                1,
            )
        }

        date_re = re.compile(
            r"^(?:Monday|Tuesday|Wednesday|Thursday|"
            r"Friday|Saturday|Sunday)\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"([A-Za-z]+)\s+(20\d{2})$",
            re.I,
        )

        current_date = None

        for i, line in enumerate(lines):
            match = date_re.match(line)

            if match:
                day, month, year = match.groups()

                try:
                    current_date = dt.date(
                        int(year),
                        month_names[month.lower()],
                        int(day),
                    )
                except (KeyError, ValueError):
                    current_date = None

                continue

            if (
                not current_date
                or not today <= current_date <= end
            ):
                continue

            fixture = re.match(
                r"^(.{2,70}?)\s+v\s+(.{2,70}?)$",
                line,
                re.I,
            )

            if not fixture:
                continue

            next_lines = lines[i + 1:i + 12]
            rights = []

            for next_line in next_lines:
                if (
                    date_re.match(next_line)
                    or re.match(
                        r"^.{2,70}\s+v\s+.{2,70}$",
                        next_line,
                    )
                ):
                    break

                rights.append(next_line)

            if not any(
                "amazon prime video" in x.casefold()
                for x in rights
            ):
                continue

            home, away = fixture.groups()

            selections.add(
                (
                    current_date.isoformat(),
                    normalize_club(home),
                    normalize_club(away),
                )
            )

    except Exception as exc:
        print(
            "INFO: Prime UK guide unavailable; "
            f"using saved selections only: {exc}",
            flush=True,
        )

    return selections


def apply_prime_ucl(merged, today, end):
    selections = prime_ucl_from_uk_guide(today, end)
    applied = 0

    for g in merged.values():
        if g.get("competition") != "Champions League":
            continue

        teams = g.get("title", "").split(" at ")

        if len(teams) != 2:
            continue

        away, home = [
            normalize_club(t)
            for t in teams
        ]

        if (
            g["date"], home, away
        ) in selections:
            g.update(
                service="Prime Video",
                broadcastVerified=True,
                broadcastSource=PRIME_UCL_GUIDE,
            )
            applied += 1

    print(
        "Prime Video Champions League "
        f"broadcasts applied: {applied}",
        flush=True,
    )

    return applied


def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)

    days = [
        today + dt.timedelta(days=n)
        for n in range(35)
    ]

    previous = read_json(OUT, {})

    if not isinstance(previous, dict):
        previous = {}

    old = {
        g["id"]: g
        for g in previous.get("items", [])
        if (
            isinstance(g, dict)
            and isinstance(g.get("id"), str)
        )
    }

    overrides = read_json(OVERRIDES, {})

    if not isinstance(overrides, dict):
        overrides = {}

    jobs = [
        (*feed, day, today, end)
        for feed in FEEDS
        for day in days
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(fetch, jobs))

    successes = [
        r for r in results if r[2]
    ]
    failures = [
        r for r in results if not r[2]
    ]

    for path, day, _, _, error in failures:
        print(
            f"FAILED {path} ({day}): {error}",
            flush=True,
        )

    if not successes:
        raise RuntimeError(
            "All ESPN feeds failed; "
            "existing schedule unchanged"
        )

    merged = {}

    for _, _, _, games, _ in successes:
        for game in games:
            merged[game["id"]] = entitlement(
                game, overrides, old
            )

    success_ids = {
        (path, day)
        for path, day, ok, _, _ in successes
    }

    for gid, g in old.items():
        date = g.get("date", "")

        if (
            not isinstance(date, str)
            or not (
                today.isoformat()
                <= date
                <= end.isoformat()
            )
            or gid in merged
        ):
            continue

        if gid.startswith("espn:"):
            try:
                path = gid.split(":", 2)[1]
                local = dt.date.fromisoformat(date)
            except (ValueError, IndexError):
                continue

            nearby = (
                local - dt.timedelta(days=1),
                local,
            )

            if not all(
                (path, d.isoformat()) in success_ids
                for d in nearby
                if d >= today
            ):
                merged[gid] = entitlement(
                    g, overrides, old
                )

        elif not gid.startswith(
            (
                "nationschampionship:",
                "ukrugby:",
                "freeguide:",
            )
        ):
            merged[gid] = g

    rugby = rugby_2026(today, end)

    known = {
        (
            g["date"],
            frozenset(
                re.split(
                    r"\s+vs\s+",
                    g["title"].casefold(),
                )
            ),
        )
        for g in rugby
    }

    for g in rugby_from_tv_guide(today, end):
        matchkey = (
            g["date"],
            frozenset(
                re.split(
                    r"\s+vs\s+",
                    g["title"].casefold(),
                )
            ),
        )

        if matchkey not in known:
            rugby.append(g)
            known.add(matchkey)

    for g in rugby:
        merged[g["id"]] = g

    print(
        f"Rugby fixtures added: {len(rugby)}",
        flush=True,
    )

    add_extra_free_sports(
        merged, today, end
    )

    apply_prime_ucl(
        merged, today, end
    )

    curated = read_json(CURATED, [])

    if not isinstance(curated, list):
        curated = []

    applied = merge_curated(
        merged, curated, today, end
    )

    print(
        f"Curated UK broadcasts applied: {applied}",
        flush=True,
    )

    print(
        "Built-in UK NFL broadcasts applied: "
        + str(
            sum(
                bool(nfl_service(g))
                for g in merged.values()
            )
        ),
        flush=True,
    )

    coverage = [
        {
            "feed": path,
            "date": day,
            "ok": ok,
            **(
                {"error": error[:180]}
                if error
                else {}
            ),
        }
        for path, day, ok, _, error in sorted(
            results,
            key=lambda r: (r[0], r[1]),
        )
    ]

    payload = {
        "updatedAt": (
            dt.datetime.now(dt.timezone.utc)
            .isoformat()
        ),
        "successfulChecks": len(successes),
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
            "MLB.TV assumed; tennis, rugby union "
            "and rugby league included only when "
            "a free UK broadcaster is explicitly "
            "listed in a parseable guide row."
        ),
    }

    temp = OUT.with_suffix(".json.tmp")

    temp.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    temp.replace(OUT)

    watchable_count = sum(
        g.get("broadcastVerified") is True
        for g in merged.values()
    )

    print(
        f"Updated: {len(merged)} fixtures; "
        f"{len(successes)}/{len(results)} "
        f"checks succeeded; "
        f"{watchable_count} watchable",
        flush=True,
    )


if __name__ == "__main__":
    main()
