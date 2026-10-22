"""
RS-01 / validation scoping. List the free optical scenes that could serve as
reference for an accuracy sample of the 12 August 2016 map.

F-01 and F-02 in REVIEW.md ask for a design-based area estimate with a standard
error, which needs reference labels independent of the map. Sentinel-1 cannot
supply them, since it is the map's own sensor, and the Sen1Floods11 chips were
used to set the threshold. This script answers a narrower question first: in
the days around 12 August 2016, which optical images exist over the study area,
and how cloudy are they? If too few are clear, the accuracy sample is not
feasible and the coarse pattern check is the realistic ceiling.

Nothing here is downloaded except catalogue records. Every catalogue is
searched anonymously.

Routes searched
---------------
  Sentinel-2      Planetary Computer L2A, Earth Search L1C and L2A,
                  Copernicus Data Space L1C
  Landsat 7, 8    Planetary Computer Collection 2 Level-2, with Earth Search
                  as a second route
  MODIS daily     Planetary Computer, any MOD09G* or MYD09G* collection it lists

The same Sentinel-2 scene can appear on several routes. Each route is reported
on its own, so the output also shows which route actually holds 2016.

Cloud cover is the catalogue's figure for the whole scene or tile, not for the
study area, so treat it as a first screen. MODIS records carry no cloud figure;
its cloud has to be read from the state flags in the imagery itself.

Usage
-----
    python src\\scene_inventory.py
    python src\\scene_inventory.py --start 2016-08-05 --end 2016-08-19
    python src\\scene_inventory.py --cloud-max 50
    python src\\scene_inventory.py --map-date 2016-08-07 --start 2016-08-02 --end 2016-08-12
        for the 7 August map; writes scene_inventory_20160807*.csv instead

Writes results/validation/scene_inventory.csv, one row per scene, and
results/validation/scene_inventory_summary.csv, one row per route, sensor and
day. They record why Sentinel-2A on 12 August was chosen as the reference.

Requires pystac-client and shapely, both in the project environment.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from pyproj import Transformer
from pystac_client import Client
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BBOX, RESULTS, TARGET_CRS          # noqa: E402

MPC = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
CDSE = "https://stac.dataspace.copernicus.eu/v1"

FLOOD_DATE = date(2016, 8, 12)

# (route label, catalogue, wanted collection ids, or a prefix ending in "*")
ROUTES = [
    ("Sentinel-2 L2A, Planetary Computer", MPC, ["sentinel-2-l2a"]),
    ("Sentinel-2 L1C, Earth Search", EARTH_SEARCH, ["sentinel-2-l1c"]),
    ("Sentinel-2 L2A, Earth Search", EARTH_SEARCH, ["sentinel-2-l2a"]),
    ("Sentinel-2 L1C, Copernicus Data Space", CDSE, ["sentinel-2-l1c"]),
    ("Landsat C2 L2, Planetary Computer", MPC, ["landsat-c2-l2"]),
    ("Landsat C2 L2, Earth Search", EARTH_SEARCH, ["landsat-c2-l2"]),
    ("MODIS daily, Planetary Computer", MPC, ["modis-09g*"]),
]

TO_UTM = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True).transform
AOI = box(*BBOX)
AOI_HA = transform(TO_UTM, AOI).area / 1e4


def open_catalogue(url, cache):
    """Open a catalogue once and list its collection ids, or report why not."""
    if url in cache:
        return cache[url]
    try:
        client = Client.open(url)
        ids = sorted(c.id for c in client.get_collections())
        cache[url] = (client, ids, None)
    except Exception as exc:                        # unreachable or not STAC
        cache[url] = (None, [], f"{type(exc).__name__}: {exc}")
    return cache[url]


def match_collections(wanted, available):
    found = []
    for w in wanted:
        if w.endswith("*"):
            found += [a for a in available if a.lower().startswith(w[:-1])]
        elif w in available:
            found.append(w)
    return found


def sensor_of(item):
    """A plain sensor name from whatever the record provides."""
    p = item.properties
    plat = str(p.get("platform") or "").lower()
    if plat.startswith("sentinel-2"):
        return "Sentinel-2" + plat[-1].upper() if plat[-1] in "ab" else "Sentinel-2"
    if plat.startswith("landsat"):
        return "Landsat " + plat.split("-")[-1]
    up = item.id.upper()
    if up.startswith("MOD"):
        return "MODIS Terra"
    if up.startswith("MYD"):
        return "MODIS Aqua"
    if "terra" in plat:
        return "MODIS Terra"
    if "aqua" in plat:
        return "MODIS Aqua"
    return plat or "unknown"


def when(item):
    """Acquisition time, falling back to the start of a date range."""
    if item.datetime is not None:
        return item.datetime
    start = item.properties.get("start_datetime")
    return datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None


def cloud_of(item):
    p = item.properties
    for key in ("eo:cloud_cover", "landsat:cloud_cover_land", "cloudCover"):
        if p.get(key) is not None:
            return float(p[key])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-08-09")
    ap.add_argument("--end", default="2016-08-15")
    ap.add_argument("--cloud-max", type=float, default=30.0,
                    help="scene cloud cover, in percent, counted as usable")
    ap.add_argument("--map-date", default=FLOOD_DATE.isoformat(),
                    help="the map the scenes would check; another date writes "
                         "files named after it, beside the 12 August ones")
    args = ap.parse_args()
    map_date = date.fromisoformat(args.map_date)
    tag = "" if map_date == FLOOD_DATE else f"_{map_date:%Y%m%d}"

    out_dir = RESULTS / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"SCENE INVENTORY, OPTICAL REFERENCE AROUND THE {map_date:%d %B %Y} MAP".upper())
    print("=" * 78)
    print(f"  study area  {BBOX}, {AOI_HA:,.0f} ha")
    print(f"  window      {args.start} to {args.end}, UTC dates")
    print(f"  usable      scene cloud cover at or below {args.cloud_max:g}%\n")

    cache, rows = {}, []
    for label, url, wanted in ROUTES:
        client, available, err = open_catalogue(url, cache)
        if err:
            print(f"  {label}: catalogue not reachable ({err})")
            continue
        cols = match_collections(wanted, available)
        if not cols:
            near = [a for a in available
                    if any(w.rstrip("*").split("-")[0] in a for w in wanted)]
            print(f"  {label}: no collection named {', '.join(wanted)}; "
                  f"similar: {', '.join(near[:8]) or 'none'}")
            continue
        for col in cols:
            try:
                items = list(client.search(collections=[col], bbox=BBOX,
                                           datetime=f"{args.start}/{args.end}",
                                           max_items=5000).items())
            except Exception as exc:
                print(f"  {label} [{col}]: search failed ({type(exc).__name__}: {exc})")
                continue
            print(f"  {label} [{col}]: {len(items)} record(s)")
            for it in items:
                t = when(it)
                if t is None or it.geometry is None:
                    continue
                foot = shape(it.geometry).intersection(AOI)
                if foot.is_empty:
                    continue
                rows.append(dict(
                    route=label, collection=col, sensor=sensor_of(it), id=it.id,
                    datetime_utc=t.strftime("%Y-%m-%d %H:%M"),
                    date=t.date().isoformat(),
                    days_from_flood_map=(t.date() - map_date).days,
                    cloud_pct="" if cloud_of(it) is None else round(cloud_of(it), 1),
                    aoi_overlap_pct=round(transform(TO_UTM, foot).area / 1e4
                                          / AOI_HA * 100, 1),
                    _foot=foot,
                ))

    if not rows:
        print("\nNo scenes found on any route. Check the messages above.")
        return

    rows.sort(key=lambda r: (r["route"], r["sensor"], r["datetime_utc"]))
    fields = [k for k in rows[0] if not k.startswith("_")]
    with open(out_dir / f"scene_inventory{tag}.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # one line per route, sensor and day: how much of the study area is seen,
    # and how much by scenes under the cloud limit
    groups = defaultdict(list)
    for r in rows:
        groups[(r["route"], r["sensor"], r["date"])].append(r)

    summary = []
    for (route, sensor, day), rs in sorted(groups.items(),
                                            key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])):
        clouds = [r["cloud_pct"] for r in rs if r["cloud_pct"] != ""]
        seen = transform(TO_UTM, unary_union([r["_foot"] for r in rs])).area / 1e4
        clear = [r["_foot"] for r in rs
                 if r["cloud_pct"] != "" and r["cloud_pct"] <= args.cloud_max]
        clear_ha = transform(TO_UTM, unary_union(clear)).area / 1e4 if clear else 0.0
        summary.append(dict(
            route=route, sensor=sensor, date=day,
            days_from_flood_map=rs[0]["days_from_flood_map"], scenes=len(rs),
            aoi_seen_pct=round(seen / AOI_HA * 100, 1),
            median_cloud_pct=round(statistics.median(clouds), 1) if clouds else "",
            aoi_seen_by_usable_pct=round(clear_ha / AOI_HA * 100, 1) if clouds else "",
        ))

    with open(out_dir / f"scene_inventory{tag}_summary.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    print()
    print(f"  {'date':<10} {'d':>3}  {'sensor':<13} {'n':>3} {'seen':>6} "
          f"{'cloud':>6} {'usable':>7}  route")
    for s in summary:
        cloud = "n/a" if s["median_cloud_pct"] == "" else f"{s['median_cloud_pct']:.0f}%"
        usable = "n/a" if s["aoi_seen_by_usable_pct"] == "" \
            else f"{s['aoi_seen_by_usable_pct']:.0f}%"
        print(f"  {s['date']:<10} {s['days_from_flood_map']:>+3}  {s['sensor']:<13} "
              f"{s['scenes']:>3} {s['aoi_seen_pct']:>5.0f}% {cloud:>6} {usable:>7}  "
              f"{s['route']}")

    print(f"\n  d       days from the {map_date:%d %B} map")
    print("  seen    share of the study area inside any scene that day")
    print("  cloud   median scene cloud cover, from the catalogue")
    print(f"  usable  share of the study area inside scenes at or below "
          f"{args.cloud_max:g}% cloud")
    print("\n  Landsat 7 images from 2016 have stripe gaps from its failed scan line")
    print("  corrector, so its usable share overstates what can be labelled.")
    print(f"\n  wrote {out_dir / f'scene_inventory{tag}.csv'}")
    print(f"  wrote {out_dir / f'scene_inventory{tag}_summary.csv'}")


if __name__ == "__main__":
    main()
