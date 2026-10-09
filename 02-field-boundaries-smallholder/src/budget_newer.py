"""
RS-02. Watershed and SAM read again at the object budget of FTW's newer
checkpoints.

Until now every matched-budget comparison was made against FTW's v1
checkpoint: watershed and SAM were read at the number of objects v1 draws,
175 per chip in India and 19.5 in Slovenia. newer_checkpoints.py found that
FTW's v3 checkpoints do much better on India and draw more objects, 245 per
chip for v3 full B7. So the comparison is made again here, at each newer
checkpoint's own budget.

This is a follow-up chosen after newer_checkpoints.py's results were seen.
The rules below are set before this script's own results exist.

What is compared, chip by chip:

    FTW         per-chip results written by newer_checkpoints.py
    watershed   both windows stacked, as published, over the published sweep
                plus h of 0.4, 0.5 and 0.6, computed here and kept in
                results/<country>/watershed_chips_min500.csv
    SAM ViT-H   every composite in results/<country>/
                sam_raw_vit_h_p32_min500.csv, read from that file

A method's recall at a budget is interpolated between its settings on mean
objects per chip, as before.

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
    P0  Nothing is read unless the old numbers come back: watershed's recall
        at every published setting matches segmenter_comparison_min500.csv
        to four places, SAM's matches sam_comparison_vit_h_min500.csv to four
        places, and watershed at v1's budget matches
        season_watershed_budget.csv (0.1074 India, 0.0593 Slovenia).

    P1  At a checkpoint's budget, a method beats the checkpoint if the method
        minus the checkpoint has a 95% interval above zero, whole chips
        resampled 2,000 times in pairs. The checkpoint beats the method if
        the interval is below zero. Otherwise they are level.

    P2  A method that cannot reach the budget is read at its setting nearest
        to it. A verdict that favours whichever side draws fewer objects
        stands, since more objects would only have helped the other side.
        A verdict that favours the side drawing more objects is reported as
        unresolved.

    P3  The README's headline comparison is rewritten against v3 full B7,
        the best public checkpoint on both countries. v3.1 cc-by B7 is
        reported beside it as the best checkpoint under CC-BY.

    python src\\budget_newer.py --part watershed --limit 10
    python src\\budget_newer.py --part watershed
    python src\\budget_newer.py --part report
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
COUNTRIES = ("india", "slovenia")
CHECKPOINTS = ("v1 full", "v3 full b3", "v3 full b7", "v3.1 cc-by b3",
               "v3.1 cc-by b7")
HEADLINE = ("v3 full b7", "v3.1 cc-by b7")
WS_BUDGET_V1 = {"india": 0.1074, "slovenia": 0.0593}
SAM_NAMES = {"true": "SAM blue-green-red", "false": "SAM NIR-blue-green",
             "rgb": "SAM natural colour", "cir": "SAM colour infrared"}


def read_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def slug(key: str) -> str:
    return key.replace(" ", "_").replace(".", "")


# ---------------------------------------------------------------------------
# watershed, chip by chip
# ---------------------------------------------------------------------------

def run_watershed(args) -> None:
    import season_test as T
    for country in COUNTRIES:
        F, C, S = T.load_country(country)
        out = F.RESULTS / "watershed_chips_min500.csv"
        chips = T.chips_for(F, args.limit)
        have = read_rows(out)
        settings = list(C.SWEEPS["watershed"]) + T.EXTRA_WS
        if {r["chip"] for r in have} == set(chips) and not args.redo:
            print(f"  {country}: {out.name} is complete already")
            continue
        min_px = int(round(500.0 / F.grid_pixel_area_m2()))
        print(RULE)
        print(f"WATERSHED, {country.upper()}, {len(chips)} chips, "
              f"{len(settings)} settings")
        print(RULE)
        rows = []
        tic = time.time()
        for i, chip in enumerate(chips):
            _, _, _, full = F.load_labels(chip)
            if full.max() == 0:
                # kept so a finished file can be told from a partial one
                rows += [{"chip": chip, "setting": h, "parcels": 0,
                          "hits": 0, "objects": 0} for h in settings]
            else:
                stack = C.read_stack(chip)
                grad = C.gradient(stack)
                for h in settings:
                    seg = C.drop_small(C.segment(stack, grad, "watershed", h),
                                       min_px)
                    ious = S.parcel_scores(full, seg)
                    rows.append({
                        "chip": chip, "setting": h, "parcels": len(ious),
                        "hits": int(sum(x >= 0.5 for x in ious.values())),
                        "objects": C.object_count(seg)})
            if (i + 1) % 20 == 0 or i + 1 == len(chips):
                rate = (i + 1) / (time.time() - tic)
                print(f"    {i + 1:>4} / {len(chips)}   "
                      f"{(len(chips) - i - 1) / rate / 60:.1f} min left")
        T.write_csv(out, rows)
        print(f"  wrote results\\{country}\\{out.name}\n")


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

class Sweep:
    """One method's per-chip hits and objects at each of its settings."""

    def __init__(self, name: str, chips: list, settings: list,
                 hits: np.ndarray, objs: np.ndarray):
        self.name, self.chips, self.settings = name, chips, settings
        self.hits, self.objs = hits, objs          # chip by setting

    def at(self, budget: float, n: np.ndarray, idx=None) -> tuple:
        h = self.hits if idx is None else self.hits[idx]
        o = self.objs if idx is None else self.objs[idx]
        nn = n if idx is None else n[idx]
        mean_o = o.mean(0)
        rec = h.sum(0) / nn.sum()
        order = np.argsort(mean_o)
        r = float(np.interp(budget, mean_o[order], rec[order]))
        lo_o, hi_o = float(mean_o.min()), float(mean_o.max())
        used = min(max(budget, lo_o), hi_o)
        return r, used


def watershed_sweep(F, chips: list) -> Sweep | None:
    rows = read_rows(F.RESULTS / "watershed_chips_min500.csv")
    if not rows:
        return None
    settings = sorted({float(r["setting"]) for r in rows})
    by = {(r["chip"], float(r["setting"])): r for r in rows}
    if any((c, settings[0]) not in by for c in chips):
        return None
    hits = np.array([[float(by[(c, s)]["hits"]) for s in settings]
                     for c in chips])
    objs = np.array([[float(by[(c, s)]["objects"]) for s in settings]
                     for c in chips])
    return Sweep("watershed", chips, settings, hits, objs)


def sam_sweeps(F, chips: list) -> list:
    path = F.RESULTS / "sam_raw_vit_h_p32_min500.csv"
    if not path.exists():
        print(f"  {path.name} not found, so SAM is left out here")
        return []
    hits = defaultdict(float)
    objs = {}
    keys = set()
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["is_null"] != "0":
                continue
            k = (r["composite"].lower(), r["setting"])
            keys.add(k)
            hits[k + (r["chip"],)] += int(r["found"])
            objs[k + (r["chip"],)] = float(r["objects"])
    out = []
    for comp in sorted({k[0] for k in keys}):
        settings = sorted({k[1] for k in keys if k[0] == comp})
        if any((comp, settings[0], c) not in objs for c in chips):
            print(f"  {comp}: not every chip is in {path.name}, left out")
            continue
        h = np.array([[hits[(comp, s, c)] for s in settings] for c in chips])
        o = np.array([[objs[(comp, s, c)] for s in settings] for c in chips])
        out.append(Sweep(SAM_NAMES.get(comp, f"SAM {comp}"), chips, settings,
                         h, o))
    return out


def ftw_chips(F, key: str) -> dict:
    rows = read_rows(F.RESULTS / "newer_ckpt" / f"{slug(key)}_chips.csv")
    return {r["chip"]: r for r in rows if float(r["parcels"]) > 0}


def check_p0(F, country, ws: Sweep, sams: list, n: np.ndarray,
             v1_budget: float) -> bool:
    ok = True
    pub = read_rows(F.RESULTS / "segmenter_comparison_min500.csv")
    pub_ws = {float(r["setting"]): float(r["recall"]) for r in pub
              if r["method"] == "watershed"}
    matched = checked = 0
    for j, s in enumerate(ws.settings):
        if s in pub_ws:
            checked += 1
            rec = round(ws.hits[:, j].sum() / n.sum(), 4)
            if rec == round(pub_ws[s], 4):
                matched += 1
            else:
                print(f"    watershed h {s}: {rec:.4f} here, "
                      f"{pub_ws[s]:.4f} published")
    ok &= matched == checked
    print(f"  watershed: {matched} of {checked} published settings match")
    r, _ = ws.at(v1_budget, n)
    hit = round(r, 4) == WS_BUDGET_V1[country]
    ok &= hit
    print(f"  watershed at v1's budget of {v1_budget:.1f}: {r:.4f}, "
          f"published {WS_BUDGET_V1[country]:.4f}   "
          f"{'matches' if hit else 'DOES NOT MATCH'}")
    pub_sam = {(r["composite"].lower(), r["setting"]): float(r["recall"])
               for r in read_rows(F.RESULTS / "sam_comparison_vit_h_min500.csv")}
    name_to_comp = {v: k for k, v in SAM_NAMES.items()}
    for sw in sams:
        comp = name_to_comp.get(sw.name, sw.name)
        m = c = 0
        for j, s in enumerate(sw.settings):
            if (comp, s) in pub_sam:
                c += 1
                m += round(sw.hits[:, j].sum() / n.sum(), 4) == \
                    round(pub_sam[(comp, s)], 4)
        ok &= m == c
        print(f"  {sw.name}: {m} of {c} published settings match")
    return ok


def verdict(lo: float, hi: float, method_objs: float, ftw_objs: float,
            clamped: bool) -> str:
    if lo > 0:
        call, favours_method = "method ahead", True
    elif hi < 0:
        call, favours_method = "FTW ahead", False
    else:
        return "level"
    if not clamped:
        return call
    fewer_is_method = method_objs < ftw_objs
    if favours_method == fewer_is_method:
        return call + ", stands under P2"
    return "unresolved under P2"


def report(args) -> None:
    import season_test as T
    rng = np.random.default_rng(args.seed)
    rows_out, stop = [], False

    for country in COUNTRIES:
        F, _, _ = T.load_country(country)
        ftw = {k: ftw_chips(F, k) for k in CHECKPOINTS}
        if not ftw["v1 full"]:
            sys.exit(f"no newer_checkpoints.py results for {country}")
        chips = sorted(set.intersection(*(set(v) for v in ftw.values()
                                          if v)))
        n = np.array([float(ftw["v1 full"][c]["parcels"]) for c in chips])
        ws = watershed_sweep(F, chips)
        if ws is None:
            sys.exit(f"no watershed per-chip results for {country}. Run "
                     "--part watershed first.")
        sams = sam_sweeps(F, chips)

        print(RULE)
        print(f"{country.upper()}, {len(chips)} labelled chips")
        print(RULE)
        wsn = np.array([float(r["parcels"]) for r in read_rows(
            F.RESULTS / "watershed_chips_min500.csv")
            if float(r["setting"]) == ws.settings[0] and r["chip"] in
            set(chips)])
        if len(wsn) != len(n) or wsn.sum() != n.sum():
            print("  parcel counts differ between FTW and watershed files")
            stop = True
        v1_budget = float(np.mean([float(ftw["v1 full"][c]["objects"])
                                   for c in chips]))
        print("\n  P0, the old numbers")
        stop |= not check_p0(F, country, ws, sams, n, v1_budget)
        if args.limit_ok:
            stop = False

        methods = [ws] + sams
        print(f"\n  {'checkpoint':<15}{'budget':>8}{'FTW':>8}   "
              f"{'method':<22}{'at budget':>10}{'minus FTW':>11}"
              f"{'interval':>19}   reading")
        for key in CHECKPOINTS:
            if not ftw[key]:
                continue
            fh = np.array([float(ftw[key][c]["hits"]) for c in chips])
            fo = np.array([float(ftw[key][c]["objects"]) for c in chips])
            budget = float(fo.mean())
            f_rec = fh.sum() / n.sum()
            for m in methods:
                r, used = m.at(budget, n)
                clamped = abs(used - budget) > 1e-9
                d = np.empty(args.boots)
                k = len(chips)
                for b in range(args.boots):
                    idx = rng.integers(0, k, k)
                    d[b] = m.at(budget, n, idx)[0] - \
                        fh[idx].sum() / n[idx].sum()
                lo, hi = np.percentile(d, (2.5, 97.5))
                call = verdict(lo, hi, used, budget, clamped)
                note = f" (read at {used:.1f})" if clamped else ""
                print(f"  {key:<15}{budget:>8.1f}{f_rec * 100:>7.2f}%   "
                      f"{m.name:<22}{r * 100:>9.2f}%{(r - f_rec) * 100:>+10.2f}"
                      f"   [{lo * 100:+6.2f}, {hi * 100:+6.2f}]   {call}{note}")
                rows_out.append({
                    "country": country, "checkpoint": key,
                    "budget": round(budget, 1), "ftw_recall": round(f_rec, 4),
                    "method": m.name, "objects_used": round(used, 1),
                    "clamped": clamped, "recall_at_budget": round(r, 4),
                    "minus_ftw": round(r - f_rec, 4), "lo": round(lo, 4),
                    "hi": round(hi, 4), "reading": call,
                    "headline": key in HEADLINE})
            print()
    if stop:
        sys.exit("  P0 fails, so the readings above are not to be used. "
                 "Stop and check.")
    T.write_csv(F.PROJECT / "results" / "budget_newer.csv", rows_out)
    print("  wrote results\\budget_newer.csv")
    print(RULE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=["watershed", "report"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--limit-ok", action="store_true",
                    help="trial only: read on even when P0 fails")
    args = ap.parse_args()
    if args.part == "watershed":
        run_watershed(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
