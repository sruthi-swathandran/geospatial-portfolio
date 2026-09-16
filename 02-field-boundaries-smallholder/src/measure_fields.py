"""
RS-02. Measure every parcel once and write it down.

Two corrections are baked in here, both found by running the code on a second
country after it looked right on the first.

  The ring is semantic_3class == 2, not semantic_2class == 0. The 2-class mask
  collapses background and boundary into one value. In India there is no
  background so the two agree; in Slovenia 2class==0 is 87% of the chip and
  keying off it dilated every parcel three pixels into open ground.

  Parcels touching a chip edge are truncated, so their measured size is a
  floor. India has none. Slovenia has 22,158 of 69,435. They are reported
  separately rather than mixed into one distribution.

Writes, under results/<country>/:
    field_sizes.csv      one row per parcel, interior and reconstructed
    label_coverage.csv   one row per chip, pixel counts by 3-class value
    ring_check.csv       ring area within 1, 2 and 3 dilation steps

    python src\\measure_fields.py
    python src\\measure_fields.py --limit 200      quick trial
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftw_common as F                                        # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

RULE = "=" * 78


def pct(x):
    return f"{x * 100:.2f}%"


def scan(names, px_m):
    ha_per_px = (px_m ** 2) / 10_000.0
    m2_native = F.NATIVE_M ** 2

    fields, coverage = [], []
    orphan_total = 0
    print(f"\n  scanning {len(names):,} chips")

    for i, name in enumerate(names):
        if i and i % 400 == 0:
            print(f"    {i:,} done")

        inst, c2, c3, full, orphans = F.load_labels(name, return_orphans=True)
        orphan_total += orphans

        row = {
            "chip": name,
            "pixels": int(inst.size),
            "interior_px": int((c3 == F.C3_INTERIOR).sum()),
            "boundary_px": int((c3 == F.C3_BOUNDARY).sum()),
            "background_px": int((c3 == F.C3_BACKGROUND).sum()),
            "unlabelled_px": int((c3 == F.C3_UNLABELLED).sum()),
            "n_parcels": 0,
        }

        if inst.max() > 0:
            ids = np.unique(inst[inst > 0])
            row["n_parcels"] = len(ids)

            border = set(np.unique(full[0, :]).tolist())
            border |= set(np.unique(full[-1, :]).tolist())
            border |= set(np.unique(full[:, 0]).tolist())
            border |= set(np.unique(full[:, -1]).tolist())
            border.discard(0)

            for fid in ids.tolist():
                in_px = int((inst == fid).sum())
                fu = (full == fid)
                fu_px = int(fu.sum())
                ys, xs = np.where(fu)
                full_ha = fu_px * ha_per_px
                fields.append({
                    "chip": name,
                    "parcel_id": fid,
                    "interior_px": in_px,
                    "full_px": fu_px,
                    "interior_ha": round(in_px * ha_per_px, 5),
                    "full_ha": round(full_ha, 5),
                    "full_native_px": round(full_ha * 10_000.0 / m2_native, 2),
                    "bbox_h": int(ys.max() - ys.min() + 1),
                    "bbox_w": int(xs.max() - xs.min() + 1),
                    "row_min": int(ys.min()),
                    "col_min": int(xs.min()),
                    "touches_edge": int(fid in border),
                })
        coverage.append(row)

    return fields, coverage, orphan_total


def ring_distance(names, n=300):
    try:
        from scipy.ndimage import binary_dilation
    except ImportError:
        print("  scipy not available, skipping the ring check")
        return []
    tot = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    for name in names[:n]:
        inst, c2, c3, _ = F.load_labels(name)
        field = inst > 0
        ring = c3 == F.C3_BOUNDARY
        r_total = int(ring.sum())
        if not r_total or not field.any():
            continue
        for k in (1, 2, 3):
            grown = binary_dilation(field, iterations=k) & ~field
            tot[k][0] += int((ring & grown).sum())
            tot[k][1] += r_total
    return [{"dilation_px": k, "ring_pixels": tot[k][1],
             "within_dilation": tot[k][0],
             "share": round(tot[k][0] / tot[k][1], 4)}
            for k in (1, 2, 3) if tot[k][1]]


def write_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(F.PROJECT)}  ({len(rows):,} rows)")


def size_table(label, ha_full, ha_int, native):
    print(f"\n  {label}  ({len(ha_full):,} parcels)")
    print(f"  {'':<7}{'interior ha':>13}{'full ha':>11}"
          f"{'native 10 m px':>17}{'side':>8}")
    for q in (1, 5, 25, 50, 75, 95, 99):
        print(f"  p{q:<6}{np.percentile(ha_int, q):>13.3f}"
              f"{np.percentile(ha_full, q):>11.3f}"
              f"{np.percentile(native, q):>17.0f}"
              f"{np.percentile(native, q) ** 0.5:>8.1f}")
    print(f"  {'mean':<7}{ha_int.mean():>13.3f}{ha_full.mean():>11.3f}"
          f"{native.mean():>17.0f}{native.mean() ** 0.5:>8.1f}")


def report(fields, coverage, rings, px_m, orphans):
    full = np.array([f["full_ha"] for f in fields])
    interior = np.array([f["interior_ha"] for f in fields])
    native = np.array([f["full_native_px"] for f in fields])
    edge = np.array([f["touches_edge"] for f in fields], dtype=bool)
    nf = np.array([c["n_parcels"] for c in coverage], dtype=float)

    print("\n" + RULE)
    print("PARCEL SIZE, WITH THE ERODED BOUNDARY GIVEN BACK")
    print(RULE)
    print(f"  {len(fields):,} parcels across {len(coverage):,} chips")
    print(f"  parcels per chip: median {np.median(nf):.0f}, "
          f"mean {nf.mean():.2f}, max {nf.max():.0f}, "
          f"chips with none {int((nf == 0).sum()):,}")
    print(f"  grid pixel {px_m:.3f} m, native Sentinel-2 pixel "
          f"{F.NATIVE_M:.0f} m")
    print(f"  touching a chip edge: {int(edge.sum()):,} "
          f"({pct(edge.mean())}), truncated so their size is a floor")
    if orphans:
        print(f"  ring pixels beyond {F.MAX_RING_DIST:.0f} px of any interior, "
              f"left unassigned: {orphans:,}")

    keep = ~edge
    if keep.sum():
        size_table("parcels fully inside a chip, THE HONEST SET",
                   full[keep], interior[keep], native[keep])
    if edge.sum():
        size_table("all parcels including truncated ones",
                   full, interior, native)

    use = native[keep] if keep.sum() else native
    lift = (full[keep].sum() / interior[keep].sum()) if keep.sum() else 1.0
    print(f"\n  giving the ring back raises parcel area by "
          f"{(lift - 1) * 100:.1f}%")

    print(f"\n  share of untruncated parcels below a given NATIVE pixel count")
    for k in (4, 9, 16, 25, 49, 100, 400):
        side = int(round(k ** 0.5))
        box = f"({side} x {side})"
        print(f"    under {k:>4} px {box:<9}{pct(float((use < k).mean())):>9}"
              f"   = under {k / 100:>5.2f} ha")

    print("\n" + RULE)
    print("LABEL COVERAGE, FROM semantic_3class")
    print(RULE)
    tp = sum(c["pixels"] for c in coverage)
    parts = [("parcel interior", "interior_px"),
             ("boundary ring", "boundary_px"),
             ("verified background", "background_px"),
             ("unlabelled", "unlabelled_px")]
    for label, key in parts:
        v = sum(c[key] for c in coverage)
        print(f"  {label:<22}{v:>14,}  {pct(v / tp)}")
    comb = sum(c["interior_px"] + c["boundary_px"] for c in coverage)
    print(f"  {'parcel, combined':<22}{comb:>14,}  {pct(comb / tp)}")
    print(f"  {'total':<22}{tp:>14,}")

    unlab = sum(c["unlabelled_px"] for c in coverage) / tp
    print()
    if unlab > 0.5:
        print("  Presence-only. No ground anywhere is certified field-free, so")
        print("  recall and boundary agreement are measurable and precision is")
        print("  not.")
    else:
        print("  Complete labels. Background is verified rather than merely")
        print("  unlabelled, so precision means what it usually means.")

    if rings:
        print("\n" + RULE)
        print("HOW FAR THE RING SITS FROM ITS PARCEL")
        print(RULE)
        for r in rings:
            print(f"  within {r['dilation_px']} px: {pct(r['share'])} "
                  f"of the ring area")
        print("\n  This dilates with a 4-connected element, so a ring ONE pixel")
        print("  thick still registers partly at two steps. Read thickness off")
        print("  ring_thickness.py, which measures exact Euclidean distance.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print(f"Measuring every parcel in the FTW {F.COUNTRY} subset.\n")
    names = F.chip_names()
    if args.limit:
        names = names[:args.limit]
    px_m = F.grid_pixel_m(names)
    print(f"  grid pixel measured over {min(80, len(names))} chips: "
          f"{px_m:.3f} m")

    fields, coverage, orphans = scan(names, px_m)
    rings = ring_distance(names)

    print()
    write_csv(F.RESULTS / "field_sizes.csv", fields)
    write_csv(F.RESULTS / "label_coverage.csv", coverage)
    write_csv(F.RESULTS / "ring_check.csv", rings)

    report(fields, coverage, rings, px_m, orphans)

    print("\n" + RULE)
    print("Next: python src\\figure_field_scale.py")
    print(RULE)


if __name__ == "__main__":
    main()
