"""Reconcile every source onto the hex grid and write the web app's data files (web/data/*.json).

Game-language mapping (documented in the app's "How this map is made" panel):
  Food        <- cropland area (ESA WorldCover 2021) + grassland, fishing coast
  Production  <- industrial land, factories/works, mines, power capacity (OSM 2026) + timber
  Gold        <- GDP: MoSPI GSDP 2024-25, split within each state by population + non-residential built-up
  Science     <- universities, colleges, research institutes (OSM) + NIRF 2025 ranks
  Culture     <- World Heritage, monuments, museums, arts venues (UNESCO, OSM)
  Faith       <- mapped places of worship (OSM)
"""
import json
import math
import os
import re
from collections import Counter, defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd

from common import CRS, HEX_AREA_KM2, HEX_R, NEIGHBOURS, OUT, RAW, WORK, dump, hexkey, lonlat_to_hexkey
from pyproj import Transformer

T = Transformer.from_crs(4326, CRS, always_xy=True)


def xy_km(lon, lat):
    x, y = T.transform(lon, lat)
    return round(x / 1000, 2), round(y / 1000, 2)


# ======================================================================= load
hexes = pd.read_parquet(os.path.join(WORK, "hexes.parquet"))
hexes["key"] = hexkey(hexes.q.values, hexes.r.values)
hr = pd.read_parquet(os.path.join(WORK, "hex_raster.parquet"))
hz = pd.read_parquet(os.path.join(WORK, "hazards.parquet"))
H = hexes.merge(hr, on="key", how="left").merge(hz, on="key", how="left")
H = H.reset_index(drop=True)
idx_of = {k: i for i, k in enumerate(H.key)}

dist = gpd.read_parquet(os.path.join(WORK, "districts.parquet"))
draster = pd.read_parquet(os.path.join(WORK, "dist_raster.parquet")).set_index("dix")
nfhs = pd.read_parquet(os.path.join(WORK, "nfhs6_district.parquet"))
nfhs_state = pd.read_parquet(os.path.join(WORK, "nfhs6_state.parquet"))
se = pd.read_parquet(os.path.join(WORK, "state_econ.parquet"))
cities = pd.read_parquet(os.path.join(WORK, "cities.parquet"))
cpoly = gpd.read_parquet(os.path.join(WORK, "city_poly.parquet"))
poi = pd.read_parquet(os.path.join(WORK, "osm_poi.parquet"))
lines = pd.read_parquet(os.path.join(WORK, "osm_lines_hex.parquet"))
edges = pd.read_parquet(os.path.join(WORK, "osm_edges.parquet"))
rivers = json.load(open(os.path.join(WORK, "rivers.json")))
W = json.load(open(os.path.join(WORK, "wonders.json")))
airports = pd.read_csv(os.path.join(RAW, "airports.csv"))
airports = airports[(airports.iso_country == "IN") & airports.type.isin(["large_airport", "medium_airport", "small_airport"])]

claimed_dix = set(dist.dix[dist.claimed])
dist_state = dict(zip(dist.dix, dist.state))
H["state"] = H.dix.map(dist_state)
H.loc[H.dix.isin(claimed_dix) & (H.kind == "india"), "kind"] = "claimed"
india = H.kind.isin(["india"])

# ======================================================================= POIs per hex
poi = poi[poi.key.isin(idx_of)]
poi["hix"] = poi.key.map(idx_of)


def num(s):
    m = re.search(r"[\d.]+", str(s or "").replace(",", ""))
    if not m:
        return np.nan
    v = float(m.group())
    s = str(s).lower()
    if "gw" in s:
        v *= 1000
    elif "kw" in s and "mw" not in s:
        v /= 1000
    elif "mw" not in s and v > 20000:  # bare watts
        v /= 1e6
    return v


pp = poi[poi.cat == "power_plant"].copy()
pp["mw"] = pp["plant:output:electricity"].map(num) if "plant:output:electricity" in pp else np.nan
pp["src"] = pp["sub"].fillna("").str.split(";").str[0].str.strip().replace({"": "unknown"})
pp.loc[pp.src.isin(["photovoltaic", "solar_thermal"]), "src"] = "solar"
pp.loc[pp.src.isin(["water"]), "src"] = "hydro"
pp.loc[pp.src.isin(["gas", "oil", "diesel"]), "src"] = "gas_oil"
pp.loc[pp.src.isin(["biomass", "biofuel", "biogas", "waste"]), "src"] = "bio_waste"
print("power plants:", len(pp), "with MW:", pp.mw.notna().sum(), "total MW:", round(pp.mw.sum()))


def count_by_hex(mask, weight=None):
    s = poi[mask]
    if weight is None:
        return s.groupby("hix").size().reindex(range(len(H)), fill_value=0)
    return s.groupby("hix")[weight].sum().reindex(range(len(H)), fill_value=0)


C = poi.cat
H["univ"] = count_by_hex(C == "university")
H["college"] = count_by_hex(C == "college")
H["research"] = count_by_hex(C == "research")
H["school"] = count_by_hex(C == "school")
H["hospital"] = count_by_hex(C == "hospital")
H["clinic"] = count_by_hex(C == "clinic")
H["worship"] = count_by_hex(C == "worship")
H["heritage"] = count_by_hex(C == "heritage")
H["museum"] = count_by_hex(C == "museum")
H["arts"] = count_by_hex(C == "arts")
H["attraction"] = count_by_hex(C == "attraction")
H["bank"] = count_by_hex(C == "bank")
H["office"] = count_by_hex(C == "office")
H["mine"] = count_by_hex(C == "mine")
H["works"] = count_by_hex(C == "works")
H["military"] = count_by_hex(C == "military")
H["military_km2"] = count_by_hex(C == "military", "area_km2")
H["industrial_km2"] = count_by_hex(C == "industrial", "area_km2")
H["port"] = count_by_hex(C == "port")
H["rail_station"] = count_by_hex(C == "rail_station")
H["stadium"] = count_by_hex(C == "stadium")
H["protected_km2"] = count_by_hex(C == "protected", "area_km2")
H["dam"] = count_by_hex(C == "dam")
H["oil"] = count_by_hex(C == "oil")
H["data_center"] = count_by_hex(C == "data_center")
pmw = pp.groupby("hix").mw.sum()
H["power_mw"] = H.index.map(pmw).fillna(0)
H["power_n"] = pp.groupby("hix").size().reindex(range(len(H)), fill_value=0)
psrc = pp.assign(mw=pp.mw.fillna(0)).groupby(["hix", "src"]).mw.sum().unstack(fill_value=0)
H["power_src"] = [psrc.loc[i].idxmax() if i in psrc.index and psrc.loc[i].max() > 0 else
                  (pp[pp.hix == i].src.mode().iat[0] if (pp.hix == i).any() else "") for i in range(len(H))]

# worship by religion (mapped places; OSM coverage varies by region)
rel = poi[C == "worship"].copy()
rel["religion"] = rel["religion"].fillna("unspecified")
rel.loc[~rel.religion.isin(["hindu", "muslim", "christian", "sikh", "buddhist", "jain"]), "religion"] = "other"
relh = rel.groupby(["hix", "religion"]).size().unstack(fill_value=0)

# airports (OurAirports, current)
ap = airports.copy()
ap["key"] = lonlat_to_hexkey(ap.longitude_deg.values, ap.latitude_deg.values)
ap = ap[ap.key.isin(idx_of)]
ap["hix"] = ap.key.map(idx_of)
ap["mil"] = ap.name.str.contains("Air Force|AFS|Air Station|Naval|INS ", case=False, regex=True)
H["airport"] = ""
for _, a in ap.sort_values("type", ascending=False).iterrows():
    lvl = {"large_airport": "L", "medium_airport": "M", "small_airport": "s"}[a.type]
    if a.scheduled_service == "yes" or lvl == "L":
        cur = H.at[a.hix, "airport"]
        if cur == "" or (lvl == "L") or (cur == "s"):
            H.at[a.hix, "airport"] = lvl

# lines per hex
lw = lines.pivot_table(index="key", columns="kind", values="km", aggfunc="sum").reindex(H.key).fillna(0)
H["rail_km"] = lw["rail"].values if "rail" in lw else 0.0
H["road_km"] = lw["road"].values if "road" in lw else 0.0
H["river_km"] = lw["river"].values if "river" in lw else 0.0

# ======================================================================= terrain
coastal = np.zeros(len(H), bool)
for i, (q, r) in enumerate(zip(H.q, H.r)):
    if H.kind.iat[i] == "sea":
        continue
    for dq, dr in NEIGHBOURS:
        j = idx_of.get(hexkey(q + dq, r + dr))
        if j is not None and H.kind.iat[j] == "sea":
            coastal[i] = True
            break
H["coastal"] = coastal

TERR = ["ocean", "coast", "lake", "grassland", "plains", "desert", "tundra", "snow"]
FEAT = ["", "hills", "mountains", "forest", "rainforest", "marsh", "floodplain"]


def terrain(h):
    if h.kind == "sea":
        return "ocean" if (h.elev if not np.isnan(h.elev) else -999) < -150 else "coast", ""
    g = lambda c: 0 if np.isnan(h[c]) else h[c]
    snow, bare, tree, crop, grass, water = g("lc_snow"), g("lc_bare"), g("lc_tree"), g("lc_crop"), g("lc_grass"), g("lc_water")
    wet = g("lc_wetland") + g("lc_mangrove")
    elev, std, rain = g("elev"), g("elev_std"), g("rain_mm")
    relief = g("elev_max") - g("elev_min")
    if water > 0.6:
        return "lake", ""
    if snow > 0.35 or elev > 5300:
        base = "snow"
    elif elev > 3000:
        base = "tundra"
    elif bare > 0.4 or (rain and rain < 320):
        base = "desert"
    elif rain >= 1100:
        base = "grassland"
    else:
        base = "plains"
    feat = ""
    if std > 380 or relief > 2600:
        feat = "mountains"
    elif wet > 0.12:
        feat = "marsh"
    elif tree > 0.5 and rain >= 2000 and elev < 1800:
        feat = "rainforest"
    elif tree > 0.42:
        feat = "forest"
    elif std > 85:
        feat = "hills"
    elif h.river_km > 30 and elev < 200 and crop > 0.5:
        feat = "floodplain"
    return base, feat


tf = [terrain(h) for _, h in H.iterrows()]
H["terrain"] = [a for a, _ in tf]
H["feature"] = [b for _, b in tf]
print(H[H.kind == "india"].terrain.value_counts().to_dict())
print(H[H.kind == "india"].feature.value_counts().to_dict())

# ======================================================================= GDP (₹ crore, 2024-25)
# Each state's official GSDP is split inside the state: half by population (GHS-POP 2025), half by
# non-residential built-up surface (GHSL 2025: offices, factories, shops, warehouses).
# (Kummu et al.'s admin-2 GDP grid was evaluated and rejected: it ranks Patna below Kishanganj.)
gsdp = se.gsdp_cr_2425.dropna()


def gdp_weights(frame, mask):
    f = frame[mask]
    ps = f.groupby("state")["pop"].transform("sum")
    ns = f.groupby("state")["built_nres_km2"].transform("sum")
    w = pd.Series(0.0, index=frame.index)
    w[mask] = 0.5 * f["pop"].fillna(0) / ps + 0.5 * f["built_nres_km2"].fillna(0) / ns.replace(0, np.nan)
    return w.fillna(0)


_dw = draster.join(dist.set_index("dix")[["state", "claimed"]])
_ok = ~_dw.claimed
# states MoSPI doesn't publish: same rule applied at national level
nat_pop, nat_nres = _dw.loc[_ok, "pop"].sum(), _dw.loc[_ok, "built_nres_km2"].sum()
_ps = _dw[_ok].groupby("state")[["pop", "built_nres_km2"]].sum()
pub = _ps.reindex(gsdp.index)
gdp_unit = gsdp.sum() / (0.5 * pub["pop"].sum() / nat_pop + 0.5 * pub["built_nres_km2"].sum() / nat_nres)
st_total = {s: (gsdp[s] if s in gsdp.index else gdp_unit * (0.5 * r["pop"] / nat_pop + 0.5 * r.built_nres_km2 / nat_nres))
            for s, r in _ps.iterrows()}
print("states estimated (no MoSPI GSDP):", {s: round(v) for s, v in st_total.items() if s not in gsdp.index})
H["gdp_w"] = gdp_weights(H, H.kind == "india")
H["gdp_cr"] = [w * st_total.get(s, 0) for w, s in zip(H.gdp_w, H.state)]
print("hex GDP total ₹ lakh crore:", round(H.gdp_cr.sum() / 1e5, 2), "(GSDP sum", round(gsdp.sum() / 1e5, 2), ")")

# ======================================================================= yields
# raw quantities in real units, then 0-6 pips by sextile of positive values across India hexes
H["food_raw"] = (H.lc_crop.fillna(0) * 1.0 + H.lc_grass.fillna(0) * 0.35 + H.lc_shrub.fillna(0) * 0.1) * HEX_AREA_KM2 \
    + np.where(H.coastal, 60, 0) + np.where(H.feature == "floodplain", 40, 0)
H["prod_raw"] = H.industrial_km2 * 40 + H.works * 2 + H.mine * 3 + H.power_mw / 50 + H.oil * 5 \
    + H.lc_tree.fillna(0) * HEX_AREA_KM2 * 0.05
H["gold_raw"] = H.gdp_cr
H["sci_raw"] = H.univ * 8 + H.college * 1 + H.research * 6
H["cult_raw"] = H.heritage * 2 + H.museum * 3 + H.arts + H.attraction * 0.5
H["faith_raw"] = H.worship.astype(float)


def pips(col):
    v = H.loc[india, col]
    pos = v[v > 0]
    qs = np.quantile(pos, [1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6]) if len(pos) else [0] * 5
    out = np.zeros(len(H), int)
    vals = H[col].values
    for i in range(len(H)):
        if not india.iat[i] or vals[i] <= 0:
            continue
        out[i] = 1 + int(np.searchsorted(qs, vals[i], side="right"))
    return out, [float(x) for x in qs]


yield_q = {}
for y in ["food", "prod", "gold", "sci", "cult", "faith"]:
    H["y_" + y], yield_q[y] = pips(y + "_raw")
# wonders add culture/science (applied below once wonders are placed)

# ======================================================================= resources
RES_MINE = {"coal": "coal", "lignite": "coal", "iron_ore": "iron", "iron": "iron", "bauxite": "bauxite",
            "aluminium": "bauxite", "limestone": "limestone", "copper": "copper", "gold": "gold",
            "diamond": "diamonds", "diamonds": "diamonds", "manganese": "manganese", "chromite": "chromite",
            "chromium": "chromite", "zinc": "zinc", "lead": "zinc", "mica": "mica", "uranium": "uranium",
            "marble": "marble", "granite": "stone", "sandstone": "stone", "stone": "stone", "salt": "salt",
            "sand": "sand", "gravel": "stone"}
RES_CROP = {"tea": "tea", "coffee": "coffee", "rubber": "rubber", "coconut": "coconut", "coconut_palm": "coconut",
            "cashew": "cashew", "mango": "mango", "banana": "banana", "apple": "apples", "oil_palm": "oil palm",
            "areca": "areca", "arecanut": "areca", "cardamom": "spices", "pepper": "spices", "black_pepper": "spices",
            "orange": "citrus", "citrus": "citrus", "grape": "grapes", "grapes": "grapes", "sugarcane": "sugarcane",
            "cotton": "cotton", "rice": "rice", "saffron": "saffron", "pomegranate": "pomegranate"}
res = defaultdict(Counter)
mines = poi[C == "mine"]
for hix, s, name in zip(mines.hix, mines["sub"].fillna("") + ";" + mines.get("resource", pd.Series(dtype=str)).reindex(mines.index).fillna(""),
                        mines.get("name", pd.Series(dtype=str)).reindex(mines.index).fillna("")):
    hit = False
    for tok in re.split(r"[;,\s]+", s.lower()):
        if tok in RES_MINE:
            res[hix][RES_MINE[tok]] += 1
            hit = True
    if not hit:
        nl = name.lower()
        for k in ["coal", "iron", "bauxite", "limestone", "manganese", "copper", "zinc", "uranium", "marble", "granite", "chromite", "diamond", "gold"]:
            if k in nl:
                res[hix][RES_MINE.get(k, k if k != "iron" else "iron")] += 1
                break
pl_ = poi[C == "plantation"]
for hix, s, name in zip(pl_.hix, pl_["sub"].fillna(""), pl_.get("name", pd.Series(dtype=str)).reindex(pl_.index).fillna("")):
    toks = [t for t in re.split(r"[;,\s]+", s.lower()) if t]
    nl = name.lower()
    got = [RES_CROP[t] for t in toks if t in RES_CROP]
    if not got:
        for k in ["tea", "coffee", "rubber", "coconut", "cardamom", "apple", "mango", "cashew"]:
            if re.search(r"\b" + k + r"\b", nl):
                got = [RES_CROP.get(k, k)]
                break
    for g_ in got:
        res[hix][g_] += 1
for hix in poi[C == "oil"].hix:
    res[hix]["oil"] += 1
H["resources"] = [",".join(k for k, _ in res[i].most_common(3)) if i in res else "" for i in range(len(H))]
print("hexes with resources:", sum(1 for i in res if india.iat[i]))

# ======================================================================= hex output
xs = np.round(H.x / 1000, 2)
ys = np.round(H.y / 1000, 2)
KIND = {"india": 0, "foreign": 1, "sea": 2, "claimed": 3}
STATES = sorted(dist[~dist.claimed].state.unique())
sidx = {s: i for i, s in enumerate(STATES)}


def col(series, nd=0):
    out = []
    for v in series:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            out.append(None)
        else:
            out.append(round(float(v), nd) if nd else int(round(float(v))))
    return out


hex_out = {
    "hexR_km": HEX_R / 1000, "area_km2": HEX_AREA_KM2,
    "q": H.q.tolist(), "r": H.r.tolist(), "x": xs.tolist(), "y": ys.tolist(),
    "lon": H.lon.round(3).tolist(), "lat": H.lat.round(3).tolist(),
    "kind": [KIND[k] for k in H.kind], "d": [int(d) if k in ("india", "claimed") else -1 for d, k in zip(H.dix, H.kind)],
    "s": [sidx.get(s, -1) if k == "india" else -1 for s, k in zip(H.state, H.kind)],
    "t": [TERR.index(t) for t in H.terrain], "f": [FEAT.index(f) for f in H.feature],
    "elev": col(H.elev), "relief": col(H.elev_max - H.elev_min), "pop": col(H["pop"].where(india)),
    "built": col(H.built_km2.where(india), 2), "gdp": col(H.gdp_cr.where(india), 1),
    "rain": col(H.rain_mm), "temp": col(H.temp_c, 1),
    "tree": col(H.lc_tree * 100), "crop": col(H.lc_crop * 100), "bare": col(H.lc_bare * 100),
    "yf": H.y_food.tolist(), "yp": H.y_prod.tolist(), "yg": H.y_gold.tolist(), "ys": H.y_sci.tolist(),
    "yc": H.y_cult.tolist(), "yr": H.y_faith.tolist(),
    "univ": H.univ.tolist(), "college": H.college.tolist(), "research": H.research.tolist(),
    "hosp": H.hospital.tolist(), "clinic": H.clinic.tolist(), "school": H.school.tolist(),
    "worship": H.worship.tolist(), "herit": H.heritage.tolist(), "museum": H.museum.tolist(),
    "mine": H.mine.tolist(), "works": H.works.tolist(), "ind": col(H.industrial_km2, 2),
    "mil": col(H.military_km2, 1), "milN": H.military.tolist(), "port": H.port.tolist(),
    "pmw": col(H.power_mw), "psrc": H.power_src.tolist(), "pn": H.power_n.tolist(),
    "air": H.airport.tolist(), "rail": col(H.rail_km, 1), "road": col(H.road_km, 1), "river": col(H.river_km, 1),
    "stn": H.rail_station.tolist(), "prot": col(H.protected_km2, 1), "dam": H.dam.tolist(),
    "cyc": col(H.cyclones), "scyc": col(H.severe_cyclones), "eq": col(H.quakes), "eqn": col(H.quakes_near),
    "eqmax": col(H.quake_max, 1), "res": H.resources.tolist(), "coast": H.coastal.astype(int).tolist(),
    "rel": [{k: int(v) for k, v in relh.loc[i].items() if v} if i in relh.index else None for i in range(len(H))],
}

# ======================================================================= districts table
D = dist[["dix", "name", "state", "area_km2", "claimed"]].copy().set_index("dix")
D["pop"] = draster["pop"]
D["built_km2"] = draster.get("built_km2")
D["built_nres_km2"] = draster.get("built_nres_km2")
D.loc[D.claimed, ["pop", "built_nres_km2"]] = np.nan
D["gdp_w"] = gdp_weights(D, ~D.claimed)
D["gdp_cr"] = [w * st_total.get(s, 0) if not c else np.nan for w, s, c in zip(D.gdp_w, D.state, D.claimed)]
D["nres_pct"] = D.built_nres_km2 / D.area_km2 * 100
D["gdp_pc"] = D.gdp_cr * 1e7 / D["pop"]
D["density"] = D["pop"] / D.area_km2
D["built_pct"] = D.built_km2 / D.area_km2 * 100

# hex-derived sums per district (area-weighted by majority assignment)
hd = H[india | (H.kind == "claimed")].groupby("dix")
for c_, h_ in [("forest_pct", "lc_tree"), ("crop_pct", "lc_crop"), ("elev_m", "elev"), ("rain_mm", "rain_mm"), ("temp_c", "temp_c")]:
    D[c_] = hd[h_].mean() * (100 if c_.endswith("pct") else 1)
for c_ in ["univ", "college", "hospital", "worship", "heritage", "museum", "mine", "power_mw", "rail_km", "road_km",
           "military_km2", "industrial_km2", "port", "cyclones", "severe_cyclones", "quakes", "quakes_near"]:
    D[c_] = hd[c_].sum() if c_ not in ("cyclones", "severe_cyclones", "quakes_near") else hd[c_].max()
# POIs straight from points for districts too small to own a hex
pts = gpd.GeoDataFrame(poi[["cat"]], geometry=gpd.points_from_xy(poi.lon, poi.lat), crs=4326)
pj = gpd.sjoin(pts, dist[["dix", "geometry"]].to_crs(4326), predicate="within", how="inner")
pc = pj.groupby(["dix", "cat"]).size().unstack(fill_value=0)
for c_, cat in [("univ", "university"), ("college", "college"), ("hospital", "hospital"), ("worship", "worship"),
                ("heritage", "heritage"), ("museum", "museum"), ("mine", "mine")]:
    D[c_] = pc.get(cat, pd.Series(dtype=float)).reindex(D.index).fillna(0)
D["hosp_per100k"] = D.hospital / D["pop"] * 1e5
D["college_per100k"] = (D.college + D.univ) / D["pop"] * 1e5
D["worship_per100k"] = D.worship / D["pop"] * 1e5

NF = {  # short id: (NFHS-6 indicator, label, better)
    "women_10yr": ("Women with 10 or more years of schooling (%)", "Women with 10+ yrs schooling", "high"),
    "men_10yr": ("Men with 10 or more years of schooling (%)", "Men with 10+ yrs schooling", "high"),
    "girls_school": ("Female population age 6 years and above who ever attended school (%)", "Females 6+ who ever attended school", "high"),
    "women_internet": ("Women who have ever used the internet (%)", "Women who ever used internet", "high"),
    "men_internet": ("Men who have ever used the internet (%)", "Men who ever used internet", "high"),
    "women_phone": ("Women having a mobile phone that they themselves use (%)", "Women with own mobile phone", "high"),
    "women_bank": ("Women having a bank or savings account that they themselves use (%)", "Women with own bank account", "high"),
    "electricity": ("Population living in households with electricity (%)", "Households with electricity", "high"),
    "water": ("Population living in households with an improved drinking-water source (%)", "Improved drinking water", "high"),
    "insurance": ("Households with any usual member covered under a health insurance/financing scheme (%)", "Health insurance coverage", "high"),
    "women_property": ("Households with any usual female members owning a house and/or land (alone or jointly with others) (%)", "Women owning house/land", "high"),
    "child_marriage": ("Women age 20-24 years married before age 18 years (%)", "Girls married before 18", "low"),
    "teen_mothers": ("Women age 15-19 years who were already mothers or pregnant at the time of the survey (%)", "Teen pregnancy (15-19)", "low"),
    "stunted": ("Children under 5 years who are stunted (height-for-age (%)", "Child stunting (<5)", "low"),
    "wasted": ("Children under 5 years who are wasted (weight-for-height (%)", "Child wasting (<5)", "low"),
    "underweight": ("Children under 5 years who are underweight (weight-for-age (%)", "Child underweight (<5)", "low"),
    "child_overweight": ("Children under 5 years who are overweight (weight-for-height (%)", "Child overweight (<5)", "low"),
    "women_obese": ("Women who are overweight or obese (BMI ≥25.0 kg/m2 (%)", "Women overweight/obese", "low"),
    "inst_births": ("Institutional births (%)", "Institutional births", "high"),
    "csection": ("Births delivered by caesarean section (%)", "Caesarean births", None),
    "anc4": ("Mothers who had at least 4 antenatal care visits (%)", "4+ antenatal visits", "high"),
    "vacc_bcg": ("Children age 12-23 months who have received BCG (%)", "BCG vaccinated (12-23m)", "high"),
    "vacc_mcv": ("Children age 12-23 months who have received the first dose of measles-containing vaccine (MCV) (%)", "Measles vaccine dose 1", "high"),
    "contraception": ("Any modern method (%)", "Modern contraception use", "high"),
    "men_tobacco": ("Men age 15 years and above who use any kind of tobacco (%)", "Men using tobacco", "low"),
    "women_tobacco": ("Women age 15 years and above who use any kind of tobacco (%)", "Women using tobacco", "low"),
    "men_alcohol": ("Men age 15 years and above who consume alcohol (%)", "Men consuming alcohol", "low"),
    "high_sugar": ("Blood sugar level - high or very high (>140 mg/dl) or taking medicine to control blood sugar level (%)", "High blood sugar (women)", "low"),
    "under15": ("Population below age 15 years (%)", "Population under 15", None),
    "over60": ("Population age 60 years and above (%)", "Population 60+", None),
    "preschool": ("Children age 2-4 years who attended pre-school (%)", "Pre-school attendance (2-4)", "high"),
    "hygienic_period": ("Women age 15-24 years who use hygienic methods of protection during their menstrual period (%)", "Hygienic menstrual protection", "high"),
    "iodized_salt": ("Households using iodized salt (%)", "Iodized salt", "high"),
    "bank_hh": ("Households with any usual member having a bank account/post office account (%)", "Household bank account", "high"),
}
inds = set(nfhs.columns)
for k, (ind, _, _) in NF.items():
    cand = ind if ind in inds else next((c for c in inds if c.startswith(ind[:60])), None)
    if cand is None:
        print("!! NFHS indicator missing:", ind)
        D[k] = np.nan
    else:
        D[k] = nfhs[cand]
D["nfhs_source"] = nfhs.nfhs_source
D.loc[D.claimed, list(NF) + ["nfhs_source"]] = [np.nan] * len(NF) + ["none"]
for k in ["plfs_A", "plfs_C", "plfs_F", "plfs_G", "plfs_J", "plfs_M", "plfs_P", "plfs_Q", "wpr_total", "wpr_female"]:
    D[k] = D.state.map(se[k]) if k in se else np.nan
D["agri_share_state"] = D.pop("plfs_A")

COLS = {  # id: (label, unit, group, source, better)
    "pop": ("Population 2025", "people", "People", "GHS-POP 2025 (JRC GHSL R2023A)", None),
    "density": ("Population density", "/km²", "People", "GHS-POP 2025 ÷ district area", None),
    "area_km2": ("Area", "km²", "Land", "geoBoundaries / LGD district boundaries", None),
    "gdp_cr": ("GDP 2024-25", "₹ crore", "Economy", "MoSPI GSDP 2024-25, split by population + non-residential built-up (GHSL 2025)", "high"),
    "gdp_pc": ("GDP per person", "₹", "Economy", "Modelled GDP ÷ GHS-POP 2025", "high"),
    "built_pct": ("Built-up land", "%", "Land", "GHSL built-up surface 2025", None),
    "forest_pct": ("Tree cover", "%", "Land", "ESA WorldCover 2021", "high"),
    "crop_pct": ("Cropland", "%", "Land", "ESA WorldCover 2021", None),
    "elev_m": ("Mean elevation", "m", "Land", "AWS Terrain Tiles (SRTM/GMTED)", None),
    "rain_mm": ("Annual rainfall (normal)", "mm", "Land", "WorldClim 2.1 (1970-2000 normal)", None),
    "temp_c": ("Mean temperature (normal)", "°C", "Land", "WorldClim 2.1 (1970-2000 normal)", None),
    "hosp_per100k": ("Hospitals per 100k (mapped)", "", "Health", "OpenStreetMap 2026", "high"),
    "college_per100k": ("Colleges & universities per 100k (mapped)", "", "Education", "OpenStreetMap 2026", "high"),
    "worship_per100k": ("Places of worship per 100k (mapped)", "", "Faith", "OpenStreetMap 2026", None),
    "univ": ("Universities (mapped)", "", "Education", "OpenStreetMap 2026", "high"),
    "heritage": ("Monuments & heritage sites (mapped)", "", "Culture", "OpenStreetMap 2026", "high"),
    "power_mw": ("Power capacity (mapped plants)", "MW", "Infrastructure", "OpenStreetMap 2026 (plant:output tags)", None),
    "rail_km": ("Railway track", "km", "Infrastructure", "OpenStreetMap 2026", "high"),
    "road_km": ("Major roads (NH/SH/primary)", "km", "Infrastructure", "OpenStreetMap 2026", "high"),
    "mine": ("Mines & quarries (mapped)", "", "Economy", "OpenStreetMap 2026", None),
    "cyclones": ("Cyclones since 1990 (≥34 kt, max hex)", "", "Hazards", "IBTrACS v04r01 North Indian basin", "low"),
    "severe_cyclones": ("Severe cyclones since 1990 (≥64 kt)", "", "Hazards", "IBTrACS v04r01", "low"),
    "quakes": ("Earthquakes M4.5+ since 1990", "", "Hazards", "USGS ComCat", "low"),
    "agri_share_state": ("Workers in agriculture (state)", "%", "Work", "PLFS Annual Report 2025, Table 27", None),
    "plfs_C": ("Workers in manufacturing (state)", "%", "Work", "PLFS 2025, Table 27", None),
    "plfs_J": ("Workers in ICT (state)", "%", "Work", "PLFS 2025, Table 27", None),
    "wpr_female": ("Female worker-population ratio (state)", "%", "Work", "PLFS 2025, Table 17.0", "high"),
}
for k, (_, lab, better) in NF.items():
    grp = "Health" if k in ("stunted", "wasted", "underweight", "child_overweight", "women_obese", "inst_births", "csection",
                            "anc4", "vacc_bcg", "vacc_mcv", "men_tobacco", "women_tobacco", "men_alcohol", "high_sugar",
                            "insurance", "contraception", "hygienic_period", "iodized_salt", "teen_mothers") else \
        ("Education" if k in ("women_10yr", "men_10yr", "girls_school", "preschool") else
         ("People" if k in ("under15", "over60", "child_marriage") else "Living standards"))
    COLS[k] = (lab, "%", grp, "NFHS-6 (2023-24) district fact sheets", better)

col_ids = list(COLS)
rows = []
for dix, d in D.iterrows():
    r = [int(dix), d["name"], d.state, d.nfhs_source]
    for c_ in col_ids:
        v = d.get(c_)
        r.append(None if v is None or pd.isna(v) else (round(float(v), 2) if abs(float(v)) < 1000 else round(float(v))))
    rows.append(r)
dists_out = {"cols": ["dix", "name", "state", "nfhs"] + col_ids,
             "meta": {k: {"label": v[0], "unit": v[1], "group": v[2], "source": v[3], "better": v[4]} for k, v in COLS.items()},
             "rows": rows}
# district label anchors
dc = dist.to_crs(CRS).representative_point()
dists_out["xy"] = [[round(p.x / 1000, 1), round(p.y / 1000, 1)] for p in dc]

# ======================================================================= states
S = pd.DataFrame(index=STATES)
hs = H[india].groupby("state")
S["pop"] = hs["pop"].sum()
S["area_km2"] = dist[~dist.claimed].groupby("state").area_km2.sum()
S["gdp_cr"] = pd.Series(st_total)
S["gsdp_reported"] = S.index.isin(gsdp.index)
S["gdp_pc"] = S.gdp_cr * 1e7 / S["pop"]
for c_ in ["univ", "college", "hospital", "worship", "heritage", "power_mw", "rail_km", "road_km", "mine", "military_km2", "port"]:
    S[c_] = hs[c_].sum()
S = S.join(se.drop(columns=[c for c in se.columns if c.startswith("gsdp")], errors="ignore"))
for k, (ind, lab, better) in NF.items():
    cand = ind if ind in nfhs_state.columns else next((c for c in nfhs_state.columns if c.startswith(ind[:60])), None)
    S["nfhs_" + k] = nfhs_state[cand].reindex(S.index) if cand else np.nan
psrc_state = pp.assign(state=pp.hix.map(H.state)).groupby(["state", "src"]).mw.sum().unstack(fill_value=0)
rel_state = rel.assign(state=rel.hix.map(H.state)).groupby(["state", "religion"]).size().unstack(fill_value=0)
states_out = {"names": STATES, "rows": json.loads(S.reset_index().rename(columns={"index": "state"}).to_json(orient="records")),
              "power_src": json.loads(psrc_state.round(0).to_json(orient="index")),
              "worship_rel": json.loads(rel_state.to_json(orient="index")),
              "plfs_sections": {"A": "Agriculture, forestry & fishing", "B": "Mining & quarrying", "C": "Manufacturing",
                                "D": "Electricity & gas", "E": "Water & waste", "F": "Construction", "G": "Trade & repair",
                                "H": "Transport & storage", "I": "Hotels & restaurants", "J": "Information & communication",
                                "K": "Finance & insurance", "L": "Real estate", "M": "Professional & scientific",
                                "N": "Administrative services", "O": "Public administration & defence", "P": "Education",
                                "Q": "Health & social work", "R": "Arts & recreation", "S": "Other services", "T": "Households as employers"},
              "plfs_all_india": None}
# national PLFS row
if "all India" in se.index or "all-India" in se.index:
    pass

# ======================================================================= cities
cities = cities[cities.GC_POP_TOT_2025 >= 50000].copy()  # every urban centre >= 50k
cpoly = cpoly[cpoly.ID_UC_G0.isin(cities.ID_UC_G0)]
cj = gpd.sjoin(pts, cpoly, predicate="within", how="inner")
cj = cj.join(poi[[c for c in ["sub", "name", "industrial", "product", "office"] if c in poi.columns]], how="left")
ccount = cj.groupby(["ID_UC_G0", "cat"]).size().unstack(fill_value=0)
cind = cj[cj.cat == "industrial"].join(poi[["area_km2"]]).groupby("ID_UC_G0").area_km2.sum()

KEYWORDS = {
    "auto": (r"\b(motors?|automobiles?|automotive|auto ?components?|maruti|hyundai|tata motors|ashok leyland|hero motocorp|tvs motor|bajaj auto|renault|nissan|toyota kirloskar|honda cars|kia|tractors?)\b", "Motor City"),
    "pharma": (r"\b(pharma|pharmaceuticals?|drugs|laborator(y|ies)|biotech|life ?sciences|formulations?|api park)\b", "Pharma Hub"),
    "textile": (r"\b(textiles?|spinning|weaving|garments?|apparels?|knit(ting|wear)?|hosiery|silk|dyeing|cotton mills?|powerloom)\b", "Textile City"),
    "steel": (r"\b(steel plant|steel works|ispat|steel (ltd|limited)|steel authority|tata steel|jsw steel|jindal steel|essar steel|bhilai steel|rourkela steel|bokaro steel|vizag steel|rashtriya ispat|blast furnace)\b", "Steel City"),
    "coal": (r"\b(coal|colliery|collieries|bccl|ccl|ecl|mcl|wcl|secl|ncl|open ?cast)\b", "Coal Capital"),
    "tech": (r"\b(tech ?park|technology park|it park|software|infotech|cyber ?(city|towers?)|technopark|tech city|infosys|wipro|tcs|hcl|cognizant|accenture|ibm|microsoft|google|amazon|oracle)\b", "Tech City"),
    "diamond": (r"\b(diamonds?|gems?|jewel(le)?ry)\b", "Diamond City"),
    "petro": (r"\b(refinery|petroleum|petrochemicals?|ongc|iocl|bpcl|hpcl|oil refinery)\b", "Refinery Town"),
    "cement": (r"\b(cement|ultratech|ambuja)\b", "Cement Town"),
    "sugar": (r"\b(sugar|sakhar|distillery)\b", "Sugar Belt"),
    "leather": (r"\b(leather|tannery|tanneries|footwear)\b", "Leather Town"),
    "brass": (r"\b(brass|handicrafts?|metal ?crafts?)\b", "Brass City"),
}
kw_counts = defaultdict(Counter)
_prod = cj["product"] if "product" in cj else pd.Series(None, index=cj.index, dtype=object)
named = cj[cj.cat.isin(["industrial", "works", "office", "mine"]) & (cj.name.notna() | _prod.notna() | (cj.cat == "mine"))]
_txt = (named.name.fillna("") + " " + _prod.reindex(named.index).fillna("") + " " + named["sub"].fillna("")).str.lower()
for cid, nm in zip(named.ID_UC_G0, _txt):
    for k, (rx, _) in KEYWORDS.items():
        if re.search(rx, nm):
            kw_counts[cid][k] += 1
kw_tot = Counter()
for cid, c_ in kw_counts.items():
    kw_tot.update(c_)

STATE_CAPITALS = {"Amaravati", "Itanagar", "Dispur", "Guwahati", "Patna", "Raipur", "Panaji", "Gandhinagar", "Chandigarh",
                  "Shimla", "Ranchi", "Bengaluru", "Thiruvananthapuram", "Bhopal", "Mumbai", "Imphal", "Shillong", "Aizawl",
                  "Kohima", "Bhubaneswar", "Jaipur", "Gangtok", "Chennai", "Hyderabad", "Agartala", "Lucknow", "Dehradun",
                  "Kolkata", "Srinagar", "Jammu", "Leh", "Puducherry", "Port Blair", "Kavaratti", "Daman", "New Delhi", "Delhi"}

nat_pop = cities.GC_POP_TOT_2025.sum()
tot = ccount.sum()
nat_rate = {k: tot.get(k, 0) / nat_pop for k in ["university", "college", "research", "hospital", "worship", "heritage", "museum",
                                                   "arts", "bank", "office", "works", "stadium", "attraction", "data_center"]}
nat_ind_rate = cind.sum() / nat_pop
nirf_by_city = defaultdict(list)
for n in W["nirf"]:
    nirf_by_city[str(n["city"]).lower()].append(n)

ap_pts = airports[airports.scheduled_service == "yes"]
city_out = []
for ci, c in cities.reset_index(drop=True).iterrows():
    cid = c.ID_UC_G0
    cnt = ccount.loc[cid] if cid in ccount.index else pd.Series(dtype=float)
    g = lambda k: int(cnt.get(k, 0))
    popc = float(c.GC_POP_TOT_2025)
    lq = lambda k: (g(k) / popc) / nat_rate[k] if nat_rate.get(k) else 0
    name = c.GC_UCN_MAI_2025
    names = list(dict.fromkeys(n.strip() for n in str(c.GC_UCN_LIS_2025).split(";") if n.strip()))
    # GHSL draws urban centres from 1 km cells >= 1,500 people/km2; across the Gangetic and Kerala
    # plains that merges villages into vast low-density "centres". Flag them as belts.
    belt = (popc / max(c.GC_UCA_KM2_2025, 1) < 6000) and c.GC_UCA_KM2_2025 > 500
    if belt:
        name = "–".join(names[:2]) + " belt" if len(names) > 1 else f"{name} belt"
    nirf = []
    for n in names[:6] + [name]:
        nirf += nirf_by_city.get(n.lower(), [])
    nirf += nirf_by_city.get({"New Delhi": "new delhi"}.get(name, "__"), [])
    if name in ("New Delhi",):
        nirf += nirf_by_city.get("delhi", [])
    nirf = list({(n["category"], n["name"]): n for n in nirf}.values())
    hexes_c = [(idx_of[int(k)], a) for k, a in (c.hexes if isinstance(c.hexes, (list, np.ndarray)) else []) if int(k) in idx_of]
    hix_c = [i for i, _ in hexes_c]
    near = lambda col_, km: H.loc[[i for i in hix_c], col_].sum() if hix_c else 0
    # districts (specialisations) — each with the evidence that earned it
    dists_ = []
    sci = g("university") * 5 + g("college") + g("research") * 3
    sci_lq = (sci / popc) / ((tot.get("university", 0) * 5 + tot.get("college", 0) + tot.get("research", 0) * 3) / nat_pop)
    if nirf or (sci_lq >= 1.4 and sci >= 15):
        dists_.append({"id": "campus", "name": "Campus", "why": (f"{len(nirf)} NIRF 2025 top-10 ranking(s); " if nirf else "") +
                       f"{g('university')} universities, {g('college')} colleges, {g('research')} research institutes mapped ({sci_lq:.1f}× national urban rate)"})
    bo = g("bank") + g("office") * 2
    bo_lq = (bo / popc) / ((tot.get("bank", 0) + tot.get("office", 0) * 2) / nat_pop)
    if bo_lq >= 1.3 and bo >= 40:
        dists_.append({"id": "commercial", "name": "Commercial Hub", "why": f"{g('bank')} banks and {g('office')} company/IT offices mapped ({bo_lq:.1f}× national urban rate)"})
    ind_km2 = float(cind.get(cid, 0))
    ind_lq = (ind_km2 / popc) / nat_ind_rate if nat_ind_rate else 0
    if (ind_lq >= 1.3 and ind_km2 >= 2) or g("works") >= 25:
        dists_.append({"id": "industrial", "name": "Industrial Zone", "why": f"{ind_km2:.1f} km² industrial land and {g('works')} factories/works mapped ({ind_lq:.1f}× national urban rate)"})
    on_coast = bool(H.loc[hix_c, "coastal"].any()) if hix_c else False
    if near("port", 0) >= 3 or (on_coast and near("port", 0) >= 1):
        dists_.append({"id": "harbor", "name": "Harbour", "why": f"{int(near('port', 0))} port/harbour facilities mapped in the city's hexes"})
    lat0, lon0 = c.lat, c.lon
    dd_ = np.hypot(ap_pts.latitude_deg - lat0, (ap_pts.longitude_deg - lon0) * math.cos(math.radians(lat0))) * 111
    close = ap_pts[(dd_ < 30) & ap_pts.type.isin(["large_airport", "medium_airport"])]
    if len(close):
        a0 = close.sort_values("type").iloc[0]
        dists_.append({"id": "aerodrome", "name": "Aerodrome", "why": f"{a0['name']}" + (f" ({a0.iata_code})" if isinstance(a0.iata_code, str) else "") + " has scheduled service (OurAirports)"})
    mil = near("military_km2", 0)
    if mil >= 3:
        dists_.append({"id": "encampment", "name": "Encampment", "why": f"{mil:.0f} km² of military land mapped (cantonments, bases)"})
    w_lq = lq("worship")
    if w_lq >= 1.6 and g("worship") >= 60:
        dists_.append({"id": "holy", "name": "Holy Site", "why": f"{g('worship')} places of worship mapped ({w_lq:.1f}× national urban rate)"})
    cult = g("heritage") * 2 + g("museum") * 3 + g("arts")
    cult_lq = (cult / popc) / ((tot.get("heritage", 0) * 2 + tot.get("museum", 0) * 3 + tot.get("arts", 0)) / nat_pop)
    if cult_lq >= 1.4 and cult >= 20:
        dists_.append({"id": "theater", "name": "Theatre Square", "why": f"{g('heritage')} monuments, {g('museum')} museums, {g('arts')} theatres/arts venues ({cult_lq:.1f}× national urban rate)"})
    if g("stadium") >= 3 and lq("stadium") >= 1.2:
        dists_.append({"id": "entertainment", "name": "Entertainment Complex", "why": f"{g('stadium')} stadiums mapped"})
    if any(n in STATE_CAPITALS for n in [name] + names[:3]):
        dists_.append({"id": "gov", "name": "Government Plaza", "why": "Seat of a state, union territory or national government"})
    pmw_c = near("power_mw", 0)
    if pmw_c >= 1000:
        dists_.append({"id": "power", "name": "Power Plant", "why": f"{pmw_c:,.0f} MW of mapped generating capacity in the city's hexes"})
    if g("data_center") >= 3:
        dists_.append({"id": "datacenter", "name": "Data Centres", "why": f"{g('data_center')} data centres mapped"})
    # epithets from what the city's industrial/office names say it makes
    ep = []
    kc = kw_counts.get(cid, Counter())
    for k, n_ in kc.most_common():
        share = n_ / max(1, sum(kc.values()))
        lqk = (n_ / popc) / (kw_tot[k] / nat_pop) if kw_tot[k] else 0
        if (n_ >= 4 and lqk >= 1.8) or (n_ >= 3 and lqk >= 4):
            ep.append({"id": k, "title": KEYWORDS[k][1], "why": f"{n_} mapped factories/offices named for it ({lqk:.1f}× national urban rate)"})
    # citizens: PLFS 2025 urban workforce mix of the state applied to the city's 2025 population
    st = c.state
    wpr_u = se.wpr_urban.get(st, np.nan) if "wpr_urban" in se else np.nan
    mix = {}
    if st in se.index and not pd.isna(wpr_u):
        workers = popc * wpr_u / 100
        for s_ in "ABCDEFGHIJKLMNOPQRST":
            v = se.loc[st].get("plfsu_" + s_)
            if not pd.isna(v):
                mix[s_] = round(workers * v / 100)
    city_out.append({
        "id": int(cid), "name": name, "belt": bool(belt), "aka": names[:8], "state": st, "d": None if pd.isna(c.dix) else int(c.dix),
        "lon": round(c.lon, 4), "lat": round(c.lat, 4), "xy": xy_km(c.lon, c.lat), "hexes": [[int(i), float(a)] for i, a in hexes_c],
        "pop": round(popc), "pop2000": None if pd.isna(c.GH_POP_TOT_2000) else round(c.GH_POP_TOT_2000) if "GH_POP_TOT_2000" in c else None,
        "area": c.GC_UCA_KM2_2025, "hdi": None if pd.isna(c.SC_SEC_HDI_2020) else round(c.SC_SEC_HDI_2020, 3),
        "life_exp": None if pd.isna(c.SC_SEC_LET_2020) else round(c.SC_SEC_LET_2020, 1),
        "school_yrs": None if pd.isna(c.SC_SEC_SYT_2020) else round(c.SC_SEC_SYT_2020, 1),
        "gdp_ppp_2020": None if pd.isna(c.SC_GDP_SUM_2020) else float(c.SC_GDP_SUM_2020),
        "gdp_cr": round(sum(H.gdp_cr.iat[i] * min(1, a / HEX_AREA_KM2) for i, a in hexes_c)),
        "built_km2": None if pd.isna(c.GH_BUS_TOT_2025) else round(c.GH_BUS_TOT_2025 / 1e6, 1) if "GH_BUS_TOT_2025" in c else None,
        "bldg_h": None if pd.isna(c.GH_BUH_AVG_2020) else round(c.GH_BUH_AVG_2020, 1),
        "green": None if pd.isna(c.GR_AVG_GRN_2025) else round(c.GR_AVG_GRN_2025, 2),
        "co2_t": None if pd.isna(c.EM_CO2_TOT_2022) else float(c.EM_CO2_TOT_2022),
        "pm25_t": None if pd.isna(c.EM_PM2_TOT_2022) else float(c.EM_PM2_TOT_2022),
        "temp": None if pd.isna(c.CL_B01_CUR_2010) else round(c.CL_B01_CUR_2010, 1),
        "rain": None if pd.isna(c.CL_B12_CUR_2010) else round(c.CL_B12_CUR_2010),
        "elev": None if pd.isna(c.GE_ELV_AVG_2025) else round(c.GE_ELV_AVG_2025),
        "basin": c.GE_MRB_MAI_2025, "climate": c.CL_KOP_CUR_2025,
        "haz": {k: (None if pd.isna(c[f"HZ_CEV_{k}_2015"]) else int(c[f"HZ_CEV_{k}_2015"])) for k in ["FLO", "TCY", "EAR", "HEW", "DRO", "LAN", "TEV"] if f"HZ_CEV_{k}_2015" in c},
        "flood100_share": None if "EX_100_SHP_2025" not in c or pd.isna(c.EX_100_SHP_2025) else round(float(c.EX_100_SHP_2025), 3),
        "low_coast_share": None if "EX_L05_SHP_2030" not in c or pd.isna(c.EX_L05_SHP_2030) else round(float(c.EX_L05_SHP_2030), 3),
        "counts": {k: g(k) for k in ["university", "college", "research", "school", "hospital", "clinic", "worship", "heritage",
                                     "museum", "arts", "bank", "office", "works", "stadium", "rail_station", "metro_station",
                                     "data_center", "attraction"]},
        "industrial_km2": round(ind_km2, 2), "districts": dists_, "epithets": ep[:2], "nirf": nirf,
        "workforce": mix, "wpr_urban": None if pd.isna(wpr_u) else wpr_u,
        "capital": any(n in STATE_CAPITALS for n in [name] + names[:3]),
    })
print("cities written:", len(city_out), "with City View detail:", sum(1 for c in city_out if c["pop"] >= 300000))

# ======================================================================= wonders placement & boosts
def place(w):
    k = int(lonlat_to_hexkey(np.array([w["lon"]]), np.array([w["lat"]]))[0])
    w["hex"] = idx_of.get(k)
    w["xy"] = xy_km(w["lon"], w["lat"])
    return w


heritage_w = [place(w) for w in W["heritage"]]
parks_w = [place(w) for w in W["parks"]]
# natural wonders: World Heritage natural sites + the largest parks/tiger reserves + highest peaks
peaks = poi[(C == "peak")].copy()
peaks["elev_m"] = pd.to_numeric(peaks.ele.astype(str).str.extract(r"([\d.]+)")[0], errors="coerce")
peaks = peaks[peaks.elev_m < 8900].sort_values("elev_m", ascending=False)
peaks = peaks[peaks.hix.map(lambda i: H.kind.iat[i] in ("india", "claimed"))].drop_duplicates("name").head(8)
peak_w = [place({"type": "peak", "name": p["name"] if isinstance(p["name"], str) else (p.get("name:en") or "Peak"), "lon": round(p.lon, 4),
                 "lat": round(p.lat, 4), "elev_m": int(p.elev_m), "source": "OpenStreetMap peaks (ele tag)"}) for _, p in peaks.iterrows()]
for w in heritage_w:
    if w["hex"] is not None:
        H.loc[w["hex"], "y_cult"] = min(8, H.y_cult.iat[w["hex"]] + 2)
for n in W["nirf"]:
    pass
hex_out["yc"] = H.y_cult.tolist()

# ======================================================================= edges, rivers
def adjacent(a, b):
    qa, ra = a // 100000 - 50000, a % 100000 - 50000
    qb, rb = b // 100000 - 50000, b % 100000 - 50000
    return (qb - qa, rb - ra) in NEIGHBOURS


E = edges[edges.apply(lambda e: adjacent(int(e.a), int(e.b)) and int(e.a) in idx_of and int(e.b) in idx_of, axis=1)].copy()
E["ia"] = E.a.map(idx_of)
E["ib"] = E.b.map(idx_of)
road_rank = {"motorway": 3, "trunk": 2, "primary": 1}
rd = E[E.kind == "road"].copy()
rd["lvl"] = rd["sub"].map(road_rank)
rd = rd.groupby(["ia", "ib"]).lvl.max().reset_index()
rl = E[E.kind == "rail"].groupby(["ia", "ib"]).n.sum().reset_index()
edges_out = {"road": rd[["ia", "ib", "lvl"]].astype(int).values.tolist(), "rail": rl[["ia", "ib"]].astype(int).values.tolist()}

riv_out = []
for rv in rivers[:220]:
    ls = []
    for line in rv["lines"]:
        if len(line) < 2:
            continue
        xs_, ys_ = T.transform([p[0] for p in line], [p[1] for p in line])
        ls.append([[round(x / 1000, 1), round(y / 1000, 1)] for x, y in zip(xs_, ys_)])
    riv_out.append({"name": rv["name"], "km": rv["km"], "lines": ls})

# ======================================================================= national summary + meta
nat = {
    "pop": int(H.loc[india, "pop"].sum()), "gdp_cr": float(H.loc[india, "gdp_cr"].sum()),
    "gsdp_states_reported": int(len(gsdp)), "hexes": int(india.sum()), "districts": int((~dist.claimed).sum()),
    "cities": len(city_out), "univ": int(H.univ.sum()), "college": int(H.college.sum()),
    "hospital": int(H.hospital.sum()), "worship": int(H.worship.sum()), "power_mw": float(pp.mw.sum()),
    "power_src": json.loads(pp.groupby("src").mw.sum().round(0).to_json()),
    "power_src_n": json.loads(pp.groupby("src").size().to_json()),
    "rail_km": float(H.rail_km.sum()), "road_km": float(H.road_km.sum()),
    "yield_quantiles": yield_q,
    "worship_rel": json.loads(rel.religion.value_counts().to_json()),
    "plfs": json.loads(se.loc[[i for i in se.index if i.lower().startswith("all")]].to_json(orient="records")) if any(i.lower().startswith("all") for i in se.index) else None,
}
meta = {
    "built": pd.Timestamp.now().strftime("%Y-%m-%d"),
    "terrain": TERR, "features": FEAT,
    "sources": [
        {"name": "GHS-POP 2025 population grid (JRC GHSL R2023A, 30 arc-sec)", "use": "Population of every hex and district", "url": "https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php"},
        {"name": "NFHS-6 (2023-24) district fact sheets, MoHFW / IIPS", "use": "34 district indicators: schooling, internet, nutrition, insurance, marriage age…", "url": "https://rchiips.org/nfhs/"},
        {"name": "MoSPI GSDP 2024-25 (current prices)", "use": "State GDP, i.e. the Gold yield", "url": "https://mospi.gov.in"},
        {"name": "GHSL non-residential built-up surface 2025", "use": "Half of the weight that spreads each state's GDP across its land", "url": "https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php"},
        {"name": "PLFS Annual Report 2025 (Jan–Dec 2025), NSO", "use": "Workforce by industry and worker-population ratios per state (citizens)", "url": "https://mospi.gov.in"},
        {"name": "GHSL Urban Centre Database R2024A (epoch 2025)", "use": f"{len(city_out)} cities: population, HDI, emissions, hazards, climate", "url": "https://human-settlement.emergency.copernicus.eu"},
        {"name": "GHSL built-up surface 2025", "use": "Urbanisation lens", "url": "https://human-settlement.emergency.copernicus.eu"},
        {"name": "ESA WorldCover 2021 v200 (10 m)", "use": "Forests, cropland, desert, snow, wetlands, mangroves → terrain and Food", "url": "https://esa-worldcover.org"},
        {"name": "AWS Terrain Tiles (SRTM / GMTED / ETOPO)", "use": "Elevation → hills and mountains", "url": "https://registry.opendata.aws/terrain-tiles/"},
        {"name": "WorldClim 2.1 climate normals", "use": "Rainfall and temperature → grassland vs plains, rainforest", "url": "https://worldclim.org"},
        {"name": "OpenStreetMap India extract (Geofabrik, Nov 2026)", "use": "Power plants, mines, ports, bases, universities, hospitals, worship, rail, roads, rivers, plantations", "url": "https://download.geofabrik.de/asia/india.html"},
        {"name": "OurAirports", "use": "Airports with scheduled service", "url": "https://ourairports.com/data/"},
        {"name": "IBTrACS v04r01 (NOAA NCEI)", "use": "Cyclone tracks since 1990", "url": "https://www.ncei.noaa.gov/products/international-best-track-archive"},
        {"name": "USGS ComCat earthquake catalogue", "use": "Earthquakes M4.5+ since 1990", "url": "https://earthquake.usgs.gov"},
        {"name": "UNESCO World Heritage List (via Wikidata)", "use": "44 World Heritage Wonders", "url": "https://whc.unesco.org/en/statesparties/in"},
        {"name": "Wikidata national parks & tiger reserves", "use": "Natural wonders", "url": "https://www.wikidata.org"},
        {"name": "NIRF 2025 (Ministry of Education)", "use": "Top-ranked institutions → Campus districts and Great Institutions", "url": "https://www.nirfindia.org/2025/Ranking.html"},
        {"name": "India Tourism Data Compendium 2025 (via press coverage)", "use": "ASI monument footfall 2024 → Wonder ranking", "url": "https://tourism.gov.in"},
        {"name": "geoBoundaries IND ADM1/ADM2 (LGD, 2021)", "use": "District and state boundaries (India's official outline)", "url": "https://www.geoboundaries.org"},
        {"name": "Natural Earth 10m land", "use": "Sea vs neighbouring land", "url": "https://www.naturalearthdata.com"},
    ],
    "caveats": [
        "India's Census 2027 has not published results yet (population count: Feb 2027), so nothing here uses Census 2011. Population is the JRC's GHS-POP 2025 model (WorldPop's 2025 grid was tried, but it badly undercounts dense cores such as Mumbai).",
        "NFHS-6 did not survey Manipur, and its 2021-vintage district frame misses a few newer districts; those show their state's value (marked) or no data.",
        "District and hex GDP are modelled: official 2024-25 GSDP per state, spread within the state half by population and half by non-residential built-up area (GHSL 2025). It captures where offices, factories and shops are, but not, say, hydropower or mining output. MoSPI does not publish GSDP for Dadra & Nagar Haveli and Daman & Diu, Lakshadweep or Ladakh; those use the same rule at national level.",
        "OpenStreetMap counts (hospitals, places of worship, mines…) reflect what volunteers have mapped and are uneven across regions.",
        "City workforces apply the state's PLFS 2025 urban industry mix to the city's 2025 population; PLFS is not published for individual cities.",
        "Gilgit-Baltistan is drawn inside India's official boundary but is Pakistan-administered; no statistics are shown for it.",
    ],
}

dump(hex_out, "hexes.json")
dump(dists_out, "districts.json")
dump(states_out, "states.json")
dump(city_out, "cities.json")
dump({"heritage": heritage_w, "parks": parks_w, "peaks": peak_w, "nirf": W["nirf"], "storms": W["storms"],
      "storm_count": W.get("storm_count"), "quake_count": W.get("quake_count"), "quake_count_india": W.get("quake_count_india"),
      "big_quakes": [dict(q, xy=xy_km(q["lon"], q["lat"])) for q in W["big_quakes"]]}, "wonders.json")
dump(edges_out, "edges.json")
dump(riv_out, "rivers.json")
dump({"national": nat, "meta": meta}, "meta.json")
