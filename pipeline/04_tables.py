"""Statistical tables: NFHS-6 districts, MoSPI GSDP 2024-25, PLFS 2025 workforce by industry.

Outputs: work/nfhs6_district.parquet (dix x indicator), work/nfhs6_state.parquet,
         work/state_econ.parquet (GSDP + PLFS industry shares per state)
"""
import difflib
import io
import os
import re

import pandas as pd
import pdfplumber

import geopandas as gpd

from common import RAW, WORK
from names import CLAIMED, DISPLAY, NFHS_ALIAS, STATE_FIX

# --- fix enclave state assignment, add current display names, flag claimed territory ---
dgeo = gpd.read_parquet(os.path.join(WORK, "districts.parquet"))
dgeo["state"] = [STATE_FIX.get(d, s) for d, s in zip(dgeo.district, dgeo.state)]
dgeo["name"] = [DISPLAY.get((s, d), d) for d, s in zip(dgeo.district, dgeo.state)]
dgeo["claimed"] = [(s, d) in CLAIMED for d, s in zip(dgeo.district, dgeo.state)]
dgeo.to_parquet(os.path.join(WORK, "districts.parquet"))
dist = dgeo[["dix", "district", "state"]].copy()

STATE_ALIASES = {
    "andaman & nicobar islands": "Andaman & Nicobar", "andaman and nicobar islands": "Andaman & Nicobar",
    "andaman & n. island": "Andaman & Nicobar", "a & n islands": "Andaman & Nicobar",
    "nct delhi": "Delhi", "nct of delhi": "Delhi", "delhi": "Delhi",
    "dadra & nagar haveli and daman & diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra & nagar haveli & daman & diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dnh & dd": "Dadra and Nagar Haveli and Daman and Diu",
    "jammu and kashmir": "Jammu & Kashmir", "jammu & kashmir": "Jammu & Kashmir",
    "orissa": "Odisha", "pondicherry": "Puducherry",
}
STATES = sorted(dist.state.unique())


def canon_state(s):
    if not isinstance(s, str):
        return None
    k = re.sub(r"\s+", " ", s.strip().lower().replace("*", "")).strip()
    if k in STATE_ALIASES:
        return STATE_ALIASES[k]
    for st in STATES:
        if st.lower() == k:
            return st
    m = difflib.get_close_matches(s.strip(), STATES, n=1, cutoff=0.85)
    return m[0] if m else None


def norm(s):
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)
    for a, b in [("&", "and"), ("north", "n"), ("south", "s"), ("east", "e"), ("west", "w"),
                 ("district", ""), ("rural", ""), ("urban", ""), ("sri ", ""), ("shri ", "")]:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z]", "", s)
    for a, b in [("oo", "u"), ("ee", "i"), ("aa", "a"), ("w", "v"), ("th", "t"), ("dh", "d"),
                 ("bh", "b"), ("kh", "k"), ("gh", "g"), ("ph", "p"), ("sh", "s"), ("y", "i")]:
        s = s.replace(a, b)
    return s


# ---------------- NFHS-6 ----------------
nf = pd.read_csv(os.path.join(RAW, "nfhs_all.csv"))
nf["Indicator"] = nf.Indicator.str.replace("â‰¥", "≥", regex=False).str.replace("â‰¤", "≤", regex=False)
nf6 = nf[nf.Round == "NFHS-6"].copy()
nf6["Value"] = pd.to_numeric(nf6.Value.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")

st = nf6[nf6["Geo Level"] == "State"].copy()
st["state"] = st.Geography.map(canon_state)
st_w = st.pivot_table(index="state", columns="Indicator", values="Value", aggfunc="first")
st_w.to_parquet(os.path.join(WORK, "nfhs6_state.parquet"))

dd = nf6[nf6["Geo Level"] == "District"].copy()
dd["state"] = dd["Parent State"].map(canon_state)
dd = dd[dd.state.notna()]
names = dd[["state", "Geography"]].drop_duplicates()

match = {}
unmatched = []
for s, grp in names.groupby("state"):
    targets = dist[dist.state == s]
    tnorm = {norm(n): ix for n, ix in zip(targets.district, targets.dix)}
    used = set()
    byname = dict(zip(targets.district, targets.dix))
    for g in grp.Geography:
        if (s, g) in NFHS_ALIAS and NFHS_ALIAS[(s, g)] in byname:
            match[(s, g)] = byname[NFHS_ALIAS[(s, g)]]
            continue
        k = norm(g)
        if k in tnorm:
            match[(s, g)] = tnorm[k]
            continue
        cand = difflib.get_close_matches(k, list(tnorm), n=1, cutoff=0.78)
        if cand:
            match[(s, g)] = tnorm[cand[0]]
        else:
            unmatched.append((s, g))
print("NFHS-6 district names:", len(names), "matched:", len(match), "unmatched:", len(unmatched))
print(unmatched[:60])

dd["dix"] = [match.get((s, g)) for s, g in zip(dd.state, dd.Geography)]
dd = dd[dd.dix.notna()]
dd["dix"] = dd.dix.astype(int)
dw = dd.pivot_table(index="dix", columns="Indicator", values="Value", aggfunc="mean")
# districts NFHS-6 does not report separately (new districts carved after the frame, small UTs):
# fall back to their state's NFHS-6 value, flagged.
dw = dw.reindex(dist.dix)
flag = dw.isna().all(axis=1)
for ix in dw.index[flag]:
    s = dist.state.iat[ix]
    if s in st_w.index:
        dw.loc[ix] = st_w.loc[s].reindex(dw.columns).values
dw["nfhs_source"] = ["state" if f else "district" for f in flag]
dw.loc[dw.drop(columns="nfhs_source").isna().all(axis=1), "nfhs_source"] = "none"
print(dw.nfhs_source.value_counts().to_dict())
dw.to_parquet(os.path.join(WORK, "nfhs6_district.parquet"))

# ---------------- GSDP 2024-25 (MoSPI via statisticstimes, Oct 2026) ----------------
h = open(os.path.join(RAW, "st_gdp.html"), errors="ignore").read()
t = pd.read_html(io.StringIO(h))[1]
t.columns = ["rank", "state", "gsdp_2526", "gsdp_2425", "share", "usd_bn_2024", "real_2526", "real_2425"]
t["state_c"] = t.state.map(canon_state)
t["gsdp_cr_2425"] = pd.to_numeric(t.gsdp_2425, errors="coerce")
t["gsdp_cr_2526"] = pd.to_numeric(t.gsdp_2526, errors="coerce")
gsdp = t[t.state_c.notna()][["state_c", "gsdp_cr_2425", "gsdp_cr_2526"]].rename(columns={"state_c": "state"})
print("GSDP states:", len(gsdp), "missing:", sorted(set(STATES) - set(gsdp.state)))

# ---------------- PLFS 2025 Table 27 (persons, rural+urban / rural / urban) ----------------
SECTIONS = list("ABCDEFGHIJKLMNOPQRST")
pdf = pdfplumber.open(os.path.join(RAW, "plfs2025.pdf"))


def parse_t27(page_ix):
    rows = {}
    for pi in (page_ix, page_ix + 1):
        txt = pdf.pages[pi].extract_text() or ""
        if pi != page_ix and "Table (27)" in txt:
            break
        for line in txt.splitlines():
            m = re.match(r"^([A-Za-z&.\- ]+?)\s+((?:-?\d+\.\d+\s+){20}\d+\.\d+)\s*$", line.strip())
            if m:
                vals = [float(v) for v in m.group(2).split()]
                rows[m.group(1).strip()] = vals[:20]
    return rows


def find_t27(label):
    for i, pg in enumerate(pdf.pages[240:270]):
        txt = pg.extract_text() or ""
        if "Table (27)" in txt and txt.split("\n")[2].strip() == label:
            return 240 + i
    raise RuntimeError(label)


plfs = {}
for lab in ["rural+urban persons", "rural persons", "urban persons"]:
    rows = parse_t27(find_t27(lab))
    plfs[lab] = rows
    print("PLFS", lab, len(rows))
pl = pd.DataFrame(plfs["rural+urban persons"], index=SECTIONS).T
pl.index = [canon_state(s) or s for s in pl.index]
pl = pl.add_prefix("plfs_")
print("PLFS unmatched rows:", [s for s in pl.index if s not in STATES])

# Table 17.0: WPR (all ages, ps+ss) per state: rural m f p, urban m f p, total m f p
wpr = {}
for line in (pdf.pages[149].extract_text() or "").splitlines():
    m = re.match(r"^([A-Za-z&.\- ]+?)\s+((?:\d+\.\d+\s+){8}\d+\.\d+)\s*$", line.strip())
    if m:
        v = [float(x) for x in m.group(2).split()]
        wpr[canon_state(m.group(1).strip()) or m.group(1).strip()] = {
            "wpr_rural": v[2], "wpr_urban": v[5], "wpr_total": v[8], "wpr_female": v[7]}
wpr = pd.DataFrame(wpr).T
print("WPR rows:", len(wpr))
plu = pd.DataFrame(plfs["urban persons"], index=SECTIONS).T
plu.index = [canon_state(s) or s for s in plu.index]
plu = plu.add_prefix("plfsu_")

se = gsdp.set_index("state").join(pl, how="outer").join(plu, how="outer").join(wpr, how="outer")
se = se[se.index.isin(STATES) | (se.index == "all-India")]
se.to_parquet(os.path.join(WORK, "state_econ.parquet"))
print(se[["gsdp_cr_2425", "plfs_A", "plfs_C", "plfs_J"]].to_string())
