"""
RS-01 / validation scoping, part two. How much of each part of the 12 August
map was under clear sky when Sentinel-2A passed that morning?

scene_inventory.py found that Sentinel-2A imaged the study area at 04:15 UTC on
12 August 2016, about 19.5 hours before the Sentinel-1 frames at 23:46 UTC. Its
cloud figures are per tile, which cannot say whether the clear patches fall on
the flood or on the hills. This script reads the per-pixel scene classification
layer (SCL) that comes with Planetary Computer's L2A product, puts it on the
published 20 m map grid, and counts clear sky in each stratum an accuracy
sample would need.

Strata, each pixel in exactly one, taken in this order
------------------------------------------------------
  flood                 flood in the published map, -18.75 dB, refined
  permanent water       permanent water in the published map
  upper threshold only  land at -18.75 dB but flood in the -17.75 dB map; the
                        band between the two ends of the published range
  removed by refinement flood in the raw map that the slope cut or the 1 ha
                        clean-up turned to land; nearly all of it is the slope cut
  swath edge            imaged, but set to no data by the swath-edge buffer
  land                  land in both maps

SCL classes, grouped
--------------------
  clear                 4 vegetation, 5 bare, 6 water
  dark or unclassified  2 dark area, 7 unclassified; often usable, check by eye
  cloud                 3 cloud shadow, 8 and 9 cloud
  cirrus                10 thin cirrus; water may still show through
  unseen                outside every tile, or SCL no data

SCL is an automatic classification. It misses some thin cloud and shadow, and
it can call a dark flooded field shadow. Treat the clear share as a guide to
how many points a sample can expect to label, not as a measured figure.

The last column, the share of clear pixels that SCL calls water, is NOT a
validation. SCL water is a crude spectral class that misses water under crops
and trees, and nothing here checks it. It is printed only to show whether the
optical image and the map broadly see the same thing in each stratum.

Writes
------
  data/validation/s2_20160812_scl_20m.tif      SCL on the map grid, 255
                                               unseen; under data/, which git
                                               ignores, since it is large and
                                               rebuilt by this script
  results/validation/clear_sky_by_stratum.csv

Usage
-----
    python src\\clear_sky.py
    python src\\clear_sky.py --reuse      # skip the download, reuse the SCL mosaic
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.errors import WindowError
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BBOX, DATA, RESULTS          # noqa: E402

MPC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_DATE = "2016-08-12"

FULL = RESULTS / "fullscene"
# The sample was drawn on the maps as they stood in October 2026, refined with
# a nearest-resampled DEM. The strata come from these two and must keep coming
# from them, whatever the published map becomes (C-31). The -18.75 dB one also
# dropped flood components of exactly 10 pixels, hence --min-pixels 11 below.
# Rebuild them with
#   python src\\refine_scene.py --res 20 --apply --resample-dem nearest --min-pixels 11
#   python src\\refine_scene.py --res 20 --apply --resample-dem nearest --variant areamatched
# score_map.py checks both against the hectares the draw recorded.
MAP = FULL / "India_water_20m_dem-nearest_refined.tif"      # as drawn, -18.75 dB
RAW = FULL / "India_water_20m.tif"                          # before refinement
UPPER = FULL / "India_water_20m_areamatched_dem-nearest_refined.tif"  # -17.75 dB

OUT = RESULTS / "validation"                 # small results, committed
WORK = DATA / "validation"                   # large or rebuilt, not committed
SCL_TIF = WORK / "s2_20160812_scl_20m.tif"

LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
UNSEEN = 255

STRATA = [
    (1, "flood"),
    (2, "permanent water"),
    (3, "upper threshold only"),
    (4, "removed by refinement"),
    (5, "swath edge"),
    (6, "land"),
]

GROUPS = {
    "clear": [4, 5, 6],
    "dark or unclassified": [2, 7],
    "cloud": [3, 8, 9],
    "cirrus": [10],
    "unseen": [0, 1, 11, UNSEEN],
}


def strata_of(r, w, a):
    """One stratum code per pixel, in the order the docstring lists them."""
    s = np.zeros(r.shape, "uint8")
    s[r == LAND] = 6
    s[(r == LAND) & (w == FLOOD)] = 4
    s[(r == LAND) & (a == FLOOD)] = 3
    s[(r == NODATA) & (w != NODATA)] = 5
    s[r == PERMANENT] = 2
    s[r == FLOOD] = 1
    return s


def build_scl_mosaic(ref, px_ha):
    """Fetch the SCL band of every 12 August tile and place it on the map grid."""
    client = Client.open(MPC, modifier=planetary_computer.sign_inplace)
    items = list(client.search(collections=["sentinel-2-l2a"], bbox=BBOX,
                               datetime=S2_DATE).items())
    seen, keep = set(), []
    for it in sorted(items, key=lambda i: i.id):
        tile = it.properties.get("s2:mgrs_tile") or it.id.split("_")[4]
        if tile not in seen:
            seen.add(tile)
            keep.append(it)
    print(f"  {len(keep)} Sentinel-2 L2A tile(s) on {S2_DATE}\n")

    mosaic = np.full((ref.height, ref.width), UNSEEN, "uint8")
    full = Window(0, 0, ref.width, ref.height)
    failed = []
    for k, it in enumerate(keep, 1):
        tile = it.properties.get("s2:mgrs_tile") or it.id
        try:
            with rasterio.open(it.assets["SCL"].href) as src:
                b = transform_bounds(src.crs, ref.crs, *src.bounds)
                win = from_bounds(*b, transform=ref.transform)
                try:
                    win = win.round_offsets().round_lengths().intersection(full)
                except WindowError:
                    print(f"  [{k:>2}/{len(keep)}] {tile}  outside the map grid, skipped")
                    continue
                h, w = int(win.height), int(win.width)
                dst = np.zeros((h, w), "uint8")
                reproject(source=rasterio.band(src, 1), destination=dst,
                          src_transform=src.transform, src_crs=src.crs,
                          src_nodata=0,
                          dst_transform=ref.window_transform(win),
                          dst_crs=ref.crs, dst_nodata=0,
                          resampling=Resampling.nearest)
        except Exception as exc:
            failed.append(tile)
            print(f"  [{k:>2}/{len(keep)}] {tile}  failed: {type(exc).__name__}: {exc}")
            continue
        r0, c0 = int(win.row_off), int(win.col_off)
        block = mosaic[r0:r0 + h, c0:c0 + w]
        fill = (block == UNSEEN) & (dst != 0)
        block[fill] = dst[fill]
        cloud = float(it.properties.get("eo:cloud_cover") or 0)
        print(f"  [{k:>2}/{len(keep)}] {tile}  {cloud:5.1f}% cloud, "
              f"{int(fill.sum()) * px_ha:>10,.0f} ha placed")

    profile = ref.profile.copy()
    profile.update(dtype="uint8", nodata=UNSEEN, compress="deflate",
                   tiled=True, blockxsize=512, blockysize=512, count=1)
    with rasterio.open(SCL_TIF, "w", **profile) as dst:
        dst.write(mosaic, 1)
    print(f"\n  wrote {SCL_TIF}")
    if failed:
        print(f"  {len(failed)} tile(s) failed and count as unseen: "
              f"{', '.join(failed)}. Rerun to retry them.")
    return mosaic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true",
                    help="reuse the SCL mosaic from an earlier run")
    args = ap.parse_args()

    for p in (MAP, RAW, UPPER):
        if not p.exists():
            sys.exit(f"missing {p}; it comes from full_scene.py and refine_scene.py")
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("CLEAR SKY OVER THE 12 AUGUST MAP, SENTINEL-2A SCL, 04:15 UTC")
    print("=" * 78)

    with rasterio.open(MAP) as ref:
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        if args.reuse and SCL_TIF.exists():
            with rasterio.open(SCL_TIF) as s:
                scl = s.read(1)
            print(f"  reusing {SCL_TIF}")
        else:
            scl = build_scl_mosaic(ref, px_ha)

        # counts[stratum, scl class], read in row blocks to keep memory modest
        counts = np.zeros((8, 256), "int64")
        with rasterio.open(RAW) as raw, rasterio.open(UPPER) as up:
            for r0 in range(0, ref.height, 1024):
                win = Window(0, r0, ref.width, min(1024, ref.height - r0))
                s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                              up.read(1, window=win))
                c = scl[r0:r0 + int(win.height)]
                counts += np.bincount((s.astype("int64") * 256 + c).ravel(),
                                      minlength=8 * 256).reshape(8, 256)

    rows = []
    for code, name in STRATA:
        total = counts[code].sum()
        if total == 0:
            continue
        g = {k: counts[code, v].sum() for k, v in GROUPS.items()}
        seen = total - g["unseen"]
        rows.append(dict(
            stratum=name,
            map_ha=round(total * px_ha),
            seen_pct=round(seen / total * 100, 1),
            clear_ha=round(g["clear"] * px_ha),
            clear_pct=round(g["clear"] / total * 100, 1),
            dark_or_unclassified_pct=round(g["dark or unclassified"] / total * 100, 1),
            cloud_pct=round(g["cloud"] / total * 100, 1),
            cirrus_pct=round(g["cirrus"] / total * 100, 1),
            scl_water_in_clear_pct=(round(counts[code, 6] / g["clear"] * 100, 1)
                                    if g["clear"] else ""),
        ))

    with open(OUT / "clear_sky_by_stratum.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print()
    print(f"  {'stratum':<22} {'map ha':>10} {'seen':>6} {'clear':>6} "
          f"{'clear ha':>10} {'dark':>6} {'cloud':>6} {'cirrus':>6} {'water':>6}")
    for r in rows:
        water = "" if r["scl_water_in_clear_pct"] == "" \
            else f"{r['scl_water_in_clear_pct']:.0f}%"
        print(f"  {r['stratum']:<22} {r['map_ha']:>10,} {r['seen_pct']:>5.0f}% "
              f"{r['clear_pct']:>5.0f}% {r['clear_ha']:>10,} "
              f"{r['dark_or_unclassified_pct']:>5.0f}% {r['cloud_pct']:>5.0f}% "
              f"{r['cirrus_pct']:>5.0f}% {water:>6}")

    print("\n  seen    inside a Sentinel-2 tile with SCL data")
    print("  clear   SCL vegetation, bare or water")
    print("  dark    SCL dark area or unclassified; often usable, check by eye")
    print("  cloud   SCL cloud or cloud shadow")
    print("  water   share of the clear pixels SCL calls water; a rough look,")
    print("          not a validation")
    print(f"\n  wrote {OUT / 'clear_sky_by_stratum.csv'}")


if __name__ == "__main__":
    main()
