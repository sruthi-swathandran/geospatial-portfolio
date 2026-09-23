"""
RS-02. What do these methods emit that is not a field?

Every Indian figure in this project is recall. A method emitting 917 objects
per chip and one emitting 175 are compared on what they find and never on what
they invent, which is F-10 in REVIEW.md.

Ordinary precision is not computable on India and saying so is half the answer.
Only five parcels per chip are drawn and 98.96% of each chip was never labelled,
so an object sitting over unlabelled ground may be a perfectly good field. The
share of objects that match a labelled parcel is therefore a lower bound on
India's precision, and on Slovenia, where the cadastre is complete, the same
quantity is precision itself.

So this reports two things.

Fragmentation, which is meaningful on both. How many predicted objects overlap
each labelled parcel. A method that shatters one field into ten pieces shows it
here whatever the labelling, and this is the number that says what the 175
objects per chip are actually doing.

Matched object share, which is precision on Slovenia and a floor on India. Read
the two countries against each other only through Slovenia.

FTW and the classical methods are measured from what is already on disk or from
one sweep. SAM is measured on a subset, because a full pass costs 26 hours.

    python src\\precision.py --country india --method ftw
    python src\\precision.py --country india --method watershed --setting 0.02
    python src\\precision.py --country slovenia --method ftw
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def per_chip(full, seg, iou_cut):
    """Fragmentation and matched-object counts for one chip."""
    pids = np.unique(full[full > 0])
    labels = np.unique(seg[seg > 0])
    if labels.size == 0:
        return [{"parcel_id": int(p), "objects_over": 0, "best_iou": 0.0}
                for p in pids], 0, 0

    matched, rows = set(), []
    for p in pids:
        mask = full == p
        over = np.unique(seg[mask])
        over = over[over > 0]
        best, best_lab = 0.0, 0
        for lab in over:
            obj = seg == lab
            inter = int((obj & mask).sum())
            union = int((obj | mask).sum())
            iou = inter / union if union else 0.0
            if iou > best:
                best, best_lab = iou, int(lab)
        if best >= iou_cut:
            matched.add(best_lab)
        rows.append({"parcel_id": int(p), "objects_over": int(over.size),
                     "best_iou": round(best, 4)})
    return rows, int(labels.size), len(matched)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--method", default="ftw",
                    choices=("ftw", "watershed", "felzenszwalb", "sam"))
    ap.add_argument("--setting", default="",
                    help="h for watershed, scale for felzenszwalb")
    ap.add_argument("--composite", default="false")
    ap.add_argument("--sam-threshold", type=float, default=0.50)
    ap.add_argument("--model", default="vit_h")
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--limit", type=int, default=0,
                    help="chips to measure, 0 for all. SAM needs a subset")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import compare_segmenters as C

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    if not pred_dir.exists():
        sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    if args.method == "sam":
        tag = (f"sam_{args.model}_{args.composite}_"
               f"{str(args.sam_threshold).replace('.', 'p')}")
    else:
        tag = args.method + (f"_{args.setting}" if args.setting else "")
    print(RULE)
    print(f"PRECISION AND FRAGMENTATION, {tag.upper()} ON "
          f"{F.COUNTRY.upper()}")
    print(RULE)
    print(f"  {len(chips):,} chips, grid {px_m:.3f} m, dropping objects under "
          f"{args.min_size_m2:.0f} m2 which is {min_px} grid pixels")
    if args.limit:
        print(f"  a subset, so every figure below carries that sample size")
    print()

    gen = None
    if args.method == "sam":
        # SAM keeps no segmentations on disk, so precision for it means
        # regenerating them. Generation is the whole cost and filtering
        # afterwards is free, which sam_verify_filter.py established to the
        # mask, so one pass at the loose threshold covers whichever setting is
        # asked for. A full country is 26 hours, hence --limit.
        import sam_run as S2
        try:
            from segment_anything import (SamAutomaticMaskGenerator,
                                          sam_model_registry)
        except ImportError as exc:
            sys.exit(f"segment-anything is not importable ({exc})")
        import torch

        if args.composite not in S2.COMPOSITES:
            sys.exit(f"unknown composite {args.composite}")
        ckpt = S2.fetch(S2.BASE + S2.CKPTS[args.model],
                        F.PROJECT / "models" / S2.CKPTS[args.model])
        sam = sam_model_registry[args.model](checkpoint=str(ckpt))
        sam.to("cpu").eval()
        gen = SamAutomaticMaskGenerator(
            sam, points_per_side=args.points, crop_n_layers=0,
            pred_iou_thresh=S2.GEN_IOU,
            stability_score_thresh=S2.GEN_STABILITY,
            min_mask_region_area=0)
        print(f"  {args.model} loaded, torch threads "
              f"{torch.get_num_threads()}")
        print(f"  {args.composite} colour at predicted IoU "
              f"{args.sam_threshold:.2f} over stability "
              f"{S2.GEN_STABILITY:.2f}")
        print(f"  about {args.points ** 2:,} prompts per chip, so roughly "
              f"{len(chips) * 75 / 60:.0f} minutes for {len(chips)} chips\n")

    rows, n_objects, n_matched, n_chips = [], 0, 0, 0
    tic = time.time()
    for i, chip in enumerate(chips, 1):
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        if args.method == "ftw":
            seg = C.ftw_segments(chip, args.ref_tag)
        elif args.method == "sam":
            import sam_run as S2
            img = S2.rgb8(chip, S2.COMPOSITES[args.composite])
            masks = gen.generate(img)
            keep = [m for m in masks
                    if m["predicted_iou"] >= args.sam_threshold
                    and m["stability_score"] >= S2.GEN_STABILITY]
            seg = S2.masks_to_labels(keep, img.shape[:2])
        else:
            try:
                stack = C.read_stack(chip)
            except FileNotFoundError:
                continue
            if not args.setting:
                sys.exit(f"--setting is required for {args.method}")
            seg = C.segment(stack, C.gradient(stack), args.method,
                            float(args.setting))
        seg = C.drop_small(seg, min_px)

        r, nobj, nmatch = per_chip(full, seg, args.iou)
        for x in r:
            x["chip"] = chip
        rows += r
        n_objects += nobj
        n_matched += nmatch
        n_chips += 1

        if i % 25 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            left = (len(chips) - i) / rate if rate else 0
            print(f"    {i:>4,} / {len(chips):,}   {rate:.1f} chips/s   "
                  f"{left / 60:.1f} min left")

    if not rows:
        sys.exit("no parcels measured")

    import pandas as pd
    df = pd.DataFrame(rows)
    out = F.RESULTS / f"precision_{tag}_min{int(args.min_size_m2)}.csv"
    df.to_csv(out, index=False)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}, {len(df):,} parcels")

    over = df["objects_over"]
    print("\n" + RULE)
    print("RESULT")
    print(RULE)
    print(f"  {n_chips:,} chips, {len(df):,} labelled parcels, "
          f"{n_objects:,} objects emitted")
    print(f"  {n_objects / n_chips:.1f} objects per chip, "
          f"{len(df) / n_chips:.1f} labelled parcels per chip\n")

    print("  FRAGMENTATION, predicted objects overlapping one labelled parcel")
    print(f"    median                    {over.median():.0f}")
    print(f"    mean                      {over.mean():.1f}")
    print(f"    p90                       {over.quantile(0.9):.0f}")
    print(f"    parcels covered by one    "
          f"{float((over == 1).mean()) * 100:.1f}%")
    print(f"    parcels cut into 5 or more "
          f"{float((over >= 5).mean()) * 100:.1f}%")
    print(f"    parcels with no object at all "
          f"{float((over == 0).mean()) * 100:.1f}%")

    share = n_matched / n_objects if n_objects else float("nan")
    print(f"\n  MATCHED OBJECT SHARE  {share * 100:.2f}%")
    print(f"    {n_matched:,} of {n_objects:,} emitted objects best-match a")
    print(f"    labelled parcel at IoU {args.iou}.")
    if F.COUNTRY == "india":
        print("    India is presence-only, so this is a floor on precision")
        print("    rather than precision. An object over unlabelled ground")
        print("    may be a real field nobody drew.")
    else:
        print("    Slovenia's cadastre is complete, so this is precision.")

    print("\n" + RULE)
    print("Fragmentation is the number to read across countries. Matched share")
    print("compares between methods within Slovenia only.")
    print(RULE)


if __name__ == "__main__":
    main()
