"""
RS-01 / provenance - the reported area across every refinement choice.

Review finding F-04. Three parameters decide roughly 45% of the subtraction
between the raw threshold output and the reported flood area:

    slope cut          8 degrees
    permanent water    JRC occurrence >= 50%
    swath edge buffer  30 pixels, 600 m at 20 m

None of them can be validated. The Sen1Floods11 labels cover 65 floodplain
chips and none of these three situations occurs in them, so there is no held-out
data to choose against. Each was justified by a measurement on the scene itself,
which is a defensible way to choose and is not the same thing as validation.

Publishing one number chosen with three unvalidated parameters, and not showing
what the other choices give, is the practice this project criticises everywhere
else. This script prints the whole surface.

HOW IT AVOIDS 300 FULL RE-RUNS
------------------------------
Every combination is a different subset of the same water pixels. So bin each
water pixel once by (slope class, occurrence class, distance-from-edge class)
and accumulate counts. Any combination of cuts is then a sum over that
histogram. One pass over the scene answers the whole grid.

WHAT IT CANNOT COVER
--------------------
The minimum mapping unit is spatial, not per-pixel, so it cannot live in a
histogram. It is excluded here. At the published settings it removed 3,052 ha,
about 2.5% of what survived the other two, and it is roughly independent of
them. Figures below are therefore about 3,000 ha higher than the published
number at the equivalent settings.

Outputs:
    data/gsw_scene/India_gsw_<res>m_<ty>_<tx>.tif   cached
    results/sensitivity_grid.csv
    results/figures/sensitivity_grid.png

Usage:
    python src\\sensitivity_grid.py --res 20
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import odc.geo.xr                           # noqa: F401,E402
import planetary_computer                   # noqa: E402
import pystac_client                        # noqa: E402
import rasterio                             # noqa: E402
import rioxarray                            # noqa: F401,E402
from odc.stac import load as odc_load       # noqa: E402
from rasterio.windows import Window         # noqa: E402
from scipy.ndimage import binary_erosion    # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                        # noqa: E402
    EVENT, BBOX, DATA, RESULTS, MPC_STAC, DEM_COLLECTION, GSW_COLLECTION,
    TILE_PX, TILE_HALO_PX, RESAMPLING, SLOPE_MAX_DEG, GSW_PERMANENT_MIN,
    EDGE_BUFFER_PX, pixel_ha,
)
from refine_scene import slope_degrees, dem_tile            # noqa: E402

OUT_DIR = RESULTS / "fullscene"
GSW_DIR = DATA / "gsw_scene"
GSW_DIR.mkdir(parents=True, exist_ok=True)
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255

SLOPE_CUTS = [2.0, 5.0, 8.0, 12.0, 20.0, 90.0]      # "keep slope <= cut"
OCC_CUTS = [10, 25, 50, 70, 80, 101]                # "permanent if occ >= cut"
EDGE_CUTS = [0, 10, 20, 30, 45, 65]                 # pixels of buffer


def gsw_tile(items, gbox, key, res):
    cache = GSW_DIR / f"{EVENT}_gsw_{res:g}m_{key[0]}_{key[1]}.tif"
    if cache.exists():
        with rasterio.open(cache) as s:
            return s.read(1)
    ds = odc_load(items, bands=["occurrence"], like=gbox, chunks={},
                  resampling=RESAMPLING["occurrence"])
    da = ds["occurrence"]
    if "time" in da.dims:
        da = da.isel(time=0)
    occ = np.asarray(da.compute()).astype("float32")
    if occ.ndim == 3:
        occ = occ[0]
    occ[occ > 100] = 0.0        # no observation is not permanent water
    occ = np.nan_to_num(occ, nan=0.0).astype("uint8")
    prof = dict(driver="GTiff", height=occ.shape[0], width=occ.shape[1],
                count=1, dtype="uint8", crs=gbox.crs,
                transform=gbox.transform, compress="deflate")
    with rasterio.open(cache, "w", **prof) as dst:
        dst.write(occ, 1)
    return occ


def edge_cores(src_tif, cuts, factor=8):
    """Nested masks, one per candidate buffer, on a decimated grid."""
    with rasterio.open(src_tif) as src:
        h, w = src.height, src.width
        small = src.read(1, out_shape=(h // factor, w // factor)) != NODATA
    cores = []
    for b in cuts:
        if b <= 0:
            cores.append(small)
        else:
            it = max(1, round(b / factor))
            cores.append(binary_erosion(small, np.ones((3, 3), bool),
                                        iterations=it, border_value=0))
    return cores, factor


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--variant", default="")
    args = ap.parse_args()

    res = args.res
    px_ha = pixel_ha(res)
    tag = f"{res:g}m" + (f"_{args.variant}" if args.variant else "")
    src_tif = OUT_DIR / f"{EVENT}_water_{tag}.tif"
    if not src_tif.exists():
        raise SystemExit(f"{src_tif} not found. Run full_scene.py first.")
    print(f"reading {src_tif.name}\n")

    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    dem_items = list(client.search(collections=[DEM_COLLECTION],
                                   bbox=BBOX).items())
    gsw_items = list(client.search(collections=[GSW_COLLECTION],
                                   bbox=BBOX).items())
    if not dem_items or not gsw_items:
        raise SystemExit("DEM or GSW items not returned")

    full = rioxarray.open_rasterio(src_tif).odc.geobox
    with rasterio.open(src_tif) as src:
        h, w = src.height, src.width
    cores, cfac = edge_cores(src_tif, EDGE_CUTS)
    print(f"edge classes built for buffers {EDGE_CUTS} px "
          f"({[int(b*res) for b in EDGE_CUTS]} m)\n")

    ns, no, ne = len(SLOPE_CUTS), len(OCC_CUTS), len(EDGE_CUTS)
    H = np.zeros((ns, no, ne + 1), np.int64)     # water pixels
    A = np.zeros((ns, no, ne + 1), np.int64)     # all imaged pixels

    keys = [((ty, tx), y0, min(y0 + TILE_PX, h), x0, min(x0 + TILE_PX, w))
            for ty, y0 in enumerate(range(0, h, TILE_PX))
            for tx, x0 in enumerate(range(0, w, TILE_PX))]
    t0 = time.time()
    for n, (key, y0, y1, x0, x1) in enumerate(keys, 1):
        with rasterio.open(src_tif) as src:
            a = src.read(1, window=Window(x0, y0, x1 - x0, y1 - y0))
        valid = a != NODATA
        if not valid.any():
            print(f"\r  {n}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
                  end="", flush=True)
            continue

        py0, py1 = max(0, y0 - TILE_HALO_PX), min(h, y1 + TILE_HALO_PX)
        px0, px1 = max(0, x0 - TILE_HALO_PX), min(w, x1 + TILE_HALO_PX)
        oy, ox = y0 - py0, x0 - px0
        elev = dem_tile(dem_items, full[py0:py1, px0:px1], key, res)
        slope = slope_degrees(elev, res)[oy:oy + (y1 - y0), ox:ox + (x1 - x0)]
        occ = gsw_tile(gsw_items, full[y0:y1, x0:x1], key, res)

        s_idx = np.digitize(slope, SLOPE_CUTS)          # 0..ns
        np.clip(s_idx, 0, ns - 1, out=s_idx)
        o_idx = np.digitize(occ.astype("float32"), OCC_CUTS)
        np.clip(o_idx, 0, no - 1, out=o_idx)

        cy = np.minimum(np.arange(y0, y1) // cfac, cores[0].shape[0] - 1)
        cx = np.minimum(np.arange(x0, x1) // cfac, cores[0].shape[1] - 1)
        e_idx = np.zeros(a.shape, np.int8)
        for c in cores:
            e_idx += c[np.ix_(cy, cx)].astype(np.int8)

        water = valid & ((a == FLOOD) | (a == PERMANENT))
        flat = (s_idx * no + o_idx) * (ne + 1) + e_idx
        H += np.bincount(flat[water].ravel(),
                         minlength=ns * no * (ne + 1)).reshape(H.shape)
        A += np.bincount(flat[valid].ravel(),
                         minlength=ns * no * (ne + 1)).reshape(A.shape)
        print(f"\r  {n}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    def area(si, oi, ei) -> float:
        """Flood ha keeping slope<=SLOPE_CUTS[si], occ<OCC_CUTS[oi],
        and surviving buffer EDGE_CUTS[ei]."""
        return float(H[:si + 1, :oi + 1, ei + 1:].sum()) * px_ha

    si0 = SLOPE_CUTS.index(SLOPE_MAX_DEG)
    oi0 = OCC_CUTS.index(GSW_PERMANENT_MIN)
    ei0 = EDGE_CUTS.index(EDGE_BUFFER_PX)
    published = area(si0, oi0, ei0)

    print("\nFLOOD AREA (ha) ACROSS SLOPE AND PERMANENT-WATER CUTS")
    print(f"(swath edge buffer fixed at the published {EDGE_BUFFER_PX} px)")
    print("-" * 68)
    print(f"  {'slope <=':<10}" + "".join(f"{'occ<'+str(o):>10}"
                                          for o in OCC_CUTS))
    for i, sc in enumerate(SLOPE_CUTS):
        lab = "none" if sc >= 90 else f"{sc:g} deg"
        line = f"  {lab:<10}"
        for j in range(no):
            v = area(i, j, ei0)
            mark = "*" if (i == si0 and j == oi0) else " "
            line += f"{v:>9,.0f}{mark}"
        print(line)
    print(f"\n  * published settings, {published:,.0f} ha before the minimum "
          "mapping unit")
    print(f"    (the MMU then removes about 3,000 ha, giving the reported "
          "119,779 ha)")

    print("\nFLOOD AREA ACROSS THE SWATH EDGE BUFFER")
    print(f"(slope <= {SLOPE_MAX_DEG:g} deg, occurrence < {GSW_PERMANENT_MIN}%)")
    print("-" * 52)
    print(f"  {'buffer':<12}{'metres':>9}{'flood ha':>13}{'vs published':>15}")
    for k, b in enumerate(EDGE_CUTS):
        v = area(si0, oi0, k)
        print(f"  {str(b)+' px':<12}{int(b*res):>9}{v:>13,.0f}"
              f"{v/max(published,1)-1:>+14.1%}")

    lo = min(area(i, j, k) for i in range(ns) for j in range(no)
             for k in range(ne))
    hi = max(area(i, j, k) for i in range(ns) for j in range(no)
             for k in range(ne))
    print(f"\n  Across the whole grid the reported flood area ranges "
          f"{lo:,.0f} to {hi:,.0f} ha,")
    print(f"  a factor of {hi/max(lo,1):.1f}. The published choice sits at "
          f"{published:,.0f} ha.")
    print("  Every point on this surface is defensible from the imagery. The "
          "spread is\n  what an unvalidated parameter costs, and it is larger "
          "than any accuracy\n  difference measured anywhere else in this "
          "project.")

    with open(RESULTS / "sensitivity_grid.csv", "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["slope_max_deg", "occurrence_permanent_min",
                     "edge_buffer_px", "edge_buffer_m", "flood_ha",
                     "is_published"])
        for i, sc in enumerate(SLOPE_CUTS):
            for j, oc in enumerate(OCC_CUTS):
                for k, b in enumerate(EDGE_CUTS):
                    w_.writerow([sc, oc, b, int(b * res),
                                 round(area(i, j, k), 1),
                                 int(i == si0 and j == oi0 and k == ei0)])

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    grid = np.array([[area(i, j, ei0) for j in range(no)] for i in range(ns)])
    im = axes[0].imshow(grid / 1000.0, cmap="YlGnBu", aspect="auto")
    axes[0].set_xticks(range(no))
    axes[0].set_xticklabels([f"<{o}" for o in OCC_CUTS], fontsize=8)
    axes[0].set_yticks(range(ns))
    axes[0].set_yticklabels(["none" if s >= 90 else f"{s:g}"
                             for s in SLOPE_CUTS], fontsize=8)
    axes[0].set_xlabel("permanent water: JRC occurrence cut (%)")
    axes[0].set_ylabel("slope cut (degrees)")
    axes[0].scatter([oi0], [si0], marker="o", s=140, facecolor="none",
                    edgecolor="#b03030", linewidth=2)
    for i in range(ns):
        for j in range(no):
            axes[0].text(j, i, f"{grid[i, j]/1000:.0f}", ha="center",
                         va="center", fontsize=7,
                         color="white" if grid[i, j] > grid.max() * .6
                         else "#20303a")
    fig.colorbar(im, ax=axes[0], label="flood, thousand ha")
    axes[0].set_title("Published choice circled", fontsize=10)

    vals = [area(si0, oi0, k) for k in range(ne)]
    axes[1].plot([b * res for b in EDGE_CUTS], vals, marker="o",
                 color="#2b6f8f")
    axes[1].axvline(EDGE_BUFFER_PX * res, color="#b03030", linestyle="--",
                    label=f"published {int(EDGE_BUFFER_PX*res)} m")
    axes[1].set_xlabel("swath edge buffer (m)")
    axes[1].set_ylabel("flood (ha)")
    axes[1].grid(alpha=.25); axes[1].legend(fontsize=8)
    axes[1].set_title("Buffer alone", fontsize=10)
    fig.suptitle(f"{EVENT}: reported flood area across three unvalidated "
                 f"parameters (before MMU)")
    fig.tight_layout()
    fig.savefig(FIGURES / "sensitivity_grid.png", dpi=130)
    print("\nwrote sensitivity_grid.csv and figures/sensitivity_grid.png")


if __name__ == "__main__":
    main()
