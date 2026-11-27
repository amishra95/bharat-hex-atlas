"""Build the 25 km hex grid over India and assign every land hex to a district and state.

Inputs : raw/ind_adm2.geojson (geoBoundaries / LGD districts), raw/ind_adm1.geojson,
         raw/ne_land.zip (Natural Earth land, for neighbours vs sea)
Outputs: work/hexes.parquet, work/districts.parquet
"""
import math
import os

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from shapely.strtree import STRtree

from common import CRS, HEX_R, RAW, WORK, axial_to_xy, hex_polygon, HEX_AREA_KM2

print("loading boundaries")
dist = gpd.read_file(os.path.join(RAW, "ind_adm2.geojson")).to_crs(CRS)
states = gpd.read_file(os.path.join(RAW, "ind_adm1.geojson")).to_crs(CRS)
dist["geometry"] = dist.geometry.buffer(0)
states["geometry"] = states.geometry.buffer(0)

# Attach a state to every district by largest overlap.
print("district -> state")
inter = gpd.overlay(dist[["shapeID", "geometry"]].reset_index(),
                    states[["shapeName", "geometry"]].rename(columns={"shapeName": "state"}),
                    how="intersection", keep_geom_type=True)
inter["a"] = inter.area
best = inter.sort_values("a").groupby("shapeID").tail(1)[["shapeID", "state"]]
dist = dist.merge(best, on="shapeID", how="left")
print("districts without state:", dist.state.isna().sum())

dist = dist.rename(columns={"shapeName": "district", "shapeID": "did"})
dist["area_km2"] = dist.area / 1e6
dist = dist.sort_values(["state", "district"]).reset_index(drop=True)
dist["dix"] = np.arange(len(dist))

india = dist.unary_union
land = gpd.read_file("zip://" + os.path.join(RAW, "ne_land.zip"))
land = gpd.clip(land, box(60, 0, 106, 42)).to_crs(CRS)
land["geometry"] = land.geometry.buffer(0)

minx, miny, maxx, maxy = india.bounds
pad = 6 * HEX_R
minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
world_land = land.unary_union.intersection(box(minx, miny, maxx, maxy))

# Enumerate axial coords covering the bbox.
r0 = int(math.floor(miny / (1.5 * HEX_R))) - 1
r1 = int(math.ceil(maxy / (1.5 * HEX_R))) + 1
rows = []
for r in range(r0, r1 + 1):
    qa = int(math.floor(minx / (HEX_R * math.sqrt(3)) - r / 2)) - 1
    qb = int(math.ceil(maxx / (HEX_R * math.sqrt(3)) - r / 2)) + 1
    for q in range(qa, qb + 1):
        rows.append((q, r))
print("candidate hexes:", len(rows))

polys = [hex_polygon(q, r) for q, r in rows]
g = gpd.GeoDataFrame({"q": [a for a, _ in rows], "r": [b for _, b in rows]}, geometry=polys, crs=CRS)

print("intersecting with India")
tree = STRtree(dist.geometry.values)
dist_geoms = dist.geometry.values
india_frac = np.zeros(len(g))
best_d = np.full(len(g), -1)
second = [None] * len(g)
for i, hp in enumerate(g.geometry.values):
    idx = tree.query(hp, predicate="intersects")
    if len(idx) == 0:
        continue
    areas = [(hp.intersection(dist_geoms[j]).area, j) for j in idx]
    areas.sort(reverse=True)
    tot = sum(a for a, _ in areas)
    india_frac[i] = tot / hp.area
    best_d[i] = areas[0][1]
    second[i] = [(int(dist.dix.iloc[j]), round(a / hp.area, 3)) for a, j in areas if a / hp.area > 0.02]
g["india_frac"] = india_frac
g["dix"] = [int(dist.dix.iloc[j]) if j >= 0 else -1 for j in best_d]
g["dshares"] = second

# Make sure every district owns at least one hex (tiny UTs / islands / city districts).
in_india = g.india_frac >= 0.3
owned = set(g.loc[in_india, "dix"])
for _, d in dist.iterrows():
    if d.dix in owned:
        continue
    pt = d.geometry.representative_point()
    hits = g.index[g.geometry.contains(pt)]
    if len(hits):
        h = hits[0]
        in_india.loc[h] = True
        # a district carved out of a larger hex: keep it attached to the bigger owner,
        # but remember it so the district table can still point at a hex
print("districts with no majority hex:", len(set(dist.dix) - set(g.loc[in_india, "dix"])))

print("classifying sea / neighbour land")
lt = world_land
land_frac = np.array([hp.intersection(lt).area / hp.area if hp.intersects(lt) else 0.0 for hp in g.geometry.values])
g["land_frac"] = land_frac
g["kind"] = np.where(in_india, "india", np.where(land_frac >= 0.5, "foreign", "sea"))

# Trim the outer frame: keep sea/foreign only within 6 rings of India.
from common import NEIGHBOURS
key = {(q, r): i for i, (q, r) in enumerate(zip(g.q, g.r))}
dist_to_india = np.full(len(g), 99)
frontier = [i for i in range(len(g)) if g.kind.iat[i] == "india"]
for i in frontier:
    dist_to_india[i] = 0
step = 0
while frontier and step < 6:
    step += 1
    nxt = []
    for i in frontier:
        q, r = g.q.iat[i], g.r.iat[i]
        for dq, dr in NEIGHBOURS:
            j = key.get((q + dq, r + dr))
            if j is not None and dist_to_india[j] > step:
                dist_to_india[j] = step
                nxt.append(j)
    frontier = nxt
g["ring"] = dist_to_india
g = g[g.ring <= 6].reset_index(drop=True)

cent = g.geometry.centroid
ll = gpd.GeoSeries(cent, crs=CRS).to_crs(4326)
g["lon"], g["lat"] = ll.x.round(4), ll.y.round(4)
g["x"], g["y"] = cent.x, cent.y

print(g.kind.value_counts().to_dict(), "hex area km2:", round(HEX_AREA_KM2, 1))
g.to_parquet(os.path.join(WORK, "hexes.parquet"))
dist.to_parquet(os.path.join(WORK, "districts.parquet"))
print("states:", dist.state.nunique())
