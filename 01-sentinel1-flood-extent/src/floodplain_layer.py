"""
RS-01 / validation, step three. The labelled sample restricted to the
floodplain, where clear and cloudy ground are alike.

estimate_accuracy.py gives two layers. The clear-sky layer needs no
assumption but covers only the ground the sample can see. The whole-map layer
assumes the map errs the same way under cloud as in clear sky, and the terrain
check showed that is doubtful: the cloudy parts of the land strata are far
higher and steeper than the clear parts. This script adds a middle layer, the
floodplain, defined by the terrain alone, and repeats the estimate inside it.

The floodplain
--------------
A 20 m pixel is floodplain if the Copernicus DEM puts it at or below 150 m and
its slope at or below 2 degrees, slope computed as refine_scene.py does. The
Brahmaputra valley floor in the study area lies roughly between 30 and 150 m,
and the floodplain strata in the terrain check have medians of 56 to 70 m and
slopes under half a degree, so 150 m keeps the valley and drops the hills.
The cutoffs were set before any estimate inside them was seen. Two more,
100 m and 200 m at the same slope, show how much the answer leans on the
choice.

Inside the floodplain, each stratum's points are still a simple random sample
of that stratum's floodplain part, so the estimate uses the points that fall
inside it with the floodplain hectares of each stratum as weights. The screen
in draw_sample.py removed some candidates; its acceptance rate is recomputed
for the floodplain candidates of each stratum, falling back to the stratum's
overall rate where fewer than ten were tested there.

What it checks
--------------
The terrain check is repeated inside the floodplain: elevation and slope of
the clear part of each stratum against the rest. If they now agree, the
floodplain estimate rests on a much weaker assumption than the whole-map one.

Top-up points, from topup_sample.py, join the 150 m and 100 m floodplains,
which contain the ground they were drawn from, and stay out of the 200 m one.

Outputs, under results/validation/
----------------------------------
  floodplain_labels.csv     labels per stratum inside the 150 m floodplain
  floodplain_strata.csv     hectares and points per stratum, per cutoff
  floodplain_summary.csv    every estimate, per cutoff, layer and variant
  floodplain_terrain.csv    the terrain check inside the 150 m floodplain

Usage
-----
    python src\\floodplain_layer.py

Needs every label in place, like estimate_accuracy.py. Takes a few minutes,
since it reads the whole 20 m grid once.
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
from scipy.ndimage import maximum_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clear_sky import MAP, OUT, RAW, SCL_TIF, UPPER, strata_of        # noqa: E402
from config import GSW_PERMANENT_MIN                                   # noqa: E402
from draw_sample import (CELL, CLOUD_BUFFER_PX, CLOUD_SCL,              # noqa: E402
                         ELIGIBLE_SCL, NAMES, SAMPLE, near_flood_mask)
from estimate_accuracy import (DEM_DIR, EDGE, IN_MAP, VARIANTS,         # noqa: E402
                               estimates, label_counts, load_points,
                               occurrence_at,
                               slope_degrees, stratum_stats, terrain_at,
                               write_csv)

CUTOFFS = {"150 m": (150.0, 2.0), "100 m": (100.0, 2.0), "200 m": (200.0, 2.0),
           "150 m, any slope": (150.0, 90.0)}
MAIN = "150 m"
# All ground at or below 150 m whatever its slope. With MAIN it splits the rest
# of the map in two: low ground the DEM calls sloped, and ground above 150 m,
# which score_map.py scores apart (REVIEW F-01, F-02).
LOW = "150 m, any slope"
MIN_TESTED = 10
SHOWN = ("W only", "W or V")


def cloud_near_window(scl, r0, r1, c0, c1):
    b = CLOUD_BUFFER_PX
    a0, a1 = max(0, r0 - b), min(scl.shape[0], r1 + b)
    b0, b1 = max(0, c0 - b), min(scl.shape[1], c1 + b)
    cloud = np.isin(scl[a0:a1, b0:b1], CLOUD_SCL)
    y, x = np.ogrid[-b:b + 1, -b:b + 1]
    near = maximum_filter(cloud, footprint=x * x + y * y <= b * b)
    return near[r0 - a0:r0 - a0 + (r1 - r0), c0 - b0:c0 - b0 + (c1 - c0)]


def grid_pass(scl):
    """Floodplain hectares per stratum and cutoff, and the terrain check."""
    mapped = {c: np.zeros(8, "int64") for c in CUTOFFS}
    eligible = {c: np.zeros(8, "int64") for c in CUTOFFS}
    e_top, s_top = CUTOFFS[MAIN]
    e_bins = np.linspace(-50, e_top, int(e_top + 51))
    s_bins = np.linspace(0, s_top, 81)
    hist = {(k, e): [np.zeros(len(e_bins) - 1), np.zeros(len(s_bins) - 1),
                     np.zeros(4)] for k in NAMES for e in (True, False)}

    tiles = []
    for f in sorted(DEM_DIR.glob("India_dem_20m_*_*.tif")):
        # the default DEM cache only; a resampling test keeps its own tiles
        # in the same folder under a longer name (refine_scene.py)
        m = re.fullmatch(r"India_dem_20m_(\d+)_(\d+)\.tif", f.name)
        if m:
            tiles.append((int(m.group(1)), int(m.group(2)), f))

    with rasterio.open(MAP) as ref, rasterio.open(RAW) as raw, \
            rasterio.open(UPPER) as up:
        px_ha = abs(ref.transform.a * ref.transform.e) / 1e4
        res = abs(ref.transform.a)
        print("  marking land within about 1 km of flood ...")
        near = near_flood_mask(ref, up)
        print(f"  reading {len(tiles)} DEM tiles against the map ...")
        for n, (ty, tx, f) in enumerate(tiles, 1):
            r0, c0 = ty * 2048, tx * 2048
            r1, c1 = min(r0 + 2048, ref.height), min(c0 + 2048, ref.width)
            if r0 >= r1 or c0 >= c1:
                continue
            with rasterio.open(f) as dem:
                elev_t = dem.read(1).astype("float32")
                if dem.nodata is not None:
                    elev_t[elev_t == dem.nodata] = np.nan
                slope_t = slope_degrees(elev_t, abs(dem.transform.a))
                ro = round((dem.transform.f - (ref.transform.f - r0 * res)) / res)
                co = round((ref.transform.c + c0 * res - dem.transform.c) / res)
            h, w = r1 - r0, c1 - c0
            elev = elev_t[ro:ro + h, co:co + w]
            slope = slope_t[ro:ro + h, co:co + w]
            if elev.shape != (h, w):
                print(f"  {f.name} does not cover its map window; skipped")
                continue
            win = Window(c0, r0, w, h)
            s = strata_of(ref.read(1, window=win), raw.read(1, window=win),
                          up.read(1, window=win))
            nb = near[np.ix_(np.arange(r0, r1) // CELL, np.arange(c0, c1) // CELL)]
            s[(s == 6) & ~nb] = 7
            ok = (np.isin(scl[r0:r1, c0:c1], ELIGIBLE_SCL)
                  & ~cloud_near_window(scl, r0, r1, c0, c1))
            finite = np.isfinite(elev) & np.isfinite(slope)
            for c, (e_max, s_max) in CUTOFFS.items():
                dom = finite & (elev <= e_max) & (slope <= s_max)
                mapped[c] += np.bincount(s[dom], minlength=8)
                eligible[c] += np.bincount(s[dom & ok], minlength=8)
            dom = finite & (elev <= e_top) & (slope <= s_top)
            for k in NAMES:
                for e in (True, False):
                    sel = dom & (s == k) & (ok if e else ~ok)
                    if not sel.any():
                        continue
                    ev, sv = elev[sel].astype("float64"), slope[sel].astype("float64")
                    hh = hist[(k, e)]
                    hh[0] += np.histogram(ev, e_bins)[0]
                    hh[1] += np.histogram(sv, s_bins)[0]
                    hh[2] += [ev.sum(), (ev ** 2).sum(), sv.sum(), (sv ** 2).sum()]
            if n % 10 == 0 or n == len(tiles):
                print(f"    {n}/{len(tiles)}")
    return mapped, eligible, hist, e_bins, s_bins, px_ha


def terrain_rows(hist, e_bins, s_bins):
    def median(counts, bins):
        tot = counts.sum()
        if tot == 0:
            return float("nan")
        i = np.searchsorted(np.cumsum(counts), tot / 2)
        return float((bins[i] + bins[i + 1]) / 2)

    rows = []
    for k, name in NAMES.items():
        a, b = hist[(k, True)], hist[(k, False)]
        na, nb = a[0].sum(), b[0].sum()
        if na < 2 or nb < 2:
            continue
        row = dict(stratum=name, clear_px=int(na), rest_px=int(nb))
        for label, i, bins, j in (("elevation_m", 0, e_bins, 0),
                                  ("slope_deg", 1, s_bins, 2)):
            ma, mb = a[2][j] / na, b[2][j] / nb
            va = a[2][j + 1] / na - ma ** 2
            vb = b[2][j + 1] / nb - mb ** 2
            sd = math.sqrt(max((va + vb) / 2, 0))
            row[f"{label}_median_clear"] = round(median(a[i], bins), 1)
            row[f"{label}_median_rest"] = round(median(b[i], bins), 1)
            row[f"{label}_smd"] = round((ma - mb) / sd, 2) if sd else 0.0
        rows.append(row)
    return rows


def usable_topup(p, cutoff):
    """Top-up points were drawn inside the 150 m floodplain, so they speak for
    any floodplain inside that one, and not for a larger one, whether larger by
    elevation or by slope."""
    if not (p.get("batch") or "main").startswith("topup"):
        return True
    return (CUTOFFS[cutoff][0] <= CUTOFFS[MAIN][0]
            and CUTOFFS[cutoff][1] <= CUTOFFS[MAIN][1])


def screened_rate(points, dom_flag, codes):
    """Share of tested candidates the image screen accepted, per stratum."""
    with open(SAMPLE / "screened_out.csv", encoding="utf-8") as fh:
        out = list(csv.DictReader(fh))
    ex, ey = terrain_at([float(r["x"]) for r in out], [float(r["y"]) for r in out])
    rates = {}
    for c, (e_max, s_max) in CUTOFFS.items():
        rates[c] = {}
        for k in NAMES:
            acc = sum(1 for p in points if p["code"] == k and dom_flag[c][p["point_id"]])
            rej = sum(1 for r, e, s in zip(out, ex, ey)
                      if codes[r["stratum"]] == k and np.isfinite(e)
                      and e <= e_max and s <= s_max and usable_topup(r, c))
            acc_all = sum(1 for p in points if p["code"] == k
                          and not (p.get("batch") or "main").startswith("topup"))
            rej_all = sum(1 for r in out if codes[r["stratum"]] == k
                          and not (r.get("batch") or "main").startswith("topup"))
            if acc + rej >= MIN_TESTED:
                rates[c][k] = acc / (acc + rej)
            else:
                rates[c][k] = acc_all / (acc_all + rej_all) if acc_all + rej_all else 1.0
    return rates


def main():
    print("=" * 78)
    print("FLOODPLAIN LAYER: THE SAMPLE WHERE CLEAR AND CLOUDY GROUND ARE ALIKE")
    print("=" * 78)
    points = load_points(include_topup=True)
    blank = [p for p in points if p["label"] == ""]
    if blank:
        sys.exit(f"{len(blank)} points have no label yet; finish labelling first")
    codes = {v: k for k, v in NAMES.items()}

    occ = occurrence_at([p["x"] for p in points], [p["y"] for p in points])
    elev, slope = terrain_at([p["x"] for p in points], [p["y"] for p in points])
    for p, o, e, s in zip(points, occ, elev, slope):
        p["permanent"] = bool(np.isfinite(o) and o >= GSW_PERMANENT_MIN)
        p["elev"], p["slope"] = e, s
    dom_flag = {c: {p["point_id"]: bool(np.isfinite(p["elev"]) and p["elev"] <= em
                                        and p["slope"] <= sm
                                        and usable_topup(p, c))
                    for p in points} for c, (em, sm) in CUTOFFS.items()}

    with rasterio.open(SCL_TIF) as f:
        scl = f.read(1)
    mapped, eligible, hist, e_bins, s_bins, px_ha = grid_pass(scl)
    rates = screened_rate(points, dom_flag, codes)

    strata_rows, summary = [], []
    total_flood = None
    for c in CUTOFFS:
        sub = [p for p in points if dom_flag[c][p["point_id"]]]
        areas = {k: dict(mapped=mapped[c][k] * px_ha,
                         eligible=eligible[c][k] * px_ha * rates[c][k])
                 for k in NAMES}
        for k, name in NAMES.items():
            strata_rows.append(dict(
                cutoff=c, elevation_max_m=CUTOFFS[c][0], slope_max_deg=CUTOFFS[c][1],
                # one decimal, so scripts that read these areas back give the
                # same totals as this one (REGISTER V-05)
                stratum=name, floodplain_mapped_ha=round(areas[k]["mapped"], 1),
                floodplain_screened_eligible_ha=round(areas[k]["eligible"], 1),
                screen_acceptance=round(rates[c][k], 3),
                points_inside=sum(1 for p in sub if p["code"] == k)))
        for vname, is_water in VARIANTS.items():
            for p in points:
                p["usable"] = p["label"] in ("W", "V", "N")
                if vname == "confident only":
                    p["usable"] = p["usable"] and p["confidence"] in ("1", "2")

            def ref(p, is_water=is_water):
                return is_water(p) and not p["permanent"]

            st = stratum_stats(sub, ref)
            missing = [NAMES[k] for k in IN_MAP if st[k]["n"] == 0
                       and areas[k]["mapped"] > 0]
            for k in st:
                if st[k]["n"] == 0:
                    st[k].update(p=0.0, var=0.0)
                labelled = st[k]["n"] + st[k]["unreadable"]
                st[k]["readable"] = st[k]["n"] / labelled if labelled else 1.0
            scaled = {k: dict(areas[k], eligible=areas[k]["eligible"]
                              * st[k]["readable"]) for k in areas}
            for layer in ("eligible", "mapped"):
                for metric, mp, val, se in estimates(st, scaled, layer):
                    summary.append(dict(
                        cutoff=c, layer="clear floodplain" if layer == "eligible"
                        else "whole floodplain", variant=vname, map=mp or "",
                        metric=metric, value=round(val, 4 if val < 2 else 0),
                        se=round(se, 4 if val < 2 else 0),
                        ci95_low=round(val - 1.96 * se, 4 if val < 2 else 0),
                        ci95_high=round(val + 1.96 * se, 4 if val < 2 else 0),
                        strata_without_points="; ".join(missing)))
        if c == MAIN:
            total_flood = sum(r["floodplain_mapped_ha"] for r in strata_rows
                              if r["cutoff"] == c and r["stratum"] == "flood")

    terrain = terrain_rows(hist, e_bins, s_bins)
    write_csv(OUT / "floodplain_labels.csv",
              label_counts([p for p in points if dom_flag[MAIN][p["point_id"]]]))
    write_csv(OUT / "floodplain_strata.csv", strata_rows)
    write_csv(OUT / "floodplain_summary.csv", summary)
    write_csv(OUT / "floodplain_terrain.csv", terrain)

    e_max, s_max = CUTOFFS[MAIN]
    print(f"\n  floodplain: at or below {e_max:g} m and {s_max:g} degrees of slope")
    print(f"  it holds {total_flood:,} of the 119,779 ha of flood on the map "
          f"as drawn\n")
    print(f"  {'stratum':<22} {'floodplain ha':>14} {'clear ha':>11} {'points':>7}")
    for r in strata_rows:
        if r["cutoff"] == MAIN:
            print(f"  {r['stratum']:<22} {r['floodplain_mapped_ha']:>14,} "
                  f"{r['floodplain_screened_eligible_ha']:>11,} {r['points_inside']:>7}")

    for vname in SHOWN:
        for layer in ("clear floodplain", "whole floodplain"):
            print(f"\n  {layer.upper()}, {MAIN}, labels {vname}")
            for r in summary:
                if (r["cutoff"] != MAIN or r["layer"] != layer
                        or r["variant"] != vname or r["metric"].startswith("real")):
                    continue
                what = r["metric"] + (f", {r['map']}" if r["map"] else "")
                if r["value"] >= 2:
                    print(f"    {what:<52} {r['value']:>10,.0f} +/- {r['se']:,.0f}")
                else:
                    print(f"    {what:<52} {r['value']:>10.3f} +/- {r['se']:.3f}")
            gap = [r for r in summary if r["cutoff"] == MAIN and r["layer"] == layer
                   and r["variant"] == vname and r["strata_without_points"]]
            if gap:
                print(f"    no points inside for: {gap[0]['strata_without_points']};"
                      " counted as no flood")

    print("\n  Flood area by cutoff, whole floodplain:")
    for vname in SHOWN + ("confident only",):
        parts = []
        for c in CUTOFFS:
            r = next(r for r in summary if r["cutoff"] == c and r["variant"] == vname
                     and r["layer"] == "whole floodplain"
                     and r["metric"] == "flood area, ha")
            parts.append(f"{c}: {r['value']:>9,.0f} +/- {r['se']:,.0f}")
        print(f"    {vname:<15} " + "   ".join(parts))

    print(f"\n  Terrain inside the {MAIN} floodplain, clear part against the rest:")
    print(f"  {'stratum':<22} {'elevation, m':>18} {'smd':>6} "
          f"{'slope, deg':>14} {'smd':>6}")
    print(f"  {'':<22} {'clear':>8} {'rest':>9} {'':>6} {'clear':>6} {'rest':>7}")
    for r in terrain:
        print(f"  {r['stratum']:<22} {r['elevation_m_median_clear']:>8} "
              f"{r['elevation_m_median_rest']:>9} {r['elevation_m_smd']:>6} "
              f"{r['slope_deg_median_clear']:>6} {r['slope_deg_median_rest']:>7} "
              f"{r['slope_deg_smd']:>6}")
    print("\n  smd within about 0.25 either way: the clear part stands in fairly")
    print("  for the rest of the floodplain.")
    print(f"\n  wrote floodplain_strata.csv, floodplain_summary.csv and "
          f"floodplain_terrain.csv to {OUT}")


if __name__ == "__main__":
    main()
