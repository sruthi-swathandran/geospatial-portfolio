"""
RS-01 / step 11c - what else flew over this AOI while the flood was up?

The 12 August map covers 6.26 of the 7.75 million hectares in the AOI, about
81%. The missing wedge on the eastern side is where the three frames on
relative orbit 77 end.

Filling it means a different relative orbit, and a different orbit means a
different day. That is the whole problem. A flood moves over days, so mosaicking
two orbits into one picture produces a map where nobody can tell which part is
which date, and every hectare figure downstream inherits the confusion silently.

So the plan is not to mosaic. It is to map each acquisition separately, publish
both with their dates on them, and let the difference between them show how the
flood moved. This script is the first half of that: it lists every acquisition
over the AOI in the window and reports two areas per pass.

    covers          how much of the AOI that pass sees
    NEW             how much of that is ground 12 August did not see

A pass with a large NEW figure is worth mapping. A pass that mostly repeats
orbit 77 is a repeat visit, useful for a time series and useless for filling the
gap. Both are legitimate, the table just says which is which.

One caveat this script cannot resolve. A different relative orbit views the
ground at a different incidence angle, and RTC corrects for terrain rather than
for that, so an absolute dB threshold tuned on orbit 77 is not automatically
right on another orbit. Where two passes overlap, comparing their backscatter
over ground that is dry in both is the way to measure the offset. That comes
after we know which pass to use.

Outputs:
    results/swath_candidates.csv

Usage:
    python src\\find_swaths.py
    python src\\find_swaths.py --start 2016-07-25 --end 2016-09-05
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import planetary_computer
import pystac_client
from rasterio.warp import transform_geom
from shapely.geometry import box as sbox, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (                                        # noqa: E402
    BBOX, RESULTS, MPC_STAC, S1_COLLECTION, FLOOD_DATE, RELATIVE_ORBIT,
    TARGET_CRS,
)


def to_utm(geom):
    return shape(transform_geom("EPSG:4326", TARGET_CRS, geom))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-08-01")
    ap.add_argument("--end", default="2016-08-31")
    args = ap.parse_args()

    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    items = list(client.search(collections=[S1_COLLECTION], bbox=BBOX,
                               datetime=f"{args.start}/{args.end}").items())
    print(f"{len(items)} item(s) over the AOI, {args.start} to {args.end}\n")
    if not items:
        raise SystemExit("nothing found, widen the window")

    aoi = to_utm(sbox(*BBOX).__geo_interface__)
    aoi_ha = aoi.area / 10_000.0

    groups = defaultdict(list)
    for it in items:
        p = it.properties
        groups[(it.datetime.date().isoformat(),
                p.get("sat:relative_orbit"),
                p.get("sat:orbit_state"))].append(it)

    ref = None
    for (d, o, _s), its in groups.items():
        if d == FLOOD_DATE and o == RELATIVE_ORBIT:
            ref = unary_union([to_utm(i.geometry) for i in its]).intersection(aoi)
    if ref is None:
        print(f"  WARNING: no reference pass on {FLOOD_DATE} orbit "
              f"{RELATIVE_ORBIT} in this window, so NEW is against nothing")
        ref = sbox(0, 0, 0, 0)
    print(f"AOI {aoi_ha:,.0f} ha; the {FLOOD_DATE} orbit {RELATIVE_ORBIT} pass "
          f"covers {ref.area/10_000.0:,.0f} ha "
          f"({ref.area/10_000.0/aoi_ha:.0%})\n")

    rows = []
    for (d, o, st), its in sorted(groups.items()):
        pol = sorted({tuple(i.properties.get("sar:polarizations") or [])
                      for i in its})
        cover = unary_union([to_utm(i.geometry) for i in its]).intersection(aoi)
        new = cover.difference(ref)
        rows.append({
            "date": d, "relative_orbit": o, "pass": st,
            "frames": len(its),
            "polarisations": "|".join("+".join(p) for p in pol),
            "dual_pol": int(all(len(p) == 2 for p in pol)),
            "covers_ha": round(cover.area / 10_000.0, 1),
            "covers_pct": round(100 * cover.area / aoi.area, 1),
            "new_ha": round(new.area / 10_000.0, 1),
            "new_pct": round(100 * new.area / aoi.area, 1),
            "days_from_event": (__import__("datetime").date.fromisoformat(d)
                                - __import__("datetime").date.fromisoformat(
                                    FLOOD_DATE)).days,
        })

    print(f"{'date':<12}{'d':>5}{'orbit':>7}{'pass':<12}{'n':>3}"
          f"{'pol':<10}{'covers':>12}{'':>7}{'NEW ground':>13}{'':>7}")
    for r in rows:
        mark = "" if r["dual_pol"] else "  VV only"
        print(f"{r['date']:<12}{r['days_from_event']:>+5}"
              f"{r['relative_orbit']:>7}{r['pass']:<12}{r['frames']:>3}"
              f"{r['polarisations']:<10}{r['covers_ha']:>12,.0f}"
              f"{r['covers_pct']:>6.0f}%{r['new_ha']:>13,.0f}"
              f"{r['new_pct']:>6.0f}%{mark}")

    with open(RESULTS / "swath_candidates.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    best = [r for r in rows if r["dual_pol"] and r["new_pct"] > 3
            and abs(r["days_from_event"]) <= 14]
    best.sort(key=lambda r: (-r["new_ha"], abs(r["days_from_event"])))
    print("\nWORTH MAPPING (dual pol, adds ground, within a fortnight)")
    print("---------------------------------------------------------")
    if not best:
        print("  Nothing adds meaningful new ground on a dual-pol pass. The "
              "eastern\n  wedge stays unmapped, and saying so is the result.")
    else:
        for r in best[:6]:
            print(f"  {r['date']}  orbit {r['relative_orbit']:>3}  "
                  f"{r['days_from_event']:+d} days  adds "
                  f"{r['new_ha']:,.0f} ha")
        print("\n  Prefer the smallest day offset that adds real ground. Every "
              "day between\n  the two acquisitions is flood that rose or drained "
              "in between, and that\n  difference will show up as a seam if "
              "anyone mosaics them later.")
        r = best[0]
        print(f"\n  Next: python src\\\\full_scene.py --res 20 --date "
              f"{r['date']} --orbit {r['relative_orbit']} "
              f"--variant {r['date'].replace('-', '')}")


if __name__ == "__main__":
    main()
