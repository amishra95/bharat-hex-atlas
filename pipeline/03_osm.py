"""Extract map features from the Geofabrik India OSM extract (current OSM data).

Points of interest (nodes, way centroids, relation centroids) go to work/osm_poi.parquet.
Linear networks (rail, major roads, rivers) are cut into hex-to-hex edges and per-hex lengths:
  work/osm_lines_hex.parquet, work/osm_edges.parquet, work/rivers.json
"""
import math
import os
import time
from collections import defaultdict

import numpy as np
import osmium
import pandas as pd

from common import RAW, WORK, lonlat_to_hexkey

PBF = os.path.join(RAW, "india-latest.osm.pbf")

POI_KEYS = ["power", "landuse", "man_made", "industrial", "aeroway", "harbour", "military",
            "amenity", "railway", "boundary", "leisure", "historic", "tourism", "office",
            "telecom", "crop", "trees", "waterway", "seamark:type", "place", "natural", "plant:source"]
LINE_KEYS = ["railway", "highway", "waterway"]


def classify(tags):
    """Return (category, subtype) or None for a tagged object."""
    g = tags.get
    if g("power") == "plant":
        return "power_plant", g("plant:source", "") or g("generator:source", "")
    if g("landuse") == "quarry" or g("industrial") == "mine" or g("man_made") in ("mineshaft", "adit"):
        return "mine", g("resource", "") or g("product", "")
    if g("aeroway") == "aerodrome":
        return "airport", g("aerodrome:type", "") or g("aerodrome", "")
    if g("industrial") == "port" or g("landuse") == "port" or g("harbour") == "yes" or g("seamark:type") == "harbour":
        return "port", g("harbour:category", "")
    if g("landuse") == "military" or g("military") in ("base", "naval_base", "airfield", "barracks", "training_area"):
        return "military", g("military", "")
    a = g("amenity")
    if a == "university":
        return "university", ""
    if a == "college":
        return "college", ""
    if a == "school":
        return "school", ""
    if a == "hospital":
        return "hospital", g("healthcare:speciality", "")
    if a in ("clinic", "doctors"):
        return "clinic", ""
    if a == "place_of_worship":
        return "worship", g("religion", "")
    if a == "bank":
        return "bank", ""
    if a == "research_institute" or g("office") == "research":
        return "research", ""
    if a in ("theatre", "arts_centre", "cinema"):
        return "arts", a
    if g("tourism") == "museum":
        return "museum", ""
    if g("historic") in ("monument", "fort", "castle", "archaeological_site", "ruins", "temple", "memorial", "city_gate", "palace"):
        return "heritage", g("historic")
    if g("tourism") == "attraction":
        return "attraction", ""
    if g("railway") == "station" and g("station") not in ("subway", "light_rail", "monorail"):
        return "rail_station", g("usage", "")
    if g("railway") == "station":
        return "metro_station", g("station", "")
    b = g("boundary")
    if b == "national_park" or (b == "protected_area" and g("protect_class") in ("1", "1a", "1b", "2", "4")) or g("leisure") == "nature_reserve":
        return "protected", g("protection_title", "") or b or ""
    if g("leisure") == "stadium":
        return "stadium", ""
    if g("telecom") in ("data_center", "datacenter") or g("building") == "data_center":
        return "data_center", ""
    if g("office") in ("it", "company", "software", "telecommunication"):
        return "office", g("office")
    if g("landuse") == "industrial":
        return "industrial", g("industrial", "")
    if g("man_made") == "works":
        return "works", g("product", "")
    if g("landuse") in ("orchard", "plantation") or g("crop") or g("trees"):
        return "plantation", g("crop", "") or g("trees", "") or g("produce", "")
    if g("waterway") == "dam" or g("man_made") == "dam":
        return "dam", ""
    if g("man_made") in ("petroleum_well", "oil_well") or g("industrial") in ("refinery", "oil"):
        return "oil", g("industrial", "") or g("man_made")
    if g("place") in ("city", "town"):
        return "place", g("place")
    if g("natural") in ("peak", "volcano") and g("ele"):
        return "peak", ""
    if g("natural") == "glacier":
        return "glacier", ""
    return None


KEEP_TAGS = ["name", "name:en", "plant:output:electricity", "plant:source", "resource", "religion",
             "denomination", "operator", "iata", "icao", "ele", "wikidata", "protect_class",
             "protection_title", "capacity", "product", "crop", "trees", "military", "harbour:category",
             "population", "industrial", "aerodrome:type", "beds", "denomination", "historic", "heritage",
             "start_date", "ownership", "station", "landuse", "office"]


class H(osmium.SimpleHandler):
    def __init__(self, rel_members):
        super().__init__()
        self.pois = []
        self.lines = []      # (kind, sub, name, lon array, lat array)
        self.rel_members = rel_members  # way id -> list of relation ids
        self.rel_pts = defaultdict(list)
        self.t = time.time()
        self.n = 0

    def _poi(self, kind, sub, tags, lon, lat, area_km2, osm_type, osm_id):
        rec = {"cat": kind, "sub": sub, "lon": lon, "lat": lat, "area_km2": area_km2,
               "osm": f"{osm_type}{osm_id}"}
        for k in KEEP_TAGS:
            v = tags.get(k)
            if v is not None:
                rec[k] = v
        self.pois.append(rec)

    def node(self, n):
        if not n.tags:
            return
        c = classify(n.tags)
        if c:
            self._poi(c[0], c[1], n.tags, n.location.lon, n.location.lat, 0.0, "n", n.id)

    def way(self, w):
        self.n += 1
        if self.n % 2_000_000 == 0:
            print(f"  ways {self.n/1e6:.0f}M  {time.time()-self.t:.0f}s", flush=True)
        rels = self.rel_members.get(w.id)
        tags = w.tags
        if not tags and not rels:
            return
        if not rels:
            if "building" in tags and len(tags) < 4:
                return
            rw, hw, ww = tags.get("railway"), tags.get("highway"), tags.get("waterway")
            line = (rw == "rail") or (hw in ("motorway", "trunk", "primary")) or (ww == "river")
            if not line and classify(tags) is None:
                return
        try:
            lons = np.fromiter((nd.lon for nd in w.nodes), float)
            lats = np.fromiter((nd.lat for nd in w.nodes), float)
        except osmium.InvalidLocationError:
            return
        if len(lons) < 2:
            return
        if rels:
            for rid in rels:
                self.rel_pts[rid].append((lons[::5], lats[::5]))
        if not tags:
            return
        rw, hw, ww = tags.get("railway"), tags.get("highway"), tags.get("waterway")
        if rw in ("rail",) and tags.get("service") is None and tags.get("usage") in (None, "main", "branch"):
            self.lines.append(("rail", tags.get("usage", ""), tags.get("name", ""), lons, lats))
        elif hw in ("motorway", "trunk", "primary"):
            self.lines.append(("road", hw, tags.get("ref", ""), lons, lats))
        elif ww == "river":
            self.lines.append(("river", "", tags.get("name:en") or tags.get("name", ""), lons, lats))
        c = classify(tags)
        if c:
            closed = w.is_closed() and len(lons) > 3
            area = 0.0
            if closed:
                # shoelace on a local equirectangular projection
                lat0 = math.radians(lats.mean())
                x = np.radians(lons) * 6371.0 * math.cos(lat0)
                y = np.radians(lats) * 6371.0
                area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
            self._poi(c[0], c[1], tags, float(lons.mean()), float(lats.mean()), area, "w", w.id)


class RelPass(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.rels = {}
        self.members = defaultdict(list)

    def relation(self, r):
        if r.tags.get("type") not in ("multipolygon", "boundary"):
            return
        c = classify(r.tags)
        if not c or c[0] not in ("protected", "military", "power_plant", "port", "airport", "industrial",
                                 "mine", "university", "heritage", "plantation"):
            return
        self.rels[r.id] = (c, {k: r.tags.get(k) for k in KEEP_TAGS if r.tags.get(k) is not None})
        for m in r.members:
            if m.type == "w" and m.role in ("outer", ""):
                self.members[m.ref].append(r.id)


t0 = time.time()
rp = RelPass()
rp.apply_file(PBF)
print("relations of interest:", len(rp.rels), "member ways:", len(rp.members), f"{time.time()-t0:.0f}s")

h = H(rp.members)
h.apply_file(PBF, locations=True, idx="flex_mem")
print("pass 2 done", f"{time.time()-t0:.0f}s", "pois", len(h.pois), "lines", len(h.lines))

for rid, ((cat, sub), tags) in rp.rels.items():
    pts = h.rel_pts.get(rid)
    if not pts:
        continue
    lons = np.concatenate([p[0] for p in pts]); lats = np.concatenate([p[1] for p in pts])
    lat0 = math.radians(lats.mean())
    w = (lons.max() - lons.min()) * 111.32 * math.cos(lat0)
    hgt = (lats.max() - lats.min()) * 110.57
    rec = {"cat": cat, "sub": sub, "lon": float(lons.mean()), "lat": float(lats.mean()),
           "area_km2": float(w * hgt * 0.6), "osm": f"r{rid}"}
    rec.update(tags)
    h.pois.append(rec)

poi = pd.DataFrame(h.pois)
poi["key"] = lonlat_to_hexkey(poi.lon.values, poi.lat.values)
poi.to_parquet(os.path.join(WORK, "osm_poi.parquet"))
print(poi.cat.value_counts().to_string())

# ---- lines -> per-hex length and hex-to-hex edges ----
recs = []
edges = defaultdict(float)
river_geo = defaultdict(list)
for kind, sub, name, lons, lats in h.lines:
    lat0 = np.radians(lats)
    dx = np.diff(lons) * 111.32 * np.cos(lat0[:-1])
    dy = np.diff(lats) * 110.57
    seg = np.hypot(dx, dy)
    mlon = (lons[:-1] + lons[1:]) / 2
    mlat = (lats[:-1] + lats[1:]) / 2
    keys = lonlat_to_hexkey(mlon, mlat)
    recs.append(pd.DataFrame({"kind": kind, "sub": sub, "key": keys, "km": seg}))
    if kind in ("rail", "road"):
        k = lonlat_to_hexkey(lons, lats)
        ch = np.nonzero(np.diff(k))[0]
        for i in ch:
            a, b = int(k[i]), int(k[i + 1])
            edges[(kind, sub if kind == "road" else "rail", min(a, b), max(a, b))] += 1
    if kind == "river" and name:
        river_geo[name].append((lons, lats, float(seg.sum())))

L = pd.concat(recs)
lh = L.groupby(["key", "kind", "sub"]).km.sum().reset_index()
lh.to_parquet(os.path.join(WORK, "osm_lines_hex.parquet"))
E = pd.DataFrame([{"kind": k[0], "sub": k[1], "a": k[2], "b": k[3], "n": v} for k, v in edges.items()])
E.to_parquet(os.path.join(WORK, "osm_edges.parquet"))

# Major rivers: keep names with >= 150 km mapped, simplify to ~1 km
import json
from shapely.geometry import LineString
rivers = []
for name, parts in river_geo.items():
    tot = sum(p[2] for p in parts)
    if tot < 150:
        continue
    lines = []
    for lons, lats, _ in parts:
        ls = LineString(np.c_[lons, lats]).simplify(0.01)
        lines.append([[round(x, 3), round(y, 3)] for x, y in ls.coords])
    rivers.append({"name": name, "km": round(tot), "lines": lines})
rivers.sort(key=lambda r: -r["km"])
json.dump(rivers, open(os.path.join(WORK, "rivers.json"), "w"))
print("rivers kept", len(rivers), [r["name"] for r in rivers[:25]])
print("done", f"{time.time()-t0:.0f}s")
