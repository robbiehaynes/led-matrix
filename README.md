# LED Matrix Display

A 64×32 RGB LED matrix wall display, built on an Adafruit MatrixPortal M4, that cycles through live data instead of showing one fixed thing. A physical button on the board switches between modes; each mode polls a free API on its own schedule and renders a compact info layout sized for the panel.

## What it shows

- **Planes** — the nearest aircraft overhead, with airline, route, aircraft model, altitude and speed. Filters out helicopters and grounded aircraft so it only ever shows something actually flying nearby.
- **Football** — live scores (with match minute / HT / FT) across the Premier League, Championship, League One, Carabao Cup, and Champions League. Pages through matches two at a time, cycling leagues roughly every minute.
- **Rugby** — same layout as football, covering the URC, Premiership, Champions Cup, Challenge Cup, and international matches involving South Africa and England.

## Hardware

- [Adafruit MatrixPortal M4](https://www.adafruit.com/product/4745) — CircuitPython, ESP32 "AirLift" co-processor for Wi-Fi
- A 64×32, 4mm-pitch HUB75 RGB LED matrix panel (powered separately — a panel this size draws more current than USB can safely supply)

## How it's built

```
bench/          Desktop Python scripts used to validate each data source
                before porting it to the device. Handy for debugging a
                feed without needing the hardware connected.

firmware/code/  The actual CircuitPython files that run on the board:
                  code.py    main loop — button handling, mode switching,
                             per-mode data caching and fetch scheduling
                  planes.py  OpenSky + ADSBdb
                  football.py, rugby.py   both talk to the relay (below),
                             not the underlying APIs directly
                  net.py     Wi-Fi + HTTP session setup
                  modes.py   the list of modes and the button cycler

relay/          A small always-on relay service, meant to run on a
                Raspberry Pi or similar, that fetches football/rugby data
                on the device's behalf and serves a tiny reduced payload
                over plain local HTTP. This exists because the API those
                two modes use sits behind bot-protection that blocks the
                MatrixPortal's Wi-Fi co-processor at the TLS level —
                confirmed by testing directly against the hardware, not
                just theory. A normal machine isn't blocked, so it fetches
                on the device's behalf.
```

Each mode's fetch/reduce logic is bench-tested on a desktop first (see `bench/`), then ported into the equivalent `firmware/code/*.py` module once the data shape and payload size are confirmed to fit comfortably in the board's ~192KB of RAM.

## Setup

1. **Firmware**: see [`firmware/README.md`](firmware/README.md) for flashing CircuitPython, installing the required libraries, and wiring up the panel.
2. **Config & secrets**: copy `firmware/code/config.example.py` → `config.py` and `firmware/code/secrets.example.py` → `secrets.py`, fill in your Wi-Fi credentials, home coordinates, and API keys. Both are gitignored.
3. **Relay** (needed for football/rugby modes): copy `relay/football_relay.py` to an always-on machine on your network, run it (stdlib only, no dependencies), and point `FOOTBALL_RELAY_URL` in your device config at it. `relay/football-relay.service` is a sample systemd unit for running it as a service on a Raspberry Pi.

## Data sources

All free, no paid tiers required:

- [OpenSky Network](https://opensky-network.org/) — live aircraft positions
- [ADSBdb](https://www.adsbdb.com/) — airline/route/aircraft-type lookup by callsign
- ESPN's public scoreboard API — football and rugby scores (unofficial/undocumented, but free and genuinely live; accessed through the relay for the reason described above)
