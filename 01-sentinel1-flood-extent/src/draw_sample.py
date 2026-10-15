"""
RS-01 / validation, step one. Draw a stratified random sample of the 12 August
map inside clear sky, and cut an image chip for each point so it can be
labelled by eye.

clear_sky.py showed that every stratum has thousands of hectares under clear
sky in the Sentinel-2A image of 12 August, 04:15 UTC, about 19.5 hours before
the radar. This script draws the points and prepares them for labelling. It
does not label anything and computes no accuracy; that comes after the labels.

Strata
------
The six strata of clear_sky.py, with land split by distance to flood, since
missed flood is far likelier next to mapped flood than in the hills:

  flood                   flood in the published map, -18.75 dB
  permanent water         permanent water in the published map
  upper threshold only    flood at -17.75 dB only
  removed by refinement   raw flood that the slope cut or the 1 ha clean-up removed
  swath edge              set to no data by the swath-edge buffer
  land near flood         other land within about 1 km of flood in either map
  land far from flood     the rest of the land

Every stratum except the swath edge is part of the published map, so together
they give its accuracy and a bias-adjusted area. The swath edge lies outside the
published map and is sampled only to test the buffer. Because the strata nest,
the same sample also serves the -17.75 dB map, where "upper threshold only"
counts as flood.

"About 1 km" is measured on 100 m cells: a 20 m pixel is near flood if its
100 m cell lies within ten cells of a cell holding any flood.

Where points can fall
---------------------
Only on pixels SCL calls clear (vegetation, bare, water) or dark or
unclassified, and only where no SCL cloud, cloud shadow or cirrus lies within
100 m. The distance rule exists because SCL misses cloud: in the first draw it
called a pixel inside a cloud bank bare soil, and 144 of 550 points had cloud
within 100 m. So the sample describes the part of the map under clear sky at
least 100 m from detected cloud. Applying it to the rest assumes cloud fell
independently of map error, and the write-up has to say so. Mapped and
eligible hectares per stratum are written out so the estimator can use either.
Each draw is logged in draw_log.txt.

SCL also misses cloud outright: the second draw put P0002 inside a cloud bank
with no SCL cloud near it. So every candidate is screened on the image itself
before it is accepted. Within 100 m of the point, it is rejected if

  five or more pixels have blue reflectance above 0.15 and blue at least 0.95
  of red, which is the colour of cloud, or
  the median blue is above 0.085 and the median blue over red above 0.90,
  which is haze

Sand bars are bright but redder than blue, so they pass; a village's bright
roofs are too few pixels to trip the first test. The cutoffs were chosen on
the second draw, before any labelling, by checking chips across the range.
Candidates are taken in random order until each stratum is full, so the
accepted points remain a simple random sample of the screened population, and
the share accepted estimates how much of the eligible area that population is.
Rejected candidates are listed in screened_out.csv.

Labelling blind
---------------
labels.csv lists the points in random order with no stratum and no map class,
so the map cannot steer the labels. The key, points_key.csv, holds both. Leave
it closed until every point is labelled.

Outputs
-------
Under results/validation/sample/, committed:
  points_key.csv      every point with its stratum, map classes and SCL class
  labels.csv          the sheet to fill in, one row per point
  strata.csv          mapped and eligible hectares and sample size per stratum
  screened_out.csv    candidates the image screen rejected
  draw_log.txt        every draw, with its rules and seed
  LABELLING.txt       the labelling rules
Under data/validation/chips/, not committed, since --chips-only rebuilds them:
  P0001.png           one image per point

Usage
-----
    python src\\draw_sample.py                # draw, then cut the chips
    python src\\draw_sample.py --chips-only   # resume chips after a break
    python src\\draw_sample.py --redraw       # discard the sample and draw again

Drawing takes a minute or two. The chips need about eight small reads from
Planetary Computer per point, so expect most of an hour for 550 points. The
chip step skips points already done, so it can be stopped and restarted.
Redraw only before any labelling has started.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.windows import Window, from_bounds
from scipy.ndimage import binary_dilation, maximum_filter
from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BBOX, DATA                                # noqa: E402
from clear_sky import (FLOOD, MAP, MPC, OUT, RAW, S2_DATE,   # noqa: E402
                       SCL_TIF, UPPER, strata_of)

SEED = 20261013
SAMPLE = OUT / "sample"
CHIPS = DATA / "validation" / "chips"

NAMES = {
    1: "flood",
    2: "permanent water",
    3: "upper threshold only",
    4: "removed by refinement",
    5: "swath edge",
    6: "land near flood",
    7: "land far from flood",
}

# Points per stratum. Land far from flood gets the most: it holds about nine
# tenths of the map, so even a small rate of missed flood there carries a large
# area, and zero hits in a few dozen points would bound that rate only loosely.
ALLOCATION = {1: 100, 2: 40, 3: 80, 4: 60, 5: 50, 6: 100, 7: 120}

ELIGIBLE_SCL = [2, 4, 5, 6, 7]       # dark, vegetation, bare, water, unclassified
CLOUD_SCL = [3, 8, 9, 10]            # shadow, cloud medium and high, cirrus
CLOUD_BUFFER_PX = 5                  # 100 m at 20 m: no cloud this close
CELL = 5                             # 20 m pixels per 100 m cell
NEAR_CELLS = 10                      # ten 100 m cells, about 1 km

SCREEN_RADIUS_M = 100                # image screen, see the docstring
SCREEN_BLUE, SCREEN_WHITE, SCREEN_CORE_PX = 0.15, 0.95, 5
SCREEN_HAZE_BLUE, SCREEN_HAZE_WHITE = 0.085, 0.90
OVERDRAW = 2.0                       # candidates kept per planned point

CLOSE_M = 640                        # close-up chip width, 64 px at 10 m
CONTEXT_M = 2560                     # context chip width


def near_flood_mask(ref, upper):
    """Coarse mask, one value per 100 m cell: within about 1 km of flood."""
    hc, wc = -(-ref.height // CELL), -(-ref.width // CELL)
    coarse = np.zeros((hc, wc), bool)
    step = CELL * 200
    for r0 in range(0, ref.height, step):
        win = Window(0, r0, ref.width, min(step, ref.height - r0))
        m = (ref.read(1, window=win) == FLOOD) | (upper.read(1, window=win) == FLOOD)
        h, w = m.shape
        pad = np.zeros((-(-h // CELL) * CELL, wc * CELL), bool)
        pad[:h, :w] = m
        cells = pad.reshape(pad.shape[0] // CELL, CELL, wc, CELL).any(axis=(1, 3))
        coarse[r0 // CELL:r0 // CELL + cells.shape[0]] = cells
    y, x = np.ogrid[-NEAR_CELLS:NEAR_CELLS + 1, -NEAR_CELLS:NEAR_CELLS + 1]
    disk = x * x + y * y <= NEAR_CELLS * NEAR_CELLS
    return binary_dilation(coarse, structure=disk)


def cloud_near(scl, r0, h):
    """True where SCL cloud, shadow or cirrus lies within CLOUD_BUFFER_PX."""
    b = CLOUD_BUFFER_PX
    a0, a1 = max(0, r0 - b), min(scl.shape[0], r0 + h + b)
    cloud = np.isin(scl[a0:a1], CLOUD_SCL)
    y, x = np.ogrid[-b:b + 1, -b:b + 1]
    near = maximum_filter(cloud, footprint=x * x + y * y <= b * b)
    return near[r0 - a0:r0 - a0 + h]


def draw(allocation):
    rng = np.random.default_rng(SEED)
    with rasterio.open(SCL_TIF) as s:
        scl = s.read(1)
    with rasterio.open(MAP) as ref, rasterio.open(RAW) as raw, \
            rasterio.open(UPPER) as up:
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        print("  marking land within about 1 km of flood ...")
        near = near_flood_mask(ref, up)

        mapped = np.zeros(8, "int64")
        eligible = np.zeros(8, "int64")
        best = {k: (np.empty(0), np.empty(0, "int64")) for k in allocation}
        step = CELL * 200
        print("  drawing ...")
        for r0 in range(0, ref.height, step):
            win = Window(0, r0, ref.width, min(step, ref.height - r0))
            s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                          up.read(1, window=win))
            h, w = s.shape
            nb = np.repeat(np.repeat(near[r0 // CELL:r0 // CELL + -(-h // CELL)],
                                     CELL, axis=0), CELL, axis=1)[:h, :w]
            s[(s == 6) & ~nb] = 7
            ok = np.isin(scl[r0:r0 + h], ELIGIBLE_SCL) & ~cloud_near(scl, r0, h)
            mapped += np.bincount(s.ravel(), minlength=8)
            eligible += np.bincount(s[ok], minlength=8)
            for k, n_plan in allocation.items():
                n = int(n_plan * OVERDRAW) + 10
                idx = np.flatnonzero((s == k) & ok)
                if idx.size == 0:
                    continue
                keys = rng.random(idx.size)
                if idx.size > n:
                    sel = np.argpartition(keys, n)[:n]
                    keys, idx = keys[sel], idx[sel]
                rows, cols = np.divmod(idx, w)
                flat = (rows + r0).astype("int64") * ref.width + cols
                k_all = np.concatenate([best[k][0], keys])
                i_all = np.concatenate([best[k][1], flat])
                if k_all.size > n:
                    sel = np.argpartition(k_all, n)[:n]
                    k_all, i_all = k_all[sel], i_all[sel]
                best[k] = (k_all, i_all)

        to_ll = Transformer.from_crs(ref.crs.to_string(), "EPSG:4326",
                                     always_xy=True)
        cands = {k: [] for k in allocation}
        for k in allocation:
            keys, flat = best[k]
            for f in flat[np.argsort(keys)]:
                row, col = divmod(int(f), ref.width)
                x, y = ref.xy(row, col)
                lon, lat = to_ll.transform(x, y)
                one = Window(col, row, 1, 1)
                cands[k].append(dict(
                    stratum=NAMES[k], row=row, col=col,
                    x=round(x, 1), y=round(y, 1),
                    lon=round(lon, 6), lat=round(lat, 6),
                    map_class=int(ref.read(1, window=one)[0, 0]),
                    raw_class=int(raw.read(1, window=one)[0, 0]),
                    upper_class=int(up.read(1, window=one)[0, 0]),
                    scl_class=int(scl[row, col]),
                ))
        crs = ref.crs

    points, rejected, tested = screen_candidates(cands, allocation, crs)
    order = rng.permutation(len(points))
    points = [points[i] for i in order]
    for n, p in enumerate(points, 1):
        p["point_id"] = f"P{n:04d}"

    SAMPLE.mkdir(parents=True, exist_ok=True)
    if CHIPS.exists() and any(CHIPS.iterdir()):
        k = 1
        while (CHIPS.parent / f"chips_replaced_{k}").exists():
            k += 1
        CHIPS.rename(CHIPS.parent / f"chips_replaced_{k}")
        print(f"  old chips moved to chips_replaced_{k}; delete it when you like")
    key_fields = ["point_id", "stratum", "lon", "lat", "x", "y", "row", "col",
                  "map_class", "raw_class", "upper_class", "scl_class"]
    with open(SAMPLE / "points_key.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=key_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(points)
    with open(SAMPLE / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["point_id", "lon", "lat", "label", "confidence", "note"])
        for p in points:
            w.writerow([p["point_id"], p["lon"], p["lat"], "", "", ""])
    with open(SAMPLE / "strata.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stratum", "in_published_map", "mapped_ha", "eligible_ha",
                    "eligible_pct", "n_planned", "n_drawn", "n_tested",
                    "n_screened_out", "screened_eligible_ha"])
        print(f"\n  {'stratum':<22} {'mapped ha':>11} {'eligible ha':>12} "
              f"{'tested':>7} {'out':>5} {'screened ha':>12} {'n':>5}")
        for k, name in NAMES.items():
            drawn = sum(1 for p in points if p["stratum"] == name)
            m_ha, e_ha = mapped[k] * px_ha, eligible[k] * px_ha
            t = tested.get(k, 0)
            out = sum(1 for p in rejected if p["stratum"] == name)
            s_ha = e_ha * (t - out) / t if t else 0.0
            w.writerow([name, "no" if k == 5 else "yes", round(m_ha),
                        round(e_ha), round(e_ha / m_ha * 100, 1) if m_ha else "",
                        allocation.get(k, 0), drawn, t, out, round(s_ha)])
            print(f"  {name:<22} {m_ha:>11,.0f} {e_ha:>12,.0f} {t:>7} {out:>5} "
                  f"{s_ha:>12,.0f} {drawn:>5}")
    with open(SAMPLE / "screened_out.csv", "w", newline="", encoding="utf-8") as fh:
        f_out = ["stratum", "lon", "lat", "x", "y", "core_px", "blue_median",
                 "white_median", "reason"]
        w = csv.DictWriter(fh, fieldnames=f_out, extrasaction="ignore")
        w.writeheader()
        w.writerows(rejected)
    (SAMPLE / "LABELLING.txt").write_text(RULES, encoding="utf-8")
    from datetime import datetime, timezone
    with open(SAMPLE / "draw_log.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  seed {SEED}  "
                 f"eligible SCL {ELIGIBLE_SCL}  no cloud within "
                 f"{CLOUD_BUFFER_PX * 20} m  image screen core "
                 f"{SCREEN_CORE_PX} px above {SCREEN_BLUE} at white "
                 f"{SCREEN_WHITE}, haze median {SCREEN_HAZE_BLUE} at "
                 f"{SCREEN_HAZE_WHITE}  {len(rejected)} screened out  "
                 f"{len(points)} points  allocation {allocation}\n")
    print(f"\n  {len(points)} points, seed {SEED}, written to {SAMPLE}")
    return points


RULES = """\
Labelling rules for the RS-01 accuracy sample

Each chip shows one point. Label the 20 m cell inside the small square at the
centre of the close-up panels, judged on the Sentinel-2A image of 12 August 2016,
04:15 UTC. The radar map is from 23:46 UTC the same day.

Panels
  1  false colour close-up, 640 m wide: shortwave infrared, near infrared, red
  2  true colour close-up, same area
  3  false colour context, 2.56 km wide; the box marks the close-up

In false colour, open water is blue: deep navy when clear, bright blue when
silty, as a flooded river usually is. Vegetation is green, and a flooded crop
often shows as green mixed with blue. Bare or dry soil is pink to magenta, wet
soil darker and bluer than dry soil. Haze shows as a pale wash over everything.

Label, one letter in the label column of labels.csv
  W  open water covers most of the cell, flood or river or pond
  V  water visible through or between vegetation, such as a flooded paddy
     or a flooded crop canopy
  N  not water: land, crops, forest, soil, settlement
  C  cannot tell: cloud, shadow, haze, or too mixed to call

Confidence, one number in the confidence column
  1  sure    2  fairly sure    3  a guess

Rules
  * Judge the centre cell only. Mixed cells go to whatever covers most of it.
  * Use the note column for anything odd, such as a river bank or a cloud edge.
  * Do not open points_key.csv until every point has a label. It holds the map
    class, and seeing it would bias the labels.
  * Do not look at the radar map or the flood map while labelling.
"""


def screen_one(item, x, y, crs):
    """Measure cloud and haze within SCREEN_RADIUS_M; a reason means reject."""
    off = scale_of(item)
    width = 2 * SCREEN_RADIUS_M
    px = width // 10
    b2 = (read_patch(item.assets["B02"].href, x, y, width, px, crs) + off) / 10000
    b4 = (read_patch(item.assets["B04"].href, x, y, width, px, crs) + off) / 10000
    yy, xx = np.mgrid[0:px, 0:px] - (px - 1) / 2
    disk = np.hypot(yy, xx) * 10 <= SCREEN_RADIUS_M
    b2, b4 = b2[disk], b4[disk]
    white = b2 / np.maximum(b4, 1e-4)
    core = int(((b2 > SCREEN_BLUE) & (white > SCREEN_WHITE)).sum())
    b50, w50 = float(np.median(b2)), float(np.median(white))
    reason = ("cloud" if core >= SCREEN_CORE_PX else
              "haze" if b50 > SCREEN_HAZE_BLUE and w50 > SCREEN_HAZE_WHITE
              else "")
    return reason, dict(core_px=core, blue_median=round(b50, 4),
                        white_median=round(w50, 3), reason=reason)


def screen_candidates(cands, allocation, crs):
    """Take candidates in their random order until each stratum is full."""
    items = find_items()
    feet = [(shape(it.geometry), it) for it in items]
    points, rejected, tested = [], [], {}
    print("  screening candidates on the image ...")
    for k, n in allocation.items():
        got = 0
        tested[k] = 0
        for c in cands[k]:
            if got >= n:
                break
            here = Point(c["lon"], c["lat"])
            item = next((it for g, it in feet if g.contains(here)), None)
            if item is None:
                continue
            result, err = None, None
            for _ in range(2):                 # one retry for a dropped read
                try:
                    result = screen_one(item, c["x"], c["y"], crs)
                    break
                except Exception as exc:
                    err = exc
            if result is None:
                print(f"    a candidate in {NAMES[k]} could not be read "
                      f"({type(err).__name__}); skipped")
                continue
            tested[k] += 1
            reason, stats = result
            if reason:
                rejected.append({**c, **stats})
            else:
                points.append(c)
                got += 1
        print(f"    {NAMES[k]:<22} {got:>4} accepted of {tested[k]} tested")
        if got < n:
            print(f"    only {got} of {n} found; raise OVERDRAW and redraw")
    return points, rejected, tested


def find_items():
    client = Client.open(MPC)
    items = list(client.search(collections=["sentinel-2-l2a"], bbox=BBOX,
                               datetime=S2_DATE).items())
    seen, keep = set(), []
    for it in sorted(items, key=lambda i: i.id):
        tile = it.properties.get("s2:mgrs_tile") or it.id.split("_")[4]
        if tile not in seen:
            seen.add(tile)
            keep.append(it)
    return keep


def scale_of(item):
    """Reflectance = (DN + offset) / 10000; baselines from 04.00 add -1000."""
    try:
        base = float(item.properties.get("s2:processing_baseline", "0"))
    except ValueError:
        base = 0.0
    return -1000.0 if base >= 4.0 else 0.0


def read_patch(href, x, y, width_m, out_px, crs_from):
    """Reflectance patch centred on (x, y), padded with zeros past the tile edge."""
    with rasterio.open(planetary_computer.sign(href)) as src:
        if src.crs != crs_from:
            x, y = Transformer.from_crs(crs_from.to_string(), src.crs.to_string(),
                                        always_xy=True).transform(x, y)
        half = width_m / 2
        win = from_bounds(x - half, y - half, x + half, y + half,
                          transform=src.transform).round_offsets().round_lengths()
        full = Window(0, 0, src.width, src.height)
        out = np.zeros((out_px, out_px), "float32")
        try:
            inside = win.intersection(full)
        except Exception:
            return out
        scale_r = out_px / win.height
        scale_c = out_px / win.width
        shape_out = (max(1, round(inside.height * scale_r)),
                     max(1, round(inside.width * scale_c)))
        data = src.read(1, window=inside, out_shape=shape_out).astype("float32")
        r0 = round((inside.row_off - win.row_off) * scale_r)
        c0 = round((inside.col_off - win.col_off) * scale_c)
        h = min(data.shape[0], out_px - r0)
        w = min(data.shape[1], out_px - c0)
        out[r0:r0 + h, c0:c0 + w] = data[:h, :w]
        return out


# Reflectance that maps to full brightness, per channel. One top for all three
# bands saturated vegetation, whose near infrared often runs past 0.4, into flat
# green and hid the difference between a dry crop and a flooded one.
FALSE_TOPS = (0.35, 0.55, 0.25)      # shortwave infrared, near infrared, red
TRUE_TOPS = (0.18, 0.18, 0.18)       # red, green, blue


def stretch(rgb, tops):
    return np.clip(rgb / np.asarray(tops, "float32"), 0, 1) ** 0.8


def cut_chips(points, crs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    CHIPS.mkdir(parents=True, exist_ok=True)
    items = find_items()
    feet = [(shape(it.geometry), it) for it in items]
    todo = [p for p in points if not (CHIPS / f"{p['point_id']}.png").exists()]
    print(f"\n  chips: {len(points) - len(todo)} already done, {len(todo)} to cut")
    failed = []
    for n, p in enumerate(todo, 1):
        here = Point(float(p["lon"]), float(p["lat"]))
        item = next((it for g, it in feet if g.contains(here)), None)
        if item is None:
            failed.append(p["point_id"])
            continue
        off = scale_of(item)
        x, y = float(p["x"]), float(p["y"])
        try:
            band = {b: (read_patch(item.assets[b].href, x, y, CLOSE_M, 64, crs) + off)
                    / 10000 for b in ("B02", "B03", "B04", "B08", "B12")}
            ctx = {b: (read_patch(item.assets[b].href, x, y, CONTEXT_M, 128, crs) + off)
                   / 10000 for b in ("B04", "B08", "B12")}
        except Exception as exc:
            failed.append(p["point_id"])
            print(f"  {p['point_id']} failed: {type(exc).__name__}: {exc}")
            continue

        fc = stretch(np.dstack([band["B12"], band["B08"], band["B04"]]), FALSE_TOPS)
        tc = stretch(np.dstack([band["B04"], band["B03"], band["B02"]]), TRUE_TOPS)
        cx = stretch(np.dstack([ctx["B12"], ctx["B08"], ctx["B04"]]), FALSE_TOPS)

        fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.8))
        for a, img, t in ((ax[0], fc, "false colour, 640 m"),
                          (ax[1], tc, "true colour, 640 m"),
                          (ax[2], cx, "false colour, 2.56 km")):
            a.imshow(img, interpolation="nearest")
            a.set_title(t, fontsize=9)
            a.set_xticks([])
            a.set_yticks([])
        for a in ax[:2]:                       # the 20 m cell, 2 px at 10 m
            a.add_patch(Rectangle((30.5, 30.5), 2, 2, fill=False,
                                  edgecolor="yellow", linewidth=1.2))
            for x0, x1, y0, y1 in ((20, 28, 31.5, 31.5), (35, 43, 31.5, 31.5),
                                   (31.5, 31.5, 20, 28), (31.5, 31.5, 35, 43)):
                a.plot([x0, x1], [y0, y1], color="yellow", linewidth=1)
        ax[2].add_patch(Rectangle((47.5, 47.5), 32, 32, fill=False,
                                  edgecolor="yellow", linewidth=1))
        fig.suptitle(f"{p['point_id']}   {p['lat']}, {p['lon']}", fontsize=10)
        fig.tight_layout()
        fig.savefig(CHIPS / f"{p['point_id']}.png", dpi=110)
        plt.close(fig)
        if n % 25 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)}")
    if failed:
        print(f"\n  {len(failed)} chip(s) not cut: {', '.join(failed[:20])}"
              f"{' ...' if len(failed) > 20 else ''}. Rerun with --chips-only.")


def labelled():
    sheet = SAMPLE / "labels.csv"
    if not sheet.exists():
        return False
    with open(sheet, encoding="utf-8") as fh:
        return any((r.get("label") or "").strip() for r in csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chips-only", action="store_true",
                    help="skip drawing and cut any missing chips")
    ap.add_argument("--redraw", action="store_true",
                    help="discard the existing sample and draw a new one")
    args = ap.parse_args()

    if not SCL_TIF.exists():
        sys.exit(f"missing {SCL_TIF}; run clear_sky.py first")

    print("=" * 78)
    print("ACCURACY SAMPLE, 12 AUGUST MAP, INSIDE SENTINEL-2A CLEAR SKY")
    print("=" * 78)

    key = SAMPLE / "points_key.csv"
    if key.exists() and not args.redraw:
        with open(key, encoding="utf-8") as fh:
            points = list(csv.DictReader(fh))
        print(f"  using the existing sample, {len(points)} points "
              f"(--redraw to replace it)")
    elif args.chips_only:
        sys.exit("no sample yet; run without --chips-only first")
    else:
        if labelled():
            sys.exit("labels.csv already holds labels; a new draw would discard "
                     "them. Move labels.csv aside first if you mean it.")
        points = draw(ALLOCATION)

    with rasterio.open(MAP) as ref:
        crs = ref.crs
    cut_chips(points, crs)
    print(f"\n  next: fill in {SAMPLE / 'labels.csv'}, following LABELLING.txt")


if __name__ == "__main__":
    main()
