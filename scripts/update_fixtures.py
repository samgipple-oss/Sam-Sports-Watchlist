#!/usr/bin/env python3
"""Sports Watchlist: rolling UK fixtures, with verified UK viewing rights.

One-file updater; no third-party Python packages required.
ESPN supplies NBA/NFL/MLS/football schedules. The 2026 Nations Championship
schedule is sourced from published fixtures (not ESPN's broken rugby/164 API).
Future rugby matches can be discovered from a UK broadcast TV guide.
Unknown broadcast rights remain hidden rather than being guessed.
"""
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
RUGBY_SCHEDULE_URL = "https://www.autumn-internationals.co.uk/2026/"
RUGBY_TV_URL = "https://www.radiotimes.com/tv/sport/rugby-union/nations-championship-2026-tv/"
NFL_TV_URL = "https://www.radiotimes.com/tv/sport/nfl/live-nfl-today-tv/"
FEEDS = [
    ("NBA", "NBA", "basketball/nba", "League Pass"),
    ("NFL", "NFL", "football/nfl", "Check broadcaster"),
    ("MLS", "MLS", "soccer/usa.1", "Apple TV"),
    ("Football", "Champions League", "soccer/uefa.champions", "Check broadcaster"),
    ("Football", "Premier League", "soccer/eng.1", "Check broadcaster"),
    ("Football", "WSL", "soccer/eng.w.1", "Check broadcaster"),
    ("Football", "UEFA Nations League", "soccer/uefa.nations", "Check broadcaster"),
    ("Football", "Women’s Champions League", "soccer/uefa.wchampions", "Disney+"),
]
ALLOWED = {"League Pass", "Apple TV", "Disney+", "Prime", "Prime Video",
           "BBC iPlayer", "ITVX", "Channel 4", "Channel 5", "5Action", "Netflix"}

# Published 2026 Nations Championship fixture list, UK kick-off times.
# Competition-wide ITV/ITVX rights confirmed by UK TV schedules.
RUGBY_2026 = [
    ("11-06","20:10","Ireland","Argentina"),
    ("11-07","11:40","Italy","South Africa"),
    ("11-07","14:10","Scotland","New Zealand"),
    ("11-07","16:40","Wales","Japan"),
    ("11-07","20:10","France","Fiji"),
    ("11-08","15:10","England","Australia"),
    ("11-13","20:10","France","South Africa"),
    ("11-14","11:40","Italy","Argentina"),
    ("11-14","14:10","Wales","New Zealand"),
    ("11-14","16:40","England","Japan"),
    ("11-14","20:10","Ireland","Fiji"),
    ("11-15","15:10","Scotland","Australia"),
    ("11-21","14:10","England","New Zealand"),
    ("11-21","14:10","Scotland","Japan"),
    ("11-21","16:40","Ireland","South Africa"),
    ("11-21","16:40","Italy","Fiji"),
    ("11-21","20:10","France","Argentina"),
    ("11-21","20:10","Wales","Australia"),
]
# Finals have placeholder teams until determined, so use a descriptive title.
RUGBY_FINALS = [
    ("11-27","16:40","Northern 6","Southern 6"),
    ("11-27","20:10","Northern 3","Southern 3"),
    ("11-28","13:10","Northern 5","Southern 5"),
    ("11-28","16:40","Northern 2","Southern 2"),
    ("11-29","13:10","Northern 4","Southern 4"),
    ("11-29","16:40","Northern 1","Southern 1"),
]
# Specific previously identified Channel 5 NFL selections, NOT every NFL game.
NFL_FREE_2026 = {
    ("2026-11-08", frozenset(("new york jets","kansas city chiefs"))): "5Action",
    ("2026-11-08", frozenset(("green bay packers","new england patriots"))): "Channel 5",
}

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def download(url, timeout=18):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; SamSportsWatchlist/2.0)",
        "Accept": "text/html,application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")

def fetch(job):
    sport, competition, path, service, day, today, end = job
    url = ("https://site.api.espn.com/apis/site/v2/sports/" + path
           + "/scoreboard?" + urllib.parse.urlencode({
               "dates": day.strftime("%Y%m%d"), "limit": 300}))
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
                    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[0])
                    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[1])
                    when = dt.datetime.fromisoformat(event["date"].replace("Z","+00:00")).astimezone(TZ)
                    if not today <= when.date() <= end:
                        continue
                    def team(c):
                        obj = c.get("team") or {}
                        return obj.get("displayName") or obj.get("name") or "TBC"
                    games.append({
                        "id": f'espn:{path}:{event["id"]}',
                        "date": when.date().isoformat(),
                        "time": when.strftime("%H:%M"),
                        "sport": sport, "competition": competition,
                        "title": f"{team(away)} at {team(home)}",
                        "service": service, "source": "Scheduled data feed",
                        "liveStatus": event.get("status",{}).get("type",{}).get("description",""),
                    })
                except (KeyError, ValueError, TypeError, IndexError, AttributeError):
                    continue
            return path, day.isoformat(), True, games, None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(.4 * (attempt + 1))
    return path, day.isoformat(), False, [], error

def nations_service(g):
    if g.get("competition") != "UEFA Nations League":
        return None
    teams = [t.strip().casefold() for t in g.get("title","").split(" at ")]
    if "england" in teams:
        return "ITVX"
    if any(t in teams for t in ("scotland","wales","northern ireland")):
        return "BBC iPlayer"
    return None

def nfl_service(g):
    if g.get("sport") != "NFL":
        return None
    teams = g.get("title","").casefold().split(" at ")
    if len(teams) != 2:
        return None
    return NFL_FREE_2026.get((g["date"], frozenset(teams)))

def entitlement(game, overrides, old):
    g = dict(game)
    service, evidence = None, None
    if g["sport"] == "NBA":
        service = "League Pass"
    elif g["sport"] == "MLS":
        service = "Apple TV"
    elif g["competition"] == "Women’s Champions League":
        service = "Disney+"
    elif nations_service(g):
        service, evidence = nations_service(g), "https://www.uefa.com/uefanationsleague/"
    elif nfl_service(g):
        service, evidence = nfl_service(g), NFL_TV_URL
    if service:
        g.update(service=service, broadcastVerified=True)
        if evidence:
            g["broadcastSource"] = evidence
    else:
        g.update(service="Check broadcaster", broadcastVerified=False)
    override = overrides.get(g["id"])
    if isinstance(override, dict):
        svc, url = override.get("service"), override.get("sourceUrl")
        if svc in ALLOWED and isinstance(url,str) and url.startswith("https://"):
            g.update(service=svc,broadcastVerified=True,broadcastSource=url)
    elif g["id"] in old:
        prior = old[g["id"]]
        if (prior.get("broadcastVerified") is True
                and prior.get("service") in ALLOWED
                and str(prior.get("broadcastSource","")).startswith("https://")):
            g.update(service=prior["service"],broadcastVerified=True,
                     broadcastSource=prior["broadcastSource"])
    return g

class TableRows(HTMLParser):
    """Extract human-readable <tr> contents without third-party dependencies."""
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
        elif tag in ("td","th") and self.depth:
            self.in_cell = True
            self.current = []
    def handle_data(self, data):
        if self.in_cell:
            self.current.append(data)
    def handle_endtag(self, tag):
        if tag in ("td","th") and self.in_cell:
            self.cells.append(" ".join(" ".join(self.current).split()))
            self.in_cell = False
        elif tag == "tr" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.cells:
                self.rows.append(self.cells)

def rugby_from_tv_guide(today, end):
    """Best-effort discovery of additional rugby internationals with UK TV rights.
    Fail closed if the provider changes markup or broadcast details are unclear.
    """
    try:
        raw = download(GUIDE_URL)
    except Exception as exc:
        print(f"INFO: UK rugby TV guide unavailable: {exc}", flush=True)
        return []
    parser = TableRows()
    parser.feed(raw)
    out = []
    monthnames = {m.lower():i for i,m in enumerate(
        ("January","February","March","April","May","June","July",
         "August","September","October","November","December"),1)}
    for cells in parser.rows:
        joined = " ".join(cells)
        if not re.search(r"\bITVX\b|\bBBC iPlayer\b", joined, re.I):
            continue
        date_match = re.search(
            r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"([A-Za-z]+)\s+(\d{4})\s+(\d{1,2}):(\d{2})", joined, re.I)
        if not date_match:
            continue
        dd, month, year, hh, mm = date_match.groups()
        if month.lower() not in monthnames:
            continue
        try:
            date = dt.date(int(year),monthnames[month.lower()],int(dd))
        except ValueError:
            continue
        if not today <= date <= end:
            continue
        match = re.search(r"([A-Za-z][A-Za-z .'-]+?)\s+v(?:s\.?)?\s+([A-Za-z][A-Za-z .'-]+?)(?=\s+(?:Nations|Rugby|Fri|Sat|Sun|Mon|Tue|Wed|Thu|\d)|$)", joined, re.I)
        if not match:
            continue
        home, away = (s.strip() for s in match.groups())
        if len(home)>45 or len(away)>45:
            continue
        service = "ITVX" if re.search(r"\bITVX\b",joined,re.I) else "BBC iPlayer"
        out.append({
            "id": f"ukrugby:{date}:{re.sub('[^a-z0-9]+','-',home.lower())}:{re.sub('[^a-z0-9]+','-',away.lower())}",
            "date": date.isoformat(), "time": f"{int(hh):02d}:{mm}",
            "sport": "Rugby", "competition": "Rugby Union",
            "title": f"{home} vs {away}", "service": service,
            "source": "UK rugby TV guide", "broadcastVerified": True,
            "broadcastSource": GUIDE_URL,
        })
    print(f"UK rugby TV guide: {len(out)} parsable fixtures", flush=True)
    return out

def rugby_2026(today,end):
    out = []
    for md,tm,home,away in RUGBY_2026 + RUGBY_FINALS:
        date = dt.date.fromisoformat("2026-"+md)
        if not today <= date <= end:
            continue
        finals = (md,tm,home,away) in RUGBY_FINALS
        out.append({
            "id": f"nationschampionship:2026:{md}:{tm}",
            "date": date.isoformat(), "time": tm,
            "sport": "Rugby",
            "competition": "Nations Championship Finals" if finals else "Nations Championship",
            "title": f"{home} vs {away}",
            "service": "ITVX", "broadcastVerified": True,
            "broadcastSource": RUGBY_TV_URL,
            "source": "Published 2026 Nations Championship schedule",
        })
    return out

def merge_curated(merged, entries, today, end):
    applied = 0
    for e in entries:
        if not isinstance(e,dict) or not all(
            isinstance(e.get(k),str) and e[k].strip()
            for k in ("id","date","time","sport","competition","title","service","sourceUrl")
        ):
            continue
        if not today.isoformat() <= e["date"] <= end.isoformat():
            continue
        if e["service"] not in ALLOWED or not e["sourceUrl"].startswith("https://"):
            continue
        existing = next((g for g in merged.values()
            if g.get("sport")==e["sport"] and g.get("date")==e["date"]
            and g.get("title","").casefold()==e["title"].casefold()), None)
        if existing:
            existing.update(service=e["service"],broadcastVerified=True,
                            broadcastSource=e["sourceUrl"])
        else:
            merged[e["id"]] = {k:e[k] for k in
                ("id","date","time","sport","competition","title","service")}
            merged[e["id"]].update(source="Verified UK broadcast list",
                broadcastVerified=True,broadcastSource=e["sourceUrl"])
        applied += 1
    return applied

def main():
    today = dt.datetime.now(TZ).date()
    end = today + dt.timedelta(days=34)
    days = [today + dt.timedelta(days=n) for n in range(35)]
    previous = read_json(OUT,{})
    if not isinstance(previous,dict):
        previous = {}
    old = {g["id"]:g for g in previous.get("items",[])
           if isinstance(g,dict) and isinstance(g.get("id"),str)}
    overrides = read_json(OVERRIDES,{})
    if not isinstance(overrides,dict):
        overrides = {}
    jobs = [(*feed,day,today,end) for feed in FEEDS for day in days]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(fetch,jobs))
    successes = [r for r in results if r[2]]
    failures = [r for r in results if not r[2]]
    for path,day,_,_,error in failures:
        print(f"FAILED {path} ({day}): {error}",flush=True)
    if not successes:
        raise RuntimeError("All ESPN feeds failed; existing schedule unchanged")
    merged = {}
    for _,_,_,games,_ in successes:
        for game in games:
            merged[game["id"]] = entitlement(game,overrides,old)
    success_ids = {(path,day) for path,day,ok,_,_ in successes}
    for gid,g in old.items():
        date = g.get("date","")
        if not isinstance(date,str) or not today.isoformat()<=date<=end.isoformat() or gid in merged:
            continue
        if gid.startswith("espn:"):
            try:
                path = gid.split(":",2)[1]
                local = dt.date.fromisoformat(date)
            except (ValueError,IndexError):
                continue
            nearby = (local-dt.timedelta(days=1),local)
            if not all((path,d.isoformat()) in success_ids for d in nearby if d>=today):
                merged[gid] = entitlement(g,overrides,old)
        elif not gid.startswith(("nationschampionship:","ukrugby:")):
            merged[gid] = g

    # Reliable published 2026 fixtures are the fallback when ESPN's rugby API
    # returns 400; also discover future UK TV-listed rugby matches.
    rugby = rugby_2026(today,end)
    known = {(g["date"],frozenset(re.split(r"\s+vs\s+",g["title"].casefold()))) for g in rugby}
    for g in rugby_from_tv_guide(today,end):
        matchkey = (g["date"],frozenset(re.split(r"\s+vs\s+",g["title"].casefold())))
        if matchkey not in known:
            rugby.append(g)
            known.add(matchkey)
    for g in rugby:
        merged[g["id"]] = g
    print(f"Rugby fixtures added: {len(rugby)}",flush=True)

    curated = read_json(CURATED,[])
    if not isinstance(curated,list):
        curated = []
    applied = merge_curated(merged,curated,today,end)
    print(f"Curated UK broadcasts applied: {applied}",flush=True)
    print(f"Built-in UK NFL broadcasts applied: {sum(bool(nfl_service(g)) for g in merged.values())}",flush=True)
    coverage = [{"feed":path,"date":day,"ok":ok,
                 **({"error":error[:180]} if error else {})}
                for path,day,ok,_,error in sorted(results,key=lambda r:(r[0],r[1]))]
    payload = {
        "updatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),
        "successfulChecks":len(successes),
        "totalChecks":len(results),
        "items":sorted(merged.values(),key=lambda g:
            (g.get("date",""),g.get("time",""),g.get("title",""))),
        "coverage":coverage,
        "note":"UK rugby Nations Championship fixtures use published 2026 schedule and ITVX rights; other UK TV rights require verification.",
    }
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(OUT)
    print(f'Updated: {len(merged)} fixtures; {len(successes)}/{len(results)} checks succeeded; '
          f'{sum(g.get("broadcastVerified") is True for g in merged.values())} watchable',flush=True)

if __name__ == "__main__":
    main()
