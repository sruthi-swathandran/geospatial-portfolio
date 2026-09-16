"""
RS-02. What the label values mean, and what a pixel is worth in metres.

This characterises the shipped rasters. It does NOT measure parcel size: that
belongs to measure_fields.py, which reads every chip and reconstructs the
parcel from its interior and eroded ring. An earlier version of this script
reported a size distribution from the instance mask over 200 chips, which
disagreed with measure_fields.py by a third because it was measuring a
different thing. One question, one script.

    A  the dataset's own JSON, treated as a claim rather than an answer
    B  the three label rasters cross-tabulated pixel by pixel
    C  what that means for scoring
    D  how the imagery got onto a grid finer than the sensor

Country comes from FTW_COUNTRY, defaulting to india. Writes one file,
results/<country>/interpolation_check.csv.

    python src\\inspect_labels.py
    python src\\inspect_labels.py --chips 300
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
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
    return f"{x * 100:.2f}%"


# ------------------------------------------------------ A. the dataset's JSON
def show_json():
    print(RULE)
    print("A. WHAT THE DATASET SAYS ABOUT ITSELF")
    print(RULE)
    files = sorted(F.DATA.glob("*.json"))
    if not files:
        print("  no JSON found next to the data")
        return
    src = files[0]
    print(f"  {src.name}  ({src.stat().st_size:,} bytes)\n")
    try:
        obj = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        print(f"  could not parse: {exc}")
        return

    # The grid polygons are long and say nothing about labels, so summarise.
    grids = obj.pop("grids", None)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    for line in text.splitlines():
        print("  " + line)
    if grids:
        print(f"\n  plus {len(grids)} grid polygons "
              f"({', '.join(g.get('id', '?') for g in grids)}), omitted here")

    print("\n  Treat this as the dataset's claim. Section B checks it against")
    print("  the pixels, because documentation and files drift apart.")


# ---------------------------------------------- B. what the label values are
def crosstab(n):
    print("\n" + RULE)
    print("B. THE THREE LABEL RASTERS, CROSS-TABULATED PIXEL BY PIXEL")
    print(RULE)

    names = F.chip_names()[:n]
    tally = Counter()
    total = 0
    labelled_frac = []

    for name in names:
        try:
            inst = F.read_band(F.INSTANCE / name)
            c2 = F.read_band(F.C2_DIR / name).astype(np.int16)
            c3 = F.read_band(F.C3_DIR / name).astype(np.int16)
        except Exception:                                     # noqa: BLE001
            continue
        has = (inst > 0).astype(np.int16)
        code = has * 10_000 + c2 * 100 + c3
        vals, cnts = np.unique(code, return_counts=True)
        for v, c in zip(vals.tolist(), cnts.tolist()):
            tally[v] += c
        total += inst.size
        labelled_frac.append(float((c2 != F.C2_UNLABELLED).mean()))

    if not total:
        print("  nothing read")
        return None

    print(f"  {len(labelled_frac):,} chips, {total:,} pixels\n")
    print(f"  {'instance':<10}{'2class':<9}{'3class':<9}"
          f"{'pixels':>16}{'share':>10}")
    for code, c in sorted(tally.items(), key=lambda kv: -kv[1]):
        has, c2, c3 = code // 10_000, (code // 100) % 100, code % 100
        print(f"  {'parcel' if has else 'none':<10}{c2:<9}{c3:<9}"
              f"{c:>16,}{pct(c / total):>10}")

    wf = np.array(labelled_frac)
    print(f"\n  share of each chip carrying any label at all: "
          f"median {pct(float(np.median(wf)))}, mean {pct(float(wf.mean()))}")
    return tally, total


# ------------------------------------------------------------ C. the reading
def read_crosstab(res):
    print("\n" + RULE)
    print("C. WHAT THAT MEANS FOR SCORING")
    print(RULE)
    if not res:
        return
    tally, total = res

    by_c2, by_c3 = Counter(), Counter()
    for code, c in tally.items():
        by_c2[(code // 100) % 100] += c
        by_c3[code % 100] += c

    names = {F.C3_BACKGROUND: "verified background",
             F.C3_INTERIOR: "parcel interior",
             F.C3_BOUNDARY: "boundary ring",
             F.C3_UNLABELLED: "unlabelled"}
    print("  from semantic_3class, which is the one that can tell background")
    print("  from boundary:\n")
    for v in sorted(by_c3):
        print(f"    {v}  {names.get(v, '?'):<22}{by_c3[v]:>14,}"
              f"  {pct(by_c3[v] / total)}")

    print("\n  from semantic_2class, where 0 means background OR boundary and")
    print("  cannot say which:\n")
    for v in sorted(by_c2):
        lab = {F.C2_NOT_FIELD: "not field", F.C2_INTERIOR: "parcel interior",
               F.C2_UNLABELLED: "unlabelled"}.get(v, "?")
        print(f"    {v}  {lab:<22}{by_c2[v]:>14,}  {pct(by_c2[v] / total)}")

    unlab = by_c3.get(F.C3_UNLABELLED, 0) / total
    ring = by_c3.get(F.C3_BOUNDARY, 0) / total
    bg = by_c3.get(F.C3_BACKGROUND, 0) / total
    interior = by_c3.get(F.C3_INTERIOR, 0) / total

    print()
    if unlab > 0.5:
        print(f"  PRESENCE-ONLY. {pct(unlab)} of every chip is unlabelled")
        print(f"  ground, which is not a class and not background. Parcel")
        print(f"  interior is {pct(interior)}, the boundary ring {pct(ring)},")
        print(f"  and verified background {pct(bg)}.")
        print()
        print("  With no ground certified field-free, precision cannot be")
        print("  measured. Score only where 3class is 1 or 2, exclude 3, and")
        print("  report recall and boundary agreement. Counting 3 as")
        print("  background charges a false positive for every real parcel")
        print("  found outside the drawn ones, and chip_sparsity shows that")
        print("  ground is full of real parcels.")
    elif unlab > 0.01:
        print(f"  MOSTLY COMPLETE. {pct(unlab)} is unlabelled, so some ground")
        print(f"  is unchecked but most of each chip carries a real label.")
        print(f"  Precision is measurable if 3 is excluded from the")
        print(f"  denominator rather than counted as background.")
    else:
        print(f"  COMPLETE LABELS. Only {pct(unlab)} is unlabelled. Parcel")
        print(f"  interior is {pct(interior)}, boundary ring {pct(ring)}, and")
        print(f"  {pct(bg)} is verified background, checked and found empty.")
        print()
        print("  Precision, recall and IoU all mean what they usually mean")
        print("  here, which is what makes this a control for a presence-only")
        print("  country.")
        print()
        print(f"  Note the 2-class table above. Its value 0 covers "
              f"{pct(by_c2.get(F.C2_NOT_FIELD, 0) / total)} because it lumps")
        print("  background in with the ring. Anything keyed off that value")
        print("  treats open ground as parcel boundary, which is exactly the")
        print("  bug this project shipped once and had to undo.")


# --------------------------------------- D. was the imagery put on a finer grid
def interpolation_test(n=40):
    print("\n" + RULE)
    print("D. HOW THE IMAGERY GOT ONTO ITS GRID")
    print(RULE)

    names = F.chip_names()[:n]
    if not names:
        print("  no chips found")
        return

    px_m = F.grid_pixel_m(names)
    eq_h, eq_v, ratio = [], [], []
    for name in names:
        p = F.IMG_A / name
        if not p.exists():
            continue
        with rasterio.open(p) as s:
            b = s.read(min(4, s.count)).astype(np.int32)   # NIR, most contrast
        eq_h.append(float((b[:, 1:] == b[:, :-1]).mean()))
        eq_v.append(float((b[1:, :] == b[:-1, :]).mean()))
        d1 = np.abs(np.diff(b, n=1, axis=1)).mean()
        if d1 > 0:
            ratio.append(float(np.abs(b[:, 2:] - b[:, :-2]).mean() / d1))

    if not eq_h:
        print("  no imagery found")
        return

    eq_h, eq_v = np.array(eq_h), np.array(eq_v)
    dup = float((eq_h.mean() + eq_v.mean()) / 2)
    expected_nn = max(0.0, 1.0 - px_m / F.NATIVE_M)

    print(f"  {len(eq_h)} chips, NIR band, grid pixel {px_m:.3f} m\n")
    print(f"  adjacent pixels exactly equal, across: {pct(float(eq_h.mean()))}")
    print(f"  adjacent pixels exactly equal, down:   {pct(float(eq_v.mean()))}")
    if ratio:
        print(f"  mean |lag 2 difference| / |lag 1 difference|: "
              f"{np.mean(ratio):.2f}")

    print()
    if px_m >= F.NATIVE_M - 0.2:
        print(f"  The grid is {px_m:.2f} m, at or coarser than Sentinel-2's")
        print(f"  {F.NATIVE_M:.0f} m, so nothing was invented by upsampling.")
    else:
        print(f"  The grid is {px_m:.2f} m and Sentinel-2's finest bands sample")
        print(f"  at {F.NATIVE_M:.0f} m, so the imagery was put on a grid finer")
        print(f"  than the sensor. Nearest-neighbour resampling would leave")
        print(f"  about {pct(expected_nn)} of neighbours as exact duplicates.")
        print(f"  Measured: {pct(dup)}.")
        if dup > 0.25:
            print("\n  That is duplication, so nearest neighbour was used and a")
            print("  model here is shown blocks rather than detail.")
        elif dup < 0.05:
            print("\n  Almost none, so a smooth interpolator was used. The")
            print("  pixels differ while carrying no information finer than")
            print(f"  {F.NATIVE_M:.0f} m. An edge that looks sharp at this")
            print("  scale was drawn by the interpolator, not observed.")
        else:
            print("\n  Between the two. Look at a chip before concluding.")
        if ratio and np.mean(ratio) > 1.7:
            print("\n  The lag-2 to lag-1 ratio above 1.7 agrees: short-range")
            print("  differences are suppressed relative to longer ones, which")
            print("  is what interpolation onto a finer grid does.")

    out = F.RESULTS / "interpolation_check.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["quantity", "value"])
        w.writerow(["country", F.COUNTRY])
        w.writerow(["chips_read", len(eq_h)])
        w.writerow(["grid_pixel_m", round(px_m, 4)])
        w.writerow(["native_pixel_m", F.NATIVE_M])
        w.writerow(["adjacent_equal_across", round(float(eq_h.mean()), 6)])
        w.writerow(["adjacent_equal_down", round(float(eq_v.mean()), 6)])
        w.writerow(["adjacent_equal_mean", round(dup, 6)])
        w.writerow(["expected_if_nearest_neighbour", round(expected_nn, 6)])
        if ratio:
            w.writerow(["lag2_over_lag1", round(float(np.mean(ratio)), 4)])
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chips", type=int, default=200)
    args = ap.parse_args()

    show_json()
    res = crosstab(args.chips)
    read_crosstab(res)
    interpolation_test()

    print("\n" + RULE)
    print("Section C decides how anything here can be scored. Parcel size is")
    print("measured by measure_fields.py, not here, so that one quantity has")
    print("one source.")
    print(RULE)


if __name__ == "__main__":
    main()
