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

Outputs, under results/validation/
----------------------------------
  map_scores.csv

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
from floodplain_layer import CUTOFFS, MAIN, usable_topup              # noqa: E402

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
    """Flood pixels in the raster, over the whole map and in the floodplain."""
    e_max, s_max = CUTOFFS[MAIN]
    dem = {}
    for f in sorted(DEM_DIR.glob("India_dem_20m_*_*.tif")):
        m = re.fullmatch(r"India_dem_20m_(\d+)_(\d+)\.tif", f.name)
        if m:
            dem[(int(m.group(1)), int(m.group(2)))] = f
    whole = plain = 0
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
    return whole * px_ha, plain * px_ha


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

    codes = {v: k for k, v in NAMES.items()}
    with open(OUT / "floodplain_strata.csv", encoding="utf-8") as fh:
        fp_areas = {codes[r["stratum"]]: dict(
                        mapped=float(r["floodplain_mapped_ha"]),
                        eligible=float(r["floodplain_screened_eligible_ha"]))
                    for r in csv.DictReader(fh) if r["cutoff"] == MAIN}
    map_areas = load_strata()
    scopes = {"floodplain": ([p for p in points if p["in_floodplain"]], fp_areas),
              "whole map": ([p for p in points
                             if not p["batch"].startswith("topup")], map_areas)}

    with rasterio.open(MAP) as d:
        shape = (d.height, d.width)
    rows = []
    for name, path in CANDIDATES.items():
        if not path.exists():
            print(f"  {name:<22} {path.name} not found, skipped")
            continue
        flags = map_at(path, points, shape)
        moved = sum(1 for p in points if p["code"] in IN_MAP
                    and flags[p["point_id"]] != (p["code"] == 1))
        print(f"  {name:<22} read; {moved} points differ from the map as drawn")
        whole_ha, plain_ha = counted_ha(path)
        for scope, ha in (("whole map", whole_ha), ("floodplain", plain_ha)):
            rows.append(dict(map=name, scope=scope, layer="whole", variant="",
                             metric="mapped flood, ha, counted",
                             value=round(ha), se=0))
        for scope, (pts, areas) in scopes.items():
            for layer, lname in (("mapped", "whole"), ("eligible", "clear part")):
                for vname, letters in VARIANTS.items():
                    for metric, val, se in score(pts, flags, areas, layer, letters):
                        rows.append(dict(map=name, scope=scope, layer=lname,
                                         variant=vname, metric=metric,
                                         value=round(val, 4 if abs(val) < 2 else 0),
                                         se=round(se, 4 if abs(val) < 2 else 0)))

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
    print("\n  Flood on the ground is the same for every map; it is in map_scores.csv.")
    print(f"  wrote {OUT / 'map_scores.csv'}")


if __name__ == "__main__":
    main()
