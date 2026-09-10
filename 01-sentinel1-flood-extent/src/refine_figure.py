"""
The before and after of refinement, drawn from the two rasters themselves.

results/fullscene/refine_before_after.png was originally produced by a version
of refine_scene.py that no longer exists. It showed 217,490 ha going to
130,772 ha, which is the slope cut applied to the unbuffered raster: the edge
rim is full of steep pixels, so removing slope first takes out 86,718 ha
instead of the 68,437 the current pipeline records. The README section it sits
in is about the chain that ends at 119,779 ha, so the figure and its caption
described different pipelines.

This rebuilds it from the raw and refined rasters, so it cannot drift again.
Nothing is recomputed. Three panels:

    raw threshold output
    refined map
    what changed, and into what

The third panel is exact. A pixel that was flood in the raw map is now one of
three things: still flood, no data (the swath-edge buffer), or land (the slope
cut and the minimum mapping unit, which cannot be told apart without the DEM
and are labelled as one class). Their totals are checked against
fullscene_stats_*.json and the script refuses to write if they disagree.

Layout note. Every block below the maps gets its own axes, sized in inches
from what actually goes in it. The earlier version packed the legend, the
caption and the source line into one short axes and positioned them by axes
fraction, so the caption ran off the bottom of that axes and printed on top of
the source line. Constrained layout reserves room for axes, not for text
placed inside one, so the only reliable fix is to give each block a row.

Run from anywhere:

    python 01-sentinel1-flood-extent\\src\\refine_figure.py
    python 01-sentinel1-flood-extent\\src\\refine_figure.py --variant areamatched

Options:
    --dec N        display decimation, default 6
    --variant      "" (default), areamatched, 20160807, 20160807am, ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
RES_M = 20.0
PX_HA = cfg.pixel_ha(RES_M)
SCENE = cfg.RESULTS / "fullscene"

INK, MUTED, RULE = "#16222B", "#5C6B76", "#C9D2D8"
C_LAND, C_FLOOD, C_PERM, C_NODATA = "#EDEAE3", "#5BA3D0", "#123B63", "#FFFFFF"
C_KEPT, C_EDGE, C_STEEP = "#1B5E8C", "#8E4585", "#E0A458"


def counts(path, tile=2048):
    c = np.zeros(256, np.int64)
    with rasterio.open(path) as s:
        for i in range(0, s.height, tile):
            for j in range(0, s.width, tile):
                w = Window(j, i, min(tile, s.width - j),
                           min(tile, s.height - i))
                c += np.bincount(s.read(1, window=w).ravel(), minlength=256)
    return c


def fate(raw_p, ref_p, tile=2048):
    """Where did each raw flood pixel end up? Exact, from the two rasters."""
    kept = to_nodata = to_land = other = 0
    with rasterio.open(raw_p) as A, rasterio.open(ref_p) as B:
        if (A.height, A.width) != (B.height, B.width):
            sys.exit(f"grids differ: {A.width}x{A.height} against "
                     f"{B.width}x{B.height}. Nothing written.")
        for i in range(0, A.height, tile):
            for j in range(0, A.width, tile):
                w = Window(j, i, min(tile, A.width - j),
                           min(tile, A.height - i))
                a, b = A.read(1, window=w), B.read(1, window=w)
                was = a == FLOOD
                kept += int(np.count_nonzero(was & (b == FLOOD)))
                to_nodata += int(np.count_nonzero(was & (b == NODATA)))
                to_land += int(np.count_nonzero(was & (b == LAND)))
                other += int(np.count_nonzero(
                    was & ~((b == FLOOD) | (b == NODATA) | (b == LAND))))
    return kept, to_nodata, to_land, other


def read_display(path, dec):
    with rasterio.open(path) as s:
        h, w = max(1, s.height // dec), max(1, s.width // dec)
        img = s.read(1, out_shape=(h, w))
        left, bottom, right, top = s.bounds
    return img, (left, right, bottom, top)


def show_classes(ax, img, extent):
    cmap = ListedColormap([C_NODATA, C_LAND, C_FLOOD, C_PERM])
    disp = np.zeros(img.shape, np.uint8)
    disp[img == LAND] = 1
    disp[img == FLOOD] = 2
    disp[img == PERMANENT] = 3
    ax.imshow(disp, cmap=cmap, norm=BoundaryNorm([0, 1, 2, 3, 4], 4),
              extent=extent, interpolation="nearest", origin="upper")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dec", type=int, default=6)
    ap.add_argument("--variant", default="")
    args = ap.parse_args()

    tag = f"{RES_M:g}m" + (f"_{args.variant}" if args.variant else "")
    raw_p = SCENE / f"{cfg.EVENT}_water_{tag}.tif"
    ref_p = SCENE / f"{cfg.EVENT}_water_{tag}_refined.tif"
    for p in (raw_p, ref_p):
        if not p.exists():
            sys.exit(f"missing: {p}\nNothing written.")

    stats_p = cfg.RESULTS / f"fullscene_stats_{tag}.json"
    st = json.load(open(stats_p, encoding="utf-8")) if stats_p.exists() else {}
    ref = st.get("refined", {})

    print(f"counting {raw_p.name} and {ref_p.name} at full resolution ...")
    craw, cref = counts(raw_p), counts(ref_p)
    kept, to_nodata, to_land, other = fate(raw_p, ref_p)

    raw_flood = craw[FLOOD] * PX_HA
    ref_flood = cref[FLOOD] * PX_HA
    ha_kept, ha_edge, ha_land = kept * PX_HA, to_nodata * PX_HA, to_land * PX_HA

    print(f"\n  raw flood              {raw_flood:>12,.0f} ha")
    print(f"    still flood          {ha_kept:>12,.0f} ha")
    print(f"    became no data       {ha_edge:>12,.0f} ha   swath-edge buffer")
    print(f"    became land          {ha_land:>12,.0f} ha   slope cut and MMU")
    if other:
        print(f"    became something else{other * PX_HA:>12,.0f} ha   "
              f"UNEXPECTED")
    print(f"  refined flood          {ref_flood:>12,.0f} ha")

    # Every raw flood pixel must be accounted for, and the totals must match
    # what the pipeline recorded. If not, one of them is stale.
    if abs((ha_kept + ha_edge + ha_land + other * PX_HA) - raw_flood) > 1.0:
        sys.exit("\nthe three fates do not sum to the raw flood total. "
                 "Nothing written.")
    if abs(ha_kept - ref_flood) > 1.0:
        sys.exit(f"\nkept {ha_kept:,.0f} ha but the refined raster holds "
                 f"{ref_flood:,.0f} ha. Nothing written.")
    for label, got, want in (("flood_ha", raw_flood, st.get("flood_ha")),
                             ("refined.flood_ha_after", ref_flood,
                              ref.get("flood_ha_after"))):
        if want is not None and abs(got - float(want)) > max(1.0,
                                                             0.005 * got):
            sys.exit(f"\n{stats_p.name} records {label} = {float(want):,.0f} "
                     f"but the raster holds {got:,.0f}. One is stale. "
                     f"Nothing written.")
    steep = ref.get("removed_steep_ha")
    small = ref.get("removed_small_ha")
    if steep is not None and small is not None:
        expect = float(steep) + float(small)
        if abs(ha_land - expect) > max(1.0, 0.005 * expect):
            sys.exit(f"\nflood that became land is {ha_land:,.0f} ha but "
                     f"removed_steep + removed_small is {expect:,.0f}. "
                     f"Nothing written.")
        print(f"\n  checks out: {float(steep):,.0f} steep + "
              f"{float(small):,.0f} below the MMU = {expect:,.0f} ha")

    # ------------------------------------------------------------------ draw
    a, extent = read_display(raw_p, args.dec)
    b, _ = read_display(ref_p, args.dec)
    ch = np.zeros(a.shape, np.uint8)                       # 0 = background
    was = a == FLOOD
    ch[was & (b == FLOOD)] = 1
    ch[was & (b == NODATA)] = 2
    ch[was & (b == LAND)] = 3

    # The caption is built before the figure, because its line count decides
    # how tall its row has to be.
    cap = [f"The third panel is exact rather than illustrative. Every pixel "
           f"the raw map called flood is now one of three things, and the "
           f"three totals sum to {raw_flood:,.0f} ha."]
    if steep is not None and small is not None:
        cap.append(f"The slope cut and the minimum mapping unit share a "
                   f"colour because these two rasters cannot separate them. "
                   f"The pipeline records them as {float(steep):,.0f} ha and "
                   f"{float(small):,.0f} ha.")
    cap.append("The edge buffer becomes no data rather than land, because "
               "those pixels are unmeasured rather than dry.")
    caption = "\n".join(cap)

    left, right, bottom, top = extent
    aspect = (right - left) / (top - bottom)
    map_h = 9.2
    map_w = float(np.clip(map_h * aspect, 2.6, 7.0))
    fig_w = 3 * map_w + 1.4

    # Row heights in inches, from the content of each row. Two legend rows for
    # the fate classes plus padding, one text line per caption line.
    head_h = 0.80
    legend_h = 0.74
    cap_h = 0.14 + 0.163 * len(cap)
    src_h = 0.24
    fig_h = head_h + map_h + legend_h + cap_h + src_h

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="white",
                     layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, hspace=0.0, wspace=0.0)
    outer = fig.add_gridspec(5, 1, height_ratios=[head_h, map_h, legend_h,
                                                  cap_h, src_h])
    hax = fig.add_subplot(outer[0]); hax.set_axis_off()
    grid = outer[1].subgridspec(1, 3, wspace=0.04)
    lrow = outer[2].subgridspec(1, 3, wspace=0.04)
    lax_map = fig.add_subplot(lrow[0, 0:2]); lax_map.set_axis_off()
    lax_fate = fig.add_subplot(lrow[0, 2]); lax_fate.set_axis_off()
    cax = fig.add_subplot(outer[3]); cax.set_axis_off()
    sax = fig.add_subplot(outer[4]); sax.set_axis_off()

    ax1 = fig.add_subplot(grid[0, 0])
    show_classes(ax1, a, extent)
    ax1.set_title(f"Raw threshold output\n{raw_flood:,.0f} ha of flood",
                  fontsize=10.5, color=INK, fontweight="bold", loc="left",
                  pad=6, linespacing=1.4)

    ax2 = fig.add_subplot(grid[0, 1])
    show_classes(ax2, b, extent)
    ax2.set_title(f"After refinement\n{ref_flood:,.0f} ha of flood",
                  fontsize=10.5, color=INK, fontweight="bold", loc="left",
                  pad=6, linespacing=1.4)

    ax3 = fig.add_subplot(grid[0, 2])
    ax3.imshow(ch, cmap=ListedColormap(["#F4F6F7", C_KEPT, C_EDGE, C_STEEP]),
               norm=BoundaryNorm([0, 1, 2, 3, 4], 4), extent=extent,
               interpolation="nearest", origin="upper")
    ax3.set_title(f"What happened to each flood pixel\n"
                  f"{ha_kept / raw_flood * 100:.0f}% kept",
                  fontsize=10.5, color=INK, fontweight="bold", loc="left",
                  pad=6, linespacing=1.4)

    for ax in (ax1, ax2, ax3):
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor(RULE); sp.set_linewidth(0.7)

    hax.text(0, 1.0, f"How {raw_flood:,.0f} ha becomes {ref_flood:,.0f} ha",
             fontsize=15, fontweight="bold", color=INK, va="top", ha="left",
             transform=hax.transAxes)
    hax.text(0, 0.0, f"{cfg.EVENT}, {RES_M:g} m, drawn from the two rasters "
             f"the pipeline wrote. Nothing here is recomputed.",
             fontsize=10, color=MUTED, va="bottom", ha="left",
             transform=hax.transAxes)

    # One legend per thing it explains. The first two panels share a class
    # scheme; the third has its own, so its key sits under it rather than
    # running across all three.
    lax_map.legend(
        handles=[Patch(facecolor=C_PERM, label="permanent water, unchanged"),
                 Patch(facecolor=C_FLOOD, label="flood"),
                 Patch(facecolor=C_LAND, label="land, imaged"),
                 Patch(facecolor=C_NODATA, edgecolor=RULE, label="no data")],
        loc="upper left", ncol=4, frameon=False, fontsize=8.4,
        handlelength=1.6, columnspacing=1.6, bbox_to_anchor=(0, 1.0),
        borderpad=0)

    lax_fate.legend(
        handles=[Patch(facecolor=C_KEPT,
                       label=f"kept as flood, {ha_kept:,.0f} ha"),
                 Patch(facecolor=C_EDGE,
                       label=f"to no data, swath edge, {ha_edge:,.0f} ha"),
                 Patch(facecolor=C_STEEP,
                       label=f"to land, slope and MMU, {ha_land:,.0f} ha")],
        loc="upper left", ncol=1, frameon=False, fontsize=8.4,
        handlelength=1.6, labelspacing=0.32, bbox_to_anchor=(0, 1.0),
        borderpad=0)

    cax.text(0, 1.0, caption, fontsize=8.4, color=MUTED, va="top", ha="left",
             transform=cax.transAxes, linespacing=1.62)
    sax.text(0, 0.0, f"source: results/fullscene/{raw_p.name} and "
             f"{ref_p.name}, checked against {stats_p.name}",
             fontsize=7, color="#8A97A0", va="bottom", ha="left",
             transform=sax.transAxes)

    out = SCENE / ("refine_before_after.png" if not args.variant
                   else f"refine_before_after_{args.variant}.png")
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote {out.relative_to(cfg.PROJECT)}")


if __name__ == "__main__":
    main()
