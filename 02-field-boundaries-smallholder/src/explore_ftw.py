"""
RS-02 / step 1, corrected. Look at the data before modelling it.

This replaces an earlier version of this script that got three things wrong,
recorded here because the corrections matter more than the original run:

  1. It sampled GeoTIFFs alphabetically and read 200 instance label masks
     while reporting them as "the imagery". The chip geometry it printed was
     a label mask's.

  2. It looked for label rasters by filename. FTW puts them in a folder called
     label_masks and names the files after the chip, so it found none.

  3. It read chips_india.parquet as field polygons. That file is the chip
     index, one row per chip. The "field areas" it printed, 235 to 236 ha with
     almost no spread, were chip footprints. A field size distribution is
     never that flat, which is the tell.

What it does now
----------------
Field size is measured from the instance masks rather than from vectors. Each
mask holds a field ID per pixel on the grid the model will actually see, so
counting pixels per ID answers the question directly, with no projection step
in between to get wrong. Fields touching a chip edge are counted separately,
since a truncated field understates its own size.

Ground pixel size is measured geodesically from each chip's own transform,
not inferred from a printed bounding box.

The number this exists to produce is still the field size distribution in
PIXELS, because that decides whether this project is about a model or about a
resolution limit.

Nothing is written. This only reads and prints.

    python src\\explore_ftw.py
    python src\\explore_ftw.py --chips 500
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

CANDIDATES = [
    PROJECT / "data" / "ftw",
    PROJECT / "data",
    Path.cwd() / "data" / "ftw",
]

RULE = "=" * 78


def find_root(explicit):
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            sys.exit(f"{p} does not exist.")
        return p
    for p in CANDIDATES:
        if p.exists() and (p / "india").exists():
            return p
    for p in CANDIDATES:
        if p.exists() and any(p.iterdir()):
            return p
    sys.exit("Could not find the data. Looked in:\n  "
             + "\n  ".join(str(c) for c in CANDIDATES))


def human(n):
    for u, d in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= d:
            return f"{n / d:,.1f} {u}"
    return f"{n:,.0f} B"


def pct(x):
    return f"{x * 100:.1f}%"


# --------------------------------------------------------------- A. inventory
def inventory(root):
    print(RULE)
    print("A. WHAT ARRIVED, BY FOLDER")
    print(RULE)
    print(f"root: {root}\n")

    groups = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        key = "/".join(rel.parts[:-1]) or "."
        n, sz = groups.get(key, (0, 0))
        groups[key] = (n + 1, sz + p.stat().st_size)

    print(f"  {'folder':<38}{'files':>8}{'size':>12}")
    total_n = total_s = 0
    for key in sorted(groups):
        n, sz = groups[key]
        total_n += n
        total_s += sz
        print(f"  {key:<38}{n:>8,}{human(sz):>12}")
    print(f"  {'total':<38}{total_n:>8,}{human(total_s):>12}")
    return groups


def pick(root, sub, limit=None):
    d = root / sub
    if not d.exists():
        return []
    out = sorted(d.glob("*.tif"))
    return out[:limit] if limit else out


# --------------------------------------------------------------- B. imagery
def imagery(root):
    print("\n" + RULE)
    print("B. THE SENTINEL-2 CHIPS, READ FROM THE IMAGE FOLDER")
    print(RULE)

    import numpy as np
    import rasterio
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    out = {}

    for window in ("s2_images/window_a", "s2_images/window_b"):
        files = pick(root, window, 60)
        if not files:
            print(f"  {window}: nothing found")
            continue
        shapes, bands, dtypes, crs = Counter(), Counter(), Counter(), Counter()
        gx, gy = [], []
        for p in files:
            with rasterio.open(p) as s:
                shapes[(s.height, s.width)] += 1
                bands[s.count] += 1
                dtypes[s.dtypes[0]] += 1
                crs[str(s.crs)] += 1
                l, b, r, t = s.bounds
                midlat, midlon = (b + t) / 2, (l + r) / 2
                if s.crs and s.crs.to_epsg() == 4326:
                    _, _, w_m = geod.inv(l, midlat, r, midlat)
                    _, _, h_m = geod.inv(midlon, b, midlon, t)
                else:
                    w_m = abs(r - l)
                    h_m = abs(t - b)
                gx.append(w_m / s.width)
                gy.append(h_m / s.height)

        print(f"\n  {window}   ({len(files)} chips read)")
        for name, c in (("chip size (h, w)", shapes), ("bands", bands),
                        ("dtype", dtypes), ("CRS", crs)):
            top = ", ".join(f"{k} x{v}" for k, v in c.most_common(3))
            print(f"    {name:<20}{top}")
        gx, gy = np.array(gx), np.array(gy)
        print(f"    {'ground pixel size':<20}"
              f"{gx.mean():.2f} m across, {gy.mean():.2f} m down")
        print(f"    {'':<20}range {gx.min():.2f} to {gx.max():.2f} m")
        h, w = shapes.most_common(1)[0][0]
        print(f"    {'chip covers':<20}"
              f"{gx.mean() * w / 1000:.2f} x {gy.mean() * h / 1000:.2f} km")
        out[window] = float(gx.mean())

        with rasterio.open(files[0]) as s:
            a = s.read()
            print(f"    first chip {files[0].name}: "
                  f"{s.count} bands, {s.dtypes[0]}")
            for i in range(min(s.count, 8)):
                band = a[i]
                print(f"      band {i + 1}: min {band.min():>6}, "
                      f"max {band.max():>6}, mean {band.mean():>8.1f}")

    if out:
        m = sum(out.values()) / len(out)
        print(f"\n  Measured pixel size is about {m:.1f} m.")
        if m < 8:
            print("  That is finer than Sentinel-2's native 10 m, so the chips")
            print("  have been resampled onto a common grid. Every pixel-count")
            print("  figure below is on THIS grid, and converting to metres")
            print("  uses this number rather than 10.")
        elif m > 12:
            print("  That is coarser than Sentinel-2's native 10 m.")
        else:
            print("  That is Sentinel-2's native 10 m grid.")
    return out


# --------------------------------------------------------------- C. labels
def labels(root, n_chips):
    print("\n" + RULE)
    print("C. WHAT IS IN THE LABEL RASTERS")
    print(RULE)

    import numpy as np
    import rasterio

    for sub in ("label_masks/instance", "label_masks/semantic_2class",
                "label_masks/semantic_3class"):
        files = pick(root, sub, 120)
        if not files:
            print(f"  {sub}: nothing found")
            continue
        vals, shapes, dtypes = Counter(), Counter(), Counter()
        for p in files:
            with rasterio.open(p) as s:
                a = s.read(1)
                shapes[(s.height, s.width)] += 1
                dtypes[s.dtypes[0]] += 1
                u = np.unique(a)
                if len(u) <= 12:
                    vals.update(int(v) for v in u)
                else:
                    vals.update(["(many distinct values)"])
        print(f"\n  {sub}   ({len(files)} chips read)")
        print(f"    shape   {shapes.most_common(1)[0][0]}")
        print(f"    dtype   {dtypes.most_common(1)[0][0]}")
        shown = ", ".join(f"{k} in {v}" for k, v in vals.most_common(10))
        print(f"    values  {shown}")


# ------------------------------------------------- D. field size, the point
def field_sizes(root, n_chips, px_m):
    print("\n" + RULE)
    print("D. FIELD SIZE IN PIXELS, COUNTED FROM THE INSTANCE MASKS")
    print(RULE)

    import numpy as np
    import rasterio

    files = pick(root, "label_masks/instance")
    if not files:
        print("  no instance masks found")
        return
    files = files[:n_chips]
    print(f"  reading {len(files):,} instance masks\n")

    interior, edge = [], []
    per_chip, labelled_frac = [], []
    empty = 0

    for p in files:
        with rasterio.open(p) as s:
            a = s.read(1)
        if a.max() == 0:
            empty += 1
            per_chip.append(0)
            labelled_frac.append(0.0)
            continue
        ids, counts = np.unique(a[a > 0], return_counts=True)
        per_chip.append(len(ids))
        labelled_frac.append(float((a > 0).sum()) / a.size)

        border = set(np.unique(a[0, :]).tolist())
        border |= set(np.unique(a[-1, :]).tolist())
        border |= set(np.unique(a[:, 0]).tolist())
        border |= set(np.unique(a[:, -1]).tolist())
        border.discard(0)

        for fid, cnt in zip(ids.tolist(), counts.tolist()):
            (edge if fid in border else interior).append(cnt)

    interior = np.array(interior, dtype=float)
    edge = np.array(edge, dtype=float)
    per_chip = np.array(per_chip, dtype=float)
    labelled_frac = np.array(labelled_frac, dtype=float)

    print(f"  fields found        {len(interior) + len(edge):,}")
    print(f"    fully inside      {len(interior):,}")
    print(f"    touching an edge  {len(edge):,}  "
          f"(truncated, so their size is a floor not a measurement)")
    print(f"  chips with no label {empty:,} of {len(files):,}")
    print(f"  fields per chip     median {np.median(per_chip):.0f}, "
          f"mean {per_chip.mean():.1f}, max {per_chip.max():.0f}")
    print(f"  share of chip pixels carrying a field ID: "
          f"median {pct(float(np.median(labelled_frac)))}, "
          f"mean {pct(float(labelled_frac.mean()))}")

    if len(interior) == 0:
        print("\n  every field touches an edge, so no clean size measurement")
        return

    print(f"\n  field size in PIXELS, fields fully inside a chip")
    ha_per_px = (px_m ** 2) / 10_000.0

    def row(label, v):
        print(f"    {label:<5}{v:>9,.0f} px   "
              f"= {v ** 0.5:>5.1f} px on a side if square"
              f"   = {v * ha_per_px:>8.2f} ha")

    for q in (5, 25, 50, 75, 95):
        row(f"p{q}", float(np.percentile(interior, q)))
    row("mean", float(interior.mean()))
    print(f"\n  (converted at the measured {px_m:.2f} m pixel, "
          f"{ha_per_px:.4f} ha per pixel)")

    print(f"\n  share of interior fields below a given pixel count:")
    for n in (4, 9, 16, 25, 50, 100, 400, 1000):
        side = n ** 0.5
        print(f"    under {n:>5} px ({side:>4.0f} x {side:<4.0f}): "
              f"{pct(float((interior < n).mean())):>7}")

    print("\n  A boundary needs an interior that survives after the edge pixels")
    print("  are spent. A field of 25 pixels is 5 by 5 and its whole perimeter")
    print("  is edge. Read the table above for how much of this reference set")
    print("  lives in that regime, because that is the subject of the project")
    print("  rather than a caveat at the end of it.")


# --------------------------------------------------------------- E. the index
def chip_index(root):
    print("\n" + RULE)
    print("E. THE CHIP INDEX AND THE SPLITS")
    print(RULE)
    files = list(root.rglob("*.parquet"))
    if not files:
        print("  no parquet found")
        return
    src = files[0]
    try:
        import geopandas as gpd
        gdf = gpd.read_parquet(src)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  could not read {src.name}: {exc}")
        return
    print(f"  {src.name}: {len(gdf):,} rows")
    print(f"  columns: {', '.join(map(str, gdf.columns))}\n")
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        u = gdf[col].nunique(dropna=True)
        if u <= 12:
            counts = gdf[col].value_counts(dropna=False)
            shown = ", ".join(f"{k}: {v:,}" for k, v in counts.items())
            print(f"  {col:<22}{shown}")
        else:
            print(f"  {col:<22}{u:,} distinct values")
    print("\n  One row per chip. This is the file the earlier version of this")
    print("  script mistook for field polygons.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="")
    ap.add_argument("--chips", type=int, default=400,
                    help="how many instance masks to count fields in")
    args = ap.parse_args()

    root = find_root(args.root)
    if (root / "india").exists():
        root = root / "india"

    inventory(root)
    px = imagery(root)
    px_m = (sum(px.values()) / len(px)) if px else 10.0
    labels(root, args.chips)
    field_sizes(root, args.chips, px_m)
    chip_index(root)

    print("\n" + RULE)
    print("Nothing was written. Section D is the one that decides the shape")
    print("of this project. Section B decides what a pixel is worth in metres.")
    print(RULE)


if __name__ == "__main__":
    main()
