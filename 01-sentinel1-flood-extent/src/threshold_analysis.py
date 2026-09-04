"""
RS-01 / step 5 — how much of this problem is the threshold, and where is the ceiling?

The ablation says something specific: gating the threshold moved precision from
0.28 to 0.90, and the remaining loss is recall. Before writing more code it is
worth answering three questions with the data itself.

  1. WHAT DOES THE SEPARATION ACTUALLY LOOK LIKE?
     Plot VH for hand-labelled water pixels against VH for land pixels. The
     overlap between those two distributions is a hard ceiling on any method
     that thresholds VH. If they overlap by 20%, no threshold — adaptive,
     tiled, gated, or divinely inspired — gets past it, and the way forward is
     a different feature, not a better threshold.

  2. WHERE IS THE BEST SINGLE THRESHOLD, AND HOW SHARP IS THE OPTIMUM?
     Sweep VH from -30 to -10 dB, score every value on the VALID split only,
     and plot IoU against threshold. A flat optimum means the exact value
     hardly matters and the published -21.56 dB is fine. A sharp one means
     per-event calibration is essential — which is itself a finding about
     operational deployment.

  3. DOES THE SCALE OF ESTIMATION MATTER MORE THAN THE METHOD?
     Compare three thresholds computed with no labels at all: Otsu per chip
     (what failed), Otsu on all chips pooled (scene-like), and the published
     per-event value. If pooling fixes most of the gap, the lesson is that
     Otsu was never the problem — the window you showed it was.

Reported honestly: the swept threshold USES the valid labels, so it is a tuned
number and only its TEST score is quotable. The pooled and published
thresholds use no labels and are directly comparable to the baseline.

Outputs:
    results/threshold_sweep.csv
    results/figures/class_separation.png
    results/figures/threshold_sweep.png

Usage:
    python src\\threshold_analysis.py
    python src\\threshold_analysis.py --no-filter     # skip the Lee filter
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
from config import EVENT, LABELS_DIR, RESULTS, EVENT_VH_THRESHOLD   # noqa: E402
import metrics as M                                                 # noqa: E402
from mask_chips import lee_filter, read, chip_ids, split_lookup     # noqa: E402

FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)


def load_pixels(use_filter: bool):
    """Return {split: (vh_values, labels)} plus per-chip Otsu thresholds."""
    ids = chip_ids()
    splits = split_lookup()
    by_split: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    per_chip_thresholds = []

    for chip_id in ids:
        s1 = read("S1Hand", chip_id).astype("float64")
        vh = lee_filter(s1[1]) if use_filter else s1[1]
        label = read("LabelHand", chip_id)[0]

        keep = np.isfinite(vh) & (label != -1)
        by_split.setdefault(splits.get(chip_id, "unknown"), []).append(
            (vh[keep], label[keep]))

        vals = vh[np.isfinite(vh)]
        if vals.size > 100:
            per_chip_thresholds.append(float(threshold_otsu(vals)))

    out = {}
    for split, parts in by_split.items():
        out[split] = (np.concatenate([p[0] for p in parts]),
                      np.concatenate([p[1] for p in parts]))
    return out, np.array(per_chip_thresholds)


def score_threshold(vh: np.ndarray, label: np.ndarray, t: float) -> dict:
    pred = (vh <= t)
    truth = (label == 1)
    tp = int(np.sum(pred & truth))
    fp = int(np.sum(pred & ~truth))
    fn = int(np.sum(~pred & truth))
    tn = int(np.sum(~pred & ~truth))
    return M.scores({"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                     "n_valid": tp + fp + fn + tn, "n_ignored": 0})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-filter", action="store_true")
    ap.add_argument("--lo", type=float, default=-30.0)
    ap.add_argument("--hi", type=float, default=-10.0)
    ap.add_argument("--step", type=float, default=0.25)
    args = ap.parse_args()

    use_filter = not args.no_filter
    print(f"loading pixels (Lee filter: {use_filter})")
    data, chip_thresholds = load_pixels(use_filter)

    all_vh = np.concatenate([v for v, _ in data.values()])
    all_lb = np.concatenate([l for _, l in data.values()])
    water, land = all_vh[all_lb == 1], all_vh[all_lb == 0]

    # ------------------------------------------------------- 1. separation
    print("\nCLASS SEPARATION (VH, dB)")
    print("-------------------------")
    for name, arr in (("water", water), ("land", land)):
        q = np.percentile(arr, [5, 25, 50, 75, 95])
        print(f"  {name:<6} n={arr.size:>10,}  "
              f"p5 {q[0]:6.1f}  p25 {q[1]:6.1f}  median {q[2]:6.1f}  "
              f"p75 {q[3]:6.1f}  p95 {q[4]:6.1f}")
    overlap_lo, overlap_hi = np.percentile(water, 95), np.percentile(land, 5)
    print(f"  water p95 = {overlap_lo:.1f} dB, land p5 = {overlap_hi:.1f} dB "
          f"-> {'OVERLAP' if overlap_lo > overlap_hi else 'clean gap'} "
          f"of {abs(overlap_lo - overlap_hi):.1f} dB")

    # ------------------------------------------------------ 2. sweep
    thresholds = np.arange(args.lo, args.hi + args.step, args.step)
    rows = []
    for t in thresholds:
        row = {"threshold": round(float(t), 3)}
        for split in ("valid", "test", "train"):
            if split in data:
                s = score_threshold(*data[split], t)
                row[f"{split}_iou"] = s["iou"]
                row[f"{split}_precision"] = s["precision"]
                row[f"{split}_recall"] = s["recall"]
        rows.append(row)

    best = max(rows, key=lambda r: r.get("valid_iou", 0))
    best_t = best["threshold"]

    # -------------------------------------------- 3. label-free thresholds
    pooled_t = float(threshold_otsu(all_vh[::17]))   # subsample for speed
    per_chip_median = float(np.median(chip_thresholds))

    print("\nTHRESHOLDS")
    print("----------")
    candidates = {
        "Otsu, per chip (median)": per_chip_median,
        "Otsu, all chips pooled": pooled_t,
        "published event value": EVENT_VH_THRESHOLD,
        "best on valid (tuned)": best_t,
    }
    for name, t in candidates.items():
        s_valid = score_threshold(*data["valid"], t) if "valid" in data else None
        s_test = score_threshold(*data["test"], t) if "test" in data else None
        print(f"  {name:<26} {t:7.2f} dB   "
              f"valid IoU {s_valid['iou']:.3f}   test IoU {s_test['iou']:.3f}   "
              f"(test P {s_test['precision']:.3f} R {s_test['recall']:.3f})")

    print(f"\n  per-chip Otsu spread: {chip_thresholds.min():.1f} .. "
          f"{chip_thresholds.max():.1f} dB across {chip_thresholds.size} chips "
          f"(sd {chip_thresholds.std():.1f})")
    print("  ^ that spread is the round-1 failure in one number: the same "
          "physical surface\n    got wildly different thresholds depending on "
          "which chip it sat in.")

    with open(RESULTS / "threshold_sweep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ------------------------------------------------------- figures
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.linspace(-35, 0, 160)
    ax.hist(land, bins=bins, density=True, alpha=0.55, label=f"land (n={land.size:,})",
            color="#9a8a6b")
    ax.hist(water, bins=bins, density=True, alpha=0.55,
            label=f"water (n={water.size:,})", color="#2b6f8f")
    for t, style, name in ((EVENT_VH_THRESHOLD, "-", "published -21.56"),
                           (pooled_t, "--", f"pooled Otsu {pooled_t:.2f}"),
                           (best_t, ":", f"best on valid {best_t:.2f}")):
        ax.axvline(t, color="black", linestyle=style, linewidth=1.4, label=name)
    ax.set_xlabel("VH backscatter (dB)")
    ax.set_ylabel("density")
    ax.set_title(f"{EVENT} — VH distribution of hand-labelled water vs land")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES / "class_separation.png", dpi=130)

    fig, ax = plt.subplots(figsize=(9, 5))
    for split, colour in (("valid", "#2b6f8f"), ("test", "#8f4b2b"),
                          ("train", "#6b7a45")):
        key = f"{split}_iou"
        if key in rows[0]:
            ax.plot(thresholds, [r[key] for r in rows], label=f"{split} IoU",
                    color=colour, linewidth=1.8)
    ax.axvline(best_t, color="black", linestyle=":", linewidth=1.2,
               label=f"best on valid {best_t:.2f}")
    ax.axvline(EVENT_VH_THRESHOLD, color="black", linestyle="-", linewidth=1.2,
               label="published -21.56")
    ax.set_xlabel("VH threshold (dB)")
    ax.set_ylabel("IoU (water)")
    ax.set_title(f"{EVENT} — single-threshold sensitivity")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "threshold_sweep.png", dpi=130)

    print("\nwrote threshold_sweep.csv, figures/class_separation.png, "
          "figures/threshold_sweep.png")


if __name__ == "__main__":
    main()
