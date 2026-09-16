"""
RS-02. Is it area that beats the model, or the narrow dimension of a parcel?

The size curve says recall climbs with parcel area. The pictures say something
more specific. In Slovenia, parcels of 29 and 54 native pixels score zero while
a 148 pixel parcel scores IoU 0.852, and the difference is shape: the failures
are strip fields, long and a few pixels wide. In India the smallest parcels sit
inside crops the model has painted entirely as boundary, with no interior left
anywhere.

Both point at the same mechanism. The 3-class model spends one to two pixels on
each side of a parcel calling them boundary. A parcel three pixels across has
nothing left in the middle. Area hides this, because a 3 by 20 strip and an
8 by 8 block have the same area and completely different fates.

So this measures each parcel's narrow dimension directly, as twice the largest
circle that fits inside it, and asks which of the two predicts whether the
model found it.

    width      pixels across the parcel at its widest inscribed circle,
               converted to native 10 m px
    area       what the size curve already used

Also reported: how often the model saturates, calling most of a chip boundary
and leaving no interior to match against. That is a different failure from a
poorly traced parcel and it deserves its own number.

Reads score_parcels_<n>class<tag>.csv, so run score_predictions.py first.

Writes, under results/<country>/:
    parcel_width_<n>class<tag>.csv
and figures/recall_by_width_<n>class<tag>.png across countries.

    python src\\analyse_width.py
    python src\\analyse_width.py --classes 3 --tag _full
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78

WIDTH_BINS = [(0, 2, "under 2"), (2, 3, "2 to 3"), (3, 4, "3 to 4"),
              (4, 5, "4 to 5"), (5, 7, "5 to 7"), (7, 10, "7 to 10"),
              (10, 15, "10 to 15"), (15, 10 ** 6, "over 15")]

AREA_BINS = [(0, 4, "under 4"), (4, 9, "4 to 9"), (9, 16, "9 to 16"),
             (16, 25, "16 to 25"), (25, 49, "25 to 49"),
             (49, 100, "49 to 100"), (100, 400, "100 to 400"),
             (400, 10 ** 9, "over 400")]


def pct(x):
    return f"{x * 100:.1f}%"


def load_scores(classes, tag):
    p = F.RESULTS / f"score_parcels_{classes}class{tag}.csv"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["native_10m_px"] = float(r["native_10m_px"])
        r["best_iou"] = float(r["best_iou"])
        r["found"] = int(r["found"])
        r["parcel_id"] = int(r["parcel_id"])
    return rows


def widths_for_country(rows, px_m):
    """Twice the largest inscribed circle, per parcel, in native 10 m pixels."""
    from scipy.ndimage import distance_transform_edt

    by_chip = {}
    for r in rows:
        by_chip.setdefault(r["chip"], []).append(r)

    scale = px_m / F.NATIVE_M          # grid px -> native px
    out = []
    for i, (chip, recs) in enumerate(sorted(by_chip.items())):
        if i and i % 100 == 0:
            print(f"    {i:,} chips")
        inst, c2, c3, full = F.load_labels(chip)
        for r in recs:
            m = full == r["parcel_id"]
            if not m.any():
                r["width_native_px"] = 0.0
                out.append(r)
                continue
            # pad so a parcel touching the array edge is not treated as
            # continuing beyond it
            pad = np.pad(m, 1, constant_values=False)
            d = distance_transform_edt(pad)
            # 2d - 1 recovers the pixel count across: a 3-wide strip has
            # a centre pixel 2 from the padding, so 2*2-1 = 3.
            grid_w = max(1.0, float(d.max()) * 2.0 - 1.0)
            r["width_native_px"] = round(grid_w * scale, 3)
            out.append(r)
    return out


def saturation(country, classes, tag):
    """How often the model calls most of a chip boundary."""
    man = F.RESULTS / f"inference_manifest_{classes}class{tag}.csv"
    if not man.exists():
        return None
    with open(man, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    tot = 65536.0
    bnd = np.array([int(r["pred_boundary_px"]) for r in rows]) / tot
    fld = np.array([int(r["pred_field_px"]) for r in rows]) / tot
    return {
        "country": country,
        "chips": len(rows),
        "median_boundary_share": round(float(np.median(bnd)), 4),
        "median_field_share": round(float(np.median(fld)), 4),
        "chips_over_half_boundary": int((bnd > 0.5).sum()),
        "chips_no_field_at_all": int((fld == 0).sum()),
    }


def table(rows, key, bins, label):
    v = np.array([r[key] for r in rows])
    found = np.array([r["found"] for r in rows], dtype=bool)
    iou = np.array([r["best_iou"] for r in rows])
    print(f"\n    {label:<14}{'parcels':>9}{'found':>9}{'median IoU':>12}")
    out = []
    for lo, hi, name in bins:
        m = (v >= lo) & (v < hi)
        if m.sum() < 5:
            continue
        print(f"    {name:<14}{int(m.sum()):>9,}{pct(float(found[m].mean())):>9}"
              f"{np.median(iou[m]):>12.3f}")
        out.append({"bin": name, "lo": lo, "hi": hi if hi < 10 ** 5 else "",
                    "parcels": int(m.sum()),
                    "recall": round(float(found[m].mean()), 4),
                    "median_iou": round(float(np.median(iou[m])), 4)})
    return out


def separation(rows, key):
    """How cleanly does this variable split found from missed."""
    v = np.array([r[key] for r in rows], dtype=float)
    f = np.array([r["found"] for r in rows], dtype=bool)
    if f.sum() < 5 or (~f).sum() < 5:
        return None
    # point-biserial correlation on log scale, since both span decades
    lv = np.log10(np.maximum(v, 1e-3))
    r = float(np.corrcoef(lv, f.astype(float))[0, 1])
    return {"corr_log": round(r, 3),
            "median_found": round(float(np.median(v[f])), 2),
            "median_missed": round(float(np.median(v[~f])), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="india,slovenia")
    ap.add_argument("--classes", type=int, default=3)
    ap.add_argument("--tag", default="_full")
    args = ap.parse_args()

    print(RULE)
    print(f"PARCEL WIDTH AGAINST PARCEL AREA, "
          f"{args.classes}-class{args.tag}")
    print(RULE)

    all_rows, sats = [], []
    import importlib
    import os

    for country in [c.strip() for c in args.countries.split(",") if c.strip()]:
        os.environ["FTW_COUNTRY"] = country
        importlib.reload(F)
        rows = load_scores(args.classes, args.tag)
        if not rows:
            print(f"\n  {country}: no scores, skipping")
            continue
        rows = [r for r in rows if r["country"] == country]
        px_m = F.grid_pixel_m()
        print(f"\n  {country}: {len(rows):,} parcels, grid pixel {px_m:.3f} m")
        rows = widths_for_country(rows, px_m)

        table(rows, "width_native_px", WIDTH_BINS,
              "width, native px")
        table(rows, "native_10m_px", AREA_BINS, "area, native px")

        sw = separation(rows, "width_native_px")
        sa = separation(rows, "native_10m_px")
        if sw and sa:
            print(f"\n    how cleanly each splits found from missed")
            print(f"      width  correlation {sw['corr_log']:+.3f}   "
                  f"median found {sw['median_found']:.1f} px, "
                  f"missed {sw['median_missed']:.1f} px")
            print(f"      area   correlation {sa['corr_log']:+.3f}   "
                  f"median found {sa['median_found']:.0f} px, "
                  f"missed {sa['median_missed']:.0f} px")

        out = F.RESULTS / f"parcel_width_{args.classes}class{args.tag}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"    wrote {out.relative_to(F.PROJECT)}  ({len(rows):,} rows)")

        s = saturation(country, args.classes, args.tag)
        if s:
            sats.append(s)
        all_rows.extend(rows)

    if sats:
        print("\n" + RULE)
        print("BOUNDARY SATURATION")
        print(RULE)
        print(f"  {'country':<12}{'median boundary':>17}{'median field':>15}"
              f"{'chips >50% bnd':>17}{'chips no field':>16}")
        for s in sats:
            print(f"  {s['country']:<12}{pct(s['median_boundary_share']):>17}"
                  f"{pct(s['median_field_share']):>15}"
                  f"{s['chips_over_half_boundary']:>10,} of {s['chips']:<4}"
                  f"{s['chips_no_field_at_all']:>16,}")
        print("\n  A chip that is mostly boundary has no interior anywhere, so")
        print("  no parcel in it can be matched at any IoU threshold. That is a")
        print("  different failure from tracing a parcel badly.")
        p = F.PROJECT / "results" / f"saturation_{args.classes}class{args.tag}.csv"
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sats[0]))
            w.writeheader()
            w.writerows(sats)
        print(f"\n  wrote {p.relative_to(F.PROJECT)}")

    if all_rows:
        figure(all_rows, args.classes, args.tag)

    print("\n" + RULE)
    print("If width separates found from missed more cleanly than area, then")
    print("the limit is how many pixels sit across a parcel rather than how")
    print("many are in it, and a strip field fails for the same reason a")
    print("smallholding does.")
    print(RULE)


def figure(rows, classes, tag):
    countries = sorted({r["country"] for r in rows})
    colours = {"india": "#c0562a", "slovenia": "#2f6f8f"}
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))

    for ax, key, bins, xlab, title in (
            (axes[0], "width_native_px", WIDTH_BINS,
             "parcel width, native 10 m px",
             "Against how many pixels lie across it"),
            (axes[1], "native_10m_px", AREA_BINS,
             "parcel area, native 10 m px",
             "Against how many pixels are in it")):
        for c in countries:
            rs = [r for r in rows if r["country"] == c]
            v = np.array([r[key] for r in rs], dtype=float)
            f = np.array([r["found"] for r in rs], dtype=bool)
            xs, ys = [], []
            for i, (lo, hi, _) in enumerate(bins):
                m = (v >= lo) & (v < hi)
                if m.sum() < 5:
                    continue
                xs.append(i)
                ys.append(f[m].mean() * 100)
            ax.plot(xs, ys, "o-", color=colours.get(c, "#666"),
                    label=f"{c} ({len(rs):,})")
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels([b[2] for b in bins], rotation=35, ha="right",
                           fontsize=8)
        ax.set_xlabel(xlab, fontsize=9)
        ax.set_ylabel("parcels found, %", fontsize=9)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(-2, 102)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, frameon=False)

    fig.suptitle(f"What limits delineation: width or area "
                 f"({classes}-class {tag.strip('_') or 'CC-BY'})",
                 fontsize=12, y=0.99)
    fig.text(0.5, 0.015,
             "Width is the pixel count across the largest circle that fits "
             "inside the parcel. "
             "A 3 by 20 strip and an 8 by 8 block hold the same area and "
             "behave differently,\nbecause the 3-class model spends one to two "
             "pixels a side calling them boundary and the strip has no middle "
             "left.",
             ha="center", fontsize=8, linespacing=1.6)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.87, bottom=0.30,
                        wspace=0.22)

    out = F.PROJECT / "figures" / f"recall_by_width_{classes}class{tag}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    print(f"\n  wrote {out.relative_to(F.PROJECT)}")


if __name__ == "__main__":
    main()
