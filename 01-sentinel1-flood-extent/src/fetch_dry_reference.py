"""
RS-01 / step 9b - get a reference date that is actually dry.

Change detection scored 0.069 IoU against 0.515 for the single-date threshold.
That is not a marginal loss, it is a failure, and the cause is measured rather
than guessed: 45.1% of the pixels labelled water on 12 August were already below
the water threshold on 19 July. Nearly half the flood cannot produce a change
signal against that reference, because it was already there.

19 July is mid-monsoon in Assam. Choosing it was a reasonable trade at the time
(same orbit, same overpass time, dual polarisation, only 24 days before the
event) but the assumption behind it was wrong. The fix is a PRE-MONSOON
reference: February to mid-April, same relative orbit 77.

What that costs, stated up front so the comparison stays honest:

  Four to six months of seasonal change. Crops, soil moisture and vegetation
  structure all differ between March and August, so some of the measured
  "change" will be phenology rather than flooding. The July reference had the
  opposite problem: seasonally similar, but already wet.

  Neither reference is right in the abstract. Running both and reporting the
  difference in flooded area is the result. That sensitivity is the kind of
  number an insurance or relief client needs and almost never gets.

This script searches first and downloads nothing. Look at the candidates, pick a
date, then re-run with --fetch. The per-chip shift from co-registration is
applied on the way in, because the dry scene comes from the same orbit and the
same processing chain as the flood scene, so it inherits the same correction.

Outputs (with --fetch):
    data/reference/India_<chip>_REFDRY_ALIGNED.tif
    results/dry_reference.csv

Usage:
    python src\\fetch_dry_reference.py
    python src\\fetch_dry_reference.py --fetch 2016-03-15
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import odc.geo.xr        # noqa: F401
import planetary_computer
import pystac_client
import rasterio
import rioxarray         # noqa: F401
import xarray as xr
from odc.stac import load as odc_load

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                       # noqa: E402
    EVENT, LABELS_DIR, RESULTS, DATA, BBOX, MPC_STAC, S1_COLLECTION,
    RELATIVE_ORBIT, DRY_SEASON_SEARCH,
)
from chips import read                                     # noqa: E402

REF_DIR = DATA / "reference"
COREG = RESULTS / "coregistration.csv"


def open_catalog():
    return pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)


def search_candidates(client):
    items = list(client.search(
        collections=[S1_COLLECTION], bbox=BBOX,
        datetime=f"{DRY_SEASON_SEARCH[0]}/{DRY_SEASON_SEARCH[1]}").items())
    by_date = defaultdict(list)
    for it in items:
        p = it.properties
        by_date[it.datetime.date().isoformat()].append({
            "id": it.id,
            "rel_orbit": p.get("sat:relative_orbit"),
            "orbit_state": p.get("sat:orbit_state"),
            "pol": tuple(p.get("sar:polarizations") or []),
            "item": it,
        })
    return by_date


def shifts_by_chip() -> dict[str, tuple[int, int]]:
    if not COREG.exists():
        raise SystemExit("coregistration.csv not found. Run coregister.py first.")
    out = {}
    for r in csv.DictReader(COREG.read_text().splitlines()):
        out[r["chip_id"]] = (int(r["dy"]), int(r["dx"]))
    return out


def apply_shift(arr: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.full_like(arr, np.nan, dtype="float32")
    if dy == 0 and dx == 0:
        out[...] = arr
        return out
    src_y = slice(dy, None) if dy > 0 else slice(None, dy)
    dst_y = slice(None, -dy) if dy > 0 else slice(-dy, None)
    if dy == 0:
        src_y = dst_y = slice(None)
    src_x = slice(dx, None) if dx > 0 else slice(None, dx)
    dst_x = slice(None, -dx) if dx > 0 else slice(-dx, None)
    if dx == 0:
        src_x = dst_x = slice(None)
    out[..., dst_y, dst_x] = arr[..., src_y, src_x]
    return out


def chip_geobox(chip_id: str):
    return rioxarray.open_rasterio(
        LABELS_DIR / "S1Hand" / f"{EVENT}_{chip_id}_S1Hand.tif").odc.geobox


def to_db(da):
    return 10.0 * np.log10(da.where(da > 0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", default=None,
                    help="date (YYYY-MM-DD) from the candidate list to download")
    ap.add_argument("--water-threshold", type=float, default=-17.44,
                    help="RTC VH threshold used to report how wet each date is")
    args = ap.parse_args()

    client = open_catalog()
    print(f"searching {S1_COLLECTION} over the AOI, "
          f"{DRY_SEASON_SEARCH[0]} to {DRY_SEASON_SEARCH[1]}\n")
    by_date = search_candidates(client)

    print(f"{'date':<14}{'n':>4}  {'orbit':>6}  {'pass':<11}{'polarisations':<18}"
          f"{'usable'}")
    usable_dates = []
    for date in sorted(by_date):
        entries = by_date[date]
        rel = {e["rel_orbit"] for e in entries}
        state = {e["orbit_state"] for e in entries}
        pol = {e["pol"] for e in entries}
        match = [e for e in entries
                 if e["rel_orbit"] == RELATIVE_ORBIT and len(e["pol"]) == 2]
        if match:
            usable_dates.append((date, match))
        print(f"{date:<14}{len(entries):>4}  {str(sorted(rel)):>6}  "
              f"{str(sorted(state)):<11}{str(sorted(pol)):<18}"
              f"{'yes, ' + str(len(match)) + ' frames' if match else 'no'}")

    print(f"\n{len(usable_dates)} date(s) on relative orbit {RELATIVE_ORBIT} "
          "with dual polarisation.")
    if not usable_dates:
        raise SystemExit(
            "No dual-pol scene on this orbit in the dry window. Widen "
            "DRY_SEASON_SEARCH in config.py, or accept a VV-only reference and "
            "run the comparison on VV alone.")

    if not args.fetch:
        print("\nNothing downloaded. Re-run with --fetch YYYY-MM-DD using one of "
              "the dates marked usable.\nPrefer the LATEST usable date: closer to "
              "the event means less seasonal change\nto confound the comparison.")
        return

    picked = dict(usable_dates).get(args.fetch)
    if not picked:
        raise SystemExit(f"{args.fetch} is not in the usable list above.")
    items = [e["item"] for e in picked]
    print(f"\nfetching {len(items)} frame(s) from {args.fetch}")

    shifts = shifts_by_chip()
    chips = sorted(p.name.split("_")[1]
                   for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))
    rows, t0 = [], time.time()

    for n, chip_id in enumerate(chips, 1):
        gbox = chip_geobox(chip_id)
        ds = odc_load(items, bands=["vv", "vh"], like=gbox,
                      groupby="solar_day", chunks={})
        if "time" in ds.dims:
            ds = ds.isel(time=0)
        stack = xr.concat([to_db(ds["vv"]), to_db(ds["vh"])], dim="band")
        arr = np.asarray(stack.compute()).astype("float32")

        dy, dx = shifts.get(chip_id, (0, 0))
        arr = apply_shift(arr, dy, dx)

        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif") as src:
            profile = src.profile
        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_REFDRY_ALIGNED.tif",
                           "w", **profile) as dst:
            dst.write(arr)

        # the number that matters: how much of the labelled water was already
        # dark on this date, compared with the July reference
        label = read("LabelHand", chip_id)[0]
        w = (label == 1) & np.isfinite(arr[1])
        row = {"chip_id": chip_id, "dy": dy, "dx": dx,
               "dry_vh_median": round(float(np.nanmedian(arr[1])), 2)}
        if w.sum() > 500:
            row["water_already_dark_dry"] = round(
                float(np.mean(arr[1][w] <= args.water_threshold)), 4)
            jul_path = REF_DIR / f"{EVENT}_{chip_id}_REF_ALIGNED.tif"
            if jul_path.exists():
                with rasterio.open(jul_path) as src:
                    jul = src.read().astype("float64")
                m = w & np.isfinite(jul[1])
                if m.sum() > 500:
                    row["water_already_dark_july"] = round(
                        float(np.mean(jul[1][m] <= args.water_threshold)), 4)
        rows.append(row)
        print(f"\r  {n}/{len(chips)} chips  ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    fields = sorted({k for r in rows for k in r},
                    key=lambda k: (k != "chip_id", k))
    with open(RESULTS / "dry_reference.csv", "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=fields)
        w_.writeheader()
        w_.writerows(rows)

    dry = [r["water_already_dark_dry"] for r in rows
           if "water_already_dark_dry" in r]
    jul = [r["water_already_dark_july"] for r in rows
           if "water_already_dark_july" in r]
    if dry and jul:
        print("\nHOW MUCH OF THE FLOOD WAS ALREADY WET ON THE REFERENCE DATE?")
        print("------------------------------------------------------------")
        print(f"  19 July reference:      {np.median(jul):.1%} (median across chips)")
        print(f"  {args.fetch} reference: {np.median(dry):.1%}")
        print(f"  difference:             {np.median(jul) - np.median(dry):+.1%}")
        print("\n  A large drop means the dry reference gives change detection "
              "something to\n  work with. A small one means the flood plain is "
              "wet most of the year and\n  single-date thresholding is the right "
              "tool for this landscape, which is\n  also a finding.")

    print(f"\nwrote dry_reference.csv and {len(rows)} aligned dry-reference chips")
    print("Next: re-run change_detect.py, which will pick up REFDRY_ALIGNED.")


if __name__ == "__main__":
    main()
