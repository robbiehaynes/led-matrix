"""
Fetch + reduce logic for planes mode. Two HTTPS calls per refresh:
OpenSky (nearest aircraft) then ADSBdb (airline/route for that callsign).
Every response is closed in a finally block -- adafruit_connection_manager
only allows one open connection per host, so a leaked response breaks the
*next* poll of that same host, not just this one.
"""
import math
import time
from config import (
    HOME_LAT,
    HOME_LON,
    PLANE_BBOX_DEGREES,
    OPENSKY_CLIENT_ID,
    OPENSKY_CLIENT_SECRET,
)

OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)

# Module-level token cache: {"access_token": ..., "expires_at": monotonic-seconds}
_token_cache = {}


def _get_opensky_token(requests):
    """
    Returns a valid bearer token, refreshing if missing/expired. Returns
    None if no client_id/secret configured (caller falls back to anonymous).
    Tokens last 30 min server-side; refreshed 60s early to leave margin.
    """
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        return None

    now = time.monotonic()
    cached = _token_cache.get("access_token")
    if cached and now < _token_cache["expires_at"] - 60:
        return cached

    response = requests.post(
        OPENSKY_TOKEN_URL,
        data=(
            f"grant_type=client_credentials"
            f"&client_id={OPENSKY_CLIENT_ID}"
            f"&client_secret={OPENSKY_CLIENT_SECRET}"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        data = response.json()
    finally:
        response.close()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 1800)
    return _token_cache["access_token"]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


ROTORCRAFT_CATEGORY = 8  # OpenSky "category" field value for helicopters

# Manufacturer-name substrings (lowercase) used to catch helicopters whose
# OpenSky category field is unset (0 = "no info"), which is common --
# checked via a per-candidate ADSBdb /aircraft lookup as a fallback.
HELICOPTER_MANUFACTURER_KEYWORDS = (
    "eurocopter", "airbus helicopters", "bell", "sikorsky", "robinson",
    "leonardo", "agusta", "kaman", "md helicopters", "schweizer", "enstrom",
)

MAX_CANDIDATES_CHECKED = 3  # bounds worst-case extra HTTPS calls/blocking time


def _sorted_candidates(states):
    """States with a valid position, sorted nearest-first."""
    candidates = []
    for s in states:
        lon, lat = s[5], s[6]
        if lon is None or lat is None:
            continue
        dist = haversine_km(HOME_LAT, HOME_LON, lat, lon)
        candidates.append((dist, s))
    candidates.sort(key=lambda pair: pair[0])
    return candidates


def _is_on_ground(state):
    return bool(state[8])  # OpenSky state vector index 8: on_ground


def _fetch_aircraft_info(requests, icao24):
    """Returns ADSBdb's aircraft dict (manufacturer, icao_type, ...) or None."""
    response = requests.get(f"https://api.adsbdb.com/v0/aircraft/{icao24}")
    try:
        if response.status_code == 404:
            return None
        data = response.json()
    finally:
        response.close()
    return data.get("response", {}).get("aircraft")


def _is_helicopter_info(aircraft_info):
    if not aircraft_info:
        return False
    manufacturer = (aircraft_info.get("manufacturer") or "").lower()
    return any(kw in manufacturer for kw in HELICOPTER_MANUFACTURER_KEYWORDS)


def _fetch_nearest_state(requests):
    url = "https://opensky-network.org/api/states/all"
    params = (
        f"?lamin={HOME_LAT - PLANE_BBOX_DEGREES}"
        f"&lamax={HOME_LAT + PLANE_BBOX_DEGREES}"
        f"&lomin={HOME_LON - PLANE_BBOX_DEGREES}"
        f"&lomax={HOME_LON + PLANE_BBOX_DEGREES}"
        f"&extended=1"
    )
    token = _get_opensky_token(requests)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    response = requests.get(url + params, headers=headers)
    try:
        data = response.json()
    finally:
        response.close()

    states = data.get("states") or []
    candidates = _sorted_candidates(states)

    nearest = None
    nearest_aircraft_info = None
    checked = 0
    for _dist, state in candidates:
        if _is_on_ground(state):
            continue

        category = state[17] if len(state) > 17 else None
        if category == ROTORCRAFT_CATEGORY:
            continue

        checked += 1
        if checked > MAX_CANDIDATES_CHECKED:
            break

        aircraft_info = _fetch_aircraft_info(requests, state[0])
        if _is_helicopter_info(aircraft_info):
            continue

        nearest = state
        nearest_aircraft_info = aircraft_info
        break

    if nearest is None:
        return None

    callsign = (nearest[1] or "").strip() or nearest[0]
    return {
        "callsign": callsign,
        "alt_m": nearest[7],
        "speed_ms": nearest[9],
        "model": (nearest_aircraft_info or {}).get("icao_type"),
    }


def _fetch_route(requests, callsign):
    url = f"https://api.adsbdb.com/v0/callsign/{callsign}"
    response = requests.get(url)
    try:
        if response.status_code == 404:
            return None
        data = response.json()
    finally:
        response.close()

    route = data.get("response", {}).get("flightroute")
    if not route:
        return None

    airline = route.get("airline") or {}
    origin = route.get("origin") or {}
    destination = route.get("destination") or {}
    return {
        "airline_name": airline.get("name"),
        "origin": origin.get("iata_code") or origin.get("icao_code"),
        "destination": destination.get("iata_code") or destination.get("icao_code"),
    }


def fetch_and_reduce(requests):
    """Returns None (no aircraft in range) or a small dict for rendering."""
    state = _fetch_nearest_state(requests)
    if state is None:
        return None

    result = {
        "callsign": state["callsign"],
        "model": state["model"],
        "alt_ft": round(state["alt_m"] * 3.28084) if state["alt_m"] is not None else None,
        "speed_kt": round(state["speed_ms"] * 1.94384) if state["speed_ms"] is not None else None,
        "airline": None,
        "route": None,
    }

    route = _fetch_route(requests, state["callsign"])
    if route:
        result["airline"] = route["airline_name"]
        if route["origin"] and route["destination"]:
            result["route"] = f"{route['origin']}-{route['destination']}"

    return result
