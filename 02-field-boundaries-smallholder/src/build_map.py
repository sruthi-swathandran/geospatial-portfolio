"""
RS-02. An interactive map of where each method finds parcels.

Every figure in COMPARISON.md is a country total. This puts the same results
back on the ground: one marker per test chip in India and Slovenia, coloured by
the share of its labelled parcels a method recovered, with the Indian chips
listed by district beside the map.

FTW is shown twice: its v3 checkpoint with an EfficientNet-B7 encoder, the best
public release, and the v1 checkpoint most of the project measured (B-24). The
v3 layer comes from results/<country>/newer_ckpt/, written by
newer_checkpoints.py. The other methods are read at one setting each, the one
whose object count per chip sits nearest FTW v3's, so the map compares like
with like as far as a single setting allows. The headline figures in COMPARISON.md are interpolated to FTW's
exact count and will differ a little from the totals shown here; the page says
which setting each method is at and what it emits. In Slovenia no method other
than FTW was run coarse enough to come near FTW's count (B-08), so the page
labels those layers as clamped.

Inputs are files this project already has: chip footprints from the label
rasters, per-parcel scores from results/, district names from
chip_district.csv, and state outlines from the geoBoundaries files in
data/boundaries/ (CC BY 4.0). Output is one page, docs/index.html, with the
data written into it. It draws on Leaflet from cdnjs and, behind the chips,
the Sentinel-2 cloudless mosaic by EOX (CC BY-NC-SA 4.0), which a viewer can
switch off.

    python src\\build_map.py
"""

from __future__ import annotations

import csv
import importlib
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
PROJECT = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT / "src" / "map_template.html"
DEST = PROJECT / "docs" / "index.html"
BOUNDARIES = {"india": ("IND_ADM1.geojson", 0.02),
              "slovenia": ("SVN_ADM1.geojson", 0.002)}
METHODS = {"ftw3": "FTW v3, EfficientNet-B7",
           "ftw": "FTW v1",
           "sam": "SAM ViT-H, colour infrared",
           "watershed": "watershed"}
V3_KEY = "v3_full_b7"


def use_country(country: str) -> None:
    os.environ["FTW_COUNTRY"] = country
    importlib.reload(F)


def read_csv(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def v3_objects(country: str) -> float:
    """FTW v3 B7's objects per labelled chip, as newer_checkpoints.py counts."""
    rows = read_csv(PROJECT / "results" / country / "newer_ckpt" /
                    f"{V3_KEY}_chips.csv")
    objs = [float(r["objects"]) for r in rows if float(r["parcels"]) > 0]
    return float(np.mean(objs))


def nearest_settings(country: str) -> dict:
    """The setting per method whose objects per chip sit nearest FTW v3's."""
    rd = PROJECT / "results" / country
    sweep = read_csv(rd / "segmenter_comparison_min500.csv")
    v1_objs = float(next(r for r in sweep if r["method"] == "ftw")
                    ["objects_per_chip"])
    ftw_objs = v3_objects(country)
    out = {"ftw3": {"tag": None, "setting": "", "objects": ftw_objs},
           "ftw": {"tag": "ftw", "setting": "", "objects": v1_objs}}

    ws = [r for r in sweep if r["method"] == "watershed"]
    best = min(ws, key=lambda r: abs(float(r["objects_per_chip"]) - ftw_objs))
    out["watershed"] = {
        "tag": "watershed_" + best["setting"].replace(".", "p"),
        "setting": f"h {best['setting']}",
        "objects": float(best["objects_per_chip"])}

    sam = [r for r in read_csv(rd / "sam_comparison_vit_h_min500.csv")
           if r["composite"].lower() == "cir"]
    best = min(sam, key=lambda r: abs(float(r["objects_per_chip"]) - ftw_objs))
    thr = best["setting"].split("/")[0]
    out["sam"] = {
        "tag": "sam_vit_h_cir_" + thr.replace(".", "p"),
        "setting": f"predicted IoU {thr}",
        "objects": float(best["objects_per_chip"])}

    lowest = {"watershed": min(float(r["objects_per_chip"]) for r in ws),
              "sam": min(float(r["objects_per_chip"]) for r in sam)}
    for m in ("watershed", "sam"):
        # clamped when even the coarsest setting emits half again FTW's count
        out[m]["clamped"] = lowest[m] > ftw_objs * 1.5
    out["ftw"]["clamped"] = out["ftw3"]["clamped"] = False
    return out


def per_chip(country: str, tag) -> tuple:
    """{chip: [parcels, found]} and {(chip, parcel): best IoU} for one method."""
    rd = PROJECT / "results" / country
    path = (rd / "newer_ckpt" / f"{V3_KEY}_parcels.csv" if tag is None
            else rd / f"score_parcels_seg_{tag}_min500.csv")
    counts, ious = {}, {}
    for r in read_csv(path):
        c = counts.setdefault(r["chip"], [0, 0])
        c[0] += 1
        c[1] += int(r["found"])
        ious[(r["chip"], int(r["parcel_id"]))] = float(r["best_iou"])
    return counts, ious


def parcel_rings(full: np.ndarray) -> dict:
    """{parcel id: [ring, ...]} with each ring a flat list of pixel corners.

    These are the reconstructed parcels every IoU in the project was scored
    against, traced along pixel edges. Coordinates stay in grid pixels, which
    are whole numbers and so compact; the page places them using the chip's
    footprint. Simplifying to within one grid pixel, about 6 m, keeps the
    page to a size a browser loads quickly; it is a drawing, not the shape
    any score was computed on.
    """
    from rasterio import features
    from shapely.geometry import shape
    out = {}
    for geom, val in features.shapes(full.astype("int32"), mask=full > 0,
                                     connectivity=4):
        poly = shape(geom).simplify(1.0, preserve_topology=True)
        ring = [int(round(v)) for xy in poly.exterior.coords for v in xy]
        if len(ring) >= 8:
            out.setdefault(int(val), []).append(ring)
    return out


def chip_box(chip: str) -> list:
    """The chip's footprint as [west, south, east, north] in degrees."""
    import rasterio
    with rasterio.open(F.INSTANCE / chip) as s:
        if s.crs and s.crs.to_epsg() != 4326:
            from rasterio.warp import transform_bounds
            b = transform_bounds(s.crs, "EPSG:4326", *s.bounds)
        else:
            b = s.bounds
    return [round(float(v), 5) for v in b]


def outline(country: str) -> list:
    """State outlines as rings of [lon, lat], simplified for drawing."""
    from shapely.geometry import shape
    name, tol = BOUNDARIES[country]
    path = PROJECT / "data" / "boundaries" / name
    if not path.exists():
        print(f"  {path.name} not found, the {country} map has no outline")
        return []
    rings = []
    for feat in json.loads(path.read_text(encoding="utf-8"))["features"]:
        geom = shape(feat["geometry"]).simplify(tol, preserve_topology=True)
        polys = getattr(geom, "geoms", [geom])
        for poly in polys:
            if poly.is_empty or poly.area < tol * tol * 4:
                continue
            ring = [[round(x, 3), round(y, 3)]
                    for x, y in poly.exterior.coords]
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def districts() -> dict:
    path = PROJECT / "results" / "india" / "chip_district.csv"
    if not path.exists():
        return {}
    return {r["aoi_id"]: (r["district"], r["state"]) for r in read_csv(path)}


def build_country(country: str) -> dict:
    use_country(country)
    settings = nearest_settings(country)
    scored = {m: per_chip(country, s["tag"]) for m, s in settings.items()}
    counts = {m: v[0] for m, v in scored.items()}
    ious = {m: v[1] for m, v in scored.items()}
    order = list(METHODS)
    pred = PROJECT / "results" / country / "pred_3class_full"
    chips = [p.name for p in sorted(pred.glob("*.tif"))]
    names = districts() if country == "india" else {}

    rows, totals = [], {m: [0, 0] for m in settings}
    for chip in chips:
        box = chip_box(chip)
        lon = round((box[0] + box[2]) / 2, 5)
        lat = round((box[1] + box[3]) / 2, 5)
        stem = chip.rsplit(".", 1)[0]
        n = counts["ftw"].get(chip, [0, 0])[0]
        found = {m: counts[m].get(chip, [0, 0])[1] for m in settings}
        for m in settings:
            totals[m][0] += counts[m].get(chip, [0, 0])[0]
            totals[m][1] += found[m]
        district, state = names.get(stem, ("", ""))
        parcels = []
        if n:
            _, _, _, full = F.load_labels(chip)
            for pid, rings in sorted(parcel_rings(full).items()):
                parcels.append([pid, rings,
                                [round(ious[m].get((chip, pid), 0.0), 2)
                                 for m in order]])
            size = list(full.shape)
        else:
            size = [256, 256]
        rows.append({"id": stem, "lon": lon, "lat": lat, "b": box, "n": n,
                     "f": found, "d": district, "s": state,
                     "sz": size, "p": parcels})

    meta = {m: {"label": METHODS[m], "slot": order.index(m), "setting": s["setting"],
                "objects": round(s["objects"], 1), "clamped": s["clamped"],
                "parcels": totals[m][0], "found": totals[m][1]}
            for m, s in settings.items()}
    return {"chips": rows, "methods": meta, "outline": outline(country)}


def main() -> None:
    if not TEMPLATE.exists():
        sys.exit(f"{TEMPLATE} not found")
    data = {c: build_country(c) for c in ("india", "slovenia")}

    print(RULE)
    print("MAP DATA")
    print(RULE)
    for c, d in data.items():
        labelled = sum(1 for r in d["chips"] if r["n"])
        print(f"  {c}: {len(d['chips'])} chips, {labelled} with labelled "
              f"parcels, {len(d['outline'])} outline rings")
        for m, v in d["methods"].items():
            rec = v["found"] / v["parcels"] if v["parcels"] else 0
            print(f"    {v['label']:<26} {v['setting'] or 'as shipped':<20} "
                  f"{v['objects']:>6.1f} obj/chip  {v['found']:>5}/"
                  f"{v['parcels']:<5} {rec * 100:5.2f}%"
                  f"{'  clamped' if v['clamped'] else ''}")

    page = TEMPLATE.read_text(encoding="utf-8").replace(
        "__MAP_DATA__", json.dumps(data, separators=(",", ":")))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(page, encoding="utf-8")
    print(f"\n  wrote {DEST.relative_to(PROJECT)}, "
          f"{DEST.stat().st_size / 1024:.0f} KB")
    print(RULE)


if __name__ == "__main__":
    main()
