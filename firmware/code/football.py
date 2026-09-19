"""
Fetch football data from the local relay running on the Raspberry Pi
(see relay/football_relay.py), rather than ESPN directly.

Why: ESPN's API sits behind Akamai bot-protection that blocks the
MatrixPortal's ESP32 AirLift co-processor at the TLS handshake level
(confirmed via direct hardware testing) -- even a plain Python urllib
request gets the same 403 on a normal machine, while curl succeeds, so
this is Akamai fingerprinting TLS stacks, not something fixable with
headers. The relay (a normal machine, using curl) fetches ESPN on the
device's behalf and re-serves a tiny reduced JSON over plain local-network
HTTP, which sidesteps the problem entirely.
"""
from config import FOOTBALL_RELAY_URL


def fetch_and_reduce(requests):
    """Returns a list of (league_name, matches) tuples, one per league."""
    response = requests.get(FOOTBALL_RELAY_URL)
    try:
        data = response.json()
    finally:
        response.close()

    return [(league["league"], league["matches"]) for league in data.get("leagues", [])]
