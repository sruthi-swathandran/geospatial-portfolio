"""
RS-01 / validation. Measure how bright the Sentinel-2A image is around each
sample point, to find the clouds that SCL missed.

SCL, the scene classification shipped with the 2016 L2A product, let through
points that sit inside thick cloud: P0021 in the first draw, which it called
bare soil, and P0002 in the second, despite the 100 m rule. Cloud is bright in
every visible band and close to white. Most ground is not: vegetation and water
are dark in blue, and bare soil and sand bars are redder than they are blue.
So two numbers per point say a great deal:

  blue      surface reflectance in band 2, the highest value within 100 m
  white     band 2 over band 4, blue over red, at that same pixel; near 1 or
            above for cloud and haze, lower for soil and sand

A first run showed that the highest value alone also catches villages, whose
tin roofs are bright and nearly white in single 10 m pixels. Cloud and haze
cover many pixels at once. So the script also records the share of pixels
within 100 m that look like cloud, and saves every patch, so that rules can be
compared later without downloading again.

This script only measures. It changes nothing in the sample. Its output is
used to choose a brightness rule, which then goes into draw_sample.py.

Usage
-----
    python src\\screen_points.py
    python src\\screen_points.py --key points_key_draw1.csv

Writes results/validation/sample/screen.csv (or screen_<key name>.csv), one
row per point with no stratum, and prints how many points each candidate rule
would remove. The raw patches go to data/validation/, which git ignores.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clear_sky import MAP, WORK                                  # noqa: E402
from draw_sample import SAMPLE, find_items, read_patch, scale_of  # noqa: E402

RADIUS_M = 100
RULES = [(0.15, 0.85), (0.18, 0.85), (0.20, 0.80), (0.20, 0.90), (0.25, 0.80)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="points_key.csv",
                    help="key file in results/validation/sample")
    args = ap.parse_args()

    with open(SAMPLE / args.key, encoding="utf-8") as fh:
        points = list(csv.DictReader(fh))
    with rasterio.open(MAP) as ref:
        crs = ref.crs
    items = find_items()
    feet = [(shape(it.geometry), it) for it in items]

    out, patches = [], {}
    width = 2 * RADIUS_M
    px = width // 10
    yy, xx = np.mgrid[0:px, 0:px] - (px - 1) / 2
    disk = np.hypot(yy, xx) * 10 <= RADIUS_M
    print(f"  measuring {len(points)} points, two small reads each ...")
    for n, p in enumerate(points, 1):
        here = Point(float(p["lon"]), float(p["lat"]))
        item = next((it for g, it in feet if g.contains(here)), None)
        row = dict(point_id=p["point_id"], blue_max="", white_at_max="",
                   blue_centre="", white_centre="", blue_p75="",
                   cloudlike_share="")
        if item is not None:
            off = scale_of(item)
            x, y = float(p["x"]), float(p["y"])
            try:
                b2 = (read_patch(item.assets["B02"].href, x, y, width, px, crs)
                      + off) / 10000
                b4 = (read_patch(item.assets["B04"].href, x, y, width, px, crs)
                      + off) / 10000
                patches[p["point_id"]] = np.stack([b2, b4]).astype("float32")
                b2 = np.where(disk, b2, np.nan)
                like = (b2 > 0.12) & (b2 / np.maximum(b4, 1e-4) > 0.95)
                i = np.unravel_index(np.nanargmax(b2), b2.shape)
                c = (slice(px // 2 - 1, px // 2 + 1),) * 2
                row.update(
                    blue_max=round(float(b2[i]), 4),
                    white_at_max=round(float(b2[i] / max(b4[i], 1e-4)), 3),
                    blue_centre=round(float(np.nanmean(b2[c])), 4),
                    white_centre=round(float(np.nanmean(b2[c])
                                             / max(np.nanmean(b4[c]), 1e-4)), 3),
                    blue_p75=round(float(np.nanpercentile(b2, 75)), 4),
                    cloudlike_share=round(float(like[disk].mean()), 3))
            except Exception as exc:
                print(f"  {p['point_id']} failed: {type(exc).__name__}: {exc}")
        out.append(row)
        if n % 50 == 0 or n == len(points):
            print(f"  {n}/{len(points)}")

    name = "screen.csv" if args.key == "points_key.csv" \
        else f"screen_{Path(args.key).stem}.csv"
    with open(SAMPLE / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    WORK.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(WORK / name.replace(".csv", "_patches.npz"), **patches)

    ok = [r for r in out if r["blue_max"] != ""]
    blue = np.array([r["blue_max"] for r in ok], float)
    print(f"\n  {len(ok)} points measured")
    print("  highest blue reflectance within 100 m, percentiles:")
    for q in (50, 75, 90, 95, 99):
        print(f"    {q:>3}%  {np.percentile(blue, q):.3f}")
    print("\n  points each rule would remove (blue above, and blue over red above)")
    for b, wht in RULES:
        hit = [r["point_id"] for r in ok
               if r["blue_max"] > b and r["white_at_max"] > wht]
        print(f"    blue > {b:.2f}, white > {wht:.2f}:  {len(hit):>4}   "
              f"{' '.join(hit[:12])}{' ...' if len(hit) > 12 else ''}")
    print(f"\n  wrote {SAMPLE / name}")


if __name__ == "__main__":
    main()
