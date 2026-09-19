# Firmware setup (Stage 1: display + button test)

This stage only tests panel wiring and the mode-switch button — no Wi-Fi or
API calls yet. Get this working first; it isolates hardware problems from
network/code problems.

## 1. Install CircuitPython

Download the CircuitPython UF2 for your exact board (MatrixPortal M4) from
https://circuitpython.org/board/matrixportal_m4/ and drag it onto the board
while it's in bootloader mode (double-tap RESET). It will reboot and appear
as a `CIRCUITPY` USB drive.

If your board is actually the newer MatrixPortal S3, use
https://circuitpython.org/board/adafruit_matrixportal_s3/ instead — the
code in this repo works on either, Wi-Fi setup (Stage 2) is what differs.

## 2. Copy CircuitPython libraries

Download the **Adafruit CircuitPython Library Bundle** matching your
CircuitPython version from https://circuitpython.org/libraries, then copy
these folders into `CIRCUITPY/lib/`:

- `adafruit_matrixportal/`
- `adafruit_display_text/`
- `adafruit_bus_device/`

(`adafruit_esp32spi` and `adafruit_requests` aren't needed until Stage 2.)

## 3. Wire up the panel

Connect the Waveshare 64x32 P4 panel to the MatrixPortal's HUB75 IDC
connector. **Power the panel from its own 5V supply, not through the
MatrixPortal's USB port** — a 64x32 panel can draw well over 1A at full
brightness, more than USB can safely provide. See Adafruit's guide:
https://learn.adafruit.com/adafruit-matrixportal-m4

## 4. Copy the firmware files

Copy onto `CIRCUITPY`:
- `firmware/code/code.py` -> `CIRCUITPY/code.py`
- `firmware/code/modes.py` -> `CIRCUITPY/modes.py`

The board runs `code.py` automatically on save/reset.

## 5. What you should see

1. A quick red -> green -> blue -> white full-panel color test (~2.5s total)
2. The text "PLANES" centered on the display
3. Pressing the **UP** button cycles forward through modes
   (planes -> football -> rugby -> planes...)
4. Pressing **DOWN** cycles backward

Connect to the serial console (e.g. `screen /dev/tty.usbmodem* 115200` on
macOS, or the Mu editor's serial pane) to see `[display] mode -> ...` prints
confirming each button press is registered.

## Troubleshooting

- **Blank panel**: check the HUB75 ribbon cable orientation and that the
  panel has its own 5V power connected.
- **Garbled image / only half the panel lights up / mirrored**: the
  Waveshare panel's row-scan wiring can differ slightly from what
  `adafruit_matrixportal.matrix.Matrix()` assumes by default. Report what
  you see and we'll adjust the `Matrix()` parameters (e.g. `tile`,
  `serpentine`, `width`/`height` order) to match.
- **Buttons do nothing**: confirm you're looking at the right two buttons —
  on the MatrixPortal M4 they're labeled UP and DOWN next to the USB port.

Once this is confirmed working, tell me and we'll move to Stage 2: Wi-Fi +
live data for each mode.
