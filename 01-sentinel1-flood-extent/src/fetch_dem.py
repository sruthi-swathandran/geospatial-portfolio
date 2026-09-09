"""
RS-01 / step 8c + 10a — fetch the DEM, and test whether terrain explains the shifts.

Two jobs at once, deliberately. The Copernicus DEM is needed in phase 10 anyway,
to mask radar shadow and layover by slope. Fetching it now also lets us test the
one hypothesis about the registration offsets that is still standing.

Where the shift investigation stands:

  - The offsets are REAL. The seven chips that ran to the +/-10 boundary have
    post-alignment correlation of 0.974, higher than the interior median. A
    search chasing noise does not produce a peak that good. So those chips
    genuinely sit 10+ pixels — 100 m or more — from where the labels put them.

  - They are NOT spatially organised at chip scale. dx against longitude is
    -0.109 and against latitude +0.118. There is no smooth gradient across the
    scene, which rules out a simple frame-geometry explanation.

  - Terrain remains the candidate, and the absence of a linear gradient does not
    count against it: terrain is not a linear function of latitude. A chip in
    the hills can sit beside a chip on the floodplain. The right test is against
    ELEVATION and SLOPE, not against coordinates.

The physics, which makes this a prediction rather than a fishing expedition: a
height error h displaces a SAR pixel in slant range by roughly h / tan(theta).
At Sentinel-1's ~35 degree incidence that is about 1.4 x h. So a 70 m
disagreement between SRTM (which GEE used) and the Copernicus DEM (which RTC
uses) would displace a pixel by about 100 m — 10 pixels — in range, which for
this descending pass is close to east-west. That is exactly the size and the
axis we are seeing.

If |dx| tracks elevation or slope, the cause is identified. If it does not, we
say so and move on with the correction applied but unexplained.

Outputs:
    data/dem/India_<chip>_DEM.tif       reused in phase 10 for slope masking
    results/terrain_vs_shift.csv
    results/figures/terrain_vs_shift.png

Usage:
    python src\\fetch_dem.py --limit 3     # smoke test
    python src\\fetch_dem.py
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import odc.geo.xr        # noqa: F401
import planetary_computer
import pystac_client
import rasterio
import rioxarray         # noqa: F401
from odc.stac import load as odc_load

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                   # noqa: E402
    EVENT, LABELS_DIR, RESULTS, DATA, MPC_STAC, DEM_COLLECTION, BBOX,
)
from chips import chip_ids                             # noqa: E402

DEM_DIR = DATA / "dem"
DEM_DIR.mkdir(parents=True, exist_ok=True)
COREG = RESULTS / "coregistration.csv"


def chip_geobox(chip_id: str):
    path = LABELS_DIR / "S1Hand" / f"{EVENT}_{chip_id}_S1Hand.tif"
    return rioxarray.open_rasterio(path).odc.geobox


def slope_degrees(elev: np.ndarray, lat: float, deg_per_px: float) -> np.ndarray:
    """
    Slope in degrees from an elevation grid on a geographic (degree) grid.

    A degree of latitude is about 110.54 km everywhere; a degree of longitude
    shrinks with the cosine of latitude. Ignoring that would overstate east-west
    gradients by about 12% at 26 N — small, but free to get right.
    """
    dy_m = deg_per_px * 110_540.0
    dx_m = deg_per_px * 111_320.0 * np.cos(np.deg2rad(lat))
    gy, gx = np.gradient(elev, dy_m, dx_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    ids = chip_ids()
    if args.limit:
        ids = ids[:args.limit]

    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    items = list(client.search(collections=[DEM_COLLECTION], bbox=BBOX).items())
    print(f"{DEM_COLLECTION}: {len(items)} tile(s) over the AOI")
    if not items:
        raise SystemExit("No DEM items returned — check the collection id in config.py")

    rows, t0 = [], time.time()
    for n, chip_id in enumerate(ids, 1):
        gbox = chip_geobox(chip_id)
        ds = odc_load(items, bands=["data"], like=gbox, chunks={})
        da = ds["data"]
        if "time" in da.dims:
            da = da.isel(time=0)
        elev = np.asarray(da.compute()).astype("float64")
        if elev.ndim == 3:
            elev = elev[0]

        out = DEM_DIR / f"{EVENT}_{chip_id}_DEM.tif"
        profile = dict(driver="GTiff", height=elev.shape[0], width=elev.shape[1],
                       count=1, dtype="float32", crs=gbox.crs,
                       transform=gbox.transform, compress="deflate")
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(elev.astype("float32"), 1)

        lat = float(gbox.extent.boundingbox.range_y[0])
        deg_per_px = abs(gbox.resolution.y)
        slope = slope_degrees(elev, lat, deg_per_px)

        rows.append({
            "chip_id": chip_id,
            "elev_mean": round(float(np.nanmean(elev)), 1),
            "elev_sd": round(float(np.nanstd(elev)), 1),
            "elev_range": round(float(np.nanmax(elev) - np.nanmin(elev)), 1),
            "slope_mean": round(float(np.nanmean(slope)), 2),
            "slope_p95": round(float(np.nanpercentile(slope, 95)), 2),
        })
        print(f"\r  {n}/{len(ids)} chips  ({time.time()-t0:.0f}s)", end="", flush=True)
    print()

    # join with the co-registration result
    shifts = {}
    if COREG.exists():
        for r in csv.DictReader(COREG.read_text().splitlines()):
            shifts[r["chip_id"]] = r

    for r in rows:
        s = shifts.get(r["chip_id"])
        if s:
            r["dy"] = int(s["dy"]); r["dx"] = int(s["dx"])
            r["abs_dx"] = abs(int(s["dx"]))
            r["corr_after"] = s["corr_after"]

    with open(RESULTS / "terrain_vs_shift.csv", "w", newline="") as fh:
        fields = sorted({k for r in rows for k in r},
                        key=lambda k: (k != "chip_id", k))
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("\nTERRAIN")
    print("-------")
    for key in ("elev_mean", "elev_range", "slope_mean", "slope_p95"):
        a = np.array([r[key] for r in rows], dtype=float)
        print(f"  {key:<12} median {np.median(a):8.2f}   min {a.min():8.2f}   "
              f"max {a.max():8.2f}")

    have = [r for r in rows if "abs_dx" in r]
    if len(have) > 5:
        adx = np.array([r["abs_dx"] for r in have], dtype=float)
        ady = np.array([abs(r["dy"]) for r in have], dtype=float)
        print("\nDOES TERRAIN EXPLAIN THE SHIFTS?")
        print("--------------------------------")
        print(f"  (n={len(have)} chips with both a DEM and a shift)")
        for key in ("elev_mean", "elev_range", "slope_mean", "slope_p95"):
            a = np.array([r[key] for r in have], dtype=float)
            print(f"  corr(|dx|, {key:<11}) = {np.corrcoef(adx, a)[0,1]:+.3f}"
                  f"      corr(|dy|, {key:<11}) = {np.corrcoef(ady, a)[0,1]:+.3f}")

        big = [r for r in have if r["abs_dx"] >= 8]
        small = [r for r in have if r["abs_dx"] <= 2]
        if big and small:
            print(f"\n  chips shifted 8+ px (n={len(big)}):  "
                  f"median elevation {np.median([r['elev_mean'] for r in big]):7.1f} m, "
                  f"median slope {np.median([r['slope_mean'] for r in big]):5.2f} deg")
            print(f"  chips shifted 0-2 px (n={len(small)}): "
                  f"median elevation {np.median([r['elev_mean'] for r in small]):7.1f} m, "
                  f"median slope {np.median([r['slope_mean'] for r in small]):5.2f} deg")
            print("\n  A large-shift group that is clearly higher or steeper is the"
                  "\n  identification. Similar terrain in both groups means terrain "
                  "is not it,\n  and the correction stays empirical — which is still "
                  "a correct result,\n  just a less satisfying sentence.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                            # noqa: BLE001
        print(f"\n(figure skipped: {exc})")
        return

    if len(have) > 5:
        fig, axes = plt.subplots(1, 2, figsize=(12.5, 5))
        for ax, key, xlabel in ((axes[0], "elev_mean", "chip mean elevation (m)"),
                                (axes[1], "slope_mean", "chip mean slope (degrees)")):
            x = np.array([r[key] for r in have], dtype=float)
            y = np.array([r["abs_dx"] for r in have], dtype=float)
            ax.scatter(x, y, s=55, color="#2b6f8f", edgecolor="black",
                       linewidth=0.4)
            ax.set_xlabel(xlabel)
            ax.set_ylabel("|dx| correction (pixels)")
            ax.grid(alpha=0.25)
            ax.set_title(f"r = {np.corrcoef(x, y)[0,1]:+.3f}")
        fig.suptitle(f"{EVENT} — does terrain explain the registration offset?")
        fig.tight_layout()
        out = RESULTS / "figures" / "terrain_vs_shift.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=130)
        print(f"\nwrote figures/{out.name}")

    print("wrote terrain_vs_shift.csv and DEM chips to data/dem/")


if __name__ == "__main__":
    main()
