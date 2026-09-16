"""
RS-02 stage 3. Profile the candidate districts using FTW's own labels.

The Agriculture Census would give holding size per district, but its portal
refuses automated requests and an operational holding is a legal unit that can
be several separated parcels. Closer to the question is something we already
own: every labelled parcel in FTW India has been measured here, for width
across and for whether the model found it.

So this joins the chip-to-district mapping onto those measurements and reports
per district how narrow the parcels are and how the model did on them. A
district worth running end to end has enough test chips to check against and
parcels narrow enough that the three-pixel threshold bites.

Width and recall are computed from separate tables and merged afterwards, so a
mismatch in parcel numbering between them cannot silently drop rows.

    python src\\district_profile.py
    python src\\district_profile.py --min-test 5 --min-parcels 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def load(name: str) -> pd.DataFrame:
    p = F.RESULTS / name
    if not p.exists():
        sys.exit(f"{p} not found")
    df = pd.read_csv(p)
    print(f"  {name}: {len(df):,} rows")
    print(f"    columns: {list(df.columns)}")
    return df


def find_col(df, *needles, label=""):
    for n in needles:
        for c in df.columns:
            if n in c.lower():
                return c
    sys.exit(f"no column matching {needles} in {label}: {list(df.columns)}")


def chip_key(s: pd.Series) -> pd.Series:
    """Chip names carry .tif in the score tables and not in the chip index."""
    return s.astype(str).str.replace(r"\.tif$", "", regex=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="")
    ap.add_argument("--classes", type=int, default=3)
    ap.add_argument("--tag", default="_full")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--narrow-px", type=float, default=3.0,
                    help="the width threshold from stage 2, native pixels")
    ap.add_argument("--min-test", type=int, default=4)
    ap.add_argument("--min-parcels", type=int, default=15)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    if args.country:
        import importlib
        import os
        os.environ["FTW_COUNTRY"] = args.country
        importlib.reload(F)

    print(RULE)
    print(f"DISTRICT PROFILE, {F.COUNTRY}, "
          f"{args.classes}-class{args.tag}")
    print(RULE)

    cd = load("chip_district.csv")
    sc = load(f"score_parcels_{args.classes}class{args.tag}.csv")
    wd = load(f"parcel_width_{args.classes}class{args.tag}.csv")

    cd["key"] = chip_key(cd["aoi_id"])
    cd_small = cd[["key", "district", "state", "split"]].drop_duplicates("key")

    sc["key"] = chip_key(sc[find_col(sc, "chip", label="score table")])
    wd["key"] = chip_key(wd[find_col(wd, "chip", label="width table")])

    if "country" in sc.columns:
        sc = sc[sc["country"] == F.COUNTRY]
    if "country" in wd.columns:
        wd = wd[wd["country"] == F.COUNTRY]

    iou_col = find_col(sc, "iou", label="score table")
    area_col = find_col(sc, "native", "area", label="score table")
    w_col = find_col(wd, "width", label="width table")

    sc = sc.merge(cd_small, on="key", how="left")
    wd = wd.merge(cd_small, on="key", how="left")
    print(f"\n  parcels with a district: "
          f"{int(sc['district'].notna().sum()):,} of {len(sc):,} scored, "
          f"{int(wd['district'].notna().sum()):,} of {len(wd):,} measured")

    chips = (cd[cd["split"] == "test"].groupby("district")
             .size().rename("test_chips"))

    g = sc.dropna(subset=["district"]).groupby("district")
    recall = pd.DataFrame({
        "state": g["state"].first(),
        "parcels": g.size(),
        "median_area_px": g[area_col].median().round(1),
        "median_iou": g[iou_col].median().round(3),
        "recall": g[iou_col].apply(lambda s: (s >= args.iou).mean()).round(3),
    })

    gw = wd.dropna(subset=["district"]).groupby("district")
    width = pd.DataFrame({
        "median_width_px": gw[w_col].median().round(2),
        "share_narrow": gw[w_col].apply(
            lambda s: (s < args.narrow_px).mean()).round(3),
    })

    out = (recall.join(width, how="outer").join(chips, how="outer")
           .fillna({"test_chips": 0}))
    out["test_chips"] = out["test_chips"].astype(int)
    out = out[["state", "test_chips", "parcels", "median_width_px",
               "share_narrow", "median_area_px", "median_iou", "recall"]]

    print("\n" + RULE)
    print("BY TEST CHIPS")
    print(RULE)
    print(out.sort_values("test_chips", ascending=False)
          .head(args.top).to_string())

    keep = out[(out["test_chips"] >= args.min_test)
               & (out["parcels"] >= args.min_parcels)]
    print("\n" + RULE)
    print(f"NARROWEST FIRST, among districts with at least "
          f"{args.min_test} test chips and {args.min_parcels} parcels")
    print(RULE)
    if keep.empty:
        print("  nothing clears both floors. Lower --min-test or "
              "--min-parcels and look again.")
    else:
        print(keep.sort_values("median_width_px").head(args.top).to_string())

    by_state = (sc.dropna(subset=["district"]).groupby("state")
                .agg(parcels=(iou_col, "size"),
                     median_iou=(iou_col, "median"),
                     recall=(iou_col, lambda s: (s >= args.iou).mean()))
                .round(3).sort_values("parcels", ascending=False))
    print("\n" + RULE)
    print("BY STATE, for the sampling question")
    print(RULE)
    print(by_state.head(15).to_string())

    p = F.RESULTS / "district_profile.csv"
    out.to_csv(p)
    print(f"\n  wrote {p.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("Two things to read here. Whether any district has both enough test")
    print("chips and parcels narrow enough to be worth the run, and whether")
    print("FTW's Indian sample sits mostly in large-parcel states. The second")
    print("changes how the stage 2 numbers should be reported.")
    print(RULE)


if __name__ == "__main__":
    main()