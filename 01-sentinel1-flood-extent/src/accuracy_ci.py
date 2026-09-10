"""
RS-01 / provenance - accuracy with intervals, and an honest scope statement.

Review findings addressed:

  F-03  every accuracy figure in this project was a single number with no
        confidence interval, micro-averaged over 65 chips of very unequal water
        content, which weights by pixel count and hides chip-level variance.

  F-01  more seriously: these figures describe the CHIP-SCALE product. The
        reported 119,779 ha comes from a raster that additionally passed
        through a slope mask, a swath-edge buffer and a minimum mapping unit,
        none of which existed when these numbers were computed and none of
        which can be validated, because the Sen1Floods11 labels cover 65
        floodplain chips and none of those situations occurs in them.

        Nothing in this script fixes that. It states it, prints it, and writes
        it into the output, so the distinction cannot be lost downstream.

  F-07  the Sen1Floods11 splits for a single event are spatially adjacent chips
        from one scene. Train, valid and test share radiometry, terrain and
        flood state. The test split checks that the threshold was not fitted to
        the valid split. It is not evidence of transferability to another
        event, another sensor or another basin, and this script does not report
        it as such.

What it produces: a confusion matrix in the conventional form, producer and
user accuracy per class, overall accuracy, quantity and allocation disagreement
(Pontius and Millones 2011) in place of kappa, and percentile bootstrap
intervals resampled over CHIPS rather than pixels. Chips are the independent
unit here; pixels inside a chip are strongly autocorrelated and bootstrapping
over them would give intervals far too narrow.

Outputs:
    results/accuracy_ci.csv
    results/figures/accuracy_ci.png

Usage:
    python src\\accuracy_ci.py
    python src\\accuracy_ci.py --boot 5000
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import rasterio                             # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS, TARGET_RES, pixel_ha   # noqa: E402
from chips import read, split_lookup, lee_filter                # noqa: E402
import metrics as M                                             # noqa: E402

REF_DIR = DATA / "reference"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
PIXEL_HA = pixel_ha(TARGET_RES)


def usable_chips() -> list[str]:
    path = RESULTS / "usable_chips.txt"
    if path.exists():
        ids = [c.strip() for c in path.read_text().split() if c.strip()]
        if ids:
            return ids
    return sorted(p.name.split("_")[1]
                  for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))


def chosen_threshold() -> tuple[float, str]:
    p = RESULTS / "final_method.json"
    if not p.exists():
        raise SystemExit("results/final_method.json not found. "
                         "Run operating_point.py first.")
    d = json.loads(p.read_text())
    return (float(d["operating_points"]["max_iou"]["threshold"]),
            "max IoU on the valid split")


def scores(tp, fp, fn, tn):
    n = tp + fp + fn + tn
    return {
        "n": n,
        "iou": tp / max(tp + fp + fn, 1),
        "precision": tp / max(tp + fp, 1),          # user accuracy, water
        "recall": tp / max(tp + fn, 1),             # producer accuracy, water
        "f1": 2 * tp / max(2 * tp + fp + fn, 1),
        "oa": (tp + tn) / max(n, 1),
        "ua_land": tn / max(tn + fn, 1),
        "pa_land": tn / max(tn + fp, 1),
        # Pontius and Millones 2011, binary case: total disagreement splits
        # into a quantity part and an allocation part, and unlike kappa neither
        # is compared against a chance baseline nobody believes in.
        "quantity_disagreement": abs(fp - fn) / max(n, 1),
        "allocation_disagreement": 2 * min(fp, fn) / max(n, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20160812,
                    help="fixed so the intervals are reproducible")
    args = ap.parse_args()

    thr, why = chosen_threshold()
    ids = usable_chips()
    splits = split_lookup()
    print(f"{len(ids)} chips, threshold {thr:.2f} dB ({why})\n")

    per_chip = []
    for chip_id in ids:
        path = REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif"
        if not path.exists():
            continue
        with rasterio.open(path) as s:
            vh = lee_filter(s.read(2).astype("float64"))
        label = read("LabelHand", chip_id)[0]
        pred = np.where(~np.isfinite(vh), -1,
                        (vh <= thr).astype(np.int8)).astype(np.int8)
        c = M.confusion(pred, label)
        per_chip.append({"chip_id": chip_id,
                         "split": splits.get(chip_id, "unknown"),
                         "tp": c["tp"], "fp": c["fp"],
                         "fn": c["fn"], "tn": c["tn"]})
    if not per_chip:
        raise SystemExit("no chips loaded")

    def pooled(rows):
        return scores(sum(r["tp"] for r in rows), sum(r["fp"] for r in rows),
                      sum(r["fn"] for r in rows), sum(r["tn"] for r in rows))

    rng = np.random.default_rng(args.seed)

    def boot(rows, key):
        if len(rows) < 3:
            return (float("nan"), float("nan"))
        idx = rng.integers(0, len(rows), size=(args.boot, len(rows)))
        vals = np.empty(args.boot)
        arr = np.array([[r["tp"], r["fp"], r["fn"], r["tn"]] for r in rows],
                       dtype=np.int64)
        for b in range(args.boot):
            tp, fp, fn, tn = arr[idx[b]].sum(axis=0)
            vals[b] = scores(tp, fp, fn, tn)[key]
        return tuple(np.percentile(vals, [2.5, 97.5]))

    print("CONFUSION MATRIX, all chips, no-data excluded")
    print("---------------------------------------------")
    a = pooled(per_chip)
    tp = sum(r["tp"] for r in per_chip); fp = sum(r["fp"] for r in per_chip)
    fn = sum(r["fn"] for r in per_chip); tn = sum(r["tn"] for r in per_chip)
    print(f"  {'':<16}{'ref water':>14}{'ref land':>14}{'user acc':>11}")
    print(f"  {'map water':<16}{tp:>14,}{fp:>14,}{a['precision']:>11.3f}")
    print(f"  {'map land':<16}{fn:>14,}{tn:>14,}{a['ua_land']:>11.3f}")
    print(f"  {'producer acc':<16}{a['recall']:>14.3f}{a['pa_land']:>14.3f}")
    print(f"\n  overall accuracy         {a['oa']:.4f}")
    print(f"  quantity disagreement    {a['quantity_disagreement']:.4f}")
    print(f"  allocation disagreement  {a['allocation_disagreement']:.4f}")
    print("  (Pontius and Millones 2011, reported instead of kappa)")

    print("\nWITH 95% BOOTSTRAP INTERVALS, RESAMPLED OVER CHIPS")
    print("--------------------------------------------------")
    print(f"  {'split':<10}{'chips':>7}{'IoU':>9}{'95% CI':>18}"
          f"{'precision':>11}{'recall':>9}")
    out_rows = []
    groups = [("all", per_chip)] + [
        (sp, [r for r in per_chip if r["split"] == sp])
        for sp in ("train", "valid", "test")]
    for name, rows in groups:
        if not rows:
            continue
        sc = pooled(rows)
        # Macro weights every chip equally rather than by pixel count. It was
        # printed below and never stored, so the 0.280 quoted in README.md and
        # on the public page had no file behind it.
        macro_split = np.array(
            [scores(r["tp"], r["fp"], r["fn"], r["tn"])["iou"] for r in rows])
        lo, hi = boot(rows, "iou")
        plo, phi = boot(rows, "precision")
        rlo, rhi = boot(rows, "recall")
        print(f"  {name:<10}{len(rows):>7}{sc['iou']:>9.3f}"
              f"{f'[{lo:.3f}, {hi:.3f}]':>18}"
              f"{sc['precision']:>11.3f}{sc['recall']:>9.3f}")
        out_rows.append({
            "split": name, "chips": len(rows), "iou": round(sc["iou"], 4),
            "iou_ci_lo": round(lo, 4), "iou_ci_hi": round(hi, 4),
            "precision": round(sc["precision"], 4),
            "precision_ci_lo": round(plo, 4), "precision_ci_hi": round(phi, 4),
            "recall": round(sc["recall"], 4),
            "recall_ci_lo": round(rlo, 4), "recall_ci_hi": round(rhi, 4),
            "overall_accuracy": round(sc["oa"], 4),
            "quantity_disagreement": round(sc["quantity_disagreement"], 4),
            "allocation_disagreement": round(sc["allocation_disagreement"], 4),
            "macro_iou": round(float(np.nanmean(macro_split)), 4),
            "macro_iou_sd": round(float(np.nanstd(macro_split)), 4),
            "macro_iou_min": round(float(np.nanmin(macro_split)), 4),
        })

    macro = np.array([scores(r["tp"], r["fp"], r["fn"], r["tn"])["iou"]
                      for r in per_chip])
    print(f"\n  micro IoU {a['iou']:.3f}   macro IoU "
          f"{np.nanmean(macro):.3f} (sd {np.nanstd(macro):.3f}, "
          f"min {np.nanmin(macro):.3f}, max {np.nanmax(macro):.3f})")
    print("  Micro weights by pixel count, so chips with a lot of water "
          "dominate it.\n  Macro weights every chip equally and is the harsher "
          "of the two here.")

    truth_ha = sum((r["tp"] + r["fn"]) for r in per_chip) * PIXEL_HA
    map_ha = sum((r["tp"] + r["fp"]) for r in per_chip) * PIXEL_HA
    print("\nAREA, CHIP SCALE")
    print("----------------")
    print(f"  hand-labelled water      {truth_ha:>12,.0f} ha")
    print(f"  mapped water             {map_ha:>12,.0f} ha  "
          f"({map_ha/max(truth_ha,1)-1:+.1%})")
    print("  This is a map pixel count, not a design-based estimate. With "
          f"recall\n  {a['recall']:.3f} the map omits water and with precision "
          f"{a['precision']:.3f} it adds some, and\n  the two partly cancel. "
          "The cancellation is a property of this threshold on\n  these chips "
          "and should not be assumed to hold over the full scene.")

    print("\nSCOPE OF THESE NUMBERS")
    print("----------------------")
    print("  They describe the single-date threshold applied to 65 "
          "co-registered\n  chips at 10 m. They do NOT describe the reported "
          "full-scene product,\n  which additionally passes through a slope "
          "mask, a 600 m swath-edge\n  buffer and a 10-pixel minimum mapping "
          "unit that together remove 45% of\n  the raw area. No labelled data "
          "exists for those steps, so the reported\n  119,779 ha carries no "
          "validated accuracy of any kind.")
    print("\n  The test split is adjacent chips from the same scene. It checks "
          "that the\n  threshold was not fitted to the valid split. It is not "
          "evidence of\n  transfer to another event, sensor or basin.")

    with open(RESULTS / "accuracy_ci.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        w.writeheader(); w.writerows(out_rows)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    names = [r["split"] for r in out_rows]
    y = np.arange(len(names))
    ax.errorbar([r["iou"] for r in out_rows], y,
                xerr=[[r["iou"] - r["iou_ci_lo"] for r in out_rows],
                      [r["iou_ci_hi"] - r["iou"] for r in out_rows]],
                fmt="o", color="#2b6f8f", capsize=4)
    ax.set_yticks(y); ax.set_yticklabels(names)
    ax.set_xlabel("IoU"); ax.grid(alpha=.25, axis="x")
    ax.set_title("IoU with 95% bootstrap CI, resampled over chips", fontsize=10)

    ax = axes[1]
    ax.hist(macro, bins=20, color="#2b6f8f", alpha=.8)
    ax.axvline(a["iou"], color="#b03030", linestyle="--",
               label=f"micro {a['iou']:.3f}")
    ax.axvline(np.nanmean(macro), color="black", linestyle=":",
               label=f"macro mean {np.nanmean(macro):.3f}")
    ax.set_xlabel("per-chip IoU"); ax.set_ylabel("chips")
    ax.set_title("Chip-level variance the single figure hides", fontsize=10)
    ax.legend(fontsize=8); ax.grid(alpha=.25)
    fig.suptitle(f"{EVENT}: chip-scale accuracy at {thr:.2f} dB "
                 f"({len(per_chip)} chips)")
    fig.tight_layout()
    fig.savefig(FIGURES / "accuracy_ci.png", dpi=130)
    print("\nwrote accuracy_ci.csv and figures/accuracy_ci.png")


if __name__ == "__main__":
    main()
