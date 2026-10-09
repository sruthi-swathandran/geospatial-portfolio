"""
RS-02. Do FTW's newer checkpoints do better on India?

Every FTW result in RS-02 so far comes from the v1 release of October 2024.
FTW has released three more since: v2 in September 2025, trained with the two
windows in random order, v3 "PRUE" in November 2025, with a new loss, new
class weights and more augmentation, and v3.1 in December 2025, the same
recipe trained only on CC-BY data. The makers report that v3 beats v1 over
the whole test set. None of the releases holds a model trained without India,
and every one of them has India in its training countries.

This runs seven of those checkpoints on the Indian and Slovenian test chips
and scores them the way the v1 checkpoint was scored: objects of 500 m2 or
more, a parcel found when one object covers it at IoU 0.5, and random cells
at the same object count as the null.

    key            release   backbone   training data
    v1 full        v1        B3         all FTW, noncommercial licences too
    v1 cc-by       v1        B3         CC-BY and CC0 only
    v2 full        v2        B3         all FTW, window order shuffled
    v3 full b3     v3        B3         all FTW, PRUE recipe
    v3 full b7     v3        B7         all FTW, PRUE recipe
    v3.1 cc-by b3  v3.1      B3         CC-BY and CC0 only, PRUE recipe
    v3.1 cc-by b7  v3.1      B7         CC-BY and CC0 only, PRUE recipe

Every one is a U-Net with an EfficientNet encoder, eight input channels and
three classes. Reading ftw-tools 2.0.0b4 shows they all take the same input
as v1 at prediction time: window_b then window_a, each B04 B03 B02 B08,
divided by 3000. The PRUE models were trained with a random divisor between
1500 and 4500 and random window order, but their own test command divides by
3000 and keeps window_b first, so this does too.

ftw-tools 1.4.3 cannot load the PRUE checkpoints through its own classes, and
2.0 is still a beta. The checkpoints are plain U-Nets, so this builds the
network with segmentation_models_pytorch and loads the weights directly. The
v1 full checkpoint goes through the same loader, and its predictions are
checked against results/<country>/pred_3class_full before anything is read.

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
Chips are every test chip with v1 predictions, 398 labelled in India and 185
in Slovenia. Differences are read chip by chip: whole chips are resampled
2,000 times, the same resample applied to both checkpoints, giving a 95%
interval on the difference.

    R0  The loader is right if v1 full differs from pred_3class_full in at
        most 0.01% of pixels in each country. If not, nothing else is read.

    R1  A checkpoint does better on India if its recall minus v1 full's has
        an interval above zero.

    R2  The gain comes from better placed boundaries if its recall above its
        own null, minus v1 full's recall above its null, also has an interval
        above zero. R1 without R2 is reported as a gain that more objects
        alone would explain.

    R3  The India gap narrows materially if a checkpoint's India recall
        divided by its own Slovenia recall has a lower end of one third or
        more. v1 full stands at about 0.12.

    R4  If no checkpoint meets R1 and R2 on India, the RS-02 reading, that
        the checkpoint is the cause, holds for every public release. If one
        does, the write-up says how much of the gap newer training recovers
        and whether R3 holds.

v3.1 cc-by b3 is also set against v1 cc-by under R1 and R2, the one pair with
the same licence and the same encoder. Slovenia's changes are reported beside
India's so a gain on India can be told apart from a gain everywhere.

    python src\\newer_checkpoints.py --part download
    python src\\newer_checkpoints.py --part run --limit 5
    python src\\newer_checkpoints.py --part run
    python src\\newer_checkpoints.py --part report

The run part writes one file per checkpoint and country and skips any that
are complete, so it can be stopped and started again.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
RELEASE = ("https://github.com/fieldsoftheworld/ftw-baselines/releases/"
           "download/")
COUNTRIES = ("india", "slovenia")
REFERENCE = "v1 full"
SAME_LICENCE = ("v3.1 cc-by b3", "v1 cc-by")
MAX_DIFFER = 0.0001
GAP_THIRD = 1 / 3

# file: the name in models/. Each sha256 was computed from the release asset
# on 8 October 2026, and its first 17 characters match the digest the release
# page shows.
CHECKPOINTS = {
    "v1 full": {
        "file": "3class_full.ckpt",
        "url": RELEASE + "v1/3_Class_FULL_FTW_Pretrained.ckpt",
        "sha256": "22d9075e53c016532780c4d94b9cf3c1"
                  "106754639ca0a1373506650590ca6ca8",
        "licence": "mixed, includes noncommercial",
        "published": "pred_3class_full"},
    "v1 cc-by": {
        "file": "3class_ccby.ckpt",
        "url": RELEASE + "v1/3_Class_CCBY_FTW_Pretrained.ckpt",
        "sha256": "d04671c498c181a2bca4b9c1a82fb8dc"
                  "c93384eaf55841cb6672692f6fb21d3c",
        "licence": "CC-BY-4.0",
        "published": "pred_3class"},
    "v2 full": {
        "file": "3_Class_FULL_FTW_Pretrained_v2.ckpt",
        "url": RELEASE + "v2/3_Class_FULL_FTW_Pretrained_v2.ckpt",
        "sha256": "8d44562829ffc1d3d8a7cca29831ee21"
                  "4be8e0c592f9a35014bd30380f416342",
        "licence": "mixed, includes noncommercial"},
    "v3 full b3": {
        "file": "prue_efnet3_checkpoint.ckpt",
        "url": RELEASE + "v3/prue_efnet3_checkpoint.ckpt",
        "sha256": "9021b02e54ccf13d71b78b0ff16e6c75"
                  "b6970007d6d2f74d3518beba36cd4e43",
        "licence": "mixed, includes noncommercial"},
    "v3 full b7": {
        "file": "prue_efnet7_checkpoint.ckpt",
        "url": RELEASE + "v3/prue_efnet7_checkpoint.ckpt",
        "sha256": "2b1b34a17b85b8f70da6ff737529743b"
                  "6bc6049e987bce5a1fcdd7279eb3b120",
        "licence": "mixed, includes noncommercial"},
    "v3.1 cc-by b3": {
        "file": "prue_efnetb3_ccby_checkpoint.ckpt",
        "url": RELEASE + "v3.1/prue_efnetb3_ccby_checkpoint.ckpt",
        "sha256": "cd51f020168e66ddd1eff501e81da347"
                  "b39632af34bebf19a6a20d6c73c5a6d4",
        "licence": "CC-BY-4.0"},
    "v3.1 cc-by b7": {
        "file": "prue_efnetb7_ccby_checkpoint.ckpt",
        "url": RELEASE + "v3.1/prue_efnetb7_ccby_checkpoint.ckpt",
        "sha256": "3eb7624d22262915c82bc3e9bd56d27e"
                  "a776a6b837df950da87a228c65c4228e",
        "licence": "CC-BY-4.0"},
}
CHIP_FIELDS = ["chip", "parcels", "hits", "objects", "null_hits",
               "px_differ_published", "px_total"]
WIDTH_EDGES = [0, 20, 30, 50, np.inf]
WIDTH_LABELS = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def slug(key: str) -> str:
    return key.replace(" ", "_").replace(".", "")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

def download(models: Path) -> None:
    print(RULE)
    print("CHECKPOINTS")
    print(RULE)
    models.mkdir(parents=True, exist_ok=True)
    bad = 0
    for key, spec in CHECKPOINTS.items():
        dest = models / spec["file"]
        if not dest.exists():
            part = dest.with_suffix(".part")
            print(f"  {key:<14} downloading {spec['url'].rsplit('/', 1)[1]}")
            tic = time.time()
            urllib.request.urlretrieve(spec["url"], part)
            part.replace(dest)
            print(f"  {'':<14} {dest.stat().st_size / 1e6:.0f} MB in "
                  f"{time.time() - tic:.0f}s")
        got = sha256(dest)
        ok = got == spec["sha256"]
        bad += not ok
        print(f"  {key:<14} {dest.name:<38} sha256 "
              f"{'matches the release' if ok else 'DOES NOT MATCH ' + got}")
    print()
    if bad:
        sys.exit("  A file does not match its release. Delete it and run "
                 "this again.")
    print("  every file matches its release")


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_unet(path: Path):
    """The network inside an FTW checkpoint, without FTW's training classes."""
    import segmentation_models_pytorch as smp
    import torch
    ck = torch.load(path, map_location="cpu", weights_only=False)
    hp = ck["hyper_parameters"]
    if hp.get("model") != "unet":
        sys.exit(f"{path.name} is a {hp.get('model')}, not a U-Net")
    net = smp.Unet(encoder_name=hp["backbone"], encoder_weights=None,
                   in_channels=hp["in_channels"], classes=hp["num_classes"],
                   **(hp.get("model_kwargs") or {}))
    state = {k[len("model."):]: v for k, v in ck["state_dict"].items()
             if k.startswith("model.")}
    net.load_state_dict(state, strict=True)
    print(f"  {hp['backbone']}, {hp['in_channels']} channels in, "
          f"{hp['num_classes']} classes, loss {hp.get('loss')}, "
          f"class weights {hp.get('class_weights')}")
    return net.eval()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def read_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def run_one(F, C, S, T, key, k_idx, c_idx, chips, args) -> None:
    import rasterio
    import torch
    from scipy.ndimage import label as cc_label

    spec = CHECKPOINTS[key]
    out = F.RESULTS / "newer_ckpt"
    out.mkdir(parents=True, exist_ok=True)
    chip_csv = out / f"{slug(key)}_chips.csv"
    parcel_csv = out / f"{slug(key)}_parcels.csv"
    have = read_rows(chip_csv)
    if len(have) == len(chips) and not args.redo:
        print(f"  {key:<14} done already, {len(have)} chips")
        return

    path = F.PROJECT / "models" / spec["file"]
    if not path.exists():
        sys.exit(f"{path} not found. Run --part download first.")
    print(f"\n  {key}, {F.COUNTRY}, {len(chips)} chips")
    net = load_unet(path)
    pub_dir = F.RESULTS / spec["published"] if spec.get("published") else None
    if pub_dir is not None and not pub_dir.exists():
        pub_dir = None
    rng = np.random.default_rng([args.seed, c_idx, k_idx])
    min_px = int(round(500.0 / F.grid_pixel_area_m2()))
    wmap = T.widths(F)

    chip_rows, parcel_rows = [], []
    tic = time.time()
    for start in range(0, len(chips), args.batch):
        batch = chips[start:start + args.batch]
        imgs = torch.stack([T.stacked_image(F, c) for c in batch])
        with torch.inference_mode():
            pred = net(imgs).argmax(dim=1).cpu().numpy().astype(np.uint8)
        for k, chip in enumerate(batch):
            differ = total = ""
            if pub_dir is not None:
                with rasterio.open(pub_dir / chip) as s:
                    pub = s.read(1)
                differ, total = int((pub != pred[k]).sum()), int(pub.size)
            _, _, _, full = F.load_labels(chip)
            row = {"chip": chip, "parcels": 0, "hits": 0, "objects": 0,
                   "null_hits": 0.0, "px_differ_published": differ,
                   "px_total": total}
            if full.max() > 0:
                lab, _ = cc_label(pred[k] == 1)
                seg = C.drop_small(lab.astype(np.int32), min_px)
                n_obj = C.object_count(seg)
                ious = S.parcel_scores(full, seg)
                found = 0
                for _ in range(args.null_draws):
                    nseg = C.null_segments(full.shape, n_obj, rng)
                    found += sum(x >= 0.5 for x in
                                 S.parcel_scores(full, nseg).values())
                row.update({
                    "parcels": len(ious),
                    "hits": int(sum(x >= 0.5 for x in ious.values())),
                    "objects": n_obj,
                    "null_hits": round(found / max(1, args.null_draws), 4)})
                for pid, x in ious.items():
                    parcel_rows.append({
                        "chip": chip, "parcel_id": pid,
                        "width_m": round(wmap.get((chip, pid), np.nan), 2),
                        "best_iou": round(x, 4), "found": int(x >= 0.5)})
            chip_rows.append(row)
        done = start + len(batch)
        if done % 40 < args.batch or done == len(chips):
            rate = done / (time.time() - tic)
            print(f"    {done:>4} / {len(chips)}   "
                  f"{(len(chips) - done) / rate / 60:.1f} min left")
    T.write_csv(chip_csv, chip_rows)
    T.write_csv(parcel_csv, parcel_rows)
    del net


def run(args) -> None:
    import season_test as T
    for c_idx, country in enumerate(COUNTRIES):
        F, C, S = T.load_country(country)
        chips = T.chips_for(F, args.limit)
        print(RULE)
        print(f"NEWER CHECKPOINTS, {country.upper()}, {len(chips)} test chips")
        print(RULE)
        for k_idx, key in enumerate(CHECKPOINTS):
            if args.only and key not in args.only:
                continue
            run_one(F, C, S, T, key, k_idx, c_idx, chips, args)
        print()


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def load_results(F) -> dict:
    out = {}
    for key in CHECKPOINTS:
        rows = read_rows(F.RESULTS / "newer_ckpt" / f"{slug(key)}_chips.csv")
        if rows:
            out[key] = {r["chip"]: r for r in rows}
    return out


def arrays(res: dict, key: str, chips: list) -> tuple:
    rows = [res[key][c] for c in chips]
    n = np.array([float(r["parcels"]) for r in rows])
    h = np.array([float(r["hits"]) for r in rows])
    z = np.array([float(r["null_hits"]) for r in rows])
    o = np.array([float(r["objects"]) for r in rows])
    return n, h, z, o


def paired(n, hx, hy, boots, rng) -> tuple:
    k = len(n)
    point = (hx.sum() - hy.sum()) / n.sum()
    d = np.empty(boots)
    for i in range(boots):
        idx = rng.integers(0, k, k)
        d[i] = (hx[idx].sum() - hy[idx].sum()) / n[idx].sum()
    lo, hi = np.percentile(d, (2.5, 97.5))
    return float(point), float(lo), float(hi)


def single(n, h, boots, rng) -> np.ndarray:
    k = len(n)
    d = np.empty(boots)
    for i in range(boots):
        idx = rng.integers(0, k, k)
        d[i] = h[idx].sum() / n[idx].sum()
    return d


def report(args) -> None:
    import season_test as T
    rng = np.random.default_rng(args.seed)
    by_country, chips_of = {}, {}
    for country in COUNTRIES:
        F, _, _ = T.load_country(country)
        res = load_results(F)
        if REFERENCE not in res:
            sys.exit(f"no {REFERENCE} results for {country}. Run --part run.")
        common = sorted(set.intersection(*(set(v) for v in res.values())))
        chips_of[country] = [c for c in common
                             if float(res[REFERENCE][c]["parcels"]) > 0]
        by_country[country] = res
    project = F.PROJECT

    print(RULE)
    print("R0. THE LOADER, v1 FULL AGAINST THE PUBLISHED PREDICTIONS")
    print(RULE)
    stop = False
    for country, res in by_country.items():
        for key in (REFERENCE, "v1 cc-by"):
            if key not in res:
                continue
            rows = [r for r in res[key].values()
                    if r["px_differ_published"] != ""]
            if not rows:
                print(f"  {country:<9}{key:<10} no published predictions "
                      f"to check against")
                continue
            d = sum(int(r["px_differ_published"]) for r in rows)
            t = sum(int(r["px_total"]) for r in rows)
            ok = d / t <= MAX_DIFFER
            stop |= key == REFERENCE and not ok
            print(f"  {country:<9}{key:<10}{d:>9,} of {t:,} pixels differ "
                  f"({d / t * 100:.4f}%)   {'passes' if ok else 'FAILS'}")
    if stop:
        sys.exit("\n  R0 fails, so nothing below would mean anything. Stop "
                 "here and check the loader.")

    summary, changes, width_rows = [], [], []
    for country, res in by_country.items():
        chips = chips_of[country]
        print("\n" + RULE)
        print(f"{country.upper()}, {len(chips)} labelled chips")
        print(RULE)
        print(f"  {'checkpoint':<15}{'objects':>8}{'recall':>9}"
              f"{'interval':>18}{'null':>8}{'above null':>12}")
        boot = {}
        for key in CHECKPOINTS:
            if key not in res:
                continue
            n, h, z, o = arrays(res, key, chips)
            d = single(n, h, args.boots, rng)
            boot[key] = d
            lo, hi = np.percentile(d, (2.5, 97.5))
            rec, nul = h.sum() / n.sum(), z.sum() / n.sum()
            print(f"  {key:<15}{o.mean():>8.1f}{rec * 100:>8.2f}%"
                  f"   [{lo * 100:5.2f}, {hi * 100:5.2f}]{nul * 100:>7.2f}%"
                  f"{(rec - nul) * 100:>11.2f}%")
            summary.append({
                "country": country, "checkpoint": key,
                "licence": CHECKPOINTS[key]["licence"],
                "chips": len(chips), "parcels": int(n.sum()),
                "objects_per_chip": round(float(o.mean()), 1),
                "recall": round(float(rec), 4), "lo": round(float(lo), 4),
                "hi": round(float(hi), 4), "null_recall": round(float(nul), 4),
                "above_null": round(float(rec - nul), 4)})
        by_country[country]["_boot"] = boot

        print("\n  changes against a reference, chip by chip, 95% interval")
        pairs = [(k, REFERENCE) for k in CHECKPOINTS
                 if k != REFERENCE and k in res]
        if all(k in res for k in SAME_LICENCE):
            pairs.append(SAME_LICENCE)
        for x, y in pairs:
            n, hx, zx, _ = arrays(res, x, chips)
            _, hy, zy, _ = arrays(res, y, chips)
            r1 = paired(n, hx, hy, args.boots, rng)
            r2 = paired(n, hx - zx, hy - zy, args.boots, rng)
            print(f"    {x:<14} minus {y:<9} recall {r1[0] * 100:+6.2f} "
                  f"[{r1[1] * 100:+.2f}, {r1[2] * 100:+.2f}]   above null "
                  f"{r2[0] * 100:+6.2f} [{r2[1] * 100:+.2f}, "
                  f"{r2[2] * 100:+.2f}]")
            changes.append({
                "country": country, "x": x, "y": y,
                "recall_change": round(r1[0], 4), "recall_lo": round(r1[1], 4),
                "recall_hi": round(r1[2], 4),
                "above_null_change": round(r2[0], 4),
                "above_null_lo": round(r2[1], 4),
                "above_null_hi": round(r2[2], 4),
                "r1": r1[1] > 0, "r2": r2[1] > 0})

        F, _, _ = T.load_country(country)
        print(f"\n  recall by ground width")
        print(f"  {'checkpoint':<15}" + "".join(f"{w:>12}"
                                               for w in WIDTH_LABELS))
        for key in CHECKPOINTS:
            rows = read_rows(F.RESULTS / "newer_ckpt" /
                             f"{slug(key)}_parcels.csv")
            rows = [r for r in rows if r["chip"] in set(chips)]
            if not rows:
                continue
            cells, rec = [], {"country": country, "checkpoint": key}
            for label, lo_m, hi_m in zip(WIDTH_LABELS, WIDTH_EDGES[:-1],
                                         WIDTH_EDGES[1:]):
                band = [int(r["found"]) for r in rows
                        if r["width_m"] not in ("", "nan")
                        and lo_m <= float(r["width_m"]) < hi_m]
                rec[label] = round(float(np.mean(band)), 4) if band else ""
                rec[label + " parcels"] = len(band)
                cells.append(f"{np.mean(band) * 100:>11.2f}%" if band
                             else f"{'':>12}")
            width_rows.append(rec)
            print(f"  {key:<15}" + "".join(cells))

    print("\n" + RULE)
    print("R3. INDIA RECALL OVER SLOVENIA RECALL, SAME CHECKPOINT")
    print(RULE)
    gap_rows = []
    bi, bs = by_country["india"]["_boot"], by_country["slovenia"]["_boot"]
    for key in CHECKPOINTS:
        if key not in bi or key not in bs:
            continue
        ri = next(r["recall"] for r in summary
                  if r["country"] == "india" and r["checkpoint"] == key)
        rs = next(r["recall"] for r in summary
                  if r["country"] == "slovenia" and r["checkpoint"] == key)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = bi[key] / np.where(bs[key] > 0, bs[key], np.nan)
        ratio = ratio[np.isfinite(ratio)]
        if not len(ratio):
            print(f"  {key:<15}nothing found in one country, so the ratio is undefined")
            continue
        lo, hi = np.percentile(ratio, (2.5, 97.5))
        point = ri / rs if rs else float("nan")
        meets = lo >= GAP_THIRD
        print(f"  {key:<15}{point:>7.3f}   [{lo:.3f}, {hi:.3f}]   "
              f"{'meets one third' if meets else 'below one third'}")
        gap_rows.append({"checkpoint": key, "ratio": round(point, 4),
                         "lo": round(float(lo), 4), "hi": round(float(hi), 4),
                         "meets_third": meets})

    print("\n" + RULE)
    print("READING")
    print(RULE)
    india = [c for c in changes if c["country"] == "india"
             and c["y"] == REFERENCE]
    both = [c["x"] for c in india if c["r1"] and c["r2"]]
    only_r1 = [c["x"] for c in india if c["r1"] and not c["r2"]]
    if both:
        print(f"  R1 and R2 hold on India for: {', '.join(both)}")
    if only_r1:
        print(f"  R1 without R2, a gain more objects alone would explain: "
              f"{', '.join(only_r1)}")
    if not both:
        print("  No newer checkpoint meets R1 and R2 on India. By R4 the "
              "RS-02 reading\n  holds for every public release.")
    narrowed = [g["checkpoint"] for g in gap_rows if g["meets_third"]]
    print(f"  R3: {', '.join(narrowed) if narrowed else 'no checkpoint'} "
          f"reaches one third of its own Slovenia recall")
    sl = [c for c in changes if c["country"] == "slovenia"
          and c["y"] == REFERENCE and c["r1"]]
    if sl:
        print(f"  On Slovenia, recall rises with an interval above zero for: "
              f"{', '.join(c['x'] for c in sl)}")

    out = project / "results"
    T.write_csv(out / "newer_checkpoints.csv", summary)
    T.write_csv(out / "newer_checkpoints_changes.csv", changes)
    T.write_csv(out / "newer_checkpoints_gap.csv", gap_rows)
    T.write_csv(out / "newer_checkpoints_widths.csv", width_rows)
    print("\n  wrote results\\newer_checkpoints.csv, _changes.csv, _gap.csv "
          "and _widths.csv")
    print(RULE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True,
                    choices=["download", "run", "report"])
    ap.add_argument("--only", nargs="*", default=[],
                    help="checkpoint keys to run, e.g. --only \"v1 full\"")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args()

    # torch before rasterio and scipy, or Windows can fail to load its DLLs
    import torch
    if args.threads:
        torch.set_num_threads(args.threads)
    here = Path(__file__).resolve().parent.parent
    if args.part == "download":
        download(here / "models")
    elif args.part == "run":
        run(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
