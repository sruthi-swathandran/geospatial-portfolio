"""
RS-01 / phase 6 - publication map.

Cartographic requirements met here: projected CRS stated on the sheet, a
colour-blind-safe class palette ordered light to dark, a graticule with degree
ticks, a scale bar drawn in projected metres, a north arrow (grid north; UTM
convergence stays under about 1.2 degrees across this sheet), an inset locator,
a full source and method block, and an area table that carries the
operating-point range rather than a single figure.

The range in that table is NOT a confidence interval. It spans the two
thresholds described in CHANGELOG.md C-10. A design-based area estimate with a
standard error would need a probability sample of the mapped area that has not
been drawn; see REVIEW.md F-02.

Outputs:
    results/figures/flood_extent_map.png    300 dpi
    results/figures/flood_extent_map.pdf    300 dpi, vector text

Usage:
    python src\\make_map.py
"""
from __future__ import annotations
import csv, json, datetime as dt
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import transform_geom, transform as warp_transform
from shapely.geometry import shape, box as sbox
from shapely.ops import unary_union
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Rectangle, Polygon as MplPoly
import matplotlib.gridspec as gridspec

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS, TARGET_CRS, pixel_ha   # noqa: E402

RES = 20.0
FS = RESULTS / "fullscene"
MAIN = FS / f"{EVENT}_water_{RES:g}m_refined.tif"
ALT = FS / f"{EVENT}_water_{RES:g}m_areamatched_refined.tif"
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)
CRS_TXT = f"{TARGET_CRS} (UTM zone 46N)"
PX_HA = pixel_ha(RES)
DEC = 5

# colour-blind safe, perceptually ordered light -> dark for the water classes
C_LAND, C_FLOOD, C_PERM, C_NODATA = "#EDEAE3", "#5BA3D0", "#123B63", "#FFFFFF"

def counts(path):
    c = np.zeros(256, np.int64)
    with rasterio.open(path) as s:
        for i in range(0, s.height, 2048):
            for j in range(0, s.width, 2048):
                w = rasterio.windows.Window(j, i, min(2048, s.width - j),
                                            min(2048, s.height - i))
                c += np.bincount(s.read(1, window=w).ravel(), minlength=256)
    return c

cm, ca = counts(MAIN), counts(ALT)
with rasterio.open(MAIN) as s:
    H, W, tr, crs = s.height, s.width, s.transform, s.crs
    img = s.read(1, out_shape=(H // DEC, W // DEC))
    left, bottom, right, top = s.bounds

def crop_ha(path):
    tot = 0.0
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            tot += float(r["flooded_cropland_ha"])
    return tot

crop_m = crop_ha(RESULTS / "district_flood_stats.csv")
crop_a = crop_ha(RESULTS / "district_flood_stats_areamatched.csv")

# ---------------------------------------------------------------- districts
gj = json.load(open(RESULTS / "district_flood_stats.geojson", encoding="utf-8"))
dist = [shape(transform_geom("EPSG:4326", str(crs), f["geometry"]))
        for f in gj["features"] if f.get("geometry")]

full = json.load(open(DATA / "boundaries" / "india_adm2.geojson", encoding="utf-8"))
india = unary_union([shape(f["geometry"]).buffer(0).simplify(0.05, preserve_topology=True)
                     for f in full["features"] if f.get("geometry")])

# ------------------------------------------------------------------ figure
fig = plt.figure(figsize=(13.5, 15.5), facecolor="white")
gs = gridspec.GridSpec(2, 2, width_ratios=[1.28, 1], height_ratios=[1, 0.001],
                       wspace=0.06, hspace=0.02,
                       left=0.055, right=0.975, top=0.925, bottom=0.045)
ax = fig.add_subplot(gs[:, 0])
ax.set_facecolor("white")

cmap = ListedColormap([C_NODATA, C_LAND, C_FLOOD, C_PERM])
disp = np.full(img.shape, 0, np.uint8)
disp[img == 0] = 1; disp[img == 1] = 2; disp[img == 2] = 3
ax.imshow(disp, cmap=cmap, norm=BoundaryNorm([0, 1, 2, 3, 4], 4),
          extent=(left, right, bottom, top), interpolation="nearest",
          origin="upper")

for g in dist:
    for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
        x, y = poly.exterior.xy
        ax.plot(x, y, color="#6B7B85", linewidth=0.45, alpha=0.85, zorder=3)

# graticule in degrees, drawn in the projected frame
lons = np.arange(92.0, 94.51, 0.5); lats = np.arange(25.0, 28.51, 0.5)
for lo in lons:
    la = np.linspace(24.6, 28.5, 60)
    xs, ys = warp_transform("EPSG:4326", str(crs), [lo] * 60, la)
    ax.plot(xs, ys, color="#9AA7AF", lw=0.4, ls=(0, (2, 3)), zorder=2)
for la in lats:
    lo = np.linspace(91.9, 94.4, 60)
    xs, ys = warp_transform("EPSG:4326", str(crs), lo, [la] * 60)
    ax.plot(xs, ys, color="#9AA7AF", lw=0.4, ls=(0, (2, 3)), zorder=2)
xt, _ = warp_transform("EPSG:4326", str(crs), list(lons), [26.5] * len(lons))
_, yt = warp_transform("EPSG:4326", str(crs), [93.0] * len(lats), list(lats))
ax.set_xticks(xt); ax.set_xticklabels([f"{v:g}°E" for v in lons], fontsize=8)
ax.set_yticks(yt); ax.set_yticklabels([f"{v:g}°N" for v in lats], fontsize=8)
ax.set_xlim(left, right); ax.set_ylim(bottom, top)
for sp in ax.spines.values():
    sp.set_edgecolor("#2A3439"); sp.set_linewidth(0.8)
ax.tick_params(length=3, color="#2A3439")

# scale bar, in projected metres so it is true at map scale
bx, by, L = left + 12000, bottom + 26000, 50000
ax.add_patch(Rectangle((bx, by), L, 3500, fc="#2A3439", ec="none", zorder=5))
ax.add_patch(Rectangle((bx, by), L / 2, 3500, fc="white", ec="#2A3439",
                       lw=0.7, zorder=6))
for frac, lab in ((0, "0"), (0.5, "25"), (1, "50 km")):
    ax.text(bx + L * frac, by + 6500, lab, fontsize=7.5, ha="center",
            color="#2A3439", zorder=6)

# north arrow (grid north; UTM convergence is under 1.2 deg across this sheet)
nx, ny = right - 26000, top - 40000
ax.annotate("", xy=(nx, ny), xytext=(nx, ny - 26000),
            arrowprops=dict(arrowstyle="-|>", color="#2A3439", lw=1.3), zorder=6)
ax.text(nx, ny + 5000, "N", fontsize=11, ha="center", color="#2A3439",
        fontweight="bold", zorder=6)

ax.set_title("Flood extent, 12 August 2016", fontsize=13, fontweight="bold",
             color="#16222B", pad=8, loc="left")

# ------------------------------------------------------------------- panel
rax = fig.add_subplot(gs[:, 1]); rax.axis("off")
rax.set_xlim(0, 1); rax.set_ylim(0, 1)
y = 0.985

def line(t, size=9, weight="normal", color="#16222B", dy=0.0175, x=0.0,
         family=None, style="normal"):
    global y
    rax.text(x, y, t, fontsize=size, fontweight=weight, color=color,
             va="top", ha="left", transform=rax.transAxes, family=family,
             style=style)
    y -= dy

line("LEGEND", 9, "bold", "#5C6B76", 0.026)
for c, lab, n in ((C_PERM, "Permanent water", "JRC occurrence ≥ 50%"),
                  (C_FLOOD, "Flood water", "dark on 12 Aug, not permanent"),
                  (C_LAND, "Land, imaged", ""),
                  (C_NODATA, "No data", "outside swath, or edge buffer")):
    rax.add_patch(Rectangle((0.0, y - 0.014), 0.045, 0.016, fc=c,
                            ec="#6B7B85", lw=0.5, transform=rax.transAxes))
    rax.text(0.062, y - 0.001, lab, fontsize=9.5, va="top",
             transform=rax.transAxes, color="#16222B")
    if n:
        rax.text(0.062, y - 0.0175, n, fontsize=7.8, va="top", style="italic",
                 transform=rax.transAxes, color="#5C6B76")
        y -= 0.0165
    y -= 0.024

y -= 0.012
line("AREA BY CLASS", 9, "bold", "#5C6B76", 0.024)
rax.text(0.0, y, "class", fontsize=8, color="#5C6B76", va="top",
         transform=rax.transAxes)
rax.text(0.60, y, "hectares", fontsize=8, color="#5C6B76", va="top",
         ha="right", transform=rax.transAxes)
rax.text(1.0, y, "operating-point range", fontsize=8, color="#5C6B76",
         va="top", ha="right", transform=rax.transAxes)
y -= 0.02
rax.plot([0, 1], [y + 0.006, y + 0.006], color="#C9D2D8", lw=0.7,
         transform=rax.transAxes, clip_on=False)
y -= 0.006

rows = [
    ("Flood water", cm[1] * PX_HA, ca[1] * PX_HA, C_FLOOD),
    ("Flooded cropland", crop_m, crop_a, "#8A6A2F"),
    ("Permanent water", cm[2] * PX_HA, ca[2] * PX_HA, C_PERM),
    ("Land, imaged", cm[0] * PX_HA, ca[0] * PX_HA, "#5C6B76"),
    ("No data", cm[255] * PX_HA, ca[255] * PX_HA, "#5C6B76"),
]
for lab, a, b, col in rows:
    lo, hi = sorted((a, b))
    rax.text(0.0, y, lab, fontsize=9.5, va="top", color="#16222B",
             transform=rax.transAxes)
    rax.text(0.60, y, f"{lo:,.0f}", fontsize=9.5, va="top", ha="right",
             color=col, transform=rax.transAxes,
             fontweight="bold" if lab.startswith(("Flood", "Flooded")) else "normal")
    rng = "—" if hi - lo < 1 else f"{lo:,.0f} to {hi:,.0f}"
    rax.text(1.0, y, rng, fontsize=8.6, va="top", ha="right", color="#5C6B76",
             transform=rax.transAxes)
    y -= 0.0235

y -= 0.004
rax.text(0.0, y, "Range spans two defensible thresholds: −18.75 dB, maximum\n"
                 "agreement with hand labels, and −17.75 dB, mapped area\n"
                 "unbiased against them. Not a confidence interval.",
         fontsize=7.8, va="top", color="#5C6B76", transform=rax.transAxes)
y -= 0.060

# ------------------------------------------------------------------- inset
iax = fig.add_axes([0.655, 0.315, 0.285, 0.200])
iax.set_facecolor("#F7F9FA")
for poly in (india.geoms if india.geom_type == "MultiPolygon" else [india]):
    if poly.area < 0.5:
        continue
    iax.add_patch(MplPoly(np.array(poly.exterior.coords), closed=True,
                          fc="#E3E8EB", ec="#9AA7AF", lw=0.4))
iax.add_patch(Rectangle((92.1507, 24.8471), 2.0127, 3.4377, fc="none",
                        ec="#B3452F", lw=1.6, zorder=5))
iax.set_xlim(67, 98); iax.set_ylim(6, 37)
iax.set_aspect(1 / np.cos(np.deg2rad(22)))
iax.set_xticks([]); iax.set_yticks([])
for sp in iax.spines.values():
    sp.set_edgecolor("#9AA7AF"); sp.set_linewidth(0.6)
iax.set_title("Study area within India", fontsize=8, color="#5C6B76", pad=3)

# ---------------------------------------------------------------- metadata
mx, my = 0.655, 0.292
meta = [
    ("PROJECTION", CRS_TXT + ", 20 m pixel"),
    ("SENSOR", "Sentinel-1A IW GRD, RTC gamma0, VH polarisation"),
    ("ACQUISITION", "12 August 2016, 23:46 UTC, relative orbit 77, descending"),
    ("METHOD", "Lee 5×5 speckle filter in linear power, single-date\n"
               "threshold, 600 m swath-edge buffer to no data, slope > 8°\n"
               "reclassified as land, minimum mapping unit 0.4 ha"),
    ("PERMANENT WATER", "JRC Global Surface Water occurrence ≥ 50%\n"
                        "(Pekel et al. 2016)"),
    ("CROPLAND", "ESA WorldCover 2021 class 40. Four to five years after\n"
                 "the event; no open 10 m cropland map exists for 2016"),
    ("BOUNDARIES", "geoBoundaries ADM2 India, current vintage, CC BY 4.0.\n"
                   "Assam districts have been created since 2016"),
    ("VALIDATION", "Sen1Floods11 hand labels, 65 chips, IoU 0.519\n"
                   "(95% CI 0.395–0.609). The refinement steps above are\n"
                   "unvalidated: no labelled data covers them"),
    ("PRODUCED", dt.date.today().strftime("%d %B %Y") +
                 " · github.com/sruthi-swathandran/geospatial-portfolio"),
]
for k, v in meta:
    fig.text(mx, my, k, fontsize=7.2, fontweight="bold", color="#5C6B76",
             va="top", ha="left")
    fig.text(mx + 0.098, my, v, fontsize=7.6, color="#16222B", va="top",
             ha="left", linespacing=1.45)
    my -= 0.0158 + 0.0122 * v.count("\n")

fig.suptitle("Brahmaputra valley flood extent and flooded cropland",
             fontsize=17, fontweight="bold", color="#16222B",
             x=0.055, y=0.972, ha="left")
fig.text(0.055, 0.945, "Sentinel-1 SAR, 12 August 2016 · monsoon season, "
                       "Kharif 2016 · central Brahmaputra valley, "
                       "Assam and adjoining states",
         fontsize=10.5, color="#5C6B76", ha="left")
fig.text(0.055, 0.018, "Contains modified Copernicus Sentinel data 2016, "
                       "processed by Microsoft Planetary Computer. "
                       "Land cover © ESA WorldCover 2021. "
                       "Surface water: JRC/Google. Boundaries: geoBoundaries.",
         fontsize=7.2, color="#8A97A0", ha="left")

for ext, dpi in (("png", 300), ("pdf", 300)):
    fig.savefig(FIGURES / f"flood_extent_map.{ext}", dpi=dpi,
                facecolor="white", bbox_inches="tight")
print("wrote flood_extent_map.png and .pdf")
print(f"flood {cm[1]*PX_HA:,.0f} / {ca[1]*PX_HA:,.0f} ha")
print(f"crop  {crop_m:,.0f} / {crop_a:,.0f} ha")
print(f"perm  {cm[2]*PX_HA:,.0f} / {ca[2]*PX_HA:,.0f} ha")
