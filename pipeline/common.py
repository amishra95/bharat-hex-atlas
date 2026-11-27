"""Shared constants and helpers for the Bharat hex-map pipeline."""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "web", "data")
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# Albers equal-area tuned for India: hexes all have the same true area.
CRS = "+proj=aea +lat_1=12 +lat_2=28 +lat_0=20 +lon_0=82 +datum=WGS84 +units=m +no_defs"

# Pointy-top hexes, 25 km across the flats.
HEX_FLAT_KM = 25.0
HEX_R = HEX_FLAT_KM * 1000 / math.sqrt(3)  # centre-to-vertex, metres
HEX_AREA_KM2 = 3 * math.sqrt(3) / 2 * (HEX_R / 1000) ** 2


def axial_to_xy(q, r):
    return HEX_R * math.sqrt(3) * (q + r / 2.0), HEX_R * 1.5 * r


def xy_to_axial(x, y):
    q = (math.sqrt(3) / 3 * x - 1.0 / 3 * y) / HEX_R
    r = (2.0 / 3 * y) / HEX_R
    return hex_round(q, r)


def hex_round(q, r):
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return int(rq), int(rr)


def hex_polygon(q, r):
    from shapely.geometry import Polygon
    cx, cy = axial_to_xy(q, r)
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        pts.append((cx + HEX_R * math.cos(a), cy + HEX_R * math.sin(a)))
    return Polygon(pts)


def xy_to_axial_np(x, y):
    """Vectorised xy -> (q, r) for numpy arrays."""
    import numpy as np
    q = (np.sqrt(3) / 3 * x - 1.0 / 3 * y) / HEX_R
    r = (2.0 / 3 * y) / HEX_R
    s = -q - r
    rq, rr, rs = np.round(q), np.round(r), np.round(s)
    dq, dr, ds = np.abs(rq - q), np.abs(rr - r), np.abs(rs - s)
    m1 = (dq > dr) & (dq > ds)
    m2 = ~m1 & (dr > ds)
    rq = np.where(m1, -rr - rs, rq)
    rr = np.where(m2, -rq - rs, rr)
    return rq.astype(np.int64), rr.astype(np.int64)


_T = None


def lonlat_to_hexkey(lon, lat):
    """lon/lat arrays -> int64 key q*100000+r (shifted to be positive)."""
    import numpy as np
    global _T
    if _T is None:
        from pyproj import Transformer
        _T = Transformer.from_crs(4326, CRS, always_xy=True)
    x, y = _T.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    q, r = xy_to_axial_np(np.asarray(x), np.asarray(y))
    return hexkey(q, r)


def hexkey(q, r):
    return (q + 50000) * 100000 + (r + 50000)


NEIGHBOURS =[(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def dump(obj, name, folder=None):
    path = os.path.join(folder or OUT, name)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {path} ({os.path.getsize(path)/1e6:.2f} MB)")


def load(name, folder=None):
    with open(os.path.join(folder or WORK, name)) as f:
        return json.load(f)
