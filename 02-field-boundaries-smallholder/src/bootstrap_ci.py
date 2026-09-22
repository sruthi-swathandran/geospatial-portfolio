"""
RS-02. Confidence intervals that account for parcels sharing a chip.

Every interval this project has quoted came from Clopper-Pearson on the parcel
count, which assumes each parcel is an independent observation. They are not.
India carries about five labelled parcels per chip and Slovenia about
thirty-seven, and parcels inside one chip share the scene, the season, the
cloud state, the upsampling and the annotator. When a chip goes badly its
parcels go badly together, so the effective sample size sits closer to the
number of chips than the number of parcels and the quoted intervals are
narrower than they should be.

This resamples chips rather than parcels. Draw the chip list with replacement,
pool whatever parcels those chips carry, recompute recall, repeat. The spread
of that distribution is the interval.

Both intervals are printed side by side, along with the ratio between their
widths, which is the honest measure of how much the old ones were overstating
precision. A ratio near one means clustering costs nothing for that figure. A
ratio of two means the interval should have been twice as wide.

It reads the per-parcel tables that already exist, so nothing is rerun.

    python src\\bootstrap_ci.py --country india
    python src\\bootstrap_ci.py --country india ^
        --table parcel_width_seg_sam_vit_h_true_0p50_min500.csv
    python src\\bootstrap_ci.py --country slovenia --by-width
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

WIDTH_EDGES = [0, 20, 30, 50, np.inf]
WIDTH_LABELS = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def clopper_pearson(found: int, total: int, alpha: float = 0.05):
    """The interval this project has been quoting, for comparison."""
    from scipy.stats import beta
    if total == 0:
        return float("nan"), float("nan")
    lo = 0.0 if found == 0 else beta.ppf(alpha / 2, found, total - found + 1)
    hi = (1.0 if found == total
          else beta.ppf(1 - alpha / 2, found + 1, total - found))
    return float(lo), float(hi)


def chip_bootstrap(df: pd.DataFrame, draws: int, rng, alpha: float = 0.05):
    """Resample whole chips with replacement, recompute recall each time.

    Parcels move with their chip, so a chip that fails entirely contributes
    all of its failures or none of them, which is the dependence the
    parcel-level interval ignores.
    """
    groups = [g["hit"].to_numpy() for _, g in df.groupby("chip", sort=False)]
    if len(groups) < 2:
        return float("nan"), float("nan"), 0
    counts = np.array([g.sum() for g in groups], dtype=float)
    sizes = np.array([g.size for g in groups], dtype=float)

    idx = rng.integers(0, len(groups), size=(draws, len(groups)))
    hit = counts[idx].sum(axis=1)
    tot = sizes[idx].sum(axis=1)
    rates = np.divide(hit, tot, out=np.zeros_like(hit), where=tot > 0)
    lo, hi = np.percentile(rates, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return float(lo), float(hi), len(groups)


# Below this many hits the percentile bootstrap stops working. With one hit
# in the whole set, most resamples miss the single chip that carries it and
# return zero, so the upper tail collapses and the interval comes out narrower
# than the parcel-level one rather than wider. Clopper-Pearson is exact and
# survives a zero count, so it governs those rows.
BOOTSTRAP_FLOOR = 10


def report(label: str, df: pd.DataFrame, draws: int, rng) -> None:
    found, total = int(df["hit"].sum()), len(df)
    if not total:
        return
    rate = found / total
    cl, ch = clopper_pearson(found, total)
    bl, bh, nchips = chip_bootstrap(df, draws, rng)

    thin = found < BOOTSTRAP_FLOOR
    # Report the union of the two. Neither method dominates the other at every
    # count, and the wider of the pair is the one a reader can rely on.
    ul, uh = min(cl, bl), max(ch, bh)
    ratio = (uh - ul) / (ch - cl) if ch > cl else float("nan")
    note = "few hits, parcel governs" if thin else f"{ratio:.2f}x wider"
    print(f"  {label:<14} {found:>5,}/{total:<6,} {rate * 100:6.2f}%   "
          f"[{cl * 100:5.2f}, {ch * 100:5.2f}]   "
          f"[{bl * 100:5.2f}, {bh * 100:5.2f}]   "
          f"[{ul * 100:5.2f}, {uh * 100:5.2f}]   {note}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--table", default="parcel_width_seg_ftw_min500.csv")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--draws", type=int, default=10000)
    ap.add_argument("--by-width", action="store_true",
                    help="also break the interval down by ground width")
    ap.add_argument("--seed", type=int, default=20260922)
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    path = F.RESULTS / args.table
    if not path.exists():
        sys.exit(f"{path} not found")

    df = pd.read_csv(path)
    for need in ("chip", "best_iou"):
        if need not in df.columns:
            sys.exit(f"{args.table} has no {need} column")
    df["hit"] = df["best_iou"] >= args.iou
    if "width_native_px" in df.columns:
        df["metres"] = df["width_native_px"] * 10.0

    rng = np.random.default_rng(args.seed)
    nchips = df["chip"].nunique()

    print(RULE)
    print(f"INTERVALS FOR {args.table}, {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  {len(df):,} parcels across {nchips:,} chips, "
          f"{len(df) / nchips:.1f} per chip")
    print(f"  {args.draws:,} bootstrap draws, seed {args.seed}\n")
    print(f"  {'':<14} {'found':>5} {'of':<7} {'rate':>7}   "
          f"{'parcel 95%':^16}   {'chip 95%':^16}   "
          f"{'report this':^16}   against parcel")

    report("overall", df, args.draws, rng)

    if args.by_width and "metres" in df.columns:
        band = pd.cut(df["metres"], WIDTH_EDGES, labels=WIDTH_LABELS,
                      right=False)
        for lab in WIDTH_LABELS:
            report(lab, df[band == lab], args.draws, rng)

    print("\n" + RULE)
    print("Report the fourth column. The last one says how much wider it is")
    print("than what this project has been quoting, so anything above about")
    print("1.3 is a figure whose precision was overstated. Rows with fewer")
    print(f"than {BOOTSTRAP_FLOOR} hits fall back to the parcel interval, "
          f"because a")
    print("bootstrap over chips cannot resolve a tail it almost never samples.")
    print("The large differences in COMPARISON.md survive either column.")
    print(RULE)


if __name__ == "__main__":
    main()
