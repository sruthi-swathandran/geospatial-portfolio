"""
RS-02. How much of the India gap is parcel shape.

The cross-country table compares parcels of the same ground width, and
Slovenia wins every band. Width is one number about a shape. Two parcels 30 m
across can be a 30 by 40 m block or a 30 by 300 m strip, and Slovenia's
cadastre is full of strips. If a strip is easier to recover than a block of
the same width, Slovenia's advantage at a given width could be its shapes and
not its imagery.

This asks that question of results already on disk. No model is rerun.

THE MEASURE
-----------
Elongation is a parcel's area over the square of its width:

    elongation = area / width ** 2

Width is the largest inscribed circle, the same width every table uses. For a
rectangle that ratio is its length over its width; a square scores 1 and a
disc 0.79. An L-shaped or ragged parcel also scores high, so this is a measure
of how far a parcel departs from a compact block, which is the property in
question, and it should not be read as a strict length to width ratio.

THE COMPARISON
--------------
Each parcel is placed in a cell by width band and elongation band. Slovenia's
recall is then recomputed with each cell weighted by India's share of parcels
in it. That gives three Slovenian figures for each method:

    as measured
    reweighted to India's mix of widths
    reweighted to India's mix of widths and elongations together

The first two reproduce what the cross-country table already says. The third
adds shape. If India's parcels are found less often because they are blocks
and blocks are hard, the third figure falls towards India's.

Each country's chips are resampled 2,000 times for an interval, since parcels
in one chip share a scene.

HOW IT WILL BE READ, SET BEFORE RUNNING
---------------------------------------
On a log scale, the share of the width-matched gap that shape accounts for is

    1 - log(ratio after width and shape) / log(ratio after width)

    0.5 or more         shape is a large part of the gap
    0.2 up to 0.5       shape is a part of it
    under 0.2           shape explains little of it

A negative share means India's mix of shapes is the easier one, and matching
on it widens the gap.

The elongation bands, under 1.5, 1.5 to 2.5, 2.5 to 4 and 4 up, were set from
the two countries' shape distributions before any recall was read in this
test. A second cut into six bands at the pooled sextiles is printed as a check
that the answer does not depend on where those edges fall.

Methods and files are those of the cross-country table in COMPARISON.md: FTW,
watershed at its best setting, SAM ViT-H true colour at 0.50.

    python src\\shape_test.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78
PROJECT = Path(__file__).resolve().parent.parent
COUNTRIES = ("india", "slovenia")

WIDTH_EDGES = [0, 20, 30, 50, np.inf]
WIDTH_LABELS = ["under 20 m", "20 to 30 m", "30 to 50 m", "50 m up"]
ELONG_EDGES = [0, 1.5, 2.5, 4, np.inf]
ELONG_LABELS = ["under 1.5", "1.5 to 2.5", "2.5 to 4", "4 up"]

METHODS = {
    "ftw": ("FTW 3-class FULL", "parcel_width_seg_ftw_min500.csv"),
    "watershed": ("watershed", "parcel_width_seg_watershed_min500.csv"),
    "sam_true": ("SAM ViT-H true colour",
                 "parcel_width_seg_sam_vit_h_true_0p50_min500.csv"),
}


def load(country: str, fname: str, iou: float) -> pd.DataFrame:
    path = PROJECT / "results" / country / fname
    if not path.exists():
        sys.exit(f"{path} not found")
    d = pd.read_csv(path)
    d["width_m"] = d["width_native_px"] * 10.0
    d["elong"] = d["hectares"] * 10000.0 / d["width_m"] ** 2
    d["hit"] = (d["best_iou"] >= iou).astype(int)
    d["wband"] = pd.cut(d["width_m"], WIDTH_EDGES, labels=False, right=False)
    return d


def cell_matrix(d: pd.DataFrame, cell: str, n_cells: int) -> tuple:
    """Per chip, parcels and hits in each cell, as two chip by cell arrays."""
    chips = sorted(d["chip"].unique())
    pos = {c: i for i, c in enumerate(chips)}
    n = np.zeros((len(chips), n_cells))
    h = np.zeros((len(chips), n_cells))
    ci = d["chip"].map(pos).to_numpy()
    cc = d[cell].to_numpy().astype(int)
    np.add.at(n, (ci, cc), 1)
    np.add.at(h, (ci, cc), d["hit"].to_numpy())
    return n, h


def standardised(n, h, weights) -> float:
    """Recall with each cell weighted by an outside share of parcels.

    A cell this country has no parcels in cannot be read, so the weights are
    renormalised over the cells it does have. coverage() says how much of the
    weight that drops.
    """
    tot_n, tot_h = n.sum(0), h.sum(0)
    ok = tot_n > 0
    w = weights * ok
    if w.sum() == 0:
        return float("nan")
    rate = np.divide(tot_h, tot_n, out=np.zeros_like(tot_h), where=ok)
    return float((w * rate).sum() / w.sum())


def coverage(n, weights) -> float:
    return float((weights * (n.sum(0) > 0)).sum() / weights.sum())


def compare(ind, slo, cell: str, n_cells: int, boots: int, rng) -> dict:
    """India recall, and Slovenia's under India's weights, with intervals."""
    ni, hi = cell_matrix(ind, cell, n_cells)
    ns, hs = cell_matrix(slo, cell, n_cells)
    weights = ni.sum(0) / ni.sum()
    point = {"india": hi.sum() / ni.sum(),
             "slovenia": standardised(ns, hs, weights),
             "coverage": coverage(ns, weights)}

    draws = []
    for _ in range(boots):
        a = rng.integers(0, ni.shape[0], ni.shape[0])
        b = rng.integers(0, ns.shape[0], ns.shape[0])
        nia, hia = ni[a], hi[a]
        w = nia.sum(0) / nia.sum()
        r_i = hia.sum() / nia.sum()
        r_s = standardised(ns[b], hs[b], w)
        draws.append((r_i, r_s))
    point["draws"] = np.array(draws)
    return point


def log_ratio(draws) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(draws[:, 1] / draws[:, 0])


def ci(x) -> str:
    x = x[np.isfinite(x)]
    if not len(x):
        return "not readable"
    lo, hi = np.percentile(x, (2.5, 97.5))
    return f"[{lo:.2f}, {hi:.2f}]"


def reading(share: float) -> str:
    if not np.isfinite(share):
        return "not readable"
    if share >= 0.5:
        return "shape is a large part of the gap"
    if share >= 0.2:
        return "shape is a part of the gap"
    if share >= 0:
        return "shape explains little of the gap"
    return "India's shapes are the easier mix; matching widens the gap"


def describe(frames) -> None:
    print(RULE)
    print("HOW THE PARCELS ARE SHAPED")
    print(RULE)
    print("  elongation is area over width squared; a square is 1\n")
    print(f"  {'':<12}{'parcels':>9}{'q25':>8}{'median':>8}{'q75':>8}"
          f"{'q90':>8}")
    for c in COUNTRIES:
        e = frames[c]["elong"]
        q = e.quantile([0.25, 0.5, 0.75, 0.9]).to_numpy()
        print(f"  {c:<12}{len(e):>9,}" + "".join(f"{v:>8.2f}" for v in q))
    print("\n  share of each width band in each elongation band")
    for c in COUNTRIES:
        d = frames[c]
        t = pd.crosstab(pd.Categorical.from_codes(d["wband"], WIDTH_LABELS),
                        pd.Categorical.from_codes(d["eband"], ELONG_LABELS),
                        rownames=["width"], colnames=["elongation"],
                        normalize="index")
        print(f"\n  {c}")
        print("    " + (t * 100).round(1).to_string().replace("\n", "\n    "))


def band_table(ind, slo, label, boots, rng) -> list:
    """Within each width band, Slovenia reweighted to India's elongations."""
    rows = []
    print(f"\n  {label}")
    print(f"    {'width':<12}{'India':>9}{'Slovenia':>10}{'reweighted':>12}"
          f"{'ratio':>8}{'after':>8}")
    for wb, wl in enumerate(WIDTH_LABELS):
        a, b = ind[ind["wband"] == wb], slo[slo["wband"] == wb]
        if a.empty or b.empty:
            continue
        r_i = a["hit"].mean()
        r_s = b["hit"].mean()
        res = compare(a, b, "eband", len(ELONG_LABELS), boots, rng)
        raw = f"{r_s / r_i:.1f}x" if r_i > 0 else "n/a"
        after = f"{res['slovenia'] / r_i:.1f}x" if r_i > 0 else "n/a"
        print(f"    {wl:<12}{r_i * 100:>8.2f}%{r_s * 100:>9.2f}%"
              f"{res['slovenia'] * 100:>11.2f}%{raw:>8}{after:>8}")
        rows.append({"method": label, "width_band": wl,
                     "india_parcels": len(a), "slovenia_parcels": len(b),
                     "india_found": int(a["hit"].sum()),
                     "slovenia_found": int(b["hit"].sum()),
                     "india_recall": round(r_i, 4),
                     "slovenia_recall": round(r_s, 4),
                     "slovenia_reweighted": round(res["slovenia"], 4),
                     "coverage": round(res["coverage"], 4)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--boots", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261006)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    data = {m: {c: load(c, f, args.iou) for c in COUNTRIES}
            for m, (_, f) in METHODS.items()}

    # pooled sextiles of elongation for the robustness cut, from FTW's
    # files since every method scores the same parcels
    pooled = pd.concat([data["ftw"][c]["elong"] for c in COUNTRIES])
    sext = [0] + list(pooled.quantile([1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6])) \
        + [np.inf]

    for m in METHODS:
        for c in COUNTRIES:
            d = data[m][c]
            d["eband"] = pd.cut(d["elong"], ELONG_EDGES, labels=False,
                                right=False)
            d["eband6"] = pd.cut(d["elong"], sext, labels=False, right=False)
            d["cell"] = d["wband"] * len(ELONG_LABELS) + d["eband"]
            d["cell6"] = d["wband"] * 6 + d["eband6"]
            d["wcell"] = d["wband"]

    describe(data["ftw"])

    print("\n" + RULE)
    print("ALL PARCELS, SLOVENIA REWEIGHTED TO INDIA'S MIX")
    print(RULE)
    print("  ratio is Slovenia's recall over India's; share is how much of the")
    print("  width-matched gap shape accounts for, on a log scale\n")

    summary = []
    for m, (label, _) in METHODS.items():
        ind, slo = data[m]["india"], data[m]["slovenia"]
        r_i = ind["hit"].mean()
        r_s = slo["hit"].mean()
        # the same rng stream for each cut, so the intervals share draws
        state = rng.bit_generator.state
        w_only = compare(ind, slo, "wcell", len(WIDTH_LABELS), args.boots, rng)
        rng.bit_generator.state = state
        w_shape = compare(ind, slo, "cell", 4 * len(ELONG_LABELS),
                          args.boots, rng)
        rng.bit_generator.state = state
        w_shape6 = compare(ind, slo, "cell6", 4 * 6, args.boots, rng)

        lw = log_ratio(w_only["draws"])
        ls = log_ratio(w_shape["draws"])
        l6 = log_ratio(w_shape6["draws"])
        with np.errstate(divide="ignore", invalid="ignore"):
            share_d = 1 - ls / lw
            share6_d = 1 - l6 / lw
        rw = w_only["slovenia"] / r_i
        rs = w_shape["slovenia"] / r_i
        r6 = w_shape6["slovenia"] / r_i
        share = 1 - np.log(rs) / np.log(rw)
        share6 = 1 - np.log(r6) / np.log(rw)

        print(f"  {label}")
        print(f"    India                         {r_i * 100:6.2f}%")
        print(f"    Slovenia as measured          {r_s * 100:6.2f}%   "
              f"ratio {r_s / r_i:5.2f}x")
        print(f"    reweighted, width             {w_only['slovenia'] * 100:6.2f}%"
              f"   ratio {rw:5.2f}x  {ci(np.exp(lw))}")
        print(f"    reweighted, width and shape   {w_shape['slovenia'] * 100:6.2f}%"
              f"   ratio {rs:5.2f}x  {ci(np.exp(ls))}"
              f"   coverage {w_shape['coverage'] * 100:.1f}%")
        print(f"    share of the gap from shape   {share:6.2f}    "
              f"{ci(share_d)}   {reading(share)}")
        print(f"    six-band check                {share6:6.2f}    "
              f"{ci(share6_d)}   {reading(share6)}\n")
        summary.append({"method": label, "india": round(r_i, 4),
                         "slovenia": round(r_s, 4),
                         "slovenia_width": round(w_only["slovenia"], 4),
                         "slovenia_width_shape": round(w_shape["slovenia"], 4),
                         "slovenia_width_shape6": round(w_shape6["slovenia"], 4),
                         "coverage": round(w_shape["coverage"], 4),
                         "ratio_width": round(rw, 3),
                         "ratio_width_lo": round(float(np.nanpercentile(
                             np.exp(lw), 2.5)), 3),
                         "ratio_width_hi": round(float(np.nanpercentile(
                             np.exp(lw), 97.5)), 3),
                         "ratio_width_shape": round(rs, 3),
                         "ratio_width_shape_lo": round(float(np.nanpercentile(
                             np.exp(ls), 2.5)), 3),
                         "ratio_width_shape_hi": round(float(np.nanpercentile(
                             np.exp(ls), 97.5)), 3),
                         "share_from_shape": round(share, 3),
                         "share_lo": round(np.nanpercentile(share_d, 2.5), 3),
                         "share_hi": round(np.nanpercentile(share_d, 97.5), 3),
                         "share_six_band": round(share6, 3)})

    print(RULE)
    print("WITHIN EACH WIDTH BAND, SLOVENIA REWEIGHTED TO INDIA'S ELONGATIONS")
    print(RULE)
    bands = []
    for m, (label, _) in METHODS.items():
        bands += band_table(data[m]["india"], data[m]["slovenia"], label,
                            args.boots, rng)

    out = PROJECT / "results"
    pd.DataFrame(summary).to_csv(out / "shape_test.csv", index=False)
    pd.DataFrame(bands).to_csv(out / "shape_test_bands.csv", index=False)
    print(f"\n  wrote results\\shape_test.csv and results\\shape_test_bands.csv")
    print(RULE)


if __name__ == "__main__":
    main()
