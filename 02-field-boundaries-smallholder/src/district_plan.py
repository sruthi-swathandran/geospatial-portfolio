"""
RS-02 stage 3. Size the district run before spending the compute.

Two districts have to be tiled into chips, run through the checkpoint twice
for the two seasonal windows, and scored. On a CPU-only machine that is worth
estimating rather than discovering. The per-chip timing comes from the stage 2
manifests, so the estimate uses this machine's measured speed rather than a
guess.

It also checks that Rewa and Sidhi share a border, because the argument for
running these two rests on them sitting under the same conditions.

    python src\\district_plan.py
    python src\\district_plan.py --districts Rewa,Sidhi,Jodhpur
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
CHIP_PX = 256
NATIVE_M = 10.0
CHIP_KM2 = (CHIP_PX * NATIVE_M / 1000.0) ** 2


def geodesic_km2(geom) -> float:
    from pyproj import Geod
    area, _ = Geod(ellps="WGS84").geometry_area_perimeter(geom)
    return abs(area) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--districts", default="Rewa,Sidhi")
    ap.add_argument("--country", default="india")
    ap.add_argument("--iso", default="IND")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import geopandas as gpd
    path = F.PROJECT / "data" / "boundaries" / f"{args.iso}_ADM2.geojson"
    if not path.exists():
        sys.exit(f"{path} not found. Run pick_district.py first.")
    adm2 = gpd.read_file(path)

    wanted = [d.strip() for d in args.districts.split(",") if d.strip()]
    sel = adm2[adm2["shapeName"].isin(wanted)].copy()
    found = set(sel["shapeName"])
    for w in wanted:
        if w not in found:
            near = [n for n in adm2["shapeName"] if w.lower() in str(n).lower()]
            print(f"  '{w}' not found. Close names: {near[:8]}")
    if sel.empty:
        sys.exit("none of the named districts matched")

    print(RULE)
    print("DISTRICT SIZE AND COMPUTE")
    print(RULE)

    rows = []
    for _, r in sel.iterrows():
        area = geodesic_km2(r.geometry)
        minx, miny, maxx, maxy = r.geometry.bounds
        bbox_geom = gpd.GeoSeries.from_xy([minx, maxx], [miny, maxy]).total_bounds
        from shapely.geometry import box
        bbox_km2 = geodesic_km2(box(minx, miny, maxx, maxy))
        rows.append({
            "district": r["shapeName"],
            "area_km2": round(area, 1),
            "bbox_km2": round(bbox_km2, 1),
            "chips_area": math.ceil(area / CHIP_KM2),
            "chips_bbox": math.ceil(bbox_km2 / CHIP_KM2),
        })
    tab = pd.DataFrame(rows).set_index("district")
    print(tab.to_string())
    print(f"\n  one chip is {CHIP_PX} px at {NATIVE_M:.0f} m, "
          f"{CHIP_KM2:.2f} km2 of ground")
    print("  chips_bbox is what a naive tiling costs. chips_area is what")
    print("  survives clipping to the district, which is the honest target.")

    man = F.RESULTS / "inference_manifest_3class_full.csv"
    if man.exists():
        m = pd.read_csv(man)
        per = float(m["seconds"].median())
        print(f"\n  measured on this machine: {per:.3f} s per chip "
              f"over {len(m):,} stage 2 chips")
        for name, r in tab.iterrows():
            lo = r["chips_area"] * per / 60.0
            hi = r["chips_bbox"] * per / 60.0
            print(f"    {name:<12} {lo:6.1f} to {hi:6.1f} min of inference")
        total_lo = tab["chips_area"].sum() * per / 60.0
        total_hi = tab["chips_bbox"].sum() * per / 60.0
        print(f"    {'together':<12} {total_lo:6.1f} to {total_hi:6.1f} min")
        print("\n  Downloading and mosaicking the imagery is on top of this")
        print("  and is usually the larger share.")
    else:
        print(f"\n  {man.name} not found, so no timing estimate")

    if len(sel) >= 2:
        print("\n" + RULE)
        print("ADJACENCY")
        print(RULE)
        geoms = list(sel.geometry)
        names = list(sel["shapeName"])
        from pyproj import Geod
        g = Geod(ellps="WGS84")
        for i in range(len(geoms)):
            for j in range(i + 1, len(geoms)):
                touch = geoms[i].touches(geoms[j]) or geoms[i].intersects(geoms[j])
                p1, p2 = geoms[i].centroid, geoms[j].centroid
                _, _, d = g.inv(p1.x, p1.y, p2.x, p2.y)
                print(f"  {names[i]} and {names[j]}: "
                      f"{'share a border' if touch else 'do not touch'}, "
                      f"centroids {d / 1000:.0f} km apart")

    print("\n" + RULE)
    print("If the two districts share a border the controlled comparison")
    print("holds, because the growing season and the imagery are the same and")
    print("parcel size is what differs. If they do not, say so in the")
    print("write-up rather than leaning on the comparison.")
    print(RULE)


if __name__ == "__main__":
    main()