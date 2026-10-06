"""
RS-02. Does the India gap depend on which season the imagery shows.

FTW gives every chip two Sentinel-2 images, window_a and window_b, from date
ranges set per country in data_config_<country>.json:

    India, 2016      window_b  1 March to 30 June
                     window_a  1 July to 30 November
    Slovenia, 2021   window_a  1 May to 30 August
                     window_b  1 September to 31 October

India's window_a spans the kharif season. window_b spans the end of the rabi
harvest and the dry months before the monsoon. Neither covers December to
February, when rabi crops are standing. The script prints the ranges from the
config files, so this table can be checked against the data.

Two parts, each run per country.

PART ftw
--------
The released 3-class checkpoint reads eight channels, window_b's four bands
then window_a's (ftw/datasets.py, temporal_options "stacked"). It is run four
ways over the test chips:

    shipped         window_b, window_a     as FTW trains and ships it
    swapped         window_a, window_b
    a twice         window_a, window_a
    b twice         window_b, window_b

The shipped run must reproduce results/<country>/pred_3class_full exactly,
and the script reports how many pixels differ. The other three show how much
the model leans on each image. A model that has learned field edges from one
season should hold up when that season is given twice.

PART watershed
--------------
The watershed baseline is run on three gradients: both windows stacked (the
published setting), window_a alone and window_b alone. Each is swept over the
published settings plus three coarser ones, so that Slovenia can reach FTW's
object count, and read at FTW's own count per chip the same way COMPARISON.md
reads it. The stacked run must reproduce the recall column of
segmenter_comparison_min500.csv, and the script says whether it does.

The random-cell null depends on object count only, never on the image, so it
is not rerun. Its value at FTW's count is in COMPARISON.md.

PART windows
------------
A short description of each window, per chip: the median red and blue
reflectance, the 95th percentile of blue as a rough sign of haze or cloud, the
median NDVI as a sign of how much is growing, and the mean edge strength the
watershed sees. Bands are read by name. An earlier version read band 1 as blue
when FTW stores red there (B-23), so this part was split out to be rerun on
its own in a few seconds per country.

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
Intervals are 95%, from 2,000 resamples of whole chips.

    A window carries more of the visible boundaries if watershed on it alone
    scores higher at FTW's count, with intervals that do not overlap.

    Stacking dilutes the signal if one window alone beats both stacked, with
    intervals that do not overlap.

    FTW leans on a window if feeding it that window twice moves recall outside
    the shipped run's interval.

    Season is a candidate cause of the India gap if, in India and not in
    Slovenia, one window carries clearly less of the boundaries, or FTW's
    recall moves outside its interval when the window order changes.

What this cannot say: whether an image from December to February would do
better. Neither window has one, and finding out needs new imagery.

    python src\\season_test.py --country india
    python src\\season_test.py --country slovenia
    python src\\season_test.py --country india --part watershed
    python src\\season_test.py --country india --part windows
    python src\\season_test.py --country india --limit 10
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FTW_VARIANTS = {
    "shipped": (0, 1, 2, 3, 4, 5, 6, 7),
    "swapped": (4, 5, 6, 7, 0, 1, 2, 3),
    "a twice": (4, 5, 6, 7, 4, 5, 6, 7),
    "b twice": (0, 1, 2, 3, 0, 1, 2, 3),
}
WS_VARIANTS = ("both", "window_a", "window_b")
EXTRA_WS = [0.4, 0.5, 0.6]
WIDTH_EDGES = [0, 20, 30, 50, np.inf]
WIDTH_LABELS = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def load_country(country: str):
    """ftw_common and compare_segmenters, pointed at one country."""
    os.environ["FTW_COUNTRY"] = country
    import ftw_common as F
    importlib.reload(F)
    import compare_segmenters as C
    importlib.reload(C)
    import seg_score as S
    return F, C, S


def windows_from_config(F) -> dict:
    path = F.DATA / f"data_config_{F.COUNTRY}.json"
    if not path.exists():
        return {}
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return cfg.get("seasons", {})


def print_windows(F) -> None:
    seasons = windows_from_config(F)
    print("  date ranges, from the FTW data config")
    for w in ("window_b", "window_a"):
        s = seasons.get(w)
        if s:
            print(f"    {w}  {s['start']} to {s['end']}")
    print()


def chips_for(F, limit: int) -> list:
    pred = F.RESULTS / "pred_3class_full"
    if not pred.exists():
        sys.exit(f"{pred} not found")
    chips = [p.name for p in sorted(pred.glob("*.tif"))]
    return chips[:limit] if limit else chips


def chip_interval(hits: np.ndarray, n: np.ndarray, boots: int, rng) -> tuple:
    """95% interval on pooled recall, resampling whole chips."""
    if n.sum() == 0:
        return float("nan"), float("nan")
    k = len(n)
    vals = []
    for _ in range(boots):
        i = rng.integers(0, k, k)
        tot = n[i].sum()
        vals.append(hits[i].sum() / tot if tot else 0.0)
    lo, hi = np.percentile(vals, (2.5, 97.5))
    return float(lo), float(hi)


def widths(F) -> dict:
    """Ground width of each parcel, from the table every width figure uses."""
    path = F.RESULTS / "parcel_width_seg_ftw_min500.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[(r["chip"], int(r["parcel_id"]))] = \
                float(r["width_native_px"]) * 10.0
    return out


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# FTW with the windows rearranged
# ---------------------------------------------------------------------------

def stacked_image(F, chip: str):
    """window_b then window_a, read and scaled exactly as FTW's dataset does."""
    import rasterio
    import torch
    parts = []
    for folder in (F.IMG_B, F.IMG_A):
        with rasterio.open(folder / chip) as s:
            parts.append(s.read())
    img = np.concatenate(parts, axis=0).astype(np.int32)
    return torch.from_numpy(img).float() / 3000


def run_ftw(F, C, S, args, rng) -> None:
    import rasterio
    import torch
    from scipy.ndimage import label as cc_label
    import run_inference as R

    if args.threads:
        torch.set_num_threads(args.threads)
    model, _ = R.load_model(args.ckpt)
    chips = chips_for(F, args.limit)
    min_px = int(round(args.min_size_m2 / F.grid_pixel_area_m2()))
    wmap = widths(F)

    print(RULE)
    print(f"FTW, {F.COUNTRY.upper()}, {len(chips)} chips, the windows rearranged")
    print(RULE)
    print_windows(F)

    per = {v: {"hits": [], "n": [], "objs": [], "null": []}
           for v in FTW_VARIANTS}
    parcel_rows = []
    differ = total = 0
    tic = time.time()

    for start in range(0, len(chips), args.batch):
        batch = chips[start:start + args.batch]
        imgs = torch.stack([stacked_image(F, c) for c in batch])
        preds = {}
        with torch.inference_mode():
            for v, order in FTW_VARIANTS.items():
                logits = model(imgs[:, list(order)])
                preds[v] = logits.argmax(dim=1).cpu().numpy().astype(np.uint8)

        for k, chip in enumerate(batch):
            with rasterio.open(F.RESULTS / "pred_3class_full" / chip) as s:
                published = s.read(1)
            differ += int((published != preds["shipped"][k]).sum())
            total += published.size

            _, _, _, full = F.load_labels(chip)
            if full.max() == 0:
                continue
            for v in FTW_VARIANTS:
                lab, _ = cc_label(preds[v][k] == 1)
                seg = C.drop_small(lab.astype(np.int32), min_px)
                n_obj = C.object_count(seg)
                ious = S.parcel_scores(full, seg)
                found = sum(1 for x in ious.values() if x >= args.iou)
                null_found = 0
                for _ in range(args.null_draws):
                    nseg = C.null_segments(full.shape, n_obj, rng)
                    null_found += sum(1 for x in S.parcel_scores(
                        full, nseg).values() if x >= args.iou)
                p = per[v]
                p["hits"].append(found)
                p["n"].append(len(ious))
                p["objs"].append(n_obj)
                p["null"].append(null_found / max(1, args.null_draws))
                for pid, x in ious.items():
                    parcel_rows.append({
                        "variant": v, "chip": chip, "parcel_id": pid,
                        "width_m": round(wmap.get((chip, pid), float("nan")), 2),
                        "best_iou": round(x, 4), "found": int(x >= args.iou)})

        done = start + len(batch)
        if done % 40 < args.batch or done == len(chips):
            rate = done / (time.time() - tic)
            print(f"    {done:>5,} / {len(chips):,}   {rate:.2f} chips/s   "
                  f"{(len(chips) - done) / rate / 60:.1f} min left")

    share = differ / total if total else 0.0
    print(f"\n  shipped run against pred_3class_full: {differ:,} of "
          f"{total:,} pixels differ ({share * 100:.4f}%)")
    if differ:
        print("  The shipped run should match the published predictions. A")
        print("  handful of pixels can move with thread count; more than that")
        print("  means the input is not what FTW feeds its model. Check before")
        print("  reading the rest.")

    print(f"\n  {'variant':<10}{'objects':>9}{'recall':>9}{'interval':>18}"
          f"{'null':>8}{'vs shipped':>12}")
    base = None
    summary = []
    for v in FTW_VARIANTS:
        p = per[v]
        hits, n = np.array(p["hits"]), np.array(p["n"])
        rec = hits.sum() / n.sum()
        lo, hi = chip_interval(hits, n, args.boots, rng)
        null = np.sum(p["null"]) / n.sum()
        objs = float(np.mean(p["objs"]))
        base = rec if v == "shipped" else base
        rel = f"{rec / base:.2f}x" if base else ""
        print(f"  {v:<10}{objs:>9.1f}{rec * 100:>8.2f}%"
              f"   [{lo * 100:5.2f}, {hi * 100:5.2f}]{null * 100:>7.2f}%"
              f"{rel:>12}")
        summary.append({"country": F.COUNTRY, "variant": v,
                        "chips": len(n), "parcels": int(n.sum()),
                        "objects_per_chip": round(objs, 1),
                        "recall": round(rec, 4), "lo": round(lo, 4),
                        "hi": round(hi, 4), "null_recall": round(null, 4),
                        "pixels_differing_from_published":
                            differ if v == "shipped" else ""})

    if wmap:
        print(f"\n  recall by ground width")
        print(f"  {'variant':<10}" + "".join(f"{w:>13}" for w in WIDTH_LABELS))
        for v in FTW_VARIANTS:
            rows = [r for r in parcel_rows if r["variant"] == v]
            cells = []
            for lo_m, hi_m in zip(WIDTH_EDGES[:-1], WIDTH_EDGES[1:]):
                band = [r["found"] for r in rows
                        if lo_m <= r["width_m"] < hi_m]
                cells.append(f"{np.mean(band) * 100:>12.2f}%" if band
                             else f"{'':>13}")
            print(f"  {v:<10}" + "".join(cells))

    write_csv(F.RESULTS / "season_ftw.csv", summary)
    write_csv(F.RESULTS / "season_ftw_parcels.csv", parcel_rows)
    print(f"\n  wrote results\\{F.COUNTRY}\\season_ftw.csv and "
          f"season_ftw_parcels.csv")


# ---------------------------------------------------------------------------
# watershed on one window at a time
# ---------------------------------------------------------------------------

def window_stack(F, C, chip: str, variant: str) -> np.ndarray:
    """Every band of the chosen windows, each stretched on its own.

    "both" is compare_segmenters.read_stack, called rather than copied, so the
    published gradient is the one being reproduced.
    """
    import rasterio
    if variant == "both":
        return C.read_stack(chip)
    folder = F.IMG_A if variant == "window_a" else F.IMG_B
    with rasterio.open(folder / chip) as s:
        arr = s.read()
    return np.stack([C.stretch(b) for b in arr])


def describe_window(F, C, chip: str, folder) -> dict:
    """Red, blue, NDVI and edge strength for one window of one chip."""
    import rasterio
    path = folder / chip
    with rasterio.open(path) as s:
        red, blue, nir = s.read(F.band_index(path, ("B04", "B02", "B08"))
                                ).astype(np.float32)
        every = s.read()
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)
    stack = np.stack([C.stretch(b) for b in every])
    return {"red_median": float(np.median(red)),
            "blue_median": float(np.median(blue)),
            "blue_p95": float(np.percentile(blue, 95)),
            "ndvi_median": float(np.nanmedian(ndvi)),
            "edge_mean": float(C.gradient(stack).mean())}


def run_windows(F, C, args) -> None:
    chips = chips_for(F, args.limit)
    print(RULE)
    print(f"WHAT EACH WINDOW SHOWS, {F.COUNTRY.upper()}, {len(chips)} chips")
    print(RULE)
    print_windows(F)
    rows = []
    for chip in chips:
        for w, folder in (("window_a", F.IMG_A), ("window_b", F.IMG_B)):
            rows.append({"window": w, "chip": chip,
                         **describe_window(F, C, chip, folder)})
    cols = ["red_median", "blue_median", "blue_p95", "ndvi_median",
            "edge_mean"]
    print("  median over every test chip")
    print(f"  {'window':<10}" + "".join(f"{c:>13}" for c in cols))
    for w in ("window_a", "window_b"):
        sel = [r for r in rows if r["window"] == w]
        print(f"  {w:<10}" + "".join(
            f"{np.median([r[c] for r in sel]):>13.3f}" for c in cols))
    write_csv(F.RESULTS / "season_windows.csv", rows)
    print(f"\n  wrote results\\{F.COUNTRY}\\season_windows.csv")


def at_budget(objs: np.ndarray, rec: np.ndarray, budget: float) -> float:
    order = np.argsort(objs)
    return float(np.interp(budget, objs[order], rec[order]))


def run_watershed(F, C, S, args, rng) -> None:
    chips = chips_for(F, args.limit)
    min_px = int(round(args.min_size_m2 / F.grid_pixel_area_m2()))
    settings = list(C.SWEEPS["watershed"]) + EXTRA_WS

    published = {}
    sp = F.RESULTS / "segmenter_comparison_min500.csv"
    budget = None
    if sp.exists():
        with sp.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["method"] == "ftw":
                    budget = float(r["objects_per_chip"])
                elif r["method"] == "watershed":
                    published[float(r["setting"])] = float(r["recall"])
    if budget is None:
        sys.exit(f"{sp} not found or has no FTW row")

    print(RULE)
    print(f"WATERSHED, {F.COUNTRY.upper()}, {len(chips)} chips, one window at a time")
    print(RULE)
    print_windows(F)
    print(f"  FTW's object count, read from {sp.name}: {budget:.1f} per chip")
    print(f"  dropping objects under {args.min_size_m2:.0f} m2, "
          f"{min_px} grid pixels here\n")

    # chip by setting arrays, one set per variant
    shape = (len(chips), len(settings))
    hits = {v: np.zeros(shape) for v in WS_VARIANTS}
    objs = {v: np.zeros(shape) for v in WS_VARIANTS}
    n = np.zeros(len(chips))
    keep = np.zeros(len(chips), bool)
    tic = time.time()

    for i, chip in enumerate(chips):
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        keep[i] = True
        for v in WS_VARIANTS:
            stack = window_stack(F, C, chip, v)
            grad = C.gradient(stack)
            for j, h in enumerate(settings):
                seg = C.drop_small(C.segment(stack, grad, "watershed", h),
                                   min_px)
                ious = S.parcel_scores(full, seg)
                hits[v][i, j] = sum(1 for x in ious.values() if x >= args.iou)
                objs[v][i, j] = C.object_count(seg)
                n[i] = len(ious)
        if (i + 1) % 20 == 0 or i + 1 == len(chips):
            rate = (i + 1) / (time.time() - tic)
            print(f"    {i + 1:>5,} / {len(chips):,}   {rate:.2f} chips/s   "
                  f"{(len(chips) - i - 1) / rate / 60:.1f} min left")

    n = n[keep]
    for v in WS_VARIANTS:
        hits[v], objs[v] = hits[v][keep], objs[v][keep]

    # the stacked run against the published sweep
    print(f"\n  stacked run against {sp.name}")
    matched = checked = 0
    for j, h in enumerate(settings):
        if h in published:
            rec = round(hits["both"][:, j].sum() / n.sum(), 4)
            checked += 1
            matched += int(rec == round(published[h], 4))
            if rec != round(published[h], 4):
                print(f"    h {h}: {rec:.4f} here, {published[h]:.4f} published")
    print(f"    {matched} of {checked} published settings reproduced exactly")
    if args.limit:
        print("    (a --limit run covers fewer chips, so it will not match)")

    sweep_rows = []
    print(f"\n  {'variant':<10}{'h':>7}{'objects':>9}{'recall':>9}")
    for v in WS_VARIANTS:
        for j, h in enumerate(settings):
            o = objs[v][:, j].mean()
            r = hits[v][:, j].sum() / n.sum()
            sweep_rows.append({"country": F.COUNTRY, "variant": v,
                               "setting": h, "objects_per_chip": round(o, 1),
                               "recall": round(r, 4)})
            print(f"  {v:<10}{h:>7}{o:>9.1f}{r * 100:>8.2f}%")

    print("\n" + RULE)
    print(f"AT FTW'S OBJECT COUNT, {budget:.1f} PER CHIP")
    print(RULE)
    budget_rows = []
    k = len(n)
    for v in WS_VARIANTS:
        o_all = objs[v].mean(0)
        r_all = hits[v].sum(0) / n.sum()
        point = at_budget(o_all, r_all, budget)
        draws = []
        for _ in range(args.boots):
            idx = rng.integers(0, k, k)
            draws.append(at_budget(objs[v][idx].mean(0),
                                   hits[v][idx].sum(0) / n[idx].sum(), budget))
        lo, hi = np.percentile(draws, (2.5, 97.5))
        clamped = not (o_all.min() <= budget <= o_all.max())
        note = "   outside the sweep, clamped" if clamped else ""
        print(f"  {v:<10}{point * 100:>8.2f}%   [{lo * 100:5.2f}, "
              f"{hi * 100:5.2f}]{note}")
        budget_rows.append({"country": F.COUNTRY, "variant": v,
                            "budget": budget, "recall": round(point, 4),
                            "lo": round(float(lo), 4),
                            "hi": round(float(hi), 4), "clamped": clamped})

    write_csv(F.RESULTS / "season_watershed.csv", sweep_rows)
    write_csv(F.RESULTS / "season_watershed_budget.csv", budget_rows)
    print(f"\n  wrote results\\{F.COUNTRY}\\season_watershed.csv and "
          f"season_watershed_budget.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--part", default="all", choices=["all", "ftw", "watershed", "windows"])
    ap.add_argument("--ckpt", default="",
                    help="default models\\3class_full.ckpt")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--min-size-m2", type=float, default=500.0)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261007)
    args = ap.parse_args()

    if args.part in ("all", "ftw"):
        # torch before rasterio and scipy, or Windows can fail to load its DLLs
        import torch                                          # noqa: F401

    F, C, S = load_country(args.country)
    args.ckpt = args.ckpt or str(F.PROJECT / "models" / "3class_full.ckpt")
    rng = np.random.default_rng(args.seed)

    if args.part in ("all", "ftw"):
        run_ftw(F, C, S, args, rng)
        print()
    if args.part in ("all", "watershed"):
        run_watershed(F, C, S, args, rng)
        print()
    if args.part in ("all", "windows"):
        run_windows(F, C, args)
    print(RULE)


if __name__ == "__main__":
    main()
