"""Hazards per hex and the wonder candidates.

Hazards
  * IBTrACS v04r01 North Indian basin: storms since 1990 at >= 34 kt that passed within ~40 km
  * USGS ComCat: earthquakes M4.5+ since 1990
Wonders
  * UNESCO World Heritage Sites in India (Wikidata), ranked by ASI 2024 footfall where known
  * National parks / tiger reserves (Wikidata), ranked by area
  * NIRF 2025 top institutions (Wikipedia tables of the official ranking)
Outputs: work/hazards.parquet, work/wonders.json
"""
import io
import json
import os
import re

import numpy as np
import pandas as pd

from common import NEIGHBOURS, RAW, WORK, hexkey, lonlat_to_hexkey

hexes = pd.read_parquet(os.path.join(WORK, "hexes.parquet"))
hexes["key"] = hexkey(hexes.q.values, hexes.r.values)
keys = set(hexes.key)


def ring1(k):
    q, r = k // 100000 - 50000, k % 100000 - 50000
    return [hexkey(q + dq, r + dr) for dq, dr in [(0, 0)] + NEIGHBOURS]


# ---------------- cyclones ----------------
ib = pd.read_csv(os.path.join(RAW, "ibtracs_ni.csv"), skiprows=[1], low_memory=False)
ib["ISO_TIME"] = pd.to_datetime(ib.ISO_TIME, errors="coerce")
ib = ib[ib.ISO_TIME.dt.year >= 1990]
for c in ["LAT", "LON", "USA_WIND", "WMO_WIND", "NEWDELHI_WIND"]:
    ib[c] = pd.to_numeric(ib[c], errors="coerce")
ib["wind"] = ib[["USA_WIND", "WMO_WIND", "NEWDELHI_WIND"]].max(axis=1)
ib = ib[ib.wind >= 34]
# densify tracks to ~10 km steps so fast storms don't skip hexes
rows = []
for sid, g in ib.sort_values("ISO_TIME").groupby("SID"):
    lat, lon, w = g.LAT.values, g.LON.values, g.wind.values
    for i in range(len(g)):
        rows.append((sid, lon[i], lat[i], w[i], g.NAME.iat[i]))
        if i + 1 < len(g):
            d = np.hypot(lat[i + 1] - lat[i], lon[i + 1] - lon[i]) * 111
            n = int(d // 10)
            for k in range(1, n):
                f = k / n
                rows.append((sid, lon[i] + f * (lon[i + 1] - lon[i]), lat[i] + f * (lat[i + 1] - lat[i]),
                             w[i] + f * (w[i + 1] - w[i]), g.NAME.iat[i]))
cy = pd.DataFrame(rows, columns=["sid", "lon", "lat", "wind", "name"])
cy["key"] = lonlat_to_hexkey(cy.lon.values, cy.lat.values)
cy_rows = []
for sid, k, w in zip(cy.sid, cy.key, cy.wind):
    for kk in ring1(k):
        cy_rows.append((kk, sid, w))
cyh = pd.DataFrame(cy_rows, columns=["key", "sid", "wind"]).groupby(["key", "sid"]).wind.max().reset_index()
cyc = cyh.groupby("key").agg(cyclones=("sid", "nunique"), cyc_maxwind=("wind", "max"))
severe = cyh[cyh.wind >= 64].groupby("key").sid.nunique().rename("severe_cyclones")
print("cyclone storms since 1990:", cy.sid.nunique())

# named landfalling storm list for the disaster advisor
storms = (ib.groupby("SID").agg(name=("NAME", "first"), year=("SEASON", "first"), wind=("wind", "max"))
          .reset_index().sort_values("wind", ascending=False))

# ---------------- earthquakes ----------------
q = json.load(open(os.path.join(RAW, "quakes.geojson")))["features"]
eq = pd.DataFrame([{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
                    "depth": f["geometry"]["coordinates"][2], "mag": f["properties"]["mag"],
                    "time": f["properties"]["time"], "place": f["properties"]["place"]} for f in q])
eq["key"] = lonlat_to_hexkey(eq.lon.values, eq.lat.values)
eqh = eq.groupby("key").agg(quakes=("mag", "size"), quake_max=("mag", "max"))
# shaking reaches neighbours: smoothed count over ring-1 for the lens
sm = {}
for k, n in eqh.quakes.items():
    for kk in ring1(k):
        sm[kk] = sm.get(kk, 0) + n
print("earthquakes M4.5+ since 1990 in frame:", len(eq))

hz = pd.DataFrame({"key": hexes.key})
hz = hz.join(cyc, on="key").join(severe, on="key").join(eqh, on="key")
hz["quakes_near"] = hz.key.map(sm)
hz = hz.fillna({"cyclones": 0, "severe_cyclones": 0, "quakes": 0, "quakes_near": 0})
hz.to_parquet(os.path.join(WORK, "hazards.parquet"))
big_quakes = eq.sort_values("mag", ascending=False).head(30)

# ---------------- wonders ----------------
def wd(path):
    out = []
    for b in json.load(open(os.path.join(RAW, path)))["results"]["bindings"]:
        out.append({k: v["value"] for k, v in b.items()})
    return pd.DataFrame(out)


def coord(s):
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", s if isinstance(s, str) else "")
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


whs = wd("wd_whs.json")
whs[["lon", "lat"]] = whs.coord.apply(lambda s: pd.Series(coord(s)))
NATURAL = {"(vii)", "(viii)", "(ix)", "(x)"}
whs["crit"] = whs.get("crit", "").fillna("")
agg = whs.groupby("s").agg(name=("sLabel", "first"), lon=("lon", "mean"), lat=("lat", "mean"),
                           whs=("whs", "first"), crit=("crit", lambda c: sorted(set(c)))).reset_index()
# component sites share a WHS id; collapse to one wonder per inscription, keeping the most-described item
agg = agg.dropna(subset=["lon", "whs"])
print("component/sub-site ids dropped:", sorted(agg[~agg.whs.str.fullmatch(r"\d+(rev|bis|ter)?")].name)[:40])
agg = agg[agg.whs.str.fullmatch(r"\d+(rev|bis|ter)?")]
agg = agg.sort_values("name").groupby("whs").first().reset_index()
foot = pd.read_csv(os.path.join(RAW, "monument_footfall_2024.csv"))


def footfall(name, lon, lat):
    d = np.hypot(foot.lat - lat, (foot.lon - lon) * np.cos(np.radians(lat)))
    i = d.idxmin()
    return foot.loc[i] if d[i] < 0.03 else None


wonders = []
for _, w in agg.iterrows():
    crit = [c for c in w.crit if re.match(r"^\(?[ivx]+\)?$", c.strip())]
    natural = any(f"({c.strip('()')})" in NATURAL for c in crit) and not any(
        f"({c.strip('()')})" in {"(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)"} for c in crit)
    f = footfall(w["name"], w.lon, w.lat)
    wonders.append({"type": "natural" if natural else "heritage", "name": w["name"], "lon": round(w.lon, 4),
                    "lat": round(w.lat, 4), "source": "UNESCO World Heritage List (via Wikidata)",
                    "visitors_dom": None if f is None or pd.isna(f.domestic) else int(f.domestic),
                    "visitors_for": None if f is None or pd.isna(f.foreign) else int(f.foreign),
                    "wikidata": w.s.rsplit("/", 1)[-1]})
print("World Heritage wonders:", len(wonders))

parks = wd("wd_parks.json")
parks[["lon", "lat"]] = parks.coord.apply(lambda s: pd.Series(coord(s)))
parks["area"] = pd.to_numeric(parks.get("area"), errors="coerce")
tig = wd("wd_tiger.json")
tig[["lon", "lat"]] = tig.coord.apply(lambda s: pd.Series(coord(s)))
tig["area"] = pd.to_numeric(tig.get("area"), errors="coerce")
tig["typeLabel"] = "tiger reserve"
pk = pd.concat([parks, tig]).dropna(subset=["lon"])
pk = pk.sort_values("area", ascending=False).drop_duplicates("s")
whs_ids = {w["wikidata"] for w in wonders}
nat = []
for _, p in pk.iterrows():
    if p.s.rsplit("/", 1)[-1] in whs_ids:
        continue
    nat.append({"type": "park", "name": p.sLabel, "lon": round(p.lon, 4), "lat": round(p.lat, 4),
                "area_km2": None if pd.isna(p.area) else round(float(p.area), 1), "kind": p.typeLabel,
                "source": "Wikidata (national parks, tiger reserves)", "wikidata": p.s.rsplit("/", 1)[-1]})
print("parks / reserves:", len(nat))

# NIRF 2025 (official ranking, tables reproduced on Wikipedia)
h = json.load(open(os.path.join(RAW, "wiki_nirf.json")))["parse"]["text"]
heads = [re.sub("<[^>]+>", "", m.group(1)) for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", h)]
tabs = pd.read_html(io.StringIO(h))
cats = [x for x in heads if "Top 10" in x]
nirf = []
ti = [i for i, t in enumerate(tabs) if "Name" in t.columns]
for cat, i in zip(cats, ti):
    t = tabs[i]
    rcol = [c for c in t.columns if str(c).startswith("Rank")][0]
    for _, r in t.iterrows():
        bud = re.search(r"₹([\d,.]+)\s*crore", str(r.get("Budget", "")))
        nirf.append({"category": cat.replace(" (Top 10)", ""), "rank": int(r[rcol]), "name": r.Name,
                     "city": r.City, "state": r.get("State/UT", r.get("State")),
                     "score": None if pd.isna(r.get("NIRF Score", np.nan)) else float(r["NIRF Score"]),
                     "budget_cr": float(bud.group(1).replace(",", "")) if bud else None})
print("NIRF entries:", len(nirf))

json.dump({"heritage": wonders, "parks": nat, "nirf": nirf, "storm_count": int(cy.sid.nunique()), "quake_count": int(len(eq)),
           "quake_count_india": int(eq.key.isin(set(hexes.key[hexes.kind == "india"])).sum()),
           "storms": storms.head(40).to_dict("records"),
           "big_quakes": big_quakes[["lon", "lat", "mag", "time", "place", "depth"]].to_dict("records")},
          open(os.path.join(WORK, "wonders.json"), "w"), default=lambda o: None if pd.isna(o) else o)
print(hz.describe().T[["count", "mean", "max"]])
