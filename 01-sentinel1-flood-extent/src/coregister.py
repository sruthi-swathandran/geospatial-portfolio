"""
RS-01 / step 8 — co-register the RTC chips to the Sen1Floods11 grid.

Revised after the agreement check, which changed two things.

FIRST: correlate on speckle-suppressed images, not raw pixels. Median agreement
across 68 chips went 0.582 raw, 0.816 after 5x5 averaging, 0.922 after averaging
plus a shift. Speckle is an independent random realisation in each processing
chain, so on raw pixels it swamps the signal we are trying to align on. Aligning
on the averaged image is both more reliable and more honest about what is being
matched: structure, not noise.

SECOND, and this is why the earlier run should not be trusted: the previous
search allowed shifts of +/-2, and 37 of 68 chips came back with dx = -2 — the
edge of the search. An optimum sitting on the boundary of its search range is
not an optimum; it is a truncation. The real offset may be larger, and every
chip pegged at the edge was under-corrected.

So the search widens to +/-5 by default and the script reports how many chips
land on the boundary. If that count is not near zero, widen it further and run
again rather than accepting the numbers.

A shift concentrated on one value is a systematic offset between the two
products, worth stating as a finding in its own right: 2 pixels is 20 m, and
20 m matters when 43.8% of the labelled water sits within 20 m of land.

The reported (dy, dx) is the CORRECTION applied to the RTC image to bring it
onto the label grid — the negative of the measured displacement. The sign
convention and apply_shift were verified by a round trip: an image displaced by
a known (sy, sx) yields best = (-sy, -sx) and correlates at 1.000 after the
correction is applied.

Outputs:
    data/reference/India_<chip>_REF_ALIGNED.tif
    data/reference/India_<chip>_FLOODRTC_ALIGNED.tif
    results/coregistration.csv
    results/usable_chips.txt      chips whose alignment actually converged

Usage:
    python src\\coregister.py
    python src\\coregister.py --max-shift 8
    python src\\coregister.py --min-corr 0.6
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
from chips import read, block_mean               # noqa: E402

REF_DIR = DATA / "reference"


def corr(a: np.ndarray, b: np.ndarray, dy: int, dx: int) -> float:
    a1, b1 = (a[dy:, :], b[:-dy, :]) if dy > 0 else \
             (a[:dy, :], b[-dy:, :]) if dy < 0 else (a, b)
    a1, b1 = (a1[:, dx:], b1[:, :-dx]) if dx > 0 else \
             (a1[:, :dx], b1[:, -dx:]) if dx < 0 else (a1, b1)
    m = np.isfinite(a1) & np.isfinite(b1)
    if m.sum() < 1000 or np.std(a1[m]) == 0 or np.std(b1[m]) == 0:
        return float("nan")
    return float(np.corrcoef(a1[m], b1[m])[0, 1])


def apply_shift(arr: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """
    Move arr by (dy, dx) onto the reference grid, filling vacated edges with NaN.

    NaN rather than zero or edge replication: a fabricated border value would be
    silently classified as land or water downstream. NaN propagates into the
    nodata class, where it belongs.
    """
    out = np.full_like(arr, np.nan, dtype="float32")
    if dy == 0 and dx == 0:
        out[...] = arr
        return out
    src_y = slice(dy, None) if dy > 0 else slice(None, dy)
    dst_y = slice(None, -dy) if dy > 0 else slice(-dy, None)
    if dy == 0:
        src_y = dst_y = slice(None)
    src_x = slice(dx, None) if dx > 0 else slice(None, dx)
    dst_x = slice(None, -dx) if dx > 0 else slice(-dx, None)
    if dx == 0:
        src_x = dst_x = slice(None)
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
    ap.add_argument("--max-shift", type=int, default=5)
    ap.add_argument("--min-corr", type=float, default=0.50,
                    help="chips below this after alignment are excluded downstream")
    args = ap.parse_args()

    chips = sorted(p.name.split("_")[1]
                   for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC.tif"))
    if not chips:
        raise SystemExit("Nothing in data/reference — run fetch_reference.py first")

    print(f"{len(chips)} chips, searching +/-{args.max_shift} px on "
          f"speckle-suppressed images\n")
    rng = range(-args.max_shift, args.max_shift + 1)
    rows = []

    for n, chip_id in enumerate(chips, 1):
        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC.tif") as src:
            ours = src.read().astype("float32")
            profile = src.profile
        theirs = read("S1Hand", chip_id).astype("float64")
        label = read("LabelHand", chip_id)[0]

        ob, tb = block_mean(ours[1].astype("float64")), block_mean(theirs[1])
        grid = {(dy, dx): corr(ob, tb, dy, dx) for dy in rng for dx in rng}
        base = grid[(0, 0)]
        best = max(grid, key=lambda k: (grid[k] if np.isfinite(grid[k]) else -9))
        at_edge = abs(best[0]) == args.max_shift or abs(best[1]) == args.max_shift

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
            "at_search_edge": int(at_edge),
            "corr_before": round(base, 4) if np.isfinite(base) else "",
            "corr_after": round(grid[best], 4) if np.isfinite(grid[best]) else "",
            "gain": round(grid[best] - base, 4)
            if np.isfinite(base) and np.isfinite(grid[best]) else "",
            "contrast_theirs_db": (lambda c: round(c, 2) if c is not None else "")(
                contrast(theirs[1], label)),
            "contrast_ours_db": (lambda c: round(c, 2) if c is not None else "")(
                contrast(aligned[1].astype("float64"), label)),
        })
        print(f"\r  {n}/{len(chips)}", end="", flush=True)
    print()

    with open(RESULTS / "coregistration.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    dy = np.array([r["dy"] for r in rows])
    dx = np.array([r["dx"] for r in rows])
    after = np.array([r["corr_after"] if r["corr_after"] != "" else np.nan
                      for r in rows], dtype=float)
    before = np.array([r["corr_before"] if r["corr_before"] != "" else np.nan
                       for r in rows], dtype=float)
    edge = np.array([r["at_search_edge"] for r in rows])

    print("SEARCH VALIDITY")
    print("---------------")
    print(f"  chips whose best shift sat on the +/-{args.max_shift} boundary: "
          f"{edge.sum()} of {len(rows)}")
    if edge.sum() > len(rows) * 0.05:
        print(f"  ^ too many. Re-run with --max-shift {args.max_shift * 2} before "
              "trusting anything below.")
    else:
        print("  ^ few enough that the search range is not the limiting factor.")

    print("\nSHIFT DISTRIBUTION")
    print("------------------")
    pairs, counts = np.unique(np.stack([dy, dx], 1), axis=0, return_counts=True)
    for pair, c in sorted(zip(pairs.tolist(), counts.tolist()), key=lambda x: -x[1])[:8]:
        print(f"  ({pair[0]:+d},{pair[1]:+d}): {c} chips")
    print(f"\n  dy: median {np.median(dy):+.1f}  mean {dy.mean():+.2f}  "
          f"sd {dy.std():.2f}")
    print(f"  dx: median {np.median(dx):+.1f}  mean {dx.mean():+.2f}  "
          f"sd {dx.std():.2f}")
    print(f"\n  These are CORRECTIONS applied to the RTC image, so the measured"
          f"\n  displacement is the opposite sign. A consistent non-zero median is a"
          f"\n  systematic offset between the two products: "
          f"{abs(np.median(dx))*10:.0f} m in x, {abs(np.median(dy))*10:.0f} m in y"
          f"\n  at 10 m pixels. The spread around it is terrain.")

    print("\nAGREEMENT")
    print("---------")
    ok = np.isfinite(after) & np.isfinite(before)
    print(f"  before alignment: median {np.nanmedian(before):.3f}")
    print(f"  after alignment:  median {np.nanmedian(after):.3f}   "
          f"p10 {np.nanpercentile(after, 10):.3f}   min {np.nanmin(after):.3f}")
    print(f"  mean gain: {np.mean(after[ok] - before[ok]):+.3f}")

    usable = [r["chip_id"] for r, a in zip(rows, after)
              if np.isfinite(a) and a >= args.min_corr]
    (RESULTS / "usable_chips.txt").write_text("\n".join(usable))
    print(f"\n  chips reaching correlation >= {args.min_corr} after alignment: "
          f"{len(usable)} of {len(rows)}")
    print("  wrote usable_chips.txt — the subset the change detector should use.")
    print("  Chips that will not align are usually steep terrain, where a single"
          "\n  rigid shift cannot fix a locally varying displacement. Excluding "
          "them and\n  saying so is better than averaging over them silently.")

    ct = [r["contrast_theirs_db"] for r in rows if r["contrast_theirs_db"] != ""]
    co = [r["contrast_ours_db"] for r in rows if r["contrast_ours_db"] != ""]
    if ct and co:
        print("\nWATER-LAND CONTRAST (median land VH - median water VH)")
        print("------------------------------------------------------")
        print(f"  Sen1Floods11 chips (GEE sigma0):  {np.median(ct):5.2f} dB  "
              f"(n={len(ct)})")
        print(f"  Planetary Computer RTC gamma0:    {np.median(co):5.2f} dB")
        print(f"  difference:                       {np.median(co)-np.median(ct):+5.2f} dB")
        print("  Less contrast means the same algorithm has less to work with — a"
              "\n  property of the product, not of anyone's method.")

    print("\nwrote coregistration.csv and aligned chip pairs")


if __name__ == "__main__":
    main()
