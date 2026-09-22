"""
RS-02 stage 2b. Is FTW's Indian gap over the null real, or is it noise?

The comparison pairs every method with a null at matched object count, averaged
over three draws. Three is enough when the gap is +0.19. It is not enough for
FTW on India, where recall is 0.027 against a null of 0.022 and the gap is
+0.005, because the null itself moves by about that much between runs.

So run the null properly. Two hundred draws instead of three, and rather than
reporting only the mean, report where the method's own recall sits in the
distribution of what random cells achieve. If no draw out of two hundred
reaches it, the gap is small and real. If a third of them do, finding 3 in
COMPARISON.md says more than the data does.

The null needs the chip, its truth and an object count. It never needs the
imagery or the model, so this reruns nothing expensive. FTW's per-chip object
counts come back from the prediction rasters in a second, and SAM's are already
recorded in its raw table. The classical sweeps are left out because their gaps
are twenty to sixty times the size of the noise being measured here.

    python src\\null_strength.py --country india --method ftw
    python src\\null_strength.py --country slovenia --method ftw
    python src\\null_strength.py --country india --method sam ^
        --composite true --setting 0.50/0.88
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


def ftw_counts(chips, min_px, ref_tag):
    """Per-chip object count for the released checkpoint.

    Reads the prediction rasters the same way compare_segmenters.py does, so
    the counts match the ones the comparison table was built from.
    """
    import compare_segmenters as C
    out = {}
    for chip in chips:
        seg = C.drop_small(C.ftw_segments(chip, ref_tag), min_px)
        out[chip] = C.object_count(seg)
    return out


def sam_counts(composite, setting, model, points, min_size):
    """Per-chip object count and observed recall from SAM's raw table.

    The raw table carries one row per parcel per chip, with the object count
    for that chip repeated on each row, so nothing needs regenerating.
    """
    import pandas as pd
    name = f"sam_raw_{model}_p{points}_min{int(min_size)}.csv"
    path = F.RESULTS / name
    if not path.exists():
        sys.exit(f"{path} not found")
    df = pd.read_csv(path, dtype={"composite": str})
    df["composite"] = df["composite"].str.strip().str.lower()
    real = df[(df["composite"] == composite)
              & (df["setting"] == setting)
              & (df["is_null"] == 0)]
    if real.empty:
        have = sorted(set(zip(df["composite"], df["setting"])))
        sys.exit(f"no rows for {composite} at {setting}. Available: {have}")
    counts = real.groupby("chip")["objects"].first().to_dict()
    return counts, real


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--method", default="ftw", choices=("ftw", "sam"))
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--composite", default="true")
    ap.add_argument("--setting", default="0.50/0.88")
    ap.add_argument("--model", default="vit_h")
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260922)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import compare_segmenters as C
    import seg_score as S

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))
    rng = np.random.default_rng(args.seed)

    print(RULE)
    print(f"NULL STRENGTH, {args.method.upper()} ON {F.COUNTRY.upper()}, "
          f"{args.draws} draws")
    print(RULE)
    print(f"  grid {px_m:.3f} m, dropping objects under "
          f"{args.min_size_m2:.0f} m2, {min_px} grid pixels\n")

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    if not pred_dir.exists():
        sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    if args.method == "ftw":
        print(f"  reading object counts from {len(chips):,} "
              f"prediction rasters")
        counts = ftw_counts(chips, min_px, args.ref_tag)
        observed = None
    else:
        counts, real = sam_counts(args.composite, args.setting, args.model,
                                  args.points, args.min_size_m2)
        observed = float((real["best_iou"] >= args.iou).mean())
        chips = [c for c in chips if c in counts]
        print(f"  {len(chips):,} chips carry SAM output at "
              f"{args.composite} {args.setting}")

    truth, kept = {}, []
    for chip in chips:
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        truth[chip] = full
        kept.append(chip)
    n_parcels = sum(int(np.unique(t[t > 0]).size) for t in truth.values())
    print(f"  {len(kept):,} chips with a labelled parcel, "
          f"{n_parcels:,} parcels\n")

    if args.method == "ftw":
        hits = 0
        for chip in kept:
            seg = C.drop_small(C.ftw_segments(chip, args.ref_tag), min_px)
            rows = S.rows_for_chip(chip, truth[chip], seg, F.COUNTRY, px_m)
            hits += sum(1 for r in rows if r["best_iou"] >= args.iou)
        observed = hits / n_parcels

    rates, tic = [], time.time()
    for d in range(args.draws):
        hits = 0
        for chip in kept:
            seg = C.null_segments(truth[chip].shape, counts[chip], rng)
            rows = S.rows_for_chip(chip, truth[chip], seg, F.COUNTRY, px_m)
            hits += sum(1 for r in rows if r["best_iou"] >= args.iou)
        rates.append(hits / n_parcels)
        if (d + 1) % 10 == 0 or d + 1 == args.draws:
            rate = (d + 1) / (time.time() - tic)
            left = (args.draws - d - 1) / rate if rate else 0
            print(f"    draw {d + 1:>4} / {args.draws}   "
                  f"{left / 60:.1f} min left")

    r = np.array(rates)
    at_least = int((r >= observed).sum())

    # Keep every draw. The summary below is what the write-up quotes, and a
    # number quoted from a run nobody can inspect is the failure B-06 was.
    tag = args.method if args.method == "ftw" else \
        f"sam_{args.composite}_{args.setting.replace('/', '_')}"
    out = F.RESULTS / f"null_draws_{tag}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        fh.write("draw,null_recall,method_recall,seed\n")
        for i, v in enumerate(r):
            fh.write(f"{i},{v:.6f},{observed:.6f},{args.seed}\n")
    print(f"\n  wrote {out.relative_to(F.PROJECT)}, {len(r)} draws")

    print("\n" + RULE)
    print("RESULT")
    print(RULE)
    print(f"  method recall            {observed:.4f}")
    print(f"  null, mean of {args.draws:>4} draws  {r.mean():.4f}")
    print(f"  null, standard deviation {r.std(ddof=1):.4f}")
    print(f"  null, 2.5 to 97.5 pct    {np.percentile(r, 2.5):.4f} "
          f"to {np.percentile(r, 97.5):.4f}")
    print(f"  null, full range         {r.min():.4f} to {r.max():.4f}")
    print(f"  gap against the mean     {observed - r.mean():+.4f}")
    print(f"  draws reaching the method {at_least} of {args.draws}, "
          f"{at_least / args.draws * 100:.1f}%")

    print("\n" + RULE)
    if at_least == 0:
        print("No draw of random cells matched the method. The gap is real at")
        print("this draw count, however small it is. Quote the gap beside the")
        print("null's own spread so a reader can see the scale.")
    elif at_least / args.draws < 0.05:
        print("Random cells reach the method in under one draw in twenty. The")
        print("gap survives, and it is close enough that the three-draw")
        print("version could not have established it.")
    else:
        print("Random cells reach the method often enough that this gap is")
        print("not evidence of anything. The claim built on it has to be")
        print("written as a direction rather than a measurement, or dropped.")
    print(RULE)


if __name__ == "__main__":
    main()
