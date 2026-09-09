"""
RS-01 / step 10 - terrain and permanent water.

Two masks, and they are not the same kind of thing. Keeping them separate is the
whole point of this script.

SLOPE IS A CORRECTION. Radar shadow on a hillside is dark for the same reason
water is dark: nothing comes back to the sensor. A single-date threshold cannot
tell them apart, and your chips run into the hills north and east of the
Brahmaputra. Removing steep pixels should raise precision without costing much
recall, because flood water does not sit on a 15 degree slope. This is
scoreable against the hand labels, so it gets swept and scored like anything
else.

PERMANENT WATER IS A CHANGE OF PRODUCT. The Brahmaputra is water on every date
of the year. Removing it converts a water-extent map into a flood-extent map,
which is what a relief or insurance client actually wants. But if the
Sen1Floods11 hand labels mark the river as water, then masking it will lower
your IoU while making the output more correct, and optimising against that
metric would be optimising against the truth.

So section 1 measures whether the labels include permanent water before anything
is masked. The answer decides how the rest is reported:

  labels DO include permanent water  ->  validation stays on water extent;
                                         flood extent is reported as a derived
                                         area with no IoU and a stated reason
  labels do NOT include it           ->  masking should improve the score and
                                         can be validated normally

Occurrence comes from JRC Global Surface Water (Pekel et al. 2016), the
occurrence band, which gives the percentage of observations between 1984 and
2021 in which a pixel was water. Occurrence >= 80 is a conventional cut for
permanent water; the script sweeps it rather than assuming it.

Note on how the slope mask is applied: steep pixels are set to LAND, not to
no-data. Setting them to no-data would drop them from the confusion matrix
entirely and flatter the score for free. Calling them land is the claim the mask
actually makes.

Outputs:
    data/gsw/India_<chip>_GSW.tif
    results/mask_terrain_water.csv
    results/figures/mask_terrain_water.png

Usage:
    python src\\mask_terrain_water.py
    python src\\mask_terrain_water.py --limit 5      # smoke test the fetch
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
import odc.geo.xr                           # noqa: F401,E402
import planetary_computer                   # noqa: E402
import pystac_client                        # noqa: E402
import rasterio                             # noqa: E402
import rioxarray                            # noqa: F401,E402
from odc.stac import load as odc_load       # noqa: E402
from skimage.filters import threshold_otsu  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config                               # noqa: E402
from config import EVENT, LABELS_DIR, DATA, RESULTS, MPC_STAC, BBOX  # noqa: E402
from chips import read, split_lookup, lee_filter    # noqa: E402
import metrics as M                         # noqa: E402

REF_DIR = DATA / "reference"
DEM_DIR = DATA / "dem"
GSW_DIR = DATA / "gsw"
GSW_DIR.mkdir(parents=True, exist_ok=True)
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

PIXEL_HA = 0.01
GSW_COLLECTION = getattr(config, "GSW_COLLECTION", "jrc-gsw")
SLOPE_CUTS = (2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0, 90.0)   # 90 = no mask
OCCURRENCE_CUTS = (10, 25, 50, 70, 80, 90)


# --------------------------------------------------------------------- io
def usable_chips() -> list[str]:
    path = RESULTS / "usable_chips.txt"
    if path.exists():
        ids = [c.strip() for c in path.read_text().split() if c.strip()]
        if ids:
            return ids
    print("  (no usable_chips.txt, falling back to every aligned chip)")
    return sorted(p.name.split("_")[1]
                  for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC_ALIGNED.tif"))


def chip_geobox(chip_id: str):
    return rioxarray.open_rasterio(
        LABELS_DIR / "S1Hand" / f"{EVENT}_{chip_id}_S1Hand.tif").odc.geobox


def slope_degrees(elev: np.ndarray, lat: float, deg_per_px: float) -> np.ndarray:
    """
    Slope in degrees from an elevation grid on a geographic (degree) grid.

    Same function as fetch_dem.py. Copied rather than imported so this script
    does not drag in a STAC search at import time.
    """
    dy_m = deg_per_px * 110_540.0
    dx_m = deg_per_px * 111_320.0 * np.cos(np.deg2rad(lat))
    gy, gx = np.gradient(elev, dy_m, dx_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def fetch_gsw(ids: list[str]) -> None:
    missing = [c for c in ids
               if not (GSW_DIR / f"{EVENT}_{c}_GSW.tif").exists()]
    if not missing:
        print(f"  all {len(ids)} GSW chips already present")
        return

    client = pystac_client.Client.open(
        MPC_STAC, modifier=planetary_computer.sign_inplace)
    items = list(client.search(collections=[GSW_COLLECTION], bbox=BBOX).items())
    if not items:
        raise SystemExit(
            f"no items in {GSW_COLLECTION} over the AOI. Check the collection "
            "id, or set GSW_COLLECTION in config.py")

    assets = sorted(items[0].assets)
    print(f"  {GSW_COLLECTION}: {len(items)} tile(s), assets: "
          f"{', '.join(assets)}")
    band = "occurrence" if "occurrence" in assets else assets[0]
    if band != "occurrence":
        print(f"  WARNING: no 'occurrence' asset, falling back to '{band}'")

    t0 = time.time()
    for n, chip_id in enumerate(missing, 1):
        gbox = chip_geobox(chip_id)
        ds = odc_load(items, bands=[band], like=gbox, chunks={})
        da = ds[band]
        if "time" in da.dims:
            da = da.isel(time=0)
        occ = np.asarray(da.compute()).astype("float32")
        if occ.ndim == 3:
            occ = occ[0]
        occ[occ > 100] = np.nan          # JRC uses 255 for no observation

        profile = dict(driver="GTiff", height=occ.shape[0], width=occ.shape[1],
                       count=1, dtype="float32", crs=gbox.crs,
                       transform=gbox.transform, compress="deflate",
                       nodata=float("nan"))
        with rasterio.open(GSW_DIR / f"{EVENT}_{chip_id}_GSW.tif",
                           "w", **profile) as dst:
            dst.write(occ, 1)
        print(f"\r  fetching GSW {n}/{len(missing)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()


def load_chip(chip_id: str):
    with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC_ALIGNED.tif") as s:
        fl_vh = lee_filter(s.read(2).astype("float64")).astype("float32")

    dem_path = DEM_DIR / f"{EVENT}_{chip_id}_DEM.tif"
    with rasterio.open(dem_path) as s:
        elev = s.read(1).astype("float64")
        tr = s.transform
        lat = float(s.bounds.bottom + s.bounds.top) / 2.0
        deg_per_px = abs(tr.e)
    slope = slope_degrees(elev, lat, deg_per_px).astype("float32")

    with rasterio.open(GSW_DIR / f"{EVENT}_{chip_id}_GSW.tif") as s:
        occ = s.read(1).astype("float32")

    return fl_vh, slope, occ, read("LabelHand", chip_id)[0]


# ------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="only process the first N chips, for a smoke test")
    ap.add_argument("--stride", type=int, default=7)
    args = ap.parse_args()

    ids = usable_chips()
    if args.limit:
        ids = ids[:args.limit]

    ready = [c for c in ids if (DEM_DIR / f"{EVENT}_{c}_DEM.tif").exists()]
    if len(ready) < len(ids):
        print(f"  {len(ids) - len(ready)} chip(s) have no DEM, skipping them. "
              "Run fetch_dem.py to cover them.")
    ids = ready
    if not ids:
        raise SystemExit("no chips have a DEM. Run fetch_dem.py first.")

    print(f"{len(ids)} chips\n")
    print("FETCHING JRC GLOBAL SURFACE WATER")
    print("---------------------------------")
    fetch_gsw(ids)

    data, t0 = {}, time.time()
    for n, chip_id in enumerate(ids, 1):
        try:
            data[chip_id] = load_chip(chip_id)
        except Exception as exc:                        # noqa: BLE001
            print(f"\n  skipping {chip_id}: {exc}")
        print(f"\r  loading {n}/{len(ids)} ({time.time()-t0:.0f}s)",
              end="", flush=True)
    print()
    ids = [c for c in ids if c in data]
    splits = split_lookup()

    t_abs = float(threshold_otsu(np.concatenate(
        [d[0][np.isfinite(d[0])][::args.stride] for d in data.values()])))

    # -------------------------- 1. do the labels include permanent water?
    print("\n1. DO THE HAND LABELS INCLUDE PERMANENT WATER?")
    print("----------------------------------------------")
    print("  Two different questions, and only the second one answers this.")
    print("  Column A: what share of labelled water is permanent. Small "
          "whenever\n  permanent water is a small part of the scene, whatever "
          "the labels do.")
    print("  Column B: what share of permanent water got labelled as water. "
          "This is\n  the one that says whether the labellers marked the "
          "river.\n")
    print(f"  {'occurrence cut':>15}{'A: of labelled water':>23}"
          f"{'share of scene':>17}{'B: of that area, labelled':>28}")
    label_on_perm, perm_is_water, perm_px = {}, {}, {}
    for cut in OCCURRENCE_CUTS:
        w_tot = w_perm = scene = perm = 0
        for chip_id in ids:
            _, _, occ, label = data[chip_id]
            valid = (label != -1) & np.isfinite(occ)
            water = valid & (label == 1)
            p = valid & (occ >= cut)
            w_tot += int(water.sum()); w_perm += int((water & p).sum())
            scene += int(valid.sum()); perm += int(p.sum())
        label_on_perm[cut] = w_perm / max(w_tot, 1)
        perm_is_water[cut] = w_perm / max(perm, 1)
        perm_px[cut] = perm
        print(f"  {cut:>13}%{label_on_perm[cut]:>22.1%}"
              f"{perm / max(scene, 1):>17.1%}"
              f"{perm_is_water[cut]:>28.1%}")

    # Decide on the 50% cut: high enough to mean "usually water", and it keeps
    # enough pixels for the fraction to be stable. Fall back to a lower cut if
    # this scene has almost no permanent water at 50.
    decide_cut = 50
    for c in sorted(OCCURRENCE_CUTS):
        if perm_px[c] >= 20_000:          # about 200 ha, enough to trust
            decide_cut = c if c <= 50 else decide_cut
    includes = perm_is_water[decide_cut] > 0.50
    print(f"\n  Deciding on the {decide_cut}% cut "
          f"({perm_px[decide_cut] * PIXEL_HA:,.0f} ha of permanent water).")
    if includes:
        print(f"  {perm_is_water[decide_cut]:.1%} of it was hand-labelled as "
              "water. The labels mark WATER,\n  not flood. Masking permanent "
              "water will therefore lower IoU while\n  improving the product, so "
              "flood extent is reported below as an area\n  with no IoU attached, "
              "and validation stays on water extent.")
    else:
        print(f"  Only {perm_is_water[decide_cut]:.1%} of it was hand-labelled "
              "as water, so the labels\n  are flood-only and masking can be "
              "validated normally.")

    # ------------------------------------------- 2. slope mask, scoreable
    print("\n2. DOES A SLOPE MASK HELP? (scored, steep pixels called LAND)")
    print("-------------------------------------------------------------")
    print(f"  single-date VH threshold {t_abs:.2f} dB")
    print(f"  {'slope cut':>10}{'masked':>9}{'valid':>8}{'test':>8}{'all':>8}"
          f"{'P':>7}{'R':>7}{'area ha':>10}")

    rows = []
    for cut in SLOPE_CUTS:
        by_split, area, steep, scene = {}, 0.0, 0, 0
        for chip_id in ids:
            fl_vh, slope, occ, label = data[chip_id]
            nodata = ~np.isfinite(fl_vh)
            mask = (fl_vh <= t_abs) & (slope <= cut)
            pred = np.where(nodata, -1, mask.astype(np.int8)).astype(np.int8)
            by_split.setdefault(splits.get(chip_id, "unknown"),
                                []).append(M.confusion(pred, label))
            area += M.mapped_area_px(pred, label) * PIXEL_HA
            steep += int((~nodata & (slope > cut)).sum())
            scene += int((~nodata).sum())
        a = M.aggregate([c for v in by_split.values() for c in v])
        row = {"slope_cut": cut, "masked_frac": round(steep / max(scene, 1), 4),
               "iou_all": round(a["iou"], 4), "p_all": round(a["precision"], 4),
               "r_all": round(a["recall"], 4), "area_ha": round(area, 1)}
        for split, confs in by_split.items():
            row[f"iou_{split}"] = round(M.aggregate(confs)["iou"], 4)
        rows.append(row)
        print(f"  {cut:>9.1f}{steep / max(scene, 1):>9.1%}"
              f"{row.get('iou_valid', float('nan')):>8.3f}"
              f"{row.get('iou_test', float('nan')):>8.3f}"
              f"{row['iou_all']:>8.3f}{row['p_all']:>7.3f}{row['r_all']:>7.3f}"
              f"{area:>10.0f}")

    scored = [r for r in rows if "iou_valid" in r]
    best = max(scored, key=lambda r: r["iou_valid"])
    nomask = next(r for r in rows if r["slope_cut"] == 90.0)
    print(f"\n  best on valid: slope cut {best['slope_cut']:.1f} deg, "
          f"IoU {best['iou_valid']:.3f} valid / {best['iou_test']:.3f} test")
    print(f"  no mask:                        "
          f"IoU {nomask['iou_valid']:.3f} valid / {nomask['iou_test']:.3f} test")
    d_iou = best["iou_test"] - nomask["iou_test"]
    d_p = best["p_all"] - nomask["p_all"]
    d_r = best["r_all"] - nomask["r_all"]
    print(f"  change on test {d_iou:+.3f} IoU, precision {d_p:+.3f}, "
          f"recall {d_r:+.3f}")
    if best["slope_cut"] == 90.0:
        print("  No slope cut beat leaving the terrain alone. Radar shadow is "
              "not a\n  significant error source on these chips, which is worth "
              "saying rather\n  than quietly dropping the mask.")
    elif d_p > 0 and d_iou > 0.005:
        print("  Precision up and IoU up: the mask is removing shadow that the\n"
              "  threshold was calling water.")
    else:
        print("  The mask moves the score by less than it costs in complexity. "
              "Keep it\n  out of the pipeline and say why.")

    # ------------------------------- 3. permanent water, product not score
    print("\n3. PERMANENT WATER (product change, not a score)")
    print("------------------------------------------------")
    cut = best["slope_cut"]
    print(f"  slope cut {cut:.1f} deg applied, then permanent water removed\n")
    print(f"  {'occurrence':>11}{'predicted ha':>14}{'flood-only ha':>15}"
          f"{'removed':>9}{'truth flood-only ha':>21}")
    perm_rows = []
    for occ_cut in OCCURRENCE_CUTS:
        pred_ha = flood_ha = truth_flood_ha = 0.0
        for chip_id in ids:
            fl_vh, slope, occ, label = data[chip_id]
            good = np.isfinite(fl_vh)
            water = good & (fl_vh <= t_abs) & (slope <= cut)
            perm = np.isfinite(occ) & (occ >= occ_cut)
            lab = label != -1
            pred_ha += float((water & lab).sum()) * PIXEL_HA
            flood_ha += float((water & ~perm & lab).sum()) * PIXEL_HA
            truth_flood_ha += float(((label == 1) & ~perm).sum()) * PIXEL_HA
        perm_rows.append({"occurrence_cut": occ_cut,
                          "predicted_ha": round(pred_ha, 1),
                          "flood_only_ha": round(flood_ha, 1),
                          "truth_flood_only_ha": round(truth_flood_ha, 1)})
        print(f"  {occ_cut:>10}%{pred_ha:>14,.0f}{flood_ha:>15,.0f}"
              f"{1 - flood_ha / max(pred_ha, 1):>9.1%}"
              f"{truth_flood_ha:>21,.0f}")

    truth_ha = sum(float(np.sum(data[c][3] == 1)) * PIXEL_HA for c in ids)
    print(f"\n  hand-labelled water, nothing removed: {truth_ha:,.0f} ha")
    if includes:
        print("  The flood-only column is the number a relief or insurance\n"
              "  client wants, and it has no IoU beside it on purpose. Section 1\n"
              "  found the reference labels marking permanent water as water, so\n"
              "  there is nothing here to score flood extent against. Saying that\n"
              "  beats quoting a score that measures the wrong thing.")
    else:
        print("  Section 1 found little labelled water on permanent water, so\n"
              "  the labels are close to flood-only already and removing\n"
              "  permanent water changes the total by little. Check the truth\n"
              "  column against the labelled total above: if they track each\n"
              "  other, the mask is redundant here and belongs in the pipeline\n"
              "  only for rivers that hold water year round.\n"
              "  Watch the low occurrence cuts. A braided channel that migrates\n"
              "  between years never reaches high occurrence, so a permanent\n"
              "  water definition tuned on a stable river will miss this one.")

    # ------------------------------------------------------------ outputs
    with open(RESULTS / "mask_terrain_water.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["section", "key", "value"])
        for cut_, frac in label_on_perm.items():
            w.writerow(["labels_on_permanent", f"occ_ge_{cut_}", f"{frac:.4f}"])
        for cut_, frac in perm_is_water.items():
            w.writerow(["permanent_labelled_water", f"occ_ge_{cut_}",
                        f"{frac:.4f}"])
        for r in rows:
            for k, v in r.items():
                if k != "slope_cut":
                    w.writerow([f"slope_{r['slope_cut']:.1f}", k, v])
        for r in perm_rows:
            for k, v in r.items():
                if k != "occurrence_cut":
                    w.writerow([f"occurrence_{r['occurrence_cut']}", k, v])

    chip_id = max(ids, key=lambda c: int(np.sum(data[c][3] == 1)))
    fl_vh, slope, occ, label = data[chip_id]
    good = np.isfinite(fl_vh)
    water = good & (fl_vh <= t_abs)
    water_s = water & (slope <= cut)
    perm = np.isfinite(occ) & (occ >= 80)

    panels = [(fl_vh, "flood VH (dB)", "gray", None),
              (slope, "slope (degrees)", "magma", (0, 20)),
              (occ, "GSW occurrence (%)", "Blues", (0, 100)),
              (label.astype(float), "hand label", "Blues", (0, 1)),
              (water.astype(float), "threshold only", "Blues", (0, 1)),
              (water_s.astype(float), f"+ slope <= {cut:.0f} deg",
               "Blues", (0, 1)),
              ((water_s & ~perm).astype(float), "+ permanent water removed",
               "Blues", (0, 1)),
              ((water_s & perm).astype(float), "the part that is the river",
               "Blues", (0, 1))]

    fig, axes = plt.subplots(2, 4, figsize=(15, 8))
    for ax, (img, title, cmap, lim) in zip(axes.ravel(), panels):
        im = np.array(img, dtype=float)
        if lim:
            ax.imshow(im, cmap=cmap, vmin=lim[0], vmax=lim[1])
        else:
            f = im[np.isfinite(im)]
            ax.imshow(im, cmap=cmap, vmin=np.percentile(f, 2),
                      vmax=np.percentile(f, 98))
        ax.set_title(title, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{EVENT} chip {chip_id}: water extent to flood extent")
    fig.tight_layout()
    fig.savefig(FIGURES / "mask_terrain_water.png", dpi=130)

    print(f"\nwrote mask_terrain_water.csv and "
          f"figures/mask_terrain_water.png (chip {chip_id})")


if __name__ == "__main__":
    main()
