"""
RS-02 stage 2b. Does a parcel fail because it is narrow, or because its edge
is invisible?

Stage 3's district work turned up Jodhpur with the widest parcels in the Indian
test set, 7.35 native pixels median and none below the three-pixel floor, still
at 0.048 recall. The explanation offered was that arid ground gives little to
separate one field from the next, which is a claim about contrast rather than
resolution. It was never measured, only gestured at, and a district is a poor
unit for a claim about individual parcels.

So measure it. For every labelled parcel, take the mean gradient magnitude in
the band straddling its boundary and divide by the median gradient of the whole
chip. Dividing is what makes it comparable between scenes, since a hazy chip
and a clear one differ in absolute gradient everywhere.

The gradient is the same one compare_segmenters.py builds: Sobel magnitude
averaged across all eight bands of both seasonal windows, percentile stretched
per band, lightly smoothed.

Contrast belongs to the parcel and the imagery, not to any method, so this
computes it once and joins it to whichever method's width table you name.

    python src\\parcel_contrast.py --country india
    python src\\parcel_contrast.py --country india ^
        --width-file parcel_width_seg_sam_vit_h_false_min500.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

WIDTH_EDGES = [0, 3, 5, 10, np.inf]
WIDTH_LABELS = ["under 3", "3 to 5", "5 to 10", "10 and over"]


def boundary_contrast(mask: np.ndarray, grad: np.ndarray,
                      chip_median: float) -> float:
    """Mean gradient across the parcel's edge, relative to the chip.

    The band is one pixel either side of the boundary, so it samples the
    transition rather than the interior. A one-pixel parcel erodes to nothing
    and the band becomes its dilation, which is the right answer for a parcel
    that is all edge.
    """
    from scipy.ndimage import binary_dilation, binary_erosion
    band = binary_dilation(mask) & ~binary_erosion(mask)
    if not band.any() or chip_median <= 0:
        return float("nan")
    return float(grad[band].mean() / chip_median)


def measure(chips, px_m):
    """One row per labelled parcel: its width and its boundary contrast."""
    import compare_segmenters as C
    import seg_score as S

    rows, tic = [], time.time()
    for i, chip in enumerate(chips, 1):
        try:
            stack = C.read_stack(chip)
        except FileNotFoundError as exc:
            print(f"  skipping {chip}: {exc}")
            continue
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        grad = C.gradient(stack)
        chip_median = float(np.median(grad))
        scale = px_m / 10.0

        for pid in np.unique(full[full > 0]):
            mask = full == pid
            rows.append({
                "country": F.COUNTRY,
                "chip": chip,
                "parcel_id": int(pid),
                "width_native_px": round(S.parcel_width_px(mask) * scale, 3),
                "contrast": round(boundary_contrast(mask, grad, chip_median), 4),
            })

        if i % 50 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            left = (len(chips) - i) / rate if rate else 0
            print(f"    {i:>4,} / {len(chips):,}   {rate:.1f} chips/s   "
                  f"{left / 60:.1f} min left")
    return rows


# The chip's own pixels rather than 10 m ground. India sits on a 6.067 m grid
# and Slovenia on 4.139 m, so the same field is 4.9 pixels wide in one and 7.2
# in the other. A segmenter cares how many samples it has across an edge, not
# how much ground they cover.
GRID_EDGES = [0, 5, 8, 16, np.inf]
GRID_LABELS = ["under 5", "5 to 8", "8 to 16", "16 and over"]

# Fixed rather than per-country, so the same cell means the same thing in
# India and Slovenia.
CONTRAST_EDGES = [0, 1.0, 1.4, 1.9, np.inf]
CONTRAST_LABELS = ["under 1.0", "1.0 to 1.4", "1.4 to 1.9", "1.9 and over"]


def two_way(rows, width_file, iou_cut, px_m, unit):
    """Recall by width band against absolute boundary contrast."""
    import pandas as pd

    path = F.RESULTS / width_file
    if not path.exists():
        sys.exit(f"{path} not found")
    found = pd.read_csv(path)
    found["key"] = (found["chip"].astype(str) + "#"
                    + found["parcel_id"].astype(str))
    found = found[["key", "best_iou"]]

    df = pd.DataFrame(rows)
    df["key"] = df["chip"].astype(str) + "#" + df["parcel_id"].astype(str)
    df = df.merge(found, on="key", how="inner")
    missing = len(rows) - len(df)
    if missing:
        print(f"\n  {missing:,} parcels had no score in {width_file} "
              f"and are dropped")
    df = df.dropna(subset=["contrast"])
    df["hit"] = df["best_iou"] >= iou_cut

    if unit == "grid":
        df["w"] = df["width_native_px"] * 10.0 / px_m
        edges, labels = GRID_EDGES, GRID_LABELS
    else:
        df["w"] = df["width_native_px"]
        edges, labels = WIDTH_EDGES, WIDTH_LABELS
    df["band"] = pd.cut(df["w"], edges, labels=labels, right=False)
    df["contrast_band"] = pd.cut(df["contrast"], CONTRAST_EDGES,
                                 labels=CONTRAST_LABELS, right=False)

    print("\n" + RULE)
    print(f"RECALL BY WIDTH AND BOUNDARY CONTRAST, {width_file}")
    print(RULE)
    print(f"  width in {unit} pixels, "
          f"{'the chip grid' if unit == 'grid' else 'normalised to 10 m'}")
    print("  contrast is the mean gradient across the parcel edge divided by")
    print("  the chip's median gradient, on absolute bins\n")
    header = "".join(f"{c:>17}" for c in CONTRAST_LABELS)
    print(f"  {'width':>14}" + header)
    for wb in labels:
        cells = []
        for cb in CONTRAST_LABELS:
            sub = df[(df["band"] == wb) & (df["contrast_band"] == cb)]
            cells.append(f"{sub['hit'].mean() * 100:6.1f}% ({len(sub):>5,})"
                         if len(sub) else f"{'':>17}")
        print(f"  {wb:>14}" + "".join(cells))

    print("\n  medians within each width band")
    for wb in labels:
        sub = df[df["band"] == wb]
        if not len(sub):
            continue
        hit = sub[sub["hit"]]["contrast"]
        miss = sub[~sub["hit"]]["contrast"]
        print(f"    {wb:>14}  found {hit.median():5.2f} "
              f"({len(hit):>5,})   missed {miss.median():5.2f} "
              f"({len(miss):>5,})")

    print("\n" + RULE)
    print("Read across a row for the contrast effect at fixed width. Read the")
    print("same cell in both countries for whether the width floor is a")
    print("property of the pixels or of India's contrast.")
    print(RULE)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--width-file", default="",
                    help="a parcel_width_*.csv to cross against contrast")
    ap.add_argument("--width-unit", default="native",
                    choices=("native", "grid"),
                    help="native normalises to 10 m ground, grid uses the "
                         "chip's own pixels, which is what a method sees")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--recompute", action="store_true",
                    help="ignore the cached contrast file and measure again")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    out = F.RESULTS / "parcel_contrast.csv"
    px_m = F.grid_pixel_m()

    print(RULE)
    print(f"BOUNDARY CONTRAST, {F.COUNTRY.upper()}, grid {px_m:.3f} m")
    print(RULE)

    if out.exists() and not args.recompute:
        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            r["parcel_id"] = int(r["parcel_id"])
            r["width_native_px"] = float(r["width_native_px"])
            r["contrast"] = float(r["contrast"]) if r["contrast"] else np.nan
        print(f"  reusing {out.name}, {len(rows):,} parcels "
              f"(--recompute to measure again)")
    else:
        pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
        if not pred_dir.exists():
            sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
        chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
        if args.limit:
            chips = chips[:args.limit]
        print(f"  measuring {len(chips):,} chips\n")
        rows = measure(chips, px_m)
        if not rows:
            sys.exit("no parcels measured")
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  wrote {out.relative_to(F.PROJECT)}, {len(rows):,} parcels")

    vals = np.array([r["contrast"] for r in rows], dtype=float)
    vals = vals[np.isfinite(vals)]
    print(f"\n  contrast relative to chip median: "
          f"p10 {np.percentile(vals, 10):.2f}, "
          f"median {np.median(vals):.2f}, "
          f"p90 {np.percentile(vals, 90):.2f}")

    if args.width_file:
        two_way(rows, args.width_file, args.iou, px_m, args.width_unit)
    else:
        print("\n  pass --width-file to cross this against a method's recall")

if __name__ == "__main__":
    main()
