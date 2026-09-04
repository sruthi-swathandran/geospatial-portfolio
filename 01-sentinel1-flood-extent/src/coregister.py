"""
RS-01 / step 7c — co-register the RTC chips to the Sen1Floods11 grid.

The shift test came back inconsistent: best offsets (1,1), (1,1) and (1,-1),
with gains of +0.064, +0.007 and +0.153. A constant grid error would give the
same shift everywhere. A shift that varies per chip, in a valley flanked by
hills, is the signature of TERRAIN: Planetary Computer's RTC is orthorectified
against the Copernicus DEM, Sen1Floods11's chips came through GEE's chain on
SRTM, and where the ground moves the two disagree by up to a pixel.

Why this matters more here than it usually would: 43.8% of the labelled water
lies within two pixels of land. A one-pixel registration error is at its most
damaging precisely where this flood lives — thin channels and field margins.
Validating an RTC-derived mask against these labels without fixing it would
charge our method for someone else's DEM.

So: estimate the integer shift per chip by maximising VH correlation against the
dataset's own chip, apply the SAME shift to the reference date (same orbit, same
processing chain, so they are already mutually aligned), and write aligned
copies. The shift is reported per chip and belongs in the write-up — "we
measured and corrected a terrain-dependent sub-pixel offset between two
processing chains" is a stronger sentence than any accuracy number.

The script also measures something worth its own paragraph: the water-land
CONTRAST in each product. If RTC's noise floor compresses dark water, RTC has
less separability than the dataset's chips, and that is a property of the
product rather than of anyone's algorithm.

Outputs:
    data/reference/India_<chip>_REF_ALIGNED.tif
    data/reference/India_<chip>_FLOODRTC_ALIGNED.tif
    results/coregistration.csv

Usage:
    python src\\coregister.py
    python src\\coregister.py --max-shift 3
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS          # noqa: E402
from chips import read                           # noqa: E402

REF_DIR = DATA / "reference"


def shifted_pair(a: np.ndarray, b: np.ndarray, dy: int, dx: int):
    """Overlapping views of a and b when a is displaced by (dy, dx)."""
    a1, b1 = (a[dy:, :], b[:-dy, :]) if dy > 0 else \
             (a[:dy, :], b[-dy:, :]) if dy < 0 else (a, b)
    a1, b1 = (a1[:, dx:], b1[:, :-dx]) if dx > 0 else \
             (a1[:, :dx], b1[:, -dx:]) if dx < 0 else (a1, b1)
    return a1, b1


def corr(a: np.ndarray, b: np.ndarray, dy: int, dx: int) -> float:
    a1, b1 = shifted_pair(a, b, dy, dx)
    m = np.isfinite(a1) & np.isfinite(b1)
    if m.sum() < 1000:
        return float("nan")
    return float(np.corrcoef(a1[m], b1[m])[0, 1])


def apply_shift(arr: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """
    Move arr by (dy, dx) onto the reference grid, filling vacated edges with NaN.

    NaN rather than zero or edge-replication: a fabricated value at the border
    would be silently classified as land or water later. NaN propagates into the
    nodata class where it belongs.
    """
    out = np.full_like(arr, np.nan, dtype="float32")
    src_y = slice(dy, None) if dy > 0 else slice(None, dy if dy else None)
    dst_y = slice(None, -dy if dy > 0 else None) if dy > 0 else \
            slice(-dy, None) if dy < 0 else slice(None)
    src_x = slice(dx, None) if dx > 0 else slice(None, dx if dx else None)
    dst_x = slice(None, -dx if dx > 0 else None) if dx > 0 else \
            slice(-dx, None) if dx < 0 else slice(None)
    out[..., dst_y, dst_x] = arr[..., src_y, src_x]
    return out


def contrast(vh: np.ndarray, label: np.ndarray) -> float | None:
    """Median land VH minus median water VH — how separable the classes are."""
    w = (label == 1) & np.isfinite(vh)
    l = (label == 0) & np.isfinite(vh)
    if w.sum() < 500 or l.sum() < 500:
        return None
    return float(np.median(vh[l]) - np.median(vh[w]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-shift", type=int, default=2)
    args = ap.parse_args()

    chips = sorted(p.name.split("_")[1]
                   for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC.tif"))
    if not chips:
        raise SystemExit("Nothing in data/reference — run fetch_reference.py first")

    print(f"{len(chips)} chip(s), searching shifts up to +/-{args.max_shift} px\n")
    rows = []
    r = range(-args.max_shift, args.max_shift + 1)

    for chip_id in chips:
        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC.tif") as src:
            ours = src.read().astype("float32")
            profile = src.profile
        theirs = read("S1Hand", chip_id).astype("float64")
        label = read("LabelHand", chip_id)[0]

        grid = {(dy, dx): corr(ours[1], theirs[1], dy, dx) for dy in r for dx in r}
        base = grid[(0, 0)]
        best = max(grid, key=lambda k: (grid[k] if np.isfinite(grid[k]) else -9))

        aligned = apply_shift(ours, *best)
        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif",
                           "w", **profile) as dst:
            dst.write(aligned)

        ref_path = REF_DIR / f"{EVENT}_{chip_id}_REF.tif"
        if ref_path.exists():
            with rasterio.open(ref_path) as src:
                ref = src.read().astype("float32")
            with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_REF_ALIGNED.tif",
                               "w", **profile) as dst:
                dst.write(apply_shift(ref, *best))

        rows.append({
            "chip_id": chip_id,
            "dy": best[0], "dx": best[1],
            "corr_before": round(base, 4),
            "corr_after": round(grid[best], 4),
            "gain": round(grid[best] - base, 4),
            "contrast_theirs_db": (lambda c: round(c, 2) if c else "")(
                contrast(theirs[1], label)),
            "contrast_ours_db": (lambda c: round(c, 2) if c else "")(
                contrast(aligned[1].astype("float64"), label)),
        })
        print(f"  {chip_id}  shift ({best[0]:+d},{best[1]:+d})  "
              f"corr {base:.3f} -> {grid[best]:.3f}  ({grid[best]-base:+.3f})")

    with open(RESULTS / "coregistration.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    dy = np.array([r["dy"] for r in rows])
    dx = np.array([r["dx"] for r in rows])
    gain = np.array([r["gain"] for r in rows])

    print("\nSHIFT DISTRIBUTION")
    print("------------------")
    for name, arr in (("dy", dy), ("dx", dx)):
        vals, counts = np.unique(arr, return_counts=True)
        print(f"  {name}: " + "  ".join(f"{v:+d}:{c}" for v, c in zip(vals, counts)))
    print(f"  mean correlation gain: {gain.mean():+.3f}  "
          f"(max {gain.max():+.3f})")
    print("  Shifts scattered across several values = terrain-dependent, which is"
          "\n  what we expected. All one value would have meant a plain grid "
          "offset.")

    ct = [r["contrast_theirs_db"] for r in rows if r["contrast_theirs_db"] != ""]
    co = [r["contrast_ours_db"] for r in rows if r["contrast_ours_db"] != ""]
    if ct and co:
        print("\nWATER-LAND CONTRAST (median land VH - median water VH)")
        print("------------------------------------------------------")
        print(f"  Sen1Floods11 chips (GEE sigma0):  {np.median(ct):5.2f} dB")
        print(f"  Planetary Computer RTC gamma0:    {np.median(co):5.2f} dB")
        print(f"  difference:                       {np.median(co)-np.median(ct):+5.2f} dB")
        print("  Less contrast means the same algorithm has less to work with. If"
              "\n  RTC is materially flatter, that is a property of the product, "
              "not of\n  anyone's method — and it is worth a paragraph, because "
              "'which product'\n  is a choice most pipelines make without "
              "measuring the cost.")

    print(f"\nwrote coregistration.csv and {len(rows)} aligned chip pair(s)")


if __name__ == "__main__":
    main()
