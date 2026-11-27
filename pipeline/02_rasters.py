"""Aggregate gridded rasters onto hexes and districts.

* WorldPop 2025 constrained population (1 km)          -> pop
* GHSL built-up surface 2025 (30 arc-sec)              -> built_km2
* AWS terrain tiles (terrarium, z7 ~1.2 km)            -> elev mean / max / std
* ESA WorldCover 2021 v200 (read from COG overviews)   -> land-cover fractions
Outputs: work/hex_raster.parquet, work/dist_raster.parquet
"""
import io
import math
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from PIL import Image
from rasterio import features
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

from common import RAW, WORK, hexkey, lonlat_to_hexkey

hexes = pd.read_parquet(os.path.join(WORK, "hexes.parquet"))
hexes["key"] = hexkey(hexes.q.values, hexes.r.values)
dist = gpd.read_parquet(os.path.join(WORK, "districts.parquet")).to_crs(4326)
keyset = pd.Index(hexes.key)
out = pd.DataFrame({"key": hexes.key})
dout = pd.DataFrame({"dix": dist.dix})


def agg_grid(arr, transform, name, how="sum", nodata=None, dist_too=True):
    """Aggregate a lon/lat grid onto hexes (and optionally districts)."""
    h, w = arr.shape
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != nodata
    rows, cols = np.nonzero(valid)
    vals = arr[rows, cols].astype("float64")
    lon = transform.c + (cols + 0.5) * transform.a
    lat = transform.f + (rows + 0.5) * transform.e
    keys = lonlat_to_hexkey(lon, lat)
    s = pd.Series(vals).groupby(keys)
    agg = getattr(s, how)()
    out[name] = out.key.map(agg)
    if dist_too:
        dr = features.rasterize(((g, i) for g, i in zip(dist.geometry, dist.dix)),
                                out_shape=(h, w), transform=transform, fill=-1, dtype="int32")
        dv = dr[rows, cols]
        m = dv >= 0
        da = getattr(pd.Series(vals[m]).groupby(dv[m]), how)()
        dout[name] = dout.dix.map(da)
    print(name, "hex total", np.nansum(out[name]) if how == "sum" else "-")


# ---------------- population: GHS-POP 2025 (R2023A, 30 arc-sec) ----------------
# WorldPop's 2025 constrained 1 km grid was also tried, but it puts ~0.85 M people in Mumbai City and
# ~8 M in Bengaluru Urban; GHS-POP is consistent with the GHSL urban centres used for cities.
def ghsl(zname, col, scale=1.0):
    z = os.path.join(RAW, zname)
    with zipfile.ZipFile(z) as zf:
        tif = [n for n in zf.namelist() if n.endswith(".tif")][0]
    with rasterio.open(f"zip://{z}!/{tif}") as src:
        win = from_bounds(66, 4, 100, 39, src.transform)
        a = src.read(1, window=win).astype("float64")
        a[a < 0] = 0
        agg_grid(a * scale, src.window_transform(win), col)


ghsl("ghs_pop_2025.zip", "pop")
with rasterio.open(os.path.join(RAW, "ind_pop_2025_1km.tif")) as src:
    agg_grid(src.read(1).astype("float64"), src.transform, "pop_worldpop", nodata=src.nodata)
ghsl("ghsl_built_nres_2025.zip", "built_nres_km2", 1e-6)

# ---------------- GHSL built-up ----------------
z = os.path.join(RAW, "ghsl_built_2025.zip")
if os.path.exists(z) and zipfile.is_zipfile(z):
    with zipfile.ZipFile(z) as zf:
        tif = [n for n in zf.namelist() if n.endswith(".tif")][0]
    with rasterio.open(f"zip://{z}!/{tif}") as src:
        win = from_bounds(66, 4, 100, 39, src.transform)
        b = src.read(1, window=win).astype("float64")
        tr = src.window_transform(win)
        agg_grid(b / 1e6, tr, "built_km2", nodata=src.nodata / 1e6 if src.nodata else None)
else:
    print("!! GHSL built-up not downloaded yet; skipping", file=sys.stderr)

# ---------------- Kummu et al. gridded GDP (PPP, 2024 band) -> spatial weights ----------------
with rasterio.open(os.path.join(RAW, "kummu_gdpTot_5arcmin.tif")) as src:
    band = list(src.descriptions).index("gdp_tot_2024") + 1
    win = from_bounds(66, 4, 100, 39, src.transform)
    gd = src.read(band, window=win).astype("float64")
    tr = src.window_transform(win)
    # 5 arc-min cells (~9 km) are coarser than districts in big cities: supersample 5x5 so
    # each sub-cell carries 1/25th of the value and lands in the right hex / district.
    k = 5
    gd = np.repeat(np.repeat(gd, k, 0), k, 1) / (k * k)
    tr = tr * tr.scale(1 / k, 1 / k)
    agg_grid(gd, tr, "gdp_ppp_kummu")

# ---------------- WorldClim 2.1 climate normals (1970-2000), 10 arc-min ----------------
wcz = os.path.join(RAW, "wc_bio_10m.zip")
for bio, name in [(1, "temp_c"), (12, "rain_mm")]:
    with rasterio.open(f"zip://{wcz}!/wc2.1_10m_bio_{bio}.tif") as src:
        win = from_bounds(66, 4, 100, 39, src.transform)
        a = src.read(1, window=win, masked=True).filled(np.nan).astype("float64")
        tr = src.window_transform(win)
        k = 4  # supersample so every hex gets cells
        a = np.repeat(np.repeat(a, k, 0), k, 1)
        tr = tr * tr.scale(1 / k, 1 / k)
        agg_grid(a, tr, name, how="mean")

# ---------------- elevation (terrarium tiles) ----------------
Z = 7


def tile_xy(lon, lat):
    n = 2 ** Z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


x0, y0 = tile_xy(66, 39)
x1, y1 = tile_xy(100, 4)
cache = os.path.join(RAW, "terrarium")
os.makedirs(cache, exist_ok=True)


def get_tile(xy):
    x, y = xy
    p = os.path.join(cache, f"{Z}_{x}_{y}.png")
    if not os.path.exists(p):
        r = requests.get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png", timeout=60)
        r.raise_for_status()
        open(p, "wb").write(r.content)
    im = np.asarray(Image.open(p).convert("RGB")).astype("float64")
    return xy, im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768


tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
with ThreadPoolExecutor(16) as ex:
    got = dict(ex.map(get_tile, tiles))
n = 2 ** Z
elev_frames = []
for (x, y), e in got.items():
    px = (np.arange(256) + 0.5) / 256
    lon = (x + px) / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + px) / n))))
    LON, LAT = np.meshgrid(lon, lat)
    elev_frames.append(pd.DataFrame({"lon": LON.ravel(), "lat": LAT.ravel(), "e": e.ravel()}))
E = pd.concat(elev_frames)
E["key"] = lonlat_to_hexkey(E.lon.values, E.lat.values)
E = E[E.key.isin(keyset)]
g = E.groupby("key").e
out["elev"] = out.key.map(g.mean())
out["elev_max"] = out.key.map(g.max())
out["elev_min"] = out.key.map(g.min())
out["elev_std"] = out.key.map(g.std())
print("elevation done", len(E))

# ---------------- ESA WorldCover 2021 ----------------
WC = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare",
      70: "snow", 80: "water", 90: "wetland", 95: "mangrove", 100: "moss"}
india_hex = hexes[hexes.kind != "sea"]
need = set()
for lon, lat in zip(india_hex.lon, india_hex.lat):
    need.add((int(math.floor(lat / 3) * 3), int(math.floor(lon / 3) * 3)))
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif"


def wc_tile(ll):
    lat, lon = ll
    ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
    name = f"ESA_WorldCover_10m_2021_v200_{ns}E{lon:03d}_Map.tif"
    cachep = os.path.join(RAW, "worldcover", name.replace(".tif", "_ov.npz"))
    if os.path.exists(cachep):
        d = np.load(cachep)
        return ll, d["a"], tuple(d["t"])
    url = "/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/" + name
    try:
        with rasterio.open(url) as src:
            # 36000 px / 120 -> 300 px per degree (~330 m), plenty for 541 km2 hexes
            shape = (src.height // 120, src.width // 120)
            a = src.read(1, out_shape=shape, resampling=rasterio.enums.Resampling.mode)
            t = src.transform * src.transform.scale(src.width / shape[1], src.height / shape[0])
    except Exception as e:  # tile over open sea does not exist
        return ll, None, None
    os.makedirs(os.path.dirname(cachep), exist_ok=True)
    np.savez_compressed(cachep, a=a, t=np.array(tuple(t)[:6]))
    return ll, a, tuple(t)[:6]


fr = []
with ThreadPoolExecutor(12) as ex:
    for ll, a, t in ex.map(wc_tile, sorted(need)):
        if a is None:
            continue
        tr = rasterio.Affine(*t)
        rows, cols = np.nonzero(a > 0)
        lon = tr.c + (cols + 0.5) * tr.a
        lat = tr.f + (rows + 0.5) * tr.e
        fr.append(pd.DataFrame({"key": lonlat_to_hexkey(lon, lat), "c": a[rows, cols]}))
        print("worldcover", ll, a.shape, flush=True)
W = pd.concat(fr)
W = W[W.key.isin(keyset)]
ct = pd.crosstab(W.key, W.c)
ct = ct.div(ct.sum(axis=1), axis=0)
for code, nm in WC.items():
    out["lc_" + nm] = out.key.map(ct[code]) if code in ct.columns else 0.0
print("worldcover done")

out.to_parquet(os.path.join(WORK, "hex_raster.parquet"))
dout.to_parquet(os.path.join(WORK, "dist_raster.parquet"))
print(out.describe().T.to_string())
