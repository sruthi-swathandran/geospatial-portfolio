"""
RS-01 / step 7 — pull the pre-event scene from STAC onto the chip grid.

This is where the cloud-native stack finally earns its place. We do NOT download
Sentinel-1 scenes. We ask a STAC API for two specific acquisitions, and read
only the 512x512 windows we need out of the Cloud-Optimised GeoTIFFs on the
other end — 68 small windows instead of ~4 GB of SAFE archives.

Two dates are fetched, and the first one is a test rather than a product:

  FLOOD DATE (2016-08-12)  We already have this imagery — it is what Sen1Floods11
                           packaged as S1Hand. Fetching it again from Planetary
                           Computer and correlating the two is an end-to-end check
                           on geolocation, resampling and units. If our RTC read
                           does not agree with the dataset's own chip, nothing
                           downstream can be trusted, and we find that out here
                           rather than after building a change detector on it.

  REFERENCE DATE (2016-07-19)  The pre-event acquisition, same relative orbit 77,
                           same overpass time, same VV+VH. This is the new
                           information: change against it is the standard answer
                           to both bright flooded vegetation and dark land that
                           merely looks like water.

Note on units: Planetary Computer's sentinel-1-rtc assets are terrain-corrected
gamma0 in LINEAR power. Sen1Floods11's chips are in dB. We convert ours to dB so
the two are comparable and so thresholds carry over.

Access: reading RTC pixels needs a signed URL. planetary-computer signs
anonymously, with rate limits. If you hit 401 or 429, get a free API key at
planetarycomputer.microsoft.com and set it once per terminal:

    set PC_SDK_SUBSCRIPTION_KEY=your-key-here

Outputs:
    data/reference/India_<chip>_REF.tif    2-band (VV, VH) dB, on the chip grid
    data/reference/India_<chip>_FLOODRTC.tif
    results/reference_fetch_report.csv

Usage:
    python src\\fetch_reference.py --limit 3      # smoke test first
    python src\\fetch_reference.py
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
import odc.geo.xr    # noqa: F401  (registers the .odc accessor used for geobox)
import planetary_computer
import pystac_client
import rasterio
import rioxarray     # noqa: F401  (registers the .rio accessor)
import xarray as xr
from odc.stac import load as odc_load

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                    # noqa: E402
    EVENT, LABELS_DIR, RESULTS, DATA, MPC_STAC, S1_COLLECTION,
    FLOOD_ITEMS, REFERENCE_ITEMS, FLOOD_DATE, REFERENCE_DATE,
)
from chips import read, chip_ids                        # noqa: E402

REF_DIR = DATA / "reference"
REF_DIR.mkdir(parents=True, exist_ok=True)


def open_catalog():
    return pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)


def get_items(client, ids: list[str]):
    """Fetch specific items by id, tolerating the _rtc suffix convention."""
    wanted = [i if i.endswith("_rtc") else f"{i}_rtc" for i in ids]
    found = list(client.search(collections=[S1_COLLECTION], ids=wanted).items())
    missing = set(wanted) - {i.id for i in found}
    if missing:
        print(f"  WARNING: {len(missing)} item(s) not returned: "
              f"{sorted(missing)[:2]}")
    return found


def chip_geobox(chip_id: str):
    """
    The exact grid of a Sen1Floods11 chip, as an odc GeoBox.

    Passing this to odc.stac.load as `like=` means the fetched imagery lands
    pixel-for-pixel on the chip's grid — same CRS, same transform, same shape —
    so it can be compared with the hand labels without a resampling step of our
    own, and without any chance of a half-pixel offset creeping in.
    """
    path = LABELS_DIR / "S1Hand" / f"{EVENT}_{chip_id}_S1Hand.tif"
    da = rioxarray.open_rasterio(path)
    return da.odc.geobox


def to_db(da: xr.DataArray) -> xr.DataArray:
    """RTC gamma0 arrives as linear power; Sen1Floods11 chips are in dB."""
    return 10.0 * np.log10(da.where(da > 0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-flood", action="store_true",
                    help="skip re-fetching the flood date (skips the sanity check)")
    args = ap.parse_args()

    ids = chip_ids()
    if args.limit:
        ids = ids[:args.limit]
    print(f"{len(ids)} chip(s) to fetch\n")

    client = open_catalog()
    print(f"reference {REFERENCE_DATE}:")
    ref_items = get_items(client, REFERENCE_ITEMS)
    print(f"  {len(ref_items)} item(s)")

    flood_items = []
    if not args.skip_flood:
        print(f"flood {FLOOD_DATE}:")
        flood_items = get_items(client, FLOOD_ITEMS)
        print(f"  {len(flood_items)} item(s)")

    rows = []
    t0 = time.time()

    for n, chip_id in enumerate(ids, 1):
        gbox = chip_geobox(chip_id)
        row = {"chip_id": chip_id}

        for label, items, suffix in (("REF", ref_items, "REF"),
                                     ("FLOODRTC", flood_items, "FLOODRTC")):
            if not items:
                continue
            ds = odc_load(items, bands=["vv", "vh"], like=gbox,
                          groupby="solar_day", chunks={})
            ds = ds.isel(time=0) if "time" in ds.dims else ds

            vv, vh = to_db(ds["vv"]).compute(), to_db(ds["vh"]).compute()
            stack = xr.concat([vv, vh], dim="band").astype("float32")
            stack = stack.assign_coords(band=[1, 2]).rio.write_crs(gbox.crs)
            out = REF_DIR / f"{EVENT}_{chip_id}_{suffix}.tif"
            stack.rio.to_raster(out)

            arr = stack.values
            row[f"{label}_vv_median"] = round(float(np.nanmedian(arr[0])), 2)
            row[f"{label}_vh_median"] = round(float(np.nanmedian(arr[1])), 2)
            row[f"{label}_nan_frac"] = round(float(np.mean(~np.isfinite(arr))), 4)

        # the sanity check: does our RTC read of the flood date agree with the
        # imagery Sen1Floods11 shipped for the same chip?
        if flood_items:
            with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC.tif") as src:
                ours = src.read()
            theirs = read("S1Hand", chip_id).astype("float64")
            m = np.isfinite(ours[1]) & np.isfinite(theirs[1])
            if m.sum() > 1000:
                row["vh_corr_vs_S1Hand"] = round(
                    float(np.corrcoef(ours[1][m], theirs[1][m])[0, 1]), 4)
                row["vh_bias_db"] = round(
                    float(np.median(ours[1][m] - theirs[1][m])), 2)

        rows.append(row)
        print(f"\r  {n}/{len(ids)} chips  ({time.time()-t0:.0f}s)", end="", flush=True)

    print()
    out_csv = RESULTS / "reference_fetch_report.csv"
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "chip_id", k))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    if any("vh_corr_vs_S1Hand" in r for r in rows):
        corr = np.array([r["vh_corr_vs_S1Hand"] for r in rows
                         if "vh_corr_vs_S1Hand" in r])
        bias = np.array([r["vh_bias_db"] for r in rows if "vh_bias_db" in r])
        print("\nSANITY CHECK — our RTC read vs the dataset's own chip (VH)")
        print(f"  correlation  median {np.median(corr):.3f}  "
              f"min {corr.min():.3f}  max {corr.max():.3f}")
        print(f"  bias (dB)    median {np.median(bias):+.2f}  "
              f"min {bias.min():+.2f}  max {bias.max():+.2f}")
        print("  A high correlation with a small constant bias means the grids "
              "line up and\n  only the processing chain differs (RTC vs the "
              "dataset's GRD). A low\n  correlation means misalignment — stop "
              "and fix that before going further.")

    ref_median = [r["REF_vh_median"] for r in rows if "REF_vh_median" in r]
    flood_median = [r["FLOODRTC_vh_median"] for r in rows if "FLOODRTC_vh_median" in r]
    if ref_median and flood_median:
        print(f"\n  median VH, reference {REFERENCE_DATE}: "
              f"{np.median(ref_median):+.2f} dB")
        print(f"  median VH, flood     {FLOOD_DATE}: "
              f"{np.median(flood_median):+.2f} dB")
        print("  A drop from reference to flood is the change signal we are "
              "about to exploit.")

    print(f"\nwrote {out_csv.name} and {len(rows)} chip file(s) to data/reference/")


if __name__ == "__main__":
    main()
