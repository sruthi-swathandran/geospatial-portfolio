"""
RS-02 stage 2b, third method. Measure what SAM costs before committing to it.

SAM resizes every input to 1024 by 1024 and automatic mask generation fires a
grid of prompts at it, so on a CPU-only machine the cost per chip decides
whether the full test set is an afternoon or a week. This runs a handful of
chips, reports seconds per chip beside the recall they buy, and writes nothing
that later work depends on.

Two composites are run rather than one. SAM takes three 8-bit channels while
FTW's model sees eight bands across two seasons, so the choice of which three
is a real handicap, and picking whichever one flatters the argument would stack
the deck. True colour is what a person would look at. False colour puts the
near infrared where vegetation contrast lives.

Scoring is the same function the other methods go through, with the same null
at matched object count, so a number from here can sit in the same table.

Checkpoint and code are Apache 2.0, which is why this can live in a public
repo. The checkpoint itself stays out of git, under models/.

This is the script that chose ViT-H over ViT-B and fixed points_per_side at 32,
so the numbers behind those two choices sit in results/<country>/probe/ rather
than only in somebody's memory. It was run over 5 chips, which is enough for a
timing figure and nowhere near enough for a recall figure, and the recall column
it prints should be read as a smoke test. The measured result lives in
sam_run.py's output over the full test set.

    python src\\sam_probe.py --country india --limit 8
    python src\\sam_probe.py --country india --limit 8 --points 16
    python src\\sam_probe.py --country india --limit 4 --model vit_l
"""

from __future__ import annotations

import argparse
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


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached {dest.name}, {dest.stat().st_size / 1e6:.0f} MB")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {dest.name}, this is a few hundred MB")
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as fh:
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

    SAM returns masks that can overlap, and the scorer needs each pixel to
    belong to one object. Painting largest first means a smaller mask sitting
    inside a larger one wins its pixels, which is the reading that gives SAM
    its best chance on parcels inside a field block.
    """
    lab = np.zeros(shape, np.int32)
    order = sorted(range(len(masks)), key=lambda i: -masks[i]["area"])
    for n, i in enumerate(order, 1):
        lab[masks[i]["segmentation"]] = n
    return lab


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--model", default="vit_b", choices=sorted(CKPTS))
    ap.add_argument("--points", type=int, default=32,
                    help="points_per_side, 32 is SAM's default")
    ap.add_argument("--composites", default="true,false")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--null-draws", type=int, default=3,
                    help="3 is enough where the gap is large. For a\n                          small gap, null_strength.py measures the\n                          null at 200 draws and reruns none of this")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260917)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import seg_score as S
    import compare_segmenters as C

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
    chips = [p.name for p in sorted(pred_dir.glob("*.tif"))][:args.limit]

    comps = [c.strip() for c in args.composites.split(",") if c.strip()]
    for c in comps:
        if c not in COMPOSITES:
            sys.exit(f"unknown composite {c}, choose from {sorted(COMPOSITES)}")

    px_m = F.grid_pixel_m()
    min_px = int(round(args.min_size_m2 / (px_m * px_m)))
    rng = np.random.default_rng(args.seed)

    print(RULE)
    print(f"SAM {args.model} ON {F.COUNTRY.upper()}, {len(chips)} chips")
    print(RULE)
    print(f"  torch threads {torch.get_num_threads()}, "
          f"cuda {torch.cuda.is_available()}")
    print(f"  points_per_side {args.points}, "
          f"so {args.points ** 2:,} prompts per chip")
    print(f"  dropping objects under {args.min_size_m2:.0f} m2, "
          f"{min_px} grid pixels here\n")

    ckpt = fetch(BASE + CKPTS[args.model],
                 F.PROJECT / "models" / CKPTS[args.model])

    tic = time.time()
    sam = sam_model_registry[args.model](checkpoint=str(ckpt))
    sam.to("cpu").eval()
    print(f"  model loaded in {time.time() - tic:.1f}s")

    gen = SamAutomaticMaskGenerator(
        sam,
        points_per_side=args.points,
        crop_n_layers=0,
        min_mask_region_area=0,      # our own filter does this, and SAM's
    )                                # postprocessing route needs opencv

    rows = {c: [] for c in comps}
    nulls = {c: [] for c in comps}
    counts = {c: [] for c in comps}
    secs = {c: [] for c in comps}

    print()
    for i, chip in enumerate(chips, 1):
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            print(f"  {chip}: no labelled parcel, skipping")
            continue
        for comp in comps:
            img = rgb8(chip, COMPOSITES[comp])
            t0 = time.time()
            masks = gen.generate(img)
            dt = time.time() - t0
            secs[comp].append(dt)

            seg = C.drop_small(masks_to_labels(masks, img.shape[:2]), min_px)
            n = C.object_count(seg)
            counts[comp].append(n)
            rows[comp].extend(
                S.rows_for_chip(chip, full, seg, F.COUNTRY, px_m))
            for _ in range(args.null_draws):
                nulls[comp].extend(S.rows_for_chip(
                    chip, full, C.null_segments(seg.shape, n, rng),
                    F.COUNTRY, px_m))

            print(f"  {i:>3}/{len(chips)}  {comp:<6} {dt:6.1f}s  "
                  f"{len(masks):>4} masks, {n:>4} after the size filter")

    print("\n" + RULE)
    print("RESULT")
    print(RULE)
    print(f"  {'composite':>10} {'s/chip':>8} {'objects':>8} {'parcels':>8} "
          f"{'med IoU':>8} {'recall':>7} {'null':>7} {'gap':>7}")
    for comp in comps:
        if not rows[comp]:
            continue
        ious = np.array([r["best_iou"] for r in rows[comp]])
        nious = np.array([r["best_iou"] for r in nulls[comp]])
        rec = float((ious >= args.iou).mean())
        nrec = float((nious >= args.iou).mean())
        print(f"  {comp:>10} {np.mean(secs[comp]):>8.1f} "
              f"{np.mean(counts[comp]):>8.0f} {len(ious):>8,} "
              f"{np.median(ious):>8.3f} {rec:>7.3f} {nrec:>7.3f} "
              f"{rec - nrec:>+7.3f}")

    scored = max(len(secs[c]) for c in comps) if comps else 0
    if scored:
        per = float(np.mean([np.mean(secs[c]) for c in comps if secs[c]]))
        total = 399 if F.COUNTRY == "india" else 228
        print(f"\n  at {per:.1f}s per chip per composite, the full "
              f"{total}-chip set")
        print(f"  would take {total * per / 60:.0f} min for one composite "
              f"and {total * per * len(comps) / 60:.0f} min for {len(comps)}")

    print("\n" + RULE)
    print("Compare the gap column against watershed's +0.197 on India and")
    print("FTW's +0.008. A gap near zero means SAM is scattering shapes, and")
    print("the recall beside it means nothing whatever its value. If the time")
    print("per chip is unworkable, --points 16 cuts the prompt grid to a")
    print("quarter and is worth measuring before reaching for a smaller model.")
    print(RULE)


if __name__ == "__main__":
    main()
