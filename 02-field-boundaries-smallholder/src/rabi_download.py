"""
RS-02. A December to February image for every Indian test chip, built the way
FTW built its own.

rabi_probe.py showed two things. Nearly every Indian test chip has scenes in
both rabi seasons, and FTW's window_a and window_b can be rebuilt from the
Planetary Computer archive to within 0.11% median difference and a correlation
of 0.992 or better, with the bands, offset and resampling FTW's downloader
uses. This uses that same recipe for a third window.

For each chip and season:

    1. list the L2A scenes from 1 December to the end of February that cover
       the whole chip, least cloudy tile first
    2. read each one's scene classification layer (SCL) onto the chip's grid
       and measure the chip's own cloud: no data, saturated, cloud shadow,
       medium and high probability cloud and thin cirrus, SCL classes
       0, 1, 3, 8, 9 and 10
    3. take the first scene under 5% chip cloud, or if none is, the clearest
       one tried
    4. read B04, B03, B02 and B08 onto the chip's grid, bilinear, subtract
       1000 if the scene's processing baseline is 4.0 or later, and write a
       four-band uint16 GeoTIFF with FTW's band names and the chip's own
       profile

Every choice is written to results/india/rabi_scenes.csv, with the chip cloud
of the scene used, so a chip whose image is not clear enough can be left out
of the test by a rule set beforehand. rabi_test.py sets that rule at 10%.

The run appends as it goes and skips chips already written, so it can be
stopped and started again.

    python src\\rabi_download.py --season 2016-17 --limit 5
    python src\\rabi_download.py --season 2016-17
    python src\\rabi_download.py --season 2015-16

Writes data/rabi/india/<season>/<chip>.tif. The data folder is not in git;
the CSV of scenes is, and it is enough to rebuild every image.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
CLOUD_CLASSES = (0, 1, 3, 8, 9, 10)
GOOD_ENOUGH = 0.05
FIELDS = ["chip", "season", "scene", "date", "baseline", "tile_cloud",
          "chip_cloud", "tried", "file"]


def chip_cloud(item, grid, sign, R) -> float:
    scl = R.read_on_grid(sign(item["assets"]["SCL"]["href"]), grid,
                         nearest=True)
    return float(np.isin(scl, CLOUD_CLASSES).mean())


def write_chip(arr: np.ndarray, F, chip: str, dest: Path) -> None:
    """Four bands with the chip's own profile and FTW's band names."""
    import rasterio
    with rasterio.open(F.IMG_A / chip) as s:
        prof = s.profile
    prof.update(count=4, dtype="uint16", compress="deflate", nodata=None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dest, "w", **prof) as d:
        d.write(arr)
        for k, name in enumerate(F.FTW_BANDS, 1):
            d.set_band_description(k, name)


def done(path: Path, season: str) -> set:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["chip"] for r in csv.DictReader(fh) if r["season"] == season}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True, choices=["2015-16", "2016-17"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tries", type=int, default=6,
                    help="scenes checked for chip cloud, least cloudy first")
    args = ap.parse_args()

    os.environ["FTW_COUNTRY"] = "india"
    import ftw_common as F
    import planetary_computer as pc
    import rabi_probe as R
    import requests
    session = requests.Session()
    sign = pc.sign_url

    chips = R.chip_names(F)
    if args.limit:
        chips = chips[:args.limit]
    log = F.RESULTS / "rabi_scenes.csv"
    have = done(log, args.season)
    todo = [c for c in chips if c not in have]
    out_dir = F.PROJECT / "data" / "rabi" / "india" / args.season

    print(RULE)
    print(f"DECEMBER TO FEBRUARY IMAGES, SEASON {args.season}")
    print(RULE)
    print(f"  {len(have)} chips already done, {len(todo)} to go")
    print(f"  writing to {out_dir}\n")

    new_file = not log.exists()
    fh = log.open("a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()

    tic = time.time()
    clear = 0
    try:
        for i, chip in enumerate(todo, 1):
            grid = R.chip_grid(F, chip)
            items = R.search(grid["bbox"], R.SEASONS[args.season], 100.01,
                             session)
            items.sort(key=lambda it: it["properties"].get("eo:cloud_cover",
                                                           100))
            best, best_cloud, tried = None, 2.0, 0
            for it in items[:args.tries]:
                try:
                    cc = chip_cloud(it, grid, sign, R)
                except Exception as exc:                      # noqa: BLE001
                    print(f"    {chip} {it['id']}: SCL read failed, {exc}")
                    continue
                tried += 1
                if cc < best_cloud:
                    best, best_cloud = it, cc
                if cc < GOOD_ENOUGH:
                    break
            row = {"chip": chip, "season": args.season, "scene": "",
                   "date": "", "baseline": "", "tile_cloud": "",
                   "chip_cloud": "", "tried": tried, "file": ""}
            if best is not None:
                arr = R.build_chip(best, grid, sign)
                dest = out_dir / chip
                write_chip(arr, F, chip, dest)
                clear += best_cloud <= 0.10
                row.update({
                    "scene": best["id"],
                    "date": best["properties"]["datetime"][:10],
                    "baseline": R.baseline(best),
                    "tile_cloud": best["properties"].get("eo:cloud_cover"),
                    "chip_cloud": round(best_cloud, 4),
                    "file": dest.relative_to(F.PROJECT).as_posix()})
            w.writerow(row)
            fh.flush()
            if i % 10 == 0 or i == len(todo):
                rate = i / (time.time() - tic)
                print(f"    {i:>4} / {len(todo)}   {rate * 60:.1f} chips/min"
                      f"   {(len(todo) - i) / rate / 60:.0f} min left   "
                      f"{clear} of {i} at or under 10% cloud")
    except KeyboardInterrupt:
        print("\n  stopped. Run the same command again to carry on.")
    finally:
        fh.close()
    print(f"\n  log in results\\india\\{log.name}")
    print(RULE)


if __name__ == "__main__":
    main()
