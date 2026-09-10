"""
How often the classifier called flood inside the swath-edge buffer, against
how often it did so in the interior.

The README and the public page have both said "flood classification ran at 17%
of area against 1.9% in the interior" since the full-scene stage was written.
Neither figure appears anywhere in results/ and no script computes them, so
they were a recollection rather than a measurement. verify_all.py section A2
is what surfaced that, because it traces the page against results/ and those
two numbers had nothing to trace to.

This measures it.

Definition
----------
full_scene.py classifies the whole imaged swath. refine_scene.py then sets a
600 m band inside the swath boundary to no data, on the argument that
classification there is dominated by the range-edge brightness roll-off rather
than by water. The band is therefore exactly:

    buffer   = imaged in the raw map, no data in the refined map
    interior = still imaged in the refined map

Both rates are read off the RAW map, because the question is what the
classifier did before anything was removed. Reading the buffer rate off the
refined map would return zero by construction.

Outputs:
    results/edge_rate.csv

Run:
    python 01-sentinel1-flood-extent\\src\\edge_rate.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                                          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                             # noqa: BLE001
    pass

LAND, FLOOD, PERM, ND = 0, 1, 2, 255
RES_M = 20.0
SCENE = cfg.RESULTS / "fullscene"

VARIANTS = [
    ("", "12 Aug, map-optimal"),
    ("_areamatched", "12 Aug, area-matched"),
    ("_20160807", "7 Aug, map-optimal"),
    ("_20160807am", "7 Aug, area-matched"),
    ("_20160831", "31 Aug, map-optimal"),
    ("_20160831am", "31 Aug, area-matched"),
]


def pair(sfx):
    raw = SCENE / f"{cfg.EVENT}_water_{RES_M:g}m{sfx}.tif"
    ref = SCENE / f"{cfg.EVENT}_water_{RES_M:g}m{sfx}_refined.tif"
    return raw, ref


def measure(raw_p, ref_p, tile=2048):
    """Counts over the buffer and the interior, at full resolution."""
    n = dict(buf=0, buf_flood=0, int=0, int_flood=0)
    with rasterio.open(raw_p) as A, rasterio.open(ref_p) as B:
        if (A.height, A.width) != (B.height, B.width):
            sys.exit(f"grids differ for {raw_p.name}. Nothing written.")
        for i in range(0, A.height, tile):
            for j in range(0, A.width, tile):
                w = Window(j, i, min(tile, A.width - j),
                           min(tile, A.height - i))
                a, b = A.read(1, window=w), B.read(1, window=w)
                imaged = a != ND
                buf = imaged & (b == ND)
                ins = b != ND
                n["buf"] += int(np.count_nonzero(buf))
                n["int"] += int(np.count_nonzero(ins))
                n["buf_flood"] += int(np.count_nonzero(buf & (a == FLOOD)))
                n["int_flood"] += int(np.count_nonzero(ins & (a == FLOOD)))
    return n


def main() -> None:
    px_ha = cfg.pixel_ha(RES_M)
    rows = []

    print("Flood classification rate, swath-edge buffer against interior.")
    print("Both read off the raw map, before refinement.\n")
    print(f"  {'variant':<22}{'buffer ha':>12}{'rate':>8}"
          f"{'interior ha':>14}{'rate':>8}{'ratio':>8}")

    for sfx, label in VARIANTS:
        raw_p, ref_p = pair(sfx)
        if not raw_p.exists() or not ref_p.exists():
            print(f"  {label:<22}  skipped, missing raster")
            continue
        n = measure(raw_p, ref_p)
        if n["buf"] == 0 or n["int"] == 0:
            print(f"  {label:<22}  skipped, empty buffer or interior")
            continue
        br = n["buf_flood"] / n["buf"] * 100
        ir = n["int_flood"] / n["int"] * 100
        print(f"  {label:<22}{n['buf'] * px_ha:>12,.0f}{br:>7.1f}%"
              f"{n['int'] * px_ha:>14,.0f}{ir:>7.1f}%{br / ir:>7.1f}x")
        rows.append({
            "variant": label,
            "buffer_ha": round(n["buf"] * px_ha, 1),
            "buffer_flood_ha": round(n["buf_flood"] * px_ha, 1),
            "buffer_flood_pct": round(br, 2),
            "interior_ha": round(n["int"] * px_ha, 1),
            "interior_flood_ha": round(n["int_flood"] * px_ha, 1),
            "interior_flood_pct": round(ir, 2),
            "ratio": round(br / ir, 2),
        })

    if not rows:
        sys.exit("\nnothing measured. Nothing written.")

    out = cfg.RESULTS / "edge_rate.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out.relative_to(cfg.PROJECT)}")
    print("\nThe buffer is a thin band and the interior is the whole scene, so")
    print("the ratio is the number that carries the argument, not either rate")
    print("on its own.")


if __name__ == "__main__":
    main()
