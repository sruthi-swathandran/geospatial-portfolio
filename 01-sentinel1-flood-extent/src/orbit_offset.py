"""
RS-01 / step 11d - is a threshold tuned on orbit 77 usable on orbit 4?

The plan is to map 7 August 2016 on relative orbit 4 to cover the eastern wedge
that orbit 77 misses. Reusing the -18.75 dB threshold there is an assumption,
and it is the same shape as three assumptions this project has already had to
retract: something measured in one situation and applied to another that was
never like it.

Two orbits see the same ground at different incidence angles. RTC corrects for
terrain, not for viewing geometry, so gamma0 from orbit 4 and gamma0 from orbit
77 are not guaranteed to sit on the same scale. If they differ by a decibel or
two, one threshold produces two maps with different sensitivities and the seam
between them is a processing artefact rather than hydrology.

The test samples tiles where both passes overlap and compares their VH. Most of
that overlap is land that did not change, so the MEDIAN difference across it is
a reasonable estimate of the systematic offset between the two acquisitions.

WHAT THIS CANNOT SEPARATE, stated plainly
-----------------------------------------
Five days of monsoon sit between 7 and 12 August. Wetter soil lowers backscatter
on its own, so the measured offset mixes viewing geometry with real change in
ground moisture. Nothing here can pull those apart, and this script does not
pretend otherwise. What it gives you is the size of the discrepancy, which is
what decides whether one threshold can serve both maps.

If the offset is small, use one threshold and say the two orbits agreed to
within that much. If it is large, map the second pass at its own Otsu-derived
threshold and report the wedge area under both choices as a sensitivity, the
same way the reference date and the permanent water cut are already reported.

Outputs:
    results/orbit_offset.csv
    results/figures/orbit_offset.png

Usage:
    python src\\orbit_offset.py
    python src\\orbit_offset.py --date 2016-08-07 --orbit 4 --tiles 8
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
from shapely.geometry import box as sbox, shape   # noqa: E402
from shapely.ops import unary_union         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, RESULTS, FLOOD_DATE, RELATIVE_ORBIT   # noqa: E402
from full_scene import (                                        # noqa: E402
    open_catalog, flood_items, target_geobox, tiles, padded, read_vh,
)

FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def footprint(items):
    return unary_union([shape(i.geometry) for i in items])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--date", default="2016-08-07")
    ap.add_argument("--orbit", type=int, default=4)
    ap.add_argument("--tiles", type=int, default=8,
                    help="how many overlap tiles to sample")
    args = ap.parse_args()

    client = open_catalog()
    a_items = flood_items(client, quiet=True, date=FLOOD_DATE,
                          orbit=RELATIVE_ORBIT)
    b_items = flood_items(client, quiet=True, date=args.date, orbit=args.orbit)
    print(f"A: {FLOOD_DATE} orbit {RELATIVE_ORBIT}, {len(a_items)} frame(s)")
    print(f"B: {args.date} orbit {args.orbit}, {len(b_items)} frame(s)\n")

    fa, fb = footprint(a_items), footprint(b_items)
    gbox = target_geobox(args.res)
    all_tiles = list(tiles(gbox))
    both = []
    for key, y0, y1, x0, x1 in all_tiles:
        bb = gbox[y0:y1, x0:x1].extent.to_crs("EPSG:4326").boundingbox
        t = sbox(bb.left, bb.bottom, bb.right, bb.top)
        if t.intersects(fa) and t.intersects(fb):
            both.append((key, y0, y1, x0, x1))
    print(f"{len(both)} of {len(all_tiles)} tiles fall in the overlap")
    if len(both) < 2:
        raise SystemExit("not enough overlap to compare")

    stride = max(1, len(both) // args.tiles)
    picked = both[::stride][:args.tiles]
    print(f"sampling {len(picked)} of them\n")

    rows, dA, dB, dD = [], [], [], []
    t0 = time.time()
    for n, (key, y0, y1, x0, x1) in enumerate(picked, 1):
        pg, _ = padded(gbox, y0, y1, x0, x1)
        try:
            va = read_vh(a_items, pg)
            vb = read_vh(b_items, pg)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  tile {key} skipped: {exc}")
            continue
        m = np.isfinite(va) & np.isfinite(vb)
        if m.sum() < 50_000:
            continue
        a, b = va[m], vb[m]
        d = a - b
        # land-only view: bright in both, so neither is water on either date
        land = (a > -14) & (b > -14)
        rows.append({
            "tile": f"{key[0]}_{key[1]}",
            "pixels": int(m.sum()),
            "median_A_db": round(float(np.median(a)), 3),
            "median_B_db": round(float(np.median(b)), 3),
            "median_diff_db": round(float(np.median(d)), 3),
            "median_diff_land_db": round(float(np.median(d[land])), 3)
            if land.sum() > 5000 else None,
            "p25_diff": round(float(np.percentile(d, 25)), 3),
            "p75_diff": round(float(np.percentile(d, 75)), 3),
        })
        dA.append(a[::13]); dB.append(b[::13]); dD.append(d[::13])
        print(f"\r  {n}/{len(picked)} tiles ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    if not rows:
        raise SystemExit("no usable overlap tiles")

    A = np.concatenate(dA); Bv = np.concatenate(dB); D = np.concatenate(dD)
    land = (A > -14) & (Bv > -14)

    print("\nPER TILE")
    print("--------")
    print(f"  {'tile':<8}{'px':>10}{'median A':>11}{'median B':>11}"
          f"{'A-B':>9}{'A-B land':>11}")
    for r in rows:
        ml = r["median_diff_land_db"]
        print(f"  {r['tile']:<8}{r['pixels']:>10,}{r['median_A_db']:>11.2f}"
              f"{r['median_B_db']:>11.2f}{r['median_diff_db']:>9.2f}"
              f"{(f'{ml:.2f}' if ml is not None else '-'):>11}")

    off_all = float(np.median(D))
    off_land = float(np.median(D[land])) if land.sum() > 1000 else float("nan")
    spread = float(np.std([r["median_diff_land_db"] for r in rows
                           if r["median_diff_land_db"] is not None]))

    print("\nPOOLED")
    print("------")
    print(f"  median VH, {FLOOD_DATE} orbit {RELATIVE_ORBIT}   "
          f"{np.median(A):>7.2f} dB")
    print(f"  median VH, {args.date} orbit {args.orbit}    "
          f"{np.median(Bv):>7.2f} dB")
    print(f"  offset A minus B, all pixels          {off_all:>7.2f} dB")
    print(f"  offset A minus B, land only           {off_land:>7.2f} dB")
    print(f"  tile to tile spread of the land offset {spread:>6.2f} dB")

    print("\nWHAT TO DO WITH THIS")
    print("--------------------")
    if abs(off_land) < 0.5:
        print(f"  {abs(off_land):.2f} dB is small. Use -18.75 dB on both passes "
              "and state that\n  the two orbits agreed to within that much over "
              "their overlap.")
    elif abs(off_land) < 1.5:
        print(f"  {off_land:+.2f} dB is worth carrying. Map orbit {args.orbit} "
              f"at {-18.75 - off_land:.2f} dB\n  as the matched-sensitivity "
              "choice, and report the wedge area at -18.75 dB\n  as well, so "
              "the reader sees what the correction was worth.")
    else:
        print(f"  {off_land:+.2f} dB is too large to wave through. One threshold "
              "across both\n  passes would give the two halves of the map "
              "different sensitivities.\n  Derive orbit "
              f"{args.orbit}'s threshold from its own histogram and treat the "
              "two\n  maps as separate products that are never mosaicked.")
    print("\n  Remember the confound: five days of monsoon sit between these "
          "two dates,\n  so part of this offset is wetter ground rather than "
          "viewing geometry.\n  A tile to tile spread much larger than the "
          "offset itself would say the\n  difference is local weather rather "
          "than a systematic instrument effect.")

    with open(RESULTS / "orbit_offset.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    ax = axes[0]
    ax.hist(A, bins=140, range=(-30, -2), histtype="step", density=True,
            color="#2b6f8f", linewidth=1.6,
            label=f"{FLOOD_DATE} orbit {RELATIVE_ORBIT}")
    ax.hist(Bv, bins=140, range=(-30, -2), histtype="step", density=True,
            color="#b06a30", linewidth=1.6,
            label=f"{args.date} orbit {args.orbit}")
    ax.axvline(-18.75, color="black", linestyle="--", linewidth=1,
               label="-18.75 dB threshold")
    ax.set_xlabel("VH (dB)"); ax.set_ylabel("density")
    ax.set_title("Do the two orbits sit on the same scale?")
    ax.legend(fontsize=8); ax.grid(alpha=.25)

    ax = axes[1]
    ax.hist(D, bins=140, range=(-8, 8), color="#2b6f8f", alpha=.55,
            density=True, label="all overlap pixels")
    ax.hist(D[land], bins=140, range=(-8, 8), histtype="step", density=True,
            color="#333333", linewidth=1.4, label="land in both")
    ax.axvline(0, color="black", linewidth=.8)
    ax.axvline(off_land, color="#b03030", linestyle="--", linewidth=1.3,
               label=f"land median {off_land:+.2f} dB")
    ax.set_xlabel("VH difference, A minus B (dB)")
    ax.set_title("Offset between the two acquisitions")
    ax.legend(fontsize=8); ax.grid(alpha=.25)

    fig.suptitle(f"{EVENT}: cross-orbit check before mapping the eastern wedge")
    fig.tight_layout()
    fig.savefig(FIGURES / "orbit_offset.png", dpi=130)
    print("\nwrote orbit_offset.csv and figures/orbit_offset.png")


if __name__ == "__main__":
    main()
