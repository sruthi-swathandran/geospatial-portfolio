"""
RS-02 stage 2b, third method. SAM over the same chips, scored the same way.

Cost shapes the design. On this CPU the image encoder is about 4 seconds and
each prompt about 62 milliseconds, so a 32 by 32 grid costs roughly 67 seconds
per chip per composite. Running that several times over to sweep object counts
would take days.

It does not have to. SAM discards masks below pred_iou_thresh and
stability_score_thresh, and it attaches both scores to every mask it returns.
So this generates once with permissive thresholds and filters afterwards,
turning one pass into a whole sweep. The caveat is that SAM applies its
overlap suppression after its own thresholds, so a permissive pass followed by
filtering is close to but not identical with a strict pass. It is the same
pipeline at every setting here, which is what the comparison needs.

Two composites are run rather than one. SAM takes three 8-bit channels while
FTW's model sees eight bands across two seasons, and picking whichever three
flatter the argument would stack the deck.

Every chip's parcels are appended to disk as they finish, and a rerun skips
what is already there, so a two-hour run can be stopped and resumed.

Checkpoint and code are Apache 2.0.

    python src\\sam_run.py --country india --limit 60
    python src\\sam_run.py --country india --limit 60          (resumes)
    python src\\sam_run.py --country india --aggregate-only
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")

BASE = "https://dl.fbaipublicfiles.com/segment_anything/"
CKPTS = {
    "vit_b": "sam_vit_b_01ec64.pth",
    "vit_l": "sam_vit_l_0b3195.pth",
    "vit_h": "sam_vit_h_4b8939.pth",
}

# rasterio bands are 1-indexed. FTW ships B2, B3, B4, B8 per window, so
# 1 is blue, 2 green, 3 red, 4 near infrared.
COMPOSITES = {"true": (3, 2, 1), "false": (4, 3, 2)}

# Generation thresholds, permissive enough that filtering afterwards can
# reproduce SAM's own defaults and everything looser.
# Stability is generated at SAM's own default and never swept. SAM applies
# both score filters before its overlap suppression and ranks that suppression
# by predicted IoU alone, so loosening stability at generation time lets a mask
# a strict run would have dropped remove one it would have kept. Measured at
# 12.6% of masks. Loosening predicted IoU alone cannot do that, because every
# mask above a given IoU is ranked ahead of every mask below it, so filtering
# afterwards reproduces a strict run exactly.
GEN_IOU = 0.50
GEN_STABILITY = 0.88

# (pred_iou_thresh, stability_score_thresh). The first pair is SAM's default.
SETTINGS = [
    (0.88, 0.88),
    (0.80, 0.88),
    (0.70, 0.88),
    (0.60, 0.88),
    (0.50, 0.88),
]

FIELDS = ["composite", "setting", "chip", "parcel_id", "full_px", "hectares",
          "native_10m_px", "best_iou", "found", "width_native_px",
          "is_null", "draw", "objects", "seconds"]


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached {dest.name}, {dest.stat().st_size / 1e6:.0f} MB")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {dest.name}")
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=900) as r, open(dest, "wb") as fh:
        shutil.copyfileobj(r, fh)
    print(f"  wrote {dest.name}, {dest.stat().st_size / 1e6:.0f} MB")
    return dest


def rgb8(chip: str, bands) -> np.ndarray:
    """One window as 8-bit RGB, percentile stretched per band, HWC for SAM."""
    with rasterio.open(F.IMG_A / chip) as s:
        arr = s.read(list(bands)).astype(np.float32)
    out = np.empty(arr.shape, np.uint8)
    for i in range(arr.shape[0]):
        lo, hi = np.percentile(arr[i], (2, 98))
        a = (np.zeros_like(arr[i]) if hi <= lo
             else np.clip((arr[i] - lo) / (hi - lo), 0.0, 1.0))
        out[i] = (a * 255).astype(np.uint8)
    return np.transpose(out, (1, 2, 0))


def masks_to_labels(masks, shape) -> np.ndarray:
    """Flatten SAM's overlapping masks into one instance raster.

    SAM's masks can overlap and the scorer needs each pixel to belong to one
    object. Painting largest first means a smaller mask inside a larger one
    wins its pixels, which is the reading that gives SAM its best chance on a
    parcel sitting inside a field block.
    """
    lab = np.zeros(shape, np.int32)
    order = sorted(range(len(masks)), key=lambda i: -masks[i]["area"])
    for n, i in enumerate(order, 1):
        lab[masks[i]["segmentation"]] = n
    return lab


def setting_name(pair) -> str:
    return f"{pair[0]:.2f}/{pair[1]:.2f}"


def done_pairs(path: Path) -> set:
    """Chip and composite pairs already on disk, so a rerun can resume."""
    if not path.exists():
        return set()
    seen = set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            seen.add((row["chip"], row["composite"]))
    return seen


def aggregate(path: Path, iou_cut: float, country: str, min_size: float,
              model: str):
    import seg_score as S
    if not path.exists():
        sys.exit(f"{path} not found, nothing to aggregate")
    with open(path, encoding="utf-8") as fh:
        raw = list(csv.DictReader(fh))
    if not raw:
        sys.exit("no rows to aggregate")

    for r in raw:
        r["best_iou"] = float(r["best_iou"])
        r["objects"] = float(r["objects"])
        r["seconds"] = float(r["seconds"])
        r["is_null"] = r["is_null"] == "1"

    chips = {r["chip"] for r in raw}
    print("\n" + RULE)
    print(f"SAM ON {country.upper()}, {len(chips):,} chips")
    print(RULE)
    print(f"  {'composite':>10} {'setting':>12} {'objects':>8} {'parcels':>8} "
          f"{'med IoU':>8} {'recall':>7} {'null':>7} {'gap':>7}")

    summary, best, tables = [], (None, -9.0), {}
    for comp in sorted({r["composite"] for r in raw}):
        for pair in SETTINGS:
            name = setting_name(pair)
            real = [r for r in raw if r["composite"] == comp
                    and r["setting"] == name and not r["is_null"]]
            null = [r for r in raw if r["composite"] == comp
                    and r["setting"] == name and r["is_null"]]
            if not real:
                continue
            tables[(comp, name)] = real
            ious = np.array([r["best_iou"] for r in real])
            nious = (np.array([r["best_iou"] for r in null]) if null
                     else np.array([0.0]))
            rec = float((ious >= iou_cut).mean())
            nrec = float((nious >= iou_cut).mean())
            objs = float(np.mean([r["objects"] for r in real]))
            gap = rec - nrec
            print(f"  {comp:>10} {name:>12} {objs:>8.0f} {len(ious):>8,} "
                  f"{np.median(ious):>8.3f} {rec:>7.3f} {nrec:>7.3f} "
                  f"{gap:>+7.3f}")
            summary.append({"composite": comp, "setting": name,
                            "objects_per_chip": round(objs, 1),
                            "parcels": len(ious),
                            "median_iou": round(float(np.median(ious)), 4),
                            "recall": round(rec, 4),
                            "null_recall": round(nrec, 4),
                            "gap": round(gap, 4)})
            if gap > best[1]:
                best = ((comp, name, real), gap)

    out = F.RESULTS / f"sam_comparison_{model}_min{int(min_size)}.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    def keep_cols(rs):
        cols = ("country", "chip", "parcel_id", "full_px", "hectares",
                "native_10m_px", "best_iou", "found", "width_native_px")
        return [{k: r[k] for k in cols}
                for r in [dict(r, country=country) for r in rs]]

    # Every setting, not just the winner, so the width comparison across
    # methods can be read at a matched object count afterwards. See O-11.
    for (comp, name), rs in tables.items():
        slug = name.split("/")[0].replace(".", "p")
        S.write_tables(keep_cols(rs), F.RESULTS,
                       f"seg_sam_{model}_{comp}_{slug}_min{int(min_size)}")
    print(f"  wrote per-setting tables for {len(tables)} combinations")

    if best[0]:
        comp, name, rs = best[0]
        tag = f"seg_sam_{model}_{comp}_min{int(min_size)}"
        for p in S.write_tables(keep_cols(rs), F.RESULTS, tag):
            print(f"  wrote {p.relative_to(F.PROJECT)}  "
                  f"({comp}, {name}, gap {best[1]:+.3f})")

    secs = [r["seconds"] for r in raw if not r["is_null"]]
    if secs:
        print(f"\n  {np.mean(secs):.1f} s per chip per composite")

    print("\n" + RULE)
    print("Set the gap column beside watershed's +0.197 on India and FTW's")
    print("+0.008. Then read object count: a row near 175 is comparable with")
    print("FTW directly, and a row far below it is not, because best-overlap")
    print("matching rewards producing more objects.")
    print(RULE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--model", default="vit_b", choices=sorted(CKPTS))
    ap.add_argument("--points", type=int, default=32)
    ap.add_argument("--composites", default="true,false")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=0,
                    help="0 means every chip")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260917)
    ap.add_argument("--aggregate-only", action="store_true")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import seg_score as S
    import compare_segmenters as C

    raw_path = (F.RESULTS /
                f"sam_raw_{args.model}_p{args.points}"
                f"_min{int(args.min_size_m2)}.csv")

    if args.aggregate_only:
        aggregate(raw_path, args.iou, F.COUNTRY, args.min_size_m2, args.model)
        return

    try:
        from segment_anything import (SamAutomaticMaskGenerator,
                                      sam_model_registry)
    except ImportError as exc:
        sys.exit(f"segment-anything is not importable ({exc}).\n"
                 "  pip install segment-anything torchvision")

    import torch
    if args.threads:
        torch.set_num_threads(args.threads)

    pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
    if not pred_dir.exists():
        sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if args.limit:
        chips = chips[:args.limit]

    comps = [c.strip() for c in args.composites.split(",") if c.strip()]
    for c in comps:
        if c not in COMPOSITES:
            sys.exit(f"unknown composite {c}, choose from {sorted(COMPOSITES)}")

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))
    rng = np.random.default_rng(args.seed)

    already = done_pairs(raw_path)
    todo = [(chip, comp) for chip in chips for comp in comps
            if (chip, comp) not in already]

    print(RULE)
    print(f"SAM {args.model} ON {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  torch threads {torch.get_num_threads()}, "
          f"cuda {torch.cuda.is_available()}")
    print(f"  points_per_side {args.points}, "
          f"{args.points ** 2:,} prompts per chip")
    print(f"  generating at pred_iou {GEN_IOU} and stability "
          f"{GEN_STABILITY}, then filtering to {len(SETTINGS)} settings")
    print(f"  dropping objects under {args.min_size_m2:.0f} m2, "
          f"{min_px} grid pixels here")
    print(f"  {len(already):,} chip and composite pairs already done, "
          f"{len(todo):,} to go")
    if not todo:
        aggregate(raw_path, args.iou, F.COUNTRY, args.min_size_m2)
        return

    ckpt = fetch(BASE + CKPTS[args.model],
                 F.PROJECT / "models" / CKPTS[args.model])
    sam = sam_model_registry[args.model](checkpoint=str(ckpt))
    sam.to("cpu").eval()
    gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=args.points,
        crop_n_layers=0,
        pred_iou_thresh=GEN_IOU,
        stability_score_thresh=GEN_STABILITY,
        min_mask_region_area=0,      # our own filter does this, and SAM's
    )                                # own route needs opencv

    new_file = not raw_path.exists()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(raw_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        writer.writeheader()

    tic = time.time()
    print()
    try:
        for k, (chip, comp) in enumerate(todo, 1):
            _, _, _, full = F.load_labels(chip)
            if full.max() == 0:
                continue
            img = rgb8(chip, COMPOSITES[comp])
            t0 = time.time()
            masks = gen.generate(img)
            dt = time.time() - t0

            line = []
            for pair in SETTINGS:
                name = setting_name(pair)
                kept = [m for m in masks
                        if m["predicted_iou"] >= pair[0]
                        and m["stability_score"] >= pair[1]]
                seg = C.drop_small(masks_to_labels(kept, img.shape[:2]),
                                   min_px)
                n = C.object_count(seg)
                line.append(f"{name} {n}")

                for r in S.rows_for_chip(chip, full, seg, F.COUNTRY, px_m):
                    r.pop("country", None)
                    writer.writerow({**r, "composite": comp, "setting": name,
                                     "is_null": 0, "draw": 0,
                                     "objects": n, "seconds": round(dt, 2)})
                for d in range(args.null_draws):
                    nseg = C.null_segments(seg.shape, n, rng)
                    for r in S.rows_for_chip(chip, full, nseg, F.COUNTRY,
                                             px_m):
                        r.pop("country", None)
                        writer.writerow({**r, "composite": comp,
                                         "setting": name, "is_null": 1,
                                         "draw": d, "objects": n,
                                         "seconds": round(dt, 2)})
            fh.flush()

            rate = k / (time.time() - tic)
            left = (len(todo) - k) / rate if rate else 0
            print(f"  {k:>4}/{len(todo)}  {comp:<6} {dt:5.1f}s  "
                  f"{len(masks):>4} masks  [{', '.join(line)}]  "
                  f"{left / 60:.0f} min left")
    except KeyboardInterrupt:
        print("\n  stopped. Rerun the same command to carry on where this "
              "left off.")
    finally:
        fh.close()

    aggregate(raw_path, args.iou, F.COUNTRY, args.min_size_m2, args.model)

if __name__ == "__main__":
    main()
