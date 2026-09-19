"""
Bench test: today's fixtures/scores across URC, Premiership, Champions Cup,
Challenge Cup, and South Africa/England international matches, via ESPN's
public (unofficial) scoreboard endpoint.

Replaces the earlier TheSportsDB approach: that free tier has no live
scores at all (fixtures/last-result only). ESPN's endpoint is
undocumented/unofficial but free and genuinely live -- same source and
same relay pattern as football (see relay/football_relay.py).

Rugby uses ESPN's numeric league ids (found via the site's league
dropdown), not the alpha codes football's soccer endpoints use.
Internationals aren't a single ESPN league: general Tests/Rugby
Championship live under 289234, but Six Nations is a separate id
(confirmed: Springboks games only ever appear under 289234; England's Six
Nations games only appear under 180659, not 289234) -- fetch both and
filter to just the teams we care about.

Run: python3 bench/bench_rugby.py
"""
import sys
import os
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.common import report_size

CLUB_LEAGUES = [
    (270557, "URC"),
    (267979, "Premiership"),
    (271937, "Champions Cup"),
    (272073, "Challenge Cup"),
]

INTERNATIONAL_LEAGUE_IDS = [289234, 180659]
INTERNATIONAL_TEAMS = {"South Africa", "England"}


def fetch_scoreboard(league_id):
    # Without an explicit date, ESPN falls back to the most recent matchday
    # when nothing's on today -- confirmed wrong for these competitions,
    # which (unlike daily domestic football leagues) have gaps of days to
    # weeks between fixtures.
    today = datetime.date.today().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/rugby/{league_id}/scoreboard?dates={today}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    report_size(f"rugby-{league_id}", resp)
    return resp.json()


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
    return type_.get("shortDetail", "")


def reduce_event(event):
    comp = event["competitions"][0]
    home, away = comp["competitors"][0], comp["competitors"][1]
    if home.get("homeAway") != "home":
        home, away = away, home
    return {
        "home": home["team"]["shortDisplayName"],
        "away": away["team"]["shortDisplayName"],
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "status": _status_text(comp["status"]),
    }


def event_involves(event, team_names):
    comp = event["competitions"][0]
    names = {c["team"]["displayName"] for c in comp["competitors"]}
    return bool(names & team_names)


if __name__ == "__main__":
    for league_id, name in CLUB_LEAGUES:
        print(f"\n=== {name} ({league_id}) ===")
        data = fetch_scoreboard(league_id)
        matches = [reduce_event(e) for e in data.get("events", [])]
        if not matches:
            print("  No matches today")
            continue
        for m in matches:
            print(f"  {m['home']} {m['home_score']}-{m['away_score']} {m['away']}  [{m['status']}]")

    print("\n=== Internationals (South Africa / England) ===")
    found_any = False
    for league_id in INTERNATIONAL_LEAGUE_IDS:
        data = fetch_scoreboard(league_id)
        for event in data.get("events", []):
            if event_involves(event, INTERNATIONAL_TEAMS):
                found_any = True
                m = reduce_event(event)
                print(f"  {m['home']} {m['home_score']}-{m['away_score']} {m['away']}  [{m['status']}]")
    if not found_any:
        print("  No matches today")
