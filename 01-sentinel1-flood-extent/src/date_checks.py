"""
RS-01 / validation of the 7 and 31 August maps. Two checks on the samples that
date_sample.py drew (REVIEW F-01, F-02):

  terrain   the clear part of each stratum against the rest, on elevation and
            slope, as estimate_accuracy.py and floodplain_layer.py did for
            12 August
  second    sets up a second reading of part of one date's sample
  compare   scores the second reading against the first, and shows how far
            the estimates move when it replaces the first on those points

The terrain check
-----------------
On 12 August cloud sat on the hills, so the clear part of the land strata was
lower and flatter than the rest. Inside the floodplain the two parts agreed on
slope, which is what the whole-floodplain figure leans on. The 7 and 31 August
figures make the same assumption, and this tests it. For every pixel of each
stratum it compares the clear part, as date_sample.py defined it, with the
rest, which is under cloud, near cloud or unseen, inside the floodplain and over
the whole map. Where the standardised mean difference is beyond about 0.25
either way, that stratum's clear part is a weaker stand-in for the rest. It
needs no labels.

The second reading
------------------
On 7 August most of what the map calls flood was labelled water through
vegetation, and on 31 August much of it was labelled not water. One reader made
those calls on 30 m Landsat pixels. The second reading takes

  focus    every point in the strata "flood" and "upper threshold only", where
           those calls set user's accuracy at both thresholds
  random   40 more drawn at random from the rest, so a reader cannot tell that
           most points sit in mapped flood, and so agreement is also measured
           on points that are not all hard

mixed and renumbered in random order. The chips are cut again under the new
numbers, so a chip's title gives no hint of the point behind it. The first
reader's labels are in nothing the second reader sees.

Outputs
-------
Under results/validation/sample_<date>/, committed:
  terrain_check.csv
  second/relabel_key.csv    new number, original point and set; keep it from
                            the second reader until they finish
  second/sheet_person.csv   the sheet for the second reader
  second/agreement.csv      agreement and kappa, per set
  second/confusion.csv      first label against second, per set
  second/effect.csv         the estimates with each reading
Under data/validation/second_chips_<date>/, not committed: the renumbered chips

Usage
-----
    python src\\date_checks.py terrain --map-date 2016-08-07
    python src\\date_checks.py second --map-date 2016-08-07    # again resumes chips
    python src\\label_tool.py --sheet sample_20160807\\second\\sheet_person.csv --chips second_chips_20160807 --simple
    python src\\date_checks.py compare --map-date 2016-08-07
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA                                                # noqa: E402
from compare_labels import agreement                                   # noqa: E402
from date_sample import (PREFIX, SCENES, cut_chips, drawn_scene,      # noqa: E402
                         find_scenes, load_areas, load_sample, long_date,
                         make_scopes, paths, prepare, score_rows, tile_pass)
from draw_sample import NAMES                                          # noqa: E402
from estimate_accuracy import write_csv                                # noqa: E402
from floodplain_layer import CUTOFFS, MAIN, terrain_rows               # noqa: E402

FOCUS = ("flood", "upper threshold only")
N_RANDOM = 40
SECOND_SEEDS = {"2016-08-07": 20261025, "2016-08-31": 20261026}
READERS = {"person": "sheet_person.csv", "Claude": "sheet_claude.csv"}
SHOWN = ("flood on the ground, ha", "user's accuracy", "producer's accuracy")


def second_dir(P):
    return P["sample"] / "second"


def second_chips(P):
    return DATA / "validation" / f"second_chips_{P['tag']}"


# ---------------------------------------------------------------- terrain
def terrain(P):
    """Elevation and slope of the clear part of each stratum against the rest."""
    e_top, s_top = CUTOFFS[MAIN]
    doms = {"floodplain": (CUTOFFS[MAIN], np.linspace(-50, e_top, int(e_top + 51)),
                           np.linspace(0, s_top, 81)),
            "whole map": (None, np.linspace(-50, 6000, 6051),
                          np.linspace(0, 90, 361))}
    hist = {d: {(k, e): [np.zeros(len(eb) - 1), np.zeros(len(sb) - 1), np.zeros(4)]
                for k in NAMES for e in (True, False)}
            for d, (_, eb, sb) in doms.items()}
    for t in tile_pass(P):
        s, ok, elev, slope = t["s"], t["ok"], t["elev"], t["slope"]
        finite = np.isfinite(elev) & np.isfinite(slope)
        with np.errstate(invalid="ignore"):
            for d, (cut, eb, sb) in doms.items():
                dom = finite if cut is None else (finite & (elev <= cut[0])
                                                  & (slope <= cut[1]))
                ev, sv = elev[dom].astype("float64"), slope[dom].astype("float64")
                group = s[dom].astype("int64") * 2 + ok[dom]
                ne, ns = len(eb) - 1, len(sb) - 1
                ei = np.clip(((ev - eb[0]) / (eb[1] - eb[0])).astype("int64"), 0, ne - 1)
                si = np.clip(((sv - sb[0]) / (sb[1] - sb[0])).astype("int64"), 0, ns - 1)
                eh = np.bincount(group * ne + ei, minlength=16 * ne).reshape(16, ne)
                sh = np.bincount(group * ns + si, minlength=16 * ns).reshape(16, ns)
                sums = [np.bincount(group, weights=w, minlength=16)
                        for w in (ev, ev ** 2, sv, sv ** 2)]
                for k in NAMES:
                    for e in (True, False):
                        g = k * 2 + int(e)
                        hh = hist[d][(k, e)]
                        hh[0] += eh[g]
                        hh[1] += sh[g]
                        hh[2] += [x[g] for x in sums]
    rows = []
    for d, (_, eb, sb) in doms.items():
        rows += [dict(domain=d, **r) for r in terrain_rows(hist[d], eb, sb)]
    write_csv(P["sample"] / "terrain_check.csv", rows)
    for d in doms:
        print(f"\n  {d.upper()}")
        print(f"  {'stratum':<22} {'elevation, m':>18} {'smd':>6} "
              f"{'slope, deg':>14} {'smd':>6}")
        print(f"  {'':<22} {'clear':>8} {'rest':>9} {'':>6} {'clear':>6} {'rest':>7}")
        for r in rows:
            if r["domain"] != d:
                continue
            print(f"  {r['stratum']:<22} {r['elevation_m_median_clear']:>8} "
                  f"{r['elevation_m_median_rest']:>9} {r['elevation_m_smd']:>6} "
                  f"{r['slope_deg_median_clear']:>6} {r['slope_deg_median_rest']:>7} "
                  f"{r['slope_deg_smd']:>6}")
    print("\n  clear  eligible pixels: QA clear, no cloudy bit within 100 m")
    print("  rest   the rest of the stratum, under or near cloud, or unseen")
    print("  smd    standardised mean difference; beyond about 0.25 either way,")
    print("         the clear part is a weaker stand-in for the rest")
    print(f"\n  wrote {P['sample'] / 'terrain_check.csv'}")


# ----------------------------------------------------------------- second
def second(P, map_date):
    out = second_dir(P)
    key_path = out / "relabel_key.csv"
    points = {p["point_id"]: p for p in load_sample(P)}
    if key_path.exists():
        with open(key_path, encoding="utf-8") as fh:
            key = list(csv.DictReader(fh))
        print(f"  {key_path.name} exists; cutting any chip still missing")
    else:
        if any(not p["label"] for p in points.values()):
            sys.exit("the first reading is not finished; label every point first")
        focus = sorted(pid for pid, p in points.items() if p["stratum"] in FOCUS)
        rest = sorted(pid for pid, p in points.items() if p["stratum"] not in FOCUS)
        rng = np.random.default_rng(SECOND_SEEDS[map_date])
        rand = sorted(rng.choice(rest, size=N_RANDOM, replace=False).tolist())
        chosen = [(pid, "focus") for pid in focus] + [(pid, "random") for pid in rand]
        chosen = [chosen[i] for i in rng.permutation(len(chosen))]
        key = [dict(relabel_id=f"S{PREFIX[map_date]}{n:03d}", point_id=pid, set=which)
               for n, (pid, which) in enumerate(chosen, 1)]
        out.mkdir(parents=True, exist_ok=True)
        write_csv(key_path, key)
        write_csv(out / "sheet_person.csv",
                  [dict(point_id=r["relabel_id"], lon=points[r["point_id"]]["lon"],
                        lat=points[r["point_id"]]["lat"], label="", confidence="",
                        note="") for r in key])
        print(f"  {sum(1 for r in key if r['set'] == 'focus')} focus and "
              f"{sum(1 for r in key if r['set'] == 'random')} random points, "
              f"{key[0]['relabel_id']} to {key[-1]['relabel_id']}")
        print(f"  wrote {key_path.name} and sheet_person.csv to {out}")

    renamed = [dict(points[r["point_id"]], point_id=r["relabel_id"]) for r in key]
    with rasterio.open(P["map"]) as ref:
        crs = ref.crs
    cut_chips(dict(P, chips=second_chips(P)), renamed, crs, find_scenes(P["scene"]))
    shutil.copyfile(P["sample"] / "LABELLING.txt", out / "LABELLING.txt")
    print(f"\n  next: the second reader labels with\n    python src\\label_tool.py "
          f"--sheet sample_{P['tag']}\\second\\sheet_person.csv --chips "
          f"second_chips_{P['tag']} --simple\n  after reading "
          f"sample_{P['tag']}\\second\\LABELLING.txt")


# ---------------------------------------------------------------- compare
def read_sheet(path):
    if not path.exists():
        return None, "missing"
    with open(path, encoding="utf-8") as fh:
        rows = {r["point_id"]: r for r in csv.DictReader(fh)}
    blank = sum(1 for r in rows.values() if not (r["label"] or "").strip())
    if blank:
        return None, f"{blank} of {len(rows)} still blank"
    return {k: ((r["label"] or "").strip().upper()[:1], (r["confidence"] or "").strip())
            for k, r in rows.items()}, "full"


def compare(P, map_date):
    out = second_dir(P)
    with open(out / "relabel_key.csv", encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    to_point = {r["relabel_id"]: r["point_id"] for r in key}
    sets = {s: [r["relabel_id"] for r in key if r["set"] == s]
            for s in dict.fromkeys(r["set"] for r in key)}

    points, scopes = prepare(P)
    by_id = {p["point_id"]: p for p in points}
    readings = {"first": {rid: (by_id[pid]["label"], by_id[pid]["confidence"])
                          for rid, pid in to_point.items()}}
    for reader, sheet in READERS.items():
        got, status = read_sheet(out / sheet)
        if status != "missing":
            print(f"  {reader:<7} {sheet:<18} {status}")
        if got:
            readings[reader] = got
    if len(readings) < 2:
        sys.exit("\n  no second sheet is full yet; nothing to compare")

    agree = agreement(readings, sets)
    write_csv(out / "agreement.csv", agree)
    print(f"\n  {'pair':<18} {'set':<8} {'n':>4} {'agree':>7} {'kappa':>7} "
          f"{'agree W':>8} {'kappa W':>8} {'W flips':>8}")
    for r in agree:
        print(f"  {r['pair']:<18} {r['set']:<8} {r['points']:>4} "
              f"{r['agree_letters']:>7.2f} {r['kappa_letters']:>7.2f} "
              f"{r['agree_open_water']:>8.2f} {r['kappa_open_water']:>8.2f} "
              f"{r['open_water_flips']:>8}")

    conf = []
    for reader in readings:
        if reader == "first":
            continue
        for set_name, ids in sets.items():
            c = Counter((readings["first"][r][0], readings[reader][r][0]) for r in ids)
            for a in "WVNC":
                conf.append(dict(reader=reader, set=set_name, first=a,
                                 **{f"second_{b}": c[(a, b)] for b in "WVNC"}))
    write_csv(out / "confusion.csv", conf)
    for reader in [r for r in readings if r != "first"]:
        print(f"\n  first reader (rows) against {reader} (columns), focus set")
        print(f"  {'':<6} {'W':>4} {'V':>4} {'N':>4} {'C':>4}")
        for r in conf:
            if r["reader"] == reader and r["set"] == "focus":
                print(f"  {r['first']:<6} " + " ".join(f"{r['second_' + b]:>4}"
                                                      for b in "WVNC"))

    areas = load_areas(P)
    base = score_rows(scopes, map_date)
    effect = []
    for reader in readings:
        if reader == "first":
            rows = base
        else:
            override = {to_point[rid]: lab for rid, lab in readings[reader].items()}
            moved = []
            for p in points:
                q = dict(p)
                if p["point_id"] in override:
                    q["label"], q["confidence"] = override[p["point_id"]]
                moved.append(q)
            rows = score_rows(make_scopes(moved, areas), map_date)
        before = {(r["map"], r["scope"], r["layer"], r["variant"], r["metric"]):
                  r["value"] for r in base}
        for r in rows:
            if r["scope"] in ("floodplain", "whole map") and r["metric"] in SHOWN:
                k = (r["map"], r["scope"], r["layer"], r["variant"], r["metric"])
                effect.append(dict(labels=reader if reader == "first" else
                                   f"first, with {reader} on the relabelled points",
                                   **{f: r[f] for f in ("map", "scope", "layer",
                                                        "variant", "metric",
                                                        "value", "se")},
                                   change_from_first=round(r["value"] - before[k], 4)))
    write_csv(out / "effect.csv", effect)
    for variant in ("W only", "W or V"):
        print(f"\n  Floodplain, -18.75 dB, whole, {variant}:")
        print(f"  {'labels':<44} {'on the ground, ha':>20} {'user':>14} {'producer':>14}")
        for lab in dict.fromkeys(r["labels"] for r in effect):
            sel = {r["metric"]: r for r in effect if r["labels"] == lab
                   and r["map"] == "-18.75 dB" and r["scope"] == "floodplain"
                   and r["layer"] == "whole" and r["variant"] == variant}
            g, u, pr = (sel[m] for m in SHOWN)
            print(f"  {lab:<44} {g['value']:>10,.0f} +/- {g['se']:>6,.0f} "
                  f"{u['value']:>6.3f} +/- {u['se']:.3f} "
                  f"{pr['value']:>6.3f} +/- {pr['se']:.3f}")
    if "Claude" in readings:
        print("\n  Claude's labels are an AI's reading of the chips, not a second person's.")
    print(f"\n  wrote agreement.csv, confusion.csv and effect.csv to {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["terrain", "second", "compare"])
    ap.add_argument("--map-date", required=True, choices=sorted(SCENES))
    args = ap.parse_args()
    P = paths(args.map_date, SCENES[args.map_date])
    if not (P["sample"] / "rasters.csv").exists():
        sys.exit("no sample for that date; run date_sample.py draw first")
    P = paths(args.map_date, drawn_scene(P))
    print("=" * 78)
    print(f"{args.step.upper()}, {long_date(args.map_date).upper()} MAP")
    print("=" * 78)
    {"terrain": lambda: terrain(P),
     "second": lambda: second(P, args.map_date),
     "compare": lambda: compare(P, args.map_date)}[args.step]()


if __name__ == "__main__":
    main()
