"""
RS-01 / step 7d — which chips did the STAC fetch actually cover?

Across 68 chips the correlation against the dataset's own imagery ranges from
0.921 down to -0.029. A median of 0.58 with a minimum near zero is not one
population with scatter; it is two populations. Some chips agree well and some
do not agree at all, and the difference has a cause worth naming before any of
this feeds a change detector.

The leading suspect is coverage. We fetched three Sentinel-1 frames per date,
chosen because they cover the FLOOD acquisition footprint. The 68 label chips
span 1.56 x 1.61 degrees, and any chip falling outside those three frames comes
back empty or part-empty — odc.stac.load fills what it cannot read with NaN, and
a chip that is mostly NaN can still scrape past the "more than 1000 valid pixels"
guard with a handful of pixels that correlate with nothing.

This reads the report the fetch already wrote and answers three questions:

  1. How much of each chip is NaN, per date?
  2. Do the low-correlation chips line up with the high-NaN chips?
  3. Is the reference date covered as well as the flood date? The reference
     frames were selected on the same orbit but they are a different pass, so
     their footprint is close to — not identical to — the flood one.

If coverage explains it, the fix is more frames, not more processing.

Usage:
    python src\\triage_fetch.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RESULTS                      # noqa: E402

REPORT = RESULTS / "reference_fetch_report.csv"


def fnum(row: dict, key: str):
    v = row.get(key, "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"{REPORT} not found — run fetch_reference.py first")

    rows = list(csv.DictReader(REPORT.read_text().splitlines()))
    print(f"{len(rows)} chips in the fetch report\n")

    corr = np.array([fnum(r, "vh_corr_vs_S1Hand") for r in rows])
    bias = np.array([fnum(r, "vh_bias_db") for r in rows])
    ref_nan = np.array([fnum(r, "REF_nan_frac") for r in rows])
    fld_nan = np.array([fnum(r, "FLOODRTC_nan_frac") for r in rows])

    print("1. NO-DATA FRACTION PER CHIP")
    print("----------------------------")
    for name, arr in (("flood date", fld_nan), ("reference date", ref_nan)):
        ok = np.isfinite(arr)
        if not ok.any():
            print(f"  {name}: column missing")
            continue
        a = arr[ok]
        print(f"  {name:<16} median {np.median(a):.3f}   "
              f"p90 {np.percentile(a, 90):.3f}   max {a.max():.3f}")
        for cut in (0.05, 0.25, 0.50, 0.90):
            print(f"      chips with more than {cut:.0%} NaN: {(a > cut).sum():>3}")

    print("\n2. DOES LOW CORRELATION FOLLOW HIGH NO-DATA?")
    print("-------------------------------------------")
    ok = np.isfinite(corr) & np.isfinite(fld_nan)
    if ok.sum() > 3:
        r = float(np.corrcoef(corr[ok], fld_nan[ok])[0, 1])
        print(f"  correlation between (agreement) and (NaN fraction): {r:+.3f}")
        print("  Strongly negative means coverage explains it: the chips that "
              "disagree are\n  the chips we barely fetched.")

    bad = [r_ for r_, c in zip(rows, corr) if np.isfinite(c) and c < 0.30]
    good = [r_ for r_, c in zip(rows, corr) if np.isfinite(c) and c >= 0.70]
    print(f"\n  chips with correlation < 0.30: {len(bad)}")
    print(f"  chips with correlation >= 0.70: {len(good)}")
    if bad:
        print(f"\n  {'chip':<12}{'corr':>8}{'bias':>8}{'flood NaN':>12}{'ref NaN':>10}")
        for r_ in sorted(bad, key=lambda x: fnum(x, "vh_corr_vs_S1Hand"))[:15]:
            print(f"  {r_['chip_id']:<12}{fnum(r_, 'vh_corr_vs_S1Hand'):>8.3f}"
                  f"{fnum(r_, 'vh_bias_db'):>8.2f}"
                  f"{fnum(r_, 'FLOODRTC_nan_frac'):>12.3f}"
                  f"{fnum(r_, 'REF_nan_frac'):>10.3f}")

    print("\n3. USABLE SUBSET")
    print("----------------")
    usable = [r_ for r_, c, fn, rn in zip(rows, corr, fld_nan, ref_nan)
              if np.isfinite(c) and c >= 0.50
              and (not np.isfinite(fn) or fn < 0.05)
              and (not np.isfinite(rn) or rn < 0.05)]
    print(f"  chips with correlation >= 0.50 and under 5% NaN on both dates: "
          f"{len(usable)} of {len(rows)}")
    if usable:
        u_corr = np.array([fnum(r_, "vh_corr_vs_S1Hand") for r_ in usable])
        u_bias = np.array([fnum(r_, "vh_bias_db") for r_ in usable])
        print(f"  their correlation: median {np.median(u_corr):.3f}  "
              f"min {u_corr.min():.3f}")
        print(f"  their bias:        median {np.median(u_bias):+.2f} dB  "
              f"range {u_bias.min():+.2f} .. {u_bias.max():+.2f}")
        out = RESULTS / "usable_chips.txt"
        out.write_text("\n".join(r_["chip_id"] for r_ in usable))
        print(f"  wrote {out.name} — the chip list the change detector should use")

    print("\n  A change detector built on partly-empty chips would produce "
          "confident nonsense.\n  Better to state the covered subset and its "
          "size than to average over both.")


if __name__ == "__main__":
    main()
