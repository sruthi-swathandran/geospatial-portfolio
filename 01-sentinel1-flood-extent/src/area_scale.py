"""
RS-01 / audit. How far the UTM grid's hectares are from hectares on the ground
(REVIEW F-09).

Every area in this project is a pixel count on the 20 m grid in UTM zone 46N
(EPSG:32646). UTM is conformal: it keeps shape and lets area drift with
distance from the central meridian, 93 degrees east. This reads the area scale
the projection gives at every mapped flood pixel of the 12 August map, on a
200 m subsample, and what it does to the headline. Nothing is corrected; the
figure says how much a correction would move.

Output
------
  results/area_scale.csv

Usage
-----
    python src\\area_scale.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Proj, Transformer
from rasterio.transform import xy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RESULTS, TARGET_CRS                                 # noqa: E402

FLOOD, NODATA = 1, 255
STEP = 10                         # read every tenth 20 m pixel, so 200 m


def scales(path, keep):
    with rasterio.open(path) as d:
        a = d.read(1, out_shape=(d.height // STEP, d.width // STEP))
        t = d.transform * d.transform.scale(STEP, STEP)
    rr, cc = np.nonzero(keep(a))
    xs, ys = xy(t, rr, cc)
    lon, lat = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True
                                    ).transform(np.asarray(xs), np.asarray(ys))
    return np.asarray(Proj(TARGET_CRS).get_factors(lon, lat).areal_scale)


def main():
    path = RESULTS / "fullscene" / "India_water_20m_refined.tif"
    flood = scales(path, lambda a: a == FLOOD)
    seen = scales(path, lambda a: a != NODATA)
    with open(RESULTS / "fullscene_stats_20m.json", encoding="utf-8") as fh:
        headline = float(json.load(fh)["refined"]["flood_ha_after"])
    rows = [dict(ground="mapped flood, 12 Aug", points=len(flood),
                 scale_min=round(float(flood.min()), 4),
                 scale_max=round(float(flood.max()), 4),
                 scale_mean=round(float(flood.mean()), 5),
                 pct_below_ground=round(100 * (1 - float(flood.mean())), 2),
                 headline_ha_on_ground=round(headline / float(flood.mean())),
                 headline_shortfall_ha=round(headline / float(flood.mean()) - headline)),
            dict(ground="imaged ground, 12 Aug", points=len(seen),
                 scale_min=round(float(seen.min()), 4),
                 scale_max=round(float(seen.max()), 4),
                 scale_mean=round(float(seen.mean()), 5),
                 pct_below_ground=round(100 * (1 - float(seen.mean())), 2),
                 headline_ha_on_ground="", headline_shortfall_ha="")]
    out = RESULTS / "area_scale.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"  {r['ground']:<22} area scale {r['scale_min']} to {r['scale_max']}, "
              f"mean {r['scale_mean']}, {r['pct_below_ground']}% below the ground")
    print(f"  the headline, {headline:,.0f} ha on the grid, is about "
          f"{rows[0]['headline_shortfall_ha']} ha more on the ground")
    print(f"  wrote {out}")


if __name__ == "__main__":
    main()
