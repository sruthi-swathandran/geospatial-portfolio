"""
RS-01 / step 10c - is the gap the product, or the estimation window?

WHERE THIS CAME FROM
--------------------
Step 10b swept the pooled VH threshold on RTC gamma0 and found the published
S1OtsuLabelHand baseline sitting 0.040 of precision ABOVE the curve at matched
recall (0.820 against 0.780 at recall 0.60). I had predicted the published point
would land on the curve. It did not.

But that comparison moves two things at once:

  PRODUCT. The baseline was built on the Sen1Floods11 S1Hand chips, which come
  from Google Earth Engine sigma0. Ours are Planetary Computer RTC gamma0.
  Step 8 measured 4.83 dB of water-to-land contrast in the GEE chips against
  4.20 dB in RTC, about 13% less separation. Less separation moves a
  precision-recall curve down on its own.

  ESTIMATION WINDOW. Their threshold is Otsu on a whole scene. Ours is one
  number pooled across 65 chips. Step 5 already showed the window matters:
  per-chip Otsu scored 0.515 on test against 0.699 pooled, because a 512 by 512
  chip with little water has no second mode for Otsu to find. A full scene has
  plenty of water and adapts to local radiometry at the same time.

Both are plausible and they have different consequences. If it is the product,
the finding is about what moving off Earth Engine costs, which is worth knowing
for anyone doing the same migration. If it is the window, the fix is to estimate
per scene in the full-scene run, and this project can just do that.

The S1Hand chips are already on disk, so both curves can be swept on the same
65 chips against the same labels with the same speckle filter. The vertical
distance from the RTC curve to the GEE curve is the product cost. The distance
from the GEE curve to the published star is the window cost.

The raw GEE curve is swept too, without the Lee filter, since the published
baseline did not speckle filter and that is one more difference worth pricing
rather than assuming away.

Outputs:
    results/product_vs_window.csv
    results/figures/product_vs_window.png

Usage:
    python src\\product_vs_window.py
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
import rasterio                             # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS     # noqa: E402
from chips import read, split_lookup, lee_filter    # noqa: E402
import metrics as M                         # noqa: E402

REF_DIR = DATA / "reference"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

PIXEL_HA = 0.01
PRODUCTS = ("rtc_lee", "gee_lee", "gee_raw")
STYLE = {"rtc_lee": ("#2b6f8f", "-", "RTC gamma0, Lee 5x5"),
         "gee_lee": ("#2f8f4f", "-", "GEE sigma0 (S1Hand), Lee 5x5"),
         "gee_raw": ("#2f8f4f", "--", "GEE sigma0 (S1Hand), no filter")}


def usable_chips() -> list[str]:
    path = RESULTS / "usable_chips.txt"
    if path.exists():
        ids = [c.strip() for c in path.read_text().split() if c.strip()]
        if ids:
            return ids
    return sorted(p.name.split("_")[1]
                  for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))


def load_chip(chip_id: str):
    with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif") as s:
        rtc = s.read(2).astype("float64")
    gee = read("S1Hand", chip_id)[1].astype("float64")
    gee[~np.isfinite(gee)] = np.nan
    gee[gee < -50] = np.nan          # S1Hand marks no-data with a large negative
    return {"rtc_lee": lee_filter(rtc).astype("float32"),
            "gee_lee": lee_filter(gee).astype("float32"),
            "gee_raw": gee.astype("float32")}, read("LabelHand", chip_id)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmin", type=float, default=-28.0)
    ap.add_argument("--tmax", type=float, default=-10.0)
    ap.add_argument("--step", type=float, default=0.25)
    args = ap.parse_args()

    ids = usable_chips()
    splits = split_lookup()

    bands, labels, t0 = {}, {}, time.time()
    for n, chip_id in enumerate(ids, 1):
        try:
            bands[chip_id], labels[chip_id] = load_chip(chip_id)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  skipping {chip_id}: {exc}")
        print(f"\r  loading {n}/{len(ids)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    ids = [c for c in ids if c in bands]
    print(f"{len(ids)} chips\n")

    truth_ha = sum(float(np.sum(labels[c] == 1)) * PIXEL_HA for c in ids)

    # ------------------------------------------- 1. class separation first
    print("1. HOW SEPARABLE IS WATER FROM LAND IN EACH PRODUCT?")
    print("----------------------------------------------------")
    print(f"  {'product':<32}{'water dB':>10}{'land dB':>10}"
          f"{'contrast':>10}{'pooled sd':>11}{'d-prime':>9}")
    for prod in PRODUCTS:
        w, l = [], []
        for chip_id in ids:
            a = bands[chip_id][prod]
            lab = labels[chip_id]
            ok = np.isfinite(a) & (lab != -1)
            w.append(a[ok & (lab == 1)][::5])
            l.append(a[ok & (lab == 0)][::5])
        w = np.concatenate(w); l = np.concatenate(l)
        contrast = float(l.mean() - w.mean())
        pooled_sd = float(np.sqrt((w.var() + l.var()) / 2.0))
        print(f"  {STYLE[prod][2]:<32}{w.mean():>10.2f}{l.mean():>10.2f}"
              f"{contrast:>10.2f}{pooled_sd:>11.2f}"
              f"{contrast / pooled_sd:>9.2f}")
    print("\n  d-prime is contrast divided by the pooled spread, which is what\n"
          "  actually limits a threshold. Two products can share a contrast and\n"
          "  separate differently if one is noisier.")

    # ---------------------------------------------------- 2. sweep them all
    thresholds = np.round(np.arange(args.tmin, args.tmax + 1e-9, args.step), 2)
    curves = {}
    for prod in PRODUCTS:
        rows = []
        for t in thresholds:
            by_split, area = {}, 0.0
            for chip_id in ids:
                a = bands[chip_id][prod]
                nodata = ~np.isfinite(a)
                pred = np.where(nodata, -1, (a <= t).astype(np.int8)
                                ).astype(np.int8)
                by_split.setdefault(splits.get(chip_id, "unknown"),
                                    []).append(M.confusion(pred, labels[chip_id]))
                area += M.mapped_area_px(pred, labels[chip_id]) * PIXEL_HA
            agg = M.aggregate([c for v in by_split.values() for c in v])
            row = {"product": prod, "threshold": float(t),
                   "iou_all": round(agg["iou"], 4),
                   "p_all": round(agg["precision"], 4),
                   "r_all": round(agg["recall"], 4),
                   "area_ha": round(area, 1)}
            for split, confs in by_split.items():
                row[f"iou_{split}"] = round(M.aggregate(confs)["iou"], 4)
            rows.append(row)
        curves[prod] = rows
        print(f"\r  swept {prod} ({time.time()-t0:.0f}s)", end="", flush=True)
    print()

    # the published baseline on exactly these chips
    base = {}
    base_area = 0.0
    for chip_id in ids:
        otsu = read("S1OtsuLabelHand", chip_id)[0]
        base.setdefault(splits.get(chip_id, "unknown"), []).append(
            M.confusion(otsu, labels[chip_id]))
        base_area += M.mapped_area_px(otsu, labels[chip_id]) * PIXEL_HA
    b = M.aggregate([c for v in base.values() for c in v])

    print("\n2. PRECISION AT THE PUBLISHED BASELINE'S RECALL")
    print("-----------------------------------------------")
    print(f"  published S1OtsuLabelHand   P {b['precision']:.3f}  "
          f"R {b['recall']:.3f}  IoU {b['iou']:.3f}  "
          f"area {base_area:,.0f} ha\n")
    print(f"  {'product':<32}{'thresh':>8}{'P':>8}{'R':>8}{'IoU':>8}"
          f"{'gap to published':>19}")
    at_recall = {}
    for prod in PRODUCTS:
        near = min(curves[prod], key=lambda r: abs(r["r_all"] - b["recall"]))
        at_recall[prod] = near
        print(f"  {STYLE[prod][2]:<32}{near['threshold']:>8.2f}"
              f"{near['p_all']:>8.3f}{near['r_all']:>8.3f}"
              f"{near['iou_all']:>8.3f}"
              f"{b['precision'] - near['p_all']:>+19.3f}")

    prod_cost = at_recall["gee_lee"]["p_all"] - at_recall["rtc_lee"]["p_all"]
    window_cost = b["precision"] - at_recall["gee_lee"]["p_all"]
    total = b["precision"] - at_recall["rtc_lee"]["p_all"]
    print("\n  DECOMPOSITION OF THE PRECISION GAP (at matched recall)")
    print(f"    moving RTC -> GEE product, same method   {prod_cost:+.3f}")
    print(f"    moving pooled -> per-scene estimation    {window_cost:+.3f}")
    print(f"    total gap to the published baseline      {total:+.3f}")
    if abs(prod_cost) > abs(window_cost):
        print("\n  The product explains more of it. The cost is in the "
              "radiometry of the\n  cloud-native RTC stack, not in how the "
              "threshold was estimated, and\n  per-scene estimation in the "
              "full-scene run will not recover it.")
    elif abs(window_cost) > abs(prod_cost):
        print("\n  The estimation window explains more of it. Per-scene Otsu in "
              "the\n  full-scene run should close most of the gap, which is worth "
              "doing\n  since the full scene is exactly where that becomes "
              "possible.")
    else:
        print("\n  The two contribute about equally.")

    print("\n3. BEST EACH PRODUCT CAN DO (threshold chosen on valid)")
    print("-------------------------------------------------------")
    print(f"  {'product':<32}{'thresh':>8}{'valid':>8}{'test':>8}{'all':>8}"
          f"{'P':>7}{'R':>7}{'area ha':>10}")
    for prod in PRODUCTS:
        scored = [r for r in curves[prod] if "iou_valid" in r]
        bst = max(scored, key=lambda r: r["iou_valid"])
        print(f"  {STYLE[prod][2]:<32}{bst['threshold']:>8.2f}"
              f"{bst['iou_valid']:>8.3f}{bst.get('iou_test', float('nan')):>8.3f}"
              f"{bst['iou_all']:>8.3f}{bst['p_all']:>7.3f}{bst['r_all']:>7.3f}"
              f"{bst['area_ha']:>10,.0f}")
    print(f"  {'published S1OtsuLabelHand':<32}{'-':>8}"
          f"{M.aggregate(base['valid'])['iou'] if 'valid' in base else float('nan'):>8.3f}"
          f"{M.aggregate(base['test'])['iou'] if 'test' in base else float('nan'):>8.3f}"
          f"{b['iou']:>8.3f}{b['precision']:>7.3f}{b['recall']:>7.3f}"
          f"{base_area:>10,.0f}")
    print(f"  {'hand-labelled truth':<32}{'':>46}{truth_ha:>10,.0f}")

    # ------------------------------------------------------------ outputs
    fields = ["product", "threshold", "iou_train", "iou_valid", "iou_test",
              "iou_all", "p_all", "r_all", "area_ha"]
    with open(RESULTS / "product_vs_window.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for prod in PRODUCTS:
            w.writerows(curves[prod])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    ax = axes[0]
    for prod in PRODUCTS:
        color, ls, label = STYLE[prod]
        ax.plot([r["r_all"] for r in curves[prod]],
                [r["p_all"] for r in curves[prod]],
                color=color, linestyle=ls, linewidth=1.8, label=label)
    ax.scatter([b["recall"]], [b["precision"]], marker="*", s=280,
               color="#b03030", zorder=5, label="published, per-scene Otsu")
    ax.axvline(b["recall"], color="black", linewidth=0.6, linestyle=":")
    ax.set_xlabel("recall"); ax.set_ylabel("precision")
    ax.set_xlim(0.3, 1.0)
    ax.set_title("Product cost and estimation-window cost")
    ax.grid(alpha=0.25); ax.legend(fontsize=8, loc="lower left")

    ax = axes[1]
    for prod in PRODUCTS:
        color, ls, label = STYLE[prod]
        w_, l_ = [], []
        for chip_id in ids[:20]:
            a = bands[chip_id][prod]
            lab = labels[chip_id]
            ok = np.isfinite(a) & (lab != -1)
            w_.append(a[ok & (lab == 1)][::11])
            l_.append(a[ok & (lab == 0)][::11])
        ax.hist(np.concatenate(w_), bins=120, range=(-32, -2), density=True,
                histtype="step", color=color, linestyle=ls, linewidth=1.5)
        ax.hist(np.concatenate(l_), bins=120, range=(-32, -2), density=True,
                histtype="step", color=color, linestyle=ls, linewidth=0.8,
                alpha=0.6)
    ax.set_xlabel("VH (dB)"); ax.set_ylabel("density")
    ax.set_title("water (thick) against land (thin), first 20 chips")
    ax.grid(alpha=0.25)

    fig.suptitle(f"{EVENT}: what does leaving Earth Engine actually cost?")
    fig.tight_layout()
    fig.savefig(FIGURES / "product_vs_window.png", dpi=130)

    print("\nwrote product_vs_window.csv and figures/product_vs_window.png")


if __name__ == "__main__":
    main()
