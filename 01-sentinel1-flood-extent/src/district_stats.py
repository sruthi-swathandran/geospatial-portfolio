"""
RS-01 / step 12 - flooded cropland by district.

"130,772 hectares of water" is a remote sensing result. "X hectares of cropland
flooded in Barpeta district" is something a relief officer, an insurer or an
agriculture department can act on. This is the step that turns one into the
other, and it is the only output of this project a non-specialist will read.

WHAT IT CROSSES
---------------
  the refined flood map      step 11b, 20 m, slope > 8 deg removed
  ESA WorldCover class 40    cropland, 10 m, resampled onto the flood grid
  geoBoundaries ADM2         district polygons for India, CC-BY 4.0, open

STATE THE TIME GAP RATHER THAN HIDE IT
--------------------------------------
The flood is August 2016. WorldCover exists for 2020 and 2021 only. So the
cropland layer is four to five years after the event, and any land that changed
use in between is misattributed. There is no open 10 m cropland map for India in
2016, so the choice is between using a later one and saying so, or not
producing the number at all. This script says so, in the CSV and on the chart.

The same caveat applies to district boundaries, which get redrawn. Assam created
new districts after 2016, so a 2016 flood attributed to present-day boundaries
will not match a 2016 government bulletin district for district. Worth a line in
the README.

Outputs:
    data/boundaries/india_adm2.geojson         cached, downloaded once
    data/worldcover/India_wc_<res>m_<ty>_<tx>.tif
    results/district_flood_stats.csv
    results/district_flood_stats.geojson       for the web map in step 13
    results/figures/flooded_cropland.png

Usage:
    python src\\district_stats.py --res 20
    python src\\district_stats.py --res 20 --geojson path\\to\\your_adm2.geojson
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
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
from rasterio.features import rasterize     # noqa: E402
from rasterio.warp import transform_geom    # noqa: E402
from rasterio.windows import Window         # noqa: E402
from shapely.geometry import shape           # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                               # noqa: E402
from config import (                                      # noqa: E402
    EVENT, BBOX, DATA, RESULTS, MPC_STAC, TILE_PX, RESAMPLING,
    CROPLAND_CLASS, GEOBOUNDARIES_API, pixel_ha,
)

OUT_DIR = RESULTS / "fullscene"
BOUND_DIR = DATA / "boundaries"
WC_DIR = DATA / "worldcover"
FIGURES = RESULTS / "figures"
for d in (BOUND_DIR, WC_DIR, FIGURES):
    d.mkdir(parents=True, exist_ok=True)

TILE = TILE_PX
LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
CROPLAND = CROPLAND_CLASS
WC_COLLECTION = getattr(config, "WC_COLLECTION", "esa-worldcover")
GB_API = GEOBOUNDARIES_API


# ------------------------------------------------------------- boundaries
def fetch_boundaries(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    print(f"  downloading district boundaries from geoBoundaries")
    with urllib.request.urlopen(GB_API, timeout=60) as r:
        meta = json.loads(r.read().decode("utf-8"))
    url = meta.get("gjDownloadURL") or meta.get("simplifiedGeometryGeoJSON")
    if not url:
        raise SystemExit(
            "geoBoundaries returned no download URL. Keys were: "
            f"{sorted(meta)}. Download an ADM2 GeoJSON yourself and pass it "
            "with --geojson.")
    print(f"  {url}")
    with urllib.request.urlopen(url, timeout=300) as r:
        gj = json.loads(r.read().decode("utf-8"))
    path.write_text(json.dumps(gj), encoding="utf-8")
    print(f"  cached to {path.name} ({len(gj['features'])} features)")
    return gj


def name_of(props: dict) -> str:
    for k in ("shapeName", "NAME_2", "district", "DISTRICT", "name"):
        if props.get(k):
            return str(props[k])
    return "unnamed"


def bbox_of(geom) -> tuple[float, float, float, float]:
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


# -------------------------------------------------------------- land cover
def worldcover_tile(items, gbox, key, res) -> np.ndarray:
    cache = WC_DIR / f"{EVENT}_wc_{res:g}m_{key[0]}_{key[1]}.tif"
    if cache.exists():
        with rasterio.open(cache) as src:
            return src.read(1)

    ds = odc_load(items, bands=["map"], like=gbox, chunks={},
                  resampling=RESAMPLING["landcover"])
    da = ds["map"]
    if "time" in da.dims:
        da = da.isel(time=0)
    wc = np.asarray(da.compute()).astype("uint8")
    if wc.ndim == 3:
        wc = wc[0]

    profile = dict(driver="GTiff", height=wc.shape[0], width=wc.shape[1],
                   count=1, dtype="uint8", crs=gbox.crs,
                   transform=gbox.transform, compress="deflate")
    with rasterio.open(cache, "w", **profile) as dst:
        dst.write(wc, 1)
    return wc


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=20.0)
    ap.add_argument("--geojson", default=None,
                    help="use this ADM2 GeoJSON instead of downloading one")
    ap.add_argument("--top", type=int, default=15,
                    help="how many districts to chart")
    ap.add_argument("--variant", default="",
                    help="suffix identifying which acquisition to summarise")
    ap.add_argument("--wc-year", default=None,
                    help="WorldCover year to use; default is the most recent "
                         "available, which is the closest to the event")
    args = ap.parse_args()

    res = args.res
    tag = f"{res:g}m" + (f"_{args.variant}" if args.variant else "")
    stem = "district_flood_stats" + (f"_{args.variant}" if args.variant else "")
    src_tif = OUT_DIR / f"{EVENT}_water_{tag}_refined.tif"
    if not src_tif.exists():
        src_tif = OUT_DIR / f"{EVENT}_water_{tag}.tif"
        print(f"  no refined map found, falling back to {src_tif.name}")
    if not src_tif.exists():
        raise SystemExit("no full-scene map. Run full_scene.py first.")
    print(f"reading {src_tif.name}")

    px_ha = pixel_ha(res)
    gj = (json.loads(Path(args.geojson).read_text(encoding="utf-8"))
          if args.geojson else fetch_boundaries(BOUND_DIR / "india_adm2.geojson"))

    # keep only districts whose bounding box meets the AOI
    x0b, y0b, x1b, y1b = BBOX
    feats = []
    for f in gj["features"]:
        if not f.get("geometry"):
            continue
        a, b, c, d = bbox_of(f["geometry"])
        if a <= x1b and c >= x0b and b <= y1b and d >= y0b:
            feats.append(f)
    print(f"  {len(feats)} district(s) intersect the AOI bounding box")
    if not feats:
        raise SystemExit("no districts overlap the AOI, check the GeoJSON")

    full = rioxarray.open_rasterio(src_tif).odc.geobox
    crs = full.crs
    shapes, district_ha = [], {}
    for i, f in enumerate(feats, 1):
        g = transform_geom("EPSG:4326", str(crs), f["geometry"])
        shapes.append((g, i))
        # area of the WHOLE district, not just the imaged part. Computed in the
        # projected CRS, so it is metres squared and converts cleanly.
        district_ha[i] = shape(g).area / 10_000.0

    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    found = list(client.search(collections=[WC_COLLECTION], bbox=BBOX).items())
    if not found:
        raise SystemExit(f"no {WC_COLLECTION} items over the AOI")

    def item_year(it) -> str:
        """
        WorldCover items describe a whole year, so they carry start_datetime and
        end_datetime and leave `datetime` null. pystac surfaces that as None,
        which is correct and inconvenient.
        """
        if it.datetime is not None:
            return str(it.datetime.year)
        for k in ("start_datetime", "end_datetime"):
            v = it.properties.get(k)
            if v:
                return str(v)[:4]
        return "unknown"

    available = sorted({item_year(i) for i in found})
    year = args.wc_year or available[-1]
    if year not in available:
        raise SystemExit(f"{year} is not available. Years found: "
                         f"{', '.join(available)}")
    wc_items = [i for i in found if item_year(i) == year]
    years = [year]
    print(f"  {WC_COLLECTION}: {len(found)} item(s) across {', '.join(available)}"
          f"; using {year} ({len(wc_items)} item(s))")
    print("  NOTE: the flood is 2016 and this land cover is not. Any land that "
          "changed\n  use in between is misattributed, and that caveat travels "
          "with every\n  number below.\n")

    with rasterio.open(src_tif) as src:
        h, w = src.height, src.width

    n = len(feats)
    tot_px = np.zeros(n + 1, np.int64)
    crop_px = np.zeros(n + 1, np.int64)
    flood_px = np.zeros(n + 1, np.int64)
    floodcrop_px = np.zeros(n + 1, np.int64)
    perm_px = np.zeros(n + 1, np.int64)

    keys = [((ty, tx), y0, min(y0 + TILE, h), x0, min(x0 + TILE, w))
            for ty, y0 in enumerate(range(0, h, TILE))
            for tx, x0 in enumerate(range(0, w, TILE))]
    t0 = time.time()
    for m, (key, y0, y1, x0, x1) in enumerate(keys, 1):
        with rasterio.open(src_tif) as src:
            a = src.read(1, window=Window(x0, y0, x1 - x0, y1 - y0))
        if not np.any(a != NODATA):
            print(f"\r  {m}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
                  end="", flush=True)
            continue

        tg = full[y0:y1, x0:x1]
        did = rasterize(shapes, out_shape=a.shape, transform=tg.transform,
                        fill=0, dtype="int32")
        if not did.any():
            print(f"\r  {m}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
                  end="", flush=True)
            continue

        try:
            wc = worldcover_tile(wc_items, tg, key, res)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  tile {key}: land cover unavailable ({exc}), skipped")
            continue

        valid = a != NODATA
        crop = valid & (wc == CROPLAND)
        fl = valid & (a == FLOOD)
        pm = valid & (a == PERMANENT)

        tot_px += np.bincount(did[valid], minlength=n + 1)
        crop_px += np.bincount(did[crop], minlength=n + 1)
        flood_px += np.bincount(did[fl], minlength=n + 1)
        floodcrop_px += np.bincount(did[fl & crop], minlength=n + 1)
        perm_px += np.bincount(did[pm], minlength=n + 1)

        print(f"\r  {m}/{len(keys)} tiles ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()

    rows = []
    for i, f in enumerate(feats, 1):
        if tot_px[i] == 0:
            continue
        rows.append({
            "district": name_of(f["properties"]),
            "imaged_ha": round(tot_px[i] * px_ha, 1),
            "cropland_ha": round(crop_px[i] * px_ha, 1),
            "flood_ha": round(flood_px[i] * px_ha, 1),
            "flooded_cropland_ha": round(floodcrop_px[i] * px_ha, 1),
            "permanent_water_ha": round(perm_px[i] * px_ha, 1),
            "district_ha": round(district_ha[i], 1),
            "imaged_pct_of_district": round(
                100.0 * tot_px[i] * px_ha / max(district_ha[i], 1), 1),
            "pct_of_imaged_cropland_flooded": round(
                100.0 * floodcrop_px[i] / max(crop_px[i], 1), 2),
            "_i": i,
        })
    rows.sort(key=lambda r: -r["flooded_cropland_ha"])

    print("\nFLOODED CROPLAND BY DISTRICT")
    print("----------------------------")
    print(f"  {'district':<24}{'imaged ha':>11}{'of district':>13}"
          f"{'cropland ha':>13}{'flood ha':>10}{'flooded crop':>14}"
          f"{'% of crop':>11}  coverage")
    for r in rows[:25]:
        cov = r["imaged_pct_of_district"]
        flag = "" if cov >= 50 else ("PARTIAL" if cov >= 15 else "SLIVER")
        print(f"  {r['district'][:23]:<24}{r['imaged_ha']:>11,.0f}"
              f"{cov:>12.0f}%{r['cropland_ha']:>13,.0f}"
              f"{r['flood_ha']:>10,.0f}{r['flooded_cropland_ha']:>14,.0f}"
              f"{r['pct_of_imaged_cropland_flooded']:>10.1f}%  {flag}")
    if len(rows) > 25:
        print(f"  ... and {len(rows) - 25} more, all in the CSV")

    tot_flood = sum(r["flood_ha"] for r in rows)
    tot_fc = sum(r["flooded_cropland_ha"] for r in rows)
    print(f"\n  total flood in districts    {tot_flood:>12,.0f} ha")
    print(f"  of which cropland           {tot_fc:>12,.0f} ha  "
          f"({tot_fc/max(tot_flood,1):.0%})")
    # index 0 of the bincounts is every pixel that fell in no district polygon
    print(f"  flood outside any district  {flood_px[0]*px_ha:>12,.0f} ha  "
          f"({flood_px[0]*px_ha/max(tot_flood+flood_px[0]*px_ha,1):.1%} of the "
          f"scene total)")
    print(f"  area outside any district   {tot_px[0]*px_ha:>12,.0f} ha")
    print("  The AOI reaches into Bangladesh, Bhutan and Arunachal beyond the "
          "state\n  boundaries in this file, and geoBoundaries IND stops at "
          "the national\n  border, so flood there belongs to no row above. "
          "Check that this figure\n  matches the gap between the district "
          "total and the scene total before\n  treating either as complete.")
    print("\n  The coverage column is the share of the district the swath "
          "actually saw.\n  A percentage computed over a SLIVER is arithmetic "
          "rather than evidence:\n  Kamrup Metropolitan reading close to Nagaon "
          "means nothing when one was\n  imaged over a few thousand hectares "
          "and the other over a quarter of a\n  million. Quote the percentage "
          "only for rows with no flag, and quote the\n  hectares for the rest.")

    fields = ["district", "district_ha", "imaged_ha", "imaged_pct_of_district",
              "cropland_ha", "flood_ha", "flooded_cropland_ha",
              "permanent_water_ha", "pct_of_imaged_cropland_flooded"]
    with open(RESULTS / f"{stem}.csv", "w", newline="",
              encoding="utf-8") as fh:
        w_ = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w_.writeheader()
        w_.writerows(rows)

    by_i = {r["_i"]: r for r in rows}
    out_feats = []
    for i, f in enumerate(feats, 1):
        if i not in by_i:
            continue
        props = {k: v for k, v in by_i[i].items() if k != "_i"}
        props["source_landcover_year"] = ", ".join(years)
        out_feats.append({"type": "Feature", "geometry": f["geometry"],
                          "properties": props})
    (RESULTS / f"{stem}.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": out_feats}),
        encoding="utf-8")

    print(f"\nwrote {stem}.csv and {stem}.geojson")
    print("The chart for this table is drawn by make_figures.py, which owns "
          "flooded_cropland*.png.\nIt was drawn here as well, in a second "
          "style, with 12 August hard-coded into every\nvariant's title, and "
          "whichever script ran last decided what shipped.")


if __name__ == "__main__":
    main()
