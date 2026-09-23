"""
RS-02. Are the Indian labels drawn where the edges are?

At matched ground width the same sensor and the same method find Slovenian
parcels between 1.8 and 71.5 times more often than Indian ones. The leading
explanation is label geometry: India is presence-only with five parcels drawn
by hand per chip, Slovenia is a complete cadastre, and IoU against a loosely
placed polygon is depressed whatever the imagery shows. That explanation has
been asserted in three documents and measured in none.

This measures it without needing a second set of labels to compare against.

Take the parcel's boundary and walk it inward and outward along its own normal,
one pixel at a time, sampling the image gradient on each ring. A boundary drawn
in the right place peaks at zero. A boundary traced inside the true field peaks
outward. The headline number is the gain: how much stronger the best nearby
edge is than the edge at the drawn position. A well-placed label gains nothing,
because there is nothing better to move to.

The gain is a ratio, so it compares across countries whatever the grid. The
displacement behind it is quoted in metres, and the two countries resolve it
differently, 6.067 m per pixel in India against 4.139 m in Slovenia.

Two failures are recorded here because both changed the design. B-13 was a
rigid translation search across a 49-offset window, which put 64% of parcels
at the edge of the window and matched its own null to within 2.7 m: shifting a
band across a 6-pixel-wide parcel carries it onto the neighbours, so it found
whichever direction held more edges. B-14 was in this version's geometry. The
signed distance transform has no pixel closer than 1 to the boundary, so a ring
cut at radius zero with half-width 0.5 selected nothing, the drawn position was
scored nan and could never win, and the smallest displacement the run could
report was a whole pixel. The +-1 gap is collapsed below before any ring is cut.

The same walk runs against a gradient field borrowed from another chip, where
no ring can be right. That is what picking the best of seven returns on noise.

This reruns no model. Labels and imagery are already on disk.

    python src\\label_registration.py --self-test
    python src\\label_registration.py --country india
    python src\\label_registration.py --country slovenia
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

# Rings at whole grid pixels, inward and outward. Whole pixels because that is
# all the imagery supports: the median Indian parcel is about six pixels
# across, so asking where its edge sits to a third of a pixel is asking for
# precision the grid does not carry.
RING_PX = np.arange(-3.0, 3.01, 1.0)
RING_HALF_PX = 0.5
MIN_RING_PIXELS = 8

WIDTH_EDGES_M = [0, 20, 30, 50, np.inf]
WIDTH_LABELS_M = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def signed_distance(mask: np.ndarray) -> np.ndarray:
    """Distance from the drawn boundary, negative inside and positive outside.

    The raw difference of the two transforms reads +1 on the first pixel
    outside and -1 on the last pixel inside, with nothing between them, so a
    ring cut at zero would select no pixels at all. Collapsing that gap puts
    the boundary band at zero, where it belongs. This is B-14.
    """
    from scipy.ndimage import distance_transform_edt
    raw = (distance_transform_edt(~mask).astype(np.float32)
           - distance_transform_edt(mask).astype(np.float32))
    return np.where(raw > 0, raw - 1.0, raw + 1.0).astype(np.float32)


def interior_contrast(mask, grad, chip_median):
    """Gradient inside the parcel, away from its own boundary.

    The contrast figures elsewhere in this project divide by the chip's median
    gradient, and stage 2 found four of five Indian chips are called mostly
    boundary, so that denominator may be inflated by texture rather than
    measuring a calm background. Dividing the edge by the parcel's own interior
    removes the chip from the comparison entirely. A parcel too narrow to
    survive two erosions returns nan rather than a number built from its edge.
    """
    from scipy.ndimage import binary_erosion
    core = binary_erosion(mask, iterations=2)
    if int(core.sum()) < MIN_RING_PIXELS or chip_median <= 0:
        return np.nan
    return float(grad[core].mean() / chip_median)


def profile(signed, grad, chip_median):
    """Mean gradient on each ring, relative to the chip's own median.

    A ring that collapses to a handful of pixels inside a small parcel returns
    nan rather than a number built from four samples.
    """
    out = np.full(len(RING_PX), np.nan, dtype=np.float32)
    if chip_median <= 0:
        return out
    for i, r in enumerate(RING_PX):
        ring = np.abs(signed - r) <= RING_HALF_PX
        if int(ring.sum()) >= MIN_RING_PIXELS:
            out[i] = grad[ring].mean() / chip_median
    return out


def peak(prof):
    """Where the profile peaks, and how much better that is than the drawn edge."""
    zero = int(np.argmin(np.abs(RING_PX)))
    ok = np.isfinite(prof)
    if ok.sum() < 3 or not ok[zero]:
        return np.nan, np.nan, np.nan
    idx = np.flatnonzero(ok)
    best = idx[np.argmax(prof[idx])]
    return float(RING_PX[best]), float(prof[best]), float(prof[zero])


def measure(chips, px_m):
    """One row per parcel: where its gradient peaks against where it was drawn."""
    import compare_segmenters as C
    import seg_score as S

    rows, tic = [], time.time()
    previous = None                      # a gradient field from another chip

    for i, chip in enumerate(chips, 1):
        try:
            stack = C.read_stack(chip)
        except FileNotFoundError as exc:
            print(f"  skipping {chip}: {exc}")
            continue
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        grad = C.gradient(stack)
        med = float(np.median(grad))
        null_pair, previous = previous, (grad, med)

        for pid in np.unique(full[full > 0]):
            mask = full == pid
            signed = signed_distance(mask)
            prof = profile(signed, grad, med)
            off, best, drawn = peak(prof)
            if not np.isfinite(off):
                continue
            inner = interior_contrast(mask, grad, med)
            row = {
                "country": F.COUNTRY,
                "chip": chip,
                "parcel_id": int(pid),
                "width_native_px": round(S.parcel_width_px(mask) * px_m / 10.0, 3),
                "offset_px": round(off, 1),
                "offset_m": round(off * px_m, 2),
                "drawn_contrast": round(drawn, 4),
                "peak_contrast": round(best, 4),
                "gain": round(best / drawn, 4) if drawn > 0 else np.nan,
                "interior_contrast": round(inner, 4) if np.isfinite(inner) else np.nan,
                "edge_over_interior": (round(drawn / inner, 4)
                                       if np.isfinite(inner) and inner > 0
                                       else np.nan),
            }
            # Keep the whole walk, so a question about the shape of the
            # profile never needs another four minutes of gradient building.
            for k, r in enumerate(RING_PX):
                row[f"ring_{int(r):+d}"] = (round(float(prof[k]), 4)
                                            if np.isfinite(prof[k]) else np.nan)
            if null_pair is not None:
                noff, nbest, ndrawn = peak(
                    profile(signed, null_pair[0], null_pair[1]))
                row["null_offset_px"] = round(noff, 1) if np.isfinite(noff) else np.nan
                row["null_gain"] = (round(nbest / ndrawn, 4)
                                    if np.isfinite(ndrawn) and ndrawn > 0
                                    else np.nan)
            rows.append(row)

        if i % 25 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            left = (len(chips) - i) / rate if rate else 0
            print(f"    {i:>4,} / {len(chips):,}   {rate:.1f} chips/s   "
                  f"{left / 60:.1f} min left")
    return rows


def summarise(rows, px_m) -> None:
    import pandas as pd
    df = pd.DataFrame(rows).dropna(subset=["offset_px"])
    if df.empty:
        sys.exit("no parcels measured")
    off = df["offset_px"]
    limit = RING_PX.max()

    print("\n" + RULE)
    print(f"RESULT, {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  {len(df):,} parcels, grid {px_m:.3f} m, rings at whole pixels "
          f"from {-limit:.0f} to {limit:+.0f}")
    print(f"  which is {-limit * px_m:.1f} m to {limit * px_m:+.1f} m on the "
          f"ground here\n")

    print(f"  THE GAIN, best nearby edge over the drawn edge")
    print(f"    median                          {df['gain'].median():.3f}x")
    print(f"    share gaining less than 1.05x   "
          f"{float((df['gain'] < 1.05).mean()) * 100:.1f}%")
    if "null_gain" in df.columns and df["null_gain"].notna().any():
        print(f"    same figure on a borrowed field {df['null_gain'].median():.3f}x")

    if "edge_over_interior" in df.columns:
        e = df["edge_over_interior"].dropna()
        if len(e):
            print(f"\n  EDGE OVER THE PARCEL'S OWN INTERIOR")
            print(f"    median                          {e.median():.3f}x")
            print(f"    p25 to p75                      "
                  f"{e.quantile(.25):.3f}x to {e.quantile(.75):.3f}x")
            print(f"    share at or below 1.0           "
                  f"{float((e <= 1.0).mean()) * 100:.1f}% "
                  f"(edge no stronger than the field)")
            print(f"    parcels wide enough to measure  {len(e):,} of {len(df):,}")

    print(f"\n  DISPLACEMENT")
    print(f"    peak sits on the drawn edge     "
          f"{float((off == 0).mean()) * 100:.1f}% of parcels")
    print(f"    within one pixel of it          "
          f"{float((off.abs() <= 1).mean()) * 100:.1f}%")
    print(f"    median, unsigned                "
          f"{off.abs().median() * px_m:.2f} m")
    print(f"    mean, signed                    "
          f"{off.mean() * px_m:+.2f} m (positive is drawn inside the edge)")
    print(f"    pinned at the search limit      "
          f"{float((off.abs() >= limit).mean()) * 100:.1f}%")

    if "null_offset_px" in df.columns:
        n = df.dropna(subset=["null_offset_px"])
        if len(n):
            print(f"\n  the same walk on a gradient field from another chip:")
            print(f"    peak on the drawn edge          "
                  f"{float((n['null_offset_px'] == 0).mean()) * 100:.1f}%")
            print(f"    pinned at the search limit      "
                  f"{float((n['null_offset_px'].abs() >= limit).mean()) * 100:.1f}%")

    print("\n  by parcel width")
    band = pd.cut(df["width_native_px"] * 10.0, WIDTH_EDGES_M,
                  labels=WIDTH_LABELS_M, right=False)
    print(f"    {'width':>12} {'parcels':>8} {'median gain':>12} "
          f"{'on the edge':>12} {'signed mean':>13} {'edge/interior':>14}")
    for lab in WIDTH_LABELS_M:
        s = df[band == lab]
        if not len(s):
            continue
        eoi = s["edge_over_interior"].median() if "edge_over_interior" in s else np.nan
        eoi_txt = f"{eoi:>13.3f}x" if np.isfinite(eoi) else f"{'':>14}"
        print(f"    {lab:>12} {len(s):>8,} {s['gain'].median():>11.3f}x "
              f"{float((s['offset_px'] == 0).mean()) * 100:>11.1f}% "
              f"{s['offset_px'].mean() * px_m:>+12.2f} m {eoi_txt}")


def self_test(trials: int = 300, seed: int = 11) -> bool:
    """Can this recover a displacement it was given?

    Two failed designs went before this one, so the estimator is checked
    against synthetic parcels whose true edge offset is known before it is
    pointed at real labels. A square field is drawn, its label is placed either
    on the edge or a known distance inside it, and the walk has to tell the two
    apart across a range of parcel sizes, blurs and noise levels.

    The case that matters is the correctly drawn label. An estimator that
    invents displacement where there is none would read every Indian parcel as
    badly drawn and prove exactly the thing it was built to test.
    """
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    got = {0: [], 2: []}

    for _ in range(trials):
        size, c = 80, 40
        half = int(rng.integers(3, 18))
        blur = float(rng.uniform(0.5, 1.6))
        noise = float(rng.uniform(0.0, 0.12))
        for true_off in (0, 2):
            r = half + true_off
            img = np.zeros((size, size), np.float32)
            img[c - r:c + r, c - r:c + r] = 1.0
            img = gaussian_filter(img, blur) + rng.normal(0, noise, (size, size))
            gy, gx = np.gradient(img.astype(np.float32))
            grad = np.hypot(gy, gx)
            mask = np.zeros((size, size), bool)
            mask[c - half:c + half, c - half:c + half] = True
            off, best, drawn = peak(profile(signed_distance(mask), grad,
                                            float(np.median(grad)) or 1e-6))
            if np.isfinite(off):
                got[true_off].append((off, best / drawn))

    print(RULE)
    print(f"SELF TEST, {trials} synthetic parcels at each offset")
    print(RULE)
    ok = True
    for true_off in (0, 2):
        offs = np.array([o for o, _ in got[true_off]])
        gains = np.array([g for _, g in got[true_off]])
        hit = float((offs == true_off).mean()) if true_off == 0 else \
            float((offs >= 1).mean())
        flagged = float((gains > 1.05).mean())
        label = ("drawn on the edge" if true_off == 0
                 else "drawn 2 px inside the edge")
        print(f"  {label:<28} n={len(offs):>4}")
        print(f"    recovered correctly        {hit * 100:5.1f}%")
        print(f"    median gain                {np.median(gains):.3f}x")
        print(f"    share flagged above 1.05x  {flagged * 100:5.1f}%")
        if true_off == 0:
            ok &= hit > 0.95 and flagged < 0.05
        else:
            ok &= hit > 0.95 and flagged > 0.95

    print(f"\n  {'PASS' if ok else 'FAIL'}: a correct label has to read as "
          f"correct and a displaced one as displaced.")
    print(RULE)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true",
                    help="check the estimator against known displacements")
    ap.add_argument("--country", default="india")
    ap.add_argument("--ref-tag", default="3class_full")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--recompute", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    px_m = F.grid_pixel_m()
    out = F.RESULTS / "label_registration.csv"

    print(RULE)
    print(f"LABEL REGISTRATION, {F.COUNTRY.upper()}")
    print(RULE)

    if out.exists() and not args.recompute:
        import pandas as pd
        rows = pd.read_csv(out).to_dict("records")
        print(f"  reusing {out.name}, {len(rows):,} parcels "
              f"(--recompute to measure again)")
    else:
        pred_dir = F.RESULTS / f"pred_{args.ref_tag}"
        if not pred_dir.exists():
            sys.exit(f"{pred_dir} not found, so I cannot match the chip list")
        chips = [p.name for p in sorted(pred_dir.glob("*.tif"))]
        if args.limit:
            chips = chips[:args.limit]
        print(f"  measuring {len(chips):,} chips\n")
        rows = measure(chips, px_m)
        if not rows:
            sys.exit("no parcels measured")
        import pandas as pd
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\n  wrote {out.relative_to(F.PROJECT)}, {len(rows):,} parcels")

    summarise(rows, px_m)

    print("\n" + RULE)
    print("The gain is the number to compare between countries, because it is")
    print("a ratio and does not care that the two grids differ. Read it beside")
    print("the borrowed-field line: whatever that returns is what best-of-seven")
    print("yields on noise, and the measurement is worth the difference.")
    print(RULE)
    print("What this cannot do is prove a label wrong. A field whose edge is")
    print("genuinely invisible has no gradient to peak on, and a boundary")
    print("drawn perfectly there still reads as displaced. It is a comparison")
    print("between countries rather than a verdict on a parcel.")
    print(RULE)


if __name__ == "__main__":
    main()
