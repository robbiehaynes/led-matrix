"""
Bench test: today's fixtures/scores across Premier League, Championship,
and League One via ESPN's public (unofficial) scoreboard endpoint.

This replaced the earlier football-data.org approach: that API's free tier
is delayed (~5-10min) and doesn't cover League One at all. ESPN's endpoint
is undocumented/unofficial but free, genuinely live, and covers all three.

Run: python3 bench/bench_football.py
"""
import sys
import os
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.common import report_size

LEAGUES = [
    ("eng.1", "Premier League"),
    ("eng.2", "Championship"),
    ("eng.3", "League One"),
    ("eng.league_cup", "Carabao Cup"),
    ("uefa.champions", "Champions League"),
]


def fetch_scoreboard(league_code):
    # Without an explicit date, ESPN falls back to the most recent matchday
    # when nothing's on today -- wrong for competitions with gaps between
    # rounds (confirmed on Champions League showing a 5-day-old matchday).
    today = datetime.date.today().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/scoreboard?dates={today}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    report_size(f"football-{league_code}", resp)
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
    # pre-match: ESPN only gives kickoff time in US Eastern (detail field)
    # with no way to request UK time -- showing it as-is would be actively
    # wrong for a UK wall display, so just show "Scheduled" instead.
    return type_.get("shortDetail", "")


def reduce_scoreboard(data):
    matches = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        home, away = comp["competitors"][0], comp["competitors"][1]
        # ESPN lists competitors in [home, away] or reverse; homeAway field is authoritative
        if home.get("homeAway") != "home":
            home, away = away, home
        matches.append({
            "home": home["team"]["shortDisplayName"],
            "away": away["team"]["shortDisplayName"],
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "status": _status_text(comp["status"]),
        })
    return matches


if __name__ == "__main__":
    for code, name in LEAGUES:
        print(f"\n=== {name} ({code}) ===")
        data = fetch_scoreboard(code)
        matches = reduce_scoreboard(data)
        if not matches:
            print("  No matches today")
            continue
        for m in matches:
            print(f"  {m['home']} {m['home_score']}-{m['away_score']} {m['away']}  [{m['status']}]")
