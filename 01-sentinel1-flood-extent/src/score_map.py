"""
RS-01 / validation. Score any version of the 12 August map against the
labelled sample, so a change to the map (REVIEW S-01, S-02) is judged by how
well it matches the ground as well as by how much area it moves.

Why this needs its own estimator
--------------------------------
estimate_accuracy.py and floodplain_layer.py score the two maps the strata
were read from, whose flood classes are whole strata. A map built another way
cuts across the strata: inside "flood" some points may now be land, inside
"land near flood" some may now be flood. The strata stay what they were, since
they are how the sample was drawn and their areas set every point's weight.
Recomputing them from a new raster would break that link. What changes is the
map class read at each point.

This is the case Stehman (2014) treats, stratified sampling where the strata
differ from the map classes. For each stratum h with area A_h and n_h usable
points, and for any 0/1 value v at a point:

  total of v          T(v) = sum of A_h * mean_h(v)
  its variance        sum of A_h^2 * s2_h(v) / n_h

with y = reference flood, x = the map says flood, z = y * x and a = map and
reference agree:

  flood on the ground     T(y)          the same for every map
  mapped flood            T(x)          an estimate, with its own error
  user's accuracy         T(z) / T(x)
  producer's accuracy     T(z) / T(y)
  overall accuracy        T(a) / total area

and each ratio R = T(u) / T(w) has variance
  sum of A_h^2 * (s2_h(u) + R^2 s2_h(w) - 2 R cov_h(u, w)) / n_h  /  T(w)^2

For the map as drawn x is constant inside each stratum, so these reduce to
the formulas in estimate_accuracy.py and give the same numbers. The script
checks that before it reports anything else.

The floodplain stays the one defined in floodplain_layer.py, on the nearest
DEM the sample was drawn with, so every map is scored over the same ground.

The rest of the map is scored in two parts (REVIEW F-01, F-02): ground at or
below 150 m that the DEM calls steeper than 2 degrees, and ground above 150 m.
Each part's hectares come from floodplain_layer.py's cutoffs by difference,
and its points are the main-sample points that fall in it; above 150 m they
are joined by the third top-up, drawn in the map's flood there. The clear part of each needs no assumption
about cloud. The whole stretches clear-sky rates over ground the terrain check
found higher and steeper under cloud, and is shown only beside it.

Mapped flood is also counted on each raster, over the whole map and inside the
floodplain, and written as "mapped flood, ha, counted" with no error. For the
maps as drawn these counts equal the stratum areas, which is a second check.

Maps scored, where present under results/fullscene/
---------------------------------------------------
  as drawn, -18.75 dB     India_water_20m_dem-nearest_refined.tif
  as drawn, -17.75 dB     India_water_20m_areamatched_dem-nearest_refined.tif
  published, -18.75 dB    India_water_20m_refined.tif, bilinear DEM (C-31)
  published, -17.75 dB    India_water_20m_areamatched_refined.tif
  S-01, VH averaged       India_water_20m_sar_average_refined.tif, nearest DEM

The two "as drawn" maps are the ones the strata were read from, and the check
runs on the first of them.

Where a group of points in land on the map finds no open water at all, its
share gets no variance, and "producer's accuracy 1.000 +/- 0.000" can follow.
So for each such group the script also gives the 95% upper bound on the share
(Clopper-Pearson, 1 - 0.025^(1/n) for n readable points) and the clear hectares
it could hide, which is what the sample can rule out and no more.

The mirror case gets the same treatment. Where every readable point a map
calls flood is open water, or none is, its user's accuracy prints as 1.000 or
0.000 with no variance. user_accuracy_bounds.csv gives the 95% Clopper-Pearson
bound on the points instead: at least 0.025^(1/n) in the first case, at most
1 - 0.025^(1/n) in the second. It counts points, unweighted by stratum, which
is the plain reading of "n out of n". Every row of map_scores.csv also carries
n_readable and n_map_flood, the readable points in its scope and those the map
calls flood, so a thin row shows itself.

Outputs, under results/validation/
----------------------------------
  map_scores.csv
  zero_hit_bounds.csv        groups with no open water found, and their bound
  user_accuracy_bounds.csv   user's accuracy of exactly 1 or 0, and its bound

Usage
-----
    python src\\score_map.py
"""

from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GSW_PERMANENT_MIN, RESULTS                        # noqa: E402
from clear_sky import FLOOD, FULL, MAP, UPPER                         # noqa: E402
from draw_sample import NAMES                                         # noqa: E402
from estimate_accuracy import (IN_MAP, load_points, load_strata,     # noqa: E402
                               occurrence_at, terrain_at, write_csv)
from estimate_accuracy import DEM_DIR, slope_degrees                  # noqa: E402
from floodplain_layer import CUTOFFS, LOW, MAIN, usable_topup         # noqa: E402

OUT = RESULTS / "validation"
CANDIDATES = {
    "as drawn, -18.75 dB": MAP,
    "as drawn, -17.75 dB": UPPER,
    "published, -18.75 dB": FULL / "India_water_20m_refined.tif",
    "published, -17.75 dB": FULL / "India_water_20m_areamatched_refined.tif",
    "S-01, VH averaged": FULL / "India_water_20m_sar_average_refined.tif",
}
CHECKED = "as drawn, -18.75 dB"
VARIANTS = {"W only": ("W",), "W or V": ("W", "V")}


def map_at(path, points, shape):
    with rasterio.open(path) as d:
        if (d.height, d.width) != shape:
            sys.exit(f"{path.name} is {d.height} x {d.width}, the sample grid "
                     f"is {shape[0]} x {shape[1]}; not the same grid")
        return {p["point_id"]: int(d.read(1, window=Window(p["col"], p["row"],
                                                           1, 1))[0, 0]) == FLOOD
                for p in points}


def counted_ha(path):
    """Flood pixels in the raster: whole map, floodplain, all ground <= 150 m."""
    e_max, s_max = CUTOFFS[MAIN]
    e_low = CUTOFFS[LOW][0]
    dem = {}
    for f in sorted(DEM_DIR.glob("India_dem_20m_*_*.tif")):
        m = re.fullmatch(r"India_dem_20m_(\d+)_(\d+)\.tif", f.name)
        if m:
            dem[(int(m.group(1)), int(m.group(2)))] = f
    whole = plain = low = 0
    with rasterio.open(path) as ref:
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        res = abs(ref.transform.a)
        for ty in range(0, -(-ref.height // 2048)):
            for tx in range(0, -(-ref.width // 2048)):
                r0, c0 = ty * 2048, tx * 2048
                h, w = min(2048, ref.height - r0), min(2048, ref.width - c0)
                flood = ref.read(1, window=Window(c0, r0, w, h)) == FLOOD
                whole += int(flood.sum())
                if (ty, tx) not in dem or not flood.any():
                    continue
                with rasterio.open(dem[(ty, tx)]) as d:
                    elev_t = d.read(1).astype("float32")
                    if d.nodata is not None:
                        elev_t[elev_t == d.nodata] = np.nan
                    slope_t = slope_degrees(elev_t, abs(d.transform.a))
                    ro = round((d.transform.f - (ref.transform.f - r0 * res)) / res)
                    co = round((ref.transform.c + c0 * res - d.transform.c) / res)
                elev = elev_t[ro:ro + h, co:co + w]
                slope = slope_t[ro:ro + h, co:co + w]
                if elev.shape != (h, w):
                    continue
                with np.errstate(invalid="ignore"):
                    plain += int((flood & (elev <= e_max) & (slope <= s_max)).sum())
                    low += int((flood & (elev <= e_low)).sum())
    return whole * px_ha, plain * px_ha, low * px_ha


def total(A, vals):
    """Stratified total of one 0/1 value and its variance."""
    t = var = 0.0
    for k, v in vals.items():
        v = np.asarray(v, dtype=float)
        if v.size == 0:
            continue
        t += A[k] * v.mean()
        if v.size > 1:
            var += A[k] ** 2 * v.var(ddof=1) / v.size
    return t, var


def ratio(A, u, w):
    """R = T(u) / T(w) and its standard error, u and w per stratum."""
    tu, _ = total(A, u)
    tw, _ = total(A, w)
    if tw == 0:
        return float("nan"), float("nan")
    r = tu / tw
    var = 0.0
    for k in u:
        a, b = np.asarray(u[k], float), np.asarray(w[k], float)
        if a.size > 1:
            c = np.cov(a, b, ddof=1)
            var += A[k] ** 2 * (c[0, 0] + r * r * c[1, 1] - 2 * r * c[0, 1]) / a.size
    return r, math.sqrt(max(var, 0.0)) / tw


def score(points, flags, areas, layer, letters):
    """Every figure for one map, one scope, one layer, one variant."""
    use = [p for p in points if p["label"] in ("W", "V", "N") and p["code"] in IN_MAP]
    A = {}
    for k in IN_MAP:
        a = areas[k][layer]
        if layer == "eligible":
            n_read = sum(1 for p in points if p["code"] == k and p["label"] in "WVN"
                         and p["label"])
            n_all = sum(1 for p in points if p["code"] == k)
            a *= n_read / n_all if n_all else 1.0
        A[k] = a
    y, x, z, agree = {}, {}, {}, {}
    for k in IN_MAP:
        ps = [p for p in use if p["code"] == k]
        y[k] = [1 if (p["label"] in letters and not p["permanent"]) else 0 for p in ps]
        x[k] = [1 if flags[p["point_id"]] else 0 for p in ps]
        z[k] = [a * b for a, b in zip(y[k], x[k])]
        agree[k] = [1 if a == b else 0 for a, b in zip(y[k], x[k])]
    ty, vy = total(A, y)
    tx, vx = total(A, x)
    ua, ua_se = ratio(A, z, x)
    pa, pa_se = ratio(A, z, y)
    ta, va = total(A, agree)
    tot = sum(A.values())
    return [("flood on the ground, ha", ty, math.sqrt(vy)),
            ("mapped flood, ha", tx, math.sqrt(vx)),
            ("user's accuracy", ua, ua_se),
            ("producer's accuracy", pa, pa_se),
            ("overall accuracy", ta / tot, math.sqrt(va) / tot)]


ZERO_HIT_STRATA = (3, 4, 6, 7)        # land on the -18.75 dB map


def zero_hit_bounds(points, areas, scope, letters=("W",)):
    """For each land stratum with readable points and no open water among them,
    the 95% upper bound on its share and the clear hectares that allows."""
    rows = []
    for k in ZERO_HIT_STRATA:
        ps = [p for p in points if p["code"] == k]
        read = [p for p in ps if p["label"] in ("W", "V", "N")]
        if not read or any(p["label"] in letters and not p["permanent"]
                           for p in read):
            continue
        share = 1 - 0.025 ** (1 / len(read))
        clear = areas[k]["eligible"] * len(read) / len(ps)
        rows.append(dict(scope=scope, stratum=NAMES[k], n_readable=len(read),
                         upper_share_95=round(share, 4), clear_ha=round(clear),
                         upper_ha_95=round(share * clear)))
    return rows


def user_accuracy_bound(points, flags, letters):
    """Where every readable point the map calls flood is reference flood, or
    none is, the 95% Clopper-Pearson bound on the points; otherwise None."""
    use = [p for p in points if p["label"] in ("W", "V", "N")
           and p["code"] in IN_MAP and flags[p["point_id"]]]
    if not use:
        return None
    hits = sum(1 for p in use if p["label"] in letters and not p["permanent"])
    tail = 0.025 ** (1 / len(use))
    if hits == len(use):
        return dict(n_map_flood=len(use), user_accuracy=1.0, bound="lower",
                    bound_95=round(tail, 4))
    if hits == 0:
        return dict(n_map_flood=len(use), user_accuracy=0.0, bound="upper",
                    bound_95=round(1 - tail, 4))
    return None


def counts(points, flags):
    """Readable points in a scope, and those the map calls flood."""
    use = [p for p in points if p["label"] in ("W", "V", "N") and p["code"] in IN_MAP]
    return len(use), sum(1 for p in use if flags[p["point_id"]])


def print_ua_bounds(rows):
    if not rows:
        return
    print("\n  User's accuracy of exactly 1 or 0, which has no variance; the 95% "
          "bound on the points:")
    print(f"  {'map':<22} {'scope':<20} {'variant':<8} {'n':>4} {'value':>6} "
          f"{'bound':>14}")
    for r in rows:
        print(f"  {r['map']:<22} {r['scope']:<20} {r['variant']:<8} "
              f"{r['n_map_flood']:>4} {r['user_accuracy']:>6.3f} "
              f"{r['bound'] + ' ' + format(r['bound_95'], '.3f'):>14}")


def print_bounds(rows):
    if not rows:
        return
    print("\n  No open water found; what the sample can rule out (95% upper bound):")
    print(f"  {'scope':<20} {'stratum':<22} {'n':>4} {'share':>7} "
          f"{'clear ha':>11} {'up to ha':>9}")
    for r in rows:
        print(f"  {r['scope']:<20} {r['stratum']:<22} {r['n_readable']:>4} "
              f"{r['upper_share_95']:>7.4f} {r['clear_ha']:>11,} "
              f"{r['upper_ha_95']:>9,}")


def main():
    print("=" * 78)
    print("MAP VERSIONS SCORED AGAINST THE LABELLED SAMPLE")
    print("=" * 78)
    points = load_points(include_topup=True)
    if any(p["label"] == "" for p in points):
        sys.exit("some points have no label yet")
    occ = occurrence_at([p["x"] for p in points], [p["y"] for p in points])
    elev, slope = terrain_at([p["x"] for p in points], [p["y"] for p in points])
    e_max, s_max = CUTOFFS[MAIN]
    for p, o, e, s in zip(points, occ, elev, slope):
        p["permanent"] = bool(np.isfinite(o) and o >= GSW_PERMANENT_MIN)
        p["batch"] = p.get("batch") or "main"
        p["in_floodplain"] = bool(np.isfinite(e) and e <= e_max and s <= s_max
                                  and usable_topup(p, MAIN))
        p["low_ground"] = bool(np.isfinite(e) and e <= CUTOFFS[LOW][0])

    codes = {v: k for k, v in NAMES.items()}
    with open(OUT / "floodplain_strata.csv", encoding="utf-8") as fh:
        fp_areas = {codes[r["stratum"]]: dict(
                        mapped=float(r["floodplain_mapped_ha"]),
                        eligible=float(r["floodplain_screened_eligible_ha"]))
                    for r in csv.DictReader(fh) if r["cutoff"] == MAIN}
    with open(OUT / "floodplain_strata.csv", encoding="utf-8") as fh:
        low_areas = {codes[r["stratum"]]: dict(
                         mapped=float(r["floodplain_mapped_ha"]),
                         eligible=float(r["floodplain_screened_eligible_ha"]))
                     for r in csv.DictReader(fh) if r["cutoff"] == LOW}
    map_areas = load_strata()

    def minus(a, b):
        return {k: dict(mapped=max(a[k]["mapped"] - b[k]["mapped"], 0.0),
                        eligible=max(a[k]["eligible"] - b[k]["eligible"], 0.0))
                for k in a}

    main = [p for p in points if not p["batch"].startswith("topup")]
    scopes = {"floodplain": ([p for p in points if p["in_floodplain"]], fp_areas),
              "whole map": (main, map_areas),
              "below 150 m, sloped": ([p for p in main if p["low_ground"]
                                       and not p["in_floodplain"]],
                                      minus(low_areas, fp_areas)),
              # topup3 was drawn in mapped flood above 150 m, so it joins here
              "above 150 m": ([p for p in main if not p["low_ground"]]
                              + [p for p in points if p["batch"] == "topup3"],
                              minus(map_areas, low_areas))}
    for scope in ("below 150 m, sloped", "above 150 m"):
        pts, areas = scopes[scope]
        for k in IN_MAP:
            n = sum(1 for p in pts if p["code"] == k and p["label"] in ("W", "V", "N"))
            if n < 2 and areas[k]["eligible"] > 0:
                what = ("its share is taken as zero" if n == 0 else
                        "its share rests on that one point, with no variance")
                print(f"  {scope}: {NAMES[k]} has {n} readable point(s) for "
                      f"{areas[k]['eligible']:,.0f} clear ha; {what}")

    with rasterio.open(MAP) as d:
        shape = (d.height, d.width)
    rows, ua_bounds = [], []
    for name, path in CANDIDATES.items():
        if not path.exists():
            print(f"  {name:<22} {path.name} not found, skipped")
            continue
        flags = map_at(path, points, shape)
        moved = sum(1 for p in points if p["code"] in IN_MAP
                    and flags[p["point_id"]] != (p["code"] == 1))
        print(f"  {name:<22} read; {moved} points differ from the map as drawn")
        whole_ha, plain_ha, low_ha = counted_ha(path)
        for scope, ha in (("whole map", whole_ha), ("floodplain", plain_ha),
                          ("below 150 m, sloped", low_ha - plain_ha),
                          ("above 150 m", whole_ha - low_ha)):
            rows.append(dict(map=name, scope=scope, layer="whole", variant="",
                             metric="mapped flood, ha, counted",
                             value=round(ha), se=0, n_readable="", n_map_flood=""))
        for scope, (pts, areas) in scopes.items():
            n_read, n_flag = counts(pts, flags)
            for vname, letters in VARIANTS.items():
                b = user_accuracy_bound(pts, flags, letters)
                if b:
                    ua_bounds.append(dict(map=name, scope=scope, variant=vname, **b))
            for layer, lname in (("mapped", "whole"), ("eligible", "clear part")):
                for vname, letters in VARIANTS.items():
                    for metric, val, se in score(pts, flags, areas, layer, letters):
                        rows.append(dict(map=name, scope=scope, layer=lname,
                                         variant=vname, metric=metric,
                                         value=round(val, 4 if abs(val) < 2 else 0),
                                         se=round(se, 4 if abs(val) < 2 else 0),
                                         n_readable=n_read, n_map_flood=n_flag))

    # the map as drawn must reproduce floodplain_layer.py before anything else
    with open(OUT / "floodplain_summary.csv", encoding="utf-8") as fh:
        ref_rows = [r for r in csv.DictReader(fh) if r["cutoff"] == MAIN
                    and r["layer"] == "whole floodplain" and r["variant"] == "W only"
                    and r["map"] == "-18.75 dB, as drawn"]
    want = {r["metric"]: float(r["value"]) for r in ref_rows}
    got = {r["metric"]: r["value"] for r in rows if r["map"] == CHECKED
           and r["scope"] == "floodplain" and r["layer"] == "whole"
           and r["variant"] == "W only"}
    bad = [m for m in ("user's accuracy", "producer's accuracy")
           if abs(got.get(m, -1) - want.get(m, -2)) > 0.0006]
    if bad:
        sys.exit(f"\n  the map as drawn does not reproduce floodplain_summary.csv "
                 f"for {', '.join(bad)}: {got} against {want}. Nothing written.")
    print("\n  check: the map as drawn reproduces floodplain_layer.py")

    # and the rasters must be the ones the sample was drawn on, which the
    # draw recorded in strata.csv; a rebuilt map that differs would move
    # every floodplain area without changing a single point (C-31)
    drawn = {"as drawn, -18.75 dB": map_areas[1]["mapped"],
             "as drawn, -17.75 dB": map_areas[1]["mapped"] + map_areas[3]["mapped"]}
    for name, want_ha in drawn.items():
        have = next((r["value"] for r in rows if r["map"] == name
                     and r["scope"] == "whole map"
                     and r["metric"] == "mapped flood, ha, counted"), None)
        if have is None or abs(have - want_ha) > 2:
            sys.exit(f"\n  {name} counts {have} ha of flood where the draw "
                     f"recorded {want_ha:,.0f}. Rebuild it as clear_sky.py "
                     f"says. Nothing written.")
    print("  check: both maps as drawn match the hectares the draw recorded")

    write_csv(OUT / "map_scores.csv", rows)
    print(f"\n  Open-water flood, whole {MAIN} floodplain:")
    print(f"  {'map':<22} {'mapped, ha':>10} {'user':>14} {'producer':>14}")
    for name in CANDIDATES:
        sel = {r["metric"]: r for r in rows if r["map"] == name
               and r["scope"] == "floodplain" and r["layer"] == "whole"
               and r["variant"] == "W only"}
        if not sel:
            continue
        m = next(r["value"] for r in rows if r["map"] == name
                 and r["scope"] == "floodplain" and r["metric"] == "mapped flood, ha, counted")
        u, pr = sel["user's accuracy"], sel["producer's accuracy"]
        print(f"  {name:<22} {m:>10,.0f}"
              f" {u['value']:>7.3f} ± {u['se']:.3f} {pr['value']:>7.3f} ± {pr['se']:.3f}")
    for scope in ("below 150 m, sloped", "above 150 m"):
        pts = scopes[scope][0]
        print(f"\n  {scope}, open water (W only), {len(pts)} points:")
        print(f"  {'map':<22} {'mapped, ha':>10} {'user, clear':>14} {'producer, clear':>16}")
        for name in CANDIDATES:
            sel = {r["metric"]: r for r in rows if r["map"] == name
                   and r["scope"] == scope and r["layer"] == "clear part"
                   and r["variant"] == "W only"}
            if not sel:
                continue
            m = next(r["value"] for r in rows if r["map"] == name and r["scope"] == scope
                     and r["metric"] == "mapped flood, ha, counted")
            u, pr = sel["user's accuracy"], sel["producer's accuracy"]
            print(f"  {name:<22} {m:>10,.0f} {u['value']:>7.3f} ± {u['se']:.3f}"
                  f" {pr['value']:>9.3f} ± {pr['se']:.3f}")
        for lname in ("clear part", "whole"):
            g = next(r for r in rows if r["map"] == CHECKED and r["scope"] == scope
                     and r["layer"] == lname and r["variant"] == "W only"
                     and r["metric"] == "flood on the ground, ha")
            x = next(r for r in rows if r["map"] == CHECKED and r["scope"] == scope
                     and r["layer"] == lname and r["variant"] == "W only"
                     and r["metric"] == "mapped flood, ha")
            print(f"  {lname:<10}  open water on the ground {g['value']:>9,.0f} ± "
                  f"{g['se']:,.0f} ha, mapped as drawn {x['value']:>9,.0f} ha")
    print("  'whole' stretches clear-sky rates over higher, steeper ground.")
    bounds = [r for scope, (pts, areas) in scopes.items()
              for r in zero_hit_bounds(pts, areas, scope)]
    write_csv(OUT / "zero_hit_bounds.csv", bounds)
    print_bounds(bounds)
    write_csv(OUT / "user_accuracy_bounds.csv", ua_bounds)
    print_ua_bounds(ua_bounds)
    print("\n  Flood on the ground is the same for every map; it is in map_scores.csv.")
    print(f"  wrote {OUT / 'map_scores.csv'}")


if __name__ == "__main__":
    main()
