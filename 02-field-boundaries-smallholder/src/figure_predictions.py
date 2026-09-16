"""
RS-02. Look at what the model did where a parcel was actually labelled.

The India numbers say something odd. The 3-class FULL checkpoint predicts field
over 28.6% of a chip, and yet pixel recall against labelled parcels is 23.3%
and median best IoU is 0.000 for every size bin below 5 by 5. So the model is
predicting plenty of field somewhere, and almost none of it lands on the
parcels FTW drew.

Merging adjacent parcels would give low IoU with a high overlap. Missing them
gives low IoU with no overlap. The score cannot tell those apart and a picture
can.

Each row is one labelled parcel, cropped to its neighbourhood rather than the
whole chip, showing:

    window_a false colour   the growing season the model saw
    label                   parcel interior, its boundary ring, other parcels
    prediction              all predicted classes, kept distinct
    overlap                 where prediction and label agree and disagree

Parcels are sampled across the measured size range, so the small end and the
large end are both represented rather than whichever came first alphabetically,
which is the mistake the earlier comparison figure made.

    python src\\figure_predictions.py
    python src\\figure_predictions.py --tag _full --rows 8
    python src\\figure_predictions.py --country slovenia --tag _full
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                               # noqa: E402
from matplotlib.patches import Patch                          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

WINDOW_M = 400.0

GREY = (0.90, 0.90, 0.90)
OTHER = (0.74, 0.84, 0.74)
INTERIOR = (0.13, 0.40, 0.22)
RING = (0.95, 0.72, 0.25)
PRED_FIELD = (0.20, 0.35, 0.70)
PRED_BOUND = (0.85, 0.45, 0.80)
HIT = (0.33, 0.72, 0.38)
MISS = (0.85, 0.30, 0.25)
EXTRA = (0.45, 0.55, 0.85)


def load_scores(classes, tag):
    p = F.RESULTS / f"score_parcels_{classes}class{tag}.csv"
    if not p.exists():
        sys.exit(f"{p} not found. Run score_predictions.py --classes "
                 f"{classes} --tag {tag or '(none)'} first.")
    with open(p, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["native_10m_px"] = float(r["native_10m_px"])
        r["best_iou"] = float(r["best_iou"])
        r["parcel_id"] = int(r["parcel_id"])
    return rows


def spread(rows, n):
    """One parcel at each of n evenly spaced size quantiles."""
    sizes = np.array([r["native_10m_px"] for r in rows])
    picks, used = [], set()
    for q in np.linspace(5, 95, n):
        target = float(np.percentile(sizes, q))
        for i in np.argsort(np.abs(sizes - target)):
            key = (rows[i]["chip"], rows[i]["parcel_id"])
            if key not in used:
                used.add(key)
                picks.append((q, rows[i]))
                break
    return picks


def stretch(a, lo=2, hi=98):
    out = np.empty(a.shape, np.float32)
    for i in range(a.shape[0]):
        p1, p2 = np.percentile(a[i], lo), np.percentile(a[i], hi)
        out[i] = 0.0 if p2 <= p1 else np.clip((a[i] - p1) / (p2 - p1), 0, 1)
    return np.transpose(out, (1, 2, 0))


def crop_for(full, pid, side, h, w):
    ys, xs = np.where(full == pid)
    if not len(ys):
        return Window(0, 0, side, side)
    cy, cx = (ys.min() + ys.max()) / 2, (xs.min() + xs.max()) / 2
    r0 = max(0, min(int(round(cy - side / 2)), h - side))
    c0 = max(0, min(int(round(cx - side / 2)), w - side))
    return Window(c0, r0, side, side)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="")
    ap.add_argument("--classes", type=int, default=3)
    ap.add_argument("--tag", default="_full")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--bands", default="4,3,2")
    args = ap.parse_args()

    if args.country:
        import importlib
        import os
        os.environ["FTW_COUNTRY"] = args.country
        importlib.reload(F)

    bands = [int(x) for x in args.bands.split(",")]
    rows = load_scores(args.classes, args.tag)
    rows = [r for r in rows if r["country"] == F.COUNTRY]
    if not rows:
        sys.exit(f"no scored parcels for {F.COUNTRY}")
    picks = spread(rows, args.rows)
    print(f"Drawing {len(picks)} parcels for {F.COUNTRY}, "
          f"{args.classes}-class{args.tag}")

    px_m = F.grid_pixel_m()
    side = int(round(WINDOW_M / px_m))
    pred_dir = F.RESULTS / f"pred_{args.classes}class{args.tag}"

    fig, axes = plt.subplots(len(picks), 4, figsize=(11.0, 2.75 * len(picks)))
    if len(picks) == 1:
        axes = axes.reshape(1, 4)

    for r, (q, rec) in enumerate(picks):
        chip = rec["chip"]
        pid = rec["parcel_id"]
        with rasterio.open(F.INSTANCE / chip) as s:
            h, w = s.height, s.width
        inst_full, c2f, c3f, full_f = F.load_labels(chip)
        win = crop_for(full_f, pid, min(side, h, w), h, w)

        with rasterio.open(F.IMG_A / chip) as s:
            img = s.read(bands, window=win).astype(np.float32)
        inst, c2, c3, full = F.load_labels(chip, window=win)
        with rasterio.open(pred_dir / chip) as s:
            pred = s.read(1, window=win)

        this = full == pid

        axes[r, 0].imshow(stretch(img))

        lab = np.full(inst.shape + (3,), GREY, np.float32)
        lab[full > 0] = OTHER
        lab[c3 == F.C3_BOUNDARY] = RING
        lab[this] = INTERIOR
        axes[r, 1].imshow(lab)

        pm = np.full(pred.shape + (3,), GREY, np.float32)
        pm[pred == 1] = PRED_FIELD
        if args.classes == 3:
            pm[pred == 2] = PRED_BOUND
        axes[r, 2].imshow(pm)

        ov = np.full(pred.shape + (3,), GREY, np.float32)
        pf = pred == 1
        ov[pf & ~this] = EXTRA
        ov[this & ~pf] = MISS
        ov[this & pf] = HIT
        axes[r, 3].imshow(ov)

        for k in range(4):
            axes[r, k].contour(this.astype(float), levels=[0.5],
                               colors="black" if k else "white",
                               linewidths=0.9)
            axes[r, k].set_xticks([])
            axes[r, k].set_yticks([])

        cover = float((this & pf).sum()) / max(1, int(this.sum()))
        axes[r, 0].set_ylabel(
            f"p{q:.0f}  {rec['native_10m_px']:.0f} px\n"
            f"IoU {rec['best_iou']:.3f}\n{cover * 100:.0f}% covered",
            fontsize=8, linespacing=1.5)

    for k, t in enumerate(["window_a, false colour", "label", "prediction",
                           "overlap"]):
        axes[0, k].set_title(t, fontsize=9)

    handles = [
        Patch(facecolor=INTERIOR, label="this parcel"),
        Patch(facecolor=OTHER, label="other parcels"),
        Patch(facecolor=RING, label="boundary ring"),
        Patch(facecolor=PRED_FIELD, label="predicted field"),
        Patch(facecolor=PRED_BOUND, label="predicted boundary"),
        Patch(facecolor=HIT, label="agree"),
        Patch(facecolor=MISS, label="parcel missed"),
        Patch(facecolor=EXTRA, label="field elsewhere"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=8, bbox_to_anchor=(0.5, 0.004))

    fig.suptitle(
        f"{F.COUNTRY.capitalize()}, FTW {args.classes}-class "
        f"{args.tag.strip('_') or 'CC-BY'} checkpoint",
        fontsize=12, y=0.998)
    fig.text(0.5, 0.981,
             f"One row per labelled parcel, sampled across the size range. "
             f"Each panel covers {WINDOW_M:.0f} m of ground.",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=0.085, right=0.99, top=0.945,
                        bottom=0.055 + 0.004 * len(picks),
                        wspace=0.05, hspace=0.06)

    out = F.FIGURES / f"predictions_{args.classes}class{args.tag}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"  wrote {out.relative_to(F.PROJECT)}")
    print("\n  Read the overlap column. Red means the parcel was missed and")
    print("  blue means the model called field somewhere else in the same")
    print("  crop. A lot of both together is the model finding different")
    print("  ground than the annotators did, which is a different failure")
    print("  from merging neighbours.")


if __name__ == "__main__":
    main()
