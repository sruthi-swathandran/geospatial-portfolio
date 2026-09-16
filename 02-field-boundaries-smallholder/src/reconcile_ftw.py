"""
RS-02. Two scorers disagree about FTW on India. Work out which is right.

score_predictions.py reports object recall 0.053 for the 3-class FULL
checkpoint. seg_score.py, written later for the segmenter comparison, reports
0.027 on the same 399 chips under what should be the same rule. One is wrong
and stage 2b rests on knowing which.

The candidates are all about what goes into the match. Truth can be the eroded
instance mask FTW ships, or the parcel reconstructed by giving its boundary
ring back, and the reconstructed parcel is larger, so it is harder to match and
would score lower. Prediction can be the field class alone or the field class
together with the boundary ring. And a rate can be pooled over every parcel or
averaged over chips, which differ whenever chips carry different numbers of
parcels.

This runs every combination and prints both averages. Whichever reproduces
0.053 says what score_predictions.py actually did, and then we decide which
definition is the defensible one rather than which is the flattering one.

    python src\\reconcile_ftw.py --country india
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402
import seg_score as S                                         # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

COMBOS = [
    ("truth reconstructed, pred class 1", "full", "c1"),
    ("truth eroded instance, pred class 1", "inst", "c1"),
    ("truth reconstructed, pred class 1+2", "full", "c12"),
    ("truth eroded instance, pred class 1+2", "inst", "c12"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--tag", default="3class_full")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    from scipy.ndimage import label as cc_label

    pred_dir = F.RESULTS / f"pred_{args.tag}"
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    print(RULE)
    print(f"{F.COUNTRY.upper()}, {len(chips):,} chips, checkpoint {args.tag}")
    print(RULE)

    hits = {c[0]: [] for c in COMBOS}
    per_chip = {c[0]: [] for c in COMBOS}

    for i, chip in enumerate(chips):
        inst, _, c3, full = F.load_labels(chip)
        with rasterio.open(pred_dir / chip) as s:
            pred = s.read(1)

        masks = {
            "c1": pred == 1,
            "c12": (pred == 1) | (pred == 2),
        }
        truths = {"full": full, "inst": inst}

        for name, tkey, pkey in COMBOS:
            truth = truths[tkey]
            if truth.max() == 0:
                continue
            seg, _ = cc_label(masks[pkey])
            ious = S.parcel_scores(truth, seg.astype(np.int32))
            found = [1 if v >= args.iou else 0 for v in ious.values()]
            if not found:
                continue
            hits[name].extend(found)
            per_chip[name].append(float(np.mean(found)))

        if (i + 1) % 100 == 0:
            print(f"    {i + 1:,} chips")

    print(f"\n  {'combination':<40} {'found':>7} {'of':>7} "
          f"{'pooled':>8} {'per chip':>9}")
    rows = []
    for name, _, _ in COMBOS:
        arr = hits[name]
        if not arr:
            continue
        pooled = float(np.mean(arr))
        macro = float(np.mean(per_chip[name])) if per_chip[name] else 0.0
        print(f"  {name:<40} {int(np.sum(arr)):>7,} {len(arr):>7,} "
              f"{pooled:>8.4f} {macro:>9.4f}")
        rows.append({"combination": name, "found": int(np.sum(arr)),
                     "parcels": len(arr), "pooled": round(pooled, 4),
                     "per_chip": round(macro, 4)})

    out = F.RESULTS / "scorer_reconciliation.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("Looking for whichever cell reads 0.053. The eroded instance mask")
    print("is the wrong truth to score against, because it is the parcel with")
    print("its outer ring removed and matching a shrunken target is easier.")
    print("If that is where 0.053 comes from, RESULTS.md needs a correction")
    print("and the number drops to 0.027.")
    print(RULE)


if __name__ == "__main__":
    main()