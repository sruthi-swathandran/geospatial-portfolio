"""
RS-01 / step 7e — is the low correlation a data problem or a metric problem?

Coverage is ruled out: the disagreeing chips have zero no-data. So either the
imagery really is wrong on those chips, or pixel correlation is the wrong way to
compare two SAR images. There is a strong reason to suspect the latter.

Correlation measures shared VARIANCE. Sentinel-1 VH over flat, uniform terrain
is nearly constant plus heavy multiplicative speckle. Two independent processing
chains of the same acquisition produce independent speckle realisations, so over
a featureless chip almost all the variance is noise and the correlation collapses
towards zero — even when both images are perfectly correct and perfectly aligned.
On a chip containing a river, a treeline, a town, real structure dominates and
correlation is high.

If that is what is happening, the prediction is specific: raw correlation should
track how much spatial STRUCTURE the chip contains, and it should recover once
speckle is averaged away. This tests exactly that, three ways:

  sd_theirs        how much structure the chip has at all
  corr_raw         pixel-for-pixel, speckle included
  corr_block5      after 5x5 mean filtering, which suppresses speckle by ~5x
                   while leaving real structure intact
  corr_block_best  the same, allowing up to a +/-2 pixel shift, so registration
                   and speckle are separated from each other

Read it like this: corr_block5 high everywhere means the data is fine and
correlation was simply the wrong instrument for low-contrast chips. corr_block5
still near zero on the same chips means something is genuinely wrong with them.

Usage:
    python src\\agreement_check.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import uniform_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import EVENT, DATA, RESULTS         # noqa: E402
from chips import read                          # noqa: E402

REF_DIR = DATA / "reference"


def block_mean(a: np.ndarray, size: int = 5) -> np.ndarray:
    """Mean filter that tolerates NaN, keeping NaN where the input had it."""
    valid = np.isfinite(a)
    if not valid.any():
        return a
    filled = np.where(valid, a, np.nanmean(a[valid]))
    out = uniform_filter(filled, size)
    return np.where(valid, out, np.nan)


def corr(a: np.ndarray, b: np.ndarray, dy: int = 0, dx: int = 0) -> float:
    a1, b1 = (a[dy:, :], b[:-dy, :]) if dy > 0 else \
             (a[:dy, :], b[-dy:, :]) if dy < 0 else (a, b)
    a1, b1 = (a1[:, dx:], b1[:, :-dx]) if dx > 0 else \
             (a1[:, :dx], b1[:, -dx:]) if dx < 0 else (a1, b1)
    m = np.isfinite(a1) & np.isfinite(b1)
    if m.sum() < 1000:
        return float("nan")
    if np.std(a1[m]) == 0 or np.std(b1[m]) == 0:
        return float("nan")
    return float(np.corrcoef(a1[m], b1[m])[0, 1])


def main() -> None:
    chips = sorted(p.name.split("_")[1]
                   for p in REF_DIR.glob(f"{EVENT}_*_FLOODRTC.tif"))
    if not chips:
        raise SystemExit("Nothing in data/reference — run fetch_reference.py")

    rows = []
    for chip_id in chips:
        with rasterio.open(REF_DIR / f"{EVENT}_{chip_id}_FLOODRTC.tif") as src:
            ours = src.read()[1].astype("float64")
        theirs = read("S1Hand", chip_id).astype("float64")[1]
        label = read("LabelHand", chip_id)[0]

        ok = np.isfinite(theirs)
        sd_theirs = float(np.std(theirs[ok])) if ok.sum() > 1000 else float("nan")
        sd_ours = float(np.std(ours[np.isfinite(ours)])) if np.isfinite(ours).any() \
            else float("nan")

        ob, tb = block_mean(ours), block_mean(theirs)
        c_raw = corr(ours, theirs)
        c_blk = corr(ob, tb)
        best = max(((dy, dx) for dy in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)),
                   key=lambda k: (lambda v: v if np.isfinite(v) else -9)(corr(ob, tb, *k)))
        c_best = corr(ob, tb, *best)

        valid = label != -1
        rows.append({
            "chip_id": chip_id,
            "sd_theirs": round(sd_theirs, 2),
            "sd_ours": round(sd_ours, 2),
            "corr_raw": round(c_raw, 4),
            "corr_block5": round(c_blk, 4),
            "corr_block_best": round(c_best, 4),
            "best_dy": best[0], "best_dx": best[1],
            "water_frac": round(float(np.mean(label[valid] == 1)), 4)
            if valid.any() else 0.0,
        })

    with open(RESULTS / "agreement_check.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    raw = np.array([r["corr_raw"] for r in rows])
    blk = np.array([r["corr_block5"] for r in rows])
    best = np.array([r["corr_block_best"] for r in rows])
    sd = np.array([r["sd_theirs"] for r in rows])
    ok = np.isfinite(raw) & np.isfinite(blk) & np.isfinite(sd)

    print(f"{len(rows)} chips\n")
    print("AGREEMENT, THREE WAYS")
    print("---------------------")
    for name, arr in (("corr_raw", raw), ("corr_block5", blk),
                      ("corr_block_best", best)):
        a = arr[np.isfinite(arr)]
        print(f"  {name:<18} median {np.median(a):.3f}   "
              f"p10 {np.percentile(a, 10):.3f}   min {a.min():.3f}")

    print("\nDOES RAW CORRELATION TRACK HOW MUCH STRUCTURE THE CHIP HAS?")
    print("----------------------------------------------------------")
    if ok.sum() > 3:
        print(f"  corr(corr_raw, sd_theirs)    = {np.corrcoef(raw[ok], sd[ok])[0,1]:+.3f}")
        print(f"  corr(corr_block5, sd_theirs) = {np.corrcoef(blk[ok], sd[ok])[0,1]:+.3f}")
        print("  A strong positive on the first and a weak one on the second is the"
              "\n  speckle explanation: agreement looked bad only where there was "
              "little\n  structure for the two images to agree about.")

    weak = [r for r in rows if np.isfinite(r["corr_raw"]) and r["corr_raw"] < 0.30]
    print(f"\nTHE {len(weak)} CHIPS THAT LOOKED BAD RAW")
    print("-" * 34)
    if weak:
        wr = np.array([r["corr_raw"] for r in weak])
        wb = np.array([r["corr_block5"] for r in weak])
        wbest = np.array([r["corr_block_best"] for r in weak])
        wsd = np.array([r["sd_theirs"] for r in weak])
        print(f"  their raw correlation   median {np.median(wr):.3f}")
        print(f"  after 5x5 averaging     median {np.median(wb):.3f}")
        print(f"  after averaging + shift median {np.median(wbest):.3f}")
        print(f"  their sd (structure)    median {np.median(wsd):.2f} dB   "
              f"vs {np.median(sd[np.isfinite(sd)]):.2f} dB across all chips")
        print(f"\n  {'chip':<10}{'sd':>7}{'raw':>8}{'block5':>9}{'+shift':>9}"
              f"{'shift':>9}{'water%':>9}")
        for r in sorted(weak, key=lambda x: x["corr_raw"])[:12]:
            shift = f"({r['best_dy']:+d},{r['best_dx']:+d})"
            print(f"  {r['chip_id']:<10}{r['sd_theirs']:>7.2f}{r['corr_raw']:>8.3f}"
                  f"{r['corr_block5']:>9.3f}{r['corr_block_best']:>9.3f}"
                  f"{shift:>9}{r['water_frac']*100:>9.1f}")

    shifts = [(r["best_dy"], r["best_dx"]) for r in rows]
    vals, counts = np.unique(np.array(shifts), axis=0, return_counts=True)
    print("\nBEST SHIFT AFTER SPECKLE SUPPRESSION")
    print("------------------------------------")
    for v, c in sorted(zip(vals.tolist(), counts.tolist()), key=lambda x: -x[1])[:6]:
        print(f"  ({v[0]:+d},{v[1]:+d}): {c} chips")
    print("  One dominant shift = a systematic offset worth correcting once."
          "\n  A spread = terrain, correctable per chip.")

    print("\nwrote agreement_check.csv")


if __name__ == "__main__":
    main()
