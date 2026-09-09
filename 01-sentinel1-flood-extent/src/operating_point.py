"""
RS-01 / step 10b - pick the operating point, and close the precision question.

THE QUESTION
------------
The pooled single-date threshold scores precision 0.652 and recall 0.710.
The published S1OtsuLabelHand baseline scores 0.820 and 0.601. Almost the same
IoU (0.515 against 0.531) reached from opposite directions.

Two explanations, and they call for different responses.

  SAME CURVE, DIFFERENT POINT. Their threshold is simply stricter. Nothing is
  wrong with the detector, and the difference is a choice about whether to miss
  water or invent it. Nothing to fix.

  BETTER SEPARATION. Their per-scene threshold estimation genuinely separates
  water from land better than one pooled threshold does, and their whole
  precision-recall curve sits above ours. Then there IS something to fix.

Sweeping the threshold and plotting precision against recall distinguishes them
in one run. If the published point lands ON our curve, the first explanation
holds. If it sits above and to the right of it, the second does.

THE OTHER THING THIS DECIDES
----------------------------
Maximum IoU and correct total area are different operating points, and the
project needs both stated. A map user wants the pixels right. A relief or
insurance user wants the hectares right, and will accept a blurrier map to get
them. This script reports the threshold that maximises IoU on valid, and
separately the threshold at which predicted area matches the hand-labelled
total, then writes both into results/final_method.json for the full-scene run
to read.

Everything here follows what steps 9 and 10 established: no change detection, no
slope mask, permanent water removed only to report flood extent and never to
compute a score.

Outputs:
    results/operating_point.csv
    results/final_method.json
    results/figures/operating_point.png

Usage:
    python src\\operating_point.py
"""

from __future__ import annotations

import argparse
import csv
import json
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
GSW_DIR = DATA / "gsw"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

PIXEL_HA = 0.01
OCCURRENCE_CUT = 50          # settled in step 10: 95% of this area is labelled water


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
        fl_vh = lee_filter(s.read(2).astype("float64")).astype("float32")
    gsw = GSW_DIR / f"{EVENT}_{chip_id}_GSW.tif"
    occ = None
    if gsw.exists():
        with rasterio.open(gsw) as s:
            occ = s.read(1).astype("float32")
    return fl_vh, occ, read("LabelHand", chip_id)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmin", type=float, default=-24.0)
    ap.add_argument("--tmax", type=float, default=-12.0)
    ap.add_argument("--step", type=float, default=0.25)
    args = ap.parse_args()

    ids = usable_chips()
    splits = split_lookup()

    data, t0 = {}, time.time()
    for n, chip_id in enumerate(ids, 1):
        try:
            data[chip_id] = load_chip(chip_id)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  skipping {chip_id}: {exc}")
        print(f"\r  loading {n}/{len(ids)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    ids = [c for c in ids if c in data]
    print(f"{len(ids)} chips\n")

    truth_ha = sum(float(np.sum(data[c][2] == 1)) * PIXEL_HA for c in ids)

    thresholds = np.round(np.arange(args.tmin, args.tmax + 1e-9, args.step), 2)
    rows = []
    for t in thresholds:
        by_split, area, area_all, flood_ha = {}, 0.0, 0.0, 0.0
        for chip_id in ids:
            fl_vh, occ, label = data[chip_id]
            nodata = ~np.isfinite(fl_vh)
            water = fl_vh <= t
            pred = np.where(nodata, -1, water.astype(np.int8)).astype(np.int8)
            by_split.setdefault(splits.get(chip_id, "unknown"),
                                []).append(M.confusion(pred, label))
            area += M.mapped_area_px(pred, label) * PIXEL_HA
            area_all += float(np.sum(pred == 1)) * PIXEL_HA
            if occ is not None:
                perm = np.isfinite(occ) & (occ >= OCCURRENCE_CUT)
                flood_ha += float(np.sum(water & ~nodata & ~perm)) * PIXEL_HA
        a = M.aggregate([c for v in by_split.values() for c in v])
        row = {"threshold": float(t), "iou_all": round(a["iou"], 4),
               "p_all": round(a["precision"], 4),
               "r_all": round(a["recall"], 4), "f1_all": round(a["f1"], 4),
               "area_ha": round(area, 1),
               "area_ha_all_pixels": round(area_all, 1),
               "flood_only_ha": round(flood_ha, 1),
               "area_err": round(area / truth_ha - 1, 4)}
        for split, confs in by_split.items():
            row[f"iou_{split}"] = round(M.aggregate(confs)["iou"], 4)
        rows.append(row)

    # the published baseline, on exactly these chips
    base = {}
    base_area = 0.0
    for chip_id in ids:
        otsu = read("S1OtsuLabelHand", chip_id)[0]
        base.setdefault(splits.get(chip_id, "unknown"), []).append(
            M.confusion(otsu, data[chip_id][2]))
        base_area += M.mapped_area_px(otsu, data[chip_id][2]) * PIXEL_HA
    b = M.aggregate([c for v in base.values() for c in v])

    scored = [r for r in rows if "iou_valid" in r]
    best_iou = max(scored, key=lambda r: r["iou_valid"])
    best_area = min(rows, key=lambda r: abs(r["area_err"]))

    print("1. IS THE PUBLISHED BASELINE ON OUR CURVE, OR ABOVE IT?")
    print("-------------------------------------------------------")
    print(f"  published S1OtsuLabelHand: P {b['precision']:.3f}  "
          f"R {b['recall']:.3f}  IoU {b['iou']:.3f}  area {base_area:,.0f} ha")

    # find our threshold with the closest recall, and compare precision there
    near = min(rows, key=lambda r: abs(r["r_all"] - b["recall"]))
    gap = b["precision"] - near["p_all"]
    print(f"  our curve at the same recall ({near['r_all']:.3f}, threshold "
          f"{near['threshold']:.2f} dB):\n"
          f"                             P {near['p_all']:.3f}  "
          f"R {near['r_all']:.3f}  IoU {near['iou_all']:.3f}  "
          f"area {near['area_ha']:,.0f} ha")
    print(f"  precision gap at matched recall: {gap:+.3f}")
    if abs(gap) < 0.03:
        print("\n  The published point sits on our curve. Their higher precision "
              "is a\n  stricter threshold, not a better detector. Nothing to fix, "
              "and the\n  operating point becomes a stated choice rather than an "
              "accident.")
    elif gap > 0:
        print("\n  The published point sits ABOVE our curve, so their per-scene "
              "threshold\n  estimation separates water from land better than one "
              "pooled threshold.\n  That is a real gap and it is worth naming in "
              "the README.")
    else:
        print("\n  Our curve sits above the published point at matched recall.")

    print("\n2. TWO OPERATING POINTS, BOTH DEFENSIBLE")
    print("----------------------------------------")
    print(f"  {'choice':<26}{'thresh':>8}{'valid':>8}{'test':>8}{'all':>8}"
          f"{'P':>7}{'R':>7}{'area ha':>10}{'vs truth':>10}")
    for name, r in (("max IoU on valid", best_iou),
                    ("area matches truth", best_area)):
        print(f"  {name:<26}{r['threshold']:>8.2f}"
              f"{r.get('iou_valid', float('nan')):>8.3f}"
              f"{r.get('iou_test', float('nan')):>8.3f}"
              f"{r['iou_all']:>8.3f}{r['p_all']:>7.3f}{r['r_all']:>7.3f}"
              f"{r['area_ha']:>10,.0f}{r['area_err']:>+9.0%}")
    print(f"  {'hand-labelled truth':<26}{'':>46}{truth_ha:>10,.0f}")
    print("\n  These are different products. A map user wants the first. Someone\n"
          "  buying a hectare figure wants the second. Publishing one without\n"
          "  saying which is how a flood map ends up quoted for a purpose it was\n"
          "  never tuned for.")

    print("\n3. FLOOD EXTENT AT THE CHOSEN POINT")
    print("-----------------------------------")
    for name, r in (("max IoU on valid", best_iou),
                    ("area matches truth", best_area)):
        print(f"  {name:<22} water {r['area_ha']:>9,.0f} ha   "
              f"flood only {r['flood_only_ha']:>9,.0f} ha   "
              f"(permanent water = occurrence >= {OCCURRENCE_CUT}%)")

    # ------------------------------------------------------------ outputs
    fields = ["threshold", "iou_train", "iou_valid", "iou_test", "iou_all",
              "p_all", "r_all", "f1_all", "area_ha", "flood_only_ha",
              "area_err"]
    with open(RESULTS / "operating_point.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    chosen = {
        "event": EVENT,
        "method": "single-date pooled Otsu on RTC gamma0 VH, Lee 5x5",
        "polarisation": "VH",
        "speckle_filter": "Lee 5x5 on linear power",
        "slope_mask": None,
        "slope_mask_reason": "swept 2 to 20 degrees in step 10; removed true "
                             "water faster than shadow, precision +0.008 for "
                             "recall -0.003",
        "change_detection": None,
        "change_detection_reason": "step 9c; best change threshold was the one "
                                   "that made the constraint inert, and the "
                                   "change signal alone scored IoU 0.147 "
                                   "against 0.130 for labelling the whole "
                                   "scene as water",
        "permanent_water": {"source": "JRC Global Surface Water occurrence",
                            "cut_percent": OCCURRENCE_CUT,
                            "note": "used only to report flood extent, never "
                                    "in a score, because the hand labels mark "
                                    "permanent water as water"},
        "operating_points": {
            "max_iou": {k: best_iou.get(k) for k in
                        ("threshold", "iou_valid", "iou_test", "iou_all",
                         "p_all", "r_all", "area_ha", "flood_only_ha",
                         "area_err")},
            "area_matched": {k: best_area.get(k) for k in
                             ("threshold", "iou_valid", "iou_test", "iou_all",
                              "p_all", "r_all", "area_ha", "flood_only_ha",
                              "area_err")},
        },
        "published_baseline_same_chips": {
            "precision": round(b["precision"], 4),
            "recall": round(b["recall"], 4),
            "iou": round(b["iou"], 4),
            "area_ha": round(base_area, 1),
        },
        "truth_area_ha": round(truth_ha, 1),
        "n_chips": len(ids),
    }
    (RESULTS / "final_method.json").write_text(json.dumps(chosen, indent=2))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    ax = axes[0]
    ax.plot([r["r_all"] for r in rows], [r["p_all"] for r in rows],
            color="#2b6f8f", linewidth=1.8, label="pooled threshold, swept")
    ax.scatter([b["recall"]], [b["precision"]], marker="*", s=260,
               color="#b03030", zorder=5, label="published S1OtsuLabelHand")
    ax.scatter([best_iou["r_all"]], [best_iou["p_all"]], marker="o", s=70,
               color="black", zorder=5, label="max IoU on valid")
    ax.scatter([best_area["r_all"]], [best_area["p_all"]], marker="s", s=70,
               facecolor="none", edgecolor="black", zorder=5,
               label="area matches truth")
    ax.set_xlabel("recall"); ax.set_ylabel("precision")
    ax.set_title("Is the published baseline on our curve?")
    ax.grid(alpha=0.25); ax.legend(fontsize=8, loc="lower left")

    ax = axes[1]
    t = [r["threshold"] for r in rows]
    ax.plot(t, [r["area_ha"] for r in rows], color="#2b6f8f",
            label="water extent")
    ax.plot(t, [r["flood_only_ha"] for r in rows], color="#2b6f8f",
            linestyle="--", label=f"flood only (occ < {OCCURRENCE_CUT}%)")
    ax.axhline(truth_ha, color="#b03030", linestyle=":",
               label="hand-labelled water")
    ax.axvline(best_iou["threshold"], color="black", linewidth=0.8)
    ax.set_xlabel("VH threshold (dB)"); ax.set_ylabel("hectares")
    ax.set_title("How much does the hectare figure move?")
    ax.grid(alpha=0.25); ax.legend(fontsize=8)

    fig.suptitle(f"{EVENT}: choosing an operating point on {len(ids)} chips")
    fig.tight_layout()
    fig.savefig(FIGURES / "operating_point.png", dpi=130)

    print("\nwrote operating_point.csv, final_method.json and "
          "figures/operating_point.png")


if __name__ == "__main__":
    main()
