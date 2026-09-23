"""
RS-02. Parcel width in metres, measured on pixels that are not square.

`grid_check.py` found that Fields of The World ships the two countries on
different grid conventions. India's chips carry non-square degree pixels
chosen so that a pixel comes out square on the ground, 6.069 m by 6.068 m.
Slovenia's carry square degree pixels at latitude 46.6, which on the ground
are 4.138 m across and 6.002 m tall, taller than wide by 1.450.

`seg_score.parcel_width_px` measures the largest inscribed circle with
`distance_transform_edt` and no sampling argument, so it counts a step north
as the same length as a step east. The result is then multiplied by
`grid_pixel_m()`, which reports the east to west size alone. On India that is
correct. On Slovenia it understates any parcel whose narrow axis runs north to
south, by up to the full 1.450.

Every Slovenian width in this project passes through that, so every band it
was sorted into and every cross-country comparison built on those bands needs
remeasuring. This does the measuring.

The fix is one argument. `distance_transform_edt` takes `sampling`, a physical
size per axis, and returns distances in those units. Handing it the two ground
sizes gives the inscribed circle in metres directly, with no scale factor
afterwards and nothing assumed about the pixel being square.

Pixel sizes are read per chip rather than averaged, since they drift across a
country and Slovenia's chips are the ones that matter.

    python src\\width_ground.py --country india
    python src\\width_ground.py --country slovenia

Writes parcel_width_ground.csv, which carries both the published width and the
corrected one so the difference can be read rather than taken on trust.
"""

from __future__ import annotations

import argparse
import sys
import time
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
WIDTH_EDGES_M = [0, 20, 30, 50, np.inf]
WIDTH_LABELS_M = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def chip_pixel_m(path: Path, geod):
    """Ground size of one pixel on this chip, east to west and north to south."""
    with rasterio.open(path) as s:
        left, bottom, right, top = s.bounds
        midlat, midlon = (bottom + top) / 2, (left + right) / 2
        _, _, w_m = geod.inv(left, midlat, right, midlat)
        _, _, h_m = geod.inv(midlon, bottom, midlon, top)
        return w_m / s.width, h_m / s.height


def width_metres(mask: np.ndarray, x_m: float, y_m: float) -> float:
    """Largest inscribed circle, in metres, on rectangular pixels.

    sampling takes the physical size of a step along each axis, so the
    distance comes back in metres and no scale factor is applied afterwards.
    The 2d minus one pixel convention of the original is kept, expressed as
    subtracting the smaller of the two pixel sizes, so that a one-pixel strip
    still reports the width of one pixel rather than nothing.
    """
    from scipy.ndimage import distance_transform_edt
    if not mask.any():
        return 0.0
    d = distance_transform_edt(np.pad(mask, 1, constant_values=False),
                               sampling=(y_m, x_m))
    return max(min(x_m, y_m), float(d.max()) * 2.0 - min(x_m, y_m))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import pandas as pd
    from pyproj import Geod
    geod = Geod(ellps="WGS84")

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    if not pred_dir.exists():
        sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    px_m = F.grid_pixel_m()
    print(RULE)
    print(f"GROUND WIDTH, {F.COUNTRY.upper()}, {len(chips):,} chips")
    print(RULE)
    print(f"  the published width uses one number for both axes, "
          f"{px_m:.3f} m\n")

    rows, tic = [], time.time()
    for i, chip in enumerate(chips, 1):
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        x_m, y_m = chip_pixel_m(F.INSTANCE / chip, geod)
        for pid in np.unique(full[full > 0]):
            mask = full == pid
            # the published measure, rebuilt here so the two sit side by side
            from scipy.ndimage import distance_transform_edt
            d = distance_transform_edt(np.pad(mask, 1, constant_values=False))
            old_px = max(1.0, float(d.max()) * 2.0 - 1.0)
            rows.append({
                "country": F.COUNTRY,
                "chip": chip,
                "parcel_id": int(pid),
                "px_x_m": round(x_m, 4),
                "px_y_m": round(y_m, 4),
                "width_published_m": round(old_px * px_m, 2),
                "width_ground_m": round(width_metres(mask, x_m, y_m), 2),
            })
        if i % 50 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            print(f"    {i:>4,} / {len(chips):,}   {rate:.1f} chips/s   "
                  f"{(len(chips) - i) / rate / 60:.1f} min left")

    if not rows:
        sys.exit("no parcels measured")
    df = pd.DataFrame(rows)
    df["ratio"] = (df["width_ground_m"] / df["width_published_m"]).round(4)
    out = F.RESULTS / "parcel_width_ground.csv"
    df.to_csv(out, index=False)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}, {len(df):,} parcels")

    print("\n" + RULE)
    print("RESULT")
    print(RULE)
    print(f"  pixel, east to west {df['px_x_m'].mean():.3f} m, "
          f"north to south {df['px_y_m'].mean():.3f} m")
    print(f"  corrected over published width: median "
          f"{df['ratio'].median():.3f}x, "
          f"p10 {df['ratio'].quantile(.1):.3f}x, "
          f"p90 {df['ratio'].quantile(.9):.3f}x")
    print(f"  median width  published {df['width_published_m'].median():.1f} m"
          f"   corrected {df['width_ground_m'].median():.1f} m")

    print("\n  how many parcels change band")
    old = pd.cut(df["width_published_m"], WIDTH_EDGES_M,
                 labels=WIDTH_LABELS_M, right=False)
    new = pd.cut(df["width_ground_m"], WIDTH_EDGES_M,
                 labels=WIDTH_LABELS_M, right=False)
    moved = (old.astype(str) != new.astype(str))
    print(f"    {int(moved.sum()):,} of {len(df):,}, "
          f"{float(moved.mean()) * 100:.1f}%")
    print(f"\n    {'band':>12} {'published':>10} {'corrected':>10} {'change':>8}")
    for lab in WIDTH_LABELS_M:
        a, b = int((old == lab).sum()), int((new == lab).sum())
        print(f"    {lab:>12} {a:>10,} {b:>10,} {b - a:>+8,}")

    print("\n" + RULE)
    print("A ratio near 1.000 means the published width was already the ground")
    print("width and nothing downstream moves. Anything else means the bands")
    print("in COMPARISON.md were cut on the wrong numbers for this country,")
    print("and the cross-country tables were comparing unlike with unlike.")
    print(RULE)


if __name__ == "__main__":
    main()
