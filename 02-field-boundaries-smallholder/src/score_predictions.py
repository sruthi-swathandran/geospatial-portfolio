"""
RS-02 / stage 2. Score the FTW checkpoint, honestly, per parcel and by size.

The question is not whether the model finds cropland. On India it predicts
88% of a chip as field and the landscape really is densely farmed, so pixel
recall will be high and will mean very little. The question is whether those
predicted regions are individual parcels or several parcels merged into one.
Under-segmentation and good detection look identical in a pixel score and
opposite in an object score, so both are computed here and reported together.

What gets measured, and what deliberately does not
--------------------------------------------------
PIXEL metrics follow FTW exactly: the 2-class mask, field is 1, not-field is 0,
and value 3 excluded. Their own trainer uses ignore_index=3 and their test
passes it to every metric, so this is comparable to their published numbers.

    On India that denominator is 1.03% of the chip, and within it the only
    negative pixels are the one-pixel boundary rings. So pixel precision there
    is close to asking how often the model avoids calling a parcel's own edge a
    field. It is a real number about a very narrow question. Reported, labelled.

OBJECT metrics match each labelled parcel to the best-overlapping connected
component of the prediction, IoU above a threshold counting as found. Truth
parcels come from the instance mask, which is eroded, and the rings keep
adjacent parcels apart. FTW's object metric takes components of 2class==1,
which is the same thing.

    Object RECALL is valid on both countries: it only asks whether a parcel
    that exists was found.

    Object PRECISION is computed for complete-label countries only. On
    presence-only data a predicted parcel with no match may be a real field
    nobody drew, and FTW's get_object_level_metrics counts it as a false
    positive regardless, which is why their India object precision cannot be
    used.

Everything is broken down by parcel size in native 10 m Sentinel-2 pixels,
because that is the axis the project exists to measure.

Writes, under results/<country>/:
    score_parcels.csv    one row per labelled parcel in the test split
    score_summary.csv    pixel metrics, and object recall overall and by size
and figures/recall_by_size.png across all scored countries.

    python src\\score_predictions.py
    python src\\score_predictions.py --iou 0.3
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                               # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

# native 10 m pixel bins, the axis this project is about
BINS = [(0, 4, "under 2x2"), (4, 9, "2x2 to 3x3"), (9, 16, "3x3 to 4x4"),
        (16, 25, "4x4 to 5x5"), (25, 49, "5x5 to 7x7"),
        (49, 100, "7x7 to 10x10"), (100, 400, "10x10 to 20x20"),
        (400, 10 ** 9, "over 20x20")]


def pct(x):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def parcel_ious(truth_labels, pred_mask):
    """Best IoU for every truth parcel against the prediction's components.

    Returns {parcel_id: (best_iou, best_component)} and the component count.
    """
    from scipy.ndimage import label as cc_label

    pred_lab, n_pred = cc_label(pred_mask)
    out = {}
    if n_pred == 0:
        for pid in np.unique(truth_labels[truth_labels > 0]):
            out[int(pid)] = (0.0, 0)
        return out, 0

    pred_sizes = np.bincount(pred_lab.ravel(), minlength=n_pred + 1)

    for pid in np.unique(truth_labels[truth_labels > 0]):
        tmask = truth_labels == pid
        t_size = int(tmask.sum())
        overlaps = np.bincount(pred_lab[tmask].ravel(), minlength=n_pred + 1)
        overlaps[0] = 0                      # component 0 is background
        if not overlaps.any():
            out[int(pid)] = (0.0, 0)
            continue
        j = int(overlaps.argmax())
        inter = int(overlaps[j])
        union = t_size + int(pred_sizes[j]) - inter
        iou = inter / union if union else 0.0
        out[int(pid)] = (float(iou), j)
    return out, n_pred


def score_country(country, iou_thr, classes, tag):
    """All scoring for one country. Returns (parcel rows, summary dict)."""
    import importlib
    import os
    os.environ["FTW_COUNTRY"] = country
    importlib.reload(F)

    pred_dir = F.RESULTS / f"pred_{classes}class{tag}"
    if not pred_dir.exists():
        print(f"  {country}: no {pred_dir.name}, skipping")
        return [], None
    names = [p.name for p in sorted(pred_dir.glob("*.tif"))]
    print(f"\n  {country}: {len(names):,} predicted chips")

    px_m = F.grid_pixel_m(names)
    ha_per_px = (px_m ** 2) / 10_000.0
    m2_native = F.NATIVE_M ** 2

    tp = fp = fn = tn = 0
    valid_px = 0
    n_pred_objects = 0
    n_pred_matched = 0
    rows = []
    complete = True

    for name in names:
        with rasterio.open(pred_dir / name) as s:
            pred = s.read(1)
        inst, c2, c3, full = F.load_labels(name)

        # pixel metrics, FTW's convention: 2class, ignore 3
        valid = c2 != F.C2_UNLABELLED
        if (c3 == F.C3_UNLABELLED).any():
            complete = False
        yt = (c2 == F.C2_INTERIOR) & valid
        yp = (pred == 1) & valid
        tp += int((yt & yp).sum())
        fp += int((~yt & yp).sum())
        fn += int((yt & ~yp).sum())
        tn += int((~yt & ~yp & valid).sum())
        valid_px += int(valid.sum())

        # The reconstructed parcel, not the eroded instance mask. C-04
        # established the parcel as this project's unit and every size figure
        # uses it, so the IoU has to be measured against the same object.
        # reconcile_ftw.py carries the FTW-convention number alongside.
        ious, n_comp = parcel_ious(full, pred == 1)
        n_pred_objects += n_comp
        hit_components = set()
        for pid, (iou, comp) in ious.items():
            fu_px = int((full == pid).sum())
            ha = fu_px * ha_per_px
            native = ha * 10_000.0 / m2_native
            found = iou >= iou_thr
            if found:
                hit_components.add(comp)
            rows.append({
                "country": country, "chip": name, "parcel_id": pid,
                "full_px": fu_px, "hectares": round(ha, 5),
                "native_10m_px": round(native, 2),
                "best_iou": round(iou, 4),
                "found": int(found),
            })
        n_pred_matched += len(hit_components)

    if not rows:
        print(f"  {country}: no labelled parcels in the predicted chips")
        return [], None

    native = np.array([r["native_10m_px"] for r in rows])
    found = np.array([r["found"] for r in rows], dtype=bool)
    best = np.array([r["best_iou"] for r in rows])

    pix_recall = tp / (tp + fn) if (tp + fn) else float("nan")
    pix_prec = tp / (tp + fp) if (tp + fp) else float("nan")
    pix_iou = tp / (tp + fp + fn) if (tp + fp + fn) else float("nan")
    obj_recall = float(found.mean())
    obj_prec = (n_pred_matched / n_pred_objects
                if complete and n_pred_objects else None)

    summary = {
        "country": country, "classes": classes, "tag": tag or "ccby",
        "chips": len(names), "parcels": len(rows),
        "complete_labels": int(complete),
        "grid_pixel_m": round(px_m, 3),
        "scored_pixels": valid_px,
        "pixel_recall": round(pix_recall, 4),
        "pixel_precision": round(pix_prec, 4),
        "pixel_iou": round(pix_iou, 4),
        "object_recall": round(obj_recall, 4),
        "object_precision": round(obj_prec, 4) if obj_prec is not None else "",
        "median_best_iou": round(float(np.median(best)), 4),
        "iou_threshold": iou_thr,
        "predicted_objects": n_pred_objects,
    }

    print(f"    scored pixels: {valid_px:,} "
          f"({valid_px / (len(names) * 65536) * 100:.2f}% of chip area)")
    print(f"    pixel   recall {pct(pix_recall)}   precision {pct(pix_prec)}"
          f"   IoU {pct(pix_iou)}")
    print(f"    object  recall {pct(obj_recall)} at IoU {iou_thr}   "
          f"precision {pct(obj_prec) if obj_prec is not None else 'withheld'}")
    print(f"    median best IoU per parcel: {np.median(best):.3f}")
    if not complete:
        print("    precision withheld: labels are presence-only, so a")
        print("    predicted parcel with no match may be a real field nobody")
        print("    drew. FTW's object precision here counts those as errors.")

    print(f"\n    {'parcel size':<18}{'parcels':>9}{'found':>9}"
          f"{'median IoU':>12}")
    bin_rows = []
    for lo, hi, label in BINS:
        m = (native >= lo) & (native < hi)
        if not m.any():
            continue
        print(f"    {label:<18}{int(m.sum()):>9,}"
              f"{pct(float(found[m].mean())):>9}"
              f"{np.median(best[m]):>12.3f}")
        bin_rows.append({
            "country": country, "bin": label, "lo_native_px": lo,
            "hi_native_px": hi if hi < 10 ** 8 else "",
            "parcels": int(m.sum()),
            "object_recall": round(float(found[m].mean()), 4),
            "median_best_iou": round(float(np.median(best[m])), 4),
        })

    write_csv(F.RESULTS / f"score_parcels_{classes}class{tag}.csv", rows)
    write_csv(F.RESULTS / f"score_bins_{classes}class{tag}.csv", bin_rows)
    return rows, summary


def write_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"    wrote {path.relative_to(F.PROJECT)}  ({len(rows):,} rows)")


def figure(all_rows, iou_thr, classes, tag):
    if not all_rows:
        return
    countries = sorted({r["country"] for r in all_rows})
    colours = {"india": "#c0562a", "slovenia": "#2f6f8f"}

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    centres = [(lo + min(hi, 1000)) / 2 for lo, hi, _ in BINS]
    labels = [lab for _, _, lab in BINS]

    for c in countries:
        rs = [r for r in all_rows if r["country"] == c]
        native = np.array([r["native_10m_px"] for r in rs])
        found = np.array([r["found"] for r in rs], dtype=bool)
        best = np.array([r["best_iou"] for r in rs])
        xs, rec, iou, ns = [], [], [], []
        for i, (lo, hi, _) in enumerate(BINS):
            m = (native >= lo) & (native < hi)
            if m.sum() < 5:
                continue
            xs.append(i)
            rec.append(found[m].mean() * 100)
            iou.append(np.median(best[m]))
            ns.append(int(m.sum()))
        col = colours.get(c, "#666666")
        axes[0].plot(xs, rec, "o-", color=col, label=f"{c} ({len(rs):,})")
        axes[1].plot(xs, iou, "o-", color=col, label=c)

    for ax, ylab, title in (
            (axes[0], f"parcels found, % at IoU {iou_thr}",
             "Is the parcel found at all"),
            (axes[1], "median best IoU", "How well is it traced")):
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel(ylab, fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, frameon=False)
    axes[0].set_ylim(-2, 102)
    axes[1].axhline(iou_thr, color="0.5", ls="--", lw=1)

    fig.suptitle(f"FTW {classes}-class {tag.strip(chr(95)) or 'CC-BY'} checkpoint, by parcel size",
                 fontsize=12, y=0.99)
    fig.text(0.5, 0.015,
             "Parcel size in native 10 m Sentinel-2 pixels. Both countries are "
             "in this checkpoint's training set. Object recall asks "
             "whether a labelled parcel\nwas found; it is valid on "
             "presence-only data because it never counts an unmatched "
             "prediction against the model.",
             ha="center", fontsize=8, linespacing=1.6)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.87, bottom=0.30,
                        wspace=0.22)

    out = F.PROJECT / "figures" / f"recall_by_size_{classes}class{tag}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="india,slovenia")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--tag", default="",
                    help="which prediction folder suffix to score")
    ap.add_argument("--classes", type=int, default=2,
                    help="which prediction set to score, 2 or 3")
    args = ap.parse_args()

    print(RULE)
    print(f"SCORING THE {args.classes}-CLASS PREDICTIONS AT IoU {args.iou}")
    print(RULE)

    all_rows, summaries = [], []
    for c in [x.strip() for x in args.countries.split(",") if x.strip()]:
        rows, summary = score_country(c, args.iou, args.classes, args.tag)
        all_rows.extend(rows)
        if summary:
            summaries.append(summary)

    if summaries:
        out = F.PROJECT / "results" / f"score_summary_{args.classes}class{args.tag}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(summaries[0]))
            w.writeheader()
            w.writerows(summaries)
        print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    figure(all_rows, args.iou, args.classes, args.tag)

    print("\n" + RULE)
    print("Object recall is the column this project exists to report. Pixel")
    print("metrics are here for comparability with FTW's published numbers.")
    print()
    print("A 2-class checkpoint predicts extent, so one connected region can")
    print("span many parcels and every parcel then fails IoU by arithmetic.")
    print("The 3-class checkpoint carries a boundary class to keep touching")
    print("parcels apart, which is what FTW polygonize uses, so --classes 3")
    print("is the run that tests delineation.")
    print(RULE)


if __name__ == "__main__":
    main()
