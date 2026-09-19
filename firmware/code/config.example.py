"""
Copy this file to config.py on CIRCUITPY and fill in your own values.
config.py is gitignored — never commit real credentials.

Wi-Fi credentials live separately in secrets.py (see secrets.example.py) —
that's the conventional split for adafruit_esp32spi-based projects.
"""

# --- Home location, for nearest-plane distance calculations ---
HOME_LAT = 0.0
HOME_LON = 0.0

# Half-width (in degrees) of the bounding box searched around HOME_LAT/LON
# for OpenSky queries. ~0.5 degrees is roughly 35-55km depending on latitude.
PLANE_BBOX_DEGREES = 0.5

# Optional: OpenSky authenticated access (free account + API client at
# https://opensky-network.org -> Account page). Raises the daily credit
# budget from 400 (anonymous) to 4000, which is what allows a ~20s poll
# interval instead of ~5min. Leave both as "" to stay anonymous.
OPENSKY_CLIENT_ID = ""
OPENSKY_CLIENT_SECRET = ""

# --- Sports relay (runs on a local always-on machine, see relay/football_relay.py) ---
# Serves both /football and /rugby -- rugby.py derives its own URL from this.
FOOTBALL_RELAY_URL = "http://<pi-ip-address>:8090/football"
