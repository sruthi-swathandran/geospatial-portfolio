"""
RS-02. How much of each reported number is the setting being chosen on it?

Every figure this project quotes comes from the best setting of a sweep,
picked on the same parcels the figure is reported from. Watershed 0.02 is the
maximum-gap row of the sweep that reports it, felzenszwalb 100 likewise, SAM
0.50 likewise. There is no held-out split anywhere in the work, which is F-07
in REVIEW.md, and the size of the resulting optimism has never been measured.

This measures it, and it reruns nothing. Every setting already has its own
per-parcel table on disk with a chip column, so the split is a re-analysis.
Chips are shuffled once with a fixed seed and cut in half. The best setting is
chosen on the first half and read on the second. The difference between that
and the published figure is what choosing on the reporting data was worth.

Chips rather than parcels are the unit of the split, for the reason
bootstrap_ci.py gives: parcels inside one chip share the scene, the season, the
cloud state and the annotator, so splitting parcels would leak a chip across
both halves.

The split is repeated over several shuffles, because a single cut of 398 chips
carries its own noise and a one-off difference would say very little.

    python src\\holdout.py --country india
    python src\\holdout.py --country slovenia --repeats 40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

SWEEPS = {
    "watershed": ["0p005", "0p01", "0p02", "0p05", "0p08",
                  "0p1", "0p13", "0p16", "0p2", "0p3"],
    "felzenszwalb": ["25", "50", "100", "150", "200", "300", "400", "800"],
    "sam_vit_h_true": ["0p50", "0p60", "0p70", "0p80", "0p88"],
    "sam_vit_h_false": ["0p50", "0p60", "0p70", "0p80", "0p88"],
}


def load_sweep(country: str, method: str, tags, iou: float):
    """Per-parcel hits for every setting of one method, keyed by setting."""
    rd = F.PROJECT / "results" / country
    out = {}
    for t in tags:
        path = rd / f"parcel_width_seg_{method}_{t}_min500.csv"
        if not path.exists():
            continue
        d = pd.read_csv(path)[["chip", "parcel_id", "best_iou"]]
        d["hit"] = d["best_iou"] >= iou
        out[t.replace("p", ".")] = d
    return out


def one_split(sweep, chips, rng):
    """Choose the best setting on one half, read it on the other."""
    order = rng.permutation(len(chips))
    cut = len(chips) // 2
    tune = set(chips[order[:cut]])
    report = set(chips[order[cut:]])

    best_tag, best_rate = None, -1.0
    for tag, d in sweep.items():
        r = d[d["chip"].isin(tune)]["hit"].mean()
        if np.isfinite(r) and r > best_rate:
            best_tag, best_rate = tag, float(r)
    if best_tag is None:
        return None
    held = float(sweep[best_tag][sweep[best_tag]["chip"].isin(report)]["hit"].mean())
    return best_tag, best_rate, held


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="india")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--repeats", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260923)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    print(RULE)
    print(f"HELD-OUT SELECTION, {args.country.upper()}, "
          f"{args.repeats} splits")
    print(RULE)
    print("  the published figure picks its setting on the parcels it reports")
    print("  from. these pick on one half of the chips and report on the "
          "other.\n")
    print(f"  {'method':>18} {'published':>10} {'held out':>10} "
          f"{'optimism':>10}  setting chosen most often")

    rows = []
    for method, tags in SWEEPS.items():
        sweep = load_sweep(args.country, method, tags, args.iou)
        if len(sweep) < 2:
            print(f"  {method:>18}  only {len(sweep)} setting on disk, skipped")
            continue

        chips = np.array(sorted({c for d in sweep.values()
                                 for c in d["chip"].unique()}))

        # what the project currently reports: best on everything, read on
        # everything
        published_tag, published = None, -1.0
        for tag, d in sweep.items():
            r = float(d["hit"].mean())
            if r > published:
                published_tag, published = tag, r

        picks, helds = [], []
        for _ in range(args.repeats):
            res = one_split(sweep, chips, rng)
            if res is None:
                continue
            tag, _, held = res
            picks.append(tag)
            helds.append(held)

        if not helds:
            continue
        held_med = float(np.median(helds))
        common = max(set(picks), key=picks.count)
        agree = picks.count(common) / len(picks)
        print(f"  {method:>18} {published:>10.4f} {held_med:>10.4f} "
              f"{published - held_med:>+10.4f}  {common} "
              f"({agree * 100:.0f}% of splits)")
        rows.append({
            "country": args.country, "method": method,
            "published_setting": published_tag,
            "published_recall": round(published, 4),
            "heldout_recall_median": round(held_med, 4),
            "optimism": round(published - held_med, 4),
            "modal_setting": common,
            "setting_stability": round(agree, 3),
            "splits": len(helds),
        })

    if rows:
        out = F.PROJECT / "results" / args.country / "holdout_selection.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\n  wrote {out.relative_to(F.PROJECT)}")

    print("\n" + RULE)
    print("Optimism is how much the published figure owes to picking its own")
    print("setting. Setting stability says whether the choice was stable at")
    print("all: a setting chosen in 90% of splits was never really a free")
    print("parameter, and one chosen in 30% was being fitted to noise.")
    print(RULE)


if __name__ == "__main__":
    main()
