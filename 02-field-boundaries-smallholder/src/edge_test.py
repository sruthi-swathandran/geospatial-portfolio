"""
RS-02. Weaker edges as a cause, tested on Slovenia.

The README's open question is why FTW reads Indian field edges so much worse
than Slovenian ones. The lead suspect is contrast: the labelled Indian
boundaries carry a weaker image gradient relative to their own interior, a
median of 1.297 against 1.588 in Slovenia (edge_over_interior in
label_registration.csv). One analyst's blind check agreed with that measure
only weakly (F-14). This tests the suspicion from the other side. If weak edges
cost a model this much, softening Slovenia's edges until they measure like
India's should cost it a large part of the gap.

What it does
------------
Slovenia's labelled test chips are split at random, seed 20261024, into 60
calibration chips and the rest for scoring.

  calibrate  Blurs the calibration chips with a Gaussian of rising width,
             isotropic on the ground, every band of both windows, and measures
             edge_over_interior on their labelled parcels exactly as
             label_registration.py does. The width at which the median falls
             to India's 1.297 is read off by linear interpolation and rounded
             to half a metre. Choosing it on chips that are never scored keeps
             the choice from leaning on the result.
  run        Scores the remaining chips at no blur and at that width, with FTW
             v3 B7, loaded as newer_checkpoints.py loads it, and watershed at
             h 0.05, Slovenia's best setting. Objects under 500 m2 are dropped
             and a parcel is found at IoU 0.5, as everywhere else.
  report     Reads the result against the rules below.

The blurred images are never written out. Each band is blurred on its raw
values and rounded back to its stored type, so FTW and watershed see what a
blurred file would hold.

How it will be read, set before running
---------------------------------------
For a method and its parcels 20 m and wider, with S0 Slovenia's recall at no
blur, S1 at the calibrated blur and I India's recall from the full Indian test
set at that method's own setting (v3 B7; watershed at India's best, h 0.02, as
in the width tables), the share of the gap closed is

    (S0 - S1) / (S0 - I)

with a 95% interval from resampling the scoring chips 2,000 times, the same
resample for S0 and S1. India's figure is held fixed. For all parcels 20 m and
wider together, India's recall is standardised to Slovenia's mix of widths:
each band's Indian recall weighted by the Slovenian parcels in that band, so a
difference in the mix of widths cannot pass for a difference in recall.

  E0  The pipeline is right if, at no blur, every scoring parcel's found or
      not matches results/slovenia/newer_ckpt/v3_full_b7_parcels.csv for v3
      and parcel_width_seg_watershed_0p05_min500.csv for watershed. If not,
      nothing else is read.
  E1  The calibration holds if the scoring chips' median edge_over_interior at
      the chosen blur is within 0.05 of 1.297.
  E2  Weak edges are a credible main cause, for a method, if the share closed
      is 0.5 or more with a lower end of 0.25 or more.
  E3  They are a minor cause at most if the upper end is below 0.25.
  E4  Anything else is partial, and is reported as that.

What it cannot show: a blurred Slovenian image is not an Indian one. Blur
lowers edge contrast and also smooths texture inside fields and across them.
A large share closed would show that this model depends on edge contrast
enough to explain the gap, not that weak edges are what India has. A small
one would show that edge contrast of India's level does not, on its own, stop
the model in Slovenia.

Outputs
-------
  results/slovenia/edge_test_calibration.csv  blur width against median edge
                                              ratio, calibration chips
  results/slovenia/edge_test_parcels.csv      one row per parcel, method and
                                              blur
  results/slovenia/edge_test_chips.csv        objects per chip, method and blur
  results/edge_test.csv                       the reading, per method and band

Usage
-----
    python src\\edge_test.py --part calibrate
    python src\\edge_test.py --part run
    python src\\edge_test.py --part report
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import season_test as T                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

RULE = "=" * 78
N_CALIBRATION = 60
SIGMAS_M = [0, 2, 4, 6, 8, 10, 12, 15, 18, 24]
INDIA_EOI = 1.297
CALIBRATION_TOL = 0.05
WATERSHED_H = 0.05
CHECKPOINT = "v3 full b7"
MIN_M = 20.0
BANDS = [("20 to 30 m", 20, 30), ("30 to 50 m", 30, 50), ("50 m up", 50, np.inf),
         ("20 m up", 20, np.inf)]
METHODS = ("FTW v3 B7", "watershed")


def split(F, seed: int) -> tuple:
    """Labelled Slovenian test chips, shuffled once, calibration first."""
    path = F.RESULTS / "newer_ckpt" / "v3_full_b7_chips.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        chips = sorted(r["chip"] for r in csv.DictReader(fh) if int(r["parcels"]) > 0)
    order = np.random.default_rng(seed).permutation(len(chips))
    chips = [chips[i] for i in order]
    return chips[:N_CALIBRATION], chips[N_CALIBRATION:]


def raw_windows(F, chip: str) -> dict:
    import rasterio
    out = {}
    for key, folder in (("a", F.IMG_A), ("b", F.IMG_B)):
        if (folder / chip).exists():
            with rasterio.open(folder / chip) as s:
                out[key] = s.read()
    return out


def blur(raws: dict, sigma_m: float, x_m: float, y_m: float) -> dict:
    """Gaussian blur of sigma_m metres on the ground, every band, rounded back
    to the stored type. Pixels are 4.14 m wide and 6.00 m tall in Slovenia, so
    the width in pixels differs by axis."""
    if sigma_m <= 0:
        return raws
    from scipy.ndimage import gaussian_filter
    out = {}
    for key, arr in raws.items():
        info = np.iinfo(arr.dtype) if np.issubdtype(arr.dtype, np.integer) else None
        b = np.empty_like(arr)
        for i, band in enumerate(arr):
            f = gaussian_filter(band.astype(np.float64),
                                sigma=(sigma_m / y_m, sigma_m / x_m), mode="reflect")
            b[i] = (np.clip(np.rint(f), info.min, info.max) if info else f)
        out[key] = b
    return out


def gradient_of(C, raws: dict) -> tuple:
    """The stack compare_segmenters.read_stack builds, window a then b."""
    parts = [np.stack([C.stretch(b) for b in raws[k]]) for k in ("a", "b") if k in raws]
    stack = np.concatenate(parts, axis=0)
    return stack, C.gradient(stack)


def ftw_input(raws: dict):
    """What season_test.stacked_image gives FTW: window b then a, over 3000."""
    import torch
    img = np.concatenate([raws["b"], raws["a"]], axis=0).astype(np.int32)
    return torch.from_numpy(img).float() / 3000


def edge_ratios(LR, full, grad, x_m, y_m) -> dict:
    """edge_over_interior per parcel, as label_registration.measure has it."""
    med = float(np.median(grad))
    out = {}
    for pid in np.unique(full[full > 0]):
        mask = full == pid
        prof = LR.profile(LR.signed_distance(mask, x_m, y_m), grad, med)
        off, _, drawn = LR.peak(prof)
        if not np.isfinite(off):
            continue
        inner = LR.interior_contrast(mask, grad, med)
        if np.isfinite(inner) and inner > 0:
            out[int(pid)] = drawn / inner
    return out


def write(path: Path, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ calibrate
def calibrate(args) -> None:
    F, C, S = T.load_country("slovenia")
    import label_registration as LR
    cal, _ = split(F, args.seed)
    print(RULE)
    print(f"CALIBRATION, {len(cal)} Slovenian chips, target median {INDIA_EOI}")
    print(RULE)
    per_sigma = {s: [] for s in SIGMAS_M}
    tic = time.time()
    for i, chip in enumerate(cal, 1):
        raws = raw_windows(F, chip)
        _, _, _, full = F.load_labels(chip)
        x_m, y_m = F.chip_pixel_xy_m(chip)
        for s in SIGMAS_M:
            _, grad = gradient_of(C, blur(raws, s, x_m, y_m))
            per_sigma[s] += list(edge_ratios(LR, full, grad, x_m, y_m).values())
        if i % 10 == 0 or i == len(cal):
            print(f"    {i:>3} / {len(cal)}   {(time.time() - tic) / 60:.1f} min")
    rows = [dict(sigma_m=s, parcels=len(v), median_edge_over_interior=round(float(np.median(v)), 4))
            for s, v in per_sigma.items()]
    meds = np.array([r["median_edge_over_interior"] for r in rows])
    sig = np.array(SIGMAS_M, float)
    below = np.flatnonzero(meds <= INDIA_EOI)
    chosen = ""
    if below.size and below[0] > 0:
        j = below[0]
        t = (meds[j - 1] - INDIA_EOI) / (meds[j - 1] - meds[j])
        chosen = round((sig[j - 1] + t * (sig[j] - sig[j - 1])) * 2) / 2
    for r in rows:
        r["chosen_sigma_m"] = chosen
    write(F.RESULTS / "edge_test_calibration.csv", rows)
    print(f"\n  {'blur, m':>8} {'parcels':>8} {'median edge ratio':>18}")
    for r in rows:
        print(f"  {r['sigma_m']:>8} {r['parcels']:>8} {r['median_edge_over_interior']:>18}")
    if chosen == "":
        sys.exit("\n  the median never reaches India's; widen SIGMAS_M. Nothing chosen.")
    print(f"\n  chosen blur: {chosen} m, written to edge_test_calibration.csv")


# ------------------------------------------------------------------------ run
def chosen_sigma(F) -> float:
    path = F.RESULTS / "edge_test_calibration.csv"
    if not path.exists():
        sys.exit("run --part calibrate first")
    with path.open(encoding="utf-8", newline="") as fh:
        return float(next(csv.DictReader(fh))["chosen_sigma_m"])


def run(args) -> None:
    import torch
    from scipy.ndimage import label as cc_label
    import newer_checkpoints as N
    F, C, S = T.load_country("slovenia")
    import label_registration as LR
    if args.threads:
        torch.set_num_threads(args.threads)
    _, test = split(F, args.seed)
    if args.limit:
        test = test[:args.limit]
    sigma = chosen_sigma(F)
    net = N.load_unet(F.PROJECT / "models" / N.CHECKPOINTS[CHECKPOINT]["file"])
    min_px = int(round(500.0 / F.grid_pixel_area_m2()))
    px_m = F.grid_pixel_m()
    print(RULE)
    print(f"SCORING, {len(test)} Slovenian chips, no blur and {sigma} m")
    print(RULE)
    parcels, chips_out = [], []
    tic = time.time()
    for i, chip in enumerate(test, 1):
        raws0 = raw_windows(F, chip)
        _, _, _, full = F.load_labels(chip)
        x_m, y_m = F.chip_pixel_xy_m(chip)
        for s in (0.0, sigma):
            raws = blur(raws0, s, x_m, y_m)
            stack, grad = gradient_of(C, raws)
            eoi = edge_ratios(LR, full, grad, x_m, y_m)
            with torch.inference_mode():
                pred = net(ftw_input(raws)[None]).argmax(dim=1)[0].numpy()
            lab, _ = cc_label(pred == 1)
            segs = {"FTW v3 B7": C.drop_small(lab.astype(np.int32), min_px),
                    "watershed": C.drop_small(C.segment(stack, grad, "watershed",
                                                        WATERSHED_H), min_px)}
            for method, seg in segs.items():
                chips_out.append(dict(sigma_m=s, method=method, chip=chip,
                                      objects=C.object_count(seg)))
                for r in S.rows_for_chip(chip, full, seg, F.COUNTRY, px_m,
                                         px_xy=(x_m, y_m)):
                    parcels.append(dict(
                        sigma_m=s, method=method, chip=chip,
                        parcel_id=r["parcel_id"],
                        width_m=round(r["width_native_px"] * 10.0, 2),
                        best_iou=r["best_iou"], found=r["found"],
                        edge_over_interior=(round(eoi[r["parcel_id"]], 4)
                                            if r["parcel_id"] in eoi else "")))
        if i % 10 == 0 or i == len(test):
            rate = i / (time.time() - tic)
            print(f"    {i:>3} / {len(test)}   {(len(test) - i) / rate / 60:.1f} min left")
    write(F.RESULTS / "edge_test_parcels.csv", parcels)
    write(F.RESULTS / "edge_test_chips.csv", chips_out)
    print(f"\n  wrote edge_test_parcels.csv and edge_test_chips.csv")


# --------------------------------------------------------------------- report
def report(args) -> None:
    import pandas as pd
    F, _, _ = T.load_country("slovenia")
    par = pd.read_csv(F.RESULTS / "edge_test_parcels.csv")
    obj = pd.read_csv(F.RESULTS / "edge_test_chips.csv")
    sigma = chosen_sigma(F)
    base = F.PROJECT / "results"

    # E0, against the published per-parcel files
    zero = par[par["sigma_m"] == 0]
    ref = {"FTW v3 B7": pd.read_csv(base / "slovenia" / "newer_ckpt" / "v3_full_b7_parcels.csv"),
           "watershed": pd.read_csv(base / "slovenia" / "parcel_width_seg_watershed_0p05_min500.csv")}
    e0 = True
    for m, r in ref.items():
        mine = zero[zero["method"] == m].set_index(["chip", "parcel_id"])["found"]
        theirs = r.set_index(["chip", "parcel_id"])["found"].reindex(mine.index)
        bad = int((mine != theirs).sum())
        print(f"  E0 {m:<10} {len(mine):>5} parcels, {bad} differ from the published file")
        e0 &= bad == 0
    if not e0:
        sys.exit("\n  E0 fails: the pipeline does not reproduce the published "
                 "results at no blur. Nothing else is read.")

    blurred = par[par["sigma_m"] == sigma]
    eoi = blurred.drop_duplicates(["chip", "parcel_id"])["edge_over_interior"].dropna()
    e1 = abs(float(eoi.median()) - INDIA_EOI) <= CALIBRATION_TOL
    print(f"  E1 scoring chips' median edge ratio at {sigma} m: {eoi.median():.4f} "
          f"against {INDIA_EOI}; {'holds' if e1 else 'does not hold'}")

    india = {"FTW v3 B7": pd.read_csv(base / "india" / "newer_ckpt" / "v3_full_b7_parcels.csv"),
             "watershed": pd.read_csv(base / "india" / "parcel_width_seg_watershed_min500.csv")}
    india["watershed"]["width_m"] = india["watershed"]["width_native_px"] * 10.0

    rng = np.random.default_rng(args.seed)
    rows = []
    for m in METHODS:
        a = par[(par["method"] == m) & (par["sigma_m"] == 0)].set_index(["chip", "parcel_id"])
        b = par[(par["method"] == m) & (par["sigma_m"] == sigma)].set_index(["chip", "parcel_id"])
        b = b.reindex(a.index)
        ia = india[m]
        for band, lo, hi in BANDS:
            sel = (a["width_m"] >= lo) & (a["width_m"] < hi)
            if band == "20 m up":
                # India standardised to Slovenia's width mix
                parts = [(int(((a["width_m"] >= l) & (a["width_m"] < h)).sum()),
                          ia[(ia["width_m"] >= l) & (ia["width_m"] < h)]["found"].mean())
                         for _, l, h in BANDS[:3]]
                iv = sum(n * r for n, r in parts) / sum(n for n, _ in parts)
            else:
                iv = ia[(ia["width_m"] >= lo) & (ia["width_m"] < hi)]["found"].mean()
            chips = a[sel].index.get_level_values(0)
            f0 = a[sel]["found"].groupby(chips).agg(["sum", "count"])
            f1 = b[sel]["found"].groupby(chips).sum().reindex(f0.index)
            s0 = f0["sum"].sum() / f0["count"].sum()
            s1 = f1.sum() / f0["count"].sum()
            share = (s0 - s1) / (s0 - iv) if s0 > iv else float("nan")
            k = len(f0)
            idx = rng.integers(0, k, size=(args.boots, k))
            n = f0["count"].to_numpy()[idx].sum(axis=1)
            b0 = f0["sum"].to_numpy()[idx].sum(axis=1) / n
            b1 = f1.to_numpy()[idx].sum(axis=1) / n
            with np.errstate(divide="ignore", invalid="ignore"):
                shares = (b0 - b1) / (b0 - iv)
            slo, shi = np.nanpercentile(shares, (2.5, 97.5))
            o0 = obj[(obj["method"] == m) & (obj["sigma_m"] == 0)]["objects"].mean()
            o1 = obj[(obj["method"] == m) & (obj["sigma_m"] == sigma)]["objects"].mean()
            reading = ""
            if band == "20 m up":
                reading = ("credible main cause" if share >= 0.5 and slo >= 0.25
                           else "minor cause at most" if shi < 0.25 else "partial")
            rows.append(dict(method=m, band=band, sigma_m=sigma, parcels=int(sel.sum()),
                             chips=k, slovenia_no_blur=round(s0, 4),
                             slovenia_blurred=round(s1, 4), india=round(iv, 4),
                             share_closed=round(share, 3), share_lo=round(slo, 3),
                             share_hi=round(shi, 3),
                             objects_no_blur=round(o0, 1), objects_blurred=round(o1, 1),
                             reading=reading))
    write(base / "edge_test.csv", rows)
    print(f"\n  {'method':<10} {'band':<11} {'Slovenia':>9} {'blurred':>8} {'India':>7} "
          f"{'share closed':>22} {'objects':>13}")
    for r in rows:
        print(f"  {r['method']:<10} {r['band']:<11} {r['slovenia_no_blur'] * 100:8.2f}% "
              f"{r['slovenia_blurred'] * 100:7.2f}% {r['india'] * 100:6.2f}% "
              f"{r['share_closed']:>7} [{r['share_lo']}, {r['share_hi']}] "
              f"{r['objects_no_blur']:>6}->{r['objects_blurred']:<6} {r['reading']}")
    print("\n  E2 to E4 are read on '20 m up'. India's recall is held fixed.")
    print(f"  wrote results/edge_test.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["calibrate", "run", "report"])
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--limit", type=int, default=0, help="run only: first n chips")
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()
    {"calibrate": calibrate, "run": run, "report": report}[args.part](args)


if __name__ == "__main__":
    main()
