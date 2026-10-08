"""
RS-02. Does a December to February image change what FTW and watershed find
in India?

season_test.py found that India's second FTW image, March to June, works
against the checkpoint, and that neither window shows rabi crops standing.
rabi_download.py builds a third image, December to February, the way FTW
builds its own. This gives it to the same two methods.

Windows are named by letter: b is FTW's window_b (March to June), a is
window_a (July to November), r is the rabi image. FTW reads eight channels,
the first four in window_b's place and the last four in window_a's.

    FTW, as given           shipped        b, a     the published run
                            a twice        a, a     best arrangement so far
                            rabi for b     r, a     the dry season replaced
                            a then rabi    a, r     the same, order swapped
                            rabi twice     r, r

    watershed gradient      a alone, r alone, a and r stacked, and b and a
                            stacked as published

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
Chips are those whose rabi image has 10% chip cloud or less, from
results/india/rabi_scenes.csv. Every arrangement is scored on those same
chips, the shipped run included, so no comparison mixes chip sets.

Changes are read chip by chip: whole chips are resampled 2,000 times and the
same resample is applied to both arrangements, giving a 95% interval on the
difference.

    A rabi image helps the checkpoint if "rabi for b" beats "shipped" with an
    interval on the difference above zero.

    It helps beyond dropping the dry-season image if "rabi for b" beats
    "a twice" the same way.

    The rabi image carries more of the visible boundaries than kharif if
    watershed on r alone beats a alone at FTW's object count, interval above
    zero; it adds to them if a and r stacked beats b and a stacked.

    Season is at most a minor cause of the India gap if the best arrangement
    still leaves FTW below a third of Slovenia's 22.22%, that is under 7.41%.

Both rabi seasons are run. A reading stands only if 2015-16 and 2016-17 agree
on its direction; where they disagree it is reported as unresolved.

    python src\\rabi_test.py --season 2016-17
    python src\\rabi_test.py --season 2015-16
    python src\\rabi_test.py --season 2016-17 --part watershed --limit 10
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
MAX_CLOUD = 0.10
SLOVENIA_FTW = 0.2222
FTW_ARRANGEMENTS = {
    "shipped": ("b", "a"),
    "a twice": ("a", "a"),
    "rabi for b": ("r", "a"),
    "a then rabi": ("a", "r"),
    "rabi twice": ("r", "r"),
}
WS_ARRANGEMENTS = {
    "b and a": ("b", "a"),
    "a alone": ("a",),
    "r alone": ("r",),
    "a and r": ("a", "r"),
}
WIDTH_EDGES = [0, 20, 30, 50, np.inf]
WIDTH_LABELS = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]


def usable_chips(F, season: str, limit: int) -> list:
    log = F.RESULTS / "rabi_scenes.csv"
    if not log.exists():
        sys.exit(f"{log} not found. Run rabi_download.py first.")
    with log.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["season"] == season]
    ok = [r["chip"] for r in rows if r["chip_cloud"] != ""
          and float(r["chip_cloud"]) <= MAX_CLOUD
          and (F.PROJECT / r["file"]).exists()]
    print(f"  {len(rows)} chips downloaded for {season}, {len(ok)} with "
          f"{MAX_CLOUD * 100:.0f}% chip cloud or less\n")
    ok = sorted(ok)
    return ok[:limit] if limit else ok


def windows(F, season: str, chip: str) -> dict:
    """Each window as raw integers, in FTW's band order."""
    import rasterio
    paths = {"a": F.IMG_A / chip, "b": F.IMG_B / chip,
             "r": F.PROJECT / "data" / "rabi" / "india" / season / chip}
    out = {}
    for k, p in paths.items():
        with rasterio.open(p) as s:
            out[k] = s.read(F.band_index(p, F.FTW_BANDS)).astype(np.int32)
    return out


def paired(hits: dict, n: np.ndarray, x: str, y: str, boots: int,
           rng) -> tuple:
    """Recall of x minus recall of y, whole chips resampled in pairs."""
    k = len(n)
    hx, hy = np.asarray(hits[x]), np.asarray(hits[y])
    point = (hx.sum() - hy.sum()) / n.sum()
    d = np.empty(boots)
    for i in range(boots):
        idx = rng.integers(0, k, k)
        d[i] = (hx[idx].sum() - hy[idx].sum()) / n[idx].sum()
    lo, hi = np.percentile(d, (2.5, 97.5))
    return float(point), float(lo), float(hi)


def verdict(lo: float) -> str:
    return "above zero" if lo > 0 else "not above zero"


def run_ftw(F, C, S, T, season, chips, args, rng) -> list:
    import rasterio
    import torch
    from scipy.ndimage import label as cc_label
    import run_inference as RI

    if args.threads:
        torch.set_num_threads(args.threads)
    model, _ = RI.load_model(str(F.PROJECT / "models" / "3class_full.ckpt"))
    min_px = int(round(500.0 / F.grid_pixel_area_m2()))
    wmap = T.widths(F)

    print(RULE)
    print(f"FTW WITH A DECEMBER TO FEBRUARY IMAGE, {season}, "
          f"{len(chips)} chips")
    print(RULE)
    hits = {v: [] for v in FTW_ARRANGEMENTS}
    objs = {v: [] for v in FTW_ARRANGEMENTS}
    nulls = {v: [] for v in FTW_ARRANGEMENTS}
    n, parcel_rows = [], []
    differ = total = 0
    tic = time.time()

    for start in range(0, len(chips), args.batch):
        batch = chips[start:start + args.batch]
        wins = [windows(F, season, c) for c in batch]
        preds = {}
        with torch.inference_mode():
            for v, (s1, s2) in FTW_ARRANGEMENTS.items():
                x = torch.stack([torch.from_numpy(
                    np.concatenate([w[s1], w[s2]])).float() / 3000
                    for w in wins])
                preds[v] = model(x).argmax(dim=1).cpu().numpy().astype(
                    np.uint8)
        for k, chip in enumerate(batch):
            with rasterio.open(F.RESULTS / "pred_3class_full" / chip) as s:
                pub = s.read(1)
            differ += int((pub != preds["shipped"][k]).sum())
            total += pub.size
            _, _, _, full = F.load_labels(chip)
            if full.max() == 0:
                for v in FTW_ARRANGEMENTS:
                    hits[v].append(0)
                    objs[v].append(0)
                    nulls[v].append(0.0)
                n.append(0)
                continue
            for v in FTW_ARRANGEMENTS:
                lab, _ = cc_label(preds[v][k] == 1)
                seg = C.drop_small(lab.astype(np.int32), min_px)
                n_obj = C.object_count(seg)
                ious = S.parcel_scores(full, seg)
                hits[v].append(sum(x >= 0.5 for x in ious.values()))
                objs[v].append(n_obj)
                found = 0
                for _ in range(args.null_draws):
                    nseg = C.null_segments(full.shape, n_obj, rng)
                    found += sum(x >= 0.5 for x in
                                 S.parcel_scores(full, nseg).values())
                nulls[v].append(found / max(1, args.null_draws))
                for pid, x in ious.items():
                    parcel_rows.append({
                        "season": season, "arrangement": v, "chip": chip,
                        "parcel_id": pid,
                        "width_m": round(wmap.get((chip, pid), np.nan), 2),
                        "best_iou": round(x, 4), "found": int(x >= 0.5)})
            n.append(len(ious))
        done_n = start + len(batch)
        if done_n % 40 < args.batch or done_n == len(chips):
            rate = done_n / (time.time() - tic)
            print(f"    {done_n:>4} / {len(chips)}   "
                  f"{(len(chips) - done_n) / rate / 60:.1f} min left")

    n = np.array(n)
    print(f"\n  shipped run against pred_3class_full: {differ:,} of "
          f"{total:,} pixels differ")
    print(f"  {int(n.sum()):,} labelled parcels on these chips\n")
    print(f"  {'arrangement':<13}{'objects':>9}{'recall':>9}{'null':>8}")
    summary = []
    for v in FTW_ARRANGEMENTS:
        rec = np.sum(hits[v]) / n.sum()
        lab = n > 0
        o = float(np.mean(np.array(objs[v])[lab]))
        nul = np.sum(nulls[v]) / n.sum()
        print(f"  {v:<13}{o:>9.1f}{rec * 100:>8.2f}%{nul * 100:>7.2f}%")
        summary.append({"season": season, "arrangement": v,
                        "chips": int(lab.sum()), "parcels": int(n.sum()),
                        "objects_per_chip": round(o, 1),
                        "recall": round(rec, 4), "null_recall": round(nul, 4),
                        "pixels_differing_from_published":
                            differ if v == "shipped" else ""})

    print("\n  changes, chip by chip, 95% interval")
    tests = [("rabi for b", "shipped"), ("rabi for b", "a twice"),
             ("a then rabi", "shipped"), ("rabi twice", "shipped"),
             ("a twice", "shipped")]
    changes = []
    for x, y in tests:
        pt, lo, hi = paired(hits, n, x, y, args.boots, rng)
        print(f"    {x:<12} minus {y:<9}{pt * 100:+7.2f}  "
              f"[{lo * 100:+.2f}, {hi * 100:+.2f}]   {verdict(lo)}")
        changes.append({"season": season, "method": "ftw", "x": x, "y": y,
                        "change": round(pt, 4), "lo": round(lo, 4),
                        "hi": round(hi, 4)})

    best = max(summary, key=lambda r: r["recall"])
    print(f"\n  best arrangement {best['arrangement']}, "
          f"{best['recall'] * 100:.2f}%, against Slovenia's "
          f"{SLOVENIA_FTW * 100:.2f}%: "
          f"{SLOVENIA_FTW / best['recall']:.1f} times lower" if best["recall"]
          else "\n  nothing found")

    T.write_csv(F.RESULTS / f"rabi_test_{season}_ftw.csv", summary)
    T.write_csv(F.RESULTS / f"rabi_test_{season}_ftw_parcels.csv",
                parcel_rows)
    return changes


def run_watershed(F, C, S, T, season, chips, args, rng) -> list:
    settings = list(C.SWEEPS["watershed"]) + T.EXTRA_WS
    min_px = int(round(500.0 / F.grid_pixel_area_m2()))
    with (F.RESULTS / "segmenter_comparison_min500.csv").open(
            encoding="utf-8", newline="") as fh:
        budget = next(float(r["objects_per_chip"])
                      for r in csv.DictReader(fh) if r["method"] == "ftw")

    print(RULE)
    print(f"WATERSHED WITH A DECEMBER TO FEBRUARY IMAGE, {season}, "
          f"{len(chips)} chips, read at {budget:.1f} objects per chip")
    print(RULE)
    shape = (len(chips), len(settings))
    hits = {v: np.zeros(shape) for v in WS_ARRANGEMENTS}
    objs = {v: np.zeros(shape) for v in WS_ARRANGEMENTS}
    n = np.zeros(len(chips))
    keep = np.zeros(len(chips), bool)
    tic = time.time()
    for i, chip in enumerate(chips):
        _, _, _, full = F.load_labels(chip)
        if full.max() == 0:
            continue
        keep[i] = True
        wins = windows(F, season, chip)
        for v, parts in WS_ARRANGEMENTS.items():
            stack = np.concatenate([np.stack([C.stretch(b) for b in wins[p]])
                                    for p in parts])
            grad = C.gradient(stack)
            for j, h in enumerate(settings):
                seg = C.drop_small(C.segment(stack, grad, "watershed", h),
                                   min_px)
                ious = S.parcel_scores(full, seg)
                hits[v][i, j] = sum(x >= 0.5 for x in ious.values())
                objs[v][i, j] = C.object_count(seg)
                n[i] = len(ious)
        if (i + 1) % 20 == 0 or i + 1 == len(chips):
            rate = (i + 1) / (time.time() - tic)
            print(f"    {i + 1:>4} / {len(chips)}   "
                  f"{(len(chips) - i - 1) / rate / 60:.1f} min left")

    n = n[keep]
    for v in WS_ARRANGEMENTS:
        hits[v], objs[v] = hits[v][keep], objs[v][keep]

    def at(v, idx):
        return T.at_budget(objs[v][idx].mean(0),
                           hits[v][idx].sum(0) / n[idx].sum(), budget)

    k = len(n)
    every = np.arange(k)
    print(f"\n  {'gradient from':<14}{'recall at budget':>18}")
    rows = []
    for v in WS_ARRANGEMENTS:
        r = at(v, every)
        clamped = not (objs[v].mean(0).min() <= budget
                       <= objs[v].mean(0).max())
        print(f"  {v:<14}{r * 100:>17.2f}%"
              f"{'   clamped' if clamped else ''}")
        rows.append({"season": season, "arrangement": v,
                     "recall_at_budget": round(r, 4), "clamped": clamped})

    print("\n  changes, chip by chip, 95% interval")
    changes = []
    for x, y in (("r alone", "a alone"), ("a and r", "b and a"),
                 ("a and r", "a alone")):
        pt = at(x, every) - at(y, every)
        d = np.empty(args.boots)
        for b in range(args.boots):
            idx = rng.integers(0, k, k)
            d[b] = at(x, idx) - at(y, idx)
        lo, hi = np.percentile(d, (2.5, 97.5))
        print(f"    {x:<9} minus {y:<9}{pt * 100:+7.2f}  "
              f"[{lo * 100:+.2f}, {hi * 100:+.2f}]   {verdict(lo)}")
        changes.append({"season": season, "method": "watershed", "x": x,
                        "y": y, "change": round(pt, 4), "lo": round(lo, 4),
                        "hi": round(hi, 4)})
    T.write_csv(F.RESULTS / f"rabi_test_{season}_watershed.csv", rows)
    return changes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=True, choices=["2015-16", "2016-17"])
    ap.add_argument("--part", default="all",
                    choices=["all", "ftw", "watershed"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261009)
    args = ap.parse_args()

    if args.part in ("all", "ftw"):
        # torch before rasterio and scipy, or Windows can fail to load its DLLs
        import torch                                          # noqa: F401
    import season_test as T
    F, C, S = T.load_country("india")
    rng = np.random.default_rng(args.seed)

    print(RULE)
    print(f"RABI TEST, SEASON {args.season}")
    print(RULE)
    chips = usable_chips(F, args.season, args.limit)
    changes = []
    if args.part in ("all", "ftw"):
        changes += run_ftw(F, C, S, T, args.season, chips, args, rng)
        print()
    if args.part in ("all", "watershed"):
        changes += run_watershed(F, C, S, T, args.season, chips, args, rng)
    T.write_csv(F.RESULTS / f"rabi_test_{args.season}_changes.csv", changes)
    print(f"\n  wrote results\\india\\rabi_test_{args.season}_*.csv")
    print(RULE)


if __name__ == "__main__":
    main()
