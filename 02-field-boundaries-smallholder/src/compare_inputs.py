"""
RS-02. Why the same checkpoint predicts 92.8% field in India and nothing in
Slovenia.

The facts to explain:

    India     399 test chips, median 92.8% of the chip predicted field,
              against 1.03% labelled (presence-only, so the rest is unknown)
    Slovenia  228 test chips, median 2 pixels of 65,536 predicted field,
              111 chips predicting nothing at all, against 12.18% labelled
              and verified

A model that had never seen Slovenia would be mediocre there. Silence is a
different failure and usually means the inputs are outside the range the
network was trained on. FTW's preprocessing is one line, image / 3000, applied
identically to both, so if the two countries' reflectances sit at different
scales then one of them is being fed something it never saw.

This measures, for both countries, with no theorising in between:

    A  raw band values per country, per band, as percentiles
    B  the same after / 3000, which is what the network actually receives
    C  predicted field fraction against labelled field fraction, per chip
    D  a figure: imagery, label and prediction side by side for both

It reads both countries directly rather than through FTW_COUNTRY, since the
whole point is the comparison.

    python src\\compare_inputs.py
    python src\\compare_inputs.py --countries india,slovenia --chips 40
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                               # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
RULE = "=" * 78

C3_INTERIOR, C3_BOUNDARY, C3_UNLABELLED = 1, 2, 3


class Country:
    def __init__(self, name):
        self.name = name
        self.data = PROJECT / "data" / "ftw" / name
        self.results = PROJECT / "results" / name
        self.pred = self.results / "pred_2class"
        self.img_a = self.data / "s2_images" / "window_a"
        self.img_b = self.data / "s2_images" / "window_b"
        self.c3 = self.data / "label_masks" / "semantic_3class"

    def predicted_chips(self, n=None):
        if not self.pred.exists():
            return []
        names = [p.name for p in sorted(self.pred.glob("*.tif"))]
        return names[:n] if n else names


def band_stats(c, names, limit=40):
    """Percentiles per band, over both windows, on the test chips only."""
    per_band = {}
    for name in names[:limit]:
        for tag, folder in (("b", c.img_b), ("a", c.img_a)):
            p = folder / name
            if not p.exists():
                continue
            with rasterio.open(p) as s:
                arr = s.read().astype(np.float32)
            for i in range(arr.shape[0]):
                per_band.setdefault((tag, i + 1), []).append(
                    np.percentile(arr[i], [1, 25, 50, 75, 99]))
    return {k: np.mean(np.stack(v), axis=0) for k, v in per_band.items() if v}


def section_a(cs, names_by, limit):
    print(RULE)
    print("A. RAW BAND VALUES, TEST CHIPS")
    print(RULE)
    stats = {}
    for c in cs:
        stats[c.name] = band_stats(c, names_by[c.name], limit)
        print(f"\n  {c.name}   ({min(limit, len(names_by[c.name]))} chips)")
        print(f"    {'window/band':<14}{'p1':>9}{'p25':>9}{'p50':>9}"
              f"{'p75':>9}{'p99':>9}")
        for (tag, b), v in sorted(stats[c.name].items()):
            print(f"    window_{tag} band {b:<3}" + "".join(
                f"{x:>9,.0f}" for x in v))
    return stats


def section_b(stats):
    print("\n" + RULE)
    print("B. WHAT THE NETWORK RECEIVES, AFTER / 3000")
    print(RULE)
    print(f"  {'country':<12}{'median input':>15}{'p99 input':>13}"
          f"{'p1 input':>12}")
    for name, st in stats.items():
        med = np.mean([v[2] for v in st.values()]) / 3000
        hi = np.mean([v[4] for v in st.values()]) / 3000
        lo = np.mean([v[0] for v in st.values()]) / 3000
        print(f"  {name:<12}{med:>15.3f}{hi:>13.3f}{lo:>12.3f}")
    vals = [np.mean([v[2] for v in st.values()]) for st in stats.values()]
    if len(vals) == 2 and min(vals) > 0:
        ratio = max(vals) / min(vals)
        print(f"\n  median raw values differ by {ratio:.2f}x between the two")
        if ratio > 1.6:
            print("  That is enough to matter. The same division by 3000 puts")
            print("  the two countries in different parts of the input range,")
            print("  and the model only ever saw one of them.")
        else:
            print("  Similar scales, so input range is NOT the explanation and")
            print("  the cause is elsewhere. Read section C and the figure.")


def section_c(cs, names_by, limit=None):
    print("\n" + RULE)
    print("C. PREDICTED AGAINST LABELLED, PER CHIP")
    print(RULE)
    rows = []
    for c in cs:
        names = names_by[c.name]
        if limit:
            names = names[:limit]
        pred_f, true_f, unlab_f = [], [], []
        for name in names:
            pp, cp = c.pred / name, c.c3 / name
            if not (pp.exists() and cp.exists()):
                continue
            with rasterio.open(pp) as s:
                pr = s.read(1)
            with rasterio.open(cp) as s:
                c3 = s.read(1)
            n = pr.size
            pred_f.append(float((pr == 1).sum()) / n)
            true_f.append(float(((c3 == C3_INTERIOR) |
                                 (c3 == C3_BOUNDARY)).sum()) / n)
            unlab_f.append(float((c3 == C3_UNLABELLED).sum()) / n)
        if not pred_f:
            print(f"  {c.name}: no predictions found, run run_inference.py")
            continue
        pf, tf, uf = map(np.array, (pred_f, true_f, unlab_f))
        print(f"\n  {c.name}   ({len(pf):,} chips)")
        print(f"    predicted field   median {np.median(pf) * 100:6.2f}%   "
              f"mean {pf.mean() * 100:6.2f}%   "
              f"chips at zero {(pf == 0).sum():,}")
        print(f"    labelled parcel   median {np.median(tf) * 100:6.2f}%   "
              f"mean {tf.mean() * 100:6.2f}%")
        print(f"    unlabelled        median {np.median(uf) * 100:6.2f}%")
        if uf.mean() < 0.5 and len(pf) > 2:
            r = float(np.corrcoef(pf, tf)[0, 1])
            print(f"    correlation between predicted and labelled: {r:+.3f}")
            print("    (meaningful only where labels are complete)")
        rows.append({"country": c.name, "chips": len(pf),
                     "pred_field_median": round(float(np.median(pf)), 5),
                     "labelled_median": round(float(np.median(tf)), 5),
                     "unlabelled_median": round(float(np.median(uf)), 5),
                     "chips_predicting_zero": int((pf == 0).sum())})
    return rows


def stretch(a, lo=2, hi=98):
    out = np.empty(a.shape, np.float32)
    for i in range(a.shape[0]):
        p1, p2 = np.percentile(a[i], lo), np.percentile(a[i], hi)
        out[i] = 0.0 if p2 <= p1 else np.clip((a[i] - p1) / (p2 - p1), 0, 1)
    return np.transpose(out, (1, 2, 0))


def section_d(cs, names_by, per_country=3, bands=(4, 3, 2)):
    print("\n" + RULE)
    print("D. LOOKING AT IT")
    print(RULE)
    picks = []
    for c in cs:
        for name in names_by[c.name][:per_country]:
            picks.append((c, name))
    if not picks:
        print("  nothing to draw")
        return

    fig, axes = plt.subplots(len(picks), 3,
                             figsize=(9.6, 3.2 * len(picks)))
    if len(picks) == 1:
        axes = axes.reshape(1, 3)

    for r, (c, name) in enumerate(picks):
        with rasterio.open(c.img_a / name) as s:
            arr = s.read(list(bands)).astype(np.float32)
        with rasterio.open(c.c3 / name) as s:
            c3 = s.read(1)
        with rasterio.open(c.pred / name) as s:
            pr = s.read(1)

        axes[r, 0].imshow(stretch(arr))
        axes[r, 0].set_ylabel(f"{c.name}\n{name}", fontsize=8,
                              linespacing=1.4)

        lab = np.zeros(c3.shape + (3,), np.float32)
        lab[:] = (0.88, 0.88, 0.88)                     # unlabelled or bg
        lab[c3 == C3_BOUNDARY] = (0.95, 0.72, 0.25)
        lab[c3 == C3_INTERIOR] = (0.15, 0.42, 0.23)
        axes[r, 1].imshow(lab)

        pm = np.zeros(pr.shape + (3,), np.float32)
        pm[:] = (0.88, 0.88, 0.88)
        pm[pr == 1] = (0.20, 0.35, 0.70)
        axes[r, 2].imshow(pm)

        for k in range(3):
            axes[r, k].set_xticks([])
            axes[r, k].set_yticks([])

    for k, t in enumerate(["window_a, false colour", "label",
                           "prediction"]):
        axes[0, k].set_title(t, fontsize=9)

    fig.suptitle("Same checkpoint, two countries", fontsize=12, y=0.995)
    fig.text(0.5, 0.008,
             "Green is labelled parcel interior, amber its boundary ring, "
             "grey is background or unlabelled. Blue is predicted field.",
             ha="center", fontsize=8)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.955, bottom=0.035,
                        wspace=0.04, hspace=0.06)

    out = PROJECT / "figures" / "input_comparison.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  wrote {out.relative_to(PROJECT)}")
    print("  Send me this figure. If Slovenia's imagery looks normal and the")
    print("  prediction is simply empty, the cause is the input range or the")
    print("  season ordering rather than anything about the fields.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="india,slovenia")
    ap.add_argument("--chips", type=int, default=40)
    args = ap.parse_args()

    cs = [Country(n.strip()) for n in args.countries.split(",") if n.strip()]
    names_by = {}
    for c in cs:
        names_by[c.name] = c.predicted_chips()
        print(f"[{c.name}] {len(names_by[c.name]):,} predicted chips")
    cs = [c for c in cs if names_by[c.name]]
    if not cs:
        sys.exit("No predictions found. Run run_inference.py first.")
    print()

    stats = section_a(cs, names_by, args.chips)
    section_b(stats)
    rows = section_c(cs, names_by)
    section_d(cs, names_by)

    if rows:
        out = PROJECT / "results" / "country_comparison.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n  wrote {out.relative_to(PROJECT)}")

    print("\n" + RULE)
    print("Section B decides it. If the two countries' raw values differ by")
    print("much, one of them is being fed a range the model never trained on,")
    print("and no score from this run means anything until that is fixed.")
    print(RULE)


if __name__ == "__main__":
    main()
