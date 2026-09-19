"""
Shared helpers for bench scripts. These reduction functions are written to be
CircuitPython-portable (no external deps beyond stdlib math) so the same
logic can move onto the MatrixPortal once bench-tested here.
"""
import math


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two lat/lon points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def report_size(label, response):
    """Print raw response size so we can judge on-device feasibility."""
    n = len(response.content)
    print(f"[{label}] raw response: {n} bytes")
    return n
