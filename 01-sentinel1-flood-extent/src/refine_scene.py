"""
RS-01 / step 11b - take the terrain out of the full-scene map.

WHY THIS EXISTS
---------------
Step 10 swept slope cuts from 2 to 20 degrees on the 65 labelled chips and found
the mask worthless: precision moved +0.008 for recall -0.003, so it removed true
water about as fast as it removed shadow. That conclusion was correct about the
chips and wrong about the scene, because every one of those chips sits in the
Brahmaputra floodplain. There are no mountains in the validation set.

The full-scene map shows the consequence. The Arunachal foothills in the north
and the Meghalaya and Mizoram hills in the south are speckled with pixels called
flood. Radar shadow and layover are dark for geometric reasons: the slope faces
away from the sensor, or the return is compressed, and either way little energy
comes back. A darkness threshold cannot tell that from calm water.

This is the second time a conclusion from the chips has failed to transfer to
the scene. The first was Otsu, where "per-scene estimation" measured on a
floodplain scene turned into "Otsu over a 203 by 381 km rectangle including dry
upland" and returned a threshold 3.4 dB too permissive. Both failures have the
same shape: the validation set was selected around the flood, so it represents
the flood rather than the region.

WHAT THIS DOES
--------------
Post-processing only. The water map is already written, so nothing here touches
the radar archive again. For each tile it fetches the Copernicus DEM, computes
slope, and reports how much of the mapped flood sits on each slope class. Then,
with --apply, it writes a refined map where flood on steep ground becomes land
and specks below a minimum mapping unit are dropped.

Run it without --apply first. The slope distribution of the flood is the
evidence for whichever cut you pick, and it belongs in the README.

ON THE MINIMUM MAPPING UNIT
---------------------------
A lone 20 m pixel of flood is not a mappable flood, it is one noisy sample. Most
operational flood products drop connected components below a threshold, and
saying so with a number is better than leaving thousands of single pixels in a
product and calling it detail. Objects are removed per tile with a 16 pixel
halo, so a component straddling a tile edge is judged on what falls inside the
padded window rather than being cut in half.

Outputs:
    data/dem_scene/India_dem_<res>m_<ty>_<tx>.tif      cached DEM tiles
    results/fullscene/India_water_<res>m_refined.tif   with --apply
    results/refine_scene_<res>m.csv

Usage:
    python src\\refine_scene.py --res 20
    python src\\refine_scene.py --res 20 --apply --slope 8 --min-pixels 10
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
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
from odc.stac import load as odc_load       # noqa: E402
from rasterio.windows import Window         # noqa: E402
from scipy.ndimage import binary_erosion    # noqa: E402
from skimage.morphology import remove_small_objects   # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                        # noqa: E402
    EVENT, BBOX, DATA, RESULTS, MPC_STAC, DEM_COLLECTION,
    SLOPE_MAX_DEG, EDGE_BUFFER_PX, MIN_OBJECT_PX_SCENE,
    TILE_PX, TILE_HALO_PX, RESAMPLING, pixel_ha,
)

OUT_DIR = RESULTS / "fullscene"
DEM_DIR = DATA / "dem_scene"
DEM_DIR.mkdir(parents=True, exist_ok=True)

TILE = TILE_PX
HALO = TILE_HALO_PX
LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
SLOPE_CLASSES = (0, 2, 5, 8, 12, 20, 35, 90)


def slope_degrees(elev: np.ndarray, res: float) -> np.ndarray:
    """Slope from a projected grid, where pixel spacing is metres in both axes."""
    gy, gx = np.gradient(elev.astype("float64"), res, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")


def dem_tile(items, gbox, key, res, resampling=None) -> np.ndarray:
    # The resampling rule is part of the cache key. Without that, testing an
    # alternative would silently reuse tiles built with the default and report
    # no difference.
    resampling = resampling or RESAMPLING["dem"]
    suffix = "" if resampling == RESAMPLING["dem"] else f"_{resampling}"
    cache = DEM_DIR / f"{EVENT}_dem_{res:g}m{suffix}_{key[0]}_{key[1]}.tif"
    if cache.exists():
        with rasterio.open(cache) as src:
            return src.read(1).astype("float32")

    ds = odc_load(items, bands=["data"], like=gbox, chunks={},
                  resampling=resampling)
    da = ds["data"]
    if "time" in da.dims:
        da = da.isel(time=0)
    elev = np.asarray(da.compute()).astype("float32")
    if elev.ndim == 3:
        elev = elev[0]

    profile = dict(driver="GTiff", height=elev.shape[0], width=elev.shape[1],
                   count=1, dtype="float32", crs=gbox.crs,
                   transform=gbox.transform, compress="deflate")
    with rasterio.open(cache, "w", **profile) as dst:
        dst.write(elev, 1)
    return elev


def core_mask(src_tif, buffer_px, factor=8):
    """
    Everything further than buffer_px from the swath boundary.

    Measured on this scene: flood classification runs at about 17% of area
    inside the first 30 pixels of the frame edge and 1.9% beyond 45, because the
    return falls away at near and far range and residual border noise leaves
    those pixels dark enough to pass a water threshold. They are not dry and
    they are not wet, they are unmeasured, so the buffer becomes NO DATA rather
    than land.

    Eroded on a decimated copy. A 194 megapixel boolean erosion is minutes of
    work and hundreds of megabytes for a 600 m buffer whose edge does not need
    to be exact.
    """
    with rasterio.open(src_tif) as src:
        h, w = src.height, src.width
        small = src.read(1, out_shape=(h // factor, w // factor)) != NODATA
    it = max(1, round(buffer_px / factor))
    return binary_erosion(small, np.ones((3, 3), bool), iterations=it,
                          border_value=0), factor


def tile_core(core, factor, y0, y1, x0, x1):
    cy = np.minimum(np.arange(y0, y1) // factor, core.shape[0] - 1)
    cx = np.minimum(np.arange(x0, x1) // factor, core.shape[1] - 1)
    return core[np.ix_(cy, cx)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--apply", action="store_true",
                    help="write a refined raster; without it, only report")
    ap.add_argument("--slope", type=float, default=SLOPE_MAX_DEG,
                    help="flood on ground steeper than this becomes land")
    ap.add_argument("--min-pixels", type=int, default=MIN_OBJECT_PX_SCENE,
                    help="drop flood components smaller than this")
    ap.add_argument("--resample-dem", default=RESAMPLING["dem"],
                    help="resampling for the DEM load, which sets the slope "
                         "surface the mask acts on (REVIEW S-02)")
    ap.add_argument("--variant", default="",
                    help="suffix identifying which acquisition to refine; "
                         "must match the one used by full_scene.py")
    ap.add_argument("--edge-buffer", type=int, default=EDGE_BUFFER_PX,
                    help="pixels inward from the swath boundary to declare no "
                         "data; 0 disables it")
    args = ap.parse_args()

    res = args.res
    tag = f"{res:g}m" + (f"_{args.variant}" if args.variant else "")
    src_tif = OUT_DIR / f"{EVENT}_water_{tag}.tif"
    if not src_tif.exists():
        raise SystemExit(f"{src_tif} not found. Run full_scene.py first.")

    px_ha = pixel_ha(res)
    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    dem_items = list(client.search(collections=[DEM_COLLECTION],
                                   bbox=BBOX).items())
    if not dem_items:
        raise SystemExit(f"no {DEM_COLLECTION} items over the AOI")
    print(f"{DEM_COLLECTION}: {len(dem_items)} tile(s)")

    dst_tif = OUT_DIR / f"{EVENT}_water_{tag}_refined.tif"
    if args.apply:
        shutil.copyfile(src_tif, dst_tif)
        print(f"writing into {dst_tif.name}")

    with rasterio.open(src_tif) as src:
        h, w = src.height, src.width
        gbox = src.read(1, window=Window(0, 0, 1, 1))  # touch, keeps API simple
    import rioxarray                                    # noqa: E402
    full = rioxarray.open_rasterio(src_tif).odc.geobox

    keys = [((ty, tx), y0, min(y0 + TILE, h), x0, min(x0 + TILE, w))
            for ty, y0 in enumerate(range(0, h, TILE))
            for tx, x0 in enumerate(range(0, w, TILE))]
    print(f"{len(keys)} tiles at {res:g} m, {px_ha:.4f} ha per pixel\n")

    if args.resample_dem != RESAMPLING["dem"]:
        print(f"  RESAMPLING OVERRIDDEN: dem={args.resample_dem}\n")

    core = cfac = None
    if args.edge_buffer > 0:
        core, cfac = core_mask(src_tif, args.edge_buffer)
        print(f"swath edge buffer: {args.edge_buffer} px "
              f"({args.edge_buffer * res:.0f} m) becomes no data\n")
    edge_flood = edge_area = 0

    hist = np.zeros(len(SLOPE_CLASSES) - 1, dtype=np.int64)
    perm_hist = np.zeros(len(SLOPE_CLASSES) - 1, dtype=np.int64)
    removed_slope = removed_small = kept = 0
    t0 = time.time()

    for n, (key, y0, y1, x0, x1) in enumerate(keys, 1):
        with rasterio.open(src_tif) as src:
            a = src.read(1, window=Window(x0, y0, x1 - x0, y1 - y0))

        if core is not None:
            drop = (~tile_core(core, cfac, y0, y1, x0, x1)) & (a != NODATA)
            if drop.any():
                edge_flood += int((drop & (a == FLOOD)).sum())
                edge_area += int(drop.sum())
                a = a.copy()
                a[drop] = NODATA
                if args.apply:
                    with rasterio.open(dst_tif, "r+") as dst:
                        dst.write(a, 1, window=Window(x0, y0, x1 - x0, y1 - y0))

        if not np.any((a == FLOOD) | (a == PERMANENT)):
            print(f"\r  {n}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
                  end="", flush=True)
            continue

        py0, py1 = max(0, y0 - HALO), min(h, y1 + HALO)
        px0, px1 = max(0, x0 - HALO), min(w, x1 + HALO)
        oy, ox = y0 - py0, x0 - px0
        try:
            elev = dem_tile(dem_items, full[py0:py1, px0:px1], key, res,
                            args.resample_dem)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  tile {key}: DEM unavailable ({exc}), left unchanged")
            continue
        slope = slope_degrees(elev, res)[oy:oy + (y1 - y0), ox:ox + (x1 - x0)]

        flood = a == FLOOD
        idx = np.clip(np.digitize(slope, SLOPE_CLASSES) - 1, 0,
                      len(hist) - 1)
        hist += np.bincount(idx[flood], minlength=len(hist))
        perm_hist += np.bincount(idx[a == PERMANENT], minlength=len(perm_hist))

        steep = flood & (slope > args.slope)
        removed_slope += int(steep.sum())
        gentle = flood & ~steep
        if args.min_pixels > 1 and gentle.any():
            # scikit-image 0.26 deprecated min_size in favour of max_size, and
            # flipped the comparison: min_size=n dropped objects smaller than
            # n, max_size=m drops objects smaller than OR EQUAL TO m. So
            # max_size = min_pixels - 1 is exactly the old behaviour, which
            # keeps the published 3,052 ha unchanged while surviving 2.0.
            try:
                cleaned = remove_small_objects(gentle,
                                               max_size=args.min_pixels - 1)
            except TypeError:
                cleaned = remove_small_objects(gentle,
                                               min_size=args.min_pixels)
        else:
            cleaned = gentle
        removed_small += int(gentle.sum() - cleaned.sum())
        kept += int(cleaned.sum())

        if args.apply:
            out = a.copy()
            out[flood & ~cleaned] = LAND
            with rasterio.open(dst_tif, "r+") as dst:
                dst.write(out, 1, window=Window(x0, y0, x1 - x0, y1 - y0))

        print(f"\r  {n}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    total = hist.sum()
    print("\nWHERE DOES THE MAPPED FLOOD SIT ON THE TERRAIN?")
    print("-----------------------------------------------")
    print(f"  {'slope class':<16}{'flood ha':>12}{'share':>9}"
          f"{'permanent ha':>15}")
    for i in range(len(hist)):
        lo, hi = SLOPE_CLASSES[i], SLOPE_CLASSES[i + 1]
        print(f"  {f'{lo}-{hi} deg':<16}{hist[i]*px_ha:>12,.0f}"
              f"{hist[i]/max(total,1):>9.1%}{perm_hist[i]*px_ha:>15,.0f}")
    print(f"  {'all':<16}{total*px_ha:>12,.0f}")
    print("\n  Real flood water sits on flat ground. Permanent water is the "
          "control:\n  the river is genuinely flat, so its slope distribution "
          "shows what a\n  correct water class looks like. Flood spread across "
          "steep classes that\n  the river never occupies is shadow, not water.")

    print("\nWHAT THE PROPOSED REFINEMENT WOULD REMOVE")
    print("-----------------------------------------")
    if core is not None:
        print(f"  swath edge buffer        {edge_flood*px_ha:>12,.0f} ha of "
              f"flood, in {edge_area*px_ha:,.0f} ha now marked no data")
    print(f"  slope > {args.slope:g} deg          {removed_slope*px_ha:>12,.0f} ha  "
          f"({removed_slope/max(total,1):.1%} of mapped flood)")
    print(f"  components < {args.min_pixels} px      "
          f"{removed_small*px_ha:>12,.0f} ha  "
          f"({removed_small/max(total,1):.1%})")
    print(f"  kept as flood            {kept*px_ha:>12,.0f} ha  "
          f"({kept/max(total,1):.1%})")
    if not args.apply:
        print("\n  Nothing written. Re-run with --apply once you are happy with "
              "the cut.")

    with open(RESULTS / f"refine_scene_{tag}.csv", "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["slope_lo", "slope_hi", "flood_ha", "permanent_ha"])
        for i in range(len(hist)):
            w_.writerow([SLOPE_CLASSES[i], SLOPE_CLASSES[i + 1],
                         round(hist[i] * px_ha, 1),
                         round(perm_hist[i] * px_ha, 1)])
        w_.writerow([])
        w_.writerow(["slope_cut", args.slope, "removed_ha",
                     round(removed_slope * px_ha, 1)])
        w_.writerow(["min_pixels", args.min_pixels, "removed_ha",
                     round(removed_small * px_ha, 1)])
        w_.writerow(["kept_ha", round(kept * px_ha, 1)])

    if args.apply:
        stats_path = RESULTS / f"fullscene_stats_{tag}.json"
        if stats_path.exists():
            stats = json.loads(stats_path.read_text())
            stats["refined"] = {
                "slope_cut_deg": args.slope,
                "min_pixels": args.min_pixels,
                "flood_ha_before": round(total * px_ha, 1),
                "flood_ha_after": round(kept * px_ha, 1),
                "removed_steep_ha": round(removed_slope * px_ha, 1),
                "removed_small_ha": round(removed_small * px_ha, 1),
                "note": "the slope mask was neutral on the labelled chips "
                        "(precision +0.008, recall -0.003) because every chip "
                        "is in the floodplain; it is applied here for the "
                        "uplands the chips never sampled",
            }
            stats_path.write_text(json.dumps(stats, indent=2))

    fig, ax = plt.subplots(figsize=(8, 4.6))
    x = np.arange(len(hist))
    ax.bar(x - 0.2, hist * px_ha, width=0.4, label="mapped flood",
           color="#2b6f8f")
    ax.bar(x + 0.2, perm_hist * px_ha, width=0.4, label="permanent water",
           color="#8fb8cc")
    ax.axvline(np.searchsorted(SLOPE_CLASSES, args.slope) - 0.5,
               color="#b03030", linestyle="--", linewidth=1.2,
               label=f"proposed cut, {args.slope:g} deg")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{SLOPE_CLASSES[i]}-{SLOPE_CLASSES[i+1]}"
                        for i in range(len(hist))], fontsize=8)
    ax.set_xlabel("slope (degrees)"); ax.set_ylabel("hectares")
    ax.set_yscale("log")
    ax.set_title(f"{EVENT}: mapped flood against terrain, {res:g} m")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"flood_by_slope_{tag}.png", dpi=130)

    print(f"\nwrote refine_scene_{tag}.csv and flood_by_slope_{tag}.png")


if __name__ == "__main__":
    main()
