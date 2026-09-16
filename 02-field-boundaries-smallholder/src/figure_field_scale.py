"""
RS-02 / step 4. Look at the parcels, at the resolution the sensor actually has.

Everything before this was summary statistics. "Median 0.24 ha" and "61% under
5 by 5 native pixels" are the right numbers and they still do not show anyone
what that looks like to Sentinel-2. This draws it.

  figures/field_scale.png
      Parcels at the 5th, 25th, 50th, 75th and 95th percentile of the measured
      size distribution, each shown three ways: on the 6.07 m grid FTW ships,
      area-averaged onto the 10 m grid the sensor samples, and as the label.
      Every panel covers the same 500 m of ground, so sizes compare by eye.

      The middle row is the honest one. The top row holds more pixels, and the
      extra pixels came from the interpolator that built the grid rather than
      from the satellite.

  figures/chip_sparsity.png
      Whole chips, 1.5 km across, with every labelled parcel outlined. Five
      parcels drawn per chip and 98.96% of the ground never looked at. The
      figure exists because that ratio is hard to believe as a percentage.

Outlines are the reconstructed parcel, interior plus its eroded boundary ring,
which is the real extent. The instance mask alone is about a third smaller.

Bands are taken as blue, green, red, near infrared, which is what the band
statistics suggest. The default rendering is 4, 3, 2, so healthy vegetation
comes out red. If it does not, the band order is wrong and --bands fixes it.

Reads results/field_sizes.csv, so run measure_fields.py first.

    python src\\figure_field_scale.py
    python src\\figure_field_scale.py --bands 3,2,1
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                               # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

WINDOW_M = 500.0

GREY = (0.90, 0.90, 0.90)
RING_C = (0.95, 0.72, 0.25)
OTHER_C = (0.72, 0.83, 0.72)
THIS_C = (0.15, 0.42, 0.23)


def coverage():
    """Class shares, read from results/ rather than written into the caption."""
    p = F.RESULTS / "label_coverage.csv"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    tot = sum(int(r["pixels"]) for r in rows)
    if not tot:
        return None
    return {
        "chips": len(rows),
        "interior": sum(int(r["interior_px"]) for r in rows) / tot,
        "ring": sum(int(r["boundary_px"]) for r in rows) / tot,
        "unlabelled": sum(int(r["unlabelled_px"]) for r in rows) / tot,
    }


def load_fields():
    p = F.RESULTS / "field_sizes.csv"
    if not p.exists():
        sys.exit(f"{p} not found. Run measure_fields.py first.")
    with open(p, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if "full_ha" not in rows[0]:
        sys.exit("field_sizes.csv has no full_ha column. Re-run "
                 "measure_fields.py, it was corrected.")
    for r in rows:
        for k in ("full_ha", "interior_ha", "full_native_px"):
            r[k] = float(r[k])
        for k in ("full_px", "interior_px", "parcel_id",
                  "row_min", "col_min", "bbox_h", "bbox_w"):
            r[k] = int(r[k])
    return rows


def pick(rows, quantiles):
    ha = np.array([r["full_ha"] for r in rows])
    out, used = [], set()
    for q in quantiles:
        target = float(np.percentile(ha, q))
        for i in np.argsort(np.abs(ha - target)):
            key = (rows[i]["chip"], rows[i]["parcel_id"])
            if key not in used:
                used.add(key)
                out.append((q, rows[i]))
                break
    return out


def stretch(a, lo=2, hi=98):
    a = a.astype(np.float32)
    out = np.empty(a.shape, np.float32)
    for i in range(a.shape[0]):
        b = a[i]
        p1, p2 = np.percentile(b, lo), np.percentile(b, hi)
        out[i] = 0.0 if p2 <= p1 else np.clip((b - p1) / (p2 - p1), 0, 1)
    return np.transpose(out, (1, 2, 0))


def to_native(rgb, px_m):
    from PIL import Image
    h, w, _ = rgb.shape
    tw = max(1, int(round(w * px_m / F.NATIVE_M)))
    th = max(1, int(round(h * px_m / F.NATIVE_M)))
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    back = im.resize((tw, th), Image.BOX).resize((w, h), Image.NEAREST)
    return np.asarray(back).astype(np.float32) / 255.0, (th, tw)


def crop_window(row, side, h, w):
    cy = row["row_min"] + row["bbox_h"] / 2
    cx = row["col_min"] + row["bbox_w"] / 2
    r0 = max(0, min(int(round(cy - side / 2)), h - side))
    c0 = max(0, min(int(round(cx - side / 2)), w - side))
    return Window(c0, r0, side, side)


def field_scale_figure(rows, bands, px_m):
    chosen = pick(rows, [5, 25, 50, 75, 95])
    side = int(round(WINDOW_M / px_m))

    n = len(chosen)
    fig, axes = plt.subplots(3, n, figsize=(2.55 * n, 8.8))
    native_shape = None

    for col, (q, r) in enumerate(chosen):
        img = F.IMG_A / r["chip"]
        if not img.exists():
            for k in range(3):
                axes[k, col].axis("off")
            continue
        with rasterio.open(F.INSTANCE / r["chip"]) as s:
            h, w = s.height, s.width
        win = crop_window(r, min(side, h, w), h, w)

        with rasterio.open(img) as s:
            arr = s.read(bands, window=win)
        inst, c2, c3, full = F.load_labels(r["chip"], window=win)

        rgb = stretch(arr)
        nat, native_shape = to_native(rgb, px_m)
        mask = (full == r["parcel_id"])

        axes[0, col].imshow(rgb)
        axes[1, col].imshow(nat)

        # Paint in order of specificity so nothing is overwritten: other
        # parcels, then this parcel's full extent in the ring colour, then its
        # interior on top. What stays amber is exactly the boundary FTW eroded
        # off and this project gave back.
        lab = np.zeros(inst.shape + (3,), np.float32)
        lab[:] = GREY
        lab[full > 0] = OTHER_C
        lab[mask] = RING_C
        lab[mask & (inst == r["parcel_id"])] = THIS_C
        axes[2, col].imshow(lab)

        for k in range(3):
            axes[k, col].contour(mask.astype(float), levels=[0.5],
                                 colors="white" if k < 2 else "black",
                                 linewidths=1.1)
            axes[k, col].set_xticks([])
            axes[k, col].set_yticks([])

        axes[0, col].set_title(
            f"p{q}\n{r['full_ha']:.3f} ha\n"
            f"{r['full_native_px']:.0f} native px",
            fontsize=9, linespacing=1.35)

    for k, text in enumerate([f"as shipped\n{px_m:.2f} m grid",
                              f"as sampled\n{F.NATIVE_M:.0f} m sensor",
                              "label"]):
        axes[k, 0].set_ylabel(text, fontsize=9, linespacing=1.35)

    fig.suptitle("What a smallholding looks like to Sentinel-2",
                 fontsize=13, y=0.985)
    fig.text(0.5, 0.947,
             f"Five parcels at the 5th to 95th percentile of the FTW "
             f"{F.COUNTRY.capitalize()} size distribution. Every panel covers "
             f"the same {WINDOW_M:.0f} m of ground.",
             ha="center", fontsize=9)

    note = (f"Top row is the {px_m:.2f} m grid FTW ships, 256 pixels over "
            f"1,536 m. Sentinel-2's finest bands sample at "
            f"{F.NATIVE_M:.0f} m, so the middle row, area-averaged onto the "
            f"sensor grid and shown as\nblocks, is what was observed. Detail "
            f"in the top row that is absent from the middle was produced by "
            f"the interpolator. Near infrared, red, green, so vegetation "
            f"reads red.\nIn the label row, dark green is the instance mask "
            f"FTW ships, amber is the boundary ring it erodes off, and the "
            f"two together are the parcel. Pale green is other parcels, grey "
            f"is unlabelled ground.")
    fig.text(0.5, 0.052, note, ha="center", fontsize=8, linespacing=1.6)
    fig.text(0.5, 0.012, F.SOURCE, ha="center", fontsize=7, color="0.35")

    fig.subplots_adjust(left=0.075, right=0.985, top=0.852, bottom=0.145,
                        wspace=0.06, hspace=0.06)
    F.FIGURES.mkdir(parents=True, exist_ok=True)
    out = F.FIGURES / "field_scale.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"  wrote {out.relative_to(F.PROJECT)}")
    if native_shape:
        print(f"  each panel is {side} grid px, "
              f"{native_shape[0]} x {native_shape[1]} native Sentinel-2 px")
    return chosen


def sparsity_figure(rows, bands, px_m, n_chips=3):
    by_chip = {}
    for r in rows:
        by_chip.setdefault(r["chip"], []).append(r)
    picks = [c for c, v in sorted(by_chip.items()) if len(v) >= 5][:n_chips]
    if not picks:
        print("  no chip with five parcels found, skipping sparsity figure")
        return

    fig, axes = plt.subplots(1, len(picks), figsize=(4.0 * len(picks), 4.9))
    if len(picks) == 1:
        axes = [axes]

    for ax, chip in zip(axes, picks):
        with rasterio.open(F.IMG_A / chip) as s:
            arr = s.read(bands)
            w = s.width
        inst, c2, c3, full = F.load_labels(chip)
        ax.imshow(stretch(arr))
        ax.contour((full > 0).astype(float), levels=[0.5],
                   colors="white", linewidths=1.3)
        ax.set_title(f"{chip}, {w * px_m / 1000.0:.2f} km across\n"
                     f"{len(by_chip[chip])} parcels drawn, "
                     f"{(full > 0).mean() * 100:.2f}% of pixels labelled",
                     fontsize=9, linespacing=1.35)
        ax.set_xticks([])
        ax.set_yticks([])

    cov = coverage()
    if cov and cov["unlabelled"] > 0.5:
        fig.suptitle("Five parcels per chip, and nothing said about the rest",
                     fontsize=13, y=0.975)
        stat = (f"Interiors cover {cov['interior'] * 100:.2f}% of pixels "
                f"across all {cov['chips']:,} chips and the boundary rings a "
                f"further {cov['ring'] * 100:.2f}%. The remaining "
                f"{cov['unlabelled'] * 100:.2f}% is coded 3, unlabelled, and "
                f"it is plainly full of fields.")
        tail = ("Scoring it as background would penalise a model for finding "
                "real parcels, which is why recall is measurable on this "
                "dataset and precision is not.")
    else:
        fig.suptitle(f"Every parcel drawn: FTW {F.COUNTRY.capitalize()}",
                     fontsize=13, y=0.975)
        c = cov or {"interior": 0, "ring": 0, "unlabelled": 0, "chips": 0}
        stat = (f"Interiors cover {c['interior'] * 100:.2f}% of pixels across "
                f"{c['chips']:,} chips, boundary rings {c['ring'] * 100:.2f}%, "
                f"and only {c['unlabelled'] * 100:.2f}% is unlabelled.")
        tail = ("With the ground verified rather than merely unlabelled, "
                "precision means what it usually means here, which is what "
                "makes this a control.")
    note = ("White outlines are the labelled parcels.\n" + stat + "\n" + tail)
    fig.text(0.5, 0.045, note, ha="center", fontsize=8, linespacing=1.6)
    fig.text(0.5, 0.008, F.SOURCE, ha="center", fontsize=7, color="0.35")

    fig.subplots_adjust(left=0.02, right=0.98, top=0.835, bottom=0.215,
                        wspace=0.06)
    F.FIGURES.mkdir(parents=True, exist_ok=True)
    out = F.FIGURES / "chip_sparsity.png"
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"  wrote {out.relative_to(F.PROJECT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bands", default="4,3,2")
    ap.add_argument("--pixel", type=float, default=0.0,
                    help="override the measured grid pixel, metres")
    args = ap.parse_args()

    bands = [int(x) for x in args.bands.split(",")]
    rows = load_fields()
    px_m = args.pixel or F.grid_pixel_m()
    print(f"Drawing from {len(rows):,} measured parcels, "
          f"grid pixel {px_m:.3f} m.\n")

    chosen = field_scale_figure(rows, bands, px_m)
    sparsity_figure(rows, bands, px_m)

    print("\n  parcels drawn:")
    for q, r in chosen:
        print(f"    p{q:<3} {r['chip']} id {r['parcel_id']:<5}"
              f"{r['full_ha']:.3f} ha full, {r['interior_ha']:.3f} ha "
              f"interior only, {r['full_native_px']:.0f} native px")

    print("\nCheck two things in field_scale.png: that vegetation reads red,")
    print("and that the middle row looks coarser than the top. If either")
    print("fails, an assumption behind it is wrong.")


if __name__ == "__main__":
    main()
