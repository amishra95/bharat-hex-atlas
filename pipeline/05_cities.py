"""Cities from the GHSL Urban Centre Database R2024A (epoch 2025).

Every Indian urban centre with its 2025 population, built-up, HDI, GDP, hospitals, hazards,
air pollution, emissions, greenness and climate. Output: work/cities.parquet
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from common import CRS, RAW, WORK, lonlat_to_hexkey

F = os.path.join(RAW, "ucdb", "GHS_UCDB_GLOBE_R2024A.gpkg")
WANT = {
    "GENERAL_CHARACTERISTICS": ["GC_UCN_MAI_2025", "GC_UCN_LIS_2025", "GC_CNT_GAD_2025", "GC_UCA_KM2_2025",
                                "GC_POP_TOT_2025", "GC_UCM_CAP"],
    "SOCIOECONOMIC": ["SC_GDP_SUM_2020", "SC_GDP_AVG_2020", "SC_SEC_HDI_2020", "SC_SEC_LET_2020", "SC_SEC_SYT_2020"],
    "HEALTH": ["HL_FCL_HOS_2024", "HL_SHP_HOS_2025"],
    "HAZARD_RISK": ["HZ_CEV_TEV_2015", "HZ_CEV_FLO_2015", "HZ_CEV_TCY_2015", "HZ_CEV_EAR_2015", "HZ_CEV_HEW_2015",
                    "HZ_CEV_DRO_2015", "HZ_CEV_LAN_2015", "HZ_CON_TOT_2020"],
    "NATURAL_SYSTEMS": ["NS_ESB_P25_2025"],
    "GREENNESS": ["GR_AVG_GRN_2025"],
    "EMISSIONS": ["EM_CO2_TOT_2022", "EM_PM2_TOT_2022"],
    "CLIMATE": ["CL_B01_CUR_2010", "CL_B12_CUR_2010", "CL_KOP_CUR_2025"],
    "GEOGRAPHY": ["GE_ELV_AVG_2025", "GE_MRB_MAI_2025"],
    "GHSL": ["GH_BUH_AVG_2020", "GH_BUS_TOT_2025", "GH_POP_TOT_2000"] ,
    "EXPOSURE": ["EX_100_SHP_2025", "EX_L05_SHP_2030"],
}


def clean(df):
    df.columns = [c.replace("﻿", "") for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.replace("﻿", "", regex=False).str.strip()
    return df


base = None
for theme, cols in WANT.items():
    layer = f"GHS_UCDB_THEME_{theme}_GLOBE_R2024A"
    info = pyogrio.read_info(F, layer=layer)
    have = {c.replace("﻿", ""): c for c in info["fields"]}
    real = [have[c] for c in cols if c in have] + [have["ID_UC_G0"]]
    missing = [c for c in cols if c not in have]
    if missing:
        print(theme, "missing", missing)
    df = clean(pyogrio.read_dataframe(F, layer=layer, columns=real, read_geometry=(theme == "GENERAL_CHARACTERISTICS")))
    if theme == "GENERAL_CHARACTERISTICS":
        df = df[df.GC_CNT_GAD_2025 == "India"]
        base = df
    else:
        base = base.merge(df.drop(columns=[c for c in df.columns if c in base.columns and c != "ID_UC_G0"]),
                          on="ID_UC_G0", how="left")

cent = clean(pyogrio.read_dataframe(F, layer="UC_centroids", read_geometry=False))
base = base.merge(cent, on="ID_UC_G0", how="left")
base = gpd.GeoDataFrame(base, geometry="geometry", crs=pyogrio.read_info(F, layer="GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A")["crs"])
for c in base.columns:
    if c not in ("geometry", "GC_UCN_MAI_2025", "GC_UCN_LIS_2025", "GC_CNT_GAD_2025", "CL_KOP_CUR_2025", "GE_MRB_MAI_2025"):
        base[c] = pd.to_numeric(base[c], errors="coerce")
# centroid columns are Mollweide metres despite their names
from pyproj import Transformer
_t = Transformer.from_crs(pyogrio.read_info(F, layer="UC_centroids")["crs"], 4326, always_xy=True)
lo, la = _t.transform(base.GC_UCC_LON_2025.values, base.GC_UCC_LAT_2025.values)
base["lon"], base["lat"] = np.round(lo, 4), np.round(la, 4)
base = base.drop(columns=["GC_UCC_LON_2025", "GC_UCC_LAT_2025", "NS_ESB_P25_2025"])
base["key"] = lonlat_to_hexkey(base.lon.values, base.lat.values)

# district + state via the urban centre's centroid
dist = gpd.read_parquet(os.path.join(WORK, "districts.parquet")).to_crs(4326)
pts = gpd.GeoDataFrame(base[["ID_UC_G0"]], geometry=gpd.points_from_xy(base.lon, base.lat), crs=4326)
j = gpd.sjoin(pts, dist[["dix", "state", "name", "geometry"]], how="left", predicate="within").drop_duplicates("ID_UC_G0")
base = base.merge(j[["ID_UC_G0", "dix", "state"]], on="ID_UC_G0", how="left")

# hexes covered by each urban centre polygon (for city territory / POI attribution)
poly = base[["ID_UC_G0", "geometry"]].to_crs(CRS)
hexes = pd.read_parquet(os.path.join(WORK, "hexes.parquet"))
from common import hexkey, hex_polygon
hg = gpd.GeoDataFrame({"key": hexkey(hexes.q.values, hexes.r.values)},
                      geometry=[hex_polygon(q, r) for q, r in zip(hexes.q, hexes.r)], crs=CRS)
ov = gpd.overlay(poly, hg, how="intersection", keep_geom_type=True)
ov["a"] = ov.area / 1e6
base = base.merge(ov.groupby("ID_UC_G0").apply(lambda d: list(zip(d.key.astype("int64"), d.a.round(2)))).rename("hexes"),
                  on="ID_UC_G0", how="left")

gpd.GeoDataFrame(base[["ID_UC_G0"]], geometry=base.geometry, crs=base.crs).to_crs(4326).to_parquet(
    os.path.join(WORK, "city_poly.parquet"))
base = base.drop(columns="geometry")
base = pd.DataFrame(base).sort_values("GC_POP_TOT_2025", ascending=False).reset_index(drop=True)
print(len(base), "Indian urban centres;", (base.GC_POP_TOT_2025 >= 1e6).sum(), "over 1M")
print(base[["GC_UCN_MAI_2025", "state", "GC_POP_TOT_2025", "SC_SEC_HDI_2020", "HL_FCL_HOS_2024", "lon", "lat"]].head(20).to_string())
base.to_parquet(os.path.join(WORK, "cities.parquet"))
