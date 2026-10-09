"""
RS-02 stage 2b. The object budget control, drawn.

The budget column is the contribution of this stage and it is hard to see in a
table, because the reader has to hold two numbers per method and compare them
against a third. As a curve it is one glance: recall against how many objects a
method emitted, with a line marking where FTW sits.

FTW is drawn twice. The hollow dot is the v1 checkpoint most of this project
measured, the filled one FTW's v3 checkpoint with an EfficientNet-B7 encoder,
the best public release (findings 18 and 19, B-24). The dashed line marks the
objects v3 emits and the dotted one v1's. On India v3 sits well above v1 and
still below watershed and SAM at its own line. On Slovenia it sits alone on the
left, above every other method.

Watershed includes h 0.4 from season_test.py, the setting coarse enough to
reach FTW's Slovenian count, so that curve now crosses the line. SAM's
Slovenian curve stops right of it (B-08), so its values there are ceilings,
and the drawing says so by not extending it.

SAM is drawn on colour infrared, the composite the README's headline quotes.
Natural colour, which carries the cross-country table, and the first run's
inputs (B-23) are in the tables and not drawn here.

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
    ("sam_cir", "SAM ViT-H, colour infrared", "SAM ViT-H", "#eda100", "D",
     "left"),
]

# FTW is one dot rather than a curve, so its label has no line to sit beside.
# Which side is clear differs by panel: on India another curve passes just
# above the dot, on Slovenia just below it.
FTW_LABEL = {"india": (13, 0), "slovenia": (10, 13)}
FTW_COLOUR = "#2a78d6"
# v1 and v3 B7 from newer_checkpoints.py, which reproduces v1's published run.
FTW_POINTS = [("v1 full", "FTW v1", "FTW v1", False),
              ("v3 full b7", "FTW v3, EfficientNet-B7", "FTW v3", True)]
FTW_OFFSET = {("india", "v1 full"): (12, 0), ("india", "v3 full b7"): (12, -2),
              ("slovenia", "v1 full"): (12, -1),
              ("slovenia", "v3 full b7"): (12, 0)}
# Coarser watershed settings run by season_test.py, kept above this many
# objects per chip so the x axis does not stretch for points far off the
# panel's subject.
WS_EXTRA_MIN_OBJECTS = 8.0


def load(country: str) -> dict:
    """Objects per chip against recall, per method."""
    rd = F.PROJECT / "results" / country
    out = {}

    seg = pd.read_csv(rd / "segmenter_comparison_min500.csv")
    for method, grp in seg.groupby("method"):
        g = grp.sort_values("objects_per_chip")
        out[str(method)] = (g["objects_per_chip"].to_numpy(),
                            g["recall"].to_numpy())

    extra = rd / "season_watershed.csv"
    if extra.exists() and "watershed" in out:
        e = pd.read_csv(extra)
        e = e[(e["variant"] == "both")
              & (e["objects_per_chip"] >= WS_EXTRA_MIN_OBJECTS)]
        xs, ys = out["watershed"]
        known = set(np.round(xs, 1))
        add = e[~e["objects_per_chip"].round(1).isin(known)]
        xs = np.concatenate([xs, add["objects_per_chip"].to_numpy()])
        ys = np.concatenate([ys, add["recall"].to_numpy()])
        order = np.argsort(xs)
        out["watershed"] = (xs[order], ys[order])

    ck = F.PROJECT / "results" / "newer_checkpoints.csv"
    if ck.exists():
        c = pd.read_csv(ck)
        c = c[c["country"] == country].set_index("checkpoint")
        for key, *_ in FTW_POINTS:
            if key in c.index:
                out[key] = (float(c.loc[key, "objects_per_chip"]),
                            float(c.loc[key, "recall"]))

    sam_path = rd / "sam_comparison_vit_h_min500.csv"
    if sam_path.exists():
        sam = pd.read_csv(sam_path, dtype={"composite": str})
        for comp, grp in sam.groupby("composite"):
            g = grp.sort_values("objects_per_chip")
            out[f"sam_{str(comp).strip().lower()}"] = (
                g["objects_per_chip"].to_numpy(), g["recall"].to_numpy())
    return out


def draw_panel(ax, country: str, data: dict, show_legend: bool) -> None:
    v3 = data.get("v3 full b7")
    budget = v3[0] if v3 else float(data["ftw"][0][0])
    v1_budget = float(data["ftw"][0][0])

    if v3:
        ax.axvline(v1_budget, color=INK_SOFT, lw=1.0, ls=(0, (1, 2.5)),
                   zorder=1)
    ax.axvline(budget, color=INK_SOFT, lw=1.2, ls=(0, (4, 3)), zorder=1)
    # On Slovenia the v3 dot and its label sit just right of the line, so
    # the line's own label goes on its left there.
    left = country == "slovenia"
    ax.annotate(f"FTW v3 emits {budget:.0f}" if v3 else
                f"FTW emits {budget:.0f}", xy=(budget, 0.385),
                xytext=(-4 if left else 4, 0), textcoords="offset points",
                color=INK_SOFT, fontsize=8.5, rotation=90,
                va="top", ha="right" if left else "left")

    if v3:
        x1, y1 = data["v1 full"]
        ax.annotate("", xy=v3, xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=FTW_COLOUR,
                                    lw=1.0, alpha=0.45,
                                    shrinkA=7, shrinkB=8), zorder=3)
        for key, _full, label, filled in FTW_POINTS:
            x, y = data[key]
            ax.plot([x], [y], marker="o", ms=11, ls="none", zorder=5,
                    color=FTW_COLOUR if filled else SURFACE,
                    mec=FTW_COLOUR if not filled else SURFACE,
                    mew=2)
            ax.annotate(label, xy=(x, y), xytext=FTW_OFFSET[(country, key)],
                        textcoords="offset points", color=FTW_COLOUR,
                        fontsize=9, va="center", ha="left", zorder=6)

    for key, _full, label, colour, marker, anchor in SERIES:
        if key not in data or (key == "ftw" and v3):
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
    ax.set_xlim(8, 4000)
    ax.set_ylim(0, 0.40)
    ax.set_xticks([10, 20, 50, 100, 200, 500, 1000, 2000])
    ax.set_xticklabels(["10", "20", "50", "100", "200", "500", "1,000",
                        "2,000"])
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
        if "v3 full b7" in data:
            for _key, full, _short, filled in reversed(FTW_POINTS):
                handles.append(mlines.Line2D(
                    [], [], ls="none", marker="o", ms=8,
                    color=FTW_COLOUR if filled else SURFACE,
                    mec=FTW_COLOUR if not filled else SURFACE, mew=1.6,
                    label=full))
        for key, full, _short, colour, marker, _anchor in SERIES:
            if key in data and not (key == "ftw" and "v3 full b7" in data):
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
             "Read each panel at the dashed line, where FTW v3 sits; the dotted "
             "line is v1. SAM's Slovenian curve stops right of it, so its "
             "values there are ceilings.",
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
        print(f"  {country:>9}  FTW v1 at {budget:>5.0f} objects/chip, "
              f"recall {data[country]['ftw'][1][0]:.3f}")
        if "v3 full b7" in data[country]:
            x, y = data[country]["v3 full b7"]
            print(f"             FTW v3 B7 at {x:>5.0f} objects/chip, "
                  f"recall {y:.3f}")
            budget = x
        for key, label, _s, _c, _m, _a in SERIES[1:]:
            if key not in data[country]:
                continue
            xs, ys = data[country][key]
            if min(xs) > budget:
                edge = f"stops at {min(xs):.0f}"
            elif max(xs) < budget:
                edge = f"stops at {max(xs):.0f}"
            else:
                edge = "reaches it"
            print(f"             {label:<16} sweep {min(xs):.0f} to "
                  f"{max(xs):.0f} objects, {edge}")
    print(f"\n  wrote {dest.relative_to(F.PROJECT)}")
    print("\n" + RULE)
    print("The numbers behind it are in results/comparison_tables.md.")
    print(RULE)


if __name__ == "__main__":
    main()
