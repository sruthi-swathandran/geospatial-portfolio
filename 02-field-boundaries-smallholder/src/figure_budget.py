"""
RS-02 stage 2b. The object budget control, drawn.

The budget column is the contribution of this stage and it is hard to see in a
table, because the reader has to hold two numbers per method and compare them
against a third. As a curve it is one glance: recall against how many objects a
method emitted, with a line marking where FTW sits.

India shows the checkpoint at the bottom of its own budget line. Slovenia shows
it alone on the left, reaching higher recall from a fifth of the objects any
other method needed, which is the shape of a method that is economical rather
than merely accurate.

The Slovenian curves stop well right of the budget line. That gap is B-08: no
competing method was run coarse enough to be read at 18 objects per chip, so
their figures there are ceilings and the drawing says so by not extending them.

SAM is drawn at true colour, matching the cross-country table in COMPARISON.md.
False colour runs within 0.01 of it on India and about 0.03 below on Slovenia.

Numbers come from the same CSVs as every table, so the figure cannot drift from
the text. Colours are the four leading slots of a categorical palette validated
for colour vision deficiency, and every line carries a direct label so identity
never rests on colour alone.

    python src\\figure_budget.py
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
COUNTRIES = ("india", "slovenia")

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"

# Categorical slots one to four, in the order the palette fixes. The order is
# what keeps adjacent pairs separable under colour vision deficiency, so it is
# taken as given rather than rearranged to taste.
# Each row: key, legend name, direct-label name, colour, marker, label side.
# The direct label is shortened where the legend already carries the full
# name, because a long one crowds its neighbours. SAM is
# labelled above the left end of its sweep, since its curve stops in the middle
# of the panel and a label at either end at line height lands on watershed.
SERIES = [
    ("ftw", "FTW 3-class FULL", "FTW", "#2a78d6", "o", "point"),
    ("watershed", "watershed", "watershed", "#eb6834", "s", "right"),
    ("felzenszwalb", "felzenszwalb", "felzenszwalb", "#1baf7a", "^", "right"),
    ("sam_true", "SAM ViT-H", "SAM ViT-H", "#eda100", "D", "left"),
]

# FTW is one dot rather than a curve, so its label has no line to sit beside.
# Which side is clear differs by panel: on India another curve passes just
# above the dot, on Slovenia just below it.
FTW_LABEL = {"india": (13, 0), "slovenia": (10, 13)}


def load(country: str) -> dict:
    """Objects per chip against recall, per method."""
    rd = F.PROJECT / "results" / country
    out = {}

    seg = pd.read_csv(rd / "segmenter_comparison_min500.csv")
    for method, grp in seg.groupby("method"):
        g = grp.sort_values("objects_per_chip")
        out[str(method)] = (g["objects_per_chip"].to_numpy(),
                            g["recall"].to_numpy())

    sam_path = rd / "sam_comparison_vit_h_min500.csv"
    if sam_path.exists():
        sam = pd.read_csv(sam_path, dtype={"composite": str})
        for comp, grp in sam.groupby("composite"):
            g = grp.sort_values("objects_per_chip")
            out[f"sam_{str(comp).strip().lower()}"] = (
                g["objects_per_chip"].to_numpy(), g["recall"].to_numpy())
    return out


def draw_panel(ax, country: str, data: dict, show_legend: bool) -> None:
    budget = float(data["ftw"][0][0])

    ax.axvline(budget, color=INK_SOFT, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.annotate(f"FTW emits {budget:.0f}", xy=(budget, 0.385),
                xytext=(4, 0), textcoords="offset points",
                color=INK_SOFT, fontsize=8.5, rotation=90,
                va="top", ha="left")

    for key, _full, label, colour, marker, anchor in SERIES:
        if key not in data:
            continue
        xs, ys = data[key]
        if len(xs) == 1:
            ax.plot(xs, ys, marker=marker, ms=11, color=colour,
                    mec=SURFACE, mew=2, ls="none", zorder=5)
        else:
            ax.plot(xs, ys, color=colour, lw=2, marker=marker, ms=6,
                    mec=SURFACE, mew=1.2, zorder=4)

        # A direct label on every series, so colour is never the only thing
        # carrying identity.
        if anchor == "left":
            at, off, ha = (xs[0], ys[0]), (-9, 14), "right"
        elif anchor == "point":
            at, off, ha = (xs[0], ys[0]), FTW_LABEL[country], "left"
        else:
            at, off, ha = (xs[-1], ys[-1]), (10, 0), "left"
        ax.annotate(label, xy=at, xytext=off, textcoords="offset points",
                    color=colour, fontsize=9, va="center", ha=ha, zorder=6)

    ax.set_xscale("log")
    ax.set_xlim(15, 4000)
    ax.set_ylim(0, 0.40)
    ax.set_xticks([20, 50, 100, 200, 500, 1000, 2000])
    ax.set_xticklabels(["20", "50", "100", "200", "500", "1,000", "2,000"])
    ax.set_xlabel("objects emitted per chip", color=INK_SOFT, fontsize=9.5)
    if show_legend:
        ax.set_ylabel("share of parcels found at IoU 0.5",
                      color=INK_SOFT, fontsize=9.5)
    ax.set_title(country.capitalize(), color=INK, fontsize=12,
                 loc="left", pad=10)

    ax.set_facecolor(SURFACE)
    ax.grid(True, which="major", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SOFT, labelsize=9, length=0)

    if show_legend:
        handles = []
        import matplotlib.lines as mlines
        for key, full, _short, colour, marker, _anchor in SERIES:
            if key in data:
                handles.append(mlines.Line2D(
                    [], [], color=colour, lw=2, marker=marker, ms=6,
                    mec=SURFACE, mew=1.2, label=full))
        leg = ax.legend(handles=handles, loc="upper left", frameon=False,
                        fontsize=9, labelcolor=INK_SOFT,
                        handlelength=1.8, borderpad=0.2)
        leg.set_zorder(7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = {}
    for country in COUNTRIES:
        rd = F.PROJECT / "results" / country
        if not (rd / "segmenter_comparison_min500.csv").exists():
            sys.exit(f"{rd} has no comparison table, run compare_segmenters "
                     f"for {country} first")
        data[country] = load(country)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.1), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, country in zip(axes, COUNTRIES):
        draw_panel(ax, country, data[country], show_legend=(country == "india"))

    fig.suptitle("What each method recovers, against how many objects it emits",
                 color=INK, fontsize=13.5, x=0.045, ha="left", y=0.985)
    fig.text(0.045, 0.925,
             "Read each panel at the dashed line. Slovenian curves stop right "
             "of it because no method was run that coarse, so their values "
             "there are ceilings.",
             color=INK_SOFT, fontsize=9.5, ha="left")
    fig.subplots_adjust(left=0.062, right=0.985, top=0.80, bottom=0.11,
                        wspace=0.09)

    dest = F.PROJECT / "figures" / "recall_by_object_budget.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=args.dpi, facecolor=SURFACE)
    plt.close(fig)

    print(RULE)
    print("OBJECT BUDGET FIGURE")
    print(RULE)
    for country in COUNTRIES:
        budget = float(data[country]["ftw"][0][0])
        print(f"  {country:>9}  FTW at {budget:>5.0f} objects/chip, "
              f"recall {data[country]['ftw'][1][0]:.3f}")
        for key, label, _s, _c, _m, _a in SERIES[1:]:
            if key not in data[country]:
                continue
            xs, ys = data[country][key]
            edge = "reaches it" if min(xs) <= budget else \
                   f"stops at {min(xs):.0f}"
            print(f"             {label:<16} sweep {min(xs):.0f} to "
                  f"{max(xs):.0f} objects, {edge}")
    print(f"\n  wrote {dest.relative_to(F.PROJECT)}")
    print("\n" + RULE)
    print("The numbers behind it are in results/comparison_tables.md.")
    print(RULE)


if __name__ == "__main__":
    main()
