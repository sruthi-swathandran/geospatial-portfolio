"""
Scoring that any segmentation can go through, so SAM and a classical baseline
land in the same tables as FTW's checkpoint and the numbers can be compared.

The match rule is the one score_predictions.py uses. Every labelled parcel is
matched against whichever segment covers most of it, and that pair's IoU is
the parcel's score. Segments with no label under them are ignored rather than
counted as errors, because 98.96% of an Indian chip was never labelled and
scoring those would measure the annotation instead of the method.

Width is measured the same way analyse_width.py measures it, by the inscribed
circle, so a parcel's width here is the same number it has there.
"""

from __future__ import annotations

import csv

import numpy as np


def parcel_scores(truth_labels: np.ndarray, segments: np.ndarray) -> dict:
    """Best IoU for each labelled parcel against any segment.

    `segments` is an instance label raster where 0 means nothing was
    segmented. No connected component step is needed, unlike the FTW path,
    because a segmenter already hands back separated objects.
    """
    seg = segments.astype(np.int64, copy=False)
    n_seg = int(seg.max())
    seg_sizes = np.bincount(seg.ravel(), minlength=n_seg + 1)
    out = {}
    for pid in np.unique(truth_labels[truth_labels > 0]):
        tmask = truth_labels == pid
        overlaps = np.bincount(seg[tmask].ravel(), minlength=n_seg + 1)
        overlaps[0] = 0
        j = int(overlaps.argmax())
        inter = int(overlaps[j])
        union = int(tmask.sum()) + int(seg_sizes[j]) - inter
        out[int(pid)] = (inter / union) if union else 0.0
    return out


def parcel_width_px(mask: np.ndarray) -> float:
    """Width across a parcel in grid pixels, by the largest inscribed circle.

    Padding matters. A three-wide strip has a centre pixel two steps from the
    padding, so 2d - 1 recovers the three.
    """
    from scipy.ndimage import distance_transform_edt
    if not mask.any():
        return 0.0
    d = distance_transform_edt(np.pad(mask, 1, constant_values=False))
    return max(1.0, float(d.max()) * 2.0 - 1.0)


def rows_for_chip(chip, full_labels, segments, country, px_m, native_m=10.0):
    """One row per labelled parcel in this chip, in the FTW table schema."""
    scale = px_m / native_m
    ious = parcel_scores(full_labels, segments)
    rows = []
    for pid, iou in ious.items():
        mask = full_labels == pid
        px = int(mask.sum())
        rows.append({
            "country": country,
            "chip": chip,
            "parcel_id": pid,
            "full_px": px,
            "hectares": round(px * px_m * px_m / 10000.0, 4),
            "native_10m_px": round(px * scale * scale, 2),
            "best_iou": round(iou, 4),
            "found": int(iou >= 0.5),
            "width_native_px": round(parcel_width_px(mask) * scale, 3),
        })
    return rows


def write_tables(rows, results_dir, tag):
    """Write the score and width tables under the names the other tools expect."""
    results_dir.mkdir(parents=True, exist_ok=True)
    fields = ["country", "chip", "parcel_id", "full_px", "hectares",
              "native_10m_px", "best_iou", "found", "width_native_px"]
    paths = []
    for stem in (f"score_parcels_{tag}.csv", f"parcel_width_{tag}.csv"):
        p = results_dir / stem
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        paths.append(p)
    return paths