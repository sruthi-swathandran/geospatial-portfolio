"""
RS-01 / validation. Compare the second labellings with the first, and show how
far the open-water estimate moves when the second reader's calls replace the
first's.

Reads results/validation/second/: the key from second_label.py and the two
sheets, one from a second person and one from Claude. A sheet that is not yet
full is reported and left out.

What it reports
---------------
  agreement   for each pair of readers, the share of points where they agree,
              and Cohen's kappa, which discounts the agreement two readers
              would reach by chance. Given on the random set, which is fair,
              and on the uncertain set, which is not and is shown for contrast.
              Once over all four letters, and once over open water against
              everything else, which is what the headline uses.
  effect      the floodplain and whole-map estimates recomputed with each
              second reader's labels in place of the first reader's, for the
              points they relabelled. The first reader's labels stay on every
              other point. The difference is how much the headline rests on
              who made the hard calls.

Claude's labels are an AI's reading of the same chips, not a second person's,
and are reported as such.

Outputs, under results/validation/second/
-----------------------------------------
  agreement.csv
  effect.csv

Usage
-----
    python src\\compare_labels.py
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GSW_PERMANENT_MIN, RESULTS                        # noqa: E402
from draw_sample import NAMES                                         # noqa: E402
from estimate_accuracy import (EDGE, IN_MAP, estimates, load_points,  # noqa: E402
                               load_strata, occurrence_at, stratum_stats,
                               terrain_at, write_csv)
from floodplain_layer import CUTOFFS, MAIN, usable_topup              # noqa: E402

SECOND = RESULTS / "validation" / "second"
READERS = {"person": "sheet_person.csv", "Claude": "sheet_claude.csv"}
LETTERS = ["W", "V", "N", "C"]


def read_sheet(name):
    p = SECOND / name
    if not p.exists():
        return None, "missing"
    with open(p, encoding="utf-8") as fh:
        rows = {r["point_id"]: r for r in csv.DictReader(fh)}
    blank = sum(1 for r in rows.values() if not (r["label"] or "").strip())
    if blank:
        return None, f"{blank} of {len(rows)} still blank"
    return {k: ((r["label"] or "").strip().upper()[:1], (r["confidence"] or "").strip())
            for k, r in rows.items()}, "full"


def kappa(a, b, cats):
    n = len(a)
    if n == 0:
        return float("nan"), float("nan")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def agreement(readings, sets):
    rows = []
    names = list(readings)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_name, b_name = names[i], names[j]
            for set_name, ids in sets.items():
                a = [readings[a_name][r][0] for r in ids]
                b = [readings[b_name][r][0] for r in ids]
                po4, k4 = kappa(a, b, LETTERS)
                wa = ["W" if x == "W" else "-" for x in a]
                wb = ["W" if x == "W" else "-" for x in b]
                po2, k2 = kappa(wa, wb, ["W", "-"])
                rows.append(dict(
                    pair=f"{a_name} / {b_name}", set=set_name, points=len(ids),
                    agree_letters=round(po4, 3), kappa_letters=round(k4, 3),
                    agree_open_water=round(po2, 3), kappa_open_water=round(k2, 3),
                    open_water_flips=sum(1 for x, y in zip(wa, wb) if x != y)))
    return rows


def estimate_with(points, override, fp_areas, map_areas):
    """Floodplain and whole-map figures with some labels replaced."""
    out = {}
    for p in points:
        lab = override.get(p["point_id"])
        p["lab2"], p["conf2"] = lab if lab else (p["label"], p["confidence"])
    variants = {"W only": lambda p: p["lab2"] == "W",
                "W or V": lambda p: p["lab2"] in ("W", "V")}
    for vname, is_water in variants.items():
        for p in points:
            p["label_saved"] = p["label"]
            p["label"] = p["lab2"]
            p["usable"] = p["lab2"] in ("W", "V", "N")

        def ref(p, is_water=is_water):
            return is_water(p) and not p["permanent"]

        for scope, pts, areas in (
                ("floodplain", [p for p in points if p["in_floodplain"]], fp_areas),
                ("whole map", [p for p in points if not p["batch"].startswith("topup")],
                 map_areas)):
            st = stratum_stats(pts, ref)
            for k in st:
                if st[k]["n"] == 0:
                    st[k].update(p=0.0, var=0.0)
                labelled = st[k]["n"] + st[k]["unreadable"]
                st[k]["readable"] = st[k]["n"] / labelled if labelled else 1.0
            scaled = {k: dict(areas[k], eligible=areas[k]["eligible"]
                              * st[k]["readable"]) for k in areas}
            for layer, lname in (("mapped", "whole"), ("eligible", "clear part")):
                for metric, mp, val, se in estimates(st, scaled, layer):
                    if metric == "flood area, ha":
                        out[(scope, lname, vname)] = (val, se)
        for p in points:
            p["label"] = p["label_saved"]
    return out


def main():
    print("=" * 78)
    print("SECOND LABELLING AGAINST THE FIRST")
    print("=" * 78)
    with open(SECOND / "relabel_key.csv", encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    to_point = {r["relabel_id"]: r["point_id"] for r in key}
    names = list(dict.fromkeys(r["set"] for r in key))   # in order of appearance
    sets = {s: [r["relabel_id"] for r in key if r["set"] == s] for s in names}

    points = load_points(include_topup=True)
    by_id = {p["point_id"]: p for p in points}
    readings = {"first": {rid: (by_id[pid]["label"], by_id[pid]["confidence"])
                          for rid, pid in to_point.items()}}
    for reader, sheet in READERS.items():
        got, status = read_sheet(sheet)
        print(f"  {reader:<7} {sheet:<18} {status}")
        if got:
            readings[reader] = got
    if len(readings) < 2:
        sys.exit("\n  no second sheet is full yet; nothing to compare")

    agree = agreement(readings, sets)
    write_csv(SECOND / "agreement.csv", agree)
    print(f"\n  {'pair':<18} {'set':<12} {'n':>4} {'agree':>7} {'kappa':>7} "
          f"{'agree W':>8} {'kappa W':>8} {'W flips':>8}")
    for r in agree:
        print(f"  {r['pair']:<18} {r['set']:<12} {r['points']:>4} "
              f"{r['agree_letters']:>7.2f} {r['kappa_letters']:>7.2f} "
              f"{r['agree_open_water']:>8.2f} {r['kappa_open_water']:>8.2f} "
              f"{r['open_water_flips']:>8}")
    print("\n  agree, kappa      over all four letters")
    print("  agree W, kappa W  over open water against everything else")
    print("  kappa near 1 is strong agreement; near 0 is no better than chance")

    occ = occurrence_at([p["x"] for p in points], [p["y"] for p in points])
    elev, slope = terrain_at([p["x"] for p in points], [p["y"] for p in points])
    e_max, s_max = CUTOFFS[MAIN]
    for p, o, e, s in zip(points, occ, elev, slope):
        p["permanent"] = bool(np.isfinite(o) and o >= GSW_PERMANENT_MIN)
        p["batch"] = p.get("batch") or "main"
        p["in_floodplain"] = bool(np.isfinite(e) and e <= e_max and s <= s_max
                                  and usable_topup(p, MAIN))

    codes = {v: k for k, v in NAMES.items()}
    with open(RESULTS / "validation" / "floodplain_strata.csv", encoding="utf-8") as fh:
        fp_areas = {codes[r["stratum"]]: dict(
                        mapped=float(r["floodplain_mapped_ha"]),
                        eligible=float(r["floodplain_screened_eligible_ha"]))
                    for r in csv.DictReader(fh) if r["cutoff"] == MAIN}
    map_areas = load_strata()

    effect = []
    base = estimate_with(points, {}, fp_areas, map_areas)
    for reader in readings:
        override = {} if reader == "first" else {
            to_point[rid]: lab for rid, lab in readings[reader].items()}
        res = base if reader == "first" else estimate_with(points, override,
                                                           fp_areas, map_areas)
        for (scope, layer, variant), (val, se) in res.items():
            b_val = base[(scope, layer, variant)][0]
            effect.append(dict(labels=reader if reader == "first"
                               else f"first, with {reader} on the relabelled points",
                               scope=scope, layer=layer, variant=variant,
                               flood_area_ha=round(val), se=round(se),
                               change_from_first_ha=round(val - b_val)))
    write_csv(SECOND / "effect.csv", effect)

    print(f"\n  Open-water flood, whole {MAIN} floodplain, by whose labels:")
    for r in effect:
        if (r["scope"], r["layer"], r["variant"]) == ("floodplain", "whole", "W only"):
            print(f"    {r['labels']:<46} {r['flood_area_ha']:>9,} +/- {r['se']:,}"
                  f"   change {r['change_from_first_ha']:+,}")
    print(f"\n  The same with V counted as flood:")
    for r in effect:
        if (r["scope"], r["layer"], r["variant"]) == ("floodplain", "whole", "W or V"):
            print(f"    {r['labels']:<46} {r['flood_area_ha']:>9,} +/- {r['se']:,}"
                  f"   change {r['change_from_first_ha']:+,}")
    print("\n  Claude's labels are an AI's reading of the chips, not a second person's.")
    print(f"\n  wrote agreement.csv and effect.csv to {SECOND}")


if __name__ == "__main__":
    main()
