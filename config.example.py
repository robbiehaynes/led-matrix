"""
Copy this file to config.py and fill in your own values.
config.py is gitignored — never commit real credentials.
"""

# --- Wi-Fi (used by the CircuitPython firmware, not the bench scripts) ---
WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

# --- Home location, for nearest-plane distance calculations ---
HOME_LAT = 51.5074
HOME_LON = -0.1278

# Half-width (in degrees) of the bounding box searched around HOME_LAT/LON
# for OpenSky queries. ~0.5 degrees is roughly 35-55km depending on latitude.
# Widen this if you rarely see aircraft; narrow it if responses are too large.
PLANE_BBOX_DEGREES = 0.5

# Optional: OpenSky authenticated access (free account + API client at
# https://opensky-network.org -> Account page). Raises the daily credit
# budget from 400 (anonymous) to 4000. Leave both as "" to stay anonymous.
OPENSKY_CLIENT_ID = ""
OPENSKY_CLIENT_SECRET = ""

# --- football-data.org: UNUSED. Football/rugby both use ESPN's hidden API ---
# --- via the Pi relay instead (see relay/football_relay.py). Not read by ---
# --- any current code path -- kept only as a historical note. ---
FOOTBALL_DATA_API_KEY = "your-api-key-here"
FOOTBALL_DATA_COMPETITION = "PL"  # Premier League
