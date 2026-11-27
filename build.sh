#!/bin/sh
# Rebuild every derived dataset from raw/ into web/data/.
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python
for s in 01_grid 02_rasters 03_osm 04_tables 05_cities 06_hazards_wonders 07_build; do
  echo "== $s"
  PYTHONUNBUFFERED=1 $PY pipeline/$s.py
done
