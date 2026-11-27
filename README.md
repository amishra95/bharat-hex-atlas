# Bharat Hex Atlas

India as a strategy-game map, built from real public data and reconciled onto one
25 km hex grid (541 km² per tile, equal-area Albers projection).

No Census 2011 anywhere: India's Census 2027 has not published results yet, so every layer
uses the newest source available (GHS-POP 2025, NFHS-6 2023-24, GSDP 2024-25, PLFS 2025,
OpenStreetMap Nov 2026, GHSL 2025, …).

## Run it

```bash
python3 -m http.server 8765 -d web   # then open http://localhost:8765
```

## Rebuild the data

```bash
python3 -m venv .venv && .venv/bin/pip install numpy pandas geopandas shapely pyproj rasterio \
    requests openpyxl pdfplumber pyarrow osmium lxml html5lib beautifulsoup4 pillow
./build.sh            # runs pipeline/01..07, writes web/data/*.json
```

`raw/` holds downloaded sources (≈2.5 GB; the OSM extract is most of it). See the
"How it's made" panel in the app or `pipeline/07_build.py` for the full source list.

| Step | Script | What it does |
|---|---|---|
| 1 | `01_grid.py` | Hex grid, district/state assignment, sea vs neighbouring land |
| 2 | `02_rasters.py` | GHS-POP 2025, GHSL built-up (total + non-residential), WorldClim, elevation, ESA WorldCover |
| 3 | `03_osm.py` | OSM India: plants, mines, ports, bases, campuses, hospitals, worship, rail/roads/rivers |
| 4 | `04_tables.py` | NFHS-6 districts, MoSPI GSDP 2024-25, PLFS 2025 tables |
| 5 | `05_cities.py` | GHSL Urban Centre Database 2025 → 1,925 cities |
| 6 | `06_hazards_wonders.py` | IBTrACS cyclones, USGS quakes, UNESCO / parks / NIRF wonders |
| 7 | `07_build.py` | Yields, terrain, city districts, citizens → `web/data/*.json` |
