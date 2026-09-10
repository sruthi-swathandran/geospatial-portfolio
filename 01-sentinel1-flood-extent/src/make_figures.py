"""
Regenerate the figures the README shows, from the CSVs already in results/.

Seven figures, one design. Each is written back over the file it replaces, so
nothing else in the project needs to change:

  operating_point.png    two operating points, and why the headline is a range
  accuracy_ci.png        per-split accuracy with bootstrap intervals
  change_sweep.png       change detection swept across every setting it has
  product_vs_window.png  what leaving Earth Engine costs
  orbit_offset.png       radiometric agreement between relative orbits 4 and 77
  sensitivity_grid.png   mapped area across 216 parameter combinations
  flooded_cropland.png   flooded cropland by district

Run from anywhere:

    python 01-sentinel1-flood-extent\\src\\make_figures.py

Options:
    --only NAME[,NAME]   regenerate a subset, by figure name without .png
    --dpi N              default 200

Nothing is computed here. Every number is read from a CSV the pipeline wrote,
and each figure prints the file it came from in its own footer, so a reader can
check any value without running anything. If a CSV is missing or has a column
this script does not expect, that figure is skipped with a message and the rest
still write.

Layout note. Title and caption live in their own blank axes inside the grid
rather than in figure coordinates. matplotlib's constrained layout only knows
about axes, so text placed with fig.text gets drawn over. Giving the header and
footer real axes is what stops that happening.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

FIGS = cfg.RESULTS / "figures"

# --------------------------------------------------------------------------
# One design, shared by every figure and matched to the maps
# --------------------------------------------------------------------------
INK = "#16222B"
MUTED = "#5C6B76"
RULE = "#C9D2D8"
FAINT = "#E8EDF0"

BLUE = "#1B5E8C"
SAND = "#E0A458"
PLUM = "#8E4585"
TEAL = "#3F7D6B"
BRICK = "#B3452F"
SLATE = "#7B94A6"
SERIES = [BLUE, SAND, PLUM, TEAL, BRICK, SLATE]

SPLIT_COLOUR = {"all": INK, "train": SAND, "valid": BLUE, "test": TEAL}

TITLE_SZ, SUB_SZ, LAB_SZ, TICK_SZ, CAP_SZ = 13.5, 9.8, 9.5, 8.5, 8.2

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#2A3439",
    "axes.linewidth": 0.7,
    "axes.labelcolor": INK,
    "axes.labelsize": LAB_SZ,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": TICK_SZ,
    "ytick.labelsize": TICK_SZ,
    "grid.color": FAINT,
    "grid.linewidth": 0.7,
    "legend.frameon": False,
    "legend.fontsize": 8.6,
    "font.size": 9,
})


# --------------------------------------------------------------------------
# Layout scaffold
# --------------------------------------------------------------------------
def canvas(width, content_h, title, subtitle, caption, source,
           legend_row=False):
    """A figure with the header and footer as real axes, so constrained layout
    reserves room for them instead of drawing the plot on top."""
    cap_lines = caption.count("\n") + 1
    head_in = 0.78
    legend_in = 0.34 if legend_row else 0.0
    foot_in = 0.34 + 0.163 * cap_lines
    fig_h = head_in + legend_in + content_h + foot_in

    fig = plt.figure(figsize=(width, fig_h), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, hspace=0.0,
                                wspace=0.0)

    heights = [head_in] + ([legend_in] if legend_row else []) \
        + [content_h, foot_in]
    outer = fig.add_gridspec(len(heights), 1, height_ratios=heights)

    hax = fig.add_subplot(outer[0])
    hax.set_axis_off()
    hax.text(0, 1.0, title, fontsize=TITLE_SZ, fontweight="bold", color=INK,
             va="top", ha="left", transform=hax.transAxes)
    hax.text(0, 0.0, subtitle, fontsize=SUB_SZ, color=MUTED, va="bottom",
             ha="left", transform=hax.transAxes)

    lax = None
    if legend_row:
        lax = fig.add_subplot(outer[1])
        lax.set_axis_off()

    slot = outer[len(heights) - 2]

    fax = fig.add_subplot(outer[-1])
    fax.set_axis_off()
    fax.text(0, 1.0, caption, fontsize=CAP_SZ, color=MUTED, va="top",
             ha="left", transform=fax.transAxes, linespacing=1.62)
    fax.text(0, 0.0, f"source: results/{source}", fontsize=7,
             color="#8A97A0", va="bottom", ha="left", transform=fax.transAxes)

    return fig, slot, lax


def frame(ax, grid="y"):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid:
        ax.set_axisbelow(True)
        ax.grid(axis=grid, which="major")


def legend_into(lax, handles, labels, ncol=4):
    lax.legend(handles, labels, loc="center left", ncol=ncol,
               bbox_to_anchor=(0, 0.5), handlelength=1.8,
               columnspacing=1.8, borderpad=0)


def save(fig, name, dpi):
    out = FIGS / f"{name}.png"
    fig.savefig(out, dpi=dpi, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.relative_to(cfg.PROJECT)}")


def pct(x, _pos=None):
    return f"{x * 100:.0f}%"


def db(v, nd=2):
    """Unicode minus, so annotations match matplotlib's own tick labels."""
    return f"{v:.{nd}f}".replace("-", "\u2212")


HALO = dict(boxstyle="round,pad=0.3", fc="white", ec="none", alpha=0.86)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def _num(v):
    """float() accepts digit separators, so float('1_3') is 13.0. Tile ids
    like '1_3' would silently become numbers. Reject anything with one."""
    if v is None or v == "":
        return np.nan
    if "_" in str(v):
        raise ValueError("underscore")
    return float(v)


def load(name: str):
    p = cfg.RESULTS / name
    if not p.exists():
        return None
    with open(p, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return None
    out = {}
    for k in rows[0]:
        vals = [r.get(k, "") for r in rows]
        try:
            out[k] = np.array([_num(v) for v in vals])
        except ValueError:
            out[k] = np.array([str(v) for v in vals], dtype=object)
    out["_n"] = len(rows)
    return out


def need(name: str):
    d = load(name)
    if d is None:
        print(f"  skipped, results/{name} not found")
    return d


# --------------------------------------------------------------------------
# 1. Operating point
# --------------------------------------------------------------------------
def fig_operating_point(dpi):
    d = need("operating_point.csv")
    if d is None:
        return
    o = np.argsort(d["threshold"])
    t = d["threshold"][o]

    fig, slot, lax = canvas(
        9.4, 6.8,
        "Two operating points, and why the headline is a range",
        "Threshold sweep against the Sen1Floods11 hand labels, 65 chips, "
        "India event",
        "The upper panel is agreement with the labels. The lower is how much "
        "water the map draws against how much the labels contain.\n"
        "They do not peak in the same place. One threshold matches the shape "
        "of the flood best, the other matches its size. On these\nchips the "
        "two are not separable, so the README reports both rather than "
        "picking one and hoping.",
        "operating_point.csv", legend_row=True)

    inner = slot.subgridspec(2, 1, height_ratios=[1.45, 1], hspace=0.06)
    ax1 = fig.add_subplot(inner[0])
    ax2 = fig.add_subplot(inner[1], sharex=ax1)

    for key, lab in (("iou_train", "train, 37 chips"),
                     ("iou_valid", "valid, 14 chips"),
                     ("iou_test", "test, 14 chips")):
        if key in d:
            ax1.plot(t, d[key][o], lw=1.5,
                     color=SPLIT_COLOUR[key.split("_")[1]], label=lab)
    if "iou_all" in d:
        ax1.plot(t, d["iou_all"][o], lw=2.6, color=INK, label="all 65 chips")

    ax1.set_ylabel("IoU against hand labels")
    ax1.set_ylim(0, float(np.nanmax(d["iou_test"][o])) * 1.14)
    ax1.tick_params(labelbottom=False)
    frame(ax1)
    legend_into(lax, *ax1.get_legend_handles_labels(), ncol=4)

    i_map = int(np.nanargmax(d["iou_valid"][o])) if "iou_valid" in d else None
    i_area = None
    if "area_err" in d:
        i_area = int(np.nanargmin(np.abs(d["area_err"][o])))

    top = ax1.get_ylim()[1]
    for idx, col, lab, side, yf in (
            (i_map, BLUE, "map-optimal\nhighest IoU on valid", "right", 0.60),
            (i_area, SAND, "area-matched\nmapped area unbiased", "left", 0.30)):
        if idx is None:
            continue
        for ax in (ax1, ax2):
            ax.axvline(t[idx], color=col, lw=1.1, ls=(0, (4, 3)), zorder=1)
        ax1.annotate(f"{lab}\n{db(t[idx])} dB", xy=(t[idx], top * yf),
                     xytext=(-8 if side == "right" else 8, 0),
                     textcoords="offset points", fontsize=8.2, color=col,
                     va="center", ha=side, linespacing=1.45, bbox=HALO,
                     zorder=6)

    if "area_err" in d:
        e = d["area_err"][o] * 100
        ax2.plot(t, e, lw=2.2, color=BRICK, zorder=3)
        ax2.axhline(0, color=MUTED, lw=0.9)
        ax2.fill_between(t, 0, e, color=BRICK, alpha=0.10)
        ax2.set_ylabel("mapped area error\nagainst labelled area")
        ax2.set_ylim(-108, 165)
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:+.0f}%"))
        hi = float(np.nanmax(e))
        if hi > 165:
            ax2.annotate(f"rises to {hi:+,.0f}% at "
                         f"{db(t[int(np.nanargmax(e))])} dB,\n"
                         f"off the top of this panel",
                         xy=(t[-1], 150), xytext=(-6, 0),
                         textcoords="offset points", ha="right", va="top",
                         fontsize=7.8, color=BRICK, linespacing=1.45)
    ax2.set_xlabel("VH threshold (dB), gamma0")
    frame(ax2)

    save(fig, "operating_point", dpi)


# --------------------------------------------------------------------------
# 2. Accuracy with intervals
# --------------------------------------------------------------------------
def fig_accuracy_ci(dpi):
    d = need("accuracy_ci.csv")
    if d is None:
        return
    splits = [str(s) for s in d["split"]]
    order = [s for s in ("all", "train", "valid", "test") if s in splits]
    idx = [splits.index(s) for s in order]

    metrics = [(k, lab) for k, lab in
               (("iou", "IoU"), ("precision", "Precision"),
                ("recall", "Recall")) if k in d]

    fig, slot, lax = canvas(
        11.6, 4.0,
        "Accuracy on the validation chips, with intervals",
        "Percentile bootstrap resampled over chips rather than pixels, so the "
        "interval reflects how few chips there are",
        "Quantity disagreement is mapping the wrong amount of water. "
        "Allocation disagreement is mapping the right amount in the wrong "
        "place. They are\nreported instead of kappa, following Pontius and "
        "Millones (2011). Note the spread across splits: quoting the "
        "friendliest of them would have read 0.680.\n"
        "These figures describe the chip-scale product. They do not describe "
        "the full-scene map the README reports, which has never been "
        "validated against\nindependent labels.",
        "accuracy_ci.csv", legend_row=True)

    inner = slot.subgridspec(1, len(metrics) + 1,
                             width_ratios=[1] * len(metrics) + [0.95],
                             wspace=0.26)
    axes = [fig.add_subplot(inner[0, i]) for i in range(len(metrics) + 1)]

    ypos = np.arange(len(order))[::-1]
    for ax, (k, lab) in zip(axes, metrics):
        v, lo, hi = d[k][idx], d[f"{k}_ci_lo"][idx], d[f"{k}_ci_hi"][idx]
        for y, s, m, a, b in zip(ypos, order, v, lo, hi):
            c = SPLIT_COLOUR.get(s, INK)
            ax.plot([a, b], [y, y], lw=2.8, color=c, alpha=0.32,
                    solid_capstyle="round")
            ax.plot(m, y, "o", ms=7, color=c, zorder=3)
            ax.annotate(f"{m:.3f}", (m, y), xytext=(0, 9),
                        textcoords="offset points", ha="center",
                        fontsize=7.8, color=c)
        ax.set_yticks(ypos)
        if ax is axes[0]:
            ax.set_yticklabels(
                [f"{s}  n={int(d['chips'][splits.index(s)])}"
                 for s in order], fontsize=8.6)
        else:
            ax.set_yticklabels([])
        ax.set_xlim(0, 1)
        ax.set_xlabel(lab)
        ax.set_ylim(-0.62, len(order) - 0.38)
        frame(ax, grid="x")

    ax = axes[-1]
    q, a = d.get("quantity_disagreement"), d.get("allocation_disagreement")
    if q is not None and a is not None:
        h1 = ax.barh(ypos, q[idx], height=0.44, color=SAND)
        h2 = ax.barh(ypos, a[idx], height=0.44, left=q[idx], color=PLUM)
        tot = q[idx] + a[idx]
        for y, v in zip(ypos, tot):
            ax.annotate(f"{v * 100:.1f}%", (v, y), xytext=(5, 0),
                        textcoords="offset points", va="center",
                        fontsize=7.8, color=MUTED)
        ax.set_yticks(ypos)
        ax.set_yticklabels([])
        ax.set_xlabel("Disagreement")
        ax.set_xlim(0, float(np.nanmax(tot)) * 1.35)
        ax.xaxis.set_major_formatter(FuncFormatter(pct))
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.set_ylim(-0.62, len(order) - 0.38)
        frame(ax, grid="x")
        legend_into(lax, [h1, h2], ["quantity disagreement",
                                    "allocation disagreement"], ncol=2)
    else:
        ax.set_axis_off()

    save(fig, "accuracy_ci", dpi)


# --------------------------------------------------------------------------
# 3. Change detection sweep
# --------------------------------------------------------------------------
def fig_change_sweep(dpi):
    d = need("change_sweep.csv")
    if d is None:
        return
    t, y = d["threshold"], d["iou_all"]
    smooth = d.get("smooth", np.zeros_like(t))
    gate = d.get("gate", np.zeros_like(t))
    gates = sorted(set(gate.tolist()))

    ref = load("accuracy_ci.csv")
    ref_iou = None
    if ref is not None:
        s = [str(x) for x in ref["split"]]
        if "all" in s:
            ref_iou = float(ref["iou"][s.index("all")])

    fig, slot, lax = canvas(
        10.0, 5.4,
        "Change detection swept across every setting it has",
        f"{len(set(zip(smooth.tolist(), gate.tolist())))} combinations, "
        f"{int(d['_n'])} evaluations, IoU against the hand labels on all chips",
        "A negative value on this axis is a real requirement: the pixel must "
        "be that much darker than it was on the reference date. A positive "
        "value lets\nthrough pixels that got brighter, so the change test "
        "stops constraining anything and what remains is the single-date "
        "threshold. That is where\nthe sweep peaks. The best this method can "
        "do is to switch itself off, which is why it is not in the final "
        "pipeline.\n"
        "The sweep exists because the first run reported −3.00 dB for all "
        "four variants, and that turned out to be a cap in the code rather "
        "than a result.",
        "change_sweep.csv", legend_row=True)

    ax = fig.add_subplot(slot)

    gate_colour = {g: SERIES[i % len(SERIES)] for i, g in enumerate(gates)}
    handles, labels = [], []
    for g in gates:
        c = gate_colour[g]
        first = True
        for s in sorted(set(smooth[gate == g].tolist())):
            m = (gate == g) & (smooth == s)
            o = np.argsort(t[m])
            ln, = ax.plot(t[m][o], y[m][o], lw=1.7, color=c, alpha=0.85)
            if first:
                handles.append(ln)
                labels.append(f"gate {g:g}")
                first = False

    if ref_iou is not None:
        ln = ax.axhline(ref_iou, color=INK, lw=1.3, ls=(0, (5, 3)), zorder=1)
        handles.append(ln)
        labels.append(f"single-date threshold, all 65 chips ({ref_iou:.3f})")

    lo, hi = float(np.nanmin(t)), float(np.nanmax(t))
    ax.axvspan(0, hi, color=SAND, alpha=0.10, zorder=0)
    ax.axvline(0, color=MUTED, lw=0.9)

    # Two points, and they answer different questions. The first is what the
    # change signal manages on its own, which is the figure the README quotes.
    # The second is the best available once the absolute-threshold gate is
    # allowed to help while the drop requirement still bites.
    marks = []
    if 0.0 in set(gate.tolist()):
        m0 = gate == 0.0
        marks.append((int(np.nanargmax(np.where(m0, y, -np.inf))),
                      "change signal alone,\nbest {v:.3f} at {t} dB",
                      BRICK, (-10, 18), "right"))
    restrictive = t <= -0.5
    if restrictive.any():
        j1 = int(np.nanargmax(np.where(restrictive, y, -np.inf)))
        if not marks or j1 != marks[0][0]:
            marks.append((j1, "with the gate still on and a drop\nstill "
                              "required, best {v:.3f} at {t} dB",
                          PLUM, (-12, 14), "right"))
    for j, fmt, col, off, ha in marks:
        ax.plot(t[j], y[j], "o", ms=8, color=col, zorder=5)
        ax.annotate(fmt.format(v=y[j], t=db(t[j])), (t[j], y[j]),
                    xytext=off, textcoords="offset points", ha=ha,
                    fontsize=8.2, color=col, linespacing=1.45, bbox=HALO,
                    zorder=6)

    ax.annotate("change test admits pixels\nthat got brighter",
                xy=(hi, ax.get_ylim()[1] * 0.62), xytext=(-8, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8, color="#9A7B3F", linespacing=1.45, bbox=HALO)

    ax.set_xlabel("required drop from the reference date (dB)")
    ax.set_ylabel("IoU against hand labels, all chips")
    ax.set_xlim(lo, hi)
    ax.set_ylim(bottom=0)
    frame(ax)
    legend_into(lax, handles, labels, ncol=max(2, len(handles)))

    save(fig, "change_sweep", dpi)


# --------------------------------------------------------------------------
# 4. Product comparison
# --------------------------------------------------------------------------
def fig_product_vs_window(dpi):
    d = need("product_vs_window.csv")
    if d is None:
        return
    prod = [str(p) for p in d["product"]]
    uniq = sorted(set(prod))
    t, y = d["threshold"], d["iou_all"]

    fig, slot, lax = canvas(
        11.4, 4.3,
        "What leaving Google Earth Engine costs",
        "The same chips and the same threshold search, run against each "
        "product in turn",
        "Earth Engine serves sigma0 from GRD. Planetary Computer serves "
        "gamma0 from the RTC collection, which is terrain corrected and not "
        "the same\nquantity. Moving between them is not free, and the table "
        "is the size of the bill. Each product is scored at its own best "
        "threshold, so the comparison\nis between two methods each given "
        "their best shot rather than one threshold imposed on both.",
        "product_vs_window.csv", legend_row=True)

    inner = slot.subgridspec(1, 2, width_ratios=[1.5, 1], wspace=0.10)
    ax = fig.add_subplot(inner[0, 0])
    tax = fig.add_subplot(inner[0, 1])
    tax.set_axis_off()
    tax.set_xlim(0, 1)
    tax.set_ylim(0, 1)

    peak = {}
    handles, labels = [], []
    for k, p in enumerate(uniq):
        m = np.array([x == p for x in prod])
        o = np.argsort(t[m])
        c = SERIES[k % len(SERIES)]
        ln, = ax.plot(t[m][o], y[m][o], lw=2.2, color=c)
        handles.append(ln)
        labels.append(p)
        j = int(np.nanargmax(y[m]))
        ax.plot(t[m][j], y[m][j], "o", ms=7, color=c, zorder=3)
        peak[p] = dict(c=c, t=t[m][j], iou=y[m][j],
                       p=d["p_all"][m][j] if "p_all" in d else np.nan,
                       r=d["r_all"][m][j] if "r_all" in d else np.nan)

    ax.set_xlabel("VH threshold (dB)")
    ax.set_ylabel("IoU against hand labels, all chips")
    ax.set_ylim(bottom=0)
    frame(ax)
    legend_into(lax, handles, labels, ncol=len(uniq))

    yy = 0.97
    tax.text(0.0, yy, "AT EACH PRODUCT'S BEST THRESHOLD", fontsize=8.6,
             fontweight="bold", color=MUTED, va="top")
    yy -= 0.085
    for lab, x, ha in (("product", 0.0, "left"), ("dB", 0.50, "right"),
                       ("IoU", 0.68, "right"), ("prec.", 0.85, "right"),
                       ("rec.", 1.0, "right")):
        tax.text(x, yy, lab, fontsize=8, color=MUTED, va="top", ha=ha)
    yy -= 0.042
    tax.plot([0, 1], [yy + 0.012, yy + 0.012], color=RULE, lw=0.7,
             clip_on=False)
    yy -= 0.028
    for p in uniq:
        v = peak[p]
        tax.text(0.0, yy, p, fontsize=9.2, color=INK, va="top")
        tax.text(0.50, yy, f"{v['t']:.2f}", fontsize=9.2, color=MUTED,
                 va="top", ha="right")
        tax.text(0.68, yy, f"{v['iou']:.3f}", fontsize=9.2, color=v["c"],
                 va="top", ha="right", fontweight="bold")
        for x, key in ((0.85, "p"), (1.0, "r")):
            tax.text(x, yy, f"{v[key]:.3f}" if np.isfinite(v[key]) else "—",
                     fontsize=9.2, color=MUTED, va="top", ha="right")
        yy -= 0.060

    # the migration specifically, rather than best minus worst
    pairs = [("gee_lee", "rtc_lee", "the migration, like for like"),
             ("gee_raw", "gee_lee", "what the Lee filter buys, within GEE")]
    yy -= 0.035
    for a, b, note in pairs:
        if a in peak and b in peak:
            di = peak[b]["iou"] - peak[a]["iou"]
            dp = peak[b]["p"] - peak[a]["p"]
            tax.text(0.0, yy, f"{a} to {b}", fontsize=9, fontweight="bold",
                     color=INK, va="top")
            yy -= 0.048
            tax.text(0.0, yy,
                     f"{di:+.3f} IoU, {dp:+.3f} precision\n{note}",
                     fontsize=8.6, color=MUTED, va="top", linespacing=1.5)
            yy -= 0.095

    save(fig, "product_vs_window", dpi)


# --------------------------------------------------------------------------
# 5. Cross-orbit agreement
# --------------------------------------------------------------------------
def fig_orbit_offset(dpi):
    d = need("orbit_offset.csv")
    if d is None:
        return
    tiles = [str(x) for x in d["tile"]]
    diff = d["median_diff_db"]
    land = d.get("median_diff_land_db")
    p25, p75 = d.get("p25_diff"), d.get("p75_diff")
    px = d.get("pixels", np.ones_like(diff))

    o = np.argsort(diff)
    ypos = np.arange(len(o))
    w = float(np.nansum(diff * px) / np.nansum(px))

    fig, slot, lax = canvas(
        9.8, 4.9,
        "Two orbits looking at the same ground, five days apart",
        f"{len(o)} overlap tiles, {np.nansum(px) / 1e6:.1f} M pixels, "
        f"pixel-weighted median offset {w:+.3f} dB",
        "The 12 August map is relative orbit 77. The 7 and 31 August maps are "
        "orbit 4. Different orbits see the same surface at different "
        "incidence angles,\nso before comparing anything across them it is "
        "worth knowing whether they agree radiometrically at all. At the "
        "median they do. The spread within\neach tile is far wider than the "
        "offset between them, which is why the three dates are still never "
        "mosaicked into one product.",
        "orbit_offset.csv", legend_row=True)

    ax = fig.add_subplot(slot)
    ax.axvline(0, color=MUTED, lw=0.9, zorder=1)

    for y, i in zip(ypos, o):
        if p25 is not None and p75 is not None:
            ax.plot([p25[i], p75[i]], [y, y], lw=2.8, color=SLATE, alpha=0.42,
                    solid_capstyle="round", zorder=2)
        ax.plot(diff[i], y, "o", ms=8, color=BLUE, zorder=4)
        if land is not None:
            ax.plot(land[i], y, "D", ms=5.5, color=SAND, zorder=4)

    lo = float(np.nanmin(p25 if p25 is not None else diff))
    hi = float(np.nanmax(p75 if p75 is not None else diff))
    span = hi - lo
    ax.set_xlim(lo - 0.06 * span, hi + 0.30 * span)
    for y, i in zip(ypos, o):
        ax.annotate(f"{px[i] / 1e6:.2f} M px", (hi + 0.30 * span, y),
                    xytext=(-4, 0), textcoords="offset points", va="center",
                    ha="right", fontsize=7.8, color=MUTED)

    ax.set_yticks(ypos)
    ax.set_yticklabels([tiles[i] for i in o], fontsize=8.4)
    ax.set_ylabel("overlap tile")
    ax.set_xlabel("orbit 77 minus orbit 4, VH gamma0 (dB)")
    ax.set_ylim(-0.7, len(o) - 0.3)
    frame(ax, grid="x")

    h = [ax.plot([], [], "o", ms=8, color=BLUE)[0]]
    lb = ["median, all pixels"]
    if land is not None:
        h.append(ax.plot([], [], "D", ms=5.5, color=SAND)[0])
        lb.append("median, land only")
    h.append(ax.plot([], [], lw=2.8, color=SLATE, alpha=0.42)[0])
    lb.append("25th to 75th percentile")
    legend_into(lax, h, lb, ncol=3)

    save(fig, "orbit_offset", dpi)


# --------------------------------------------------------------------------
# 6. Sensitivity grid
# --------------------------------------------------------------------------
def fig_sensitivity_grid(dpi):
    d = need("sensitivity_grid.csv")
    if d is None:
        return
    slope, occ = d["slope_max_deg"], d["occurrence_permanent_min"]
    edge = d.get("edge_buffer_m", d.get("edge_buffer_px"))
    ha, pub = d["flood_ha"], d.get("is_published", np.zeros_like(d["flood_ha"]))

    s_vals = sorted(set(slope.tolist()))
    o_vals = sorted(set(occ.tolist()))
    e_vals = sorted(set(edge.tolist()))
    n = len(s_vals)

    vmin, vmax = float(np.nanmin(ha)), float(np.nanmax(ha))

    fig, slot, _ = canvas(
        2.28 * n + 2.0, 4.3,
        "Where the answer moves without the method changing",
        f"{int(d['_n'])} combinations of the three refinement parameters, "
        f"spanning {vmin:,.0f} to {vmax:,.0f} ha of mapped flood",
        "None of these three parameters can be validated. The hand labels "
        "cover 65 floodplain chips and contain no steep terrain, no swath "
        "edge, and no\npermanent channel of the kind these cuts are aimed at. "
        "Between them they set roughly 45% of the difference between the raw "
        "threshold output and\nthe reported figure, so the range above is the "
        "honest width of that one decision. Every combination was answered "
        "from a single binning pass over\nevery water pixel rather than "
        f"{int(d['_n'])} separate runs of the pipeline.",
        "sensitivity_grid.csv")

    inner = slot.subgridspec(1, n + 1, width_ratios=[1] * n + [0.06],
                             wspace=0.10)
    axes = [fig.add_subplot(inner[0, k]) for k in range(n)]
    cbx = fig.add_subplot(inner[0, n])

    im = None
    for k, (ax, s) in enumerate(zip(axes, s_vals)):
        g = np.full((len(o_vals), len(e_vals)), np.nan)
        for i, ov in enumerate(o_vals):
            for j, ev in enumerate(e_vals):
                m = (slope == s) & (occ == ov) & (edge == ev)
                if m.any():
                    g[i, j] = float(np.nanmean(ha[m]))
        im = ax.imshow(g, cmap="YlGnBu", vmin=vmin, vmax=vmax, aspect="auto",
                       origin="lower", interpolation="nearest")
        ax.set_xticks(range(len(e_vals)))
        ax.set_xticklabels([f"{v:g}" for v in e_vals], fontsize=7.6)
        ax.set_yticks(range(len(o_vals)))
        if k == 0:
            ax.set_yticklabels(["none" if v > 100 else f"{v:g}"
                                for v in o_vals], fontsize=7.8)
            ax.set_ylabel("permanent-water cut\n(JRC occurrence, %)")
        else:
            ax.set_yticklabels([])
        ax.set_xlabel("edge buffer (m)")
        ax.set_title("no slope cut" if s >= 90 else f"slope ≤ {s:g}°",
                     fontsize=9.5, color=INK, fontweight="bold", pad=5)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)

        m = (slope == s) & (pub == 1)
        if m.any():
            i, j = o_vals.index(float(occ[m][0])), e_vals.index(float(edge[m][0]))
            ax.plot(j, i, marker="s", ms=18, mfc="none", mec=BRICK, mew=2.2)
            ax.annotate("published", (j, i), xytext=(0, 16),
                        textcoords="offset points", ha="center", fontsize=7.8,
                        color=BRICK, fontweight="bold")

    cb = fig.colorbar(im, cax=cbx)
    cb.set_label("mapped flood area (ha)", fontsize=LAB_SZ, color=INK)
    cb.ax.tick_params(labelsize=TICK_SZ)
    cb.outline.set_visible(False)

    save(fig, "sensitivity_grid", dpi)


# --------------------------------------------------------------------------
# 7. Flooded cropland by district
# --------------------------------------------------------------------------
def fig_flooded_cropland(dpi, csv_name="district_flood_stats.csv",
                         out="flooded_cropland", when="12 August 2016"):
    d = need(csv_name)
    if d is None:
        return
    name = [str(x) for x in d["district"]]
    crop = d["flooded_cropland_ha"]
    share = d.get("pct_of_imaged_cropland_flooded")
    seen = d.get("imaged_pct_of_district")

    keep = np.argsort(crop)[::-1][:18][::-1]
    ypos = np.arange(len(keep))
    part = np.array([seen is not None and seen[i] < 99.5 for i in keep])

    fig, slot, lax = canvas(
        11.4, 6.3,
        f"Flooded cropland by district, {when}",
        "Cropland is ESA WorldCover class 40. Districts are geoBoundaries "
        "ADM2 at current vintage",
        "The two panels rank differently on purpose. Hectares say where the "
        "most land went under. Share says where it mattered most to the "
        "district.\nA district the swath only partly covers is shaded "
        "differently, because its total is a floor rather than a "
        "measurement, and its share is computed against\nthe cropland "
        "actually imaged rather than all the cropland it has. WorldCover is "
        "a 2021 product used on a 2016 event, since no open 10 m cropland "
        "map\nexists for 2016. Assam has also created districts since 2016, "
        "so these boundaries are not the ones in use at the time.",
        csv_name, legend_row=True)

    inner = slot.subgridspec(1, 2, width_ratios=[1.5, 1], wspace=0.04)
    ax = fig.add_subplot(inner[0, 0])
    bx = fig.add_subplot(inner[0, 1], sharey=ax)

    cols = [SLATE if p else BLUE for p in part]
    ax.barh(ypos, crop[keep], height=0.68, color=cols)
    for y, i in zip(ypos, keep):
        ax.annotate(f"{crop[i]:,.0f}", (crop[i], y), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=8.2,
                    color=MUTED)
    ax.set_yticks(ypos)
    ax.set_yticklabels([name[i] for i in keep], fontsize=8.8)
    ax.set_xlabel("flooded cropland (ha)")
    ax.set_xlim(0, float(np.nanmax(crop)) * 1.18)
    ax.xaxis.set_major_locator(MaxNLocator(5))
    frame(ax, grid="x")

    if share is not None:
        bx.barh(ypos, share[keep], height=0.68,
                color=[SAND if not p else "#EFCFA2" for p in part])
        for y, i in zip(ypos, keep):
            lab = f"{share[i]:.1f}%"
            if seen is not None and seen[i] < 99.5:
                lab += f"   {seen[i]:.0f}% imaged"
            bx.annotate(lab, (share[i], y), xytext=(5, 0),
                        textcoords="offset points", va="center", fontsize=8.2,
                        color=MUTED)
        bx.set_xlabel("share of that district's imaged cropland under water")
        bx.set_xlim(0, float(np.nanmax(share[keep])) * 1.75)
        bx.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.0f}%"))
        bx.xaxis.set_major_locator(MaxNLocator(5))
        bx.tick_params(labelleft=False)
        frame(bx, grid="x")
    else:
        bx.set_axis_off()

    # An empty barh container carries no colour into a legend, so
    # both swatches came out matplotlib's default blue while the
    # bars behind them were BLUE and SLATE. A Patch carries it.
    h = [Patch(facecolor=BLUE), Patch(facecolor=SLATE)]
    legend_into(lax, h, ["fully imaged by this pass",
                         "partly imaged, total is a floor"], ncol=2)

    save(fig, out, dpi)


# --------------------------------------------------------------------------
# The same figure for the other acquisitions and for the area-matched
# operating point. district_stats.py used to draw these itself, in a different
# style, with 12 August hard-coded into every one of their titles.
CROPLAND_VARIANTS = [
    ("areamatched", "12 August 2016, area-matched threshold"),
    ("20160807", "7 August 2016"),
    ("20160807am", "7 August 2016, area-matched threshold"),
    ("20160831", "31 August 2016"),
    ("20160831am", "31 August 2016, area-matched threshold"),
]


def fig_cropland_variants(dpi):
    for tag, when in CROPLAND_VARIANTS:
        print(f"  {tag}")
        fig_flooded_cropland(dpi,
                             csv_name=f"district_flood_stats_{tag}.csv",
                             out=f"flooded_cropland_{tag}", when=when)


FIGURES = {
    "operating_point": fig_operating_point,
    "accuracy_ci": fig_accuracy_ci,
    "change_sweep": fig_change_sweep,
    "product_vs_window": fig_product_vs_window,
    "orbit_offset": fig_orbit_offset,
    "sensitivity_grid": fig_sensitivity_grid,
    "flooded_cropland": fig_flooded_cropland,
    "cropland_variants": fig_cropland_variants,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    FIGS.mkdir(parents=True, exist_ok=True)
    wanted = ([s.strip() for s in args.only.split(",") if s.strip()]
              or list(FIGURES))
    unknown = [w for w in wanted if w not in FIGURES]
    if unknown:
        sys.exit(f"unknown figure name(s): {', '.join(unknown)}\n"
                 f"available: {', '.join(FIGURES)}")

    for w in wanted:
        print(f"\n{w}")
        try:
            FIGURES[w](args.dpi)
        except Exception as e:                                 # noqa: BLE001
            print(f"  FAILED: {type(e).__name__}: {e}")

    print("\ndone.")


if __name__ == "__main__":
    main()
