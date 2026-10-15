"""
RS-01 / validation. A top-up sample for the one part of the floodplain the
main sample barely reached.

floodplain_layer.py found that land far from flood inside the 150 m floodplain
covers about 170,000 ha but holds only 7 of the 550 points. Seven points with
no water still allow a flood rate of up to about 41% at 95% confidence, which
could hide tens of thousands of hectares. This script draws 60 more points in
exactly that part, under the same rules as the main draw:

  stratum         land far from flood, more than about 1 km from flood in
                  either map, the same 100 m cell test as draw_sample.py
  floodplain      DEM at or below 150 m, slope at or below 2 degrees
  clear sky       SCL clear, dark or unclassified, no SCL cloud within 100 m
  image screen    the cloud and haze rules of draw_sample.py

Candidates are taken in random order until 60 pass the screen. The 7 earlier
points are a simple random sample of the same ground, so both sets can be
pooled for that part. The top-up points are marked batch "topup" in the key.
estimate_accuracy.py leaves them out, since they come from one part of their
stratum only; floodplain_layer.py uses them for the 150 m and 100 m
floodplains, which contain the ground they were drawn from, and leaves them
out for 200 m, which does not.

New points continue the numbering, P0551 onward, are added to points_key.csv
and labels.csv, and get chips like the rest. Rejected candidates go to
screened_out.csv with batch "topup". Run once; it refuses if a top-up exists.

A second top-up (REGISTER V-01)
-------------------------------
Land near flood holds 624,310 ha of the floodplain and only 44 readable
points, and carries 96% of the headline's variance. --second draws 150 more
there, inside the 150 m floodplain, under the same rules, as batch "topup2",
P0611 onward. Every script that leaves top-up points out of whole-stratum
estimates treats any batch starting "topup" the same way.

Usage
-----
    python src\\topup_sample.py              # the first top-up, already drawn
    python src\\topup_sample.py --second     # land near flood, V-01
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clear_sky import MAP, RAW, SCL_TIF, UPPER, strata_of            # noqa: E402
from draw_sample import (CELL, ELIGIBLE_SCL, NAMES, OVERDRAW, SAMPLE,  # noqa: E402
                         cut_chips, near_flood_mask, screen_candidates)
from estimate_accuracy import DEM_DIR, slope_degrees                   # noqa: E402
from floodplain_layer import CUTOFFS, MAIN, cloud_near_window          # noqa: E402

# batch: (stratum, points, seed); stratum 7 is land far from flood, 6 near
BATCHES = {"topup": (7, 60, 20261015), "topup2": (6, 150, 20261017)}
BATCH = "topup"
STRATUM, N_TOPUP, SEED = BATCHES[BATCH]
STRATUM_NAME = NAMES[STRATUM]


def draw_candidates(scl):
    rng = np.random.default_rng(SEED)
    e_max, s_max = CUTOFFS[MAIN]
    n_keep = int(N_TOPUP * OVERDRAW) + 10
    keys_all, flat_all = np.empty(0), np.empty(0, "int64")
    tiles = []
    for f in sorted(DEM_DIR.glob("India_dem_20m_*_*.tif")):
        # the default DEM cache only; a resampling test keeps its own tiles
        # in the same folder under a longer name (refine_scene.py)
        m = re.fullmatch(r"India_dem_20m_(\d+)_(\d+)\.tif", f.name)
        if m:
            tiles.append((int(m.group(1)), int(m.group(2)), f))

    with rasterio.open(MAP) as ref, rasterio.open(RAW) as raw, \
            rasterio.open(UPPER) as up:
        res = abs(ref.transform.a)
        print("  marking land within about 1 km of flood ...")
        near = near_flood_mask(ref, up)
        print(f"  finding floodplain {STRATUM_NAME} under clear sky ...")
        area_px = 0
        for ty, tx, f in tiles:
            r0, c0 = ty * 2048, tx * 2048
            r1, c1 = min(r0 + 2048, ref.height), min(c0 + 2048, ref.width)
            if r0 >= r1 or c0 >= c1:
                continue
            with rasterio.open(f) as dem:
                elev_t = dem.read(1).astype("float32")
                slope_t = slope_degrees(elev_t, abs(dem.transform.a))
                ro = round((dem.transform.f - (ref.transform.f - r0 * res)) / res)
                co = round((ref.transform.c + c0 * res - dem.transform.c) / res)
            h, w = r1 - r0, c1 - c0
            elev = elev_t[ro:ro + h, co:co + w]
            slope = slope_t[ro:ro + h, co:co + w]
            if elev.shape != (h, w):
                continue
            win = Window(c0, r0, w, h)
            s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                          up.read(1, window=win))
            nb = near[np.ix_(np.arange(r0, r1) // CELL, np.arange(c0, c1) // CELL)]
            s[(s == 6) & ~nb] = 7
            ok = (np.isin(scl[r0:r1, c0:c1], ELIGIBLE_SCL)
                  & ~cloud_near_window(scl, r0, r1, c0, c1))
            sel = ((s == STRATUM) & ok & np.isfinite(elev)
                   & (elev <= e_max) & (slope <= s_max))
            idx = np.flatnonzero(sel)
            area_px += idx.size
            if idx.size == 0:
                continue
            keys = rng.random(idx.size)
            if idx.size > n_keep:
                pick = np.argpartition(keys, n_keep)[:n_keep]
                keys, idx = keys[pick], idx[pick]
            rr, cc = np.divmod(idx, w)
            flat = (rr + r0).astype("int64") * ref.width + (cc + c0)
            keys_all = np.concatenate([keys_all, keys])
            flat_all = np.concatenate([flat_all, flat])
            if keys_all.size > n_keep:
                pick = np.argpartition(keys_all, n_keep)[:n_keep]
                keys_all, flat_all = keys_all[pick], flat_all[pick]

        to_ll = Transformer.from_crs(ref.crs.to_string(), "EPSG:4326",
                                     always_xy=True)
        cands = []
        for f in flat_all[np.argsort(keys_all)]:
            row, col = divmod(int(f), ref.width)
            x, y = ref.xy(row, col)
            lon, lat = to_ll.transform(x, y)
            one = Window(col, row, 1, 1)
            cands.append(dict(
                stratum=STRATUM_NAME, row=row, col=col,
                x=round(x, 1), y=round(y, 1), lon=round(lon, 6), lat=round(lat, 6),
                map_class=int(ref.read(1, window=one)[0, 0]),
                raw_class=int(raw.read(1, window=one)[0, 0]),
                upper_class=int(up.read(1, window=one)[0, 0]),
                scl_class=int(scl[row, col]), batch=BATCH))
        print(f"  {area_px * res * res / 1e4:,.0f} ha of such ground before the "
              f"image screen; {len(cands)} candidates kept")
        return cands, ref.crs


def main():
    global BATCH, STRATUM, N_TOPUP, SEED, STRATUM_NAME
    ap = argparse.ArgumentParser()
    ap.add_argument("--second", action="store_true",
                    help="the V-01 top-up of land near flood")
    BATCH = "topup2" if ap.parse_args().second else "topup"
    STRATUM, N_TOPUP, SEED = BATCHES[BATCH]
    STRATUM_NAME = NAMES[STRATUM]
    print("=" * 78)
    print(f"TOP-UP SAMPLE, {BATCH}: FLOODPLAIN {STRATUM_NAME.upper()}")
    print("=" * 78)
    key_path, sheet_path = SAMPLE / "points_key.csv", SAMPLE / "labels.csv"
    with open(key_path, encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    if any(r.get("batch") == BATCH for r in key):
        sys.exit(f"batch {BATCH} is already in points_key.csv; nothing done")
    with open(sheet_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        sheet_fields, sheet = reader.fieldnames, list(reader)

    with rasterio.open(SCL_TIF) as f:
        scl = f.read(1)
    cands, crs = draw_candidates(scl)
    taken = {(int(r["row"]), int(r["col"])) for r in key}
    cands = [c for c in cands if (c["row"], c["col"]) not in taken]
    points, rejected, tested = screen_candidates({STRATUM: cands},
                                                 {STRATUM: N_TOPUP}, crs)

    if not points:
        sys.exit("no candidate passed; nothing written")
    start = max(int(r["point_id"][1:]) for r in key) + 1
    for n, p in enumerate(points):
        p["point_id"] = f"P{start + n:04d}"
    for r in key:
        r.setdefault("batch", "main")
        r["batch"] = r["batch"] or "main"
    fields = list(key[0].keys())
    if "batch" not in fields:
        fields.append("batch")
    with open(key_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(key + points)
    with open(sheet_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sheet_fields)
        w.writeheader()
        w.writerows(sheet)
        for p in points:
            w.writerow({"point_id": p["point_id"], "lon": p["lon"], "lat": p["lat"],
                        "label": "", "confidence": "", "note": ""})

    out_path = SAMPLE / "screened_out.csv"
    with open(out_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        out_fields, out_rows = list(reader.fieldnames), list(reader)
    if "batch" not in out_fields:
        out_fields.append("batch")
    for r in out_rows:
        r["batch"] = r.get("batch") or "main"
    for r in rejected:
        r["batch"] = BATCH
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows + rejected)

    with open(SAMPLE / "draw_log.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  {BATCH}  seed "
                 f"{SEED}  {STRATUM_NAME}, floodplain {MAIN}  "
                 f"{tested.get(STRATUM, 0)} tested, {len(rejected)} screened out, "
                 f"{len(points)} points, P{start:04d} onward\n")
    print(f"\n  {len(points)} points added as P{start:04d} to "
          f"P{start + len(points) - 1:04d}; {len(rejected)} screened out")
    cut_chips(points, crs)
    print("\n  next: python src\\label_tool.py, which starts at the first new point")


if __name__ == "__main__":
    main()
