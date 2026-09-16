"""
RS-02 stage 2b. FTW, classical segmentation and a null model, scored alike.

The comparison this makes possible is the point: if a segmenter that was never
trained on anything beats a trained checkpoint, the checkpoint is the problem,
and if nothing clears the floor at three native pixels then the pixels are.

Two things have to be controlled for or the numbers mean nothing.

Best-overlap matching rewards producing more objects. A method that cuts a
chip into six hundred pieces has better odds of one piece fitting a parcel
than a method that produces twelve, with no more skill. So every setting is
paired with a null: the same number of cells, placed from random seeds with
the imagery ignored entirely. The gap between a method and its null is what
the method earned. The null matches object count but not the size
distribution, so it is a floor rather than a twin, and a method that fails to
clear it has certainly learned nothing.

The second is minimum object size. FTW's own polygonize step drops anything
under 500 square metres, so scoring its raw argmax output counts specks its
shipped pipeline would delete, inflates its object count, and raises its null.
The same filter is applied to every method here, which is fairer to FTW and
closer to how any of these would be deployed.

    python src\\compare_segmenters.py --country slovenia --limit 30
    python src\\compare_segmenters.py --country india
    python src\\compare_segmenters.py --country india --min-size-m2 0
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
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

SWEEPS = {
    "watershed": [0.005, 0.01, 0.02, 0.05, 0.10, 0.20],
    "felzenszwalb": [25, 50, 100, 200, 400, 800],
}


def stretch(band: np.ndarray) -> np.ndarray:
    a = band.astype(np.float32)
    lo, hi = np.percentile(a, (2, 98))
    if hi <= lo:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def read_stack(chip: str) -> np.ndarray:
    """Both seasonal windows, every band, each stretched on its own."""
    parts = []
    for folder in (F.IMG_A, getattr(F, "IMG_B", None)):
        if folder is None or not (folder / chip).exists():
            continue
        with rasterio.open(folder / chip) as s:
            arr = s.read()
        parts.append(np.stack([stretch(b) for b in arr]))
    if not parts:
        raise FileNotFoundError(f"no imagery for {chip}")
    return np.concatenate(parts, axis=0)


def gradient(stack: np.ndarray) -> np.ndarray:
    """Mean Sobel magnitude across every band, lightly smoothed."""
    from scipy.ndimage import gaussian_filter, sobel
    total = np.zeros(stack.shape[1:], np.float32)
    for b in stack:
        total += np.hypot(sobel(b, axis=0), sobel(b, axis=1))
    return gaussian_filter(total / stack.shape[0], 1.0)


def segment(stack, grad, method, param):
    """One segmentation. Labels start at 1, 0 is reserved for nothing."""
    if method == "watershed":
        from skimage.measure import label as sklabel
        from skimage.morphology import h_minima
        from skimage.segmentation import watershed
        markers = sklabel(h_minima(grad, param))
        if markers.max() == 0:
            return np.zeros(grad.shape, np.int32)
        return watershed(grad, markers).astype(np.int32)

    # felzenszwalb warns about eight channels because it was written for RGB.
    # Treating the stack as a multichannel 2d image is what we want, and the
    # warning is worth leaving visible rather than silencing.
    from skimage.segmentation import felzenszwalb
    img = np.transpose(stack, (1, 2, 0))
    lab = felzenszwalb(img, scale=float(param), sigma=0.8, min_size=4,
                       channel_axis=-1)
    return (lab + 1).astype(np.int32)


def drop_small(seg: np.ndarray, min_px: int) -> np.ndarray:
    """Remove objects below the minimum size, the way polygonize does.

    FTW's polygonize defaults to 500 square metres. Applying it to every
    method equally is fairer to FTW and closer to how any of these would be
    used, since nobody ships a layer full of single-pixel fields.
    """
    if min_px <= 1:
        return seg
    counts = np.bincount(seg.ravel())
    small = np.flatnonzero(counts < min_px)
    if small.size == 0:
        return seg
    out = seg.copy()
    out[np.isin(out, small)] = 0
    return out


def object_count(seg: np.ndarray) -> int:
    """Distinct non-zero labels. Dropping leaves gaps, so max() would lie."""
    counts = np.bincount(seg.ravel())
    return int((counts[1:] > 0).sum()) if counts.size > 1 else 0


def null_segments(shape, n, rng):
    """n Voronoi cells from random seeds. Same object count, no imagery used."""
    from scipy.ndimage import distance_transform_edt
    n = max(1, int(n))
    lab = np.zeros(shape, np.int32)
    ys = rng.integers(0, shape[0], n)
    xs = rng.integers(0, shape[1], n)
    lab[ys, xs] = np.arange(1, n + 1)
    if lab.max() == 0:
        return lab
    _, idx = distance_transform_edt(lab == 0, return_indices=True)
    return lab[tuple(idx)]


def ftw_segments(chip, ref_tag):
    """FTW's own prediction as objects, the way score_predictions.py reads it."""
    from scipy.ndimage import label as cc_label
    path = F.RESULTS / f"pred_{ref_tag}" / chip
    with rasterio.open(path) as s:
        pred = s.read(1)
    lab, _ = cc_label(pred == 1)
    return lab.astype(np.int32)


def summarise(rows, iou_cut):
    ious = np.array([r["best_iou"] for r in rows]) if rows else np.array([0.0])
    return float(np.median(ious)), float((ious >= iou_cut).mean()), len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--methods", default="watershed,felzenszwalb")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--min-size-m2", type=float, default=500.0,
                    help="FTW polygonize's own default, 0 to disable")
    ap.add_argument("--seed", type=int, default=20260916)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    try:
        import skimage                                        # noqa: F401
    except ImportError:
        sys.exit("scikit-image is needed.\n  pip install scikit-image")

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    if not pred_dir.exists():
        sys.exit(f"{pred_dir} not found")
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    for m in methods:
        if m not in SWEEPS:
            sys.exit(f"unknown method {m}, choose from {sorted(SWEEPS)}")

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))
    rng = np.random.default_rng(args.seed)

    print(RULE)
    print(f"{F.COUNTRY.upper()}, {len(chips):,} chips, grid {px_m:.3f} m")
    print(RULE)
    print("  every method scored by the same rule on the same chips, and")
    print("  every setting paired with a null at matched object count")
    print(f"  dropping objects under {args.min_size_m2:.0f} m2, "
          f"which is {min_px} grid pixels here\n")

    runs = [("ftw", args.ref_tag)]
    for m in methods:
        runs += [(m, p) for p in SWEEPS[m]]

    rows = {k: [] for k in runs}
    counts = {k: [] for k in runs}
    null_rows = {k: [] for k in runs}
    tic = time.time()
    scored = 0

    for i, chip in enumerate(chips):
        try:
            stack = read_stack(chip)
        except FileNotFoundError as exc:
            print(f"  skipping {chip}: {exc}")
            continue
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        grad = gradient(stack)
        shape = grad.shape
        scored += 1

        for key in runs:
            method, param = key
            seg = (ftw_segments(chip, param) if method == "ftw"
                   else segment(stack, grad, method, param))
            seg = drop_small(seg, min_px)
            n = object_count(seg)
            counts[key].append(n)
            rows[key].extend(S.rows_for_chip(chip, full, seg, F.COUNTRY, px_m))
            for _ in range(args.null_draws):
                nseg = null_segments(shape, n, rng)
                null_rows[key].extend(
                    S.rows_for_chip(chip, full, nseg, F.COUNTRY, px_m))

        if (i + 1) % 10 == 0 or i + 1 == len(chips):
            rate = (i + 1) / (time.time() - tic)
            left = (len(chips) - i - 1) / rate if rate else 0
            print(f"    {i + 1:>4,} / {len(chips):,}   {rate:.2f} chips/s   "
                  f"{left / 60:.1f} min left")

    if not scored:
        sys.exit("no chip carried a label, nothing to compare")
    print(f"\n  {scored:,} chips carried at least one labelled parcel")

    print("\n" + RULE)
    print("COMPARISON")
    print(RULE)
    print(f"  {'method':>13} {'setting':>8} {'objects':>8} {'med IoU':>8} "
          f"{'recall':>7} {'null':>7} {'gap':>7}")

    summary, best = [], {}
    for key in runs:
        method, param = key
        if not rows[key]:
            continue
        med, rec, n_parcels = summarise(rows[key], args.iou)
        _, null_rec, _ = summarise(null_rows[key], args.iou)
        objs = float(np.mean(counts[key])) if counts[key] else 0.0
        gap = rec - null_rec
        label = str(param) if method != "ftw" else ""
        print(f"  {method:>13} {label:>8} {objs:>8.0f} {med:>8.3f} "
              f"{rec:>7.3f} {null_rec:>7.3f} {gap:>+7.3f}")
        summary.append({"method": method, "setting": param,
                        "parcels": n_parcels,
                        "objects_per_chip": round(objs, 1),
                        "median_iou": round(med, 4),
                        "recall": round(rec, 4),
                        "null_recall": round(null_rec, 4),
                        "gap": round(gap, 4)})
        if gap > best.get(method, (None, -9.0))[1]:
            best[method] = (key, gap)

    if not summary:
        sys.exit("nothing scored")

    ftw_objs = next((r["objects_per_chip"] for r in summary
                     if r["method"] == "ftw"), None)
    if ftw_objs:
        print("\n" + RULE)
        print(f"EVERY METHOD AT FTW'S OBJECT BUDGET, {ftw_objs:.0f} per chip")
        print(RULE)
        print("  Gap over a null does not control for object count on its")
        print("  own, because a method with more objects has more room above")
        print("  its null. Reading every method at one budget does.")
        for method in ["ftw"] + methods:
            pts = sorted((r["objects_per_chip"], r["recall"])
                         for r in summary if r["method"] == method)
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rec = float(np.interp(ftw_objs, xs, ys))
            edge = ("" if xs[0] <= ftw_objs <= xs[-1]
                    else "   (outside the sweep, so this is clamped)")
            print(f"    {method:<14} {rec:.3f}{edge}")
            for r in summary:
                if r["method"] == method:
                    r["recall_at_ftw_budget"] = round(rec, 4)

    sp = F.RESULTS / "segmenter_comparison.csv"
    with open(sp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"\n  wrote {sp.relative_to(F.PROJECT)}")

    for method, (key, gap) in best.items():
        tag = "seg_ftw" if method == "ftw" else f"seg_{method}"
        for p in S.write_tables(rows[key], F.RESULTS, tag):
            print(f"  wrote {p.relative_to(F.PROJECT)}  "
                  f"(setting {key[1]}, gap {gap:+.3f})")

    print("\n" + RULE)
    print("Read the gap column and nothing else first. A method well above")
    print("its null is reading the imagery. A method level with its null")
    print("found parcels by scattering enough shapes that some landed, and")
    print("its recall means nothing whatever the value. The best setting per")
    print("method is chosen by gap, not by recall.")
    print(RULE)


if __name__ == "__main__":
    main()