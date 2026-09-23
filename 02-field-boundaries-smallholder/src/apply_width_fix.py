"""
RS-02. Replace every published parcel width with the ground width.

`grid_check.py` found that Slovenia's chips carry pixels 4.138 m across and
6.002 m tall, and `width_ground.py` measured what that cost: a median parcel
width of 22.0 m where the ground figure is 30.4 m, and 2,280 of 6,831 parcels
sorted into the wrong band. India is unaffected, 1.002x, because its chips were
built square on the ground.

Width is a property of the labelled parcel rather than of any method, so it is
identical in every table that carries it and can be corrected in all of them
from one measurement. That is what this does, which is why fixing this costs
minutes rather than the hours a re-segmentation would.

`width_native_px` is a width in units of 10 m, so the corrected value is the
ground width over ten. Every file keeps its old column under
`width_native_px_published` so the two can be compared afterwards rather than
taken on trust.

Run `width_ground.py` for the country first. This rewrites files in place.

    python src\\apply_width_fix.py --country slovenia
    python src\\apply_width_fix.py --country india
    python src\\apply_width_fix.py --country slovenia --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="slovenia")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    import pandas as pd

    ground = F.RESULTS / "parcel_width_ground.csv"
    if not ground.exists():
        sys.exit(f"{ground} not found. Run width_ground.py --country "
                 f"{args.country} first.")
    g = pd.read_csv(ground)
    g["width_fixed"] = (g["width_ground_m"] / 10.0).round(3)
    lookup = g.set_index(["chip", "parcel_id"])["width_fixed"]

    print(RULE)
    print(f"APPLYING GROUND WIDTHS, {F.COUNTRY.upper()}")
    print(RULE)
    print(f"  {len(g):,} parcels measured, median correction "
          f"{g['ratio'].median():.3f}x")
    if args.dry_run:
        print("  dry run, nothing is written\n")
    else:
        print()

    touched, skipped = 0, 0
    for path in sorted(F.RESULTS.glob("*.csv")):
        if path.name in ("parcel_width_ground.csv",):
            continue
        try:
            d = pd.read_csv(path)
        except Exception:                                     # noqa: BLE001
            continue
        if "width_native_px" not in d.columns:
            continue
        if not {"chip", "parcel_id"}.issubset(d.columns):
            print(f"  {path.name}: has a width but no parcel key, skipped")
            skipped += 1
            continue
        if "width_native_px_published" in d.columns:
            print(f"  {path.name}: already corrected, skipped")
            skipped += 1
            continue

        key = list(zip(d["chip"], d["parcel_id"]))
        fixed = lookup.reindex(key)
        missing = int(fixed.isna().sum())
        d["width_native_px_published"] = d["width_native_px"]
        d["width_native_px"] = fixed.to_numpy()
        # a parcel the ground measurement never saw keeps its old number
        # rather than turning into a blank
        d.loc[d["width_native_px"].isna(), "width_native_px"] = \
            d.loc[d["width_native_px"].isna(), "width_native_px_published"]

        note = f", {missing:,} kept their old width" if missing else ""
        print(f"  {path.name}: {len(d):,} rows{note}")
        if not args.dry_run:
            d.to_csv(path, index=False)
        touched += 1

    print(f"\n  {touched} file(s) {'would be ' if args.dry_run else ''}"
          f"corrected, {skipped} skipped")
    print("\n" + RULE)
    print("Now rerun build_comparison.py, then check_tables.py, then reread")
    print("every width band in COMPARISON.md. The recall figures do not move,")
    print("because no width enters them. What moves is which band each parcel")
    print("was counted in, and therefore every table cut by width.")
    print(RULE)


if __name__ == "__main__":
    main()
