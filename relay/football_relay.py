"""
Sports relay: runs on a normal machine (Raspberry Pi) on the home network,
fetches football and rugby data from ESPN's hidden scoreboard API on its
own schedule, and serves small reduced JSON payloads over plain HTTP to
the MatrixPortal.

Why this exists: ESPN's API sits behind Akamai bot-protection that blocks
the MatrixPortal's ESP32 AirLift co-processor at the TLS handshake level
(confirmed via direct hardware testing -- not fixable with HTTP headers).
A normal machine's TLS stack isn't blocked, so it fetches ESPN on the
device's behalf and re-serves a tiny payload over plain local-network HTTP,
which the AirLift has no trouble with. It also fetches with an explicit
date, since ESPN's default scoreboard query falls back to the most recent
matchday when nothing's on today -- wrong for competitions with gaps
between rounds (confirmed on both football's Champions League and rugby's
club competitions, which don't play every day).

Stdlib only -- no pip install needed on the Pi.
"""
import json
import time
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = 8090
REFRESH_SECONDS = 20  # how often *this relay* polls ESPN

FOOTBALL_LEAGUES = [
    ("eng.1", "Premier League"),
    ("eng.2", "Championship"),
    ("eng.3", "League One"),
    ("eng.league_cup", "Carabao Cup"),
    ("uefa.champions", "Champions League"),
]

# Rugby uses ESPN's numeric league ids (found via the site's league
# dropdown), not the alpha codes football's soccer endpoints use.
RUGBY_CLUB_LEAGUES = [
    (270557, "URC"),
    (267979, "Premiership"),
    (271937, "Champions Cup"),
    (272073, "Challenge Cup"),
]

# Internationals aren't a single ESPN league: general Tests/Rugby
# Championship live under 289234, but Six Nations is a separate id
# (confirmed: Springboks games only ever appear under 289234; England's
# Six Nations games only appear under 180659, not 289234). Fetch both and
# filter to just the teams we care about.
RUGBY_INTERNATIONAL_LEAGUE_IDS = [289234, 180659]
RUGBY_INTERNATIONAL_TEAMS = {"South Africa", "England"}

_football_cache = {"data": [], "updated_at": 0}
_football_lock = threading.Lock()

_rugby_cache = {"data": [], "updated_at": 0}
_rugby_lock = threading.Lock()


def _status_text(status):
    type_ = status["type"]
    state = type_["state"]
    if state == "in":
        name = type_.get("name", "")
        if "HALFTIME" in name:
            return "HT"
        return status.get("displayClock") or type_.get("shortDetail", "")
    if state == "post":
        return "FT"
    # Pre-match: the display shows this statically (no scroll room to spare),
    # and we don't have a correct UK kickoff time anyway (see football.py),
    # so just use a compact placeholder instead of "Scheduled".
    return "-"


MAX_CARD_SLOTS = 3  # the display has room for three pixels per team

# A rugby yellow is a 10-minute sin-bin, so it only counts while it's being
# served. Football yellows (and all reds) stay for the whole match.
SIN_BIN_SECONDS = 600
HALF_SECONDS = 2400
# Set False to keep rugby yellows on screen for the whole match instead.
RUGBY_YELLOWS_ONLY_WHILE_ACTIVE = True

# event id -> (latest logged event time in game-seconds, wall time we saw it).
# ESPN's rugby status clock is unreliable (stuck on "second half, 1'" with
# tries logged at 66'), so the game clock is estimated from logged events.
_clock_anchors = {}


def _estimated_game_seconds(event_id, details, status_name):
    """
    Latest logged event time plus wall time elapsed since the relay first saw
    it, pinned at 40' through half time. Never earlier than the latest logged event, so a
    relay restart mid-match can't resurrect a yellow that has already expired.
    """
    latest = max((d.get("clock", {}).get("value") or 0 for d in details), default=0)
    now = time.time()
    anchor = _clock_anchors.get(event_id)
    if anchor is None or latest > anchor[0]:
        anchor = (latest, now)
    elif "HALFTIME" in status_name:
        # Half time is 40' by definition: pin the clock there and hold it.
        anchor = (max(anchor[0], HALF_SECONDS), now)
    _clock_anchors[event_id] = anchor
    return anchor[0] + (now - anchor[1])


def _rugby_minute_text(comp):
    """
    Live match minute for rugby, from the estimated clock. ESPN's own status
    clock is stuck (e.g. "second half, 1'" with tries logged at 66').
    """
    status = comp["status"]
    period = 2 if status.get("period", 1) >= 2 else 1
    seconds = _estimated_game_seconds(
        comp.get("id") or id(comp), comp.get("details") or [], status["type"].get("name", ""))
    seconds = min(max(seconds, HALF_SECONDS if period == 2 else 0), HALF_SECONDS * period)
    return f"{max(int(seconds // 60), 1)}'"


def _card_kind(detail):
    text = (detail.get("type") or {}).get("text", "").lower()
    if "red card" in text:
        return "R"
    if "yellow card" in text:
        return "Y"
    return None


def _player_key(detail):
    """Athlete id (display name as a fallback), or None if unknown."""
    athletes = detail.get("athletesInvolved") or []
    if not athletes:
        return None
    return athletes[0].get("id") or athletes[0].get("displayName")


def _card_strings(comp, home_id, away_id, rugby):
    """
    Returns (home_cards, away_cards): strings like "RYY", reds first, at
    most MAX_CARD_SLOTS long. A second yellow is logged as a yellow followed
    by a red for the same player, so that player's yellows are dropped and
    just the red shows.
    """
    details = comp.get("details") or []
    status = comp["status"]["type"]
    cards = []  # (kind, team_id, player_key, seconds)
    for d in details:
        kind = _card_kind(d)
        if kind:
            cards.append((kind, (d.get("team") or {}).get("id"), _player_key(d),
                          d.get("clock", {}).get("value") or 0))
    if not cards:
        return "", ""

    sent_off = {pk for kind, _, pk, _ in cards if kind == "R" and pk}
    cards = [c for c in cards if not (c[0] == "Y" and c[2] in sent_off)]

    if rugby and RUGBY_YELLOWS_ONLY_WHILE_ACTIVE:
        game_now = None
        if status["state"] == "in":
            game_now = _estimated_game_seconds(
                comp.get("id") or id(comp), details, status.get("name", ""))
        cards = [c for c in cards
                 if c[0] == "R" or (game_now is not None and game_now < c[3] + SIN_BIN_SECONDS)]

    def for_team(team_id):
        mine = sorted((c for c in cards if c[1] == team_id), key=lambda c: (c[0] != "R", c[3]))
        return "".join(c[0] for c in mine)[:MAX_CARD_SLOTS]

    return for_team(home_id), for_team(away_id)


def _reduce_event(event, rugby=False):
    comp = event["competitions"][0]
    home, away = comp["competitors"][0], comp["competitors"][1]
    if home.get("homeAway") != "home":
        home, away = away, home
    comp.setdefault("id", event.get("id"))
    status_text = _status_text(comp["status"])
    if rugby and comp["status"]["type"]["state"] == "in":
        # Always advance the clock (pins it at half time too); only the
        # minute text is skipped at HT.
        minute_text = _rugby_minute_text(comp)
        if status_text != "HT":
            status_text = minute_text
    home_cards, away_cards = _card_strings(comp, home["team"].get("id"), away["team"].get("id"), rugby)
    return {
        "home_cards": home_cards,
        "away_cards": away_cards,
        # 3-letter abbreviations, not full names -- the device renders
        # these on a static (non-scrolling) line with limited width.
        "home": home["team"]["abbreviation"],
        "away": away["team"]["abbreviation"],
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "status": status_text,
    }


def _curl_json(url):
    """
    Shell out to curl rather than using urllib/requests. ESPN's API sits
    behind Akamai bot-protection that fingerprints the TLS handshake --
    confirmed on this exact Pi that curl gets a clean 200 while Python's
    urllib gets a 403 "Access Denied" for the identical request. curl's
    TLS stack apparently isn't flagged; Python's ssl module is.
    """
    result = subprocess.run(
        ["curl", "-s", "-f", "--max-time", "15", url],
        capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _fetch_scoreboard(sport, league, today):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={today}"
    return _curl_json(url)


def fetch_all_football():
    today = time.strftime("%Y%m%d", time.gmtime())
    results = []
    for code, name in FOOTBALL_LEAGUES:
        data = _fetch_scoreboard("soccer", code, today)
        matches = [_reduce_event(e) for e in data.get("events", [])]
        results.append({"league": name, "matches": matches})
    return results


def _event_involves(event, team_names):
    comp = event["competitions"][0]
    names = {c["team"]["displayName"] for c in comp["competitors"]}
    return bool(names & team_names)


def fetch_all_rugby():
    today = time.strftime("%Y%m%d", time.gmtime())
    results = []

    for league_id, name in RUGBY_CLUB_LEAGUES:
        data = _fetch_scoreboard("rugby", league_id, today)
        matches = [_reduce_event(e, rugby=True) for e in data.get("events", [])]
        results.append({"league": name, "matches": matches})

    international_matches = []
    for league_id in RUGBY_INTERNATIONAL_LEAGUE_IDS:
        data = _fetch_scoreboard("rugby", league_id, today)
        for event in data.get("events", []):
            if _event_involves(event, RUGBY_INTERNATIONAL_TEAMS):
                international_matches.append(_reduce_event(event, rugby=True))
    results.append({"league": "Internationals", "matches": international_matches})

    return results


def refresh_loop(fetch_fn, cache, lock, label):
    while True:
        try:
            data = fetch_fn()
            with lock:
                cache["data"] = data
                cache["updated_at"] = time.time()
            print(f"[relay] {label} refreshed OK, {sum(len(l['matches']) for l in data)} matches total")
        except Exception as e:  # noqa: BLE001 -- keep the refresh loop alive
            print(f"[relay] {label} refresh failed: {e!r}")
        time.sleep(REFRESH_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep the systemd journal quiet; refresh loops already log

    def do_GET(self):
        if self.path == "/football":
            cache, lock = _football_cache, _football_lock
        elif self.path == "/rugby":
            cache, lock = _rugby_cache, _rugby_lock
        else:
            self.send_response(404)
            self.end_headers()
            return

        with lock:
            payload = json.dumps({
                "leagues": cache["data"],
                "updated_at": cache["updated_at"],
            }).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    threading.Thread(
        target=refresh_loop, args=(fetch_all_football, _football_cache, _football_lock, "football"),
        daemon=True,
    ).start()
    threading.Thread(
        target=refresh_loop, args=(fetch_all_rugby, _rugby_cache, _rugby_lock, "rugby"),
        daemon=True,
    ).start()
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    print(f"[relay] listening on :{LISTEN_PORT}, refreshing every {REFRESH_SECONDS}s")
    server.serve_forever()
