"""
RS-02. What does a grid pixel actually measure on the ground?

F-11 in REVIEW.md: this project measures its own pixel size geodesically and
never checks it against what Fields of The World says it ships. 6.067 m for
India and 4.139 m for Slovenia are load-bearing, because every parcel width in
three documents is normalised through them.

There is a second question the review did not ask and this answers too.
`grid_pixel_m` measures the geodesic width of a chip and divides by its pixel
count, so it reports the east to west size of a pixel. If the chips sit on a
grid of constant degrees rather than constant metres, then a pixel is a fixed
number of degrees in both directions, the east to west ground size shrinks with
the cosine of latitude while the north to south size barely moves, and pixels
are taller than they are wide. Slovenia sits about twenty degrees nearer the
pole than India, so any such effect lands on the two countries differently and
would run straight through the cross-country comparisons.

So this reads the chips rather than reasoning about them. It reports the CRS,
the transform, and the geodesic size of one pixel along both axes at the
latitude of each chip.

    python src\\grid_check.py --country india
    python src\\grid_check.py --country slovenia
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--chips", type=int, default=60)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    from pyproj import Geod
    geod = Geod(ellps="WGS84")

    names = F.chip_names()[:args.chips]
    if not names:
        sys.exit("no chips found")

    print(RULE)
    print(f"GRID GEOMETRY, {F.COUNTRY.upper()}, {len(names)} chips")
    print(RULE)

    rows = []
    crs_seen, shapes, px_units = set(), set(), []
    for name in names:
        with rasterio.open(F.INSTANCE / name) as s:
            crs_seen.add(str(s.crs))
            shapes.add((s.height, s.width))
            t = s.transform
            px_units.append((abs(t.a), abs(t.e)))
            left, bottom, right, top = s.bounds
            midlat = (bottom + top) / 2
            midlon = (left + right) / 2
            # east to west across the middle row, north to south down the
            # middle column, both on the ellipsoid
            _, _, w_m = geod.inv(left, midlat, right, midlat)
            _, _, h_m = geod.inv(midlon, bottom, midlon, top)
            rows.append((midlat, w_m / s.width, h_m / s.height))

    lats = np.array([r[0] for r in rows])
    wide = np.array([r[1] for r in rows])
    tall = np.array([r[2] for r in rows])

    print(f"  CRS            {sorted(crs_seen)}")
    print(f"  raster shape   {sorted(shapes)}")
    ax = np.array([p[0] for p in px_units])
    ay = np.array([p[1] for p in px_units])
    print(f"  transform      {ax.mean():.8g} by {ay.mean():.8g} CRS units "
          f"per pixel")
    print(f"  square in CRS  {'yes' if np.allclose(ax, ay) else 'no'}")
    print(f"\n  latitude       {lats.min():.2f} to {lats.max():.2f} degrees")
    print(f"\n  one pixel on the ground")
    print(f"    east to west   {wide.mean():.3f} m  "
          f"(range {wide.min():.3f} to {wide.max():.3f})")
    print(f"    north to south {tall.mean():.3f} m  "
          f"(range {tall.min():.3f} to {tall.max():.3f})")
    ratio = tall.mean() / wide.mean()
    print(f"    taller than wide by {ratio:.3f}x")

    print(f"\n  grid_pixel_m() reports {F.grid_pixel_m():.3f} m, which is the")
    print(f"  east to west figure. Every width in this project is normalised")
    print(f"  through it.")

    print("\n" + RULE)
    if abs(ratio - 1.0) < 0.02:
        print("Pixels are square on the ground to within 2%, so measuring one")
        print("axis was safe and the normalised widths stand.")
    else:
        print(f"Pixels are NOT square on the ground: {ratio:.3f} times taller")
        print("than wide. A parcel width counted in pixels therefore means a")
        print("different distance depending on which way the parcel runs, and")
        print("the effect differs between countries because it follows")
        print("latitude. Every width normalised through a single number needs")
        print("rereading, and the cross-country tables most of all.")
    print(RULE)
    print("Compare the transform against what FTW documents it ships. A grid")
    print("in degrees explains a latitude-dependent ground size; a grid in")
    print("metres does not, and would mean something else is going on.")
    print(RULE)


if __name__ == "__main__":
    main()
