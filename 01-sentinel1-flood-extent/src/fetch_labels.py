"""
RS-01 / step 2 — get the Sen1Floods11 hand labels for the India event.

Updated after seeing the real bucket layout. Beyond the imagery and the labels,
the bucket carries two things worth taking:

  S1OtsuLabelHand   the dataset authors' OWN Otsu thresholding output for these
                    exact chips. Comparing your implementation against their
                    result on identical inputs is a far stronger claim than
                    quoting an IoU from the paper, because it removes every
                    question about differing evaluation protocol.

  splits/flood_handlabeled/*.csv
                    the official train / valid / test split. Using it is what
                    makes your numbers comparable to published work instead of
                    comparable to nothing.

JRCWaterHand gives per-chip permanent water, so permanent-water separation can
be validated without a second trip to the JRC collection. S2Hand is the optical
view of the same chip — the evidence for "SAR missed this flooded area", which
is a claim you want a picture for.

Usage
-----
    python src\\fetch_labels.py                       # list only (cached after first run)
    python src\\fetch_labels.py --download --limit 3  # smoke test, 3 chips
    python src\\fetch_labels.py --download            # all 68 chips, all layers
    python src\\fetch_labels.py --footprints          # rebuild the footprint GeoJSON
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, LABELS_DIR, RESULTS          # noqa: E402

BUCKET = "sen1floods11"
LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
GET_URL = f"https://storage.googleapis.com/{BUCKET}/{{name}}"

# Layer -> why we want it
LAYERS = {
    "S1Hand":           "Sentinel-1 VV+VH for the chip — the model input",
    "LabelHand":        "hand-drawn ground truth — the thing we score against",
    "S1OtsuLabelHand":  "the authors' own Otsu result — our comparison baseline",
    "JRCWaterHand":     "JRC permanent water for the chip",
    "S2Hand":           "Sentinel-2 optical — visual evidence for missed flooding",
}
DEFAULT_LAYERS = list(LAYERS)

SPLITS_PREFIX = "v1.1/splits/flood_handlabeled/"
SPLITS_DIR = LABELS_DIR / "splits"


def list_all(prefix: str = "") -> list[dict]:
    items, token, page = [], None, 0
    while True:
        params = {"maxResults": 1000,
                  "fields": "items(name,size),nextPageToken",
                  "prefix": prefix}
        if token:
            params["pageToken"] = token
        r = requests.get(LIST_URL, params=params, timeout=60)
        r.raise_for_status()
        payload = r.json()
        items += payload.get("items", [])
        page += 1
        print(f"\r  listed {len(items):,} objects ({page} pages)", end="", flush=True)
        token = payload.get("nextPageToken")
        if not token:
            break
    print()
    return items


def collect(items: list[dict], layers: list[str]) -> dict[str, dict[str, dict]]:
    """{chip_id: {layer: object}} for this event only."""
    chips: dict[str, dict[str, dict]] = defaultdict(dict)
    for obj in items:
        base = obj["name"].rsplit("/", 1)[-1]
        if not base.startswith(f"{EVENT}_") or not base.endswith(".tif"):
            continue
        stem = base[:-4]
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        chip_id, layer = parts[1], "_".join(parts[2:])
        if layer in layers:
            chips[chip_id][layer] = obj
    return chips


def report(chips: dict[str, dict[str, dict]], layers: list[str]) -> None:
    print(f"\n{EVENT}: {len(chips)} chip ids")
    total = 0
    for layer in layers:
        present = [c for c in chips.values() if layer in c]
        size = sum(int(c[layer].get("size", 0)) for c in present)
        total += size
        print(f"  {layer:<18} {len(present):>3} chips  {size/1e6:>8.1f} MB   {LAYERS[layer]}")
    print(f"  {'TOTAL':<18} {'':>3}         {total/1e6:>8.1f} MB")

    incomplete = [c for c, v in chips.items() if len(v) < len(layers)]
    if incomplete:
        print(f"\n  {len(incomplete)} chip(s) missing at least one layer: "
              f"{', '.join(sorted(incomplete)[:8])}")


def fetch(url: str, dest: Path, expect: int | None = None) -> None:
    if dest.exists() and (expect is None or dest.stat().st_size == expect):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for block in r.iter_content(1 << 20):
                fh.write(block)


def download_splits() -> None:
    print(f"\nSplit definitions -> {SPLITS_DIR}")
    for obj in list_all(SPLITS_PREFIX):
        name = obj["name"]
        dest = SPLITS_DIR / name.rsplit("/", 1)[-1]
        fetch(GET_URL.format(name=name), dest, int(obj.get("size", 0)))
        rows = dest.read_text().splitlines()
        ours = [r for r in rows if r.startswith(f"{EVENT}_")]
        print(f"  {dest.name:<34} {len(rows):>5} rows, {len(ours):>3} for {EVENT}")


def download_chips(chips, layers, limit) -> None:
    ids = sorted(chips)[:limit] if limit else sorted(chips)
    print(f"\nDownloading {len(ids)} chip(s) x {len(layers)} layer(s) -> {LABELS_DIR}")
    for i, chip_id in enumerate(ids, 1):
        for layer in layers:
            obj = chips[chip_id].get(layer)
            if not obj:
                continue
            name = obj["name"]
            dest = LABELS_DIR / layer / name.rsplit("/", 1)[-1]
            fetch(GET_URL.format(name=name), dest, int(obj.get("size", 0)))
        print(f"\r  {i}/{len(ids)} chips", end="", flush=True)
    print("\ndone")


def build_footprints() -> None:
    import geopandas as gpd
    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import box

    files = sorted((LABELS_DIR / "S1Hand").glob(f"{EVENT}_*_S1Hand.tif"))
    if not files:
        raise SystemExit(f"No chips in {LABELS_DIR / 'S1Hand'} — run --download first.")

    # which split each chip belongs to, if the split files were downloaded
    split_of: dict[str, str] = {}
    for csv_path in sorted(SPLITS_DIR.glob("*.csv")):
        split_name = csv_path.stem
        for row in csv.reader(csv_path.read_text().splitlines()):
            if row and row[0].startswith(f"{EVENT}_"):
                split_of[row[0].split("_")[1]] = split_name

    rows = []
    for f in files:
        chip_id = f.name.split("_")[1]
        with rasterio.open(f) as src:
            w, s, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            rows.append({
                "chip_id": chip_id,
                "split": split_of.get(chip_id, "unknown"),
                "crs": str(src.crs),
                "width": src.width,
                "height": src.height,
                "bands": src.count,
                "dtype": src.dtypes[0],
                "res_m": round(abs(src.transform.a), 2),
                "geometry": box(w, s, e, n),
            })

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    out = RESULTS / "label_chip_footprints.geojson"
    gdf.to_file(out, driver="GeoJSON")

    b = gdf.total_bounds
    print(f"\n{len(gdf)} chips -> {out}")
    print(f"combined bounds : {b[0]:.4f} {b[1]:.4f} {b[2]:.4f} {b[3]:.4f}")
    print(f"span            : {b[2]-b[0]:.2f}° lon x {b[3]-b[1]:.2f}° lat")
    print(f"chip CRS        : {sorted(set(gdf['crs']))}")
    print(f"chip size / res : {sorted(set(zip(gdf['width'], gdf['height'])))} @ "
          f"{sorted(set(gdf['res_m']))} m")
    print(f"S1 bands        : {sorted(set(gdf['bands']))} ({sorted(set(gdf['dtype']))})")
    print("\nsplit membership:")
    for split, count in gdf["split"].value_counts().items():
        print(f"  {split:<28} {count}")
    print("\nThat combined bounding box is the AOI the imagery pipeline covers.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--footprints", action="store_true")
    ap.add_argument("--layers", nargs="+", default=DEFAULT_LAYERS, choices=list(LAYERS))
    args = ap.parse_args()

    if args.footprints and not args.download:
        build_footprints()
        return

    cache = LABELS_DIR / "_bucket_listing.json"
    if cache.exists():
        print(f"Using cached listing: {cache.name}")
        items = json.loads(cache.read_text())["items"]
    else:
        print(f"Listing {BUCKET}:")
        items = list_all()
        cache.write_text(json.dumps({"bucket": BUCKET, "items": items}))

    chips = collect(items, args.layers)
    report(chips, args.layers)

    if args.download:
        download_splits()
        download_chips(chips, args.layers, args.limit)
        build_footprints()
    else:
        print("\nNothing downloaded. Re-run with --download.")


if __name__ == "__main__":
    main()
