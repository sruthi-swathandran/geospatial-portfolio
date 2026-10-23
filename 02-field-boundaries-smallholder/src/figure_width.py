"""
RS-02 stage 2b. Recall by ground width in both countries, the argument of
finding 3 in one figure, and the reach figures finding 5 quotes.

Finding 3 says resolution does not explain the Indian failure: on the same
10 m Sentinel-2, a parcel of a given ground width is found far less often in
India than in Slovenia, by every method. This draws that for FTW's v3 checkpoint
with an EfficientNet-B7 encoder, the best public release (B-24), and for
watershed, which is never trained, each in both countries and by width band.
Each point carries a 95% interval over whole chips, or the parcel-level
interval where a band holds fewer than ten found parcels, as
`bootstrap_ci.py` does (B-27).

It also writes the per-parcel reach figures finding 5 quotes: how many
labelled parcels a method puts no object on at all, and how many of the
largest fields, about 100 m across and wider, it finds. A parcel with a best
IoU of zero has no object over it.

Every number comes from per-parcel files already in results/, so nothing is
rerun:

  FTW v1 and v3 B7     results/<country>/newer_ckpt/<checkpoint>_parcels.csv
  watershed            results/<country>/parcel_width_seg_watershed_min500.csv
  SAM ViT-H            results/<country>/parcel_width_seg_sam_vit_h_<composite>_0p50_min500.csv,
                       natural colour and colour infrared, at the 0.50
                       threshold the width tables use

Outputs
-------
  results/recall_by_width.csv      method, country, band, found, parcels,
                                   recall and its interval
  results/reach_by_method.csv      method, country, recall, share of parcels
                                   with no object, recall on fields 100 m up
  figures/recall_by_width.png

Usage
-----
    python src\\figure_width.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                         # noqa: E402
from bootstrap_ci import (BOOTSTRAP_FLOOR, WIDTH_EDGES,        # noqa: E402
                          WIDTH_LABELS, chip_bootstrap, clopper_pearson)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

RULE = "=" * 78
COUNTRIES = ("india", "slovenia")
SEED = 20261023
DRAWS = 10000
LARGE_M = 100.0

# key, name, file under results/<country>/, width column, whether it is drawn
METHODS = [
    ("v3_b7", "FTW v3, EfficientNet-B7", "newer_ckpt/v3_full_b7_parcels.csv",
     "width_m", True),
    ("watershed", "watershed", "parcel_width_seg_watershed_min500.csv",
     "width_native_px", True),
    ("v1", "FTW v1", "newer_ckpt/v1_full_parcels.csv", "width_m", False),
    ("sam_rgb", "SAM ViT-H natural colour",
     "parcel_width_seg_sam_vit_h_rgb_0p50_min500.csv", "width_native_px", False),
    ("sam_cir", "SAM ViT-H colour infrared",
     "parcel_width_seg_sam_vit_h_cir_0p50_min500.csv", "width_native_px", False),
]

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"
# slots one and two of the categorical palette figure_budget.py uses
COUNTRY_STYLE = {"india": ("India", "#2a78d6", "o"),
                 "slovenia": ("Slovenia", "#eb6834", "s")}


def load(country: str, rel: str, width_col: str) -> pd.DataFrame:
    path = F.PROJECT / "results" / country / rel
    if not path.exists():
        sys.exit(f"{path} not found")
    df = pd.read_csv(path)
    for need in ("chip", "best_iou", "found", width_col):
        if need not in df.columns:
            sys.exit(f"{path.name} has no {need} column")
    metres = df[width_col] * (10.0 if width_col == "width_native_px" else 1.0)
    return pd.DataFrame({"chip": df["chip"], "best_iou": df["best_iou"],
                         "hit": df["found"].astype(bool), "metres": metres})


def interval(df: pd.DataFrame, rng) -> tuple:
    found, total = int(df["hit"].sum()), len(df)
    cl, ch = clopper_pearson(found, total)
    if found < BOOTSTRAP_FLOOR:
        return cl, ch, "parcel"
    bl, bh, _ = chip_bootstrap(df, DRAWS, rng)
    return min(cl, bl), max(ch, bh), "union"


def draw(rows: pd.DataFrame, dest: Path, dpi: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    drawn = [m for m in METHODS if m[4]]
    fig, axes = plt.subplots(1, len(drawn), figsize=(10.5, 4.6), sharey=True,
                             facecolor=SURFACE)
    x = np.arange(len(WIDTH_LABELS))
    for ax, (key, name, *_rest) in zip(axes, drawn):
        ax.set_facecolor(SURFACE)
        for country, (label, colour, marker) in COUNTRY_STYLE.items():
            sub = rows[(rows["method"] == name) & (rows["country"] == country)]
            sub = sub.set_index("band").loc[WIDTH_LABELS]
            y = sub["recall"].to_numpy() * 100
            lo = y - sub["lo"].to_numpy() * 100
            hi = sub["hi"].to_numpy() * 100 - y
            off = -0.07 if country == "india" else 0.07
            ax.errorbar(x + off, y, yerr=[lo, hi], color=colour, marker=marker,
                        markersize=6, linewidth=1.6, capsize=3, elinewidth=1,
                        zorder=3)
            ax.text(x[-1] + off + 0.12, y[-1], label, color=colour, fontsize=9,
                    va="center", ha="left")
        ax.set_xticks(x, WIDTH_LABELS, fontsize=9, color=INK_SOFT)
        ax.set_xlim(-0.4, len(WIDTH_LABELS) - 0.15)
        ax.set_title(name, color=INK, fontsize=11.5, loc="left")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=INK_SOFT, labelsize=9)
        ax.set_xlabel("ground width of the labelled parcel", color=INK_SOFT,
                      fontsize=9.5)
    axes[0].set_ylabel("parcels found, % (IoU 0.5)", color=INK_SOFT,
                       fontsize=9.5)
    axes[0].set_ylim(0, 85)
    fig.suptitle("Same sensor, same parcel width: Slovenian parcels are found "
                 "far more often", color=INK, fontsize=12.5, x=0.06, ha="left")
    fig.text(0.06, 0.01, "Bars: 95% interval over whole chips, or the "
             "parcel-level interval below ten found parcels. Watershed at its "
             "best setting, as in the width tables.\nSource: "
             "results/recall_by_width.csv, from the per-parcel files in "
             "results/ (src/figure_width.py)", color=INK_SOFT,
             fontsize=8.5, ha="left", va="bottom", linespacing=1.4)
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=dpi, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)

    width_rows, reach_rows = [], []
    for key, name, rel, col, _ in METHODS:
        for country in COUNTRIES:
            df = load(country, rel, col)
            band = pd.cut(df["metres"], WIDTH_EDGES, labels=WIDTH_LABELS,
                          right=False)
            for lab in WIDTH_LABELS:
                sub = df[band == lab]
                lo, hi, governs = interval(sub, rng)
                width_rows.append(dict(
                    method=name, country=country, band=lab,
                    found=int(sub["hit"].sum()), parcels=len(sub),
                    recall=round(sub["hit"].mean(), 4),
                    lo=round(lo, 4), hi=round(hi, 4), governs=governs,
                    exact=sub["hit"].mean()))
            large = df[df["metres"] >= LARGE_M]
            reach_rows.append(dict(
                method=name, country=country, parcels=len(df),
                recall=round(df["hit"].mean(), 4),
                no_object_pct=round((df["best_iou"] == 0).mean() * 100, 1),
                parcels_100m_up=len(large),
                recall_100m_up_pct=round(large["hit"].mean() * 100, 1)))

    widths = pd.DataFrame(width_rows)
    # Slovenia over India in each band, from the unrounded shares
    ind = widths[widths["country"] == "india"].set_index(["method", "band"])["exact"]
    widths["slovenia_over_india"] = [
        (round(r["exact"] / ind[(r["method"], r["band"])], 1)
         if r["country"] == "slovenia" and ind[(r["method"], r["band"])] > 0
         else "") for _, r in widths.iterrows()]
    widths = widths.drop(columns="exact")
    reach = pd.DataFrame(reach_rows)
    out = F.PROJECT / "results"
    widths.to_csv(out / "recall_by_width.csv", index=False, lineterminator="\n")
    reach.to_csv(out / "reach_by_method.csv", index=False, lineterminator="\n")

    print(RULE)
    print("RECALL BY GROUND WIDTH, BOTH COUNTRIES")
    print(RULE)
    for name in widths["method"].unique():
        print(f"\n  {name}")
        print(f"  {'band':<12} {'India':>22} {'Slovenia':>22} {'ratio':>7}")
        for lab in WIDTH_LABELS:
            i = widths[(widths["method"] == name) & (widths["country"] == "india")
                       & (widths["band"] == lab)].iloc[0]
            s = widths[(widths["method"] == name)
                       & (widths["country"] == "slovenia")
                       & (widths["band"] == lab)].iloc[0]
            ratio = (f"{s['slovenia_over_india']}x" if s["slovenia_over_india"] != ""
                     else "n/a")
            print(f"  {lab:<12} {i['found']:>5}/{i['parcels']:<5} "
                  f"{i['recall'] * 100:6.2f}%   {s['found']:>5}/{s['parcels']:<5} "
                  f"{s['recall'] * 100:6.2f}%   {ratio:>7}")
    print(f"\n  {'method':<28} {'country':<9} {'recall':>7} {'no object':>10} "
          f"{'100 m up':>14}")
    for r in reach_rows:
        print(f"  {r['method']:<28} {r['country']:<9} {r['recall'] * 100:6.2f}% "
              f"{r['no_object_pct']:>9}% {r['recall_100m_up_pct']:>6}% of "
              f"{r['parcels_100m_up']}")
    dest = F.PROJECT / "figures" / "recall_by_width.png"
    draw(widths, dest, args.dpi)
    print(f"\n  wrote results/recall_by_width.csv, results/reach_by_method.csv "
          f"and figures/recall_by_width.png")


if __name__ == "__main__":
    main()
