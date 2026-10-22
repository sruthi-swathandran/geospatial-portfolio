"""
RS-01 / validation scoping for the 7 and 31 August maps (REVIEW F-01, F-02).
How much of each map was under clear sky in the nearest Landsat scenes?

scene_inventory.py found no Sentinel-2 scene near either date with usable sky.
The nearest candidates are Landsat: Landsat 8 on 3 August, four days before
the 7 August radar, and Landsat 7 on 4 August; for 31 August, Landsat 7 on 27
August and Landsat 8 on 28 August. Their cloud figures are per scene. This
script reads the per-pixel QA band of each scene from Planetary Computer's
Collection 2 Level-2, puts it on the map's 20 m grid, and counts clear sky over
the map's imaged ground and over its mapped flood.

Clear means a QA pixel that is not fill and carries none of the bits for
dilated cloud, cirrus, cloud or cloud shadow. Landsat 7's scan-line gaps are
fill, so they count as unseen. The QA band is automatic and misses some cloud,
as SCL did on 12 August, so the clear figure is an upper bound on what a
sample could label.

Two things make these scenes weaker references than 12 August's whatever the
sky: they are 3 to 4 days from the radar while the flood was receding, against
20 hours, and Landsat's 30 m pixels are coarser than the map's 20 m cells.

Outputs
-------
  data/validation/landsat_qa_<scene date>_20m.tif   QA on the map grid, not committed
  results/validation/landsat_clear_<map date>.csv   one row per scene date

Usage
-----
    python src\\landsat_clear_sky.py --map-date 2016-08-07
    python src\\landsat_clear_sky.py --map-date 2016-08-31
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.errors import WindowError
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BBOX, DATA, RESULTS                                # noqa: E402

MPC = "https://planetarycomputer.microsoft.com/api/stac/v1"
FULL = RESULTS / "fullscene"
OUT = RESULTS / "validation"
WORK = DATA / "validation"
LAND, FLOOD, PERMANENT, NODATA = 0, 1, 2, 255
UNSEEN = 0
# QA_PIXEL bits: 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow
CLOUDY_BITS = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)
DEFAULT_SCENES = {"2016-08-07": ["2016-08-03", "2016-08-04"],
                  "2016-08-31": ["2016-08-27", "2016-08-28"]}


def qa_mosaic(ref, day):
    """Every Landsat 7 and 8 QA band of one day, placed on the map grid."""
    client = Client.open(MPC, modifier=planetary_computer.sign_inplace)
    items = sorted(client.search(collections=["landsat-c2-l2"], bbox=BBOX,
                                 datetime=day).items(), key=lambda i: i.id)
    items = [i for i in items if i.properties.get("platform", "").lower()
             in ("landsat-7", "landsat-8")]
    mosaic = np.zeros((ref.height, ref.width), "uint16")
    full = Window(0, 0, ref.width, ref.height)
    for k, it in enumerate(items, 1):
        with rasterio.open(it.assets["qa_pixel"].href) as src:
            b = transform_bounds(src.crs, ref.crs, *src.bounds)
            try:
                win = from_bounds(*b, transform=ref.transform)
                win = win.round_offsets().round_lengths().intersection(full)
            except WindowError:
                continue
            h, w = int(win.height), int(win.width)
            dst = np.ones((h, w), "uint16")              # 1 = fill
            reproject(source=rasterio.band(src, 1), destination=dst,
                      src_transform=src.transform, src_crs=src.crs, src_nodata=1,
                      dst_transform=ref.window_transform(win), dst_crs=ref.crs,
                      dst_nodata=1, resampling=Resampling.nearest)
        r0, c0 = int(win.row_off), int(win.col_off)
        block = mosaic[r0:r0 + h, c0:c0 + w]
        seen = (dst & 1) == 0
        fill = (block == UNSEEN) & seen
        block[fill] = dst[fill]
        print(f"  [{k}/{len(items)}] {it.id}  "
              f"{float(it.properties.get('eo:cloud_cover') or 0):5.1f}% cloud")
    return mosaic, [i.id for i in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map-date", required=True, choices=sorted(DEFAULT_SCENES))
    ap.add_argument("--scene-date", nargs="+", default=None,
                    help="Landsat dates to measure; defaults to the nearest ones")
    args = ap.parse_args()
    tag = args.map_date.replace("-", "")
    map_tif = FULL / f"India_water_20m_{tag}_refined.tif"
    if not map_tif.exists():
        sys.exit(f"{map_tif} not found")

    print("=" * 78)
    print(f"CLEAR SKY OVER THE {args.map_date} MAP, LANDSAT QA")
    print("=" * 78)
    rows = []
    with rasterio.open(map_tif) as ref:
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        m = ref.read(1)
        imaged = m != NODATA
        flood = m == FLOOD
        for day in args.scene_date or DEFAULT_SCENES[args.map_date]:
            print(f"\n{day}")
            qa, ids = qa_mosaic(ref, day)
            if not ids:
                print("  no Landsat 7 or 8 scene that day")
                continue
            profile = ref.profile.copy()
            profile.update(dtype="uint16", nodata=UNSEEN, compress="deflate",
                           tiled=True, blockxsize=512, blockysize=512, count=1)
            WORK.mkdir(parents=True, exist_ok=True)
            with rasterio.open(WORK / f"landsat_qa_{day.replace('-', '')}_20m.tif",
                               "w", **profile) as dst:
                dst.write(qa, 1)
            seen = qa != UNSEEN
            clear = seen & ((qa & CLOUDY_BITS) == 0)
            row = dict(map_date=args.map_date, scene_date=day, scenes=len(ids),
                       imaged_ha=round(float(imaged.sum()) * px_ha),
                       imaged_seen_ha=round(float((imaged & seen).sum()) * px_ha),
                       imaged_clear_ha=round(float((imaged & clear).sum()) * px_ha),
                       flood_ha=round(float(flood.sum()) * px_ha),
                       flood_clear_ha=round(float((flood & clear).sum()) * px_ha))
            row["imaged_clear_pct"] = round(100 * row["imaged_clear_ha"]
                                            / max(row["imaged_ha"], 1), 1)
            row["flood_clear_pct"] = round(100 * row["flood_clear_ha"]
                                           / max(row["flood_ha"], 1), 1)
            rows.append(row)
            print(f"  map imaged {row['imaged_ha']:>12,} ha, clear "
                  f"{row['imaged_clear_ha']:>10,} ha ({row['imaged_clear_pct']}%)")
            print(f"  map flood  {row['flood_ha']:>12,} ha, clear "
                  f"{row['flood_clear_ha']:>10,} ha ({row['flood_clear_pct']}%)")
    if rows:
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"landsat_clear_{tag}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  wrote {path}")
    print("\n  Clear is the QA band's call, an upper bound on what can be labelled.")
    print("  These scenes are 3 to 4 days from the radar, at 30 m.")


if __name__ == "__main__":
    main()
