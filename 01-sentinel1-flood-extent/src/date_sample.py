"""
RS-01 / validation of the 7 and 31 August maps (REVIEW F-01, F-02). Draws a
stratified random sample of each map inside Landsat clear sky, cuts a chip
for each point, and turns the labels into accuracy figures and a flood area.

landsat_clear_sky.py found that the nearest Landsat scenes see a fair share
of both maps under clear sky: 66% of the 7 August map's flood in the Landsat 7
scene of 4 August, and 38% of the 31 August map's flood in the Landsat 8
scene of 28 August. No Sentinel-2 scene near either date is usable. So each
map is checked the way draw_sample.py checked 12 August, with Landsat as the
reference image.

Reference scenes
----------------
  7 August map     Landsat 7, 4 August, three days before the radar
  31 August map    Landsat 8, 28 August, three days before the radar

On 3 August, Landsat 8 sees only 31% of the 7 August flood under clear sky,
so Landsat 7 is used despite its scan-line gaps. --scene-date picks another
day; landsat_clear_sky.py must have written that day's QA raster first.

These checks are weaker than the 12 August one in two ways, and the write-up
has to carry both:

  the gap     three days against 20 hours. The flood was receding through
              August, so the image probably shows more water than the radar
              saw. That would push the estimated flood area and the user's
              accuracy up and the producer's accuracy down. How far is not
              known.
  the pixel   Landsat pixels are 30 m against the map's 20 m. The 20 m cell
              sits inside one Landsat pixel or across two, so cells at a
              water edge are harder to call.

Strata
------
The seven of draw_sample.py, read from that date's maps:

  map      India_water_20m_<date>_refined.tif     -18.75 dB, as published
  raw      India_water_20m_<date>.tif             before refinement
  upper    India_water_20m_<date>am_refined.tif   -17.75 dB

Where points can fall
---------------------
On pixels the scene's QA band calls clear, meaning seen and carrying none of
the bits for cloud, dilated cloud, cirrus or cloud shadow, with no such bit
within 100 m. The QA raster is the one landsat_clear_sky.py put on the map
grid, which takes the first scene of the day, in order of scene id, that saw
each pixel. The chips use that same scene.

Each candidate is then screened on the image, as in draw_sample.py, using
Landsat surface reflectance within 100 m of the point. It is rejected if two
or more pixels have blue above 0.15 and blue at least 0.95 of red, or if the
median blue is above 0.085 with median blue over red above 0.90. The cutoffs
are the 12 August ones, fixed before this draw. Two 30 m pixels, 1,800 m2,
stand in for the five 10 m pixels used there, since one bright Landsat pixel
can be a cluster of roofs. Scan-line gaps are left out of the screen.

Areas
-----
One pass over the grid, tile by tile with the nearest DEM, counts mapped and
eligible hectares per stratum over the whole map, the 150 m floodplain of
floodplain_layer.py, and all ground at or below 150 m. Eligible hectares are
then scaled by the share of tested candidates the screen accepted, inside each
domain where ten or more were tested there, and over the whole stratum
otherwise.

The estimate
------------
score_map.py's estimator (Stehman 2014), for the map and the -17.75 dB map,
over the same four scopes: the floodplain, the whole map, ground at or below
150 m that the DEM calls sloped, and ground above 150 m. Each is given for
the clear part, which needs no assumption about cloud, and for the whole,
which stretches clear-sky rates over cloudy ground. Reference flood is W, or
W or V, off JRC permanent water.

The draw records a SHA-256 digest of each map and of the QA raster in
rasters.csv, and the estimate stops if any of them has changed since.

Outputs
-------
Under results/validation/sample_<date>/, committed:
  points_key.csv  labels.csv  strata.csv  screened_out.csv  rasters.csv
  draw_log.txt  LABELLING.txt
  after labelling: estimates.csv, strata_estimates.csv, labels_by_stratum.csv,
                   zero_hit_bounds.csv
Under data/validation/chips_<date>/, not committed: one image per point

Usage
-----
    python src\\date_sample.py draw --map-date 2016-08-07      # draw, then chips
    python src\\date_sample.py chips --map-date 2016-08-07     # resume chips
    python src\\date_sample.py estimate --map-date 2016-08-07  # after labelling

Labelling, blind as before:
    python src\\label_tool.py --sheet sample_20160807\\labels.csv --chips chips_20160807 --simple
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.errors import WindowError
from rasterio.windows import Window
from scipy.ndimage import maximum_filter
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BBOX, DATA, GSW_PERMANENT_MIN                       # noqa: E402
from clear_sky import FLOOD, FULL, MPC, OUT, strata_of                # noqa: E402
from draw_sample import (CELL, FALSE_TOPS, NAMES, OVERDRAW,           # noqa: E402
                         SCREEN_BLUE, SCREEN_HAZE_BLUE, SCREEN_HAZE_WHITE,
                         SCREEN_WHITE, TRUE_TOPS, near_flood_mask, stretch)
from estimate_accuracy import (DEM_DIR, EDGE, IN_MAP, label_counts,   # noqa: E402
                               occurrence_at, slope_degrees, stratum_stats,
                               terrain_at, write_csv)
from floodplain_layer import CUTOFFS, LOW, MAIN, MIN_TESTED            # noqa: E402
from landsat_clear_sky import CLOUDY_BITS, UNSEEN, WORK                # noqa: E402
from score_map import print_bounds, score, zero_hit_bounds             # noqa: E402

# Planetary Computer answers 503 when busy. GDAL then retries on its own,
# waiting a little longer each time, before the read counts as failed.
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "5")

SCENES = {"2016-08-07": "2016-08-04", "2016-08-31": "2016-08-28"}
SEEDS = {"2016-08-07": 20261023, "2016-08-31": 20261024}
PREFIX = {"2016-08-07": "A", "2016-08-31": "B"}     # P is the 12 August sample

# Points per stratum, about 300 per date. Flood and land near flood carry the
# accuracy; land far from flood is mostly hills under cloud on these dates.
ALLOCATION = {1: 60, 2: 20, 3: 45, 4: 35, 5: 20, 6: 80, 7: 40}

TILE = 2048                          # DEM tile size on the map grid
CLOUD_BUFFER_PX = 5                  # 100 m at 20 m
SCREEN_RADIUS_M = 100
SCREEN_CORE_PX = 2                   # 30 m pixels, see the docstring
SR_SCALE, SR_OFFSET = 0.0000275, -0.2
CLOSE_M, CONTEXT_M = 640, 2560
MAPS = {"-18.75 dB": "map_class", "-17.75 dB": "upper_class"}
LETTERS = {"W only": ("W",), "W or V": ("W", "V")}
DOMAINS = {"whole": None, "floodplain": CUTOFFS[MAIN], "low": CUTOFFS[LOW]}


def paths(map_date, scene):
    tag = map_date.replace("-", "")
    return dict(
        tag=tag, scene=scene,
        map=FULL / f"India_water_20m_{tag}_refined.tif",
        raw=FULL / f"India_water_20m_{tag}.tif",
        upper=FULL / f"India_water_20m_{tag}am_refined.tif",
        qa=WORK / f"landsat_qa_{scene.replace('-', '')}_20m.tif",
        sample=OUT / f"sample_{tag}",
        chips=DATA / "validation" / f"chips_{tag}")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dem_tiles():
    """The nearest-DEM tiles the floodplain is defined on (C-31)."""
    tiles = {}
    for f in DEM_DIR.glob("India_dem_20m_*_*.tif"):
        m = re.fullmatch(r"India_dem_20m_(\d+)_(\d+)\.tif", f.name)
        if m:
            tiles[(int(m.group(1)), int(m.group(2)))] = f
    return tiles


def eligible_window(qa_ds, r0, r1, c0, c1):
    """QA clear, with no cloudy bit within CLOUD_BUFFER_PX."""
    b = CLOUD_BUFFER_PX
    a0, a1 = max(0, r0 - b), min(qa_ds.height, r1 + b)
    b0, b1 = max(0, c0 - b), min(qa_ds.width, c1 + b)
    qa = qa_ds.read(1, window=Window(b0, a0, b1 - b0, a1 - a0))
    cloudy = (qa != UNSEEN) & ((qa & CLOUDY_BITS) != 0)
    y, x = np.ogrid[-b:b + 1, -b:b + 1]
    near = maximum_filter(cloudy, footprint=x * x + y * y <= b * b)
    sl = (slice(r0 - a0, r1 - a0), slice(c0 - b0, c1 - b0))
    q = qa[sl]
    return (q != UNSEEN) & ((q & CLOUDY_BITS) == 0) & ~near[sl]


# ------------------------------------------------------------------ draw
def grid_pass(P, rng):
    """Hectares per stratum and domain, and the candidates per stratum."""
    tiles = dem_tiles()
    mapped = {d: np.zeros(8, "int64") for d in DOMAINS}
    eligible = {d: np.zeros(8, "int64") for d in DOMAINS}
    best = {k: (np.empty(0), np.empty(0, "int64")) for k in ALLOCATION}
    with rasterio.open(P["map"]) as ref, rasterio.open(P["raw"]) as raw, \
            rasterio.open(P["upper"]) as up, rasterio.open(P["qa"]) as qa_ds:
        for d in (raw, up, qa_ds):
            if (d.shape, d.transform) != (ref.shape, ref.transform):
                sys.exit(f"{Path(d.name).name} is not on the map's grid")
        need = sorted((ty, tx) for ty in range(-(-ref.height // TILE))
                      for tx in range(-(-ref.width // TILE)))
        missing = [t for t in need if t not in tiles]
        if missing:
            sys.exit(f"DEM tiles missing for {missing[:5]}; run refine_scene.py "
                     "with --resample-dem nearest first")
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        res = abs(ref.transform.a)
        print("  marking land within about 1 km of flood ...")
        near = near_flood_mask(ref, up)
        print(f"  reading {len(need)} tiles ...")
        for n, (ty, tx) in enumerate(need, 1):
            r0, c0 = ty * TILE, tx * TILE
            r1, c1 = min(r0 + TILE, ref.height), min(c0 + TILE, ref.width)
            h, w = r1 - r0, c1 - c0
            with rasterio.open(tiles[(ty, tx)]) as dem:
                elev_t = dem.read(1).astype("float32")
                if dem.nodata is not None:
                    elev_t[elev_t == dem.nodata] = np.nan
                slope_t = slope_degrees(elev_t, abs(dem.transform.a))
                ro = round((dem.transform.f - (ref.transform.f - r0 * res)) / res)
                co = round((ref.transform.c + c0 * res - dem.transform.c) / res)
            elev = elev_t[ro:ro + h, co:co + w]
            slope = slope_t[ro:ro + h, co:co + w]
            if elev.shape != (h, w):
                sys.exit(f"{tiles[(ty, tx)].name} does not cover its map window")
            win = Window(c0, r0, w, h)
            s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                          up.read(1, window=win))
            nb = near[np.ix_(np.arange(r0, r1) // CELL, np.arange(c0, c1) // CELL)]
            s[(s == 6) & ~nb] = 7
            ok = eligible_window(qa_ds, r0, r1, c0, c1)
            with np.errstate(invalid="ignore"):
                for dname, cut in DOMAINS.items():
                    if cut is None:
                        dom = np.ones((h, w), bool)
                    else:
                        dom = (elev <= cut[0]) & (slope <= cut[1])
                    mapped[dname] += np.bincount(s[dom], minlength=8)
                    eligible[dname] += np.bincount(s[dom & ok], minlength=8)
            for k, n_plan in ALLOCATION.items():
                keep = int(n_plan * OVERDRAW) + 10
                idx = np.flatnonzero((s == k) & ok)
                if idx.size == 0:
                    continue
                keys = rng.random(idx.size)
                if idx.size > keep:
                    sel = np.argpartition(keys, keep)[:keep]
                    keys, idx = keys[sel], idx[sel]
                rr, cc = np.divmod(idx, w)
                flat = (rr + r0).astype("int64") * ref.width + (cc + c0)
                k_all = np.concatenate([best[k][0], keys])
                i_all = np.concatenate([best[k][1], flat])
                if k_all.size > keep:
                    sel = np.argpartition(k_all, keep)[:keep]
                    k_all, i_all = k_all[sel], i_all[sel]
                best[k] = (k_all, i_all)
            if n % 10 == 0 or n == len(need):
                print(f"    {n}/{len(need)}")
    return mapped, eligible, best, px_ha


def candidates(P, best):
    """Candidates per stratum in their random order, with what lies under them."""
    e_fp, s_fp = CUTOFFS[MAIN]
    e_low = CUTOFFS[LOW][0]
    cands = {k: [] for k in ALLOCATION}
    with rasterio.open(P["map"]) as ref, rasterio.open(P["raw"]) as raw, \
            rasterio.open(P["upper"]) as up, rasterio.open(P["qa"]) as qa_ds:
        to_ll = Transformer.from_crs(ref.crs.to_string(), "EPSG:4326",
                                     always_xy=True)
        for k in ALLOCATION:
            keys, flat = best[k]
            for f in flat[np.argsort(keys)]:
                row, col = divmod(int(f), ref.width)
                x, y = ref.xy(row, col)
                lon, lat = to_ll.transform(x, y)
                one = Window(col, row, 1, 1)
                cands[k].append(dict(
                    code=k, stratum=NAMES[k], row=row, col=col,
                    x=round(x, 1), y=round(y, 1),
                    lon=round(lon, 6), lat=round(lat, 6),
                    map_class=int(ref.read(1, window=one)[0, 0]),
                    raw_class=int(raw.read(1, window=one)[0, 0]),
                    upper_class=int(up.read(1, window=one)[0, 0]),
                    qa_value=int(qa_ds.read(1, window=one)[0, 0])))
        crs = ref.crs
    every = [c for k in ALLOCATION for c in cands[k]]
    elev, slope = terrain_at([c["x"] for c in every], [c["y"] for c in every])
    for c, e, s in zip(every, elev, slope):
        fin = bool(np.isfinite(e) and np.isfinite(s))
        c["elevation_m"] = round(float(e), 1) if fin else ""
        c["slope_deg"] = round(float(s), 2) if fin else ""
        c["in_floodplain"] = "yes" if fin and e <= e_fp and s <= s_fp else "no"
        c["low_ground"] = "yes" if fin and e <= e_low else "no"
    return cands, crs


# ------------------------------------------------------- Landsat reading
def find_scenes(day):
    """Landsat 7 and 8 scenes of one day, in the order the QA mosaic used."""
    client = Client.open(MPC)
    items = sorted(client.search(collections=["landsat-c2-l2"], bbox=BBOX,
                                 datetime=day).items(), key=lambda i: i.id)
    return [i for i in items if i.properties.get("platform", "").lower()
            in ("landsat-7", "landsat-8")]


def read_native(href, x, y, half, crs_from):
    """Native pixels covering (x - half, y - half) to (x + half, y + half), and
    their extent in metres from the point, so the point can be marked exactly
    wherever it falls inside a 30 m pixel. Outside the scene reads as 0, fill."""
    with rasterio.open(planetary_computer.sign(href)) as src:
        if src.crs != crs_from:
            x, y = Transformer.from_crs(crs_from.to_string(), src.crs.to_string(),
                                        always_xy=True).transform(x, y)
        t = src.transform
        c0 = math.floor((x - half - t.c) / t.a)
        c1 = math.ceil((x + half - t.c) / t.a)
        r0 = math.floor((y + half - t.f) / t.e)
        r1 = math.ceil((y - half - t.f) / t.e)
        out = np.zeros((r1 - r0, c1 - c0), src.dtypes[0])
        try:
            inside = Window(c0, r0, c1 - c0, r1 - r0).intersection(
                Window(0, 0, src.width, src.height))
            d = src.read(1, window=inside)
            ro, co = int(inside.row_off) - r0, int(inside.col_off) - c0
            out[ro:ro + d.shape[0], co:co + d.shape[1]] = d
        except WindowError:
            pass
        left, top = t.c + c0 * t.a - x, t.f + r0 * t.e - y
        extent = (left, left + (c1 - c0) * t.a, top + (r1 - r0) * t.e, top)
    return out, extent


def centres(arr, extent):
    """Distance in metres from the point to each pixel centre."""
    h, w = arr.shape
    left, right, bottom, top = extent
    xs = left + (np.arange(w) + 0.5) * (right - left) / w
    ys = top - (np.arange(h) + 0.5) * (top - bottom) / h
    return np.hypot(*np.meshgrid(xs, ys))


def reflectance(dn):
    return np.where(dn > 0, dn.astype("float32") * SR_SCALE + SR_OFFSET, 0.0)


def pixel_at(href, x, y, crs_from):
    """The one pixel holding (x, y); 1, fill, outside the scene."""
    with rasterio.open(planetary_computer.sign(href)) as src:
        if src.crs != crs_from:
            x, y = Transformer.from_crs(crs_from.to_string(), src.crs.to_string(),
                                        always_xy=True).transform(x, y)
        row, col = src.index(x, y)
        if not (0 <= row < src.height and 0 <= col < src.width):
            return 1
        return int(src.read(1, window=Window(col, row, 1, 1))[0, 0])


def scene_at(items, feet, c, crs):
    """The first scene, by id, that saw the point, and its QA value there."""
    here = Point(c["lon"], c["lat"])
    for g, it in zip(feet, items):
        if g.contains(here):
            qa = pixel_at(it.assets["qa_pixel"].href, c["x"], c["y"], crs)
            if qa & 1 == 0:
                return it, qa
    return None, None


def screen_one(item, c, crs):
    half = SCREEN_RADIUS_M + 30
    blue, ext = read_native(item.assets["blue"].href, c["x"], c["y"], half, crs)
    red, _ = read_native(item.assets["red"].href, c["x"], c["y"], half, crs)
    keep = (centres(blue, ext) <= SCREEN_RADIUS_M) & (blue > 0) & (red > 0)
    if not keep.any():
        return "no data", dict(core_px=0, blue_median="", white_median="",
                               reason="no data")
    b, r = reflectance(blue[keep]), reflectance(red[keep])
    white = b / np.maximum(r, 1e-4)
    core = int(((b > SCREEN_BLUE) & (white > SCREEN_WHITE)).sum())
    b50, w50 = float(np.median(b)), float(np.median(white))
    reason = ("cloud" if core >= SCREEN_CORE_PX else
              "haze" if b50 > SCREEN_HAZE_BLUE and w50 > SCREEN_HAZE_WHITE
              else "")
    return reason, dict(core_px=core, blue_median=round(b50, 4),
                        white_median=round(w50, 3), reason=reason)


def screen_candidates(cands, crs, items):
    feet = [shape(it.geometry) for it in items]
    points, tested = [], []
    print("  screening candidates on the image ...")
    for k, n in ALLOCATION.items():
        got = t_k = 0
        for c in cands[k]:
            if got >= n:
                break
            result, err = None, None
            for _ in range(2):                 # one retry for a dropped read
                try:
                    item, qa = scene_at(items, feet, c, crs)
                    if item is None:
                        result = ("not seen", dict(reason="not seen"))
                    elif qa & CLOUDY_BITS:
                        result = ("cloud in QA", dict(reason="cloud in QA"))
                    else:
                        result = screen_one(item, c, crs)
                        c["scene_id"] = item.id
                    break
                except Exception as exc:
                    err = exc
            if result is None:
                print(f"    a candidate in {NAMES[k]} could not be read "
                      f"({type(err).__name__}); skipped")
                continue
            reason, stats = result
            t_k += 1
            tested.append({**c, **stats, "reason": reason})
            if not reason:
                points.append(c)
                got += 1
        print(f"    {NAMES[k]:<22} {got:>4} accepted of {t_k} tested")
        if got < n:
            print(f"    only {got} of {n} found; raise OVERDRAW and redraw")
    return points, tested


def accept_rate(tested, k, flag):
    """Share of tested candidates accepted, inside a domain where ten or more
    were tested there, over the whole stratum otherwise."""
    every = [c for c in tested if c["code"] == k]
    some = [c for c in every if flag is None or c[flag] == "yes"]
    use = some if len(some) >= MIN_TESTED else every
    return sum(1 for c in use if not c["reason"]) / len(use) if use else 1.0


# ------------------------------------------------------------------ rules
RULES = """\
Labelling rules for the {date_long} accuracy sample

Each chip shows one point. Label the 20 m cell inside the small square at the
centre of the close-up panels, judged on the {platform} image of {scene_long},
about {scene_time} UTC. The radar image behind the map was taken {days}
days later.

Panels
  1  false colour close-up, 640 m wide: shortwave infrared, near infrared, red
  2  true colour close-up, same area
  3  false colour context, 2.56 km wide; the box marks the close-up

Landsat pixels are 30 m, so they show as blocks a little larger than the
square. The square sits inside one pixel or across two; judge what covers most
of it.{stripes}

In false colour, open water is blue: deep navy when clear, bright blue when
silty, as a flooded river usually is. Vegetation is green, and a flooded crop
often shows as green mixed with blue. Bare or dry soil is pink to magenta, wet
soil darker and bluer than dry soil. Haze shows as a pale wash over everything.

Label, one letter in the label column of labels.csv
  W  open water covers most of the cell, flood or river or pond
  V  water visible through or between vegetation, such as a flooded paddy
     or a flooded crop canopy
  N  not water: land, crops, forest, soil, settlement
  C  cannot tell: cloud, shadow, haze, missing data, or too mixed to call

Confidence, one number in the confidence column
  1  sure    2  fairly sure    3  a guess

Rules
  * Judge the centre cell only. Mixed cells go to whatever covers most of it.
  * Use the note column for anything odd, such as a river bank or a cloud edge.
  * Do not open points_key.csv until every point has a label. It holds the map
    class, and seeing it would bias the labels.
  * Do not look at the radar map or the flood map while labelling.
"""

STRIPES = """

Landsat 7 has black diagonal stripes where its scan-line corrector failed in
2003. Points sit on pixels the scene saw, but if the square falls on a stripe,
label it C."""


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def draw(P, map_date):
    rng = np.random.default_rng(SEEDS[map_date])
    mapped, eligible, best, px_ha = grid_pass(P, rng)
    cands, crs = candidates(P, best)
    items = find_scenes(P["scene"])
    if not items:
        sys.exit(f"no Landsat 7 or 8 scene on {P['scene']}")
    points, tested = screen_candidates(cands, crs, items)
    order = rng.permutation(len(points))
    points = [points[i] for i in order]
    for n, p in enumerate(points, 1):
        p["point_id"] = f"{PREFIX[map_date]}{n:04d}"

    out = P["sample"]
    out.mkdir(parents=True, exist_ok=True)
    key_fields = ["point_id", "stratum", "lon", "lat", "x", "y", "row", "col",
                  "map_class", "raw_class", "upper_class", "qa_value", "scene_id",
                  "elevation_m", "slope_deg", "in_floodplain", "low_ground"]
    with open(out / "points_key.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=key_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(points)
    with open(out / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["point_id", "lon", "lat", "label", "confidence", "note"])
        for p in points:
            w.writerow([p["point_id"], p["lon"], p["lat"], "", "", ""])
    with open(out / "screened_out.csv", "w", newline="", encoding="utf-8") as fh:
        f_out = ["stratum", "lon", "lat", "x", "y", "elevation_m", "slope_deg",
                 "in_floodplain", "low_ground", "core_px", "blue_median",
                 "white_median", "reason"]
        w = csv.DictWriter(fh, fieldnames=f_out, extrasaction="ignore")
        w.writeheader()
        w.writerows([c for c in tested if c["reason"]])

    print(f"\n  {'stratum':<22} {'mapped ha':>11} {'eligible ha':>12} "
          f"{'tested':>7} {'out':>5} {'screened ha':>12} {'n':>5}")
    rows = []
    for k, name in NAMES.items():
        row = dict(stratum=name, in_published_map="no" if k == EDGE else "yes")
        for dname, flag, pre in (("whole", None, ""),
                                 ("floodplain", "in_floodplain", "floodplain_"),
                                 ("low", "low_ground", "low_")):
            m_ha, e_ha = mapped[dname][k] * px_ha, eligible[dname][k] * px_ha
            rate = accept_rate(tested, k, flag)
            row[f"{pre}mapped_ha"] = round(m_ha, 1)
            row[f"{pre}eligible_ha"] = round(e_ha, 1)
            row[f"{pre}screened_eligible_ha"] = round(e_ha * rate, 1)
        t = sum(1 for c in tested if c["code"] == k)
        row.update(n_planned=ALLOCATION[k],
                   n_drawn=sum(1 for p in points if p["code"] == k),
                   n_tested=t,
                   n_screened_out=sum(1 for c in tested
                                      if c["code"] == k and c["reason"]))
        rows.append(row)
        print(f"  {name:<22} {row['mapped_ha']:>11,.0f} {row['eligible_ha']:>12,.0f} "
              f"{t:>7} {row['n_screened_out']:>5} "
              f"{row['screened_eligible_ha']:>12,.0f} {row['n_drawn']:>5}")
    write_csv(out / "strata.csv", rows)

    with open(out / "rasters.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["role", "file", "sha256", "scene_date"])
        for role in ("map", "raw", "upper", "qa"):
            w.writerow([role, P[role].name, digest(P[role]), P["scene"]])

    if not points:
        sys.exit("no point passed the screen; nothing to label")
    used = next(it for it in items if it.id == points[0]["scene_id"])
    platform = used.properties.get("platform", "").replace("landsat-", "Landsat ")
    when = used.datetime
    days = (date.fromisoformat(map_date) - date.fromisoformat(P["scene"])).days
    (out / "LABELLING.txt").write_text(RULES.format(
        date_long=long_date(map_date), platform=platform,
        scene_long=long_date(P["scene"]), scene_time=f"{when:%H:%M}", days=days,
        stripes=STRIPES if platform.endswith("7") else ""), encoding="utf-8")
    with open(out / "draw_log.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  map {map_date}  "
                 f"scene {P['scene']} ({len(items)} items)  seed "
                 f"{SEEDS[map_date]}  QA clear, no cloudy bit within "
                 f"{CLOUD_BUFFER_PX * 20} m  image screen core "
                 f"{SCREEN_CORE_PX} px of 30 m above {SCREEN_BLUE} at white "
                 f"{SCREEN_WHITE}, haze median {SCREEN_HAZE_BLUE} at "
                 f"{SCREEN_HAZE_WHITE}  "
                 f"{sum(1 for c in tested if c['reason'])} screened out  "
                 f"{len(points)} points  allocation {ALLOCATION}\n")
    check_flood_ha(P, rows)
    print(f"\n  {len(points)} points, seed {SEEDS[map_date]}, written to {out}")
    return points, crs, items


def check_flood_ha(P, rows):
    """The flood stratum must hold the hectares landsat_clear_sky.py counted."""
    f = OUT / f"landsat_clear_{P['tag']}.csv"
    if not f.exists():
        return
    with open(f, encoding="utf-8") as fh:
        want = next((float(r["flood_ha"]) for r in csv.DictReader(fh)
                     if r["scene_date"] == P["scene"]), None)
    have = next(r["mapped_ha"] for r in rows if r["stratum"] == NAMES[1])
    if want is not None:
        ok = abs(have - want) <= 2
        print(f"\n  check: flood stratum {have:,.0f} ha, landsat_clear_sky.py "
              f"counted {want:,.0f} ha{'' if ok else '  DIFFERENT'}")


# ------------------------------------------------------------------ chips
def cut_chips(P, points, crs, items):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    P["chips"].mkdir(parents=True, exist_ok=True)
    by_id = {it.id: it for it in items}
    todo = [p for p in points if not (P["chips"] / f"{p['point_id']}.png").exists()]
    print(f"\n  chips: {len(points) - len(todo)} already done, {len(todo)} to cut")
    failed = []
    for n, p in enumerate(todo, 1):
        item = by_id.get(p["scene_id"])
        if item is None:
            failed.append(p["point_id"])
            continue
        x, y = float(p["x"]), float(p["y"])
        near = wide = err = None
        for wait in (0, 30, 120):              # Planetary Computer drops reads
            time.sleep(wait)
            try:
                near = {b: read_native(item.assets[b].href, x, y, CLOSE_M / 2, crs)
                        for b in ("blue", "green", "red", "nir08", "swir22")}
                wide = {b: read_native(item.assets[b].href, x, y, CONTEXT_M / 2,
                                       crs) for b in ("red", "nir08", "swir22")}
                break
            except Exception as exc:
                err = exc
        if wide is None:
            failed.append(p["point_id"])
            print(f"  {p['point_id']} failed after three tries: "
                  f"{type(err).__name__}")
            continue

        def rgb(src, bands, tops):
            return stretch(np.dstack([reflectance(src[b][0]) for b in bands]), tops)

        panels = ((rgb(near, ("swir22", "nir08", "red"), FALSE_TOPS),
                   near["red"][1], CLOSE_M, "false colour, 640 m"),
                  (rgb(near, ("red", "green", "blue"), TRUE_TOPS),
                   near["red"][1], CLOSE_M, "true colour, 640 m"),
                  (rgb(wide, ("swir22", "nir08", "red"), FALSE_TOPS),
                   wide["red"][1], CONTEXT_M, "false colour, 2.56 km"))
        fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.8))
        for a, (img, ext, width, title) in zip(ax, panels):
            a.imshow(img, extent=ext, interpolation="nearest")
            a.set_xlim(-width / 2, width / 2)
            a.set_ylim(-width / 2, width / 2)
            a.set_title(title, fontsize=9)
            a.set_xticks([])
            a.set_yticks([])
        for a in ax[:2]:                       # the 20 m cell and a cross
            a.add_patch(Rectangle((-10, -10), 20, 20, fill=False,
                                  edgecolor="yellow", linewidth=1.2))
            for x0, x1, y0, y1 in ((-115, -35, 0, 0), (35, 115, 0, 0),
                                   (0, 0, -115, -35), (0, 0, 35, 115)):
                a.plot([x0, x1], [y0, y1], color="yellow", linewidth=1)
        ax[2].add_patch(Rectangle((-CLOSE_M / 2, -CLOSE_M / 2), CLOSE_M, CLOSE_M,
                                  fill=False, edgecolor="yellow", linewidth=1))
        fig.suptitle(f"{p['point_id']}   {p['lat']}, {p['lon']}", fontsize=10)
        fig.tight_layout()
        fig.savefig(P["chips"] / f"{p['point_id']}.png", dpi=110)
        plt.close(fig)
        if n % 25 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)}")
    if failed:
        print(f"\n  {len(failed)} chip(s) not cut: {', '.join(failed[:20])}"
              f"{' ...' if len(failed) > 20 else ''}. Run the chips step again.")


# --------------------------------------------------------------- estimate
def load_sample(P):
    with open(P["sample"] / "points_key.csv", encoding="utf-8") as fh:
        key = {r["point_id"]: r for r in csv.DictReader(fh)}
    with open(P["sample"] / "labels.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = key[r["point_id"]]
            p["label"] = (r.get("label") or "").strip().upper()[:1]
            p["confidence"] = (r.get("confidence") or "").strip()
    codes = {v: k for k, v in NAMES.items()}
    for p in key.values():
        p["code"] = codes[p["stratum"]]
        p["x"], p["y"] = float(p["x"]), float(p["y"])
    return list(key.values())


def load_areas(P):
    codes = {v: k for k, v in NAMES.items()}
    with open(P["sample"] / "strata.csv", encoding="utf-8") as fh:
        rows = {codes[r["stratum"]]: r for r in csv.DictReader(fh)}

    def pick(pre):
        return {k: dict(mapped=float(r[f"{pre}mapped_ha"]),
                        eligible=float(r[f"{pre}screened_eligible_ha"]))
                for k, r in rows.items()}

    def minus(a, b):
        return {k: dict(mapped=max(a[k]["mapped"] - b[k]["mapped"], 0.0),
                        eligible=max(a[k]["eligible"] - b[k]["eligible"], 0.0))
                for k in a}

    whole, plain, low = pick(""), pick("floodplain_"), pick("low_")
    return dict(whole=whole, floodplain=plain, sloped=minus(low, plain),
                above=minus(whole, low))


def check_rasters(P):
    with open(P["sample"] / "rasters.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if digest(P[r["role"]]) != r["sha256"]:
                sys.exit(f"{r['file']} has changed since the draw; the strata "
                         "no longer match it. Nothing written.")
    print("  check: the maps and the QA raster are the ones the draw used")


def estimate(P, map_date):
    check_rasters(P)
    points = load_sample(P)
    bad = [p for p in points if p["label"] not in ("", "W", "V", "N", "C")]
    if bad:
        sys.exit(f"unknown labels at {', '.join(p['point_id'] for p in bad[:10])}")
    blank = [p for p in points if p["label"] == ""]
    if blank:
        sys.exit(f"{len(blank)} of {len(points)} points have no label yet. "
                 "Finish labelling first.")
    occ = occurrence_at([p["x"] for p in points], [p["y"] for p in points])
    for p, o in zip(points, occ):
        p["permanent"] = bool(np.isfinite(o) and o >= GSW_PERMANENT_MIN)
        p["usable"] = p["label"] in ("W", "V", "N")
    areas = load_areas(P)
    scopes = {
        "floodplain": ([p for p in points if p["in_floodplain"] == "yes"],
                       areas["floodplain"]),
        "whole map": (points, areas["whole"]),
        "below 150 m, sloped": ([p for p in points if p["low_ground"] == "yes"
                                 and p["in_floodplain"] == "no"], areas["sloped"]),
        "above 150 m": ([p for p in points if p["low_ground"] == "no"],
                        areas["above"]),
    }
    for scope, (pts, ar) in scopes.items():
        for k in IN_MAP:
            n = sum(1 for p in pts if p["code"] == k and p["usable"])
            if n < 2 and ar[k]["eligible"] > 0:
                what = ("its share is taken as zero" if n == 0 else
                        "its share rests on that one point, with no variance")
                print(f"  {scope}: {NAMES[k]} has {n} readable point(s) for "
                      f"{ar[k]['eligible']:,.0f} clear ha; {what}")

    rows = []
    for mname, field in MAPS.items():
        flags = {p["point_id"]: int(p[field]) == FLOOD for p in points}
        for scope, (pts, ar) in scopes.items():
            for layer, lname in (("mapped", "whole"), ("eligible", "clear part")):
                for vname, letters in LETTERS.items():
                    for metric, val, se in score(pts, flags, ar, layer, letters):
                        rows.append(dict(map_date=map_date, map=mname, scope=scope,
                                         layer=lname, variant=vname, metric=metric,
                                         value=round(val, 4 if abs(val) < 2 else 0),
                                         se=round(se, 4 if abs(val) < 2 else 0)))

    strata_rows = []
    for vname, letters in LETTERS.items():
        def ref(p, letters=letters):
            return p["label"] in letters and not p["permanent"]
        st = stratum_stats(points, ref)
        for k, s in st.items():
            strata_rows.append(dict(
                variant=vname, stratum=NAMES[k], n_labelled=s["n"],
                n_unreadable=s["unreadable"], n_flood=s["flood"],
                flood_share=round(s["p"], 4) if s["n"] else "",
                se=round(math.sqrt(s["var"]), 4) if s["n"] > 1 else "",
                cp95_low=round(s["cp_low"], 4) if s["n"] else "",
                cp95_high=round(s["cp_high"], 4) if s["n"] else ""))
        a = areas["whole"][EDGE]
        e = st[EDGE]
        if e["n"]:
            for layer, lname in (("mapped", "whole"), ("eligible", "clear part")):
                se = (math.sqrt(a[layer] ** 2 * e["var"]) if e["n"] > 1
                      else float("nan"))
                rows.append(dict(map_date=map_date, map="", scope="swath edge",
                                 layer=lname, variant=vname,
                                 metric="real flood inside the swath-edge buffer, ha",
                                 value=round(a[layer] * e["p"]),
                                 se=round(se) if math.isfinite(se) else ""))

    out = P["sample"]
    bounds = [r for scope, (pts, ar) in scopes.items()
              for r in zero_hit_bounds(pts, ar, scope)]
    write_csv(out / "zero_hit_bounds.csv", bounds)
    write_csv(out / "estimates.csv", rows)
    write_csv(out / "strata_estimates.csv", strata_rows)
    write_csv(out / "labels_by_stratum.csv", label_counts(points))

    n_c = sum(1 for p in points if p["label"] == "C")
    print(f"\n  {len(points)} points, {n_c} unreadable (C), "
          f"{sum(1 for p in points if p['permanent'])} on JRC permanent water")
    print(f"\n  {'stratum':<22} {'n':>4} {'C':>4} {'flood':>6} {'share':>7} "
          f"{'95% interval':>16}")
    for r in strata_rows:
        if r["variant"] != "W only":
            continue
        ci = (f"{r['cp95_low']:.3f} to {r['cp95_high']:.3f}"
              if r["n_labelled"] else "")
        share = f"{r['flood_share']:.3f}" if r["n_labelled"] else "n/a"
        print(f"  {r['stratum']:<22} {r['n_labelled']:>4} {r['n_unreadable']:>4} "
              f"{r['n_flood']:>6} {share:>7} {ci:>16}")
    for scope in scopes:
        print(f"\n  {scope.upper()}, open water (W only), {len(scopes[scope][0])} points")
        for lname in ("clear part", "whole"):
            sel = {(r["map"], r["metric"]): r for r in rows if r["scope"] == scope
                   and r["layer"] == lname and r["variant"] == "W only"}
            g = sel[("-18.75 dB", "flood on the ground, ha")]
            print(f"    {lname:<11} on the ground {g['value']:>9,.0f} +/- "
                  f"{g['se']:,.0f} ha")
            for mname in MAPS:
                m = sel[(mname, "mapped flood, ha")]
                u = sel[(mname, "user's accuracy")]
                pr = sel[(mname, "producer's accuracy")]
                ua = ("n/a, no point in map flood here" if math.isnan(u["value"])
                      else f"{u['value']:.3f} +/- {u['se']:.3f}")
                print(f"      {mname:<10} mapped {m['value']:>9,.0f} ha   user "
                      f"{ua}   producer {pr['value']:.3f} +/- {pr['se']:.3f}")
    print_bounds(bounds)
    days = (date.fromisoformat(map_date) - date.fromisoformat(P["scene"])).days
    print(f"\n  The reference image is {days} days before the radar, with the")
    print("  flood receding, so it probably shows more water than the radar saw.")
    print("  That would bias flood on the ground and user's accuracy up and")
    print("  producer's accuracy down.")
    print(f"\n  wrote estimates.csv, strata_estimates.csv and labels_by_stratum.csv"
          f" to {out}")


# ------------------------------------------------------------------- main
def labelled(P):
    sheet = P["sample"] / "labels.csv"
    if not sheet.exists():
        return False
    with open(sheet, encoding="utf-8") as fh:
        return any((r.get("label") or "").strip() for r in csv.DictReader(fh))


def drawn_scene(P):
    with open(P["sample"] / "rasters.csv", encoding="utf-8") as fh:
        return next(csv.DictReader(fh))["scene_date"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["draw", "chips", "estimate"])
    ap.add_argument("--map-date", required=True, choices=sorted(SCENES))
    ap.add_argument("--scene-date", help="Landsat day to label on, draw only; "
                    "defaults to the one in the docstring")
    ap.add_argument("--redraw", action="store_true",
                    help="discard the existing sample and draw a new one")
    args = ap.parse_args()

    P = paths(args.map_date, args.scene_date or SCENES[args.map_date])
    key = P["sample"] / "points_key.csv"
    print("=" * 78)
    print(f"ACCURACY SAMPLE, {long_date(args.map_date).upper()} MAP, "
          "INSIDE LANDSAT CLEAR SKY")
    print("=" * 78)

    if args.step == "draw":
        for role in ("map", "raw", "upper", "qa"):
            if not P[role].exists():
                hint = (" run landsat_clear_sky.py for that map date first"
                        if role == "qa" else "")
                sys.exit(f"missing {P[role]};{hint}")
        if key.exists() and not args.redraw:
            sys.exit(f"{key} exists. Use the chips step to resume chips, or "
                     "--redraw to replace the sample.")
        if labelled(P):
            sys.exit("labels.csv already holds labels; a new draw would discard "
                     "them. Move labels.csv aside first if you mean it.")
        if P["chips"].exists() and any(P["chips"].iterdir()):
            k = 1
            while (P["chips"].parent / f"{P['chips'].name}_replaced_{k}").exists():
                k += 1
            P["chips"].rename(P["chips"].parent / f"{P['chips'].name}_replaced_{k}")
        points, crs, items = draw(P, args.map_date)
        cut_chips(P, points, crs, items)
    else:
        if not key.exists():
            sys.exit("no sample yet; run the draw step first")
        P = paths(args.map_date, drawn_scene(P))
        if args.step == "chips":
            with open(key, encoding="utf-8") as fh:
                points = list(csv.DictReader(fh))
            with rasterio.open(P["map"]) as ref:
                crs = ref.crs
            cut_chips(P, points, crs, find_scenes(P["scene"]))
        else:
            estimate(P, args.map_date)
            return
    print(f"\n  next: label with\n    python src\\label_tool.py --sheet "
          f"sample_{P['tag']}\\labels.csv --chips chips_{P['tag']} --simple")


if __name__ == "__main__":
    main()
