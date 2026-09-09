"""
RS-01 / step 9c - was the threshold the problem, or is change detection
genuinely beaten on this floodplain?

ROUND 1 RESULT AND ITS MISTAKE
------------------------------
Round 1 swept -12.0 to -0.5 dB and reported the best value at every one of the
eight settings as exactly -0.50 dB. That is the least negative value in the
range, so the sweep did not locate an optimum, it hit the wall. Same class of
error as the +/-2 truncation in the co-registration search.

The fix is to sweep past zero. As the change threshold rises above 0 dB the
condition (diff <= t) stops excluding anything, so the gated variant collapses
onto the plain single-date threshold and its 0.515 IoU. If the curve climbs
monotonically to that value, the best available change configuration is the one
that ignores the change signal, and that is worth seeing on a plot rather than
taking on argument.

WHAT ROUND 1 DID ESTABLISH
--------------------------
Otsu on the difference image picked -0.85 dB uncapped, against -3.00 for the cap
that change_detect.py applied. So the change thresholds in step 9 were a
constant typed into an argument parser, not an estimate from the data. Otsu
needs two modes; a difference image has one, because most pixels did not change
and their difference is speckle minus speckle piled around zero, with the
changed pixels in a tail.

More damaging: the tuned change method scored precision 0.599 and recall 0.460,
against 0.653 and 0.709 for the plain single-date threshold. Adding the change
constraint made both worse. A filter that trades recall for precision is a
judgement call. A filter that loses both is removing the wrong pixels, and
section 4 below measures exactly which.

Outputs:
    results/change_sweep.csv
    results/figures/change_sweep.png

Usage:
    python src\\change_sweep.py
    python src\\change_sweep.py --ref july
    python src\\change_sweep.py --tmin -12 --tmax 4 --step 0.25
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import rasterio                             # noqa: E402
from scipy.ndimage import uniform_filter    # noqa: E402
from skimage.filters import threshold_otsu  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                        # noqa: E402
    EVENT, DATA, RESULTS, TARGET_RES, pixel_ha,
)
from chips import read, split_lookup, lee_filter   # noqa: E402
import metrics as M                         # noqa: E402

REF_DIR = DATA / "reference"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

PIXEL_HA = pixel_ha(TARGET_RES)
REFERENCES = {"july": "REF_ALIGNED", "dry": "REFDRY_ALIGNED"}
SMOOTH_SIZES = (1, 3, 5, 9)


# --------------------------------------------------------------------- io
def usable_chips() -> list[str]:
    path = RESULTS / "usable_chips.txt"
    if path.exists():
        ids = [c.strip() for c in path.read_text().split() if c.strip()]
        if ids:
            return ids
    print("  (no usable_chips.txt, falling back to every aligned chip)")
    return sorted(p.name.split("_")[1]
                  for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))


def load_chip(chip_id: str, refname: str):
    with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif") as s:
        fl = s.read().astype("float64")
    with rasterio.open(
            REF_DIR / f"{EVENT}_{chip_id}_{REFERENCES[refname]}.tif") as s:
        rf = s.read().astype("float64")
    return (lee_filter(fl[1]).astype("float32"),
            lee_filter(rf[1]).astype("float32"),
            read("LabelHand", chip_id)[0])


def smooth(a: np.ndarray, size: int) -> np.ndarray:
    """
    Box mean that ignores NaN instead of spreading it.

    uniform_filter propagates NaN across the whole window, which would eat the
    chip border. Filling with zero and dividing by the count of valid pixels in
    the same window gives the mean of what is actually there.
    """
    if size <= 1:
        return a
    m = np.isfinite(a)
    num = uniform_filter(np.where(m, a, 0.0).astype("float64"),
                         size, mode="nearest")
    den = uniform_filter(m.astype("float64"), size, mode="nearest")
    out = np.divide(num, den, out=np.full_like(num, np.nan), where=den > 1e-9)
    return np.where(m, out, np.nan).astype("float32")


def pooled_otsu(arrays, stride: int = 7) -> float:
    v = np.concatenate([x[np.isfinite(x)][::stride] for x in arrays])
    return float(threshold_otsu(v))


# ------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="dry", choices=sorted(REFERENCES),
                    help="which reference date to sweep against")
    ap.add_argument("--tmin", type=float, default=-12.0)
    ap.add_argument("--tmax", type=float, default=4.0,
                    help="sweep past 0 dB so the collapse onto the single-date "
                         "threshold is visible")
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--stride", type=int, default=7,
                    help="pixel subsample used when pooling for Otsu")
    args = ap.parse_args()

    thresholds = np.round(np.arange(args.tmin, args.tmax + 1e-9, args.step), 2)
    suffix = REFERENCES[args.ref]
    ids = usable_chips()
    splits = split_lookup()

    data, t0 = {}, time.time()
    for n, chip_id in enumerate(ids, 1):
        if not (REF_DIR / f"{EVENT}_{chip_id}_{suffix}.tif").exists():
            continue
        try:
            data[chip_id] = load_chip(chip_id, args.ref)
        except Exception as exc:                       # noqa: BLE001
            print(f"  skipping {chip_id}: {exc}")
        print(f"\r  loading {n}/{len(ids)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    ids = [c for c in ids if c in data]
    if not ids:
        raise SystemExit(f"no chips carry a {suffix} file. Fetch it first.")

    n_valid = sum(1 for c in ids if splits.get(c) == "valid")
    n_test = sum(1 for c in ids if splits.get(c) == "test")
    print(f"{len(ids)} chips against the {args.ref} reference "
          f"({n_valid} valid, {n_test} test)\n")

    # ---------------------------------------------- 1. what Otsu really chose
    t_abs = pooled_otsu([d[0] for d in data.values()], args.stride)
    t_otsu_diff = pooled_otsu([d[0] - d[1] for d in data.values()], args.stride)
    diff_all = np.concatenate(
        [(d[0] - d[1])[np.isfinite(d[0] - d[1])][::args.stride]
         for d in data.values()])

    print("1. WHAT DID OTSU ACTUALLY PICK ON THE DIFFERENCE IMAGE?")
    print("-------------------------------------------------------")
    print(f"  absolute VH threshold (single date) {t_abs:8.2f} dB")
    print(f"  Otsu on the difference, uncapped    {t_otsu_diff:8.2f} dB")
    print(f"  cap applied in change_detect.py     {-3.00:8.2f} dB")
    print(f"  difference distribution: median {np.median(diff_all):+.2f}, "
          f"sd {diff_all.std():.2f}, "
          f"2nd pct {np.percentile(diff_all, 2):+.2f} dB")
    if t_otsu_diff > -3.0:
        print("\n  Otsu sits above the cap, so the cap is what ran. The change\n"
              "  thresholds reported in step 9 were a constant, not an estimate.")
    else:
        print("\n  Otsu sits below the cap, so the cap did not bind for this\n"
              "  reference and the earlier threshold was genuinely estimated.")

    # ------------------------------------------------------- 2. the sweep
    print("\n2. SWEEPING THE CHANGE THRESHOLD")
    print("--------------------------------")
    print(f"  {len(thresholds)} thresholds from {args.tmin:+.2f} to "
          f"{args.tmax:+.2f} dB x {len(SMOOTH_SIZES)} smoothing windows "
          f"x 2 gate settings")
    print("  scored on valid only, so the test split stays unused until a "
          "configuration is picked")

    rows = []
    t0 = time.time()
    for size in SMOOTH_SIZES:
        sm = {c: smooth(data[c][0] - data[c][1], size) for c in ids}
        for gate in (False, True):
            for t in thresholds:
                by_split, area = {}, 0.0
                for chip_id in ids:
                    fl_vh, rf_vh, label = data[chip_id]
                    nodata = ~(np.isfinite(fl_vh) & np.isfinite(rf_vh))
                    mask = sm[chip_id] <= t
                    if gate:
                        mask &= fl_vh <= t_abs
                    pred = np.where(nodata, -1, mask.astype(np.int8)
                                    ).astype(np.int8)
                    by_split.setdefault(splits.get(chip_id, "unknown"),
                                        []).append(M.confusion(pred, label))
                    area += M.mapped_area_px(pred, label) * PIXEL_HA
                row = {"smooth": size, "gate": int(gate), "threshold": float(t),
                       "area_ha": round(area, 1)}
                for split, confs in by_split.items():
                    a = M.aggregate(confs)
                    row[f"iou_{split}"] = round(a["iou"], 4)
                allc = [c for v in by_split.values() for c in v]
                a = M.aggregate(allc)
                row["iou_all"] = round(a["iou"], 4)
                row["p_all"] = round(a["precision"], 4)
                row["r_all"] = round(a["recall"], 4)
                rows.append(row)
        print(f"\r  smoothing {size}x{size} done ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    scored = [r for r in rows if "iou_valid" in r]
    if not scored:
        raise SystemExit("no valid-split chips in this subset, cannot select")

    lo, hi = float(thresholds[0]), float(thresholds[-1])
    print("\n  best threshold at each setting, chosen on valid")
    print(f"  {'smooth':>7}{'gate':>6}{'thresh':>9}{'valid':>8}{'test':>8}"
          f"{'all':>8}{'P':>7}{'R':>7}{'area ha':>10}  note")
    at_edge = 0
    for size in SMOOTH_SIZES:
        for gate in (0, 1):
            sub = [r for r in scored
                   if r["smooth"] == size and r["gate"] == gate]
            b = max(sub, key=lambda r: r["iou_valid"])
            edge = abs(b["threshold"] - lo) < 1e-6 or abs(b["threshold"] - hi) < 1e-6
            at_edge += int(edge)
            print(f"  {size:>7}{gate:>6}{b['threshold']:>9.2f}"
                  f"{b['iou_valid']:>8.3f}"
                  f"{b.get('iou_test', float('nan')):>8.3f}"
                  f"{b['iou_all']:>8.3f}{b['p_all']:>7.3f}{b['r_all']:>7.3f}"
                  f"{b['area_ha']:>10.0f}"
                  f"  {'AT SWEEP EDGE' if edge else ''}")

    if at_edge:
        print(f"\n  WARNING: {at_edge} of 8 settings put their optimum at an end "
              f"of the sweep.\n  The range {lo:+.2f} to {hi:+.2f} dB does not "
              "contain the peak. Widen it with\n  --tmin / --tmax before "
              "quoting any of these numbers.")
    else:
        print("\n  No setting sits at an end of the sweep, so the range "
              "contains the peak.")

    best = max(scored, key=lambda r: r["iou_valid"])

    # ------------------------------------------- 3. the honest comparison
    truth_area = sum(float(np.sum(data[c][2] == 1)) * PIXEL_HA for c in ids)

    def score_pred(fn):
        by_split, area = {}, 0.0
        for chip_id in ids:
            fl_vh, rf_vh, label = data[chip_id]
            pred = fn(chip_id, fl_vh, rf_vh, label)
            by_split.setdefault(splits.get(chip_id, "unknown"),
                                []).append(M.confusion(pred, label))
            area += M.mapped_area_px(pred, label) * PIXEL_HA
        return by_split, area

    def single_date(chip_id, fl_vh, rf_vh, label):
        return np.where(~np.isfinite(fl_vh), -1,
                        (fl_vh <= t_abs).astype(np.int8)).astype(np.int8)

    def published(chip_id, fl_vh, rf_vh, label):
        return read("S1OtsuLabelHand", chip_id)[0]

    print("\n3. DOES THE TUNED CHANGE METHOD BEAT THE SINGLE DATE?")
    print("-----------------------------------------------------")
    print(f"  {'method':<36}{'valid':>8}{'test':>8}{'all':>8}{'P':>7}{'R':>7}"
          f"{'area ha':>10}{'vs truth':>10}")

    def line(name, by_split, area):
        a = M.aggregate([c for v in by_split.values() for c in v])
        out = f"  {name:<36}"
        for split in ("valid", "test"):
            out += (f"{M.aggregate(by_split[split])['iou']:>8.3f}"
                    if split in by_split else f"{'-':>8}")
        out += (f"{a['iou']:>8.3f}{a['precision']:>7.3f}{a['recall']:>7.3f}"
                f"{area:>10.0f}{area / truth_area - 1:>+9.0%}")
        print(out)

    tag = (f"change, tuned ({best['smooth']}x{best['smooth']}, "
           f"gate {best['gate']}, {best['threshold']:+.2f} dB)")
    print(f"  {tag:<36}"
          f"{best['iou_valid']:>8.3f}"
          f"{best.get('iou_test', float('nan')):>8.3f}"
          f"{best['iou_all']:>8.3f}{best['p_all']:>7.3f}{best['r_all']:>7.3f}"
          f"{best['area_ha']:>10.0f}"
          f"{best['area_ha'] / truth_area - 1:>+9.0%}")
    sd_split, sd_area = score_pred(single_date)
    line("single date, pooled Otsu", sd_split, sd_area)
    line("published S1OtsuLabelHand", *score_pred(published))
    print(f"  {'hand-labelled truth':<36}{'':>46}{truth_area:>10.0f}")

    # ------------------------------ 4. what is the change filter removing?
    print("\n4. WHAT DOES THE CHANGE FILTER ACTUALLY REMOVE?")
    print("-----------------------------------------------")
    print("  Starting from the pixels the single-date threshold already found,")
    print("  the change condition deletes some of them. A useful filter deletes")
    print("  false positives faster than true water. These are the rates.\n")
    print(f"  {'threshold':>10}{'scene darkened':>16}{'true water cut':>16}"
          f"{'false pos cut':>15}{'verdict':>12}")

    probe = sorted({-6.0, -3.0, -1.0, -0.5, 0.0, 1.0,
                    round(float(best["threshold"]), 2)})
    scene_px = tp_s = fp_s = 0
    per_t = {t: [0, 0, 0] for t in probe}      # darkened, tp_kept, fp_kept
    for chip_id in ids:
        fl_vh, rf_vh, label = data[chip_id]
        valid = np.isfinite(fl_vh) & np.isfinite(rf_vh) & (label != -1)
        water = valid & (label == 1)
        single = valid & (fl_vh <= t_abs)
        diff = fl_vh - rf_vh
        scene_px += int(valid.sum())
        tp_s += int((single & water).sum())
        fp_s += int((single & ~water).sum())
        for t in probe:
            dark = valid & (diff <= t)
            per_t[t][0] += int(dark.sum())
            per_t[t][1] += int((single & water & dark).sum())
            per_t[t][2] += int((single & ~water & dark).sum())

    for t in probe:
        dark, tp_k, fp_k = per_t[t]
        tw_cut = 1.0 - tp_k / max(tp_s, 1)
        fp_cut = 1.0 - fp_k / max(fp_s, 1)
        verdict = "backwards" if tw_cut > fp_cut else "helping"
        print(f"  {t:>+10.2f}{dark/scene_px:>15.1%}{tw_cut:>16.1%}"
              f"{fp_cut:>15.1%}{verdict:>12}")

    print(f"\n  scene = {scene_px * PIXEL_HA:,.0f} ha across {len(ids)} chips; "
          f"hand-labelled water = {truth_area:,.0f} ha "
          f"({truth_area / (scene_px * PIXEL_HA):.1%})")
    print("  A darkened fraction far above the water fraction means the change\n"
          "  signal is dominated by seasonal wetting rather than by flooding.\n"
          "  'backwards' rows delete correct answers faster than wrong ones,\n"
          "  which is the clearest possible statement that the filter is not\n"
          "  measuring what we want it to measure.")

    # ------------------------------------------------------------ outputs
    fields = ["smooth", "gate", "threshold", "iou_train", "iou_valid",
              "iou_test", "iou_all", "p_all", "r_all", "area_ha"]
    with open(RESULTS / "change_sweep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    sd_valid = M.aggregate(sd_split["valid"])["iou"] if "valid" in sd_split else None

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, gate in zip(axes, (0, 1)):
        for size in SMOOTH_SIZES:
            sub = sorted([r for r in scored
                          if r["smooth"] == size and r["gate"] == gate],
                         key=lambda r: r["threshold"])
            ax.plot([r["threshold"] for r in sub],
                    [r["iou_valid"] for r in sub],
                    marker="o", markersize=2.5, linewidth=1.4,
                    label=f"{size}x{size}")
        ax.axvline(-3.0, color="black", linestyle=":", linewidth=1.2)
        ax.text(-3.0, 0.005, " cap used in step 9", fontsize=7, rotation=90,
                va="bottom")
        ax.axvline(0.0, color="#555555", linestyle="-", linewidth=0.8)
        if sd_valid is not None:
            ax.axhline(sd_valid, color="#b03030", linestyle="--", linewidth=1.2)
            ax.text(lo + 0.2, sd_valid + 0.008,
                    "single-date threshold, valid split", fontsize=7,
                    color="#b03030")
        ax.set_xlabel("change threshold on VH (dB)")
        ax.set_title("with absolute darkness gate" if gate
                     else "change signal alone")
        ax.grid(alpha=0.25)
        ax.legend(title="smoothing", fontsize=8)
    axes[0].set_ylabel("IoU on the valid split")
    fig.suptitle(f"{EVENT}: can any change threshold beat a single date? "
                 f"({args.ref} reference)")
    fig.tight_layout()
    fig.savefig(FIGURES / "change_sweep.png", dpi=130)

    print("\nwrote change_sweep.csv and figures/change_sweep.png")


if __name__ == "__main__":
    main()
