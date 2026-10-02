"""
Stage 3 firmware: non-blocking main loop with per-mode data caching.

Design, deliberately:
  - Each mode fetches on its own interval, only when its cached data is
    stale, and only for the currently-selected mode (see maybe_fetch()).
    Non-selected modes are never fetched, so switching to one always shows
    its last-known data first, then refreshes.
  - Buttons are polled every loop iteration -- EXCEPT during the brief
    window an actual fetch is in flight (a couple of seconds, at most once
    per FETCH_INTERVAL_SECONDS). CircuitPython on the M4 has no real
    threading, so a fully non-blocking fetch isn't practical here; keeping
    fetches infrequent and short is the mitigation, not a fix.
  - Only "planes" mode is wired up so far; other modes show a placeholder.
"""
import time
import gc
import board
import displayio
import digitalio
import microcontroller
from adafruit_matrixportal.matrix import Matrix
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font

from modes import ModeCycler
import net
import planes
import football
import rugby

FETCH_INTERVAL_SECONDS = {
    "planes": 20,
    "football": 15,  # relay refreshes from ESPN every 20s server-side; local HTTP is cheap
    "rugby": 15,  # same relay, same reasoning
}

PAGE_SECONDS = 4  # how long each page of up to 2 matches stays on screen
LEAGUE_SECONDS = 60  # how long to stay on one league before moving to the next
# Both used by LeagueScorePager -- shared by football and rugby modes.

# --- Display setup ---
matrix = Matrix(width=64, height=32, bit_depth=4)
display = matrix.display

group = displayio.Group()
display.root_group = group

FONT = bitmap_font.load_font("/fonts/tom-thumb.bdf")
# render_planes() fills exactly 4 lines -- LINE_Y must match that count or
# the extra slot(s) render as permanent blank space.
LINE_COUNT = 4
# 1px clear margin on all four edges: rows 1..30 usable, 4 lines spread
# evenly across that full range instead of being crammed near the top.
LINE_Y = [5, 12, 20, 27]
TEXT_X = 1  # leave column 0 clear (right edge, column 63, is clear too since lines are short)

line_labels = []
for y in LINE_Y:
    lbl = Label(FONT, text="", color=0x00CFFF)
    lbl.anchor_point = (0.0, 0.5)
    lbl.anchored_position = (TEXT_X, y)
    group.append(lbl)
    line_labels.append(lbl)


def render_lines(lines):
    for i, lbl in enumerate(line_labels):
        lbl.text = lines[i] if i < len(lines) else ""


def render_planes(data):
    if data is None:
        render_lines(["No planes", "nearby right now"])
        return

    line1 = data["airline"] or "Unknown airline"
    line2 = data["route"] or ""
    line3 = f"{data['callsign']} {data['model']}" if data["model"] else data["callsign"]
    alt = f"{data['alt_ft']}ft" if data["alt_ft"] is not None else ""
    spd = f"{data['speed_kt']}kt" if data["speed_kt"] is not None else ""
    line4 = f"{alt} {spd}".strip()

    render_lines([line1, line2, line3, line4])


def render_placeholder(mode_name):
    render_lines([mode_name.upper(), "(coming soon)"])


class LeagueScorePager:
    """
    League name stays static in the top row. Below it, up to 2 matches are
    shown statically at a time ("a page"); after PAGE_SECONDS it
    advances to the next page of 2, and once a league's matches are
    exhausted it moves on to the next league. No animation, so there's
    nothing for a brief blocking-fetch stall (see maybe_fetch()) to visibly
    stutter -- a static page just holds a little longer than usual.
    """

    def __init__(self, font, group, title):
        self.title = title
        self.has_data = False
        self.header_label = Label(font, text="", color=0x00CFFF)
        self.header_label.anchor_point = (0.5, 0.5)
        self.header_label.anchored_position = (32, 4)
        group.append(self.header_label)

        self.row_labels = []
        for y in (14, 24):
            lbl = Label(font, text="", color=0x00CFFF)
            lbl.anchor_point = (0.0, 0.5)
            lbl.anchored_position = (TEXT_X, y)
            group.append(lbl)
            self.row_labels.append(lbl)

        self.leagues = []  # list of (league_name, matches)
        self.league_index = 0
        self.page_index = 0
        self.page_started_at = time.monotonic()
        self.league_started_at = time.monotonic()

    def set_data(self, leagues):
        # Leagues with nothing on today are dropped entirely, so the pager
        # only ever rotates through competitions that actually have matches.
        current_name, _ = self._current_league()
        self.has_data = True
        self.leagues = [(name, matches) for name, matches in (leagues or []) if matches]
        if not self.leagues:
            self.league_index = 0
            return

        names = [name for name, _ in self.leagues]
        if current_name in names:
            self.league_index = names.index(current_name)
        else:
            # The league on screen disappeared (or this is the first data):
            # start the next one fresh rather than mid-way through its timer.
            self.league_index %= len(self.leagues)
            self.page_index = 0
            now = time.monotonic()
            self.league_started_at = now
            self.page_started_at = now

    def _current_league(self):
        if not self.leagues:
            return None, []
        return self.leagues[self.league_index]

    def _page_count(self, matches):
        return max((len(matches) + 1) // 2, 1)  # always at least 1 page, even if empty

    def _advance_page(self):
        """
        Pages cycle every PAGE_SECONDS (looping back to the start
        within the same league); only after LEAGUE_SECONDS total
        does it move on to the next league, regardless of how few matches
        (and therefore pages) the current league has.
        """
        _, matches = self._current_league()
        now = time.monotonic()
        self.page_index = (self.page_index + 1) % self._page_count(matches)
        self.page_started_at = now

        if now - self.league_started_at > LEAGUE_SECONDS:
            self.page_index = 0
            self.league_index = (self.league_index + 1) % max(len(self.leagues), 1)
            self.league_started_at = now
            self.page_started_at = now

    @staticmethod
    def _match_line(m):
        return f"{m['home']} {m['home_score']}-{m['away_score']} {m['away']}  {m['status']}"

    def update(self):
        league_name, matches = self._current_league()
        if league_name is None:
            self.header_label.text = self.title
            self.row_labels[0].text = "No matches today" if self.has_data else "Loading..."
            self.row_labels[1].text = ""
            return

        self.header_label.text = league_name
        self.page_index %= self._page_count(matches)  # clamp if data shrank
        start = self.page_index * 2
        page = matches[start:start + 2]
        for i, lbl in enumerate(self.row_labels):
            lbl.text = self._match_line(page[i]) if i < len(page) else ""

        if time.monotonic() - self.page_started_at > PAGE_SECONDS:
            self._advance_page()

    def clear(self):
        self.header_label.text = ""
        for lbl in self.row_labels:
            lbl.text = ""


RENDERERS = {
    "planes": render_planes,
}

FETCHERS = {
    "planes": lambda requests: planes.fetch_and_reduce(requests),
    "football": lambda requests: football.fetch_and_reduce(requests),
    "rugby": lambda requests: rugby.fetch_and_reduce(requests),
}


# --- Buttons ---
button_up = digitalio.DigitalInOut(board.BUTTON_UP)
button_up.switch_to_input(pull=digitalio.Pull.UP)

button_down = digitalio.DigitalInOut(board.BUTTON_DOWN)
button_down.switch_to_input(pull=digitalio.Pull.UP)


def button_pressed(button, prev_state):
    pressed_now = not button.value
    if pressed_now and not prev_state:
        time.sleep(0.03)
        if not button.value:
            return True, True
    return False, pressed_now


# --- Cache: mode_name -> {"data": ..., "fetched_at": monotonic seconds} ---
cache = {}


FETCH_RETRY_SECONDS = 5  # backoff after a failed fetch -- short, but not every tick


# Self-healing: a hung AirLift or dropped Wi-Fi makes every fetch fail until
# power-cycled (seen 2026-10-02). After this many consecutive failures, hard
# reset the ESP32 and rejoin Wi-Fi; if failures continue past the second
# threshold (or the rejoin fails), reboot the whole board.
RECONNECT_AFTER_FAILURES = 5
REBOOT_AFTER_FAILURES = 10
consecutive_failures = 0


def recover_connection(esp):
    """Escalating recovery, called after each failed fetch."""
    if consecutive_failures >= REBOOT_AFTER_FAILURES:
        print("Too many failed fetches, rebooting board")
        microcontroller.reset()
    elif consecutive_failures == RECONNECT_AFTER_FAILURES:
        render_lines(["Reconnecting", "Wi-Fi..."])
        if not net.reconnect(esp):
            print("Reconnect failed, rebooting board")
            microcontroller.reset()


def maybe_fetch(mode_name, requests, esp):
    global consecutive_failures
    interval = FETCH_INTERVAL_SECONDS.get(mode_name)
    fetcher = FETCHERS.get(mode_name)
    if interval is None or fetcher is None:
        return

    now = time.monotonic()
    entry = cache.get(mode_name)
    if entry is not None and (now - entry["fetched_at"]) < entry["next_interval"]:
        return

    try:
        data = fetcher(requests)
        cache[mode_name] = {"data": data, "fetched_at": now, "next_interval": interval, "failed": False}
        consecutive_failures = 0
        print(f"[{mode_name}] fetched OK, free mem: {gc.mem_free()}")
    except Exception as e:  # noqa: BLE001 -- keep the loop alive on any fetch error
        consecutive_failures += 1
        print(f"[{mode_name}] fetch failed ({consecutive_failures} in a row): {e!r}")
        prev_data = entry["data"] if entry else None
        cache[mode_name] = {
            "data": prev_data, "fetched_at": now,
            "next_interval": FETCH_RETRY_SECONDS, "failed": True,
        }
        recover_connection(esp)
    gc.collect()


CUSTOM_WIDGETS = {
    "football": LeagueScorePager(FONT, group, "Football"),
    "rugby": LeagueScorePager(FONT, group, "Rugby"),
}


def render_current(mode_name):
    widget = CUSTOM_WIDGETS.get(mode_name)
    for other in CUSTOM_WIDGETS.values():
        if other is not widget:
            other.clear()

    # Fetch failed and there's no earlier data to fall back on: say so,
    # rather than showing "No planes" / "Loading..." which look like real
    # empty results.
    entry = cache.get(mode_name)
    if entry and entry.get("failed") and entry["data"] is None:
        if widget is not None:
            widget.clear()
        render_lines(["Fetch error", "retrying..."])
        return

    if widget is not None:
        render_lines(["", "", "", ""])  # clear the static-line labels
        entry = cache.get(mode_name)
        if entry and entry["data"] is not None:
            widget.set_data(entry["data"])
        widget.update()
        return

    renderer = RENDERERS.get(mode_name)
    if renderer is None:
        render_placeholder(mode_name)
        return
    entry = cache.get(mode_name)
    renderer(entry["data"] if entry else None)


if __name__ == "__main__":
    cycler = ModeCycler()

    print("Connecting to Wi-Fi...")
    render_lines(["Connecting", "to Wi-Fi..."])
    requests, esp = net.connect()

    render_current(cycler.current)

    up_prev = False
    down_prev = False

    while True:
        up_edge, up_prev = button_pressed(button_up, up_prev)
        down_edge, down_prev = button_pressed(button_down, down_prev)

        if up_edge:
            render_current(cycler.next())
        elif down_edge:
            render_current(cycler.previous())

        maybe_fetch(cycler.current, requests, esp)
        render_current(cycler.current)

        time.sleep(0.02)
