"""
Check that generating permissively and filtering afterwards reproduces
generating strictly.

sam_run.py generates once with loose thresholds and derives a sweep by
filtering on the predicted IoU and stability scores SAM attaches to every
mask. That is only sound if the loose-then-filter path returns what a strict
run would have returned. Reading the source says the two score filters run
before the overlap suppression, and the suppression ranks by predicted IoU
alone, so a mask that clears the IoU bar but fails the stability bar can
survive into suppression here and remove a mask a strict run would have kept.

The effect should be small and should only ever cost SAM masks, never add
them. Should is not measured, so this measures it.

Model-independent, so ViT-B answers it and no download is needed.

    python src\\sam_verify_filter.py --country india --limit 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
STRICT = (0.88, None)   # stability filled from sam_run.GEN_STABILITY in main


def key(m):
    """Identify a mask by its footprint rather than its pixels."""
    return (int(m["area"]), tuple(int(v) for v in m["bbox"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--model", default="vit_b")
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--composites", default="true,false")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import sam_run as R
    global STRICT
    STRICT = (STRICT[0], R.GEN_STABILITY)
    import compare_segmenters as C
    from segment_anything import (SamAutomaticMaskGenerator,
                                  sam_model_registry)

    ckpt = R.fetch(R.BASE + R.CKPTS[args.model],
                   F.PROJECT / "models" / R.CKPTS[args.model])
    sam = sam_model_registry[args.model](checkpoint=str(ckpt))
    sam.to("cpu").eval()

    def build(piou, stab):
        return SamAutomaticMaskGenerator(
            sam, points_per_side=args.points, crop_n_layers=0,
            pred_iou_thresh=piou, stability_score_thresh=stab,
            min_mask_region_area=0)

    strict_gen = build(*STRICT)
    loose_gen = build(R.GEN_IOU, R.GEN_STABILITY)

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))][:args.limit]
    comps = [c.strip() for c in args.composites.split(",") if c.strip()]

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))

    print(RULE)
    print(f"STRICT AGAINST LOOSE-THEN-FILTER, {args.model}, "
          f"{len(chips)} chips")
    print(RULE)
    print(f"  strict thresholds {STRICT[0]} and {STRICT[1]}, "
          f"loose {R.GEN_IOU} and {R.GEN_STABILITY}\n")
    print(f"  {'chip':<24} {'comp':<6} {'strict':>7} {'filtered':>9} "
          f"{'only strict':>12} {'only filtered':>14}")

    lost_total = gained_total = strict_total = 0
    for chip in chips:
        for comp in comps:
            img = R.rgb8(chip, R.COMPOSITES[comp])
            s_masks = strict_gen.generate(img)
            l_masks = [m for m in loose_gen.generate(img)
                       if m["predicted_iou"] >= STRICT[0]
                       and m["stability_score"] >= STRICT[1]]

            s_keys = {key(m) for m in s_masks}
            l_keys = {key(m) for m in l_masks}
            lost = len(s_keys - l_keys)
            gained = len(l_keys - s_keys)
            lost_total += lost
            gained_total += gained
            strict_total += len(s_keys)

            s_n = C.object_count(
                C.drop_small(R.masks_to_labels(s_masks, img.shape[:2]),
                             min_px))
            l_n = C.object_count(
                C.drop_small(R.masks_to_labels(l_masks, img.shape[:2]),
                             min_px))
            print(f"  {chip[:24]:<24} {comp:<6} {s_n:>7} {l_n:>9} "
                  f"{lost:>12} {gained:>14}")

    print("\n" + RULE)
    share = lost_total / strict_total if strict_total else 0.0
    print(f"  {lost_total:,} of {strict_total:,} strict masks missing from "
          f"the filtered set, {share * 100:.1f}%")
    print(f"  {gained_total:,} masks in the filtered set that strict "
          f"generation did not return")
    print()
    print("  Zero in both columns means the sweep in sam_run.py is exactly a")
    print("  strict run at every setting. A small number in the first column")
    print("  and zero in the second means the shortcut costs SAM a few masks")
    print("  and never flatters it, which is a stated caveat rather than a")
    print("  problem. Anything in the second column means the shortcut adds")
    print("  masks a strict run would not return, and then the default row")
    print("  has to come from strict generation.")
    print(RULE)


if __name__ == "__main__":
    main()