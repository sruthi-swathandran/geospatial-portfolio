"""
RS-01 / step 6 — why does the ceiling sit at IoU ~0.70, and what is the bright water?

The sweep put the best single VH threshold at about 0.70 IoU on test, and the
class distributions say why: 25% of hand-labelled water pixels are brighter than
-18.7 dB, which is inside the land distribution. No threshold can recover those.
So the useful question is no longer "which threshold" but "what ARE those bright
water pixels", because the answer decides what to build next.

Three hypotheses, and this script tests each against the data rather than
asserting the fashionable one:

  H1  MIXED PIXELS AT THE EDGE. A 10 m pixel straddling a flood margin is part
      water, part land, and lands between the two modes. Test: split water into
      edge and interior by eroding the label mask. If bright water is mostly
      edge, the ceiling is a resolution limit and the fix is sub-pixel or
      higher-resolution data — not a better threshold.

  H2  FLOODED VEGETATION. Water under a canopy produces double-bounce off
      trunks and stems and comes back BRIGHT, not dark — the well-known blind
      spot of SAR flood mapping. Test: compute NDVI from the paired Sentinel-2
      chip and compare it between dark water and bright water. If bright water
      is vegetated, the fix is a different feature (VV/VH ratio, change against
      a pre-event reference), not a better threshold.

  H3  ROUGHENED OPEN WATER. Wind roughens the surface and raises backscatter.
      Test: bright water that is interior AND has low NDVI falls here — it is
      the residual once H1 and H2 are accounted for.

Whatever the split, the number that matters for the write-up is the same: how
much of the recall gap is physically unrecoverable from VH alone.

Outputs:
    results/ceiling_breakdown.csv
    results/figures/bright_water.png

Usage:
    python src\\ceiling_analysis.py
    python src\\ceiling_analysis.py --bright -18.0 --dark -22.0
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import rasterio                          # noqa: E402
from scipy.ndimage import binary_erosion  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, LABELS_DIR, RESULTS, EVENT_VH_THRESHOLD  # noqa: E402
from mask_chips import lee_filter, read, chip_ids, split_lookup    # noqa: E402

FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

# Sentinel-2 band order in Sen1Floods11's S2Hand chips is the Sentinel-2
# native order. For a 13-band stack that is B1,B2,B3,B4,B5,B6,B7,B8,B8A,B9,
# B10,B11,B12 -> red = index 3, NIR = index 7. The script prints the band
# count so you can confirm rather than assume; if it is not 13, check before
# trusting the NDVI numbers.
RED_IDX, NIR_IDX = 3, 7


def ndvi_from_s2(s2: np.ndarray) -> np.ndarray | None:
    if s2.shape[0] <= max(RED_IDX, NIR_IDX):
        return None
    red = s2[RED_IDX].astype("float64")
    nir = s2[NIR_IDX].astype("float64")
    denom = nir + red
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (nir - red) / denom
    return np.where(np.isfinite(out) & (denom != 0), out, np.nan)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bright", type=float, default=-18.0,
                    help="water at or above this VH is 'bright' (dB)")
    ap.add_argument("--dark", type=float, default=-22.0,
                    help="water at or below this VH is 'dark' (dB)")
    ap.add_argument("--erode", type=int, default=2,
                    help="erosion radius in pixels separating edge from interior")
    args = ap.parse_args()

    ids = chip_ids()
    splits = split_lookup()
    if not ids:
        raise SystemExit("No chips found.")

    vh_edge, vh_interior = [], []
    # Four buckets, not two. Edge pixels are mixed by definition — they contain
    # land — so they are BOTH brighter and greener than open water, and a plain
    # bright-vs-dark NDVI comparison cannot tell flooded vegetation apart from
    # ordinary edge mixing. Splitting interior from edge first is what makes the
    # vegetation question answerable.
    ndvi_buckets: dict[str, list[np.ndarray]] = {
        "interior_dark": [], "interior_bright": [],
        "edge_dark": [], "edge_bright": [],
    }
    rows = []
    band_counts = set()

    for chip_id in ids:
        s1 = read("S1Hand", chip_id).astype("float64")
        vh = lee_filter(s1[1])
        label = read("LabelHand", chip_id)[0]

        water = (label == 1) & np.isfinite(vh)
        if not water.any():
            continue

        interior = binary_erosion(water, np.ones((2 * args.erode + 1,) * 2))
        edge = water & ~interior

        vh_edge.append(vh[edge])
        vh_interior.append(vh[interior])

        try:
            s2 = read("S2Hand", chip_id)
            band_counts.add(int(s2.shape[0]))
            ndvi = ndvi_from_s2(s2)
        except Exception:                              # noqa: BLE001
            ndvi = None

        bright = water & (vh >= args.bright)
        dark = water & (vh <= args.dark)
        if ndvi is not None:
            ok = np.isfinite(ndvi)
            ndvi_buckets["interior_dark"].append(ndvi[interior & dark & ok])
            ndvi_buckets["interior_bright"].append(ndvi[interior & bright & ok])
            ndvi_buckets["edge_dark"].append(ndvi[edge & dark & ok])
            ndvi_buckets["edge_bright"].append(ndvi[edge & bright & ok])

        n_water = int(water.sum())
        n_bright = int(bright.sum())
        rows.append({
            "chip_id": chip_id,
            "split": splits.get(chip_id, "unknown"),
            "water_px": n_water,
            "bright_px": n_bright,
            "bright_frac": round(n_bright / n_water, 4),
            "edge_px": int(edge.sum()),
            "bright_and_edge_px": int((bright & edge).sum()),
            "bright_and_interior_px": int((bright & interior).sum()),
            "median_vh_water": round(float(np.median(vh[water])), 2),
        })

    vh_edge = np.concatenate(vh_edge)
    vh_interior = np.concatenate(vh_interior)
    all_water = np.concatenate([vh_edge, vh_interior])

    tot_bright = sum(r["bright_px"] for r in rows)
    tot_water = sum(r["water_px"] for r in rows)
    b_edge = sum(r["bright_and_edge_px"] for r in rows)
    b_int = sum(r["bright_and_interior_px"] for r in rows)

    print(f"{len(rows)} chips containing water; S2 band counts seen: "
          f"{sorted(band_counts) or 'none read'}")

    print("\nHOW MUCH WATER IS BRIGHT")
    print("------------------------")
    print(f"  water pixels                     {tot_water:>12,}")
    print(f"  brighter than {args.bright:>6.1f} dB          {tot_bright:>12,}"
          f"  ({tot_bright/tot_water:.1%} of water)")
    for t in (EVENT_VH_THRESHOLD, -20.75, -18.98):
        missed = int(np.sum(all_water > t))
        print(f"  missed by a {t:>6.2f} dB threshold  {missed:>12,}"
              f"  ({missed/tot_water:.1%}) -> recall ceiling {1-missed/tot_water:.3f}")

    print("\nH1 — EDGE OR INTERIOR?")
    print("----------------------")
    print(f"  edge water pixels     {vh_edge.size:>12,}  median VH "
          f"{np.median(vh_edge):6.2f} dB")
    print(f"  interior water pixels {vh_interior.size:>12,}  median VH "
          f"{np.median(vh_interior):6.2f} dB")
    if tot_bright:
        print(f"  of the bright water:  {b_edge/tot_bright:.1%} is edge, "
              f"{b_int/tot_bright:.1%} is interior")
        print("  -> mostly edge would mean a resolution limit; mostly interior "
              "means a\n     physical scattering effect, which is the more "
              "interesting case.")

    print(f"\n  water perimeter share: {vh_edge.size / all_water.size:.1%} of all "
          f"water pixels lie within {args.erode} px of land")
    print("  -> a compact lake would be a few percent. A large share means the "
          "flood is\n     thin and fragmented: channels, field margins, "
          "sheet water between bunds.")

    print("\nH2 — IS BRIGHT WATER VEGETATED, OR JUST MIXED?")
    print("---------------------------------------------")
    pooled = {k: (np.concatenate(v) if any(a.size for a in v) else np.array([]))
              for k, v in ndvi_buckets.items()}
    if any(a.size for a in pooled.values()):
        for name in ("interior_dark", "interior_bright", "edge_dark", "edge_bright"):
            a = pooled[name]
            if a.size:
                print(f"  NDVI {name:<16} n={a.size:>10,}  median "
                      f"{np.median(a):6.3f}  p75 {np.percentile(a, 75):6.3f}")
        i_d, i_b = pooled["interior_dark"], pooled["interior_bright"]
        if i_d.size and i_b.size:
            diff = float(np.median(i_b) - np.median(i_d))
            print(f"\n  INTERIOR-ONLY difference (the test that counts): {diff:+.3f}")
            print("  Edge pixels are part land by construction, so they are both "
                  "brighter and\n  greener regardless of vegetation — comparing "
                  "bright vs dark across all water\n  cannot separate the two "
                  "explanations. Comparing them WITHIN the interior can:\n"
                  "  a clear positive difference is flooded vegetation; near "
                  "zero is roughening.")
    else:
        print("  no usable S2 pixels — check the band indices at the top of this file")

    with open(RESULTS / "ceiling_breakdown.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ------------------------------------------------------------- figure
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    bins = np.linspace(-35, -2, 140)

    axes[0].hist(vh_interior, bins=bins, density=True, alpha=0.6,
                 label=f"interior water (n={vh_interior.size:,})", color="#2b6f8f")
    axes[0].hist(vh_edge, bins=bins, density=True, alpha=0.6,
                 label=f"edge water (n={vh_edge.size:,})", color="#c08a3e")
    axes[0].axvline(EVENT_VH_THRESHOLD, color="black", linewidth=1.3,
                    label="published -21.56")
    axes[0].axvline(args.bright, color="black", linestyle=":", linewidth=1.3,
                    label=f"'bright' cutoff {args.bright}")
    axes[0].set_xlabel("VH (dB)"); axes[0].set_ylabel("density")
    axes[0].set_title("Water pixels: edge vs interior")
    axes[0].legend(fontsize=8)

    order = ["interior_dark", "interior_bright", "edge_dark", "edge_bright"]
    data = [pooled[k] for k in order if pooled[k].size]
    labels = [k.replace("_", "\n") for k in order if pooled[k].size]
    if data:
        # matplotlib renamed this parameter in 3.9 and drops the old name in
        # 3.11 — you are on 3.11.1, so the new spelling comes first.
        try:
            axes[1].boxplot(data, tick_labels=labels, showfliers=False)
        except TypeError:
            axes[1].boxplot(data, labels=labels, showfliers=False)
        axes[1].axhline(0, color="black", linewidth=0.8, alpha=0.5)
        axes[1].set_ylabel("NDVI (from paired Sentinel-2)")
        axes[1].set_title("Vegetated, or just mixed?\ncompare the two interior boxes")
        axes[1].grid(alpha=0.25, axis="y")
    else:
        axes[1].text(0.5, 0.5, "no S2 NDVI available", ha="center", va="center")
        axes[1].axis("off")

    fig.suptitle(f"{EVENT} — what limits recall")
    fig.tight_layout()
    fig.savefig(FIGURES / "bright_water.png", dpi=130)
    print("\nwrote ceiling_breakdown.csv, figures/bright_water.png")


if __name__ == "__main__":
    main()
