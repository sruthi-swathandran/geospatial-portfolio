"""
RS-02. Score our predictions with FTW's own code, and compare.

Our India object recall is 0.053. FTW's paper reports India without
fine-tuning at 0.03, 0.05 and 0.14 depending on the pre-training set, so ours
sits inside their range. What stays unexplained is that their 0.14 comes from a
model trained on FTW minus India, while our checkpoints include India and score
lower. A model that saw the country should not do worse on it.

Three candidate explanations were named in RESULTS.md as O-03. This tests the
two that can be tested from here.

    A  what --postprocess actually does, read from the installed source
    B  FTW's own get_object_level_metrics run over our predictions
    C  FTW's own torchmetrics, with ignore_index=3, over the same predictions
    D  what ftw inference polygonize does, read from the source

B and C are the decisive ones. If FTW's scoring functions return our numbers on
our predictions, then the scorer is not where the difference lives and the
remaining candidate is the model or its training, which we cannot reproduce on
this hardware.

Nothing is written unless --out is given.

    python src\\verify_against_ftw.py
    python src\\verify_against_ftw.py --classes 3 --tag _full --limit 100
"""

from __future__ import annotations

import argparse
import inspect
import sys
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


def pct(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def show(obj, label, limit=90):
    try:
        src = inspect.getsource(obj)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  {label}: source unavailable ({exc})")
        return
    lines = src.splitlines()
    print(f"\n  --- {label}  ({len(lines)} lines) ---")
    for line in lines[:limit]:
        print("  " + line)
    if len(lines) > limit:
        print(f"  ... {len(lines) - limit} more ...")


def section_a():
    print(RULE)
    print("A. WHAT --postprocess DOES")
    print(RULE)
    found = False
    for mod_name in ("ftw_cli.model", "ftw_cli.postprocess", "ftw.postprocess",
                     "ftw_cli.inference"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:                                     # noqa: BLE001
            continue
        for name in dir(mod):
            if "post" not in name.lower():
                continue
            obj = getattr(mod, name)
            if callable(obj) and getattr(obj, "__module__", "").startswith(
                    ("ftw", "ftw_cli")):
                show(obj, f"{mod_name}.{name}")
                found = True
    if not found:
        print("  no postprocess function found in ftw or ftw_cli")
    print("\n  The test loop we read earlier contains:")
    print("      if postprocess:")
    print("          post_processed_output = out.copy()")
    print("          output = post_processed_output")
    print("  `out` there is the -o metrics file path, a string or None, not the")
    print("  model output. If that is still the shipped code, --postprocess")
    print("  cannot run, and no published number can have used this code path.")


def section_bc(classes, tag, limit, thr):
    print("\n" + RULE)
    print("B and C. FTW'S OWN SCORING, OVER OUR PREDICTIONS")
    print(RULE)

    try:
        from ftw_cli.metrics import get_object_level_metrics as ftw_obj
    except Exception:                                         # noqa: BLE001
        try:
            from ftw_cli.model import get_object_level_metrics as ftw_obj
        except Exception as exc:                              # noqa: BLE001
            print(f"  could not import their object metric: {exc}")
            ftw_obj = None

    import torch
    from torchmetrics import MetricCollection
    from torchmetrics.classification import (JaccardIndex, Precision, Recall)

    metrics = MetricCollection([
        JaccardIndex(task="multiclass", average="none", num_classes=2,
                     ignore_index=3),
        Precision(task="multiclass", average="none", num_classes=2,
                  ignore_index=3),
        Recall(task="multiclass", average="none", num_classes=2,
               ignore_index=3),
    ])

    pred_dir = F.RESULTS / f"pred_{classes}class{tag}"
    if not pred_dir.exists():
        print(f"  {pred_dir} not found")
        return None
    names = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    if limit:
        names = names[:limit]
    print(f"  {F.COUNTRY}: {len(names):,} chips\n")

    tps = fps = fns = 0
    for i, name in enumerate(names):
        if i and i % 100 == 0:
            print(f"    {i:,} chips")
        with rasterio.open(pred_dir / name) as s:
            pred = s.read(1)
        c2 = F.read_band(F.C2_DIR / name)

        # their test maps a 3-class prediction to 2 classes exactly this way
        out2 = (pred == 1).astype(np.uint8)

        metrics.update(torch.from_numpy(out2.astype(np.int64))[None],
                       torch.from_numpy(c2.astype(np.int64))[None])

        if ftw_obj is not None:
            t, f, n = ftw_obj(c2.astype(np.uint8), out2, iou_threshold=thr)
            tps += t
            fps += f
            fns += n

    res = metrics.compute()
    pix_iou = float(res["MulticlassJaccardIndex"][1])
    pix_prec = float(res["MulticlassPrecision"][1])
    pix_rec = float(res["MulticlassRecall"][1])

    obj_prec = tps / (tps + fps) if (tps + fps) else float("nan")
    obj_rec = tps / (tps + fns) if (tps + fns) else float("nan")

    print(f"\n  FTW torchmetrics, ignore_index=3")
    print(f"    pixel IoU        {pix_iou:.4f}")
    print(f"    pixel precision  {pix_prec:.4f}")
    print(f"    pixel recall     {pix_rec:.4f}")
    if ftw_obj is not None:
        print(f"\n  FTW get_object_level_metrics at IoU {thr}")
        print(f"    true positives   {tps:,}")
        print(f"    false positives  {fps:,}")
        print(f"    false negatives  {fns:,}")
        print(f"    object precision {obj_prec:.4f}   "
              f"(meaningless on presence-only labels)")
        print(f"    object recall    {obj_rec:.4f}")
    return {
        "country": F.COUNTRY, "chips": len(names),
        "pixel_iou": round(pix_iou, 4),
        "pixel_precision": round(pix_prec, 4),
        "pixel_recall": round(pix_rec, 4),
        "object_tps": tps, "object_fps": fps, "object_fns": fns,
        "object_precision": round(float(obj_prec), 4),
        "object_recall": round(float(obj_rec), 4),
    }


def section_d():
    print("\n" + RULE)
    print("D. WHAT ftw inference polygonize DOES")
    print(RULE)
    for mod_name in ("ftw_cli.inference", "ftw_cli.polygonize", "ftw.polygonize"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:                                     # noqa: BLE001
            continue
        for name in dir(mod):
            if "polygon" not in name.lower():
                continue
            obj = getattr(mod, name)
            if callable(obj):
                show(obj, f"{mod_name}.{name}", limit=80)
                return
    print("  no polygonize function found")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="india,slovenia")
    ap.add_argument("--classes", type=int, default=3)
    ap.add_argument("--tag", default="_full")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--iou", type=float, default=0.5)
    args = ap.parse_args()

    section_a()

    import importlib
    import os
    rows = []
    for c in [x.strip() for x in args.countries.split(",") if x.strip()]:
        os.environ["FTW_COUNTRY"] = c
        importlib.reload(F)
        r = section_bc(args.classes, args.tag, args.limit, args.iou)
        if r:
            rows.append(r)

    section_d()

    if rows:
        import csv
        out = F.PROJECT / "results" / f"ftw_own_scoring_{args.classes}class{args.tag}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("Compare these against results/score_summary_3class_full.csv. If the")
    print("two agree, our scorer is not where the difference with the paper")
    print("lives, and the remaining candidate is the model or its training.")
    print("If they disagree, the difference is ours and is now located.")
    print(RULE)


if __name__ == "__main__":
    main()
