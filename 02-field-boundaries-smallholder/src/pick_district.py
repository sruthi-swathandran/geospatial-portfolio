"""
RS-02 stage 3. Work out which district to run end to end.

The district has to satisfy two conditions at once. FTW must have labelled
chips inside it, so the district run can be checked against hand-drawn parcels
rather than against nothing. And its parcels have to be small enough that the
three-pixel width threshold from stage 2 bites, because running this where
fields are large would show the method working and teach us nothing.

This settles the first condition. It reads FTW's own chip index, puts each
chip on a district, and counts them per district by split.

District polygons come from geoBoundaries, CC BY 4.0, used only to cut the
study area. Any open district layer would substitute.

    python src\\pick_district.py
    python src\\pick_district.py --schema-only
    python src\\pick_district.py --simplified
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

# source.coop taught us that a default urllib User-Agent gets refused.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")

API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"
ISO = {"india": "IND", "slovenia": "SVN", "kenya": "KEN", "brazil": "BRA",
       "rwanda": "RWA", "france": "FRA", "germany": "DEU", "spain": "ESP"}

BOUNDARY_DIR = F.PROJECT / "data" / "boundaries"


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(url, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"    cached {dest.name}, {dest.stat().st_size / 1e6:.1f} MB")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"    downloading {dest.name}")
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as fh:
        shutil.copyfileobj(r, fh)
    print(f"    wrote {dest.name}, {dest.stat().st_size / 1e6:.1f} MB")
    return dest


def boundaries(iso: str, level: str, simplified: bool):
    """Fetch one admin level from geoBoundaries and return it as a GeoDataFrame."""
    import geopandas as gpd
    meta = get_json(API.format(iso=iso, level=level))
    if isinstance(meta, list):
        meta = meta[0]
    key = "simplifiedGeometryGeoJSON" if simplified else "gjDownloadURL"
    url = meta.get(key) or meta.get("gjDownloadURL")
    print(f"  {level}: {meta.get('boundaryName', iso)} "
          f"release {meta.get('boundaryYearRepresented', '?')}")
    print(f"    licence {meta.get('boundaryLicense', '?')}, "
          f"source {meta.get('boundarySourceURL', '?')}")
    path = BOUNDARY_DIR / f"{iso}_{level}{'_simple' if simplified else ''}.geojson"
    fetch(url, path)
    gdf = gpd.read_file(path)
    print(f"    {len(gdf):,} polygons, crs {gdf.crs}")
    return gdf


def chip_index():
    """FTW's own chip index, as points, whatever shape the parquet is in."""
    import geopandas as gpd
    import pandas as pd

    paths = sorted(F.DATA.glob("chips_*.parquet"))
    if not paths:
        sys.exit(f"no chips_*.parquet under {F.DATA}")
    path = paths[0]
    print(f"  reading {path.name}")

    try:
        gdf = gpd.read_parquet(path)
        print(f"    geoparquet, {len(gdf):,} rows, crs {gdf.crs}")
        print(f"    columns: {list(gdf.columns)}")
        return gdf
    except Exception as exc:                                  # noqa: BLE001
        print(f"    not geoparquet ({type(exc).__name__}), trying pandas")

    df = pd.read_parquet(path)
    print(f"    {len(df):,} rows")
    print(f"    columns: {list(df.columns)}")
    print(f"    dtypes:\n{df.dtypes.to_string()}")
    print(f"\n    first row:\n{df.iloc[0].to_string()}\n")

    from shapely import from_wkb, from_wkt
    from shapely.geometry import box

    for col in df.columns:
        if col.lower() not in ("geometry", "geom", "wkb", "wkt"):
            continue
        sample = df[col].iloc[0]
        try:
            geom = (from_wkb(df[col]) if isinstance(sample, (bytes, bytearray))
                    else from_wkt(df[col]))
        except Exception:                                     # noqa: BLE001
            continue
        return gpd.GeoDataFrame(df.drop(columns=[col]), geometry=geom,
                                crs="EPSG:4326")

    lower = {c.lower(): c for c in df.columns}
    corners = ("minx", "miny", "maxx", "maxy")
    if all(c in lower for c in corners):
        geom = [box(*vals) for vals in
                zip(*(df[lower[c]] for c in corners))]
        return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")

    sys.exit("could not find a geometry in this parquet. "
             "Paste the columns printed above and I will adapt the script.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="", help="override FTW_COUNTRY")
    ap.add_argument("--iso", default="", help="override the ISO3 code")
    ap.add_argument("--simplified", action="store_true",
                    help="use the simplified boundary geometry, smaller file")
    ap.add_argument("--schema-only", action="store_true",
                    help="print the chip index schema and stop")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()
    if args.country:
        import importlib
        import os
        os.environ["FTW_COUNTRY"] = args.country
        importlib.reload(F)

    try:
        import geopandas                                      # noqa: F401
    except ImportError:
        sys.exit("geopandas is needed here.\n"
                 "  pip install geopandas pyogrio")

    print(RULE)
    print(f"WHERE FTW PUT ITS {F.COUNTRY.upper()} CHIPS")
    print(RULE)

    chips = chip_index()
    if args.schema_only:
        return

    split_col = next((c for c in chips.columns
                      if c.lower() in ("split", "subset", "partition")), None)
    if split_col:
        print(f"  split column '{split_col}': "
              f"{chips[split_col].value_counts().to_dict()}")
    else:
        print("  no split column, counting every chip together")

    iso = args.iso or ISO.get(F.COUNTRY, "")
    if not iso:
        sys.exit(f"no ISO3 code for {F.COUNTRY}, pass --iso")

    print(f"\n  boundaries for {iso}")
    adm2 = boundaries(iso, "ADM2", args.simplified)
    adm1 = boundaries(iso, "ADM1", args.simplified)

    import geopandas as gpd
    import pandas as pd

    if chips.crs is None:
        chips = chips.set_crs("EPSG:4326")
    chips = chips.to_crs(adm2.crs)

    pts = chips.copy()
    pts["geometry"] = pts.geometry.representative_point()

    joined = gpd.sjoin(pts, adm2[["shapeName", "geometry"]],
                       how="left", predicate="within")
    joined = joined.rename(columns={"shapeName": "district"})
    lost = int(joined["district"].isna().sum())

    d_pts = adm2.copy()
    d_pts["geometry"] = d_pts.geometry.representative_point()
    d_state = gpd.sjoin(d_pts[["shapeName", "geometry"]],
                        adm1[["shapeName", "geometry"]],
                        how="left", predicate="within",
                        lsuffix="d", rsuffix="s")
    state_of = dict(zip(d_state["shapeName_d"], d_state["shapeName_s"]))

    id_col = next((c for c in chips.columns
                   if c.lower() in ("aoi_id", "id", "chip", "name")), None)
    if id_col:
        per_chip = joined[[id_col, "district"]].copy()
        per_chip["state"] = [state_of.get(d, "")
                             for d in per_chip["district"]]
        if split_col:
            per_chip["split"] = joined[split_col].values
        per_chip = per_chip.rename(columns={id_col: "aoi_id"})
        p = F.RESULTS / "chip_district.csv"
        per_chip.to_csv(p, index=False)
        print(f"  wrote {p.relative_to(F.PROJECT)}")

    if split_col:
        table = (joined.groupby(["district", split_col]).size()
                 .unstack(fill_value=0))
    else:
        table = joined.groupby("district").size().to_frame("chips")
    table["total"] = table.sum(axis=1)
    table.insert(0, "state", [state_of.get(d, "") for d in table.index])

    sort_on = "test" if "test" in table.columns else "total"
    table = table.sort_values(sort_on, ascending=False)

    print("\n" + RULE)
    print(f"CHIPS PER DISTRICT, sorted by {sort_on}")
    print(RULE)
    print(table.head(args.top).to_string())
    if lost:
        print(f"\n  {lost:,} chips fell outside every district polygon. "
              f"Coastal chips do this when the boundary is simplified.")

    out = F.RESULTS / "chips_by_district.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("A district needs enough test chips to check the run against, so")
    print("read the test column rather than the total. Send me the top rows")
    print("and I will look up landholding size for those districts before we")
    print("commit to one.")
    print(RULE)


if __name__ == "__main__":
    main()