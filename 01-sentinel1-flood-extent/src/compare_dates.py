"""
RS-01 / step 11e - what five days did, and what a mosaic would have hidden.

Two refined maps now exist on the same grid, from the same code, with the same
threshold, slope cut and edge buffer:

    12 August 2016, relative orbit 77   the event date, central and lower valley
     7 August 2016, relative orbit  4   five days earlier, upper valley

They were deliberately not mosaicked. This script says what that decision was
worth, by splitting the ground into three parts and refusing to add them
together.

    OVERLAP     seen by both passes. Flood here can be compared date to date,
                and the disagreement is what a seamless-looking mosaic would
                have quietly averaged away.

    WEDGE       seen only on 7 August. Real flood, real hectares, wrong date
                for the event. Reportable on its own and never added to the
                12 August total.

    ORBIT 77    seen only on 12 August. The existing headline figure.

The number that matters most is persistence: of the flood mapped on 12 August
inside the overlap, how much was already there on 7 August. High persistence
means the two dates describe one slowly-changing state and a mosaic would have
been nearly harmless. Low persistence means the flood moved substantially in
five days, and any single map stitched from two dates is a chimera.

WHAT THIS IS NOT
----------------
It is not a validation. Neither date has hand labels outside the Sen1Floods11
chips, so disagreement between the two maps cannot be attributed to one of them
being wrong. It measures how much the answer depends on which day you ask,
which is the same question the reference date and the permanent water cut
already raised, asked a third way.

Outputs:
    results/date_comparison.csv
    results/figures/date_comparison.png

Usage:
    python src\\compare_dates.py --res 20 --other 20160807
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import rasterio                             # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from rasterio.windows import Window         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                         # noqa: E402
    EVENT, RESULTS, FLOOD_DATE, TILE_PX, pixel_ha,
)

OUT_DIR = RESULTS / "fullscene"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

TILE = TILE_PX
LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--base", default="",
                    help="variant tag of the FIRST acquisition; empty means "
                         "the event-date map with no variant suffix")
    ap.add_argument("--base-date", default="")
    ap.add_argument("--other", default="20160807",
                    help="variant tag of the second acquisition")
    ap.add_argument("--other-date", default="2016-08-07")
    ap.add_argument("--out", default="date_comparison",
                    help="stem for the csv and figure, so one pair does not "
                         "overwrite another")
    args = ap.parse_args()

    res = args.res
    px_ha = pixel_ha(res)
    base_date = args.base_date or FLOOD_DATE
    a_sfx = f"_{args.base}" if args.base else ""
    a_tif = OUT_DIR / f"{EVENT}_water_{res:g}m{a_sfx}_refined.tif"
    b_tif = OUT_DIR / f"{EVENT}_water_{res:g}m_{args.other}_refined.tif"
    other_date = args.other_date
    # A is always the EARLIER acquisition. Without this the temporal labels
    # invert whenever the pair is given in the other order, and the script
    # reports a receding flood as filling.
    if base_date > other_date:
        a_tif, b_tif = b_tif, a_tif
        base_date, other_date = other_date, base_date
    gap = (dt.date.fromisoformat(other_date)
           - dt.date.fromisoformat(base_date)).days
    print(f"earlier  {base_date}  {a_tif.name}")
    print(f"later    {other_date}  {b_tif.name}")
    print(f"{gap} days apart\n")
    for t in (a_tif, b_tif):
        if not t.exists():
            raise SystemExit(f"{t} not found")

    with rasterio.open(a_tif) as sa, rasterio.open(b_tif) as sb:
        if (sa.width, sa.height) != (sb.width, sb.height):
            raise SystemExit("the two maps are on different grids")
        h, w = sa.height, sa.width

    keys = [(y0, min(y0 + TILE, h), x0, min(x0 + TILE, w))
            for y0 in range(0, h, TILE) for x0 in range(0, w, TILE)]

    # counters, all in pixels
    c = dict(overlap=0, ov_both=0, ov_a_only=0, ov_b_only=0,
             a_only_area=0, a_only_flood=0,
             b_only_area=0, b_only_flood=0,
             ov_perm_a=0, ov_perm_b=0)

    small = np.zeros((max(1, h // 24), max(1, w // 24)), "uint8")
    t0 = time.time()
    for n, (y0, y1, x0, x1) in enumerate(keys, 1):
        win = Window(x0, y0, x1 - x0, y1 - y0)
        with rasterio.open(a_tif) as sa:
            A = sa.read(1, window=win)
        with rasterio.open(b_tif) as sb:
            B = sb.read(1, window=win)

        va, vb = A != NODATA, B != NODATA
        fa, fb = A == FLOOD, B == FLOOD
        ov = va & vb

        c["overlap"] += int(ov.sum())
        c["ov_both"] += int((ov & fa & fb).sum())
        c["ov_a_only"] += int((ov & fa & ~fb).sum())
        c["ov_b_only"] += int((ov & fb & ~fa).sum())
        c["ov_perm_a"] += int((ov & (A == PERMANENT)).sum())
        c["ov_perm_b"] += int((ov & (B == PERMANENT)).sum())
        c["a_only_area"] += int((va & ~vb).sum())
        c["a_only_flood"] += int((fa & ~vb).sum())
        c["b_only_area"] += int((vb & ~va).sum())
        c["b_only_flood"] += int((fb & ~va).sum())

        # 1 both, 2 only 12 Aug, 3 only 7 Aug, 4 overlap dry, 5 outside overlap
        code = np.zeros(A.shape, "uint8")
        code[va | vb] = 5
        code[ov] = 4
        code[ov & fa & fb] = 1
        code[ov & fa & ~fb] = 2
        code[ov & fb & ~fa] = 3
        code[(va & ~vb) & fa] = 2
        code[(vb & ~va) & fb] = 3
        sy = slice(y0 // 24, min(y1 // 24, small.shape[0]))
        sx = slice(x0 // 24, min(x1 // 24, small.shape[1]))
        blk = code[::24, ::24]
        small[sy, sx] = blk[:sy.stop - sy.start, :sx.stop - sx.start]
        print(f"\r  {n}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    ha = lambda k: c[k] * px_ha                             # noqa: E731
    a_ov_flood = c["ov_both"] + c["ov_a_only"]
    b_ov_flood = c["ov_both"] + c["ov_b_only"]
    union = c["ov_both"] + c["ov_a_only"] + c["ov_b_only"]

    print("\n1. GROUND EACH PASS SAW")
    print("-----------------------")
    print(f"  {'seen by both':<30}{ha('overlap'):>12,.0f} ha")
    print(f"  {'only ' + base_date:<30}{ha('a_only_area'):>12,.0f} ha")
    print(f"  {'only ' + other_date:<30}{ha('b_only_area'):>12,.0f} ha")
    print(f"  {'combined':<30}"
          f"{(c['overlap']+c['a_only_area']+c['b_only_area'])*px_ha:>12,.0f} ha")

    drained, appeared = c["ov_a_only"], c["ov_b_only"]
    print(f"\n2. INSIDE THE OVERLAP, WHAT DID {gap} DAYS DO?")
    print("-" + "-" * (32 + len(str(gap))))
    print(f"  flood on {base_date:<14}{a_ov_flood*px_ha:>12,.0f} ha")
    print(f"  flood on {other_date:<14}{b_ov_flood*px_ha:>12,.0f} ha")
    print(f"  {'wet on both dates':<23}{ha('ov_both'):>12,.0f} ha")
    print(f"  {'drained by ' + other_date:<23}{drained*px_ha:>12,.0f} ha")
    print(f"  {'newly flooded by ' + other_date:<23}{appeared*px_ha:>12,.0f} ha")

    persist = c["ov_both"] / max(a_ov_flood, 1)
    iou = c["ov_both"] / max(union, 1)
    ratio = b_ov_flood / max(a_ov_flood, 1)
    print(f"\n  persistence: {persist:.1%} of the {base_date} flood was still "
          f"wet on {other_date}")
    print(f"  agreement between the two dates: IoU {iou:.3f}")
    print(f"  net change: the overlap went to {ratio:.1%} of its {base_date} "
          f"extent")
    if drained and appeared:
        big, small_ = max(drained, appeared), min(drained, appeared)
        direction = "receding" if drained > appeared else "filling"
        print(f"  direction: {direction}, {big/max(small_,1):.1f} to 1")

    # Direction is the better signal than persistence on its own. Water that
    # recedes in place keeps a high persistence and a falling IoU, and reading
    # only the IoU makes recession look like disagreement between the maps.
    lop = max(drained, appeared) / max(min(drained, appeared), 1)
    if lop > 3 and drained > appeared:
        print("\n  Change is one-directional recession. The two maps agree "
              "about WHERE the\n  water is and differ in HOW MUCH, which is "
              "hydrology rather than method\n  noise, and the falling IoU "
              "reflects the shrinking rather than disagreement.")
    elif lop > 3:
        print("\n  Change is one-directional filling. Water is spreading into "
              "ground that\n  was dry on the earlier date rather than moving "
              "about.")
    elif iou > 0.8:
        print("\n  The two dates describe nearly the same state, so a mosaic "
              "would have been\n  close to harmless. Worth saying, since it is "
              "the case where the careful\n  choice turned out not to matter.")
    else:
        print("\n  Gains and losses are comparable, so the footprint moved "
              "rather than simply\n  growing or shrinking. That is the hardest "
              "case for any single-date map.")

    # What a mosaic would cost, in BOTH directions. Filling the event-date map
    # with an earlier wedge is the operationally interesting one, but the
    # reverse is equally real and costs nothing to state.
    pairs = [(base_date, c["a_only_flood"], other_date, ratio),
             (other_date, c["b_only_flood"], base_date, 1.0 / max(ratio, 1e-6))]
    if any(w * px_ha > 500 for _, w, _, _ in pairs):
        print("\n  WHAT A MOSAIC WOULD COST, EITHER DIRECTION")
        for name, wedge_px, onto, scale in pairs:
            w_ha = wedge_px * px_ha
            if w_ha <= 500:
                continue
            scaled = w_ha * scale
            print(f"    the {name} wedge holds {w_ha:>10,.0f} ha; grafted onto "
                  f"the {onto} map")
            print(f"      the overlap's own change puts it nearer "
                  f"{scaled:>10,.0f} ha on that date,")
            print(f"      so the mosaic would be off by  {w_ha - scaled:>+10,.0f}"
                  f" ha")
        print("    The scaling assumes each wedge changed at the same rate as "
              "the overlap.\n    That is an assumption rather than a "
              "measurement, since a wedge is a\n    different part of the "
              "basin. It gives the order of magnitude.")
    else:
        print("\n  Both passes cover essentially the same ground, so there is "
              "no wedge to\n  mosaic and nothing here to get wrong. That is "
              "what makes this pair the\n  clean measurement: same orbit, same "
              "footprint, same viewing geometry, and\n  the only variable left "
              "is water.")

    print("\n3. GROUND ONLY ONE PASS SAW")
    print("---------------------------")
    print(f"  only {base_date} saw    {ha('a_only_area'):>12,.0f} ha, "
          f"holding {ha('a_only_flood'):,.0f} ha of flood")
    print(f"  only {other_date} saw    {ha('b_only_area'):>12,.0f} ha, "
          f"holding {ha('b_only_flood'):,.0f} ha of flood")
    print(f"\n  These two flood figures are never added. One is {base_date}, "
          f"the other is\n  {other_date}, and a single number combining them "
          "would describe no date.")

    with open(RESULTS / f"{args.out}.csv", "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["quantity", "hectares"])
        for k, label in (("overlap", "seen_by_both"),
                         ("a_only_area", f"seen_only_{base_date}"),
                         ("b_only_area", f"seen_only_{other_date}"),
                         ("ov_both", "overlap_flood_both_dates"),
                         ("ov_a_only", f"overlap_drained_by_{other_date}"),
                         ("ov_b_only", f"overlap_new_by_{other_date}"),
                         ("a_only_flood", f"wedge_flood_{base_date}"),
                         ("b_only_flood", f"wedge_flood_{other_date}")):
            w_.writerow([label, round(c[k] * px_ha, 1)])
        w_.writerow(["persistence_fraction", round(persist, 4)])
        w_.writerow(["date_to_date_iou", round(iou, 4)])

    cmap = ListedColormap(["#ffffff", "#0d3b66", "#3fa7d6", "#e08e45",
                           "#eef3f6", "#f7f9fa"])
    fig, ax = plt.subplots(figsize=(7.5, 7.5 * small.shape[0] / small.shape[1]))
    ax.imshow(small, cmap=cmap, vmin=-0.5, vmax=5.5, interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=9,
                          color=c_, label=l_)
               for c_, l_ in (("#0d3b66", "flood on both dates"),
                              ("#3fa7d6", f"flood {base_date} only"),
                              ("#e08e45", f"flood {other_date} only"),
                              ("#eef3f6", "seen by both, dry"),
                              ("#f7f9fa", "seen by one pass"))]
    ax.legend(handles=handles, fontsize=8, loc="lower left", framealpha=.95)
    ax.set_title(f"{EVENT}: two acquisitions, five days apart\n"
                 f"persistence {persist:.0%}, IoU {iou:.2f} in the overlap",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / f"{args.out}.png", dpi=140)
    print(f"\nwrote {args.out}.csv and figures/{args.out}.png")


if __name__ == "__main__":
    main()
