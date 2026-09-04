"""
RS-01 / step 4 — build the water mask one decision at a time, and measure each.

Round 2. Round 1 produced recall 0.80-0.88 with precision 0.23-0.28: the masks
were finding the water and then calling a great deal of land water as well. The
cause is structural, not a coding error:

    Otsu assumes two comparable populations. Across these chips water is about
    10% of valid pixels, and many individual chips contain almost none. Given a
    histogram with one mode, Otsu still returns a threshold — it splits the land
    distribution down the middle. A chip with no water then comes back roughly
    half "water", and precision collapses.

The authors' baseline avoids this by estimating its threshold at SCENE scale,
where water is well represented, and applying it to the chips. Sen1Floods11
even records the value it used for this event: VH <= -21.56 dB.

So round 2 adds three variants that attack the threshold rather than the
filtering:

    v6_event_thresh   the published per-event VH threshold, applied directly
    v7_gated          tiled Otsu that REFUSES to guess: a tile counts only if
                      its histogram is bimodal and its dark mode is physically
                      plausible for water; if no tile qualifies, the chip is
                      declared dry instead of falling back to a global Otsu
    v8_gated_full     v7 + VV agreement + morphological cleanup

Round 1's variants stay in the table. A failed idea that you measured and kept
in the record is worth more than a clean table that hides the attempt.

Outputs:
    results/ablation_chips.csv        every variant x split
    results/chip_diagnostics.csv      per-chip thresholds and water fractions
    results/figures/variant_comparison.png

Usage:
    python src\\mask_chips.py
    python src\\mask_chips.py --tile 256
    python src\\mask_chips.py --variants v6_event_thresh v7_gated v8_gated_full
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                        # noqa: E402
    EVENT, LABELS_DIR, RESULTS, OTSU_TILE, SPECKLE_WINDOW,
    EVENT_VH_THRESHOLD, MAX_WATER_THRESHOLD_VH, MAX_WATER_THRESHOLD_VV,
)
import metrics as M                         # noqa: E402

FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
SPLITS_DIR = LABELS_DIR / "splits"

# Shared chip I/O and SAR helpers now live in chips.py so that scripts which
# do not plot need not import matplotlib. Re-exported here so existing imports
# (`from mask_chips import lee_filter, read, ...`) keep working.
from chips import (                                       # noqa: E402
    ASHMAN_MIN, MIN_CLASS_FRAC, MIN_HOLE_PX, MIN_OBJECT_PX,
    ashman_d, chip_ids, global_otsu, lee_filter, morph_clean, read,
    split_lookup, tiled_otsu,
)

# ---------------------------------------------------------------- variants
VARIANTS = [
    "v0_otsu_vv", "v1_otsu_vh", "v2_lee_vh", "v3_tiled_vh",
    "v4_dual_pol", "v5_morph",
    "v6_event_thresh", "v7_gated", "v8_gated_full",
]


def predict(variant: str, vv: np.ndarray, vh: np.ndarray,
            tile: int) -> tuple[np.ndarray, dict]:
    """Return (mask int8: 1 water / 0 land / -1 nodata, info dict)."""
    nodata = ~(np.isfinite(vv) & np.isfinite(vh))
    info = {"threshold": None, "tiles_accepted": 0, "tiles_examined": 0}

    if variant == "v0_otsu_vv":
        band, t = vv, global_otsu(vv)
    elif variant == "v1_otsu_vh":
        band, t = vh, global_otsu(vh)
    elif variant == "v2_lee_vh":
        band = lee_filter(vh); t = global_otsu(band)
    elif variant in ("v3_tiled_vh", "v4_dual_pol", "v5_morph"):
        band = lee_filter(vh)
        t, acc, exm = tiled_otsu(band, tile, gated=False,
                                 max_threshold=MAX_WATER_THRESHOLD_VH)
        info.update(tiles_accepted=acc, tiles_examined=exm)
    elif variant == "v6_event_thresh":
        band, t = lee_filter(vh), EVENT_VH_THRESHOLD
    elif variant in ("v7_gated", "v8_gated_full"):
        band = lee_filter(vh)
        t, acc, exm = tiled_otsu(band, tile, gated=True,
                                 max_threshold=MAX_WATER_THRESHOLD_VH)
        info.update(tiles_accepted=acc, tiles_examined=exm)
    else:
        raise ValueError(variant)

    info["threshold"] = t
    if t is None:
        # no plausible water threshold -> the chip is dry. Saying so is a
        # result; guessing a threshold anyway is what wrecked round 1.
        return np.where(nodata, -1, 0).astype(np.int8), info

    mask = (band <= t).astype(np.int8)

    if variant in ("v4_dual_pol", "v5_morph", "v8_gated_full"):
        vv_f = lee_filter(vv)
        gated = variant == "v8_gated_full"
        t_vv, _, _ = tiled_otsu(vv_f, tile, gated=gated,
                                max_threshold=MAX_WATER_THRESHOLD_VV)
        if t_vv is not None:
            mask &= (vv_f <= t_vv).astype(np.int8)
        elif gated:
            mask[:] = 0

    if variant in ("v5_morph", "v8_gated_full"):
        mask = morph_clean(mask)

    return np.where(nodata, -1, mask).astype(np.int8), info


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile", type=int, default=128,
                    help=f"adaptive Otsu tile size (config value for full "
                         f"scenes is {OTSU_TILE})")
    ap.add_argument("--variants", nargs="+", default=VARIANTS, choices=VARIANTS)
    ap.add_argument("--figure-chip", default=None)
    args = ap.parse_args()

    ids = chip_ids()
    if not ids:
        raise SystemExit("No chips found. Run fetch_labels.py --download first.")
    splits = split_lookup()
    print(f"{len(ids)} chips, tile size {args.tile}\n")

    data = {}
    for chip_id in ids:
        s1 = read("S1Hand", chip_id).astype("float64")
        data[chip_id] = (s1[0], s1[1], read("LabelHand", chip_id)[0],
                         read("S1OtsuLabelHand", chip_id)[0])

    results: dict[str, dict[str, list[dict]]] = {}
    diagnostics: list[dict] = []

    for variant in args.variants:
        by_split: dict[str, list[dict]] = {}
        for chip_id in ids:
            vv, vh, label, _ = data[chip_id]
            pred, info = predict(variant, vv, vh, args.tile)
            c = M.confusion(pred, label)
            by_split.setdefault(splits.get(chip_id, "unknown"), []).append(c)

            valid = label != -1
            diagnostics.append({
                "variant": variant,
                "chip_id": chip_id,
                "split": splits.get(chip_id, "unknown"),
                "threshold": "" if info["threshold"] is None else f"{info['threshold']:.2f}",
                "tiles_accepted": info["tiles_accepted"],
                "tiles_examined": info["tiles_examined"],
                "truth_water_frac": f"{np.mean(label[valid] == 1):.4f}",
                "pred_water_frac": f"{np.mean(pred[valid] == 1):.4f}",
                "iou": f"{M.scores(c)['iou']:.4f}",
            })
        results[variant] = by_split
        allc = [c for v in by_split.values() for c in v]
        print(M.format_row(variant + " [all]", M.aggregate(allc)))

    base: dict[str, list[dict]] = {}
    for chip_id in ids:
        _, _, label, otsu = data[chip_id]
        base.setdefault(splits.get(chip_id, "unknown"), []).append(
            M.confusion(otsu, label))
    results["baseline_authors_otsu"] = base

    print("\nBY SPLIT (micro IoU)")
    print(f"{'variant':<24}{'train':>10}{'valid':>10}{'test':>10}{'all':>10}")
    for variant, by_split in results.items():
        line = f"{variant:<24}"
        for split in ("train", "valid", "test"):
            line += (f"{M.aggregate(by_split[split])['iou']:>10.3f}"
                     if split in by_split else f"{'-':>10}")
        allc = [c for v in by_split.values() for c in v]
        line += f"{M.aggregate(allc)['iou']:>10.3f}"
        print(line)

    with open(RESULTS / "ablation_chips.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "split", "n_chips", "tp", "fp", "fn", "tn",
                    "iou", "precision", "recall", "f1",
                    "macro_iou", "macro_recall", "n_chips_no_prediction"])
        for variant, by_split in results.items():
            groups = list(sorted(by_split.items()))
            groups.append(("all", [c for v in by_split.values() for c in v]))
            for split, confs in groups:
                a, mac = M.aggregate(confs), M.macro(confs)
                w.writerow([variant, split, len(confs), a["tp"], a["fp"], a["fn"],
                            a["tn"], f"{a['iou']:.4f}", f"{a['precision']:.4f}",
                            f"{a['recall']:.4f}", f"{a['f1']:.4f}",
                            f"{mac['iou']:.4f}", f"{mac['recall']:.4f}",
                            mac.get("n_chips_no_prediction", 0)])

    with open(RESULTS / "chip_diagnostics.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(diagnostics[0]))
        w.writeheader()
        w.writerows(diagnostics)

    # where is precision lost? chips whose truth is dry but prediction is wet
    print("\nDRY-CHIP BEHAVIOUR (truth water < 1% of valid pixels)")
    print(f"{'variant':<24}{'n dry chips':>13}{'mean pred water %':>20}")
    for variant in args.variants:
        rows = [d for d in diagnostics
                if d["variant"] == variant and float(d["truth_water_frac"]) < 0.01]
        if rows:
            mean_pred = np.mean([float(d["pred_water_frac"]) for d in rows]) * 100
            print(f"{variant:<24}{len(rows):>13}{mean_pred:>20.1f}")

    print("\nwrote ablation_chips.csv, chip_diagnostics.csv")

    # ------------------------------------------------------------- figure
    test_ids = [c for c in ids if splits.get(c) == "test"] or ids
    chip_id = args.figure_chip or max(test_ids,
                                      key=lambda c: int(np.sum(data[c][2] == 1)))
    vv, vh, label, otsu = data[chip_id]
    panels = [(vh, "VH (dB)", "gray"), (label, "hand label", "Blues"),
              (otsu, "authors' Otsu", "Blues")]
    panels += [(predict(v, vv, vh, args.tile)[0], v, "Blues") for v in args.variants]

    cols = 4
    rows_n = int(np.ceil(len(panels) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(3.4 * cols, 3.7 * rows_n))
    axes = np.atleast_1d(axes).ravel()

    for ax, (img, title, cmap) in zip(axes, panels):
        img = np.asarray(img, dtype=float).copy()
        if cmap == "Blues":
            scored = img.astype(int)
            img[img == -1] = np.nan
            ax.imshow(img, cmap=cmap, vmin=0, vmax=1)
            if title != "hand label":
                s = M.evaluate(scored, label)
                title = f"{title}\nIoU {s['iou']:.3f}  P {s['precision']:.2f}  R {s['recall']:.2f}"
        else:
            finite = img[np.isfinite(img)]
            ax.imshow(img, cmap=cmap, vmin=np.percentile(finite, 2),
                      vmax=np.percentile(finite, 98))
        ax.set_title(title, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes[len(panels):]:
        ax.axis("off")

    fig.suptitle(f"{EVENT} chip {chip_id} ({splits.get(chip_id, '?')}) — variants")
    fig.tight_layout()
    fig.savefig(FIGURES / "variant_comparison.png", dpi=130)
    print(f"wrote figures/variant_comparison.png (chip {chip_id})")


if __name__ == "__main__":
    main()
