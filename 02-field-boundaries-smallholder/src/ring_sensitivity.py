"""
RS-02. How much does the parcel reconstruction decide?

F-12 in REVIEW.md. FTW ships each parcel as an eroded interior plus a separate
boundary class. `ftw_common.full_fields` gives each boundary pixel back to the
nearest interior, but only if that interior is within MAX_RING_DIST, which is
3.0 grid pixels. A ring pixel further out than that stays unassigned. Every
area, every width and every recall figure in this project is measured against
parcels rebuilt that way, so the cap is load bearing, and it was validated on
synthetic parcels only.

This cannot validate the cap. That needs parcels digitised independently of
FTW. What it can do is bound it: rebuild the parcels at several caps, score the
same segmentations against each, and report how far every headline moves.

Two things about the published cap need saying first. It counts grid pixels,
so it means about 18 m in India and, because Slovenian pixels are 4.14 m
across and 6.00 m tall (B-18), between 12 m and 18 m in Slovenia depending on
direction. So the sweep is run in metres, with the transform given each chip's
own pixel size, and the published 3 pixel cap is run alongside as the
reference. 12, 18 and 24 m are about 2, 3 and 4 pixels in India.

Segmentations do not depend on the cap, so each chip is segmented once per
method and scored against every version of its parcels. FTW is read from its
saved prediction. Watershed and felzenszwalb are run at their reported setting
for the country. SAM keeps nothing on disk, so it is regenerated, which costs
about 75 seconds a chip; run it on a subset with --methods sam --limit 100.

The run checks itself. At the published cap every recall must equal the
figure in segmenter_comparison_min500.csv, because nothing else differs.

    python src\\ring_sensitivity.py --country india
    python src\\ring_sensitivity.py --country slovenia
    python src\\ring_sensitivity.py --country india --methods sam --limit 100

Writes ring_sensitivity_truth.csv, ring_sensitivity.csv and
ring_sensitivity_bands.csv in the country's results folder, and prints the
cross-country table at every cap once both countries have run.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if "sam" in " ".join(sys.argv[1:]):
    # Load torch before anything else. Imported after pandas and the rest of
    # this script's imports, c10.dll failed to initialise (WinError 1114),
    # though torch and rasterio load together without complaint. sam_run.py
    # and precision.py happen to load torch early and never met this.
    import torch                                              # noqa: F401

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
CAPS = [("3 px, published", None), ("12 m", 12.0), ("18 m", 18.0),
        ("24 m", 24.0)]
REPORTED = {"india": {"watershed": 0.02, "felzenszwalb": 100.0},
            "slovenia": {"watershed": 0.05, "felzenszwalb": 100.0}}
WIDTH_EDGES_M = [0, 20, 30, 50, np.inf]
WIDTH_LABELS_M = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]
IOU = 0.5


def full_fields_m(inst, c3, cap_m, x_m, y_m):
    """full_fields with the cap in metres on this chip's own pixel size.

    Identical to ftw_common.full_fields except that the distance transform is
    given sampling, so the distance and the cap are both ground metres.
    Returns the parcels and the number of ring pixels left unassigned.
    """
    from scipy.ndimage import distance_transform_edt
    ring = c3 == F.C3_BOUNDARY
    if inst.max() == 0 or not ring.any():
        return inst.copy(), 0
    dist, idx = distance_transform_edt(inst == 0, sampling=(y_m, x_m),
                                       return_indices=True)
    claim = ring & (dist <= cap_m)
    full = inst.copy()
    full[claim] = inst[tuple(idx)][claim]
    return full, int((ring & ~claim).sum())


def sam_generator(points):
    """SAM ViT-H false colour at 0.50, the setting precision.py measured."""
    import sam_run as S2
    from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
    ckpt = S2.fetch(S2.BASE + S2.CKPTS["vit_h"],
                    F.PROJECT / "models" / S2.CKPTS["vit_h"])
    sam = sam_model_registry["vit_h"](checkpoint=str(ckpt))
    sam.to("cpu").eval()
    return SamAutomaticMaskGenerator(
        sam, points_per_side=points, crop_n_layers=0,
        pred_iou_thresh=S2.GEN_IOU, stability_score_thresh=S2.GEN_STABILITY,
        min_mask_region_area=0)


def sam_segments(chip, gen):
    import sam_run as S2
    img = S2.rgb8(chip, S2.COMPOSITES["false"])
    keep = [m for m in gen.generate(img)
            if m["predicted_iou"] >= 0.50
            and m["stability_score"] >= S2.GEN_STABILITY]
    return S2.masks_to_labels(keep, img.shape[:2])


def cross_country(results_root: Path) -> None:
    """FTW at matched ground width in both countries, at every cap."""
    import pandas as pd
    paths = {c: results_root / c / "ring_sensitivity_bands.csv"
             for c in ("india", "slovenia")}
    if not all(p.exists() for p in paths.values()):
        return
    a = pd.read_csv(paths["india"])
    b = pd.read_csv(paths["slovenia"])
    print("\n" + RULE)
    print("FTW AT MATCHED GROUND WIDTH, BOTH COUNTRIES, EVERY CAP")
    print(RULE)
    print(f"  {'cap':>16} {'band':>11} {'India':>9} {'Slovenia':>9} "
          f"{'ratio':>7}")
    for cap, _ in CAPS:
        for band in WIDTH_LABELS_M[1:]:
            ra = a[(a.cap == cap) & (a.method == "ftw") & (a.band == band)]
            rb = b[(b.cap == cap) & (b.method == "ftw") & (b.band == band)]
            if ra.empty or rb.empty:
                continue
            pa = ra.found.iloc[0] / max(ra.parcels.iloc[0], 1)
            pb = rb.found.iloc[0] / max(rb.parcels.iloc[0], 1)
            ratio = f"{pb / pa:.1f}x" if pa > 0 else "n/a"
            print(f"  {cap:>16} {band:>11} {pa * 100:>8.2f}% "
                  f"{pb * 100:>8.2f}% {ratio:>7}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--methods", default="ftw,watershed,felzenszwalb")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--points", type=int, default=32)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import pandas as pd
    import compare_segmenters as C
    import seg_score as S

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    min_px = int(round(args.min_size_m2 / F.grid_pixel_area_m2()))
    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    print(RULE)
    print(f"RING DISTANCE SENSITIVITY, {F.COUNTRY.upper()}, "
          f"{len(chips):,} chips")
    print(RULE)
    print(f"  caps: {', '.join(c for c, _ in CAPS)}")
    print(f"  methods: {', '.join(methods)}, objects under "
          f"{args.min_size_m2:.0f} m2 dropped ({min_px} grid pixels)\n")

    gen = sam_generator(args.points) if "sam" in methods else None

    truth = {c: {"ring_px": 0, "orphan_px": 0, "area": [], "width": []}
             for c, _ in CAPS}
    found = {(c, m): [] for c, _ in CAPS for m in methods}
    scored, tic = 0, time.time()

    for i, chip in enumerate(chips, 1):
        try:
            stack = C.read_stack(chip)
        except FileNotFoundError:
            continue
        inst, _, c3, full_pub, orph_pub = F.load_labels(chip,
                                                        return_orphans=True)
        if full_pub.max() == 0:
            continue
        scored += 1
        x_m, y_m = F.chip_pixel_xy_m(chip)
        ring_px = int((c3 == F.C3_BOUNDARY).sum())

        segs = {}
        grad = None
        for m in methods:
            if m == "ftw":
                seg = C.ftw_segments(chip, args.ref_tag)
            elif m == "sam":
                seg = sam_segments(chip, gen)
            else:
                grad = C.gradient(stack) if grad is None else grad
                seg = C.segment(stack, grad, m,
                                REPORTED[F.COUNTRY][m])
            segs[m] = C.drop_small(seg, min_px)

        for cap, cap_m in CAPS:
            if cap_m is None:
                full, orph = full_pub, orph_pub
            else:
                full, orph = full_fields_m(inst, c3, cap_m, x_m, y_m)
            t = truth[cap]
            t["ring_px"] += ring_px
            t["orphan_px"] += orph
            pids = np.unique(full[full > 0])
            for pid in pids:
                mask = full == pid
                t["area"].append(mask.sum() * x_m * y_m / 1e4)
                # rounded the way the published width tables store it, a
                # thousandth of a native pixel, so a parcel within a
                # hundredth of a metre of a band edge falls the same side
                w = round(S.width_m(mask, x_m, y_m) / 10.0, 3) * 10.0
                t["width"].append(w)
            for m in methods:
                ious = S.parcel_scores(full, segs[m])
                found[(cap, m)] += [ious.get(int(p), 0.0) >= IOU
                                    for p in pids]

        if i % 25 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            left = (len(chips) - i) / rate if rate else 0
            print(f"    {i:>4,} / {len(chips):,}   {rate:.2f} chips/s   "
                  f"{left / 60:.1f} min left")

    if not scored:
        sys.exit("no chip carried a label")

    tag = "_sam" if methods == ["sam"] else ""
    trows, mrows, brows = [], [], []
    for cap, cap_m in CAPS:
        t = truth[cap]
        widths = np.array(t["width"])
        trows.append({
            "country": F.COUNTRY, "cap": cap, "cap_m": cap_m,
            "chips": scored, "parcels": len(widths),
            "ring_px": t["ring_px"], "orphan_px": t["orphan_px"],
            "orphan_share": round(t["orphan_px"] / max(t["ring_px"], 1), 5),
            "median_area_ha": round(float(np.median(t["area"])), 4),
            "median_width_m": round(float(np.median(widths)), 2),
            "share_under_30m": round(float((widths < 30).mean()), 4),
        })
        bands = pd.cut(widths, WIDTH_EDGES_M, labels=WIDTH_LABELS_M,
                       right=False)
        for m in methods:
            f = np.array(found[(cap, m)], bool)
            mrows.append({"country": F.COUNTRY, "cap": cap, "method": m,
                          "chips": scored, "parcels": len(f),
                          "found": int(f.sum()),
                          "recall": round(float(f.mean()), 4)})
            for lab in WIDTH_LABELS_M:
                sel = np.asarray(bands == lab)
                brows.append({"country": F.COUNTRY, "cap": cap, "method": m,
                              "band": lab, "parcels": int(sel.sum()),
                              "found": int(f[sel].sum())})

    out = {}
    for name, rows in (("ring_sensitivity_truth", trows),
                       ("ring_sensitivity", mrows),
                       ("ring_sensitivity_bands", brows)):
        p = F.RESULTS / f"{name}{tag}.csv"
        pd.DataFrame(rows).to_csv(p, index=False)
        out[name] = p
        print(f"  wrote {p.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("THE PARCELS AT EACH CAP")
    print(RULE)
    print(f"  {'cap':>16} {'parcels':>8} {'ring left out':>14} "
          f"{'median ha':>10} {'median m':>9} {'under 30 m':>11}")
    for r in trows:
        print(f"  {r['cap']:>16} {r['parcels']:>8,} "
              f"{r['orphan_share'] * 100:>13.2f}% {r['median_area_ha']:>10.4f} "
              f"{r['median_width_m']:>9.2f} {r['share_under_30m'] * 100:>10.2f}%")

    print("\n" + RULE)
    print("RECALL AT EACH CAP")
    print(RULE)
    print(f"  {'method':>13} " + " ".join(f"{c:>16}" for c, _ in CAPS))
    for m in methods:
        vals = [r["recall"] for r in mrows if r["method"] == m]
        print(f"  {m:>13} " + " ".join(f"{v:>16.4f}" for v in vals))

    # the check: at the published cap nothing differs from the main run
    pub = F.RESULTS / f"segmenter_comparison_min{int(args.min_size_m2)}.csv"
    if pub.exists() and not args.limit and "sam" not in methods:
        p = pd.read_csv(pub, dtype={"setting": str})
        print("\n  check against the published run, at the published cap")
        ok = True
        for m in methods:
            if m == "ftw":
                row = p[p.method == "ftw"]
            else:
                want = REPORTED[F.COUNTRY][m]
                num = pd.to_numeric(p.setting, errors="coerce")
                row = p[(p.method == m) & (num == float(want))]
            mine = next(r["recall"] for r in mrows
                        if r["method"] == m and r["cap"] == CAPS[0][0])
            theirs = float(row.recall.iloc[0]) if not row.empty else None
            same = theirs is not None and abs(mine - theirs) < 5e-5
            ok &= same
            print(f"    {m:>13}  here {mine:.4f}  published "
                  f"{theirs if theirs is not None else 'missing'}  "
                  f"{'same' if same else 'DIFFERENT'}")
        if not ok:
            print("\n  The published cap should reproduce the published run.")
            print("  It does not, so something other than the cap differs and")
            print("  nothing below can be read as the cap's effect.")

    cross_country(F.PROJECT / "results")

    print("\n" + RULE)
    print("This bounds the reconstruction rather than validating it. A figure")
    print("that holds across 12 to 24 m does not depend on the cap. One that")
    print("moves is only as good as the cap, and the cap is untested against")
    print("independently digitised parcels.")
    print(RULE)


if __name__ == "__main__":
    main()
