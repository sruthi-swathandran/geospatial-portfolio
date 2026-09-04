"""
RS-01 / step 7b — why does our RTC read differ from the dataset's chip?

The check returned correlation 0.68 and a +3.7 dB bias. Neither number is fatal
on its own, but they mean different things depending on their cause, and the
cause decides what we are allowed to do next. Three candidates:

  A. RADIOMETRY. Planetary Computer serves terrain-corrected gamma0; Sen1Floods11
     built its chips from GEE's S1_GRD, which is sigma0 with its own border- and
     thermal-noise removal. Different products, so a systematic offset is
     expected. gamma0 = sigma0 / cos(incidence) accounts for roughly 0.6-1.5 dB,
     not 3.7, so noise-floor treatment is the likelier bulk of it.
     Signature: bias roughly constant across the image, and LARGER in dark
     pixels, because VH over water sits near the noise floor where the two
     chains disagree most.
     Consequence: harmless for change detection (RTC minus RTC cancels any
     product-level offset), fatal for carrying the -21.56 dB threshold across.

  B. MISALIGNMENT. A half- or whole-pixel offset would depress correlation while
     leaving the medians roughly intact.
     Signature: correlation improves measurably when one array is shifted by a
     pixel. This test tries all nine shifts in a 3x3 neighbourhood.
     Consequence: fatal for validating against the hand labels. Must be fixed.

  C. TERRAIN. Different DEMs and terrain-flattening give different answers on
     slopes.
     Signature: the difference is spatially structured — patchy on hillsides,
     clean on the floodplain — rather than uniform.

Speckle alone caps how high the correlation can go: two independent processing
chains of the same acquisition are not expected to agree pixel-for-pixel. So
read the SHIFT test first. If no shift improves things, the grids are aligned
and 0.68 is just what two chains look like through speckle.

Figures are optional here — if matplotlib will not import on your machine, the
numbers still print.

Usage:
    python src\\compare_rtc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS, EVENT_VH_THRESHOLD   # noqa: E402
from chips import read                                        # noqa: E402

REF_DIR = DATA / "reference"


def load_pair(chip_id: str):
    with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC.tif") as src:
        ours = src.read().astype("float64")
    theirs = read("S1Hand", chip_id).astype("float64")
    label = read("LabelHand", chip_id)[0]
    return ours, theirs, label


def shifted_corr(a: np.ndarray, b: np.ndarray, dy: int, dx: int) -> float:
    """Correlation of a against b displaced by (dy, dx), on the overlap only."""
    if dy > 0:
        a1, b1 = a[dy:, :], b[:-dy, :]
    elif dy < 0:
        a1, b1 = a[:dy, :], b[-dy:, :]
    else:
        a1, b1 = a, b
    if dx > 0:
        a1, b1 = a1[:, dx:], b1[:, :-dx]
    elif dx < 0:
        a1, b1 = a1[:, :dx], b1[:, -dx:]
    m = np.isfinite(a1) & np.isfinite(b1)
    if m.sum() < 1000:
        return float("nan")
    return float(np.corrcoef(a1[m], b1[m])[0, 1])


def main() -> None:
    chips = sorted(p.name.split("_")[1]
                   for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC.tif"))
    if not chips:
        raise SystemExit("No fetched chips in data/reference — run fetch_reference.py")

    print(f"{len(chips)} fetched chip(s)\n")

    all_ours, all_theirs, all_label = [], [], []
    print("B. SHIFT TEST — does a pixel offset improve agreement?")
    print("-----------------------------------------------------")
    for chip_id in chips:
        ours, theirs, label = load_pair(chip_id)
        o, t = ours[1], theirs[1]                       # VH
        grid = {(dy, dx): shifted_corr(o, t, dy, dx)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
        best = max(grid, key=lambda k: (grid[k] if np.isfinite(grid[k]) else -9))
        print(f"  chip {chip_id}: corr at (0,0) = {grid[(0, 0)]:.3f}   "
              f"best shift {best} = {grid[best]:.3f}   "
              f"gain {grid[best] - grid[(0, 0)]:+.3f}")
        m = np.isfinite(o) & np.isfinite(t)
        all_ours.append(o[m]); all_theirs.append(t[m]); all_label.append(label[m])

    print("\n  A gain under ~0.02 means the grids are aligned and the shift is "
          "noise.\n  A gain of 0.05+ at a consistent non-zero shift means real "
          "misalignment.")

    ours = np.concatenate(all_ours)
    theirs = np.concatenate(all_theirs)
    label = np.concatenate(all_label)
    diff = ours - theirs

    print("\nA. RADIOMETRY — is the offset level-dependent?")
    print("---------------------------------------------")
    print(f"  overall bias (ours - theirs): {np.median(diff):+.2f} dB   "
          f"sd {np.std(diff):.2f}")
    edges = np.percentile(theirs, np.arange(0, 101, 10))
    print(f"  {'their VH decile':<22}{'their median':>14}{'bias':>10}{'n':>12}")
    for i in range(10):
        m = (theirs >= edges[i]) & (theirs < edges[i + 1])
        if m.sum():
            print(f"  {f'{edges[i]:.1f} .. {edges[i+1]:.1f} dB':<22}"
                  f"{np.median(theirs[m]):>14.2f}{np.median(diff[m]):>10.2f}"
                  f"{m.sum():>12,}")
    print("  Bias growing towards the DARK end is the noise-floor signature: the"
          "\n  two chains disagree most where VH is weakest, which is over water.")

    print("\nBIAS BY CLASS")
    print("-------------")
    for name, sel in (("water", label == 1), ("land", label == 0)):
        if sel.sum():
            print(f"  {name:<6} n={sel.sum():>10,}  "
                  f"theirs median {np.median(theirs[sel]):7.2f}  "
                  f"ours median {np.median(ours[sel]):7.2f}  "
                  f"bias {np.median(diff[sel]):+.2f} dB")

    print("\nWHAT THIS MEANS FOR THE THRESHOLD")
    print("---------------------------------")
    w, l = label == 1, label == 0
    if w.sum() and l.sum():
        # where would the equivalent boundary sit in OUR radiometry?
        shift_water = float(np.median(ours[w]) - np.median(theirs[w]))
        print(f"  published threshold (their radiometry): "
              f"{EVENT_VH_THRESHOLD:+.2f} dB")
        print(f"  same threshold shifted by the water-class bias: "
              f"{EVENT_VH_THRESHOLD + shift_water:+.2f} dB")
        print("  Do NOT reuse -21.56 dB on RTC data. Either re-estimate the "
              "threshold in\n  RTC space, or — better — use RTC only for CHANGE "
              "(flood minus reference),\n  where any product-level offset "
              "cancels out entirely.")

    # ----------------------------------------------------------------- figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:                             # noqa: BLE001
        print(f"\n(skipping figures: matplotlib unavailable — {exc})")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5))
    sub = slice(None, None, max(1, ours.size // 200_000))
    axes[0].hexbin(theirs[sub], ours[sub], gridsize=90, bins="log", cmap="Blues")
    lim = [-32, -2]
    axes[0].plot(lim, lim, color="black", linewidth=1, label="1:1")
    axes[0].set_xlim(lim); axes[0].set_ylim(lim)
    axes[0].set_xlabel("Sen1Floods11 S1Hand VH (dB)")
    axes[0].set_ylabel("Planetary Computer RTC VH (dB)")
    axes[0].set_title("Same acquisition, two processing chains")
    axes[0].legend(fontsize=9)

    centres = [(edges[i] + edges[i + 1]) / 2 for i in range(10)]
    biases = [np.median(diff[(theirs >= edges[i]) & (theirs < edges[i + 1])])
              for i in range(10)]
    axes[1].plot(centres, biases, marker="o", color="#8f4b2b")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xlabel("their VH (dB)")
    axes[1].set_ylabel("bias, ours - theirs (dB)")
    axes[1].set_title("Is the offset constant, or worse in the dark?")
    axes[1].grid(alpha=0.25)

    fig.tight_layout()
    out = RESULTS / "figures" / "rtc_vs_s1hand.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"\nwrote figures/{out.name}")


if __name__ == "__main__":
    main()
