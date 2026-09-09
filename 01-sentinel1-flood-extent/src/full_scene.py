"""
RS-01 / step 11 - run the settled method over the whole scene.

Everything up to here ran on 65 chips of 512 by 512. This runs on the event:
about 155 by 178 km, which at 10 m is roughly 276 million pixels and will not
fit in memory. So it works in tiles, writes each tile into the output as it
finishes, and records which tiles are done. Interrupt it and run it again and it
picks up where it stopped, which matters when a single pass takes the better
part of an hour over the network.

THE METHOD, AND WHERE EACH PIECE CAME FROM
------------------------------------------
  VH only                     step 5: VV adds nothing a threshold can use
  Lee 5x5 on linear power     step 10c: worth +0.037 IoU on the GEE product,
                              a bigger effect than the whole GEE to RTC move
  per-scene Otsu              step 10c: worth +0.016 precision at matched
                              recall against one pooled threshold, and the full
                              scene is the first place it can actually be done
  no slope mask               step 10: swept 2 to 20 degrees, removed true water
                              faster than shadow
  no change detection         step 9c: the best change threshold was the one
                              that made the constraint inert
  permanent water separated,  step 10: 95% of pixels JRC calls water half the
  never scored                time were hand-labelled as water, so removing them
                              improves the product and worsens the metric

OUTPUT CODING
-------------
One uint8 raster, because a three-way split is what the map needs:

    0    land
    1    flood water        (dark on 12 August, not permanently wet)
    2    permanent water    (dark on 12 August, JRC occurrence >= 50%)
    255  no data            (outside the frames, or masked)

Flood extent is code 1. Water extent is codes 1 and 2 together, which is the
thing the chip metrics were computed on. Keeping them in one file means the
viewer in step 13 can show either without a second pass.

RUN IT AT 20 m FIRST
--------------------
    python src\\full_scene.py --res 20

That covers the same ground with a quarter of the pixels and finishes in a
fraction of the time. Once it completes end to end, run the 10 m version. The
two outputs live in separate files, so nothing is overwritten.

Outputs:
    results/fullscene/India_water_<res>m.tif
    results/fullscene/state_<res>m.json          resume record and threshold
    results/fullscene/overview_<res>m.png
    results/fullscene_stats_<res>m.json

Usage:
    python src\\full_scene.py --res 20
    python src\\full_scene.py --res 20 --limit-tiles 2      # smoke test
    python src\\full_scene.py
    python src\\full_scene.py --threshold -18.75            # override Otsu
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
import xarray as xr                         # noqa: E402
from odc.geo.geobox import GeoBox           # noqa: E402
from odc.geo.geom import box                # noqa: E402
from odc.stac import load as odc_load       # noqa: E402
from rasterio.windows import Window         # noqa: E402
from shapely.geometry import box as sbox, shape   # noqa: E402
from shapely.ops import unary_union         # noqa: E402
from skimage.filters import threshold_otsu  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                               # noqa: E402
from config import (                                        # noqa: E402
    EVENT, BBOX, RESULTS, MPC_STAC, S1_COLLECTION, FLOOD_ITEMS,
    FLOOD_DATE, RELATIVE_ORBIT, TARGET_CRS, TARGET_RES,
    TILE_PX, TILE_HALO_PX, GSW_PERMANENT_MIN, RESAMPLING, pixel_ha,
)
from chips import lee_filter, morph_clean   # noqa: E402

OUT_DIR = RESULTS / "fullscene"
OUT_DIR.mkdir(parents=True, exist_ok=True)
GSW_COLLECTION = getattr(config, "GSW_COLLECTION", "jrc-gsw")

TILE = TILE_PX
HALO = TILE_HALO_PX
OCCURRENCE_CUT = GSW_PERMANENT_MIN
SIGN_TTL = 1500      # re-sign asset URLs every 25 min; the SAS tokens last ~45
RETRIES = 3          # per tile, each with freshly signed URLs

# Mutable copy so a command-line override can replace a declared rule for one
# run without editing config.py. Default is exactly what config declares, so
# an unflagged run reproduces the published numbers.
_RS = dict(RESAMPLING)

LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255


# ------------------------------------------------------------------ setup
def open_catalog():
    return pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)


def flood_items(client, quiet=False, date=None, orbit=None):
    """
    Resolve the flood frames the way every other script here does.

    FLOOD_ITEMS holds Sentinel-1 GRD granule names from the Earth Search
    catalogue. The RTC collection on Planetary Computer does not use those ids,
    so searching by id returns nothing. Bounding box plus date plus relative
    orbit is what the rest of the pipeline uses and what actually works.
    """
    date = date or FLOOD_DATE
    orbit = RELATIVE_ORBIT if orbit is None else orbit
    d = dt.date.fromisoformat(date)
    window = (f"{(d - dt.timedelta(days=1)).isoformat()}/"
              f"{(d + dt.timedelta(days=1)).isoformat()}")
    found = list(client.search(collections=[S1_COLLECTION], bbox=BBOX,
                               datetime=window).items())
    items = [i for i in found
             if i.datetime.date().isoformat() == date
             and i.properties.get("sat:relative_orbit") == orbit
             and len(i.properties.get("sar:polarizations") or []) == 2]

    if not items:
        print(f"  nothing on {date}, orbit {orbit}, dual pol. "
              f"The search returned {len(found)} item(s):")
        for i in found[:20]:
            print(f"    {i.datetime.date()}  orbit "
                  f"{i.properties.get('sat:relative_orbit')}  "
                  f"{i.properties.get('sar:polarizations')}  {i.id}")
        raise SystemExit("no usable flood frames, check FLOOD_DATE and "
                         "RELATIVE_ORBIT in config.py")

    if not quiet:
        print(f"  resolved {len(items)} frame(s) on {date}, "
              f"orbit {orbit}:")
        for i in items:
            print(f"    {i.id}")
        if len(items) != len(FLOOD_ITEMS):
            print(f"  (config lists {len(FLOOD_ITEMS)} GRD granule name(s); "
                  "these are the RTC equivalents)")
    return items


def refresh_frames(date=None, orbit=None):
    """
    Search again to get freshly signed asset URLs.

    planetary_computer.sign_inplace stamps each asset href with a SAS token that
    lasts under an hour, and it does that once, at search time. A full-scene run
    outlives its own credentials, which shows up as "Aborting load due to
    failure while reading" partway through. Re-searching is the cheap fix.
    """
    client = open_catalog()
    return (flood_items(client, quiet=True, date=date, orbit=orbit),
            gsw_items(client))


def process_tile(items, gsw, gbox, thr, y0, y1, x0, x1):
    pg, (oy, ox) = padded(gbox, y0, y1, x0, x1)
    th, tw = y1 - y0, x1 - x0
    vh = read_vh(items, pg)
    if not np.isfinite(vh).any():
        return np.full((th, tw), NODATA, "uint8")

    filt = lee_filter(vh.astype("float64"))
    water = morph_clean((filt <= thr).astype(np.int8)).astype(bool)
    water = water[oy:oy + th, ox:ox + tw]
    valid = np.isfinite(filt)[oy:oy + th, ox:ox + tw]

    occ = read_occurrence(gsw, pg)[oy:oy + th, ox:ox + tw]
    perm = np.isfinite(occ) & (occ >= OCCURRENCE_CUT)

    out = np.full((th, tw), NODATA, "uint8")
    out[valid] = LAND
    out[valid & water & ~perm] = FLOOD
    out[valid & water & perm] = PERMANENT
    return out


def gsw_items(client):
    items = list(client.search(collections=[GSW_COLLECTION], bbox=BBOX).items())
    if not items:
        raise SystemExit(f"no {GSW_COLLECTION} items over the AOI")
    return items


def target_geobox(res: float) -> GeoBox:
    aoi = box(*BBOX, crs="EPSG:4326").to_crs(TARGET_CRS)
    return GeoBox.from_bbox(aoi.boundingbox, crs=TARGET_CRS, resolution=res)


def tiles(gbox: GeoBox):
    h, w = gbox.shape
    for ty, y0 in enumerate(range(0, h, TILE)):
        for tx, x0 in enumerate(range(0, w, TILE)):
            yield (ty, tx), y0, min(y0 + TILE, h), x0, min(x0 + TILE, w)


def padded(gbox: GeoBox, y0, y1, x0, x1):
    h, w = gbox.shape
    py0, py1 = max(0, y0 - HALO), min(h, y1 + HALO)
    px0, px1 = max(0, x0 - HALO), min(w, x1 + HALO)
    return gbox[py0:py1, px0:px1], (y0 - py0, x0 - px0)


def to_db(da):
    return 10.0 * np.log10(da.where(da > 0))


def read_vh(items, gbox) -> np.ndarray:
    ds = odc_load(items, bands=["vh"], like=gbox, groupby="solar_day",
                  chunks={}, resampling=_RS["sar"])
    da = ds["vh"]
    if "time" in da.dims:
        da = da.isel(time=0)
    return np.asarray(to_db(da).compute()).astype("float32")


def read_occurrence(items, gbox) -> np.ndarray:
    ds = odc_load(items, bands=["occurrence"], like=gbox, chunks={},
                  resampling=_RS["occurrence"])
    da = ds["occurrence"]
    if "time" in da.dims:
        da = da.isel(time=0)
    occ = np.asarray(da.compute()).astype("float32")
    if occ.ndim == 3:
        occ = occ[0]
    occ[occ > 100] = np.nan
    return occ


# ------------------------------------------------------------- threshold
def covered_tiles(gbox, items, all_tiles):
    """
    Drop tiles that do not touch any frame.

    The AOI rectangle is much larger than the three descending frames that cross
    it, so most tiles hold nothing. Testing the geometry locally costs
    microseconds; discovering the same thing by loading the tile costs a network
    round trip each time.
    """
    footprint = unary_union([shape(i.geometry) for i in items])
    keep = []
    for key, y0, y1, x0, x1 in all_tiles:
        bb = gbox[y0:y1, x0:x1].extent.to_crs("EPSG:4326").boundingbox
        if sbox(bb.left, bb.bottom, bb.right, bb.top).intersects(footprint):
            keep.append((key, y0, y1, x0, x1))
    return keep


def validated_threshold():
    """The operating point chosen against hand labels in step 10b."""
    p = RESULTS / "final_method.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return float(d["operating_points"]["max_iou"]["threshold"])


def estimate_threshold(gbox, items, tile_list, n_samples=12) -> tuple[float, int]:
    """
    Per-scene Otsu, estimated from tiles spread across the whole footprint.

    Sampling rather than reading everything twice. Tiles are taken on an even
    stride so the sample covers hills and floodplain alike; taking the first
    twelve would estimate the threshold from one corner of the scene.
    """
    stride = max(1, len(tile_list) // n_samples)
    picked = tile_list[::stride][:n_samples]
    print(f"  estimating the scene threshold from {len(picked)} tiles spread "
          f"across {len(tile_list)}")

    pool, t0 = [], time.time()
    for n, (_, y0, y1, x0, x1) in enumerate(picked, 1):
        pg, _ = padded(gbox, y0, y1, x0, x1)
        vh = read_vh(items, pg)
        vh = lee_filter(vh.astype("float64")).astype("float32")
        v = vh[np.isfinite(vh)]
        if v.size > 5000:
            pool.append(v[::17])
        print(f"\r    sampled {n}/{len(picked)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    if not pool:
        raise SystemExit("every sampled tile was empty, check the frame ids")
    v = np.concatenate(pool)
    return float(threshold_otsu(v)), int(v.size)


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=float(TARGET_RES))
    ap.add_argument("--threshold", type=float, default=None,
                    help="use this VH threshold in dB, overriding everything")
    ap.add_argument("--otsu", action="store_true",
                    help="estimate the threshold by Otsu over the whole AOI "
                         "instead of using the label-validated one")
    ap.add_argument("--limit-tiles", type=int, default=None,
                    help="stop after N tiles, for a smoke test")
    ap.add_argument("--restart", action="store_true",
                    help="ignore the resume record and start over")
    ap.add_argument("--date", default=FLOOD_DATE,
                    help="acquisition date to map; defaults to the event date")
    ap.add_argument("--orbit", type=int, default=RELATIVE_ORBIT,
                    help="relative orbit; a different orbit means a different "
                         "day and a different incidence angle")
    ap.add_argument("--resample-sar", default=RESAMPLING["sar"],
                    help="resampling for the VH load; declared in config, "
                         "overridable here to test the choice (REVIEW S-01)")
    ap.add_argument("--resample-occurrence", default=RESAMPLING["occurrence"],
                    help="resampling for the JRC occurrence load")
    ap.add_argument("--variant", default="",
                    help="suffix for the output files, so a second "
                         "acquisition never overwrites the first")
    args = ap.parse_args()

    res = args.res
    _RS.update(sar=args.resample_sar, occurrence=args.resample_occurrence)
    if (args.resample_sar, args.resample_occurrence) != (
            RESAMPLING["sar"], RESAMPLING["occurrence"]):
        print(f"  RESAMPLING OVERRIDDEN: sar={args.resample_sar}, "
              f"occurrence={args.resample_occurrence}")
    tag = f"{res:g}m" + (f"_{args.variant}" if args.variant else "")
    out_tif = OUT_DIR / f"{EVENT}_water_{tag}.tif"
    state_path = OUT_DIR / f"state_{tag}.json"

    gbox = target_geobox(res)
    h, w = gbox.shape
    all_tiles = list(tiles(gbox))
    px_ha = pixel_ha(res)
    print(f"{EVENT} full scene at {res:g} m")
    print(f"  grid {w} x {h} px = {w*h/1e6:.1f} Mpx, "
          f"{w*res/1000:.1f} x {h*res/1000:.1f} km")
    print(f"  {len(all_tiles)} tiles of {TILE} px, {px_ha:.4f} ha per pixel\n")

    client = open_catalog()
    items = flood_items(client, date=args.date, orbit=args.orbit)
    gsw = gsw_items(client)
    print(f"  {len(gsw)} GSW tile(s)")

    live = covered_tiles(gbox, items, all_tiles)
    print(f"  {len(live)} of {len(all_tiles)} tiles touch a frame, "
          f"{len(all_tiles) - len(live)} are outside the swath\n")

    state = {"done": [], "threshold": None}
    if state_path.exists() and not args.restart:
        state = json.loads(state_path.read_text())
        print(f"  resuming: {len(state['done'])} tile(s) already written")

    if args.threshold is not None:
        state["threshold"] = args.threshold
        state["threshold_source"] = "command line"
        print(f"  threshold set on the command line: {args.threshold:.2f} dB")
    elif state["threshold"] is not None:
        print(f"  threshold from the resume record: {state['threshold']:.2f} dB "
              f"({state.get('threshold_source', 'unknown source')})")
    elif args.otsu:
        t, n = estimate_threshold(gbox, items, live)
        state["threshold"] = t
        state["threshold_source"] = "Otsu over the whole AOI"
        print(f"  Otsu over the AOI, {n:,} sampled pixels: {t:.2f} dB")
        print("  NOTE: this window is far larger than the one step 10c "
              "measured. It\n  includes hills and dry upland the labelled chips "
              "never sampled, which\n  pulls the split upward. Compare the "
              "flooded fraction below against the\n  label-validated run before "
              "trusting it.")
        state_path.write_text(json.dumps(state))
    else:
        t = validated_threshold()
        if t is None:
            raise SystemExit(
                "results/final_method.json not found. Run operating_point.py "
                "first, or pass --threshold, or pass --otsu.")
        state["threshold"] = t
        state["threshold_source"] = "max-IoU point from operating_point.py"
        print(f"  threshold from the labelled chips: {t:.2f} dB "
              "(max IoU on valid)")
        state_path.write_text(json.dumps(state))
    thr = state["threshold"]

    if not out_tif.exists() or args.restart:
        profile = dict(driver="GTiff", height=h, width=w, count=1,
                       dtype="uint8", crs=gbox.crs, transform=gbox.transform,
                       nodata=NODATA, tiled=True, blockxsize=512,
                       blockysize=512, compress="deflate", BIGTIFF="IF_SAFER")
        with rasterio.open(out_tif, "w", **profile) as dst:
            for _, y0, y1, x0, x1 in all_tiles:
                dst.write(np.full((y1 - y0, x1 - x0), NODATA, "uint8"), 1,
                          window=Window(x0, y0, x1 - x0, y1 - y0))
        state["done"] = []
        print(f"  created {out_tif.name}")

    done = {tuple(d) for d in state["done"]}
    todo = [t for t in live if t[0] not in done]
    if args.limit_tiles:
        todo = todo[:args.limit_tiles]
    print(f"\n  {len(todo)} tile(s) to process\n")

    t0 = time.time()
    signed_at = time.time()
    failed = []
    for n, (key, y0, y1, x0, x1) in enumerate(todo, 1):
        if time.time() - signed_at > SIGN_TTL:
            items, gsw = refresh_frames(args.date, args.orbit)
            signed_at = time.time()
            print("\n  re-signed the asset URLs")

        out = None
        for attempt in range(1, RETRIES + 1):
            try:
                out = process_tile(items, gsw, gbox, thr, y0, y1, x0, x1)
                break
            except Exception as exc:                    # noqa: BLE001
                if attempt == RETRIES:
                    print(f"\n  tile {key} failed {RETRIES} times, leaving it "
                          f"as no data\n    {exc}")
                    failed.append(list(key))
                else:
                    print(f"\n  tile {key} attempt {attempt} failed, re-signing "
                          "and retrying")
                    items, gsw = refresh_frames(args.date, args.orbit)
                    signed_at = time.time()
                    time.sleep(3)
        if out is None:
            continue

        with rasterio.open(out_tif, "r+") as dst:
            dst.write(out, 1, window=Window(x0, y0, x1 - x0, y1 - y0))

        state["done"].append(list(key))
        state_path.write_text(json.dumps(state))
        rate = (time.time() - t0) / n
        print(f"\r  {n}/{len(todo)} tiles  ({time.time()-t0:.0f}s, "
              f"{rate:.0f}s/tile, ~{rate*(len(todo)-n)/60:.0f} min left)  ",
              end="", flush=True)
    print()
    if failed:
        print(f"\n  {len(failed)} tile(s) could not be read: "
              f"{', '.join(str(tuple(f)) for f in failed)}")
        print("  They are not marked done, so running the script again retries "
              "them.")

    # ----------------------------------------------------------- totals
    counts = np.zeros(256, dtype=np.int64)
    with rasterio.open(out_tif) as src:
        for _, y0, y1, x0, x1 in all_tiles:
            a = src.read(1, window=Window(x0, y0, x1 - x0, y1 - y0))
            counts += np.bincount(a.ravel(), minlength=256)
        over = src.read(1, out_shape=(max(1, h // 30), max(1, w // 30)))

    flood_ha = counts[FLOOD] * px_ha
    perm_ha = counts[PERMANENT] * px_ha
    land_ha = counts[LAND] * px_ha
    nod_ha = counts[NODATA] * px_ha
    covered = land_ha + flood_ha + perm_ha

    print("\nFULL SCENE TOTALS")
    print("-----------------")
    print(f"  threshold used            {thr:>12.2f} dB")
    print(f"  imaged area               {covered:>12,.0f} ha")
    print(f"  flood water               {flood_ha:>12,.0f} ha  "
          f"({flood_ha/max(covered,1):.1%} of imaged area)")
    print(f"  permanent water           {perm_ha:>12,.0f} ha")
    print(f"  water extent (both)       {flood_ha + perm_ha:>12,.0f} ha")
    print(f"  no data                   {nod_ha:>12,.0f} ha")

    frac = flood_ha / max(covered, 1)
    if frac > 0.35:
        print(f"\n  WARNING: {frac:.0%} of the imaged area came out as flood. "
              "A threshold that\n  is too permissive is the usual cause. Compare "
              f"{thr:.2f} dB against the\n  label-validated "
              f"{validated_threshold()} dB and rerun with --restart if they\n"
              "  differ by more than about a decibel.")

    if len(state["done"]) < len(live):
        print(f"\n  NOTE: {len(live) - len(state['done'])} tile(s) inside the "
              "swath are still\n  unprocessed, so these totals are partial. Run "
              "again to finish them.")

    stats = {"event": EVENT, "resolution_m": res, "threshold_db": thr,
             "date": args.date, "relative_orbit": args.orbit,
             "pixel_ha": px_ha, "grid": [h, w], "crs": str(gbox.crs),
             "tiles_in_grid": len(all_tiles), "tiles_in_swath": len(live),
             "tiles_done": len(state["done"]),
             "occurrence_cut": OCCURRENCE_CUT,
             "threshold_source": state.get("threshold_source", "unknown"),
             "resampling": dict(_RS),
             "flood_ha": round(flood_ha, 1), "permanent_ha": round(perm_ha, 1),
             "water_ha": round(flood_ha + perm_ha, 1),
             "land_ha": round(land_ha, 1), "nodata_ha": round(nod_ha, 1)}
    (RESULTS / f"fullscene_stats_{tag}.json").write_text(
        json.dumps(stats, indent=2))

    show = np.full(over.shape, np.nan)
    show[over == LAND] = 0
    show[over == FLOOD] = 1
    show[over == PERMANENT] = 2
    fig, ax = plt.subplots(figsize=(11, 11 * h / max(w, 1)))
    ax.imshow(show, cmap=plt.get_cmap("Blues", 3), vmin=-0.5, vmax=2.5,
              interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{EVENT} 12 Aug 2016, {res:g} m, threshold {thr:.2f} dB\n"
                 f"flood {flood_ha:,.0f} ha, permanent water {perm_ha:,.0f} ha",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"overview_{tag}.png", dpi=130)

    print(f"\nwrote {out_tif.name}, overview_{tag}.png and "
          f"fullscene_stats_{tag}.json")


if __name__ == "__main__":
    main()
