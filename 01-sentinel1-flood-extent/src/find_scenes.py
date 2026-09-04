"""
RS-01 / step 1 — find the Sentinel-1 scenes for a Sen1Floods11 event.

Sen1Floods11 gives us, per event, the S1 acquisition date, the orbit direction
and the relative orbit number. To map a flood we need TWO acquisitions on the
SAME relative orbit: the flood one, and a dry reference from before the event.
Same relative orbit matters because backscatter depends on incidence angle and
look direction -- comparing across orbits compares apples to pears.

This script searches two STAC APIs so you can pick your access route:

  * Planetary Computer  sentinel-1-rtc   radiometrically terrain-corrected,
                                         analysis-ready, needs a free MPC
                                         account for the SAS token at READ time
                                         (searching is anonymous)
  * Earth Search        sentinel-1-grd   anonymous, but NOT terrain corrected

Usage
-----
    python find_scenes.py                       # India event, default windows
    python find_scenes.py --event Bolivia
    python find_scenes.py --pre-days 60         # widen the dry-reference window

Requires: pystac-client (pip install pystac-client)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from pystac_client import Client

MPC = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"

# Sen1Floods11 event table, transcribed from Sen1Floods11_Metadata.geojson
# (location, ISO, S1 date, orbit direction, relative orbit, hand-labelled val chips)
EVENTS = {
    "India":     dict(iso="IND", s1="2016-08-12", orbit="descending", rel=77,  val=68,
                      bbox=[92.1507, 24.8471, 94.1634, 28.2848]),
    "USA":       dict(iso="USA", s1="2019-05-22", orbit="ascending",  rel=136, val=69),
    "Paraguay":  dict(iso="PRY", s1="2018-10-31", orbit="descending", rel=68,  val=67),
    "Ghana":     dict(iso="GHA", s1="2018-09-18", orbit="ascending",  rel=147, val=53),
    "Sri-Lanka": dict(iso="LKA", s1="2017-05-30", orbit="descending", rel=19,  val=42),
    "Spain":     dict(iso="ESP", s1="2019-09-17", orbit="descending", rel=110, val=30),
    "Cambodia":  dict(iso="KHM", s1="2018-08-05", orbit="ascending",  rel=26,  val=30),
    "Pakistan":  dict(iso="PAK", s1="2017-06-28", orbit="descending", rel=5,   val=28),
    "Somalia":   dict(iso="SOM", s1="2018-05-07", orbit="ascending",  rel=116, val=26),
    "Nigeria":   dict(iso="NGA", s1="2018-09-21", orbit="ascending",  rel=103, val=18),
    "Bolivia":   dict(iso="BOL", s1="2018-02-15", orbit="descending", rel=156, val=15),
    "Colombia":  dict(iso="COL", s1="2018-08-22", orbit="ascending",  rel=106, val=0),
}


def search(api_url: str, collection: str, bbox, start, end, sign_note=""):
    """Run one STAC search and return items sorted by datetime."""
    client = Client.open(api_url)
    items = list(
        client.search(
            collections=[collection],
            bbox=bbox,
            datetime=f"{start}/{end}",
        ).items()
    )
    items.sort(key=lambda i: i.datetime)
    return items


def describe(item):
    p = item.properties
    return dict(
        id=item.id,
        datetime=item.datetime.strftime("%Y-%m-%d %H:%M"),
        orbit_state=p.get("sat:orbit_state") or p.get("sar:pass_direction"),
        rel_orbit=p.get("sat:relative_orbit"),
        polarisations=p.get("sar:polarizations") or p.get("s1:polarizations"),
        mode=p.get("sar:instrument_mode"),
        platform=p.get("platform"),
    )


def report(title, items, rel_orbit):
    print(f"\n{title}")
    print("-" * len(title))
    if not items:
        print("  no items returned")
        return
    matching = [i for i in items if describe(i)["rel_orbit"] == rel_orbit]
    print(f"  {len(items)} item(s) in window, {len(matching)} on relative orbit {rel_orbit}")
    for i in items:
        d = describe(i)
        flag = "  <-- same orbit" if d["rel_orbit"] == rel_orbit else ""
        print(
            f"  {d['datetime']}  rel_orbit={d['rel_orbit']!s:>4}  "
            f"{str(d['orbit_state']):<11} {str(d['polarisations']):<18} {d['id']}{flag}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default="India", choices=sorted(EVENTS))
    ap.add_argument("--pre-days", type=int, default=36,
                    help="how far back to look for a dry reference (default 36 = 3 S1A revisits)")
    ap.add_argument("--pad-days", type=int, default=2,
                    help="window either side of the flood acquisition")
    ap.add_argument("--out", default="results/scenes.json")
    args = ap.parse_args()

    ev = EVENTS[args.event]
    if "bbox" not in ev:
        raise SystemExit(
            f"No bbox stored for {args.event}. Read it from Sen1Floods11_Metadata.geojson "
            "(clone github.com/cloudtostreet/Sen1Floods11) and add it to EVENTS."
        )

    flood_date = datetime.strptime(ev["s1"], "%Y-%m-%d")
    bbox = ev["bbox"]

    print(f"Event: {args.event}  ({ev['iso']})")
    print(f"  flood acquisition : {ev['s1']}  {ev['orbit']}  relative orbit {ev['rel']}")
    print(f"  hand-labelled val chips: {ev['val']}")
    print(f"  bbox              : {bbox}")

    windows = {
        "FLOOD": (
            (flood_date - timedelta(days=args.pad_days)).strftime("%Y-%m-%d"),
            (flood_date + timedelta(days=args.pad_days)).strftime("%Y-%m-%d"),
        ),
        "DRY REFERENCE": (
            (flood_date - timedelta(days=args.pre_days)).strftime("%Y-%m-%d"),
            (flood_date - timedelta(days=args.pad_days + 1)).strftime("%Y-%m-%d"),
        ),
    }

    found = {}
    for api_name, api_url, collection in [
        ("Planetary Computer", MPC, "sentinel-1-rtc"),
        ("Earth Search", EARTH_SEARCH, "sentinel-1-grd"),
    ]:
        for label, (start, end) in windows.items():
            try:
                items = search(api_url, collection, bbox, start, end)
            except Exception as exc:                      # noqa: BLE001
                print(f"\n{api_name} / {collection} / {label}: search failed -> {exc}")
                continue
            report(f"{api_name} · {collection} · {label} window {start} .. {end}",
                   items, ev["rel"])
            found[f"{collection}|{label}"] = [
                describe(i) for i in items if describe(i)["rel_orbit"] == ev["rel"]
            ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"event": args.event, **ev, "scenes": found}, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
