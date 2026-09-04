"""
Binary segmentation metrics for RS-01.

Kept in its own file because the same functions score three different things:
the authors' Otsu baseline, each stage of our own pipeline, and the final
ablation table. If the metric code differs between them, the comparison is
meaningless — so it lives here and everything imports it.

Convention throughout: 1 = water, 0 = not water, -1 = no data (Sen1Floods11's
own convention for its hand labels).
"""

from __future__ import annotations

import numpy as np


def confusion(pred: np.ndarray, truth: np.ndarray, ignore_value: int = -1) -> dict:
    """
    Pixel counts for the water class.

    Pixels where truth == ignore_value are dropped entirely — they are not
    counted as correct or incorrect. Counting them as background is the most
    common quiet error in flood accuracy assessment, and it inflates every
    metric, because no-data regions are usually large and always "not water".
    """
    pred = np.asarray(pred)
    truth = np.asarray(truth)
    if pred.shape != truth.shape:
        raise ValueError(f"shape mismatch: pred {pred.shape} vs truth {truth.shape}")

    valid = truth != ignore_value
    p = (pred == 1) & valid
    t = (truth == 1) & valid

    return {
        "tp": int(np.sum(p & t)),
        "fp": int(np.sum(p & ~t & valid)),
        "fn": int(np.sum(~p & t & valid)),
        "tn": int(np.sum(~p & ~t & valid)),
        "n_valid": int(np.sum(valid)),
        "n_ignored": int(np.sum(~valid)),
    }


def scores(c: dict) -> dict:
    """Derive IoU / precision / recall / F1 from a confusion dict."""
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]

    def safe(num, den):
        return float(num) / float(den) if den else float("nan")

    out = dict(c)
    out["iou"] = safe(tp, tp + fp + fn)           # water-class IoU
    out["precision"] = safe(tp, tp + fp)
    out["recall"] = safe(tp, tp + fn)
    out["f1"] = safe(2 * tp, 2 * tp + fp + fn)
    out["accuracy"] = safe(tp + tn, tp + fp + fn + tn)
    out["water_frac_truth"] = safe(tp + fn, c["n_valid"])
    out["water_frac_pred"] = safe(tp + fp, c["n_valid"])
    return out


def evaluate(pred: np.ndarray, truth: np.ndarray, ignore_value: int = -1) -> dict:
    return scores(confusion(pred, truth, ignore_value))


def aggregate(confusions: list[dict]) -> dict:
    """
    Micro-average: sum the pixel counts, then compute the metrics once.

    Micro rather than macro (mean of per-chip IoU) because chips vary enormously
    in how much water they contain — a chip with 12 water pixels would otherwise
    carry the same weight as a chip that is half river. Report macro alongside
    it if you like, but the headline number should be micro, and the write-up
    should say which it is. A lot of published flood numbers are ambiguous on
    exactly this point.
    """
    total = {k: 0 for k in ("tp", "fp", "fn", "tn", "n_valid", "n_ignored")}
    for c in confusions:
        for k in total:
            total[k] += c[k]
    return scores(total)


def macro(confusions: list[dict]) -> dict:
    """
    Mean of per-chip metrics, over chips that contain water in the truth.

    Precision is undefined for a chip where nothing was predicted as water
    (tp + fp == 0), and one such chip would turn a plain mean into nan. Those
    chips are skipped for precision only — and the count of skipped chips is
    reported, because "the method predicted no water at all here" is itself
    informative and shouldn't vanish silently.
    """
    per = [scores(c) for c in confusions]
    usable = [s for s in per if s["tp"] + s["fn"] > 0]
    if not usable:
        return {k: float("nan") for k in ("iou", "precision", "recall", "f1")}

    out = {}
    for k in ("iou", "precision", "recall", "f1"):
        vals = np.array([s[k] for s in usable], dtype=float)
        out[k] = float(np.nanmean(vals)) if np.any(np.isfinite(vals)) else float("nan")

    out["n_chips"] = len(per)
    out["n_chips_with_water"] = len(usable)
    out["n_chips_no_prediction"] = sum(1 for s in usable if s["tp"] + s["fp"] == 0)
    return out


def format_row(name: str, s: dict) -> str:
    return (f"{name:<28} IoU {s['iou']:.3f}  P {s['precision']:.3f}  "
            f"R {s['recall']:.3f}  F1 {s['f1']:.3f}")
