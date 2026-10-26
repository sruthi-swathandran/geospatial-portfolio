"""
RS-02. Score the two fine-tuned v3 B7 checkpoints on the test chips.

kaggle/finetune_v3.py fine-tunes FTW v3 full B7 on India's train split in two
arms, India alone and India with as many Slovenian train chips, and keeps the
epoch with the best India val recall. This scores the two checkpoints it
returns on the same labelled test chips, 398 Indian and 185 Slovenian,
through the same code newer_checkpoints.py used for v3. Every difference is
then the weights. v3 full B7 is not run again; its saved per-chip files are
the reference.

Files from the Kaggle run, put in place by hand:
    models/v3b7_ft_india.ckpt
    models/v3b7_ft_india_slovenia.ckpt
    results/finetune/india/log.csv and done.json
    results/finetune/india_slovenia/log.csv and done.json

HOW IT WILL BE READ, SET BEFORE TRAINING
----------------------------------------
Differences are read chip by chip: whole chips are resampled 2,000 times,
the same resample for every checkpoint, giving a 95% interval.

    T0  Nothing is read unless each checkpoint's sha256 matches its
        done.json, its hyper_parameters name v3 full B7's sha256 as the
        base, and it was not a smoke run.

    T1  An arm finds more Indian parcels if its recall minus v3 full B7's has
        an interval above zero.

    T2  The gain comes from better placed boundaries if its recall above its
        own random-cell null, minus v3 full B7's, also has an interval above
        zero. T1 without T2 is reported as a gain more objects alone would
        explain.

    T3  Watershed is read at the arm's own object count, interpolated as in
        budget_newer.py and judged by that script's P1 and P2, to say whether
        an untrained method still matches the fine-tuned model.

    T4  The gap narrows if the arm's India recall over its own Slovenia
        recall, minus the same ratio for v3 full B7, has an interval above
        zero. v3 full B7 stands at 0.39.

    T5  Slovenia's change is reported beside India's. A Slovenian change
        with an interval below zero is reported as the arm forgetting.

    Reading. Fine-tuning helps on India if T1 and T2 hold for an arm. With
    two arms, a result that holds for one only is reported for that arm and
    not as a general effect of fine-tuning. If neither arm meets T1, the
    write-up says that more weight on India's presence-only labels does not
    move v3 on these chips. Recall by ground width band is reported as
    description, not judged.

    python src\\finetune_score.py --part check
    python src\\finetune_score.py --part run --limit 5
    python src\\finetune_score.py --part run
    python src\\finetune_score.py --part report
    python src\\finetune_score.py --part sam

Added after the result, 26 October 2026
---------------------------------------
T3 reads watershed only. Finding 1 also sets SAM against FTW, so --part sam
reads SAM's saved sweeps at each checkpoint's object count, interpolated and
judged as budget_newer.py judges them. It was written after the report above
had been seen, so it describes and decides nothing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
COUNTRIES = ("india", "slovenia")
BASE = "v3 full b7"
FT = {
    "v3 b7 ft india": {"arm": "india", "file": "v3b7_ft_india.ckpt"},
    "v3 b7 ft india+slovenia": {"arm": "india_slovenia",
                                "file": "v3b7_ft_india_slovenia.ckpt"},
}
BANDS = [(20, 30, "20 to 30 m"), (30, 50, "30 to 50 m"),
         (50, np.inf, "50 m up")]
PROJECT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def register() -> None:
    """Make newer_checkpoints.py's runner see the fine-tuned checkpoints."""
    import newer_checkpoints as NC
    for key, spec in FT.items():
        NC.CHECKPOINTS[key] = {
            "file": spec["file"],
            "licence": "derived from v3 full, noncommercial terms carry over"}


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def check(quiet: bool = False) -> bool:
    import torch
    import newer_checkpoints as NC
    base_sha = NC.CHECKPOINTS[BASE]["sha256"]
    ok, rows = True, []
    if not quiet:
        print(RULE)
        print("T0. THE FINE-TUNED CHECKPOINTS")
        print(RULE)
    for key, spec in FT.items():
        ckpt = PROJECT / "models" / spec["file"]
        done_path = PROJECT / "results" / "finetune" / spec["arm"] / "done.json"
        if not ckpt.exists() or not done_path.exists():
            print(f"  {key}: {ckpt.name} or {done_path.parent.name}"
                  f"\\done.json is missing")
            ok = False
            continue
        done = json.loads(done_path.read_text())
        got = sha256(ckpt)
        hp = torch.load(ckpt, map_location="cpu",
                        weights_only=False)["hyper_parameters"]
        ft = hp.get("fine_tune", {})
        checks = {
            "sha256 matches done.json": got == done.get("sha256"),
            "base is v3 full B7": ft.get("base_sha256") == base_sha,
            "not a smoke run": not ft.get("smoke", True),
        }
        ok &= all(checks.values())
        if not quiet:
            print(f"\n  {key}")
            for name, passed in checks.items():
                print(f"    {name:<26} {'yes' if passed else 'NO'}")
            print(f"    kept epoch {ft.get('best_epoch')} of "
                  f"{ft.get('epochs')}; India val recall "
                  f"{ft.get('india_val_recall_epoch0')} untouched, "
                  f"{ft.get('india_val_recall_best')} kept")
        rows.append({"checkpoint": key, "arm": spec["arm"],
                     "file": spec["file"], "sha256": got,
                     "epochs": ft.get("epochs"),
                     "best_epoch": ft.get("best_epoch"),
                     "lr": hp.get("lr"), "seed": ft.get("seed"),
                     "india_val_recall_epoch0":
                         ft.get("india_val_recall_epoch0"),
                     "india_val_recall_best": ft.get("india_val_recall_best"),
                     "passes_t0": all(checks.values())})
    if not quiet:
        write_csv(PROJECT / "results" / "finetune_checkpoints.csv", rows)
        print("\n  wrote results\\finetune_checkpoints.csv")
        print(RULE)
        print("T0 passes." if ok else "T0 FAILS. Nothing below is to be read.")
        print(RULE)
    return ok


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def run(args) -> None:
    import season_test as T
    import newer_checkpoints as NC
    if not check(quiet=True):
        sys.exit("T0 fails. Run --part check to see why.")
    register()
    for c_idx, country in enumerate(COUNTRIES):
        F, C, S = T.load_country(country)
        chips = T.chips_for(F, args.limit)
        print(RULE)
        print(f"FINE-TUNED v3 B7, {country.upper()}, {len(chips)} test chips")
        print(RULE)
        for k_idx, key in enumerate(FT, start=10):
            NC.run_one(F, C, S, T, key, k_idx, c_idx, chips, args)
        print()


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def interval(d: np.ndarray) -> tuple:
    lo, hi = np.percentile(d, (2.5, 97.5))
    return float(lo), float(hi)


def report(args) -> None:
    import season_test as T
    import newer_checkpoints as NC
    import budget_newer as BN
    if not check(quiet=True):
        sys.exit("T0 fails. Run --part check to see why.")
    register()
    keys = [BASE] + list(FT)
    rng = np.random.default_rng(args.seed)

    data = {}
    for country in COUNTRIES:
        F, _, _ = T.load_country(country)
        res = {}
        for k in keys:
            rows = NC.read_rows(F.RESULTS / "newer_ckpt"
                                / f"{NC.slug(k)}_chips.csv")
            if not rows:
                sys.exit(f"no results for {k} in {country}. Run --part run.")
            res[k] = {r["chip"]: r for r in rows}
        chips = sorted(c for c in set.intersection(*(set(v) for v in
                                                     res.values()))
                       if float(res[BASE][c]["parcels"]) > 0)
        arr = {k: NC.arrays(res, k, chips) for k in keys}
        idx = rng.integers(0, len(chips), (args.boots, len(chips)))
        rec = {k: arr[k][1][idx].sum(1) / arr[k][0][idx].sum(1) for k in keys}
        above = {k: (arr[k][1] - arr[k][2])[idx].sum(1) / arr[k][0][idx].sum(1)
                 for k in keys}
        # ftw_common is one module reloaded per country, so keep this
        # country's results folder now rather than the module itself
        here = SimpleNamespace(RESULTS=F.RESULTS)
        data[country] = dict(F=here, chips=chips, arr=arr, idx=idx, rec=rec,
                             above=above)

    scores, tests = [], []
    for country, d in data.items():
        print(RULE)
        print(f"{country.upper()}, {len(d['chips'])} labelled test chips")
        print(RULE)
        print(f"  {'checkpoint':<25}{'objects':>8}{'recall':>9}"
              f"{'interval':>18}{'null':>8}{'above null':>12}")
        for k in keys:
            n, h, z, o = d["arr"][k]
            lo, hi = interval(d["rec"][k])
            r = h.sum() / n.sum()
            print(f"  {k:<25}{o.mean():>8.1f}{r * 100:>8.2f}%"
                  f"   [{lo * 100:5.2f}, {hi * 100:5.2f}]"
                  f"{z.sum() / n.sum() * 100:>7.2f}%"
                  f"{(h - z).sum() / n.sum() * 100:>11.2f}%")
            scores.append({"country": country, "checkpoint": k,
                           "objects": round(float(o.mean()), 1),
                           "recall": round(float(r), 4), "lo": round(lo, 4),
                           "hi": round(hi, 4),
                           "null": round(float(z.sum() / n.sum()), 4),
                           "above_null": round(float((h - z).sum()
                                                     / n.sum()), 4)})
        print()

    def add(test, key, country, point, d):
        lo, hi = interval(d)
        call = ("above zero" if lo > 0 else "below zero" if hi < 0
                else "includes zero")
        tests.append({"test": test, "checkpoint": key, "country": country,
                      "point": round(point, 4), "lo": round(lo, 4),
                      "hi": round(hi, 4), "interval": call})
        return call

    print(RULE)
    print("T1 TO T5, EACH ARM AGAINST v3 FULL B7")
    print(RULE)
    ind, slo = data["india"], data["slovenia"]
    base_ratio = ind["rec"][BASE] / slo["rec"][BASE]
    for k in FT:
        n, h, z, _ = ind["arr"][k]
        nb, hb, zb, _ = ind["arr"][BASE]
        t1 = add("T1 India recall minus v3", k, "india",
                 h.sum() / n.sum() - hb.sum() / nb.sum(),
                 ind["rec"][k] - ind["rec"][BASE])
        t2 = add("T2 India above null minus v3", k, "india",
                 (h - z).sum() / n.sum() - (hb - zb).sum() / nb.sum(),
                 ind["above"][k] - ind["above"][BASE])
        ratio = ind["rec"][k] / slo["rec"][k]
        pr = (ind["arr"][k][1].sum() / ind["arr"][k][0].sum()) / \
            (slo["arr"][k][1].sum() / slo["arr"][k][0].sum())
        pb = (ind["arr"][BASE][1].sum() / ind["arr"][BASE][0].sum()) / \
            (slo["arr"][BASE][1].sum() / slo["arr"][BASE][0].sum())
        t4 = add("T4 India over Slovenia minus v3", k, "both", pr - pb,
                 ratio - base_ratio)
        ns, hs, _, _ = slo["arr"][k]
        nsb, hsb, _, _ = slo["arr"][BASE]
        t5 = add("T5 Slovenia recall minus v3", k, "slovenia",
                 hs.sum() / ns.sum() - hsb.sum() / nsb.sum(),
                 slo["rec"][k] - slo["rec"][BASE])
        if t1 == "above zero" and t2 == "above zero":
            reading = "helps on India, from better placed boundaries"
        elif t1 == "above zero":
            reading = "finds more, by a gain more objects alone would explain"
        else:
            reading = "no gain on India"
        print(f"\n  {k}")
        for t in tests[-4:]:
            s = 1 if t["test"].startswith("T4") else 100
            unit = "ratio " if s == 1 else "points"
            print(f"    {t['test']:<34}{unit} {t['point'] * s:>+8.3f}"
                  f"   [{t['lo'] * s:+7.3f}, {t['hi'] * s:+7.3f}]"
                  f"   {t['interval']}")
        print(f"    ratio {pr:.3f} against v3's {pb:.3f}")
        print(f"    T5 on Slovenia: "
              f"{'the arm forgets' if t5 == 'below zero' else 'no loss'}")
        print(f"    reading: {reading}")
        tests[-4]["reading"] = reading
        for t in tests[-3:]:
            t["reading"] = ""

    print("\n" + RULE)
    print("T3. WATERSHED AT EACH CHECKPOINT'S OBJECT COUNT")
    print(RULE)
    budget_rows = []
    for country, d in data.items():
        n = d["arr"][BASE][0]
        ws = BN.watershed_sweep(d["F"], d["chips"])
        if ws is None:
            print(f"  {country}: no watershed per-chip results, T3 skipped")
            continue
        for k in keys:
            _, h, _, o = d["arr"][k]
            budget = float(o.mean())
            r, used = ws.at(budget, n)
            clamped = abs(used - budget) > 1e-9
            diff = np.array([ws.at(budget, n, i)[0] - h[i].sum() / n[i].sum()
                             for i in d["idx"]])
            lo, hi = interval(diff)
            call = BN.verdict(lo, hi, used, budget, clamped)
            f_rec = h.sum() / n.sum()
            print(f"  {country:<9}{k:<25}{budget:>7.1f} objects  FTW "
                  f"{f_rec * 100:5.2f}%  watershed {r * 100:5.2f}%  "
                  f"[{lo * 100:+6.2f}, {hi * 100:+6.2f}]  {call}")
            budget_rows.append({"country": country, "checkpoint": k,
                                "budget": round(budget, 1),
                                "ftw_recall": round(f_rec, 4),
                                "watershed_at_budget": round(r, 4),
                                "objects_used": round(used, 1),
                                "minus_ftw": round(r - f_rec, 4),
                                "lo": round(lo, 4), "hi": round(hi, 4),
                                "reading": call})

    print("\n" + RULE)
    print("RECALL BY GROUND WIDTH, DESCRIPTION ONLY")
    print(RULE)
    width_rows = []
    for country, d in data.items():
        chips = set(d["chips"])
        for k in keys:
            rows = [r for r in NC.read_rows(d["F"].RESULTS / "newer_ckpt"
                                            / f"{NC.slug(k)}_parcels.csv")
                    if r["chip"] in chips and r["width_m"] not in ("", "nan")]
            for lo_w, hi_w, name in BANDS:
                band = [r for r in rows if lo_w <= float(r["width_m"]) < hi_w]
                if not band:
                    continue
                r_band = sum(int(r["found"]) for r in band) / len(band)
                width_rows.append({"country": country, "checkpoint": k,
                                   "band": name, "parcels": len(band),
                                   "recall": round(r_band, 4)})
                print(f"  {country:<9}{k:<25}{name:<12}{len(band):>6} "
                      f"{r_band * 100:>7.2f}%")

    res_dir = PROJECT / "results"
    write_csv(res_dir / "finetune_scores.csv", scores)
    write_csv(res_dir / "finetune_tests.csv", tests)
    write_csv(res_dir / "finetune_budget.csv", budget_rows)
    write_csv(res_dir / "finetune_widths.csv", width_rows)
    print("\n  wrote finetune_scores.csv, finetune_tests.csv, "
          "finetune_budget.csv and finetune_widths.csv in results")
    print(RULE)


def sam(args) -> None:
    """SAM at each checkpoint's object count, added after the result."""
    import season_test as T
    import newer_checkpoints as NC
    import budget_newer as BN
    register()
    keys = [BASE] + list(FT)
    rng = np.random.default_rng(args.seed)
    rows = []
    print(RULE)
    print("SAM AT EACH CHECKPOINT'S OBJECT COUNT, ADDED AFTER THE RESULT")
    print(RULE)
    for country in COUNTRIES:
        F, _, _ = T.load_country(country)
        res = {k: {r["chip"]: r for r in NC.read_rows(
            F.RESULTS / "newer_ckpt" / f"{NC.slug(k)}_chips.csv")}
            for k in keys}
        chips = sorted(c for c in set.intersection(*(set(v) for v in
                                                     res.values()))
                       if float(res[BASE][c]["parcels"]) > 0)
        sweeps = BN.sam_sweeps(SimpleNamespace(RESULTS=F.RESULTS), chips)
        n = NC.arrays(res, BASE, chips)[0]
        idx = rng.integers(0, len(chips), (args.boots, len(chips)))
        for k in keys:
            _, h, _, o = NC.arrays(res, k, chips)
            budget = float(o.mean())
            f_rec = h.sum() / n.sum()
            for m in sweeps:
                r, used = m.at(budget, n)
                clamped = abs(used - budget) > 1e-9
                diff = np.array([m.at(budget, n, i)[0]
                                 - h[i].sum() / n[i].sum() for i in idx])
                lo, hi = interval(diff)
                call = BN.verdict(lo, hi, used, budget, clamped)
                note = f" (read at {used:.1f})" if clamped else ""
                print(f"  {country:<9}{k:<25}{budget:>7.1f}  FTW "
                      f"{f_rec * 100:5.2f}%  {m.name:<22}{r * 100:6.2f}%  "
                      f"[{lo * 100:+6.2f}, {hi * 100:+6.2f}]  {call}{note}")
                rows.append({"country": country, "checkpoint": k,
                             "budget": round(budget, 1),
                             "ftw_recall": round(f_rec, 4), "method": m.name,
                             "objects_used": round(used, 1),
                             "clamped": clamped, "recall_at_budget": round(r, 4),
                             "minus_ftw": round(r - f_rec, 4),
                             "lo": round(lo, 4), "hi": round(hi, 4),
                             "reading": call})
        print()
    write_csv(PROJECT / "results" / "finetune_sam.csv", rows)
    print("  wrote results\\finetune_sam.csv")
    print(RULE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True,
                    choices=["check", "run", "report", "sam"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--null-draws", type=int, default=3)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args()

    # torch before rasterio and scipy, or Windows can fail to load its DLLs
    import torch
    if args.threads:
        torch.set_num_threads(args.threads)
    if args.part == "check":
        check()
    elif args.part == "run":
        run(args)
    elif args.part == "sam":
        sam(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
