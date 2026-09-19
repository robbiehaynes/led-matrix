"""
Bench test: find the closest aircraft to HOME_LAT/HOME_LON using OpenSky's
free, anonymous /states/all bounding-box endpoint.

Run: python3 bench/bench_planes.py
"""
import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    HOME_LAT,
    HOME_LON,
    PLANE_BBOX_DEGREES,
    OPENSKY_CLIENT_ID,
    OPENSKY_CLIENT_SECRET,
)
from bench.common import haversine_km, report_size

OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)

_token_cache = {}


def get_opensky_token():
    """Returns a bearer token if OPENSKY_CLIENT_ID/SECRET are set, else None."""
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        return None

    now = time.monotonic()
    cached = _token_cache.get("access_token")
    if cached and now < _token_cache["expires_at"] - 60:
        return cached

    resp = requests.post(
        OPENSKY_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": OPENSKY_CLIENT_ID,
            "client_secret": OPENSKY_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 1800)
    return _token_cache["access_token"]


def fetch_states():
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": HOME_LAT - PLANE_BBOX_DEGREES,
        "lamax": HOME_LAT + PLANE_BBOX_DEGREES,
        "lomin": HOME_LON - PLANE_BBOX_DEGREES,
        "lomax": HOME_LON + PLANE_BBOX_DEGREES,
    }
    token = get_opensky_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    report_size("planes", resp)
    return resp.json()


def reduce_to_nearest(data):
    """
    Take raw OpenSky JSON, return a tiny dict describing the nearest aircraft
    (or None). This is the function that would run either on-device or on a
    relay — kept separate from fetch_states() on purpose.

    OpenSky state vector indices: 0=icao24, 1=callsign, 5=lon, 6=lat,
    7=baro_altitude, 9=velocity, 10=true_track, 22=geo_altitude
    """
    states = data.get("states") or []
    nearest = None
    nearest_dist = None
    for s in states:
        lon, lat = s[5], s[6]
        if lon is None or lat is None:
            continue
        dist = haversine_km(HOME_LAT, HOME_LON, lat, lon)
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest = s

    if nearest is None:
        return None

    callsign = (nearest[1] or "").strip() or nearest[0]
    return {
        "callsign": callsign,
        "dist_km": round(nearest_dist, 1),
        "alt_m": nearest[7],
        "speed_ms": nearest[9],
        "heading": nearest[10],
    }


def fetch_route(callsign):
    """
    Look up airline + origin/destination for a callsign via adsbdb.com
    (free, no key). Returns None if the callsign isn't a scheduled flight
    ADSBdb recognises (e.g. general aviation, no route on file).
    """
    resp = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}", timeout=15)
    if resp.status_code == 404:
        report_size("route", resp)
        return None
    resp.raise_for_status()
    report_size("route", resp)
    route = resp.json().get("response", {}).get("flightroute")
    if not route:
        return None

    airline = route.get("airline") or {}
    origin = route.get("origin") or {}
    destination = route.get("destination") or {}
    return {
        "airline_name": airline.get("name"),
        "airline_icao": airline.get("icao"),
        "origin": origin.get("iata_code") or origin.get("icao_code"),
        "destination": destination.get("iata_code") or destination.get("icao_code"),
    }


if __name__ == "__main__":
    auth_mode = "authenticated" if (OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET) else "anonymous"
    print(f"Querying OpenSky ({auth_mode}) for box around ({HOME_LAT}, {HOME_LON}) "
          f"+/- {PLANE_BBOX_DEGREES} deg...")
    data = fetch_states()
    n = len(data.get("states") or [])
    print(f"Aircraft in box: {n}")

    nearest = reduce_to_nearest(data)
    if nearest:
        print("Nearest aircraft:")
        for k, v in nearest.items():
            print(f"  {k}: {v}")

        route = fetch_route(nearest["callsign"])
        if route:
            print("Route info:")
            for k, v in route.items():
                print(f"  {k}: {v}")
        else:
            print("Route info: none found for this callsign "
                  "(likely not a scheduled airline flight)")
    else:
        print("No aircraft currently in range. Try widening PLANE_BBOX_DEGREES "
              "in config.py or re-run later.")
