"""
RS-01 / validation, step two. Turn the labelled sample into accuracy figures
and a flood area with a standard error, closing F-01 and F-02 in REVIEW.md as
far as clear sky allows.

Reads the sample drawn by draw_sample.py and the labels in labels.csv. Nothing
here touches imagery again.

What counts as flood
--------------------
A point is reference flood when it is labelled W or V and its JRC occurrence
is below the project's permanent-water cut (config.GSW_PERMANENT_MIN). That is
the map's own definition, so water the map calls permanent is not counted as
missed flood. C points are dropped as unreadable. Two variants run beside the
main one: W only, which leaves out water seen through vegetation, and confident
only, which drops labels marked 3, a guess.

The estimator
-------------
Stratified estimation as in Olofsson et al. (2014), with the strata as the
sampling design, not the map classes. For stratum h with area A_h and labelled
share p_h of reference flood:

  flood area          sum of A_h * p_h
  its variance        sum of A_h^2 * p_h (1 - p_h) / (n_h - 1)
  user's accuracy     reference flood share of the strata a map calls flood
  producer's accuracy share of all reference flood that the map calls flood
  overall accuracy    share of the area where map and reference agree

Variances of the two accuracies use the usual first-order approximation.
Because the strata nest, one sample scores both maps: the published one at
-18.75 dB calls stratum "flood" flood, and the -17.75 dB one adds "upper
threshold only". The estimated flood area is the same for both, since it
estimates the ground, not a map.

Every figure is given twice:

  clear sky   areas are the eligible hectares, the part the sample represents:
              SCL clear, no SCL cloud within 100 m, passing the image screen
              in draw_sample.py, and scaled by each stratum's share of points
              you could read, since a C point is ground the sample cannot see.
              No assumption needed, though the scaling adds a little
              uncertainty the standard error leaves out
  whole map   areas are the mapped hectares; assumes the map's errors under
              cloud match those in clear sky at least 100 m from cloud

The swath edge is outside the published map. Its estimate says how much real
flood the buffer set aside, and it is reported on its own.

A stratum with no flood among its labels gets a variance of zero, which
understates what a few dozen points can rule out. The per-stratum table
therefore also gives a 95% Clopper-Pearson interval.

Two checks on the whole-map assumption
--------------------------------------
  distance to cloud   map error by distance from the point to the nearest SCL
                      cloud, cloud shadow or cirrus. A trend as cloud gets
                      closer suggests the cloudy part differs.
  clear vs cloudy     in each stratum, elevation and slope of random pixels in
                      the eligible part against the rest. A large difference
                      means the clear part is not a fair stand-in. This check
                      needs no labels, so --cloud-check-only runs it now.

Outputs, under results/validation/
----------------------------------
  accuracy_labels.csv          per stratum: how many points got each label
  accuracy_labels_by_scl.csv   every point, top-up included, by the scene
                               classification class it sits on
  accuracy_strata.csv          per stratum: n, share of flood, interval
  accuracy_summary.csv         every estimate, both layers, all variants
  check_cloud_distance.csv
  check_clear_vs_cloudy.csv

Usage
-----
    python src\\estimate_accuracy.py                    # after every label is in
    python src\\estimate_accuracy.py --cloud-check-only # now, no labels needed

The script stops if any point is unlabelled, because partial results seen
while labelling would steer the remaining labels. --allow-partial overrides
that for testing only.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import xy as pixel_xy
from rasterio.windows import Window
from scipy.stats import beta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, GSW_PERMANENT_MIN                       # noqa: E402
from clear_sky import MAP, OUT, RAW, SCL_TIF, UPPER, strata_of   # noqa: E402
from draw_sample import (CELL, CLOUD_SCL, ELIGIBLE_SCL, NAMES,   # noqa: E402
                         SAMPLE, cloud_near, near_flood_mask)

GSW_DIR = DATA / "gsw_scene"
DEM_DIR = DATA / "dem_scene"

IN_MAP = [1, 2, 3, 4, 6, 7]          # every stratum but the swath edge
EDGE = 5
# The maps the strata were read from. Since C-31 the published map has a
# bilinear DEM and is scored by score_map.py; these stay as drawn.
MAPS = {"-18.75 dB, as drawn": {1}, "-17.75 dB, as drawn": {1, 3}}
VARIANTS = {
    "W or V": lambda r: r["label"] in ("W", "V"),
    "W only": lambda r: r["label"] == "W",
    "confident only": lambda r: r["label"] in ("W", "V"),
}
CHECK_SEED = 20261014
CHECK_PER_GROUP = 3000
DIST_BINS = [(100, 200), (200, 500), (500, 1000), (1000, None)]


# ---------------------------------------------------------------- inputs
def slope_degrees(elev, res):
    """Slope as refine_scene.py computes it, from a grid in metres."""
    gy, gx = np.gradient(elev.astype("float64"), res, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")


def load_points(include_topup=False):
    """The labelled points. Top-up points come from one part of one stratum
    only, so the whole-stratum estimates here leave them out."""
    with open(SAMPLE / "points_key.csv", encoding="utf-8") as fh:
        key = {r["point_id"]: r for r in csv.DictReader(fh)
               if include_topup or not (r.get("batch") or "main").startswith("topup")}
    with open(SAMPLE / "labels.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["point_id"] not in key:
                continue
            p = key[r["point_id"]]
            p["label"] = (r.get("label") or "").strip().upper()[:1]
            p["confidence"] = (r.get("confidence") or "").strip()
    codes = {v: k for k, v in NAMES.items()}
    for p in key.values():
        p["code"] = codes[p["stratum"]]
        p["row"], p["col"] = int(p["row"]), int(p["col"])
        p["x"], p["y"] = float(p["x"]), float(p["y"])
    return list(key.values())


def load_strata():
    with open(SAMPLE / "strata.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    codes = {v: k for k, v in NAMES.items()}
    out = {}
    for r in rows:
        clear = r.get("screened_eligible_ha") or r["eligible_ha"]
        out[codes[r["stratum"]]] = dict(mapped=float(r["mapped_ha"]),
                                        eligible=float(clear))
    return out


def tile_lookup(folder, pattern):
    """Open every tile once; return (bounds, path) for a point lookup."""
    out = []
    for f in sorted(folder.glob(pattern)):
        with rasterio.open(f) as d:
            out.append((d.bounds, f))
    return out


def find_tile(tiles, x, y):
    for b, f in tiles:
        if b.left <= x < b.right and b.bottom < y <= b.top:
            return f
    return None


def sample_tiles(tiles, xs, ys, fn):
    """Apply fn(dataset, array) per tile to the points inside it."""
    out = np.full(len(xs), np.nan)
    by_tile = defaultdict(list)
    for i, (x, y) in enumerate(zip(xs, ys)):
        f = find_tile(tiles, x, y)
        if f is not None:
            by_tile[f].append(i)
    for f, idx in by_tile.items():
        with rasterio.open(f) as d:
            arr = fn(d, d.read(1))
            for i in idx:
                r, c = d.index(xs[i], ys[i])
                if 0 <= r < arr.shape[0] and 0 <= c < arr.shape[1]:
                    out[i] = arr[r, c]
    return out


def occurrence_at(xs, ys):
    tiles = tile_lookup(GSW_DIR, "India_gsw_20m_*.tif")
    occ = sample_tiles(tiles, xs, ys, lambda d, a: a.astype("float32"))
    occ[occ > 100] = np.nan          # JRC uses values above 100 for no data
    return occ


def terrain_at(xs, ys):
    # digits only, so tiles cached by a DEM resampling test are left out
    tiles = tile_lookup(DEM_DIR, "India_dem_20m_[0-9]*_[0-9]*.tif")
    elev = sample_tiles(tiles, xs, ys, lambda d, a: a)
    slope = sample_tiles(tiles, xs, ys,
                         lambda d, a: slope_degrees(a, abs(d.transform.a)))
    return elev, slope


def cloud_distance(scl, row, col, reach=60):
    """Metres from a pixel to the nearest SCL cloud, shadow or cirrus."""
    r0, r1 = max(0, row - reach), min(scl.shape[0], row + reach + 1)
    c0, c1 = max(0, col - reach), min(scl.shape[1], col + reach + 1)
    rr, cc = np.nonzero(np.isin(scl[r0:r1, c0:c1], CLOUD_SCL))
    if rr.size == 0:
        return float(reach * 20)
    d = np.hypot(rr + r0 - row, cc + c0 - col).min() * 20
    return float(d)


def label_counts(points, codes=None):
    """Points per stratum by label, and by label and confidence."""
    rows = []
    for k in IN_MAP + [EDGE]:
        ps = [p for p in points if p["code"] == k and (codes is None or k in codes)]
        if not ps:
            continue
        row = dict(stratum=NAMES[k], points=len(ps))
        for lab in "WVNC":
            row[lab] = sum(1 for p in ps if p["label"] == lab)
        for lab in "WVNC":
            for c in "123":
                row[f"{lab}{c}"] = sum(1 for p in ps if p["label"] == lab
                                       and p["confidence"] == c)
        rows.append(row)
    return rows


def labels_by_scl():
    """Labels by scene classification class, over all 610 points. Dark area
    and unclassified pixels are eligible as well as the clear classes, and
    much of the open water sits on them (REGISTER V-04)."""
    names = {2: "dark area", 4: "vegetation", 5: "bare soil", 6: "water",
             7: "unclassified"}
    pts = load_points(include_topup=True)
    rows = []
    groups = [(str(k), v, {k}) for k, v in names.items()]
    groups.append(("2 and 7", "dark area or unclassified", {2, 7}))
    for code, name, members in groups:
        ps = [p for p in pts if int(p["scl_class"]) in members]
        row = dict(scl_class=code, name=name, points=len(ps))
        for lab in "WVNC":
            row[lab] = sum(1 for p in ps if p["label"] == lab)
        rows.append(row)
    return rows


# ------------------------------------------------------------ estimation
def stratum_stats(points, ref):
    """Per stratum: usable n, flood count, share and its variance."""
    st = {}
    for k in list(IN_MAP) + [EDGE]:
        use = [p for p in points if p["code"] == k and p["usable"]]
        n = len(use)
        f = sum(1 for p in use if ref(p))
        prop = f / n if n else float("nan")
        var = prop * (1 - prop) / (n - 1) if n > 1 else float("nan")
        lo = beta.ppf(0.025, f, n - f + 1) if f > 0 else 0.0
        hi = beta.ppf(0.975, f + 1, n - f) if f < n else 1.0
        st[k] = dict(n=n, flood=f, p=prop, var=var,
                     cp_low=float(lo) if n else float("nan"),
                     cp_high=float(hi) if n else float("nan"),
                     unreadable=sum(1 for p in points
                                    if p["code"] == k and p["label"] == "C"))
    return st


def estimates(st, areas, layer):
    A = {k: areas[k][layer] for k in IN_MAP}
    total = sum(A.values())
    rows = []
    area = sum(A[k] * st[k]["p"] for k in IN_MAP)
    area_var = sum(A[k] ** 2 * st[k]["var"] for k in IN_MAP)
    rows.append(("flood area, ha", None, area, math.sqrt(area_var)))
    for name, F in MAPS.items():
        AF = sum(A[k] for k in F)
        rows.append(("mapped flood, ha", name, AF, 0.0))
        ua = sum(A[k] * st[k]["p"] for k in F) / AF
        ua_var = sum((A[k] / AF) ** 2 * st[k]["var"] for k in F)
        pa = sum(A[k] * st[k]["p"] for k in F) / area if area else float("nan")
        pa_var = (sum(A[k] ** 2 * ((1.0 if k in F else 0.0) - pa) ** 2
                      * st[k]["var"] for k in IN_MAP) / area ** 2
                  if area else float("nan"))
        oa = sum(A[k] * (st[k]["p"] if k in F else 1 - st[k]["p"])
                 for k in IN_MAP) / total
        oa_var = sum((A[k] / total) ** 2 * st[k]["var"] for k in IN_MAP)
        rows += [("user's accuracy", name, ua, math.sqrt(ua_var)),
                 ("producer's accuracy", name, pa, math.sqrt(pa_var)),
                 ("overall accuracy", name, oa, math.sqrt(oa_var))]
    edge_a = areas[EDGE][layer]
    rows.append(("real flood inside the swath-edge buffer, ha", None,
                 edge_a * st[EDGE]["p"],
                 math.sqrt(edge_a ** 2 * st[EDGE]["var"])))
    rows.append(("real flood removed by refinement, ha", None,
                 A[4] * st[4]["p"], math.sqrt(A[4] ** 2 * st[4]["var"])))
    return rows


# ---------------------------------------------------------------- checks
def check_cloud_distance(points, scl, ref):
    rows = []
    for p in points:
        p["cloud_m"] = cloud_distance(scl, p["row"], p["col"])
    for lo, hi in DIST_BINS:
        inbin = [p for p in points if p["usable"] and p["code"] in IN_MAP
                 and p["cloud_m"] >= lo and (hi is None or p["cloud_m"] < hi)]
        mf = [p for p in inbin if p["code"] in MAPS["-18.75 dB, as drawn"]]
        ml = [p for p in inbin if p["code"] not in MAPS["-18.75 dB, as drawn"]]
        rows.append(dict(
            distance=f"{lo} to {hi} m" if hi else f"{lo} m and over",
            n=len(inbin),
            map_flood_n=len(mf),
            map_flood_not_flood_pct=(round(100 * sum(1 for p in mf if not ref(p))
                                           / len(mf), 1) if mf else ""),
            map_land_n=len(ml),
            map_land_flood_pct=(round(100 * sum(1 for p in ml if ref(p))
                                      / len(ml), 1) if ml else ""),
        ))
    return rows


def check_clear_vs_cloudy(scl):
    """Random pixels per stratum, eligible part against the rest."""
    rng = np.random.default_rng(CHECK_SEED)
    groups = [(k, e) for k in NAMES for e in (True, False)]
    best = {g: (np.empty(0), np.empty(0, "int64")) for g in groups}
    n = CHECK_PER_GROUP
    with rasterio.open(MAP) as ref, rasterio.open(RAW) as raw, \
            rasterio.open(UPPER) as up:
        print("  marking land near flood, for the land strata ...")
        near = near_flood_mask(ref, up)
        print("  sampling pixels ...")
        step = CELL * 200
        for r0 in range(0, ref.height, step):
            win = Window(0, r0, ref.width, min(step, ref.height - r0))
            s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                          up.read(1, window=win))
            h, w = s.shape
            nb = np.repeat(np.repeat(near[r0 // CELL:r0 // CELL + -(-h // CELL)],
                                     CELL, axis=0), CELL, axis=1)[:h, :w]
            s[(s == 6) & ~nb] = 7
            ok = np.isin(scl[r0:r0 + h], ELIGIBLE_SCL) & ~cloud_near(scl, r0, h)
            for k, e in groups:
                idx = np.flatnonzero((s == k) & (ok if e else ~ok))
                if idx.size == 0:
                    continue
                keys = rng.random(idx.size)
                if idx.size > n:
                    sel = np.argpartition(keys, n)[:n]
                    keys, idx = keys[sel], idx[sel]
                rows_, cols_ = np.divmod(idx, w)
                flat = (rows_ + r0).astype("int64") * ref.width + cols_
                ka = np.concatenate([best[(k, e)][0], keys])
                ia = np.concatenate([best[(k, e)][1], flat])
                if ka.size > n:
                    sel = np.argpartition(ka, n)[:n]
                    ka, ia = ka[sel], ia[sel]
                best[(k, e)] = (ka, ia)
        transform, width = ref.transform, ref.width

    print("  reading terrain ...")
    allx, ally, owner = [], [], []
    for g, (_, flat) in best.items():
        rr, cc = np.divmod(flat, width)
        xs, ys = pixel_xy(transform, rr, cc)
        allx += list(np.atleast_1d(xs))
        ally += list(np.atleast_1d(ys))
        owner += [g] * len(flat)
    elev, slope = terrain_at(allx, ally)
    owner = np.array([f"{k}:{int(e)}" for k, e in owner])

    def smd(a, b):
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if a.size < 2 or b.size < 2:
            return float("nan")
        sd = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        return (a.mean() - b.mean()) / sd if sd else 0.0

    rows = []
    for k, name in NAMES.items():
        e_in, e_out = owner == f"{k}:1", owner == f"{k}:0"
        if not e_in.any() or not e_out.any():
            continue
        row = dict(stratum=name, n_clear=int(e_in.sum()), n_rest=int(e_out.sum()))
        for label, v in (("elevation_m", elev), ("slope_deg", slope)):
            row[f"{label}_median_clear"] = round(float(np.nanmedian(v[e_in])), 1)
            row[f"{label}_median_rest"] = round(float(np.nanmedian(v[e_out])), 1)
            row[f"{label}_smd"] = round(smd(v[e_in], v[e_out]), 2)
        rows.append(row)
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def print_clear_vs_cloudy(rows):
    print(f"\n  {'stratum':<22} {'elevation, m':>18} {'smd':>6} "
          f"{'slope, deg':>14} {'smd':>6}")
    print(f"  {'':<22} {'clear':>8} {'rest':>9} {'':>6} {'clear':>6} {'rest':>7}")
    for r in rows:
        print(f"  {r['stratum']:<22} {r['elevation_m_median_clear']:>8} "
              f"{r['elevation_m_median_rest']:>9} {r['elevation_m_smd']:>6} "
              f"{r['slope_deg_median_clear']:>6} {r['slope_deg_median_rest']:>7} "
              f"{r['slope_deg_smd']:>6}")
    print("\n  clear  eligible pixels, clear sky at least 100 m from cloud")
    print("  rest   the rest of the stratum, under cloud or unseen")
    print("  smd    standardised mean difference; beyond about 0.25 either way,")
    print("         the clear part is a weaker stand-in for the rest")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud-check-only", action="store_true")
    ap.add_argument("--allow-partial", action="store_true",
                    help="testing only: estimate from the labels filled so far")
    args = ap.parse_args()

    print("=" * 78)
    print("ACCURACY AND AREA FROM THE LABELLED SAMPLE")
    print("=" * 78)
    with rasterio.open(SCL_TIF) as s:
        scl = s.read(1)

    if args.cloud_check_only:
        rows = check_clear_vs_cloudy(scl)
        write_csv(OUT / "check_clear_vs_cloudy.csv", rows)
        print_clear_vs_cloudy(rows)
        print(f"\n  wrote {OUT / 'check_clear_vs_cloudy.csv'}")
        return

    points = load_points()
    blank = [p for p in points if p["label"] == ""]
    bad = [p for p in points if p["label"] not in ("", "W", "V", "N", "C")]
    if bad:
        sys.exit(f"unknown labels at {', '.join(p['point_id'] for p in bad[:10])}; "
                 "use W, V, N or C")
    if blank and not args.allow_partial:
        sys.exit(f"{len(blank)} of {len(points)} points have no label yet. "
                 "Finish labelling first.")
    if blank:
        print(f"  TESTING ONLY: {len(blank)} points unlabelled and left out\n")

    occ = occurrence_at([p["x"] for p in points], [p["y"] for p in points])
    for p, o in zip(points, occ):
        p["occurrence"] = o
        p["permanent"] = bool(np.isfinite(o) and o >= GSW_PERMANENT_MIN)

    areas = load_strata()
    summary, strata_rows = [], []
    for vname, is_water in VARIANTS.items():
        for p in points:
            p["usable"] = p["label"] in ("W", "V", "N")
            if vname == "confident only":
                p["usable"] = p["usable"] and p["confidence"] in ("1", "2")

        def ref(p, is_water=is_water):
            return is_water(p) and not p["permanent"]

        st = stratum_stats(points, ref)
        for k, s in st.items():
            strata_rows.append(dict(
                variant=vname, stratum=NAMES[k], n_labelled=s["n"],
                n_unreadable=s["unreadable"], n_flood=s["flood"],
                flood_share=round(s["p"], 4) if s["n"] else "",
                se=round(math.sqrt(s["var"]), 4) if s["n"] > 1 else "",
                cp95_low=round(s["cp_low"], 4) if s["n"] else "",
                cp95_high=round(s["cp_high"], 4) if s["n"] else ""))
        for k in st:                       # C points are ground nobody saw
            labelled = st[k]["n"] + st[k]["unreadable"]
            st[k]["readable"] = st[k]["n"] / labelled if labelled else 1.0
        scaled = {k: dict(areas[k], eligible=areas[k]["eligible"]
                          * st[k]["readable"]) for k in areas}
        for layer in ("eligible", "mapped"):
            for metric, mp, val, se in estimates(st, scaled, layer):
                summary.append(dict(
                    layer="clear sky" if layer == "eligible" else "whole map",
                    variant=vname, map=mp or "", metric=metric,
                    value=round(val, 4 if val < 2 else 0),
                    se=round(se, 4 if val < 2 else 0),
                    ci95_low=round(val - 1.96 * se, 4 if val < 2 else 0),
                    ci95_high=round(val + 1.96 * se, 4 if val < 2 else 0)))
        if vname == "W or V":
            main_st, main_ref = st, ref
    for p in points:
        p["usable"] = p["label"] in ("W", "V", "N")

    write_csv(OUT / "accuracy_labels.csv", label_counts(points))
    write_csv(OUT / "accuracy_labels_by_scl.csv", labels_by_scl())
    write_csv(OUT / "accuracy_strata.csv", strata_rows)
    write_csv(OUT / "accuracy_summary.csv", summary)
    dist = check_cloud_distance(points, scl, main_ref)
    write_csv(OUT / "check_cloud_distance.csv", dist)

    n_c = sum(1 for p in points if p["label"] == "C")
    print(f"  {len(points)} points, {n_c} unreadable (C), "
          f"{sum(1 for p in points if p['permanent'])} on JRC permanent water\n")
    print(f"  {'stratum':<22} {'n':>4} {'C':>4} {'flood':>6} {'share':>7} "
          f"{'95% interval':>16}")
    for k in IN_MAP + [EDGE]:
        s = main_st[k]
        share = f"{s['p']:.3f}" if s["n"] else "n/a"
        ci = f"{s['cp_low']:.3f} to {s['cp_high']:.3f}" if s["n"] else ""
        print(f"  {NAMES[k]:<22} {s['n']:>4} {s['unreadable']:>4} {s['flood']:>6} "
              f"{share:>7} {ci:>16}")

    for layer in ("clear sky", "whole map"):
        print(f"\n  {layer.upper()}, labels W or V")
        for r in summary:
            if r["layer"] != layer or r["variant"] != "W or V":
                continue
            what = r["metric"] + (f", {r['map']}" if r["map"] else "")
            if r["value"] >= 2:
                print(f"    {what:<52} {r['value']:>10,.0f} +/- {r['se']:,.0f}")
            else:
                print(f"    {what:<52} {r['value']:>10.3f} +/- {r['se']:.3f}")

    print("\n  Other variants, whole map flood area:")
    for r in summary:
        if (r["layer"] == "whole map" and r["metric"] == "flood area, ha"
                and r["variant"] != "W or V"):
            print(f"    {r['variant']:<16} {r['value']:>10,.0f} +/- {r['se']:,.0f} ha")

    print("\n  Map error by distance to the nearest cloud, published map:")
    print(f"    {'distance':<18} {'n':>4} {'map flood':>10} {'not flood':>10} "
          f"{'map land':>9} {'flood':>7}")
    for r in dist:
        nf = "" if r["map_flood_not_flood_pct"] == "" else f"{r['map_flood_not_flood_pct']}%"
        lf = "" if r["map_land_flood_pct"] == "" else f"{r['map_land_flood_pct']}%"
        print(f"    {r['distance']:<18} {r['n']:>4} {r['map_flood_n']:>10} {nf:>10} "
              f"{r['map_land_n']:>9} {lf:>7}")
    print("\n  Points beyond 1.2 km are counted as 1.2 km; the search stops there.")
    print("  Run --cloud-check-only for the terrain check of clear against cloudy.")
    print(f"\n  wrote accuracy_strata.csv, accuracy_summary.csv and "
          f"check_cloud_distance.csv to {OUT}")


if __name__ == "__main__":
    main()
