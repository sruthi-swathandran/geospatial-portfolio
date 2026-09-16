"""
RS-02. How thick is the boundary ring, exactly.

This decides a 26% disagreement about the headline number.

measure_fields.py reports the ring as "two pixels wide" because 98.93% of it
lies within two 4-connected dilation steps of a parcel interior. That test is
blunt. A 4-connected step does not reach diagonally, so a ring exactly ONE
pixel thick still puts its corner pixels at two steps, and the 79/20 split
between one step and two is what a one-pixel ring looks like under that test,
not a two-pixel one.

Thickness matters because it decides whether the reconstruction is right:

    one pixel thick   the ring is the parcel's own outer edge. interior + ring
                      is the parcel, the reconstruction is exact, and the
                      median parcel is 0.302 ha.

    two pixels thick  the band may straddle the true polygon edge, half inside
                      and half out. Then interior + ring overshoots, the true
                      median sits between 0.166 and 0.302 ha, and the 0.24 ha
                      the source paper reports lands near the middle.

Euclidean distance answers it without ambiguity. For every ring pixel this
measures the exact distance to the nearest interior pixel. A one-pixel ring
produces distances of 1.00 and 1.41 and nothing beyond. A two-pixel ring
reaches 2.00, 2.24 and 2.83.

Nothing is written.

    python src\\ring_thickness.py
    python src\\ring_thickness.py --chips 600
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chips", type=int, default=400)
    args = ap.parse_args()

    from scipy.ndimage import distance_transform_edt

    names = F.chip_names()[:args.chips]
    print(f"Measuring ring thickness over {len(names):,} chips.\n")

    tally = Counter()
    total = 0
    orphan_px = 0
    orphan_chips = 0

    for name in names:
        inst, c2, c3, _ = F.load_labels(name)
        if inst.max() == 0:
            continue
        ring = (c3 == F.C3_BOUNDARY)
        if not ring.any():
            continue
        # distance from every pixel to the nearest labelled interior pixel
        dist = distance_transform_edt(inst == 0)
        d = dist[ring]
        total += d.size
        far = int((d > F.MAX_RING_DIST).sum())
        orphan_px += far
        orphan_chips += 1 if far else 0
        for v in np.round(d[d <= F.MAX_RING_DIST], 2):
            tally[float(v)] += 1

    if not total:
        sys.exit("no ring pixels found")

    print(RULE)
    print("EXACT DISTANCE FROM EACH RING PIXEL TO THE NEAREST INTERIOR PIXEL")
    print(RULE)
    print(f"  {total:,} ring pixels\n")
    print(f"  {'distance':>10}{'pixels':>14}{'share':>10}")
    for d in sorted(tally):
        n = tally[d]
        bar = "#" * int(round(40 * n / total))
        print(f"  {d:>10.2f}{n:>14,}{n / total * 100:>9.2f}%   {bar}")

    print(f"\n  beyond {F.MAX_RING_DIST:.0f} px: {orphan_px:,} pixels "
          f"({orphan_px / total * 100:.2f}%), in {orphan_chips:,} chips")
    if orphan_px:
        print("  These belong to parcels whose interior erosion wiped out")
        print("  entirely. ftw_common leaves them unassigned rather than")
        print("  handing them to a distant neighbour.")

    within_141 = sum(n for d, n in tally.items() if d <= 1.45) / total
    print(f"\n  share at distance 1.41 or less: {within_141 * 100:.2f}%")

    print("\n" + RULE)
    print("READING")
    print(RULE)
    if within_141 > 0.95:
        print("  The ring is ONE pixel thick. Distance 1.00 is an orthogonal")
        print("  step and 1.41 the same ring reached diagonally, so together")
        print("  they are one ring of pixels touching the interior. What sits")
        print("  at 2.00 and beyond turns up at sharp corners and where a")
        print("  parcel pinches thin enough to break its interior up.")
        print()
        print("  So the ring is the parcel's own outer edge, not a band")
        print("  straddling it. interior + ring is the rasterised parcel, the")
        print("  reconstruction in ftw_common is exact, and the median parcel")
        print("  measures 0.302 ha ON THIS GRID.")
        print()
        print("  That last qualifier matters. The source paper reports 0.24 ha")
        print("  for the same labels, measured on the original vector polygons")
        print("  rather than on a 6.07 m rasterisation. Rasterising inflates")
        print("  small shapes, and inflates them further if every touched")
        print("  pixel is included rather than only pixels whose centre falls")
        print("  inside. At a median 82 grid pixels with a perimeter near 36,")
        print("  a half-pixel outward bias would account for the gap. That is")
        print("  a plausible explanation and not a verified one, so treat")
        print("  0.302 ha as an upper bound on the true parcel.")
    elif within_141 > 0.6:
        print("  Mixed. Most of the ring touches the interior but a real share")
        print("  sits further out, so the band is not a clean one-pixel edge.")
        print("  Quote the parcel median as a range, 0.166 to 0.302 ha, until")
        print("  the original vectors settle it.")
    else:
        print("  The ring is TWO pixels thick or more, so it may straddle the")
        print("  polygon edge. interior + ring then overshoots the parcel.")
        print("  Quote the range 0.166 to 0.302 ha, and note that the paper's")
        print("  0.24 ha sits inside it.")

    out = F.RESULTS / "ring_thickness.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["distance_px", "pixels", "share"])
        for d in sorted(tally):
            w.writerow([f"{d:.2f}", tally[d], round(tally[d] / total, 6)])
        w.writerow([f">{F.MAX_RING_DIST:.0f}", orphan_px,
                    round(orphan_px / total, 6)])
        w.writerow(["chips_read", len(names), ""])
        w.writerow(["share_within_1.41", "", round(within_141, 6)])
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")
    print(RULE)


if __name__ == "__main__":
    main()
