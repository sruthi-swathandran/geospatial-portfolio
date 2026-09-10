"""
Publication figures for the three dated flood maps.

Writes into results/figures/ at 300 dpi, PNG and PDF:

  flood_three_dates.png/.pdf
      7, 12 and 31 August on one common extent and one colour scheme. The
      12 August pass is relative orbit 77 and covers roughly twice the ground
      of the other two on orbit 4. That difference is drawn as no data rather
      than cropped away, because it is the reason the three maps are never
      mosaicked into a single product.

  flood_recession.png/.pdf
      7 August against 31 August, same orbit, same grid, so every pixel is
      directly comparable. Each one is classed as drained, still flooded,
      newly flooded, or dry throughout. The panel is cropped to the ground
      where something changed; areas are counted before cropping, over the
      whole scene.

Run from anywhere:

    python 01-sentinel1-flood-extent\\src\\make_date_maps.py

Options:
    --dec N        display decimation, default 6. Lower is sharper and slower.
    --variant      mapoptimal (default) or areamatched.
    --no-crop      draw the recession panel on the full AOI extent.

Every area is counted at full resolution in a windowed pass, never from the
decimated display array, and is cross-checked against the figure the pipeline
already recorded in results/fullscene_stats_*.json. A disagreement over 0.5%
stops the script rather than producing a figure that contradicts the README.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.warp import transform_geom, transform as warp_transform
from shapely.geometry import shape
from shapely.ops import unary_union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Rectangle, Polygon as MplPoly

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

# --------------------------------------------------------------------------
# Class codes written by full_scene.py and preserved by refine_scene.py
# --------------------------------------------------------------------------
LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255

# Change classes computed here
CH_NODATA, CH_PERM, CH_DRY, CH_PERSIST, CH_DRAINED, CH_NEW = 0, 1, 2, 3, 4, 5

# Extent palette, identical to make_map.py so the figure set reads as one
# product. Light to dark for the water classes.
C_LAND = "#EDEAE3"
C_FLOOD = "#5BA3D0"
C_PERM = "#123B63"
C_NODATA = "#FFFFFF"

# Change palette. On the recession figure permanent water is context rather
# than a finding, so it is muted to a slate and the three change classes carry
# the colour. Blue, sand and plum stay separable in the common forms of colour
# blindness and in greyscale print.
C_PERM_CTX = "#7B94A6"
C_PERSIST = "#1B5E8C"
C_DRAINED = "#E0A458"
C_NEW = "#8E4585"

INK = "#16222B"
MUTED = "#5C6B76"
HAIRLINE = "#9AA7AF"
RULE = "#C9D2D8"

RES_M = 20.0
PX_HA = cfg.pixel_ha(RES_M)

FIGS = cfg.RESULTS / "figures"
SCENE = cfg.RESULTS / "fullscene"

# (label, relative orbit, refined raster, district csv suffix, stats json tag)
DATES = {
    "mapoptimal": [
        ("7 August 2016", 4, "India_water_20m_20160807_refined.tif",
         "_20160807", "20m_20160807"),
        ("12 August 2016", 77, "India_water_20m_refined.tif",
         "", "20m"),
        ("31 August 2016", 4, "India_water_20m_20160831_refined.tif",
         "_20160831", "20m_20160831"),
    ],
    "areamatched": [
        ("7 August 2016", 4, "India_water_20m_20160807am_refined.tif",
         "_20160807am", "20m_20160807am"),
        ("12 August 2016", 77, "India_water_20m_areamatched_refined.tif",
         "_areamatched", "20m_areamatched"),
        ("31 August 2016", 4, "India_water_20m_20160831am_refined.tif",
         "_20160831am", "20m_20160831am"),
    ],
}

VARIANT_TEXT = {
    "mapoptimal": "map-optimal operating point, −18.75 dB",
    "areamatched": "area-matched operating point, −17.75 dB",
}


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def require(path: Path) -> Path:
    if not path.exists():
        sys.exit(f"missing input: {path}\nNothing written.")
    return path


def grid_of(path: Path):
    with rasterio.open(path) as s:
        return (s.height, s.width, str(s.crs),
                tuple(round(v, 6) for v in np.asarray(s.transform)[:6]))


def assert_same_grid(paths: list[Path]) -> None:
    """Every figure here overlays or differences these rasters, so a grid
    mismatch would silently produce a wrong map rather than an error."""
    ref = grid_of(paths[0])
    for p in paths[1:]:
        g = grid_of(p)
        if g != ref:
            sys.exit(
                f"grid mismatch, nothing written.\n"
                f"  {paths[0].name}: {ref[1]}x{ref[0]} {ref[2]}\n"
                f"  {p.name}: {g[1]}x{g[0]} {g[2]}\n"
                f"These rasters cannot be compared pixel for pixel.")


def class_counts(path: Path, tile: int = 2048) -> np.ndarray:
    """Full-resolution histogram of class codes, windowed so the whole scene
    never has to sit in memory at once."""
    c = np.zeros(256, np.int64)
    with rasterio.open(path) as s:
        for i in range(0, s.height, tile):
            for j in range(0, s.width, tile):
                w = Window(j, i, min(tile, s.width - j),
                           min(tile, s.height - i))
                c += np.bincount(s.read(1, window=w).ravel(), minlength=256)
    return c


def classify_change(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a is the earlier date, b the later. Permanent water on either date wins,
    because a pixel the JRC layer calls permanent is not flood on either date
    and must never appear as drained or newly flooded."""
    out = np.full(a.shape, CH_NODATA, np.uint8)
    ok = ~((a == NODATA) | (b == NODATA))
    out[((a == PERMANENT) | (b == PERMANENT)) & ok] = CH_PERM
    out[(a == LAND) & (b == LAND) & ok] = CH_DRY
    out[(a == FLOOD) & (b == FLOOD) & ok] = CH_PERSIST
    out[(a == FLOOD) & (b == LAND) & ok] = CH_DRAINED
    out[(a == LAND) & (b == FLOOD) & ok] = CH_NEW
    return out


def change_counts(pa: Path, pb: Path, tile: int = 2048) -> np.ndarray:
    c = np.zeros(6, np.int64)
    with rasterio.open(pa) as A, rasterio.open(pb) as B:
        for i in range(0, A.height, tile):
            for j in range(0, A.width, tile):
                w = Window(j, i, min(tile, A.width - j),
                           min(tile, A.height - i))
                c += np.bincount(
                    classify_change(A.read(1, window=w),
                                    B.read(1, window=w)).ravel(),
                    minlength=6)
    return c


def read_display(path: Path, dec: int):
    with rasterio.open(path) as s:
        h, w = max(1, s.height // dec), max(1, s.width // dec)
        img = s.read(1, out_shape=(h, w))
        left, bottom, right, top = s.bounds
        crs = s.crs
    return img, (left, right, bottom, top), crs


# Which row of cropland_scene.csv goes with which map. The keys are the
# suffixes used in DATES below.
SCENE_ROW = {
    "": "12 Aug, map-optimal",
    "_areamatched": "12 Aug, area-matched",
    "_20160807": "7 Aug, map-optimal",
    "_20160807am": "7 Aug, area-matched",
    "_20160831": "31 Aug, map-optimal",
    "_20160831am": "31 Aug, area-matched",
}


def cropland_ha(suffix: str) -> float:
    """Flooded cropland over the whole raster, the figure the README quotes.

    Summing flooded_cropland_ha over district_flood_stats*.csv gives a sum over
    ADM2 polygons instead. On 12 August those polygons account for 110,081 of
    the 119,779 ha of mapped flood, so the cropland total that goes with them
    is 43,494 ha against the scene's 46,943, and this sheet was printing the
    smaller one beside a scene-wide flood figure. See CHANGELOG.md C-12. The
    7 and 31 August passes are relative orbit 4 and fall entirely inside Indian
    districts, so for those two the two footprints agree to the hectare.
    """
    label = SCENE_ROW.get(suffix)
    if label is None:
        raise SystemExit(f"no cropland_scene.csv row is mapped to suffix "
                         f"{suffix!r}. Add one to SCENE_ROW. Nothing written.")
    p = require(cfg.RESULTS / "cropland_scene.csv")
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["variant"].strip() == label:
                return float(r["flooded_cropland_scene_ha"])
    raise SystemExit(f"no row named {label!r} in {p.name}. Run "
                     f"cropland_scene.py first. Nothing written.")


def recorded_flood_ha(tag: str) -> float | None:
    """The figure the pipeline already wrote. full_scene.py records its stats
    before refine_scene.py runs, so the reported number lives under
    refined.flood_ha_after, not under the top-level flood_ha."""
    p = cfg.RESULTS / f"fullscene_stats_{tag}.json"
    if not p.exists():
        return None
    j = json.load(open(p, encoding="utf-8"))
    ref = j.get("refined")
    if isinstance(ref, dict) and "flood_ha_after" in ref:
        return float(ref["flood_ha_after"])
    return None


# --------------------------------------------------------------------------
# Shared map furniture
# --------------------------------------------------------------------------
def draw_districts(ax, dist, lw=0.35):
    for g in dist:
        for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            x, y = poly.exterior.xy
            ax.plot(x, y, color="#6B7B85", linewidth=lw, alpha=0.8, zorder=3)


def draw_graticule(ax, crs, extent, dlon=0.5, dlat=0.5):
    left, right, bottom, top = extent
    lons = np.arange(92.0, 94.51, dlon)
    lats = np.arange(25.0, 28.51, dlat)
    for lo in lons:
        la = np.linspace(24.4, 28.7, 60)
        xs, ys = warp_transform("EPSG:4326", str(crs), [lo] * 60, la)
        ax.plot(xs, ys, color=HAIRLINE, lw=0.35, ls=(0, (2, 3)), zorder=2)
    for la in lats:
        lo = np.linspace(91.7, 94.6, 60)
        xs, ys = warp_transform("EPSG:4326", str(crs), lo, [la] * 60)
        ax.plot(xs, ys, color=HAIRLINE, lw=0.35, ls=(0, (2, 3)), zorder=2)
    xt, _ = warp_transform("EPSG:4326", str(crs), list(lons),
                           [26.5] * len(lons))
    _, yt = warp_transform("EPSG:4326", str(crs), [93.0] * len(lats),
                           list(lats))
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{v:g}°E" for v in lons], fontsize=7)
    ax.set_yticks(yt)
    ax.set_yticklabels([f"{v:g}°N" for v in lats], fontsize=7)
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    for sp in ax.spines.values():
        sp.set_edgecolor("#2A3439")
        sp.set_linewidth(0.7)
    ax.tick_params(length=2.5, color="#2A3439")


def draw_scalebar(ax, extent, length_m=50000, side="left"):
    """Positioned as a fraction of the drawn extent, so it lands sensibly
    whether the panel shows the whole AOI or a cropped footprint."""
    left, right, bottom, top = extent
    w, h = right - left, top - bottom
    if side == "left":
        bx = left + 0.06 * w
    else:
        bx = right - 0.06 * w - length_m
    by = bottom + 0.05 * h
    bar_h = 0.0065 * h
    ax.add_patch(Rectangle((bx, by), length_m, bar_h, fc="#2A3439",
                           ec="none", zorder=5))
    ax.add_patch(Rectangle((bx, by), length_m / 2, bar_h, fc="white",
                           ec="#2A3439", lw=0.6, zorder=6))
    for frac, lab in ((0, "0"), (0.5, f"{length_m // 2000:g}"),
                      (1, f"{length_m // 1000:g} km")):
        ax.text(bx + length_m * frac, by + bar_h * 2.1, lab, fontsize=6.8,
                ha="center", color="#2A3439", zorder=6)


def draw_north(ax, extent):
    left, right, bottom, top = extent
    w, h = right - left, top - bottom
    nx, ny = right - 0.10 * w, top - 0.075 * h
    ax.annotate("", xy=(nx, ny), xytext=(nx, ny - 0.055 * h),
                arrowprops=dict(arrowstyle="-|>", color="#2A3439", lw=1.2),
                zorder=6)
    ax.text(nx, ny + 0.012 * h, "N", fontsize=10, ha="center", color="#2A3439",
            fontweight="bold", zorder=6)


def draw_locator(fig, rect, india, title=None):
    iax = fig.add_axes(rect)
    iax.set_facecolor("#F7F9FA")
    for poly in (india.geoms if india.geom_type == "MultiPolygon"
                 else [india]):
        if poly.area < 0.5:
            continue
        iax.add_patch(MplPoly(np.array(poly.exterior.coords), closed=True,
                              fc="#E3E8EB", ec=HAIRLINE, lw=0.35))
    b = cfg.BBOX
    iax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc="none",
                            ec="#B3452F", lw=1.3, zorder=5))
    iax.set_xlim(67, 98)
    iax.set_ylim(6, 37)
    iax.set_aspect(1 / np.cos(np.deg2rad(22)))
    iax.set_xticks([])
    iax.set_yticks([])
    for sp in iax.spines.values():
        sp.set_edgecolor(HAIRLINE)
        sp.set_linewidth(0.5)
    if title:
        iax.set_title(title, fontsize=8, color=MUTED, pad=3)
    return iax


def credit(fig, x=0.05, y=0.014):
    fig.text(x, y,
             "Contains modified Copernicus Sentinel data 2016, processed by "
             "Microsoft Planetary Computer. Surface water: JRC/Google. "
             "Land cover © ESA WorldCover 2021. Boundaries: geoBoundaries.",
             fontsize=7, color="#8A97A0", ha="left")


# --------------------------------------------------------------------------
# Figure 1: three dates
# --------------------------------------------------------------------------
def figure_three_dates(rows, dist, india, dec, variant):
    cmap = ListedColormap([C_NODATA, C_LAND, C_FLOOD, C_PERM])
    norm = BoundaryNorm([0, 1, 2, 3, 4], 4)

    fig = plt.figure(figsize=(15.0, 12.4), facecolor="white")
    gs = gridspec.GridSpec(2, 3, height_ratios=[1, 0.235],
                           wspace=0.075, hspace=0.055,
                           left=0.05, right=0.975, top=0.885, bottom=0.045)

    for k, r in enumerate(rows):
        img, extent, crs = read_display(r["path"], dec)
        ax = fig.add_subplot(gs[0, k])
        ax.set_facecolor("white")

        disp = np.zeros(img.shape, np.uint8)          # 0 -> no data
        disp[img == LAND] = 1
        disp[img == FLOOD] = 2
        disp[img == PERMANENT] = 3
        ax.imshow(disp, cmap=cmap, norm=norm, extent=extent,
                  interpolation="nearest", origin="upper")

        draw_districts(ax, dist)
        draw_graticule(ax, crs, extent)
        if k == 0:
            # Scale bar on the right so it cannot collide with the area box,
            # which sits bottom left in every panel.
            draw_scalebar(ax, extent, side="right")
            draw_north(ax, extent)
        else:
            ax.set_yticklabels([])

        ax.set_title(f"{r['label']}\nrelative orbit {r['orbit']}",
                     fontsize=11.5, fontweight="bold", color=INK, pad=6,
                     loc="left", linespacing=1.35)

        ax.text(0.035, 0.018,
                f"flood  {r['flood_ha']:,.0f} ha\n"
                f"cropland  {r['crop_ha']:,.0f} ha\n"
                f"imaged  {r['imaged_ha'] / 1e6:.2f} M ha",
                transform=ax.transAxes, fontsize=8.4, va="bottom", ha="left",
                color=INK, linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.42", fc="white",
                          ec=RULE, lw=0.6, alpha=0.94), zorder=7)

    # ---------------------------------------------------------------- strip
    sax = fig.add_subplot(gs[1, :])
    sax.axis("off")
    sax.set_xlim(0, 1)
    sax.set_ylim(0, 1)

    sax.text(0.0, 0.94, "LEGEND", fontsize=8.5, fontweight="bold",
             color=MUTED, va="top")
    lx = 0.0
    for c, lab, note in ((C_PERM, "Permanent water",
                          "JRC occurrence ≥ 50%"),
                         (C_FLOOD, "Flood water",
                          "dark on the date, not permanent"),
                         (C_LAND, "Land, imaged", ""),
                         (C_NODATA, "No data",
                          "outside the swath, or edge buffer")):
        sax.add_patch(Rectangle((lx, 0.70), 0.014, 0.10, fc=c,
                                ec="#6B7B85", lw=0.5, transform=sax.transAxes))
        sax.text(lx + 0.021, 0.795, lab, fontsize=9.2, va="top", color=INK)
        if note:
            sax.text(lx + 0.021, 0.665, note, fontsize=7.4, va="top",
                     style="italic", color=MUTED)
        lx += 0.185

    sax.plot([0, 1], [0.545, 0.545], color=RULE, lw=0.7,
             transform=sax.transAxes, clip_on=False)

    # Imaged areas are read back from the counted values rather than restated,
    # so this sentence cannot drift away from the boxes above it.
    im = [r["imaged_ha"] / 1e6 for r in rows]
    sax.text(0.0, 0.46,
             f"The three maps are never merged. The 12 August pass is "
             f"relative orbit 77 and images {im[1]:.2f} M ha; 7 and 31 August "
             f"are orbit 4 and image {im[0]:.2f} and {im[2]:.2f} M ha. "
             f"Mosaicking them would join\nsurfaces observed at different "
             f"incidence angles on different days, and would misstate area by "
             f"roughly 9,150 ha. Where a panel is white, nothing was "
             f"observed, which is not the\nsame as observing no water. "
             f"Imaged area is measured after the 600 m swath-edge buffer has "
             f"been set to no data. Areas are counted at full resolution; the "
             f"display is decimated {dec}× for drawing only.",
             fontsize=8.2, va="top", color=MUTED, linespacing=1.6)

    sax.text(0.0, 0.10,
             f"Projection {cfg.TARGET_CRS} (UTM zone 46N), {RES_M:.0f} m "
             f"pixel  ·  Sentinel-1A IW GRD, RTC gamma0, VH  ·  "
             f"{VARIANT_TEXT[variant]}  ·  cropland is ESA WorldCover "
             f"class {cfg.CROPLAND_CLASS}  ·  produced "
             f"{dt.date.today().strftime('%d %B %Y')}",
             fontsize=7.6, va="top", color=MUTED)

    draw_locator(fig, [0.878, 0.735, 0.092, 0.135], india)

    fig.suptitle("Brahmaputra valley flood extent, three Sentinel-1 "
                 "acquisitions, August 2016",
                 fontsize=17, fontweight="bold", color=INK,
                 x=0.05, y=0.962, ha="left")
    fig.text(0.05, 0.932,
             "Each date mapped independently on its own swath. Monsoon "
             "season, Kharif 2016, central Brahmaputra valley, Assam and "
             "adjoining states",
             fontsize=10.5, color=MUTED, ha="left")
    credit(fig)
    return fig


# --------------------------------------------------------------------------
# Figure 2: recession
# --------------------------------------------------------------------------
def crop_to(disp, extent, mask, pad_frac=0.055):
    """Trim the display array to the bounding box of mask, with padding.
    Purely cosmetic: every area in this figure was counted at full resolution
    over the whole scene before any of this ran."""
    rows_ok = np.where(mask.any(1))[0]
    cols_ok = np.where(mask.any(0))[0]
    if not rows_ok.size or not cols_ok.size:
        return disp, extent
    left, right, bottom, top = extent
    h, w = disp.shape
    pr = max(2, int(round((rows_ok[-1] - rows_ok[0] + 1) * pad_frac)))
    pc = max(2, int(round((cols_ok[-1] - cols_ok[0] + 1) * pad_frac)))
    r0, r1 = max(0, rows_ok[0] - pr), min(h, rows_ok[-1] + pr + 1)
    c0, c1 = max(0, cols_ok[0] - pc), min(w, cols_ok[-1] + pc + 1)
    dx, dy = (right - left) / w, (top - bottom) / h
    return (disp[r0:r1, c0:c1],
            (left + c0 * dx, left + c1 * dx, top - r1 * dy, top - r0 * dy))


def figure_recession(pa, pb, counts, dist, dec, meta, do_crop=True):
    cmap = ListedColormap([C_NODATA, C_PERM_CTX, C_LAND, C_PERSIST,
                           C_DRAINED, C_NEW])
    norm = BoundaryNorm([0, 1, 2, 3, 4, 5, 6], 6)

    a, extent, crs = read_display(pa, dec)
    b, _, _ = read_display(pb, dec)
    if a.shape != b.shape:
        sys.exit("decimated shapes differ, nothing written.")
    disp = classify_change(a, b)

    if do_crop:
        changed = ((disp == CH_DRAINED) | (disp == CH_PERSIST)
                   | (disp == CH_NEW))
        if changed.any():
            disp, extent = crop_to(disp, extent, changed)
        else:
            disp, extent = crop_to(disp, extent, disp != CH_NODATA)

    # Size the figure from the cropped aspect so the map is neither a sliver
    # nor mostly empty, whatever the crop turns out to be.
    left, right, bottom, top = extent
    aspect = (right - left) / (top - bottom)
    map_h = 10.0
    map_w = float(np.clip(map_h * aspect, 3.2, 10.0))
    text_w = 6.5
    fig_w = map_w + text_w + 1.2
    fig_h = map_h + 1.75

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="white")
    gs = gridspec.GridSpec(1, 2, width_ratios=[map_w, text_w], wspace=0.05,
                           left=0.055, right=0.978,
                           top=1 - 1.30 / fig_h, bottom=0.42 / fig_h)

    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor("white")
    ax.imshow(disp, cmap=cmap, norm=norm, extent=extent,
              interpolation="nearest", origin="upper")
    draw_districts(ax, dist)
    draw_graticule(ax, crs, extent, dlon=0.5, dlat=0.5)
    draw_scalebar(ax, extent, side="left")
    draw_north(ax, extent)

    # ---------------------------------------------------------------- panel
    rax = fig.add_subplot(gs[0, 1])
    rax.axis("off")
    rax.set_xlim(0, 1)
    rax.set_ylim(0, 1)
    y = [0.99]

    def gap(dy):
        y[0] -= dy

    def head(t):
        rax.text(0.0, y[0], t, fontsize=9, fontweight="bold", color=MUTED,
                 va="top", ha="left", transform=rax.transAxes)
        y[0] -= 0.028

    def para(t, size=8.2, color=MUTED, lead=1.65):
        rax.text(0.0, y[0], t, fontsize=size, color=color, va="top",
                 ha="left", transform=rax.transAxes, linespacing=lead)
        y[0] -= 0.0175 * size / 8.2 * (t.count("\n") + 1) * lead

    head("LEGEND")
    for c, lab, note in (
        (C_DRAINED, "Drained", "flood on 7 Aug, dry on 31 Aug"),
        (C_PERSIST, "Still flooded", "flood on both dates"),
        (C_NEW, "Newly flooded", "dry on 7 Aug, flood on 31 Aug"),
        (C_PERM_CTX, "Permanent water",
         "JRC occurrence ≥ 50% on either date"),
        (C_LAND, "Dry throughout", ""),
        (C_NODATA, "No data", "not imaged on both dates"),
    ):
        rax.add_patch(Rectangle((0.0, y[0] - 0.0155), 0.042, 0.0175, fc=c,
                                ec="#6B7B85", lw=0.5, transform=rax.transAxes))
        rax.text(0.058, y[0] - 0.001, lab, fontsize=9.5, va="top", color=INK,
                 transform=rax.transAxes)
        if note:
            rax.text(0.058, y[0] - 0.0195, note, fontsize=7.6, va="top",
                     style="italic", color=MUTED, transform=rax.transAxes)
            y[0] -= 0.0175
        y[0] -= 0.0255

    gap(0.014)
    head("WHAT MOVED, 24 DAYS")

    rax.text(0.0, y[0], "class", fontsize=8, color=MUTED, va="top",
             transform=rax.transAxes)
    rax.text(0.70, y[0], "hectares", fontsize=8, color=MUTED, va="top",
             ha="right", transform=rax.transAxes)
    rax.text(0.97, y[0], "share of 7 Aug flood", fontsize=8, color=MUTED,
             va="top", ha="right", transform=rax.transAxes)
    y[0] -= 0.021
    rax.plot([0, 0.97], [y[0] + 0.006, y[0] + 0.006], color=RULE, lw=0.7,
             transform=rax.transAxes, clip_on=False)
    y[0] -= 0.008

    drained = counts[CH_DRAINED] * PX_HA
    persist = counts[CH_PERSIST] * PX_HA
    new = counts[CH_NEW] * PX_HA
    flood_a = drained + persist
    flood_b = persist + new

    for lab, val, col, share in (
        ("Flood on 7 Aug", flood_a, C_PERSIST, None),
        ("Drained by 31 Aug", drained, C_DRAINED, drained / flood_a),
        ("Still flooded", persist, C_PERSIST, persist / flood_a),
        ("Newly flooded", new, C_NEW, new / flood_a),
        ("Flood on 31 Aug", flood_b, C_PERSIST, None),
    ):
        heavy = lab.startswith("Flood on")
        rax.text(0.0, y[0], lab, fontsize=9.5, va="top", color=INK,
                 fontweight="bold" if heavy else "normal",
                 transform=rax.transAxes)
        rax.text(0.70, y[0], f"{val:,.0f}", fontsize=9.5, va="top", ha="right",
                 color=col, fontweight="bold" if heavy else "normal",
                 transform=rax.transAxes)
        if share is not None:
            rax.text(0.97, y[0], f"{share * 100:.1f}%", fontsize=8.8,
                     va="top", ha="right", color=MUTED,
                     transform=rax.transAxes)
        y[0] -= 0.0245

    gap(0.014)
    head("AGAINST FLOODED CROPLAND")

    ca, cb = meta["crop_a"], meta["crop_b"]
    for lab, val in (("Flooded cropland, 7 Aug", ca),
                     ("Flooded cropland, 31 Aug", cb)):
        rax.text(0.0, y[0], lab, fontsize=9.5, va="top", color=INK,
                 transform=rax.transAxes)
        rax.text(0.70, y[0], f"{val:,.0f}", fontsize=9.5, va="top", ha="right",
                 color="#8A6A2F", transform=rax.transAxes)
        y[0] -= 0.0245

    gap(0.012)
    fall_total = (flood_a - flood_b) / flood_a * 100
    fall_crop = (ca - cb) / ca * 100
    rax.text(0.0, y[0],
             f"Total flood fell {fall_total:.0f}%.\n"
             f"Flooded cropland fell {fall_crop:.0f}%.",
             fontsize=12, fontweight="bold", va="top", color=INK,
             transform=rax.transAxes, linespacing=1.5)
    gap(0.070)

    para("Those rates differ because the water that persists is not sitting "
         "on fields. Fields\ndrain within about three weeks. Channels, chars "
         "and low wetland do not. Peak\nextent is the number that gets "
         "reported; duration is the number that damages\na rice crop.")
    gap(0.022)

    head("READ WITH THIS IN MIND")
    para("Both dates are relative orbit 4 on the same grid, so every pixel "
         "here is compared\nagainst itself. That is why this figure uses 7 "
         "and 31 August rather than the\n12 August peak, which was imaged "
         "from a different orbit.")
    gap(0.020)
    para("Neither the change classes nor the refinement steps behind them "
         "have been\nvalidated. The Sen1Floods11 hand labels cover 65 "
         "floodplain chips on a single\ndate and contain nothing that speaks "
         "to change between two dates. What is\ndrawn here is the difference "
         "of two unvalidated maps.")
    gap(0.020)
    para(f"Areas were counted at full resolution over the whole scene. The "
         f"panel is cropped\nto the ground where something changed and the "
         f"display is decimated {dec}×, both\nfor drawing only.")

    fig.suptitle("What the flood did between two passes on the same orbit",
                 fontsize=17, fontweight="bold", color=INK,
                 x=0.055, y=1 - 0.42 / fig_h, ha="left")
    fig.text(0.055, 1 - 0.72 / fig_h,
             f"Sentinel-1A, 7 and 31 August 2016, relative orbit 4, "
             f"{cfg.TARGET_CRS}, {RES_M:.0f} m pixel, "
             f"{meta['variant_text']}",
             fontsize=10.5, color=MUTED, ha="left")
    credit(fig, x=0.055, y=0.10 / fig_h)
    return fig


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dec", type=int, default=6,
                    help="display decimation factor, default 6")
    ap.add_argument("--variant", choices=tuple(DATES), default="mapoptimal")
    ap.add_argument("--no-crop", action="store_true",
                    help="draw the recession panel on the full AOI extent")
    args = ap.parse_args()

    FIGS.mkdir(parents=True, exist_ok=True)
    spec = DATES[args.variant]
    paths = [require(SCENE / s[2]) for s in spec]
    assert_same_grid(paths)

    print(f"variant: {args.variant}, display decimation {args.dec}\n")

    rows = []
    for (label, orbit, _fname, suffix, tag), path in zip(spec, paths):
        c = class_counts(path)
        flood = c[FLOOD] * PX_HA
        imaged = (c[LAND] + c[FLOOD] + c[PERMANENT]) * PX_HA
        crop = cropland_ha(suffix)
        rec = recorded_flood_ha(tag)

        note = ""
        if rec is not None:
            drift = abs(rec - flood) / max(rec, 1.0)
            note = f"  (stats json {rec:,.0f} ha)"
            if drift > 0.005:
                sys.exit(
                    f"\n{label}: counted {flood:,.0f} ha from {path.name} but "
                    f"results/fullscene_stats_{tag}.json records "
                    f"{rec:,.0f} ha, a {drift * 100:.1f}% disagreement.\n"
                    f"One of them is stale. Nothing written.")
        print(f"{label:<16} flood {flood:>10,.0f} ha   "
              f"cropland {crop:>9,.0f} ha   imaged {imaged / 1e6:.2f} M ha"
              f"{note}")

        rows.append(dict(label=label, orbit=orbit, path=path,
                         flood_ha=flood, crop_ha=crop, imaged_ha=imaged))

    # boundaries
    gj_path = require(cfg.RESULTS / "district_flood_stats.geojson")
    with rasterio.open(paths[0]) as s:
        crs = s.crs
    gj = json.load(open(gj_path, encoding="utf-8"))
    dist = [shape(transform_geom("EPSG:4326", str(crs), f["geometry"]))
            for f in gj["features"] if f.get("geometry")]

    ind_path = require(cfg.DATA / "boundaries" / "india_adm2.geojson")
    full = json.load(open(ind_path, encoding="utf-8"))
    india = unary_union([
        shape(f["geometry"]).buffer(0).simplify(0.05, preserve_topology=True)
        for f in full["features"] if f.get("geometry")])

    print("\ndrawing three-date figure ...")
    fig = figure_three_dates(rows, dist, india, args.dec, args.variant)
    for ext in ("png", "pdf"):
        out = FIGS / f"flood_three_dates.{ext}"
        fig.savefig(out, dpi=300, facecolor="white", bbox_inches="tight")
        print(f"  wrote {out.relative_to(cfg.PROJECT)}")
    plt.close(fig)

    print("\ncounting change classes at full resolution ...")
    pa, pb = rows[0]["path"], rows[2]["path"]
    counts = change_counts(pa, pb)
    for name, code in (("drained", CH_DRAINED), ("still flooded", CH_PERSIST),
                       ("newly flooded", CH_NEW), ("permanent", CH_PERM),
                       ("dry throughout", CH_DRY), ("no data", CH_NODATA)):
        print(f"  {name:<16} {counts[code] * PX_HA:>12,.0f} ha")

    meta = dict(crop_a=rows[0]["crop_ha"], crop_b=rows[2]["crop_ha"],
                variant_text=VARIANT_TEXT[args.variant])

    print("\ndrawing recession figure ...")
    fig = figure_recession(pa, pb, counts, dist, max(3, args.dec - 2), meta,
                           do_crop=not args.no_crop)
    for ext in ("png", "pdf"):
        out = FIGS / f"flood_recession.{ext}"
        fig.savefig(out, dpi=300, facecolor="white", bbox_inches="tight")
        print(f"  wrote {out.relative_to(cfg.PROJECT)}")
    plt.close(fig)

    print("\ndone.")


if __name__ == "__main__":
    main()
