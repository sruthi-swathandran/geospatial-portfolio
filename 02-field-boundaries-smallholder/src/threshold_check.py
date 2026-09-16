"""
RS-02 stage 3. Put a confidence interval on the width threshold.

Per-district recall rests on twenty to fifty parcels, which is too few to
carry a claim. Pooling the districts whose parcels are narrow gives a number
that can be stated. This also checks what India's recall looks like without
Rajasthan, which supplies a quarter of the test parcels on its own.

Intervals are Clopper-Pearson, which is exact and does not fall apart when the
count is zero, where a normal approximation would report an interval of zero
width and say nothing.

    python src\\threshold_check.py --country india
    python src\\threshold_check.py --country india --cut 3.5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def ci(found: int, total: int, alpha: float = 0.05):
    """Clopper-Pearson interval for a proportion."""
    from scipy.stats import beta
    if total == 0:
        return float("nan"), float("nan")
    lo = 0.0 if found == 0 else beta.ppf(alpha / 2, found, total - found + 1)
    hi = (1.0 if found == total
          else beta.ppf(1 - alpha / 2, found + 1, total - found))
    return float(lo), float(hi)


def line(label: str, found: int, total: int):
    lo, hi = ci(found, total)
    rate = found / total if total else float("nan")
    print(f"  {label:<44} {found:>5,} / {total:>5,}  "
          f"{rate * 100:5.2f}%  [{lo * 100:4.2f}, {hi * 100:5.2f}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width-file", default="",
                    help="read this file instead of the FTW-named one")
    ap.add_argument("--country", default="india")
    ap.add_argument("--classes", type=int, default=3)
    ap.add_argument("--tag", default="_full")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--cut", type=float, default=3.25,
                    help="district median width that defines a narrow district")
    ap.add_argument("--parcel-cut", type=float, default=3.0,
                    help="parcel width that defines a narrow parcel")
    args = ap.parse_args()

    import importlib
    import os
    os.environ["FTW_COUNTRY"] = args.country
    importlib.reload(F)

    wname = (args.width_file
             or f"parcel_width_{args.classes}class{args.tag}.csv")
    wd = pd.read_csv(F.RESULTS / wname)
    cd = pd.read_csv(F.RESULTS / "chip_district.csv")
    cd["key"] = cd["aoi_id"].astype(str)
    wd["key"] = wd["chip"].astype(str).str.replace(r"\.tif$", "", regex=True)
    if "country" in wd.columns:
        wd = wd[wd["country"] == F.COUNTRY]
    df = wd.merge(cd[["key", "district", "state"]].drop_duplicates("key"),
                  on="key", how="left")
    missing = int(df["district"].isna().sum())
    if missing:
        print(f"  {missing:,} parcels have no district and are dropped")
        df = df.dropna(subset=["district"])

    df["hit"] = df["best_iou"] >= args.iou
    med = df.groupby("district")["width_native_px"].median()
    narrow_districts = sorted(med[med <= args.cut].index)

    print(RULE)
    print(f"{F.COUNTRY.upper()}, {args.classes}-class{args.tag}, "
          f"recall at IoU {args.iou}")
    print(RULE)
    print(f"  {'':<44} {'found':>5}   {'of':>5}   rate    95% interval")

    line("all parcels", int(df["hit"].sum()), len(df))

    raj = df[df["state"].str.contains("jasth", na=False)]
    rest = df[~df["state"].str.contains("jasth", na=False)]
    line("Rajasthan only", int(raj["hit"].sum()), len(raj))
    line("everything except Rajasthan", int(rest["hit"].sum()), len(rest))

    nd = df[df["district"].isin(narrow_districts)]
    line(f"districts with median width <= {args.cut} px",
         int(nd["hit"].sum()), len(nd))

    narrow = df[df["width_native_px"] < args.parcel_cut]
    wide = df[df["width_native_px"] >= args.parcel_cut]
    line(f"parcels narrower than {args.parcel_cut} px",
         int(narrow["hit"].sum()), len(narrow))
    line(f"parcels {args.parcel_cut} px and wider",
         int(wide["hit"].sum()), len(wide))

    print(f"\n  narrow districts ({len(narrow_districts)}): "
          f"{', '.join(narrow_districts)}")

    print("\n" + RULE)
    print("WIDTH BANDS, ALL INDIA")
    print(RULE)
    edges = [0, 2, 3, 4, 5, 7, 10, np.inf]
    labels = ["<2", "2 to 3", "3 to 4", "4 to 5", "5 to 7", "7 to 10", "10+"]
    df["band"] = pd.cut(df["width_native_px"], edges, labels=labels,
                        right=False)
    for name, grp in df.groupby("band", observed=True):
        line(f"width {name} native px", int(grp["hit"].sum()), len(grp))

    print("\n" + RULE)
    print("An interval that includes zero at the top is the claim worth")
    print("making. A rate of 0 on 25 parcels says little; the same rate on")
    print("250 says the floor is real.")
    print(RULE)


if __name__ == "__main__":
    main()