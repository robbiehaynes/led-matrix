"""
Wi-Fi + HTTP session setup for the MatrixPortal M4's ESP32 AirLift
co-processor. Call connect() once at startup and reuse the returned
requests session for every fetch afterwards.
"""
import board
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_connection_manager
import adafruit_requests

from secrets import secrets


def connect():
    esp32_cs = DigitalInOut(board.ESP_CS)
    esp32_ready = DigitalInOut(board.ESP_BUSY)
    esp32_reset = DigitalInOut(board.ESP_RESET)

    spi = board.SPI()
    esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

    print(f"Connecting to {secrets['ssid']}...")
    while not esp.is_connected:
        try:
            esp.connect_AP(secrets["ssid"], secrets["password"])
        except OSError as e:
            print(f"  retrying after error: {e}")
            continue
    print(f"Connected! IP address: {esp.pretty_ip(esp.ip_address)}")

    pool = adafruit_connection_manager.get_radio_socketpool(esp)
    ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
    return adafruit_requests.Session(pool, ssl_context), esp


def reconnect(esp, attempts=3):
    """
    Hard-resets the ESP32 and rejoins Wi-Fi, which clears hung sockets as
    well as dropped associations. Returns True on success. The existing
    requests session stays usable: it holds the same esp object.
    """
    for attempt in range(attempts):
        try:
            print(f"Reconnecting Wi-Fi (attempt {attempt + 1}/{attempts})...")
            esp.reset()
            esp.connect_AP(secrets["ssid"], secrets["password"])
            if esp.is_connected:
                print("Wi-Fi reconnected")
                return True
        except (OSError, RuntimeError) as e:
            print(f"  reconnect failed: {e!r}")
    return False
