"""
Fetch rugby data from the local relay running on the Raspberry Pi
(see relay/football_relay.py), rather than ESPN directly.

Same reasoning as football.py: ESPN's API sits behind Akamai bot-protection
that blocks the MatrixPortal's ESP32 AirLift co-processor at the TLS
handshake level, so the relay (a normal machine, using curl) fetches ESPN
on the device's behalf and re-serves a tiny reduced JSON over plain
local-network HTTP.

Covers URC, Premiership, Champions Cup, Challenge Cup, and an
"Internationals" feed filtered to just South Africa/England matches (see
RUGBY_INTERNATIONAL_TEAMS in the relay) -- the league list itself lives
solely on the relay, same as football.
"""
from config import FOOTBALL_RELAY_URL  # relay serves football and rugby both

RUGBY_RELAY_URL = FOOTBALL_RELAY_URL.rsplit("/", 1)[0] + "/rugby"


def fetch_and_reduce(requests):
    """Returns a list of (league_name, matches) tuples, one per league."""
    response = requests.get(RUGBY_RELAY_URL)
    try:
        data = response.json()
    finally:
        response.close()

    return [(league["league"], league["matches"]) for league in data.get("leagues", [])]
