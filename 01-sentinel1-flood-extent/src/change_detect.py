"""
RS-01 / step 9 - flood detection from change, against two different references.

Round 1 of this script used the 19 July reference and failed: 0.069 IoU against
0.515 for the plain single-date threshold, with recall at 0.086. The diagnostic
explained it. 45.1% of the pixels labelled water on 12 August were already below
the water threshold on 19 July, because late July in Assam is mid-monsoon. Half
the flood cannot produce a change signal against a reference that already
contains it.

So this version runs the same comparison against whichever references exist:

    REF_ALIGNED       19 July 2016, mid-monsoon, 24 days before the event
    REFDRY_ALIGNED    a pre-monsoon date on the same orbit, if fetched

Neither is correct in the abstract, and that is the point. The July reference is
seasonally similar but already wet. A pre-monsoon reference is dry but four to
six months away, so some of the measured change is crop growth rather than
water. Reporting how much the flooded-area estimate moves between them is more
useful than picking one and calling it the answer, and it is the kind of
sensitivity an insurance or relief client needs.

The final table reports predicted flooded area in hectares as well as IoU. Two
methods can score similarly and still disagree about area by a wide margin, and
area is what the client actually buys.

Outputs:
    results/change_detection.csv
    results/figures/change_detection.png

Usage:
    python src\\change_detect.py
    python src\\change_detect.py --min-drop 2.0
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import rasterio                             # noqa: E402
from skimage.filters import threshold_otsu  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                        # noqa: E402
    EVENT, DATA, RESULTS, TARGET_RES, pixel_ha,
)
from chips import read, split_lookup, lee_filter, morph_clean   # noqa: E402
import metrics as M                         # noqa: E402

REF_DIR = DATA / "reference"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

PIXEL_HA = pixel_ha(TARGET_RES)   # chips sit on the 10 m label grid
REFERENCES = {"july": "REF_ALIGNED", "dry": "REFDRY_ALIGNED"}


def usable_chips() -> list[str]:
    path = RESULTS / "usable_chips.txt"
    if path.exists():
        ids = [c.strip() for c in path.read_text().split() if c.strip()]
        if ids:
            return ids
    print("  (no usable_chips.txt, falling back to every aligned chip)")
    return sorted(p.name.split("_")[1]
                  for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))


def load_pair(path: Path):
    with rasterio.open(path) as src:
        a = src.read().astype("float64")
    return lee_filter(a[0]), lee_filter(a[1])


def load(chip_id: str, refs: list[str]):
    fl_vv, fl_vh = load_pair(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif")
    out = {"flood": (fl_vv, fl_vh), "label": read("LabelHand", chip_id)[0]}
    for name in refs:
        out[name] = load_pair(
            REF_DIR / f"{EVENT}_{chip_id}_{REFERENCES[name]}.tif")
    return out


def pooled_threshold(values, cap=None) -> float:
    v = np.concatenate([x[np.isfinite(x)][::7] for x in values])
    t = float(threshold_otsu(v))
    return t if cap is None else min(t, cap)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-drop", type=float, default=3.0)
    args = ap.parse_args()

    ids = usable_chips()
    splits = split_lookup()

    available = [name for name, suffix in REFERENCES.items()
                 if (REF_DIR / f"{EVENT}_{ids[0]}_{suffix}.tif").exists()]
    print(f"{len(ids)} co-registered chips")
    print(f"references available: {', '.join(available) if available else 'none'}\n")

    data = {}
    for chip_id in ids:
        try:
            data[chip_id] = load(chip_id, available)
        except Exception as exc:                       # noqa: BLE001
            print(f"  skipping {chip_id}: {exc}")
    ids = [c for c in ids if c in data]

    t_abs_vh = pooled_threshold([d["flood"][1] for d in data.values()])
    t_abs_vv = pooled_threshold([d["flood"][0] for d in data.values()])
    t_diff = {}
    for name in available:
        t_diff[name] = (
            pooled_threshold([d["flood"][0] - d[name][0] for d in data.values()],
                             cap=-args.min_drop),
            pooled_threshold([d["flood"][1] - d[name][1] for d in data.values()],
                             cap=-args.min_drop),
        )

    print("THRESHOLDS (label-free, pooled across chips)")
    print("--------------------------------------------")
    print(f"  absolute VH  {t_abs_vh:7.2f} dB      absolute VV  {t_abs_vv:7.2f} dB")
    for name in available:
        print(f"  change vs {name:<5} VV {t_diff[name][0]:7.2f} dB   "
              f"VH {t_diff[name][1]:7.2f} dB   (capped at {-args.min_drop:.1f})")

    def predict(variant, d):
        fl_vv, fl_vh = d["flood"]
        nodata = ~(np.isfinite(fl_vh) & np.isfinite(fl_vv))
        if variant == "c0_abs_pooled":
            mask = fl_vh <= t_abs_vh
            return np.where(nodata, -1, mask.astype(np.int8)).astype(np.int8)

        kind, name = variant.rsplit("_", 1)
        rf_vv, rf_vh = d[name]
        nodata |= ~(np.isfinite(rf_vh) & np.isfinite(rf_vv))
        d_vh = fl_vh - rf_vh
        t_vv, t_vh = t_diff[name]
        if kind == "c1_diff":
            mask = d_vh <= t_vh
        elif kind == "c2_diff_and_abs":
            mask = (d_vh <= t_vh) & (fl_vh <= t_abs_vh)
        elif kind == "c3_full":
            d_vv = fl_vv - rf_vv
            mask = ((d_vh <= t_vh) & (fl_vh <= t_abs_vh)
                    & (d_vv <= t_vv) & (fl_vv <= t_abs_vv))
            mask = morph_clean(mask.astype(np.int8)).astype(bool)
        else:
            raise ValueError(variant)
        return np.where(nodata, -1, mask.astype(np.int8)).astype(np.int8)

    variants = ["c0_abs_pooled"]
    for name in available:
        variants += [f"c1_diff_{name}", f"c2_diff_and_abs_{name}",
                     f"c3_full_{name}"]

    results, areas = {}, {}
    for variant in variants:
        by_split, area = {}, 0.0
        for chip_id in ids:
            d = data[chip_id]
            pred = predict(variant, d)
            by_split.setdefault(splits.get(chip_id, "unknown"), []).append(
                M.confusion(pred, d["label"]))
            area += M.mapped_area_px(pred, d["label"]) * PIXEL_HA
        results[variant] = by_split
        areas[variant] = area

    base, base_area = {}, 0.0
    for chip_id in ids:
        d = data[chip_id]
        otsu = read("S1OtsuLabelHand", chip_id)[0]
        base.setdefault(splits.get(chip_id, "unknown"), []).append(
            M.confusion(otsu, d["label"]))
        base_area += M.mapped_area_px(otsu, d["label"]) * PIXEL_HA
    results["baseline_same_chips"] = base
    areas["baseline_same_chips"] = base_area

    truth_area = sum(float(np.sum(data[c]["label"] == 1)) * PIXEL_HA for c in ids)

    print("\nRESULTS (micro, on the co-registered subset)")
    print("--------------------------------------------")
    print(f"{'variant':<26}{'train':>8}{'valid':>8}{'test':>8}{'all':>8}"
          f"{'P':>7}{'R':>7}{'area ha':>10}{'vs truth':>10}")
    for variant, by_split in results.items():
        line = f"{variant:<26}"
        for split in ("train", "valid", "test"):
            line += (f"{M.aggregate(by_split[split])['iou']:>8.3f}"
                     if split in by_split else f"{'-':>8}")
        a = M.aggregate([c for v in by_split.values() for c in v])
        ha = areas[variant]
        line += (f"{a['iou']:>8.3f}{a['precision']:>7.3f}{a['recall']:>7.3f}"
                 f"{ha:>10.0f}{ha / truth_area - 1:>+9.0%}")
        print(line)
    print(f"{'hand-labelled truth':<26}{'':>32}{'':>14}{truth_area:>10.0f}"
          f"{'':>10}")

    with open(RESULTS / "change_detection.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "split", "n_chips", "tp", "fp", "fn", "tn",
                    "iou", "precision", "recall", "f1", "area_ha_all",
                    "area_error_vs_truth"])
        for variant, by_split in results.items():
            groups = sorted(by_split.items())
            groups.append(("all", [c for v in by_split.values() for c in v]))
            for split, confs in groups:
                a = M.aggregate(confs)
                w.writerow([variant, split, len(confs), a["tp"], a["fp"],
                            a["fn"], a["tn"], f"{a['iou']:.4f}",
                            f"{a['precision']:.4f}", f"{a['recall']:.4f}",
                            f"{a['f1']:.4f}",
                            f"{areas[variant]:.1f}" if split == "all" else "",
                            f"{areas[variant]/truth_area-1:.4f}"
                            if split == "all" else ""])

    print("\nHOW WET WAS EACH REFERENCE?")
    print("---------------------------")
    for name in available:
        frac = []
        for chip_id in ids:
            d = data[chip_id]
            w = (d["label"] == 1) & np.isfinite(d[name][1])
            if w.sum() > 500:
                frac.append(float(np.mean(d[name][1][w] <= t_abs_vh)))
        if frac:
            print(f"  {name:<6} {np.median(frac):.1%} of labelled water was "
                  f"already below the water threshold")
    print("  Water present on both dates produces no change signal. This number "
          "is the\n  ceiling on what change detection can recover, and it is a "
          "property of the\n  reference date rather than of the method.")

    # ------------------------------------------------------------- figure
    test_ids = [c for c in ids if splits.get(c) == "test"] or ids
    chip_id = max(test_ids, key=lambda c: int(np.sum(data[c]["label"] == 1)))
    d = data[chip_id]
    panels = [(d["flood"][1], "flood VH, 12 Aug", "gray", None)]
    for name in available:
        panels.append((d[name][1], f"reference VH, {name}", "gray", None))
        panels.append((d["flood"][1] - d[name][1], f"change vs {name}",
                       "RdBu", (-8, 8)))
    panels.append((d["label"].astype(float), "hand label", "Blues", (0, 1)))
    panels += [(predict(v, d).astype(float), v, "Blues", (0, 1))
               for v in variants]

    from matplotlib.colors import ListedColormap
    C_LAND, C_WATER = "#EDEAE3", "#1B5E8C"
    C_INK, C_MUTED, C_RULE = "#16222B", "#5C6B76", "#C9D2D8"
    binary = ListedColormap([C_LAND, C_WATER])

    # Fewest empty cells in the last row. With two references there are 13
    # panels, which at four columns left one panel alone beside three gaps.
    cols = min((4, 5, 6), key=lambda c: ((-len(panels)) % c, c))
    rows_n = int(np.ceil(len(panels) / cols))

    # A constrained layout with the header and footer as real axes. tight_layout
    # cannot see figure-level text, and with aspect-locked images it leaves the
    # lower rows' titles sitting on the images above them.
    fig = plt.figure(figsize=(3.3 * cols, 3.5 * rows_n + 1.7),
                     layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, hspace=0.0, wspace=0.0)
    outer = fig.add_gridspec(3, 1, height_ratios=[0.66, 3.5 * rows_n, 1.04])
    hax = fig.add_subplot(outer[0])
    hax.set_axis_off()
    fax = fig.add_subplot(outer[2])
    fax.set_axis_off()
    grid = outer[1].subgridspec(rows_n, cols, wspace=0.05, hspace=0.14)

    for k, (img, title, cmap, lim) in enumerate(panels):
        ax = fig.add_subplot(grid[k // cols, k % cols])
        img = np.array(img, dtype=float)
        if cmap == "Blues":
            img[img == -1] = np.nan
            ax.imshow(img, cmap=binary, vmin=0, vmax=1,
                      interpolation="nearest")
        elif lim:
            ax.imshow(img, cmap=cmap, vmin=lim[0], vmax=lim[1],
                      interpolation="nearest")
        else:
            f = img[np.isfinite(img)]
            ax.imshow(img, cmap=cmap, vmin=np.percentile(f, 2),
                      vmax=np.percentile(f, 98), interpolation="nearest")
        if title in variants:
            s = M.evaluate(predict(title, d), d["label"])
            title = (f"{title}\nIoU {s['iou']:.3f}   R {s['recall']:.2f}")
        ax.set_title(title, fontsize=9, color=C_INK, loc="left", pad=4,
                     linespacing=1.35)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor(C_RULE)
            sp.set_linewidth(0.7)

    hax.text(0, 1.0, f"One date against change, {EVENT} chip {chip_id}",
             fontsize=14, fontweight="bold", color=C_INK, va="top", ha="left",
             transform=hax.transAxes)
    hax.text(0, 0.0, f"{len(available)} reference date(s). In the mask panels "
             f"dark is water and pale is not. In the change panels red is a "
             f"drop in backscatter and blue is a rise.",
             fontsize=9.8, color=C_MUTED, va="bottom", ha="left",
             transform=hax.transAxes)

    fax.text(0, 1.0,
             "c0 is the plain single-date threshold, here so the change "
             "variants have something to be measured against. c1 uses the drop "
             "alone. c2 requires\nthe drop and darkness on the flood date. c3 "
             "adds VV agreement and morphological cleanup. Against the July "
             "reference every change variant\ncollapses, because a large "
             "share of the labelled water was already below the water "
             "threshold on that date and can produce no change signal.\nThe "
             "pre-monsoon reference recovers more and still falls well short "
             "of thresholding a single date, which is why change detection is "
             "not in the pipeline.",
             fontsize=8.4, color=C_MUTED, va="top", ha="left",
             transform=fax.transAxes, linespacing=1.62)

    fig.savefig(FIGURES / "change_detection.png", dpi=200,
                facecolor="white", bbox_inches="tight")
    print(f"\nwrote change_detection.csv and figures/change_detection.png "
          f"(chip {chip_id})")


if __name__ == "__main__":
    main()
