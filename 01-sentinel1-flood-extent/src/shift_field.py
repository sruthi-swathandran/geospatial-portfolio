"""
RS-01 / step 8b — is the shift field real, or is the search chasing noise?

Widening the search from +/-5 to +/-10 left the core untouched (dx median -2
either way, about 39 chips between 0 and -4) and moved only a tail: four chips
jumped to -10. Two readings, and they call for opposite actions:

  REAL DISPLACEMENT. Those chips genuinely sit 10+ pixels off, in which case
  widening further is right and the offset has a physical cause worth naming.

  NO PEAK TO FIND. On a chip with little structure the correlation surface is
  almost flat, so the maximum lands wherever noise puts it — often at the edge,
  because the overlap shrinks with displacement and small overlaps are noisier.
  Widening then produces larger and more confident nonsense.

The two are distinguishable. If the boundary chips also have LOW post-alignment
correlation, the search found no peak and the honest move is to exclude them,
not to widen. If they have HIGH correlation, the displacement is real.

The script also tests the range-direction hypothesis. SAR geolocation error
caused by DEM disagreement acts along slant range, which for this descending
pass runs roughly east-west — so it should appear in dx and not dy, and it
should vary with terrain rather than randomly across the scene. dy sd is 0.86
against dx sd 4.09, which is consistent. Plotting dx against chip position tests
whether the variation is spatially organised (terrain or frame geometry) or
scattered (noise).

Outputs:
    results/figures/shift_field.png
    results/shift_field.csv

Usage:
    python src\\shift_field.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RESULTS                       # noqa: E402

COREG = RESULTS / "coregistration.csv"
FOOTPRINTS = RESULTS / "label_chip_footprints.geojson"


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def centroids() -> dict[str, tuple[float, float]]:
    gj = json.loads(FOOTPRINTS.read_text())
    out = {}
    for feat in gj["features"]:
        coords = feat["geometry"]["coordinates"][0]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        out[str(feat["properties"]["chip_id"])] = (
            float(np.mean(xs)), float(np.mean(ys)))
    return out


def main() -> None:
    if not COREG.exists():
        raise SystemExit(f"{COREG} not found — run coregister.py first")

    rows = list(csv.DictReader(COREG.read_text().splitlines()))
    cent = centroids() if FOOTPRINTS.exists() else {}

    dx = np.array([fnum(r["dx"]) for r in rows])
    dy = np.array([fnum(r["dy"]) for r in rows])
    after = np.array([fnum(r["corr_after"]) for r in rows])
    edge = np.array([int(r.get("at_search_edge", 0) or 0) for r in rows]).astype(bool)
    lon = np.array([cent.get(r["chip_id"], (np.nan, np.nan))[0] for r in rows])
    lat = np.array([cent.get(r["chip_id"], (np.nan, np.nan))[1] for r in rows])

    print(f"{len(rows)} chips\n")

    print("1. ARE THE BOUNDARY CHIPS THE ONES WITH NO PEAK TO FIND?")
    print("--------------------------------------------------------")
    for name, sel in (("at the search boundary", edge), ("interior", ~edge)):
        if sel.sum():
            a = after[sel]
            a = a[np.isfinite(a)]
            print(f"  {name:<24} n={sel.sum():>3}   post-alignment corr: "
                  f"median {np.median(a):.3f}   min {a.min():.3f}   "
                  f"max {a.max():.3f}")
    if edge.any() and (~edge).any():
        gap = np.nanmedian(after[~edge]) - np.nanmedian(after[edge])
        print(f"\n  interior chips agree {gap:+.3f} better than boundary chips.")
        print("  A clear gap means the boundary results are noise, not "
              "displacement:\n  exclude those chips rather than widening the "
              "search again.")

    print("\n2. IS THE SHIFT SPATIALLY ORGANISED?")
    print("------------------------------------")
    ok = np.isfinite(dx) & np.isfinite(lon) & ~edge     # interior chips only
    if ok.sum() > 5:
        print(f"  (interior chips only, n={ok.sum()})")
        print(f"  corr(dx, longitude) = {np.corrcoef(dx[ok], lon[ok])[0,1]:+.3f}")
        print(f"  corr(dx, latitude)  = {np.corrcoef(dx[ok], lat[ok])[0,1]:+.3f}")
        print(f"  corr(dy, longitude) = {np.corrcoef(dy[ok], lon[ok])[0,1]:+.3f}")
        print(f"  corr(dy, latitude)  = {np.corrcoef(dy[ok], lat[ok])[0,1]:+.3f}")
        print("\n  A strong relationship with position means frame geometry or "
              "terrain —\n  something structured. Near zero everywhere means a "
              "constant offset plus\n  per-chip noise, and the constant is all "
              "you should correct for.")
        print(f"\n  interior dx: median {np.median(dx[ok]):+.1f}  "
              f"mean {dx[ok].mean():+.2f}  sd {dx[ok].std():.2f}")
        print(f"  interior dy: median {np.median(dy[ok]):+.1f}  "
              f"mean {dy[ok].mean():+.2f}  sd {dy[ok].std():.2f}")
        print(f"  -> a constant correction of ({np.median(dy[ok]):+.0f},"
              f"{np.median(dx[ok]):+.0f}) px = "
              f"({abs(np.median(dy[ok]))*10:.0f} m, "
              f"{abs(np.median(dx[ok]))*10:.0f} m)")

    with open(RESULTS / "shift_field.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chip_id", "lon", "lat", "dy", "dx", "corr_after", "at_edge"])
        for r, lo, la in zip(rows, lon, lat):
            w.writerow([r["chip_id"], lo, la, r["dy"], r["dx"],
                        r["corr_after"], r.get("at_search_edge", "")])

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                            # noqa: BLE001
        print(f"\n(figure skipped: {exc})")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5))
    good = np.isfinite(lon) & np.isfinite(dx)
    sc = axes[0].scatter(lon[good & ~edge], lat[good & ~edge],
                         c=dx[good & ~edge], cmap="RdBu", vmin=-6, vmax=6,
                         s=70, edgecolor="black", linewidth=0.4)
    if (good & edge).any():
        axes[0].scatter(lon[good & edge], lat[good & edge], marker="x",
                        c="black", s=70, label="hit search boundary")
        axes[0].legend(fontsize=8)
    fig.colorbar(sc, ax=axes[0], label="dx correction (px)")
    axes[0].set_xlabel("longitude"); axes[0].set_ylabel("latitude")
    axes[0].set_title("Is the offset organised in space?")

    ok2 = np.isfinite(after) & np.isfinite(dx)
    axes[1].scatter(np.abs(dx[ok2 & ~edge]), after[ok2 & ~edge], s=55,
                    color="#2b6f8f", edgecolor="black", linewidth=0.4,
                    label="interior")
    if (ok2 & edge).any():
        axes[1].scatter(np.abs(dx[ok2 & edge]), after[ok2 & edge], marker="x",
                        color="black", s=70, label="boundary")
    axes[1].set_xlabel("|dx| correction (px)")
    axes[1].set_ylabel("correlation after alignment")
    axes[1].set_title("Big corrections — real, or no peak to find?")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)

    fig.tight_layout()
    out = RESULTS / "figures" / "shift_field.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"\nwrote figures/{out.name} and shift_field.csv")


if __name__ == "__main__":
    main()
