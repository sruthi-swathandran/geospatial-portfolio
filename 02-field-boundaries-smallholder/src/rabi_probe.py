"""
RS-02. Is there a December to February image for the Indian test chips, and
can FTW's own chips be rebuilt from the archive?

The season test showed that India's second FTW image, March to June 2016,
works against the checkpoint, and that neither of FTW's windows shows rabi
crops standing. The direct test is to give the checkpoint an image from
December to February. Before downloading one for every chip, two things have
to be known.

PART availability
-----------------
For every Indian test chip, the Sentinel-2 L2A scenes on Microsoft's Planetary
Computer that cover the whole chip, in two rabi seasons:

    2015-16    1 December 2015 to 29 February 2016, the season whose harvest
               window_b shows
    2016-17    1 December 2016 to 28 February 2017, the season after the
               kharif window_a shows

Only Sentinel-2A was flying then, so a chip may have few scenes. The cloud
figure here is the scene's own, for the whole 110 km tile, and says nothing
certain about the chip; it is enough to judge whether a season is worth
pursuing. Metadata only, nothing is downloaded.

PART match
----------
A December to February image is only comparable with FTW's if it is built
the same way. FTW's own downloader (ftw_cli/download_img.py) reads bands B04,
B03, B02 and B08 of Planetary Computer L2A and resamples them bilinearly. For
scenes of processing baseline 4.0 or later it first subtracts 1000, the offset
those scenes carry.

So for a few chips this rebuilds window_a and window_b that way from every
scene in FTW's date range, and compares each with FTW's own file. If one scene
reproduces FTW's chip closely, the pipeline is right and that scene is the one
FTW used. If none does, a new image built this way would not be comparable and
the test has to stop until the difference is understood.

The bar, set before running: a scene reproduces FTW's chip if every band
correlates at 0.98 or more and the median difference is within 2% of the
median value. Correlation alone would pass a scene with an offset, and the
offset is exactly what B-23's neighbour, the baseline correction, can get
wrong.

    python src\\rabi_probe.py --part availability
    python src\\rabi_probe.py --part match --chips 3

Needs network access to planetarycomputer.microsoft.com, and the
planetary-computer and requests packages, both installed with ftw-tools.
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
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
COLLECTION = "sentinel-2-l2a"
BANDS = ("B04", "B03", "B02", "B08")       # FTW's order, ftw_cli/cfg.py
SEASONS = {
    "2015-16": "2015-12-01T00:00:00Z/2016-02-29T23:59:59Z",
    "2016-17": "2016-12-01T00:00:00Z/2017-02-28T23:59:59Z",
}
MATCH_R = 0.98
MATCH_REL = 0.02


def chip_names(F) -> list:
    pred = F.RESULTS / "pred_3class_full"
    return [p.name for p in sorted(pred.glob("*.tif"))]


def chip_grid(F, chip: str) -> dict:
    """The chip's CRS, transform, size and bounds in degrees."""
    import rasterio
    from rasterio.warp import transform_bounds
    with rasterio.open(F.INSTANCE / chip) as s:
        b = s.bounds
        if s.crs and s.crs.to_epsg() != 4326:
            b = transform_bounds(s.crs, "EPSG:4326", *b)
        # FTW's Indian chips run south to north (a positive y step), so
        # rasterio's "bottom" is the northern edge; sort before searching
        x0, y0, x1, y1 = (float(v) for v in b)
        return {"crs": s.crs, "transform": s.transform, "width": s.width,
                "height": s.height,
                "bbox": [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]}


def search(bbox, period: str, max_cloud: float, session) -> list:
    """Every L2A scene in the period whose footprint covers the whole bbox."""
    from shapely.geometry import box, shape
    body = {"collections": [COLLECTION], "bbox": bbox, "datetime": period,
            "limit": 250,
            "query": {"eo:cloud_cover": {"lt": max_cloud}}}
    items, url = [], STAC
    while url:
        for attempt in range(4):
            try:
                r = session.post(url, json=body, timeout=60)
                r.raise_for_status()
                break
            except Exception:                                 # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        page = r.json()
        items += page.get("features", [])
        nxt = [lk for lk in page.get("links", []) if lk.get("rel") == "next"]
        url = nxt[0]["href"] if nxt else None
        body = nxt[0].get("body", body) if nxt else body
    chip = box(*bbox)
    return [it for it in items if shape(it["geometry"]).contains(chip)]


def baseline(item) -> float:
    p = item.get("properties", {})
    v = p.get("s2:processing_baseline", p.get("processing:version", 0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def read_on_grid(href: str, grid: dict, nearest: bool = False) -> np.ndarray:
    """One band, resampled onto the chip's own grid.

    Bilinear, as FTW does, for reflectance. Nearest for a class band such as
    the scene classification, where averaging two classes means nothing.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    how = Resampling.nearest if nearest else Resampling.bilinear
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with rasterio.open(href) as src:
            with WarpedVRT(src, crs=grid["crs"], transform=grid["transform"],
                           width=grid["width"], height=grid["height"],
                           resampling=how) as vrt:
                return vrt.read(1)


def build_chip(item, grid: dict, sign) -> np.ndarray:
    """Four bands in FTW's order and FTW's offset convention, as uint16."""
    out = []
    for b in BANDS:
        href = sign(item["assets"][b]["href"])
        out.append(read_on_grid(href, grid).astype(np.int32))
    arr = np.stack(out)
    if baseline(item) >= 4.0:
        arr = np.clip(arr - 1000, 0, None)
    return arr.astype(np.uint16)


def compare(ours: np.ndarray, ftw: np.ndarray) -> dict:
    """Per band correlation and median difference over pixels both have."""
    rs, rels = [], []
    for k in range(ours.shape[0]):
        a = ours[k].astype(np.float64).ravel()
        b = ftw[k].astype(np.float64).ravel()
        ok = (a > 0) & (b > 0)
        if ok.sum() < 100:
            return {"r_min": float("nan"), "rel_max": float("nan")}
        rs.append(float(np.corrcoef(a[ok], b[ok])[0, 1]))
        rels.append(float(abs(np.median(a[ok] - b[ok])) / np.median(b[ok])))
    return {"r_min": min(rs), "rel_max": max(rels),
            "r": [round(x, 4) for x in rs],
            "rel": [round(x, 4) for x in rels]}


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run_availability(F, args, session) -> None:
    chips = chip_names(F)
    if args.limit:
        chips = chips[:args.limit]
    print(RULE)
    print(f"DECEMBER TO FEBRUARY SCENES, {len(chips)} INDIAN TEST CHIPS")
    print(RULE)
    print("  scenes covering the whole chip, tile cloud under "
          f"{args.max_cloud:.0f}%\n")
    rows = []
    tic = time.time()
    for i, chip in enumerate(chips, 1):
        bbox = chip_grid(F, chip)["bbox"]
        row = {"chip": chip}
        for season, period in SEASONS.items():
            items = search(bbox, period, args.max_cloud, session)
            clouds = sorted(float(it["properties"].get("eo:cloud_cover", 100))
                            for it in items)
            best = min(items, key=lambda it: it["properties"].get(
                "eo:cloud_cover", 100), default=None)
            row[f"{season}_scenes"] = len(items)
            row[f"{season}_under10"] = sum(c < 10 for c in clouds)
            row[f"{season}_best_cloud"] = round(clouds[0], 2) if clouds else ""
            row[f"{season}_best_date"] = (best["properties"]["datetime"][:10]
                                          if best else "")
            row[f"{season}_best_baseline"] = baseline(best) if best else ""
        rows.append(row)
        if i % 20 == 0 or i == len(chips):
            rate = i / (time.time() - tic)
            print(f"    {i:>4} / {len(chips)}   "
                  f"{(len(chips) - i) / rate / 60:.1f} min left")

    print(f"\n  {'season':<10}{'chips with any':>16}{'with one under 10%':>20}"
          f"{'median scenes':>15}")
    for season in SEASONS:
        n_any = sum(r[f"{season}_scenes"] > 0 for r in rows)
        n_clear = sum(r[f"{season}_under10"] > 0 for r in rows)
        med = np.median([r[f"{season}_scenes"] for r in rows])
        print(f"  {season:<10}{n_any:>16}{n_clear:>20}{med:>15.0f}")
    out = F.RESULTS / "rabi_availability.csv"
    write_csv(out, rows)
    print(f"\n  wrote results\\india\\{out.name}")


def run_match(F, args, session, sign) -> None:
    import json
    import rasterio
    cfg = json.loads((F.DATA / f"data_config_{F.COUNTRY}.json")
                     .read_text(encoding="utf-8"))["seasons"]
    chips = chip_names(F)[:args.chips]
    print(RULE)
    print(f"REBUILDING FTW'S OWN CHIPS FROM THE ARCHIVE, {len(chips)} chips")
    print(RULE)
    print(f"  a scene reproduces a chip if every band correlates at "
          f"{MATCH_R} or more\n  and the median difference is within "
          f"{MATCH_REL * 100:.0f}% of the median value\n")
    rows = []
    for chip in chips:
        grid = chip_grid(F, chip)
        for win, folder in (("window_a", F.IMG_A), ("window_b", F.IMG_B)):
            period = f"{cfg[win]['start']}T00:00:00Z/{cfg[win]['end']}T23:59:59Z"
            # every scene, however cloudy the tile: FTW chose for the chip
            items = search(grid["bbox"], period, 100.01, session)
            with rasterio.open(folder / chip) as s:
                ftw = s.read(F.band_index(folder / chip, BANDS))
            best = None
            for it in sorted(items, key=lambda it: it["properties"].get(
                    "eo:cloud_cover", 100))[:args.candidates]:
                try:
                    ours = build_chip(it, grid, sign)
                except Exception as exc:                      # noqa: BLE001
                    print(f"    {chip} {win} {it['id']}: read failed, {exc}")
                    continue
                c = compare(ours, ftw)
                rec = {"chip": chip, "window": win, "scene": it["id"],
                       "date": it["properties"]["datetime"][:10],
                       "baseline": baseline(it),
                       "tile_cloud": it["properties"].get("eo:cloud_cover"),
                       "r_min": round(c["r_min"], 4),
                       "rel_max": round(c["rel_max"], 4)}
                rows.append(rec)
                if best is None or (np.nan_to_num(c["r_min"]) >
                                    np.nan_to_num(best["r_min"])):
                    best = rec
            if best is None:
                print(f"  {chip} {win}: no scene could be read")
                continue
            ok = best["r_min"] >= MATCH_R and best["rel_max"] <= MATCH_REL
            print(f"  {chip} {win}: best {best['date']} baseline "
                  f"{best['baseline']}, r {best['r_min']:.4f}, median "
                  f"difference {best['rel_max'] * 100:.2f}%   "
                  f"{'REPRODUCES' if ok else 'does not reproduce'}")
    out = F.RESULTS / "rabi_match.csv"
    write_csv(out, rows)
    print(f"\n  wrote results\\india\\{out.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="availability",
                    choices=["availability", "match"])
    ap.add_argument("--limit", type=int, default=0,
                    help="availability: first N chips only")
    ap.add_argument("--chips", type=int, default=3,
                    help="match: how many chips to rebuild")
    ap.add_argument("--candidates", type=int, default=12,
                    help="match: scenes tried per window, least cloudy first")
    ap.add_argument("--max-cloud", type=float, default=60.0)
    args = ap.parse_args()

    os.environ["FTW_COUNTRY"] = "india"
    import ftw_common as F
    import requests
    session = requests.Session()

    if args.part == "availability":
        run_availability(F, args, session)
    else:
        import planetary_computer as pc
        run_match(F, args, session, pc.sign_url)
    print(RULE)


if __name__ == "__main__":
    main()
