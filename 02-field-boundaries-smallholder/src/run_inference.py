"""
RS-02 / stage 2. Run the FTW checkpoint over a country's test split.

Why this exists rather than `ftw model test`
--------------------------------------------
ftw_cli.model.test hardcodes DataLoader(..., num_workers=12). Windows spawns
workers rather than forking, so twelve processes each re-import torch,
lightning and kornia, and the run dies with WinError 1455, the paging file
being too small. There is no flag for it. Commit charge runs out first, and
raising it needs administrator rights this machine does not grant. The 32 GB
of installed RAM is not the limit.

So this loop uses FTW's own dataset and preprocessing with no workers at all.
Same normalisation, same channel order, same split. Two details matter and
both come from reading ftw/datasets.py rather than assuming:

    preprocessing is exactly  image / 3000, and nothing else
    channel order is          window_b first, then window_a

Reversing those produces a model running on inputs it never saw and a bad
score that says nothing about FTW.

Predictions are written to disk as uint8 GeoTIFFs on the chip's own grid, so
scoring is a separate step that can be re-run and drawn.

Writes, under results/<country>/:
    pred_2class/<chip>.tif      argmax prediction per test chip
    inference_manifest.csv      one row per chip, with timings

    python src\\run_inference.py
    python src\\run_inference.py --limit 20        try 20 chips first
    python src\\run_inference.py --ckpt models\\3class_ccby.ckpt --classes 3
"""

from __future__ import annotations

import argparse
import csv
import inspect
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def show_object_metric_source():
    """Print FTW's object-level scorer, because it takes no ignore index."""
    print("\n" + RULE)
    print("FTW'S OBJECT-LEVEL SCORER, FOR THE RECORD")
    print(RULE)
    try:
        from ftw_cli.metrics import get_object_level_metrics as fn
    except Exception:                                         # noqa: BLE001
        try:
            from ftw_cli.model import get_object_level_metrics as fn
        except Exception as exc:                              # noqa: BLE001
            print(f"  could not import it: {exc}")
            return
    try:
        src = inspect.getsource(fn)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  source unavailable: {exc}")
        return
    for line in src.splitlines()[:70]:
        print("  " + line)
    print("\n  Their pixel metrics pass ignore_index=3 and are therefore sound")
    print("  on presence-only data. This function gets no such argument. If it")
    print("  treats every predicted object with no matching label as a false")
    print("  positive, then object precision on India counts correct parcels")
    print("  as errors, because 98.89% of the chip was never labelled.")


def load_model(ckpt_path):
    print(f"  loading {Path(ckpt_path).name}")
    tic = time.time()
    from ftw.trainers import CustomSemanticSegmentationTask
    task = CustomSemanticSegmentationTask.load_from_checkpoint(
        ckpt_path, map_location="cpu")
    model = task.model.eval()
    hp = dict(task.hparams)
    print(f"  {hp.get('model')} / {hp.get('backbone')}, "
          f"in_channels {hp.get('in_channels')}, "
          f"num_classes {hp.get('num_classes')}, "
          f"ignore_index {hp.get('ignore_index')}")
    print(f"  loaded in {time.time() - tic:.1f}s")
    return model, hp


def build_dataset(country, temporal):
    from ftw.datasets import FTW
    from ftw.datamodules import preprocess
    root = str(F.PROJECT / "data" / "ftw")
    ds = FTW(root=root, countries=[country], split="test",
             transforms=preprocess, load_boundaries=False,
             temporal_options=temporal)
    print(f"  {len(ds):,} test chips for {country}, "
          f"temporal_options={temporal}")
    return ds


def chip_name(ds, i):
    """FTW keeps per-index filenames; the mask path carries the chip name."""
    try:
        return Path(ds.filenames[i]["mask"]).name
    except Exception:                                         # noqa: BLE001
        return f"{i:06d}.tif"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(F.PROJECT / "models" /
                                          "2class_ccby.ckpt"))
    ap.add_argument("--classes", type=int, default=2,
                    help="how many classes the checkpoint predicts")
    ap.add_argument("--temporal", default="stacked")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="",
                    help="suffix for the output folder, e.g. _full")
    ap.add_argument("--threads", type=int, default=0,
                    help="torch CPU threads, 0 leaves the default")
    args = ap.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)
    print(f"Running inference for {F.COUNTRY}, "
          f"torch threads {torch.get_num_threads()}, "
          f"cuda {torch.cuda.is_available()}\n")

    model, hp = load_model(args.ckpt)
    ds = build_dataset(F.COUNTRY, args.temporal)
    n = min(args.limit, len(ds)) if args.limit else len(ds)

    out_dir = F.RESULTS / f"pred_{args.classes}class{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    tic_all = time.time()
    done = 0

    while done < n:
        batch_idx = list(range(done, min(done + args.batch, n)))
        tic = time.time()
        imgs = torch.stack([ds[i]["image"] for i in batch_idx])
        with torch.inference_mode():
            logits = model(imgs)
        pred = logits.argmax(dim=1).cpu().numpy().astype(np.uint8)
        dt = time.time() - tic

        for k, i in enumerate(batch_idx):
            name = chip_name(ds, i)
            src_path = F.INSTANCE / name
            if src_path.exists():
                with rasterio.open(src_path) as s:
                    prof = s.profile
            else:
                prof = {"driver": "GTiff", "height": pred.shape[1],
                        "width": pred.shape[2], "count": 1}
            prof.update(count=1, dtype="uint8", compress="deflate",
                        nodata=None)
            with rasterio.open(out_dir / name, "w", **prof) as d:
                d.write(pred[k], 1)
            rows.append({
                "chip": name,
                "pred_field_px": int((pred[k] == 1).sum()),
                "pred_boundary_px": int((pred[k] == 2).sum())
                if args.classes == 3 else 0,
                "seconds": round(dt / len(batch_idx), 3),
            })

        done += len(batch_idx)
        if done % 40 < args.batch or done == n:
            rate = done / (time.time() - tic_all)
            left = (n - done) / rate if rate else 0
            print(f"    {done:>5,} / {n:,}   {rate:.2f} chips/s   "
                  f"{left / 60:.1f} min left")

    elapsed = time.time() - tic_all
    print(f"\n  {n:,} chips in {elapsed / 60:.1f} min "
          f"({n / elapsed:.2f} chips/s)")
    print(f"  wrote {out_dir.relative_to(F.PROJECT)}")

    man = F.RESULTS / f"inference_manifest_{args.classes}class{args.tag}.csv"
    with open(man, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {man.relative_to(F.PROJECT)}")

    pf = np.array([r["pred_field_px"] for r in rows], dtype=float)
    print(f"\n  predicted field pixels per chip: "
          f"median {np.median(pf):,.0f} of 65,536 "
          f"({np.median(pf) / 65536 * 100:.1f}%), "
          f"chips predicting nothing: {int((pf == 0).sum()):,}")
    print("\n  That share is worth a glance before scoring. FTW's labels cover")
    print("  1.03% of an Indian chip and 12.18% of a Slovenian one, but the")
    print("  model is predicting over the whole chip either way, so a much")
    print("  larger share here is expected on India and is not by itself a")
    print("  fault.")

    show_object_metric_source()

    print("\n" + RULE)
    print("Next: python src\\score_predictions.py")
    print(RULE)


if __name__ == "__main__":
    main()
